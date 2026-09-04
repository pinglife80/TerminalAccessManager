"""
ARP Collector Service

Collects ARP data from switches via SSH or API,
processes entries, and triggers compliance checks.
"""

import asyncio
import re
from datetime import UTC
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.terminal import Terminal, TerminalStatus
from app.schemas.data_source import SyncResult


class ArpCollectorService:
    """Service for collecting and processing ARP data"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # SSH Collection
    # ------------------------------------------------------------------
    async def collect_from_ssh(self, source: DataSource) -> SyncResult:
        """
        Collect ARP entries from a switch via SSH.

        Connects to the switch, runs the configured command (e.g. 'show arp'),
        parses the output, and processes the entries.
        """
        import asyncio

        config = source.config
        host = config.get("host", "")
        port = config.get("port", 22)
        username = config.get("username", "")
        password = config.get("password", "")
        command = config.get("command", "show arp")

        def _ssh_collect() -> str:
            """Synchronous SSH operation - runs in thread pool to avoid blocking event loop."""
            from netmiko import ConnectHandler

            # Determine device type from the command pattern
            # Huawei uses 'display', Cisco uses 'show'
            device_type = "autodetect"
            if command.strip().lower().startswith("display"):
                device_type = "huawei"
            elif command.strip().lower().startswith("show"):
                device_type = "cisco_ios"

            device = {
                "device_type": device_type,
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "timeout": 30,
                "conn_timeout": 30,
            }

            # Debug: log connection parameters (mask password)
            masked_pw = password[:2] + "***" + password[-2:] if password and len(password) > 4 else "***"
            logger.info(
                f"netmiko connecting to {host}:{port} as {username}, "
                f"device_type={device_type}, command=[{command}], "
                f"password_masked={masked_pw}"
            )

            # If autodetect, try Huawei first then Cisco
            output = ""
            tried_types = []

            for dtype in [device_type, "huawei", "huawei_vrpv8", "cisco_ios", "cisco_xe"]:
                if dtype == "autodetect":
                    continue
                if dtype in tried_types:
                    continue
                tried_types.append(dtype)

                try:
                    device["device_type"] = dtype
                    logger.info(f"netmiko trying device_type={dtype} for {host}")
                    conn = ConnectHandler(**device)

                    # netmiko's send_command automatically handles:
                    # - Pagination (--More--) by sending space
                    # - Prompt detection
                    # Keep strip_command=False to see command echo for diagnosis
                    output = conn.send_command(
                        command,
                        read_timeout=60,
                        strip_prompt=True,
                        strip_command=False,
                    )
                    conn.disconnect()

                    has_ip = bool(re.search(r'\d+\.\d+\.\d+\.\d+', output))
                    logger.info(
                        f"netmiko device_type={dtype} output length={len(output)}, "
                        f"has_ip={has_ip}, content=[{output[:300]}]"
                    )

                    # If we got output with IP addresses, we're done
                    if output.strip() and re.search(r'\d+\.\d+\.\d+\.\d+', output):
                        break

                except Exception as e:
                    logger.warning(f"netmiko connect with device_type={dtype} failed: {e}")
                    continue

            # Clean up any remaining ANSI escape codes
            output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)

            # Debug: log raw output content for diagnosis
            logger.info(
                f"netmiko final output for {host}: len={len(output)}, "
                f"content=[{output[:300]}]"
            )

            return output

        try:
            # Run blocking SSH operations in a thread pool to avoid blocking the event loop
            output = await asyncio.to_thread(_ssh_collect)

            # Parse ARP table
            entries = self._parse_arp_output(output, source.type)

            if not entries:
                from app.services.data_source_service import DataSourceService
                ds_service = DataSourceService(self.db)
                await ds_service.update_sync_status(source.id, "success")

                logger.warning(
                    f"No ARP entries parsed from '{source.tag}'. "
                    f"Raw output length: {len(output)} chars. "
                    f"First 500 chars: {output[:500]}"
                )

                return SyncResult(
                    success=True,
                    message="No ARP entries found in output",
                    entries_processed=0,
                )

            # Process entries
            result = await self.process_arp_entries(entries, source.tag)

            # Update sync status
            from app.services.data_source_service import DataSourceService
            ds_service = DataSourceService(self.db)
            await ds_service.update_sync_status(source.id, "success")

            return result

        except ImportError:
            error_msg = "netmiko library not installed"
            from app.services.data_source_service import DataSourceService
            ds_service = DataSourceService(self.db)
            await ds_service.update_sync_status(source.id, "failed", error_msg)

            return SyncResult(
                success=False,
                message=error_msg,
                errors=[error_msg],
            )
        except Exception as e:
            error_msg = f"SSH collection failed: {str(e)}"
            logger.error(f"SSH collection failed for '{source.tag}': {str(e)}")

            from app.services.data_source_service import DataSourceService
            ds_service = DataSourceService(self.db)
            await ds_service.update_sync_status(source.id, "failed", error_msg)

            return SyncResult(
                success=False,
                message=error_msg,
                errors=[error_msg],
            )

    # ------------------------------------------------------------------
    # API Collection
    # ------------------------------------------------------------------
    async def collect_from_api(self, source: DataSource) -> SyncResult:
        """
        Collect ARP entries from an HTTP API.

        Makes an HTTP request to the configured URL and parses the JSON response.
        """
        import httpx

        config = source.config
        url = config.get("url", "")
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})

        # Handle authentication
        auth_type = config.get("auth_type", "")
        token = config.get("token", "")
        if auth_type == "bearer" and token:
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "header" and token:
            # Custom header auth: header_name + token
            header_name = config.get("header_name", "X-Auth-Token")
            headers[header_name] = token

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.post(url, headers=headers)

                response.raise_for_status()
                data = response.json()

            # Parse API response - expecting a list of {ip, mac} or {ip_address, mac_address}
            entries = self._parse_api_response(data)

            if not entries:
                from app.services.data_source_service import DataSourceService
                ds_service = DataSourceService(self.db)
                await ds_service.update_sync_status(source.id, "success")

                return SyncResult(
                    success=True,
                    message="No ARP entries found in API response",
                    entries_processed=0,
                )

            # Process entries
            result = await self.process_arp_entries(entries, source.tag)

            # Update sync status
            from app.services.data_source_service import DataSourceService
            ds_service = DataSourceService(self.db)
            await ds_service.update_sync_status(source.id, "success")

            return result

        except Exception as e:
            error_msg = f"API collection failed: {str(e)}"
            logger.error(f"API collection failed for '{source.tag}': {str(e)}")

            from app.services.data_source_service import DataSourceService
            ds_service = DataSourceService(self.db)
            await ds_service.update_sync_status(source.id, "failed", error_msg)

            return SyncResult(
                success=False,
                message=error_msg,
                errors=[error_msg],
            )

    # ------------------------------------------------------------------
    # Process ARP Entries
    # ------------------------------------------------------------------
    async def process_arp_entries(
        self, entries: list[dict], source_tag: str
    ) -> SyncResult:
        """
        Process ARP entries:
        1. Batch upsert to Terminal table (with source_tag) - one record per MAC
        2. Batch compliance check
        3. Update compliance_status
        4. Trigger auto-block (non-blocking)
        """
        added = 0
        updated = 0
        errors = []
        seen_pairs: set[tuple[str, str]] = set()

        for entry in entries:
            ip_addr = entry.get("ip_address", "").strip()
            mac_addr = entry.get("mac_address", "").strip()

            if not ip_addr or not mac_addr:
                continue

            # Normalize MAC address
            mac_normalized = self._normalize_mac(mac_addr)
            if not mac_normalized:
                continue

            mac_norm_key = mac_normalized.replace('-', '').replace(':', '').replace('.', '').upper()

            # Deduplicate within this batch by (MAC, IP) composite identity.
            pair_key = (mac_norm_key, ip_addr)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            try:
                # Upsert by (MAC, IP) composite identity; IP is part of the key.
                stmt = select(Terminal).where(
                    (Terminal.mac_address_normalized == mac_norm_key) &
                    (Terminal.ip_address == ip_addr)
                )
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    from datetime import datetime
                    existing.updated_at = datetime.now(UTC)
                    existing.source_tag = source_tag
                    existing.source = "arp"
                    updated += 1
                else:
                    # Create new entry
                    mac_record = Terminal(
                        ip_address=ip_addr,
                        mac_address=mac_normalized,
                        mac_address_normalized=mac_norm_key,
                        status=TerminalStatus.UNBLOCKED.value,
                        source="arp",
                        source_tag=source_tag,
                        compliance_status="unknown",
                    )
                    self.db.add(mac_record)
                    added += 1
                    from app.services.event_emitter import emit_terminal_online
                    await emit_terminal_online(ip_address=ip_addr, mac_address=mac_normalized)

            except Exception as e:
                errors.append(f"Error processing {ip_addr}/{mac_normalized}: {str(e)}")

        await self.db.commit()

        # Batch compliance check
        try:
            from app.services.compliance_service import ComplianceService
            compliance_service = ComplianceService(self.db)

            # Get all entries from this source that haven't been checked yet
            stmt = select(Terminal).where(
                (Terminal.source_tag == source_tag) &
                (Terminal.compliance_status == "unknown")
            )
            result = await self.db.execute(stmt)
            unchecked_entries = result.scalars().all()

            if unchecked_entries:
                check_entries = [
                    {
                        "ip_address": e.ip_address,
                        "mac_address": e.mac_address,
                        "source_tag": source_tag,
                    }
                    for e in unchecked_entries
                ]

                check_result = await compliance_service.batch_check_compliance(check_entries)

                # Build lookup maps for compliance results, keyed by (normalized MAC, IP)
                # to prevent same-MAC different-IP results from overwriting each other.
                result_lookup = {}
                if check_result.details:
                    for item in check_result.details.get("bypass", []):
                        mac_key = self._normalize_mac(item.get("mac_address", "")).replace('-', '').replace(':', '').replace('.', '').upper()
                        result_lookup[(mac_key, item.get("ip_address", ""))] = {
                            "compliance_status": "bypass",
                            "wl_match_type": item.get("wl_match_type"),
                            "wl_comments": item.get("wl_comments"),
                        }
                    for item in check_result.details.get("compliant", []):
                        mac_key = self._normalize_mac(item.get("mac_address", "")).replace('-', '').replace(':', '').replace('.', '').upper()
                        result_lookup[(mac_key, item.get("ip_address", ""))] = {
                            "compliance_status": "compliant",
                            "wl_match_type": None,
                            "wl_comments": None,
                        }
                    for item in check_result.details.get("non_compliant", []):
                        mac_key = self._normalize_mac(item.get("mac_address", "")).replace('-', '').replace(':', '').replace('.', '').upper()
                        result_lookup[(mac_key, item.get("ip_address", ""))] = {
                            "compliance_status": "non_compliant",
                            "wl_match_type": None,
                            "wl_comments": None,
                        }

                # Apply compliance results for newly discovered (unknown) terminals,
                # with confirm-threshold protection against immediate false blocks.
                for entry in unchecked_entries:
                    mac_key = entry.mac_address_normalized or ""
                    result = result_lookup.get((mac_key, entry.ip_address or ""))
                    if result:
                        await compliance_service.apply_initial_compliance_result(
                            entry,
                            result["compliance_status"],
                            result["wl_match_type"],
                            result["wl_comments"],
                            entry.ip_address or "",
                            entry.mac_address or "",
                        )

                await self.db.commit()

                logger.info(
                    f"Compliance check for source '{source_tag}': "
                    f"{check_result.compliant} compliant, {check_result.bypass} bypass, {check_result.non_compliant} non-compliant"
                )

        except Exception as e:
            logger.error(f"Compliance check failed for source '{source_tag}': {str(e)}")
            errors.append(f"Compliance check failed: {str(e)}")

        # Terminal online/offline detection (based on last-seen timestamp)
        try:
            from app.core.timezone import now_utc
            from app.services.event_emitter import emit_terminal_offline

            all_stmt = select(Terminal).where(Terminal.source_tag == source_tag)
            all_result = await self.db.execute(all_stmt)
            all_terminals = all_result.scalars().all()

            offline_threshold_seconds = 300
            try:
                from app.services.config_service import get_config_value
                interval = await get_config_value("scheduler_arp_collection_interval", 300)
                offline_multiplier = await get_config_value("alert_offline_threshold_multiplier", 3)
                offline_threshold_seconds = interval * offline_multiplier
            except Exception:
                pass

            now_ts = now_utc().timestamp()
            newly_offline = 0

            for terminal in all_terminals:
                # Check if the (MAC, IP) pair was seen in this collection.
                pair_key = (terminal.mac_address_normalized, terminal.ip_address)
                if pair_key not in seen_pairs and terminal.updated_at:
                    last_seen = terminal.updated_at.timestamp() if terminal.updated_at.tzinfo else terminal.updated_at.replace(tzinfo=None).timestamp()
                    if (now_ts - last_seen) > offline_threshold_seconds:
                        newly_offline += 1
                        try:
                            await emit_terminal_offline(
                                ip_address=terminal.ip_address,
                                mac_address=terminal.mac_address or "",
                            )
                        except Exception:
                            pass

            if newly_offline > 0:
                logger.info(
                    f"Offline detection for '{source_tag}': "
                    f"{newly_offline} terminals offline"
                )

        except Exception as e:
            logger.error(f"Offline detection failed for '{source_tag}': {str(e)}")

        return SyncResult(
            success=True,
            message=f"Processed {len(entries)} ARP entries from '{source_tag}'",
            entries_processed=len(entries),
            entries_added=added,
            entries_updated=updated,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Scheduled Collection
    # ------------------------------------------------------------------
    async def run_scheduled_collection(self):
        """Run scheduled ARP collection for all enabled ARP sources"""
        from app.core.crypto import decrypt_config

        stmt = select(DataSource).where(
            (DataSource.type.in_(["arp_ssh", "arp_api"])) &
            (DataSource.enabled == True)
        )
        result = await self.db.execute(stmt)
        sources = result.scalars().all()

        for source in sources:
            try:
                # Decrypt config before using it for SSH/API connections
                if source.config:
                    source.config = decrypt_config(source.config)

                logger.info(f"Starting scheduled collection for '{source.tag}'")
                if source.type == "arp_ssh":
                    sync_result = await self.collect_from_ssh(source)
                elif source.type == "arp_api":
                    sync_result = await self.collect_from_api(source)
                else:
                    continue

                logger.info(
                    f"Scheduled collection for '{source.tag}': "
                    f"success={sync_result.success}, "
                    f"processed={sync_result.entries_processed}, "
                    f"added={sync_result.entries_added}, "
                    f"updated={sync_result.entries_updated}"
                )

                if sync_result.errors:
                    for err in sync_result.errors:
                        logger.error(f"  Error: {err}")

            except Exception as e:
                logger.error(f"Scheduled collection failed for '{source.tag}': {str(e)}")

    # ------------------------------------------------------------------
    # ARP Output Parsing
    # ------------------------------------------------------------------
    def _parse_arp_output(self, output: str, source_type: str) -> list[dict]:
        """
        Parse ARP table output from a switch.

        Common formats:
        - Cisco: "Internet  192.168.1.1   2   aa11.bb22.cc33  ARPA  Vlan10"
        - Huawei: "192.168.1.1  aa11-bb22-cc33  I  Vlanif10"
        - H3C: "192.168.1.1  aa11-bb22-cc33  VLAN 10"
        """
        entries = []
        lines = output.strip().split("\n")

        # Pattern for Cisco-style ARP output
        cisco_pattern = re.compile(
            r'Internet\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})'
        )

        # Pattern for Huawei/H3C-style ARP output
        huawei_pattern = re.compile(
            r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4})'
        )

        # Generic pattern: IP followed by MAC in various formats
        generic_pattern = re.compile(
            r'(\d+\.\d+\.\d+\.\d+)\s+'
            r'([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})'
        )

        for line in lines:
            line = line.strip()
            if not line:
                continue

            ip_addr = None
            mac_addr = None

            # Try Cisco format
            match = cisco_pattern.search(line)
            if match:
                ip_addr = match.group(1)
                mac_addr = match.group(2)
                # Convert Cisco MAC format (aa11.bb22.cc33) to standard
                mac_addr = mac_addr.replace(".", "")
                mac_addr = "-".join(mac_addr[i:i+2] for i in range(0, len(mac_addr), 2))
            else:
                # Try Huawei/H3C format
                match = huawei_pattern.search(line)
                if match:
                    ip_addr = match.group(1)
                    mac_addr = match.group(2)
                    # Convert Huawei MAC format (aa11-bb22-cc33) to standard
                    mac_addr = mac_addr.replace("-", "")
                    mac_addr = "-".join(mac_addr[i:i+2] for i in range(0, len(mac_addr), 2))
                else:
                    # Try generic format
                    match = generic_pattern.search(line)
                    if match:
                        ip_addr = match.group(1)
                        mac_addr = match.group(2).replace(":", "-").upper()

            if ip_addr and mac_addr:
                entries.append({
                    "ip_address": ip_addr,
                    "mac_address": mac_addr,
                })

        return entries

    def _parse_api_response(self, data: Any) -> list[dict]:
        """
        Parse API response into a list of {ip_address, mac_address} dicts.

        Supports various response formats:
        - List of dicts with ip/mac fields
        - Dict with a wrapper key containing the list (data/entries/results/arp/devices/records)
        """
        entries = []

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Try common wrapper keys in order of likelihood
            for key in ("data", "entries", "results", "arp", "devices", "records"):
                items = data.get(key)
                if isinstance(items, list):
                    break
            else:
                items = []
        else:
            return entries

        for item in items:
            if not isinstance(item, dict):
                continue

            ip_addr = (
                item.get("ip_address") or
                item.get("ipv4_address") or
                item.get("ip") or
                item.get("ipAddress") or
                ""
            )
            mac_addr = (
                item.get("mac_address") or
                item.get("mac") or
                item.get("macAddress") or
                ""
            )

            if ip_addr and mac_addr:
                entries.append({
                    "ip_address": str(ip_addr).strip(),
                    "mac_address": str(mac_addr).strip(),
                })

        return entries

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_mac(mac: str) -> str | None:
        """Normalize MAC address format to XX-XX-XX-XX-XX-XX"""
        mac_clean = mac.replace("-", "").replace(":", "").replace(".", "").upper()
        if len(mac_clean) != 12 or not mac_clean.isalnum():
            return None
        formatted = "-".join(mac_clean[i:i+2] for i in range(0, len(mac_clean), 2))
        return formatted
