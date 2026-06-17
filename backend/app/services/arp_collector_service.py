"""
ARP Collector Service

Collects ARP data from switches via SSH or API,
processes entries, and triggers compliance checks.
"""

import re
import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.terminal import Terminal, TerminalStatus
from app.models.data_source import DataSource
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
        1. Batch upsert to Terminal table (with source_tag)
        2. Batch compliance check
        3. Update compliance_status
        4. Trigger auto-block (non-blocking)
        """
        added = 0
        updated = 0
        errors = []

        for entry in entries:
            ip_addr = entry.get("ip_address", "").strip()
            mac_addr = entry.get("mac_address", "").strip()

            if not ip_addr or not mac_addr:
                continue

            # Normalize MAC address
            mac_normalized = self._normalize_mac(mac_addr)
            if not mac_normalized:
                continue

            try:
                # Upsert: check if IP+MAC already exists
                stmt = select(Terminal).where(
                    (Terminal.ip_address == ip_addr) &
                    (Terminal.mac_address == mac_normalized)
                )
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # Update timestamp and source_tag
                    from datetime import datetime, timezone
                    existing.timestamp = datetime.now(timezone.utc)
                    existing.source_tag = source_tag
                    existing.source = "arp"
                    # Reset compliance_status to "unknown" so the next
                    # compliance check will re-evaluate it with current
                    # whitelist/IPGuard data. This ensures terminals that
                    # were previously non_compliant can become compliant
                    # if the baseline data has changed.
                    existing.compliance_status = "unknown"
                    existing.wl_match_type = None
                    updated += 1
                else:
                    # Create new entry
                    mac_record = Terminal(
                        ip_address=ip_addr,
                        mac_address=mac_normalized,
                        mac_address_normalized=mac_normalized.replace('-', '').replace(':', '').replace('.', '').upper(),
                        status=TerminalStatus.UNBLOCKED.value,
                        source="arp",
                        source_tag=source_tag,
                        compliance_status="unknown",
                    )
                    self.db.add(mac_record)
                    added += 1

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

                # Update compliance_status for each entry
                compliant_ips = set()
                bypass_data = {}  # ip -> wl_match_type
                non_compliant_ips = set()

                if check_result.details:
                    for item in check_result.details.get("compliant", []):
                        compliant_ips.add(item.get("ip_address"))
                    for item in check_result.details.get("bypass", []):
                        bypass_data[item.get("ip_address")] = item.get("wl_match_type")
                    for item in check_result.details.get("non_compliant", []):
                        non_compliant_ips.add(item.get("ip_address"))

                for entry in unchecked_entries:
                    if entry.ip_address in bypass_data:
                        entry.compliance_status = "bypass"
                        entry.wl_match_type = bypass_data[entry.ip_address]
                    elif entry.ip_address in compliant_ips:
                        entry.compliance_status = "compliant"
                        entry.wl_match_type = None
                    elif entry.ip_address in non_compliant_ips:
                        entry.compliance_status = "non_compliant"
                        entry.wl_match_type = None

                await self.db.commit()

                logger.info(
                    f"Compliance check for source '{source_tag}': "
                    f"{check_result.compliant} compliant, {check_result.bypass} bypass, {check_result.non_compliant} non-compliant"
                )

                # Trigger auto-block (fire and forget)
                if check_result.non_compliant > 0:
                    asyncio.create_task(
                        self._auto_block_task(source_tag)
                    )

        except Exception as e:
            logger.error(f"Compliance check failed for source '{source_tag}': {str(e)}")
            errors.append(f"Compliance check failed: {str(e)}")

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

    async def _auto_block_task(self, source_tag: str):
        """Background task for auto-blocking non-compliant terminals.

        Uses an independent database session to avoid lifecycle issues
        with the parent request's session.
        """
        from app.core.database import async_session_factory
        async with async_session_factory() as session:
            try:
                from app.services.compliance_service import ComplianceService
                compliance_service = ComplianceService(session)
                result = await compliance_service.auto_block_non_compliant(source_tag)
                await session.commit()
                logger.info(
                    f"Auto-block result for '{source_tag}': "
                    f"blocked={result.blocked}, skipped={result.skipped}"
                )
            except Exception as e:
                await session.rollback()
                logger.error(f"Auto-block task failed for '{source_tag}': {str(e)}")
