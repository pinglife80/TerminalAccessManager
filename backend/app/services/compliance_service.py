"""
Compliance Service

Core compliance checking logic:
- Check if IP+MAC is compliant against whitelist and IPGuard baseline
- Auto-block non-compliant terminals
- Auto-unblock terminals that have become compliant
- Redis caching for performance optimization
- Distributed lock for concurrent compliance recalculation
"""

import contextlib
import ipaddress
import json
import uuid
from datetime import datetime, timedelta, UTC

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.blacklist import Blacklist
from app.models.compliance_baseline import ComplianceBaseline
from app.models.data_source import DataSource
from app.models.log import AuditLog
from app.models.terminal import Terminal
from app.models.whitelist import Whitelist
from app.schemas.data_source import (
    AutoBlockResult,
    AutoUnblockResult,
    ComplianceCheckResult,
)
from app.services.config_service import get_config_value

# Redis cache key patterns and TTLs
IPGUARD_CACHE_PREFIX = "ipguard:"
IPGUARD_CACHE_TTL = 900  # 15 minutes (1.5x sync interval to avoid expiry gap)
IPGUARD_BACKUP_CACHE_PREFIX = "ipguard:backup:"
WHITELIST_CACHE_KEY = "whitelist:all"
WHITELIST_CACHE_TTL = 300  # 5 minutes

# Distributed lock for compliance recalculation
COMPLIANCE_RECALC_LOCK_KEY = "compliance:recalc:lock"
COMPLIANCE_RECALC_LOCK_TTL = 60  # 60 seconds


async def _get_redis():
    from app.core.security import get_redis_client
    return await get_redis_client()


async def _acquire_compliance_lock() -> str | None:
    """Acquire a distributed lock for compliance recalculation.
    
    Returns a lock token if acquired, None otherwise.
    The lock prevents concurrent compliance recalculation which can cause
    inconsistent terminal states.
    """
    try:
        redis = await _get_redis()
        lock_token = str(uuid.uuid4())
        acquired = await redis.set(
            COMPLIANCE_RECALC_LOCK_KEY,
            lock_token,
            nx=True,
            ex=COMPLIANCE_RECALC_LOCK_TTL,
        )
        if acquired:
            logger.debug(f"Acquired compliance recalculation lock: {lock_token}")
            return lock_token
        return None
    except Exception as e:
        logger.warning(f"Failed to acquire compliance lock: {e}")
        return None


async def _release_compliance_lock(token: str) -> None:
    """Release the distributed lock for compliance recalculation."""
    try:
        redis = await _get_redis()
        current_token = await redis.get(COMPLIANCE_RECALC_LOCK_KEY)
        if current_token == token:
            await redis.delete(COMPLIANCE_RECALC_LOCK_KEY)
            logger.debug(f"Released compliance recalculation lock: {token}")
    except Exception as e:
        logger.warning(f"Failed to release compliance lock: {e}")


class ComplianceService:
    """Service for compliance checking and auto-block/unblock operations"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Compliance Check
    # ------------------------------------------------------------------
    async def check_compliance(self, ip_address: str, mac_address: str) -> dict:
        """
        Check if IP+MAC is compliant.

        Logic:
        1. Check whitelist (IP pattern matching + MAC exact match) -> bypass
        2. Check IPGuard baseline data (IP+MAC match) -> compliant
        3. Neither matches -> non_compliant

        Returns: {"compliance_status": str, "matched_sources": [...], "whitelisted": bool, "wl_match_type": Optional[str]}
        """
        matched_sources = []
        whitelisted = False
        wl_match_type = None

        # 1. Check whitelist
        whitelist_result = await self._check_whitelist(ip_address, mac_address)
        if whitelist_result:
            whitelisted = True
            wl_match_type = whitelist_result.get("match_type")
            matched_sources.append("whitelist")

        # 2. Check IPGuard baseline
        ipguard_match = await self._check_ipguard(ip_address, mac_address)
        if ipguard_match:
            matched_sources.append("ipguard")

        if whitelisted:
            compliance_status = "bypass"
        elif ipguard_match:
            compliance_status = "compliant"
        else:
            compliance_status = "non_compliant"

        return {
            "compliance_status": compliance_status,
            "matched_sources": matched_sources,
            "whitelisted": whitelisted,
            "wl_match_type": wl_match_type,
        }

    async def batch_check_compliance(self, entries: list[dict]) -> ComplianceCheckResult:
        """
        Batch compliance check.

        Performance optimization: load all whitelist and IPGuard data into memory at once.

        Args:
            entries: List of {"ip_address": str, "mac_address": str, "source_tag": str}

        Returns:
            ComplianceCheckResult with counts and details
        """
        # Load all whitelist data into memory
        whitelist_data = await self._load_whitelist_cache()

        # Load all IPGuard data into memory (from all ipguard sources)
        ipguard_data = await self._load_all_ipguard_cache()

        compliant_list = []
        non_compliant_list = []
        bypass_list = []

        for entry in entries:
            ip_addr = entry.get("ip_address", "")
            mac_addr = entry.get("mac_address", "")
            entry.get("source_tag", "")

            # Check whitelist
            wl_result = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)

            # Check IPGuard
            ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

            if wl_result:
                entry["compliance_status"] = "bypass"
                entry["wl_match_type"] = wl_result.get("match_type")
                entry["wl_comments"] = wl_result.get("comments")
                bypass_list.append(entry)
            elif ig_match:
                entry["compliance_status"] = "compliant"
                compliant_list.append(entry)
            else:
                entry["compliance_status"] = "non_compliant"
                non_compliant_list.append(entry)

        return ComplianceCheckResult(
            total_checked=len(entries),
            compliant=len(compliant_list),
            bypass=len(bypass_list),
            non_compliant=len(non_compliant_list),
            unknown=0,
            details={
                "compliant": compliant_list,
                "non_compliant": non_compliant_list,
                "bypass": bypass_list,
            },
        )

    # ------------------------------------------------------------------
    # IPGuard Data Sync
    # ------------------------------------------------------------------
    async def sync_ipguard_data(self, source_tag: str) -> dict:
        """
        Sync IPGuard compliance baseline data to local Redis cache.

        Connects to the IPGuard database and fetches IP+MAC mappings.
        """
        # Find the ComplianceBaseline
        stmt = select(ComplianceBaseline).where(ComplianceBaseline.tag == source_tag)
        result = await self.db.execute(stmt)
        baseline = result.scalar_one_or_none()

        if not baseline:
            raise ValueError(f"Compliance baseline with tag '{source_tag}' not found")

        if not baseline.enabled:
            raise ValueError(f"Compliance baseline '{source_tag}' is disabled")

        config = baseline.config
        # Decrypt config if values are encrypted
        from app.core.crypto import decrypt_config
        if config:
            config = decrypt_config(config)
        entries = []

        # Determine database type (default: postgresql for backward compatibility)
        db_type = config.get("db_type", "postgresql")
        host = config.get("host", "")
        port = config.get("port", 3306)
        username = config.get("username", "")
        password = config.get("password", "")
        database = config.get("database", "ipguard")

        try:
            if db_type == "mssql":
                # SQL Server (IPGuard OCULAR3 typically uses this)
                # IPGuard OCULAR3 stores IP+MAC in AGENT.AGT_IP_MAC_STR
                # Format: "MAC(IP),MAC(),MAC()" — only pairs with IP are useful
                import re

                import pyodbc
                conn_str = (
                    f"DRIVER={{FreeTDS}};"
                    f"SERVER={host};"
                    f"PORT={port};"
                    f"DATABASE={database};"
                    f"UID={username};"
                    f"PWD={password};"
                    f"TDS_Version=7.3;"
                )
                conn = pyodbc.connect(conn_str, timeout=30)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT AGT_IP_MAC_STR FROM AGENT "
                    "WHERE AGT_IP_MAC_STR IS NOT NULL AND AGT_IP_MAC_STR <> ''"
                )
                # Parse MAC(IP) pairs from AGT_IP_MAC_STR
                mac_ip_pattern = re.compile(
                    r'([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-]'
                    r'[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})\(([^)]*)\)'
                )
                for row in cursor:
                    ip_mac_str = row[0] or ""
                    for mac, ip in mac_ip_pattern.findall(ip_mac_str):
                        if ip:  # Only entries with an IP address
                            entries.append({
                                "ip_address": ip.strip(),
                                "mac_address": mac.strip(),
                            })
                conn.close()

            elif db_type == "mysql":
                # MySQL / MariaDB
                import aiomysql
                conn = await aiomysql.connect(
                    host=host,
                    port=int(port),
                    user=username,
                    password=password,
                    db=database,
                    connect_timeout=30,
                )
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT ip_address, mac_address FROM terminal_info "
                        "WHERE ip_address IS NOT NULL AND mac_address IS NOT NULL"
                    )
                    rows = await cur.fetchall()
                    for row in rows:
                        entries.append({
                            "ip_address": str(row[0]),
                            "mac_address": str(row[1]),
                        })
                conn.close()

            else:
                # PostgreSQL (default)
                import asyncpg
                conn = await asyncpg.connect(
                    host=host,
                    port=int(port),
                    user=username,
                    password=password,
                    database=database,
                    timeout=30,
                )
                rows = await conn.fetch(
                    "SELECT ip_address, mac_address FROM terminal_info "
                    "WHERE ip_address IS NOT NULL AND mac_address IS NOT NULL"
                )
                for row in rows:
                    entries.append({
                        "ip_address": str(row["ip_address"]),
                        "mac_address": str(row["mac_address"]),
                    })
                await conn.close()

            # Cache to Redis
            redis = await _get_redis()
            cache_key = f"{IPGUARD_CACHE_PREFIX}{source_tag}"
            ipguard_ttl = await get_config_value("cache_ipguard_ttl", IPGUARD_CACHE_TTL)
            await redis.setex(
                cache_key,
                ipguard_ttl,
                json.dumps(entries),
            )

            # Write backup cache (no TTL) for fallback when sync fails
            backup_key = f"{IPGUARD_BACKUP_CACHE_PREFIX}{source_tag}"
            await redis.set(backup_key, json.dumps(entries))

            # Update sync status
            baseline.last_sync_status = "success"
            baseline.last_sync_at = func.now()
            baseline.last_sync_error = None
            await self.db.commit()

            logger.info(f"Synced {len(entries)} IPGuard entries from '{source_tag}'")
            return {
                "success": True,
                "entries": len(entries),
                "message": f"Synced {len(entries)} entries from IPGuard",
            }

        except Exception as e:
            # Update sync status with error
            baseline.last_sync_status = "failed"
            baseline.last_sync_at = func.now()
            baseline.last_sync_error = str(e)
            await self.db.commit()

            logger.error(f"IPGuard sync failed for '{source_tag}': {str(e)}")
            return {
                "success": False,
                "entries": 0,
                "message": f"Sync failed: {str(e)}",
            }

    # ------------------------------------------------------------------
    # Auto-Block
    # ------------------------------------------------------------------
    async def auto_block_non_compliant(
        self, arp_source_tag: str, block_time: str = "30d", dry_run: bool = False
    ) -> AutoBlockResult:
        """
        Auto-block non-compliant terminals.

        1. Find Terminal entries with compliance_status=non_compliant from this ARP source
           that are not already blocked
        2. Find associated firewall tags via DataSourceBinding
        3. Call firewall API to block
        4. Create Blacklist records (is_auto_blocked=True)
        """
        # Find non-compliant entries from this ARP source that are not already in blacklist
        # First, get all currently blacklisted IP+MAC combinations for this source
        bl_stmt = select(Blacklist.ip_address, Blacklist.mac_address_normalized).where(
            (Blacklist.source_tag == arp_source_tag) &
            (Blacklist.auto_unblocked == False) &
            (Blacklist.unblocked_at.is_(None))
        )
        bl_result = await self.db.execute(bl_stmt)
        blacklisted_pairs = set((row[0], row[1]) for row in bl_result.all())

        stmt = (
            select(Terminal)
            .where(
                (Terminal.source_tag == arp_source_tag) &
                (Terminal.compliance_status == "non_compliant") &
                (Terminal.status != "blocked")
            )
        )
        result = await self.db.execute(stmt)
        non_compliant_entries = result.scalars().all()

        # Filter out entries already in blacklist (IP+MAC level)
        def is_already_blacklisted(entry):
            mac_norm = entry.mac_address.replace('-', '').replace(':', '').replace('.', '').upper() if entry.mac_address else None
            return (entry.ip_address, mac_norm) in blacklisted_pairs

        non_compliant_entries = [
            e for e in non_compliant_entries if not is_already_blacklisted(e)
        ]

        if not non_compliant_entries:
            return AutoBlockResult(
                total_non_compliant=0,
                blocked=0,
                skipped=0,
                message="No non-compliant entries found",
            )

        # Get associated firewall tags
        from app.services.data_source_service import DataSourceService
        ds_service = DataSourceService(self.db)
        firewall_tags = await ds_service.get_firewall_tags_for_arp(arp_source_tag)

        if not firewall_tags:
            logger.warning(f"No firewall bindings found for ARP source '{arp_source_tag}'")
            return AutoBlockResult(
                total_non_compliant=len(non_compliant_entries),
                blocked=0,
                skipped=len(non_compliant_entries),
                errors=[f"No firewall bindings found for ARP source '{arp_source_tag}'"],
            )

        # Pre-resolve SangforService instances for all firewall tags
        # (1 DataSource query per tag instead of 1 per entry per tag)
        sangfor_services = {}  # fw_tag -> SangforService or None
        if not dry_run:
            for fw_tag in firewall_tags:
                try:
                    fw_stmt = select(DataSource).where(
                        (DataSource.tag == fw_tag) & (DataSource.type == "sangfor")
                    )
                    fw_result = await self.db.execute(fw_stmt)
                    fw_source = fw_result.scalar_one_or_none()

                    if fw_source and fw_source.enabled:
                        from app.core.crypto import decrypt_config
                        from app.services.sangfor_service import SangforService
                        config = fw_source.config
                        if config:
                            config = decrypt_config(config)
                        sangfor_services[fw_tag] = SangforService(
                            base_url=config.get("base_url", ""),
                            username=config.get("username", ""),
                            password=config.get("password", ""),
                            verify_ssl=config.get("verify_ssl", True),
                            ca_bundle=config.get("ca_bundle", ""),
                        )
                    else:
                        logger.warning(f"Firewall '{fw_tag}' not found or disabled")
                        sangfor_services[fw_tag] = None
                except Exception as e:
                    logger.error(f"Failed to resolve firewall '{fw_tag}': {str(e)}")
                    sangfor_services[fw_tag] = None

        blocked = 0
        skipped = 0
        errors = []
        details = []

        for entry in non_compliant_entries:
            if dry_run:
                details.append({
                    "ip_address": entry.ip_address,
                    "mac_address": entry.mac_address,
                    "action": "would_block",
                    "firewall_tags": firewall_tags,
                })
                blocked += 1
                continue

            # Block on each associated firewall (using pre-resolved services)
            # Synchronous call: only update DB after confirming firewall success
            fw_success_count = 0
            for fw_tag in firewall_tags:
                svc = sangfor_services.get(fw_tag)
                if not svc:
                    errors.append(
                        f"Failed to block {entry.ip_address} on firewall '{fw_tag}': service not available"
                    )
                    continue
                try:
                    result = await svc.block_ip(
                        [entry.ip_address],
                        source_tag=fw_tag,
                        reason=f"Auto-blocked: non-compliant (source={arp_source_tag})"
                    )
                    if result.get("code") == 0:
                        fw_success_count += 1
                        logger.debug(f"Blocked {entry.ip_address} on firewall '{fw_tag}'")
                    else:
                        error_msg = result.get("message", "unknown error")
                        errors.append(
                            f"Failed to block {entry.ip_address} on firewall '{fw_tag}': {error_msg}"
                        )
                except Exception as e:
                    errors.append(
                        f"Error blocking {entry.ip_address} on firewall '{fw_tag}': {str(e)}"
                    )
            all_success = fw_success_count == len(firewall_tags) and len(errors) == 0

            if all_success:
                # Update MAC status
                entry.status = "blocked"
                entry.firewall_tag = firewall_tags[0] if len(firewall_tags) == 1 else ",".join(firewall_tags)
                # Update comments with block info
                fw_info = ",".join(firewall_tags)
                block_comment = f"Auto-blocked by TAM on firewall [{fw_info}]"
                if entry.comments:
                    entry.comments = f"{entry.comments}; {block_comment}"
                else:
                    entry.comments = block_comment

                # Create a separate Blacklist record for each firewall
                import re
                from datetime import datetime, timedelta

                match = re.match(r'^(\d+)([dhm])$', block_time.lower())
                td = timedelta(days=30)
                if match:
                    value = int(match.group(1))
                    unit = match.group(2)
                    if unit == 'd':
                        td = timedelta(days=value)
                    elif unit == 'h':
                        td = timedelta(hours=value)
                    elif unit == 'm':
                        td = timedelta(minutes=value)

                for fw_tag in firewall_tags:
                    mac_norm = entry.mac_address.replace('-', '').replace(':', '').replace('.', '').upper() if entry.mac_address else None
                    blacklist_entry = Blacklist(
                        ip_address=entry.ip_address,
                        mac_address=entry.mac_address,
                        mac_address_normalized=mac_norm,
                        reason=f"Auto-blocked: non-compliant (source={arp_source_tag})",
                        blocked_by="system",
                        expires_at=datetime.now(UTC) + td,
                        source_tag=arp_source_tag,
                        firewall_tag=fw_tag,
                        is_auto_blocked=True,
                        auto_unblocked=False,
                    )
                    try:
                        self.db.add(blacklist_entry)
                        await self.db.flush()
                    except IntegrityError:
                        await self.db.rollback()
                        logger.warning(f"Duplicate blacklist entry for {entry.ip_address} MAC {entry.mac_address}, skipping")
                        continue

                blocked += 1

                details.append({
                    "ip_address": entry.ip_address,
                    "mac_address": entry.mac_address,
                    "action": "blocked",
                    "firewall_tags": firewall_tags,
                })

                # Emit terminal.blocked event for notification dispatch.
                # emit_event is fire-and-forget (errors are logged, not raised),
                # so this cannot break the auto-block flow.
                from app.services.event_emitter import emit_terminal_blocked, emit_auto_block_triggered
                await emit_terminal_blocked(
                    ip_address=entry.ip_address,
                    mac_address=entry.mac_address or "",
                    reason=f"Auto-blocked: non-compliant (source={arp_source_tag})",
                    blocked_by="system",
                )
                await emit_auto_block_triggered(
                    ip_address=entry.ip_address,
                    mac_address=entry.mac_address or "",
                    reason=f"Non-compliant (source={arp_source_tag})",
                )
            else:
                skipped += 1

        # Close all pre-resolved SangforService instances
        for svc in sangfor_services.values():
            if svc:
                with contextlib.suppress(Exception):
                    await svc.close()

        if not dry_run and blocked > 0:
            from app.services.event_emitter import emit_block_threshold_exceeded
            from app.services.config_service import get_config_value

            block_threshold = await get_config_value("alert_block_count_threshold", 50)
            if blocked > block_threshold:
                await emit_block_threshold_exceeded(block_threshold, blocked)

            terminal_list = [{"ip_address": d["ip_address"], "mac_address": d["mac_address"]} for d in details]
            await self.log_action("system", "auto_block_terminal", "terminal", None, {
                "message": f"Auto-blocked {blocked} non-compliant terminals from source '{arp_source_tag}'",
                "source_tag": arp_source_tag,
                "blocked": blocked,
                "skipped": skipped,
                "firewall_tags": firewall_tags,
                "terminals": terminal_list[:50],
                "total_terminals": len(terminal_list),
            }, ip_address="System")
            await self.db.commit()

        return AutoBlockResult(
            total_non_compliant=len(non_compliant_entries),
            blocked=blocked,
            skipped=skipped,
            errors=errors,
            details=details if len(details) <= 100 else None,
        )

    # ------------------------------------------------------------------
    # Auto-Unblock
    # ------------------------------------------------------------------
    async def auto_unblock_compliant(self) -> AutoUnblockResult:
        """
        Auto-unblock terminals that have become compliant.

        1. Find Blacklist entries where auto_unblocked=False (both auto and manual blocked)
        2. Group entries by (ip_address, mac_address) to handle multi-firewall atomically
        3. Check if the IP+MAC is now compliant
        4. If compliant, call firewall API to unblock on ALL firewalls
        5. Only update Terminal status if ALL firewalls were successfully unblocked
        6. Mark only successfully unblocked Blacklist entries as auto_unblocked=True
        """
        stmt = (
            select(Blacklist)
            .where(
                Blacklist.auto_unblocked == False
            )
        )
        result = await self.db.execute(stmt)
        auto_blocked_entries = result.scalars().all()

        if not auto_blocked_entries:
            return AutoUnblockResult(
                total_auto_blocked=0,
                unblocked=0,
                skipped=0,
            )

        # Load compliance data
        whitelist_data = await self._load_whitelist_cache()
        ipguard_data = await self._load_all_ipguard_cache()

        # Group entries by (ip, mac) so we process all firewalls for a
        # given terminal atomically — only mark unblocked if ALL firewalls
        # succeed.
        from collections import defaultdict
        entry_groups = defaultdict(list)
        for entry in auto_blocked_entries:
            key = (entry.ip_address or "", entry.mac_address or "")
            entry_groups[key].append(entry)

        unblocked = 0
        skipped = 0
        errors = []
        details = []

        for (ip_addr, mac_addr), entries in entry_groups.items():
            # Check if now compliant
            wl_match = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)
            ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

            if not (wl_match or ig_match):
                skipped += len(entries)
                continue

            # Try to unblock on ALL firewalls for this terminal
            all_success = True
            successfully_unblocked_entries = []

            for bl_entry in entries:
                fw_tag = bl_entry.firewall_tag
                if fw_tag:
                    try:
                        success = await self._unblock_on_firewall(ip_addr, fw_tag)
                        if success:
                            successfully_unblocked_entries.append(bl_entry)
                        else:
                            all_success = False
                            errors.append(
                                f"Failed to unblock {ip_addr} on firewall '{fw_tag}'"
                            )
                    except (ConnectionError, TimeoutError) as e:
                        all_success = False
                        errors.append(
                            f"Error unblocking {ip_addr} on firewall '{fw_tag}': {str(e)}"
                        )
                        from app.services.event_emitter import emit_firewall_connection_lost
                        await emit_firewall_connection_lost(fw_tag, str(e))
                    except Exception as e:
                        all_success = False
                        errors.append(
                            f"Error unblocking {ip_addr} on firewall '{fw_tag}': {str(e)}"
                        )
                else:
                    # No firewall_tag on blacklist entry — try to find binding
                    # via the terminal's source_tag (use multi-firewall method)
                    if bl_entry.source_tag:
                        fw_tags = await self._get_bound_firewall_tags(bl_entry.source_tag)
                        binding_success = True
                        for ft in fw_tags:
                            try:
                                success = await self._unblock_on_firewall(ip_addr, ft)
                                if not success:
                                    binding_success = False
                                    all_success = False
                                    errors.append(
                                        f"Failed to unblock {ip_addr} on firewall '{ft}' (resolved from binding)"
                                    )
                            except Exception as e:
                                binding_success = False
                                all_success = False
                                errors.append(
                                    f"Error unblocking {ip_addr} on firewall '{ft}': {str(e)}"
                                )
                        if binding_success:
                            successfully_unblocked_entries.append(bl_entry)
                    else:
                        # No firewall at all, just mark as unblocked in DB
                        successfully_unblocked_entries.append(bl_entry)

            if all_success:
                # All firewalls unblocked — update Terminal and mark all entries
                for bl_entry in successfully_unblocked_entries:
                    bl_entry.auto_unblocked = True
                    bl_entry.unblocked_at = datetime.now(UTC)

                if ip_addr:
                    mac_stmt = select(Terminal).where(
                        Terminal.ip_address == ip_addr,
                        Terminal.mac_address == mac_addr
                    )
                    mac_result = await self.db.execute(mac_stmt)
                    mac_records = mac_result.scalars().all()
                    for record in mac_records:
                        record.status = "unblocked"
                        record.firewall_tag = None  # Clear firewall tag on unblock
                        record.compliance_status = "bypass" if wl_match else "compliant"
                        record.wl_match_type = wl_match.get("match_type") if isinstance(wl_match, dict) else wl_match
                        # Update comments with unblock info
                        resolved_fw = entries[0].firewall_tag or "N/A"
                        unblock_comment = f"Auto-unblocked by TAM from firewall [{resolved_fw}]"
                        if record.comments:
                            record.comments = f"{record.comments}; {unblock_comment}"
                        else:
                            record.comments = unblock_comment

                unblocked += 1
                details.append({
                    "ip_address": ip_addr,
                    "mac_address": mac_addr,
                    "action": "unblocked",
                    "reason": "now_compliant",
                })
            else:
                # Partial failure — only mark successfully unblocked entries
                # but leave Terminal status as blocked since some firewalls
                # still hold the block
                for bl_entry in successfully_unblocked_entries:
                    bl_entry.auto_unblocked = True
                    bl_entry.unblocked_at = datetime.now(UTC)
                skipped += len(entries) - len(successfully_unblocked_entries)

        if unblocked > 0:
            # Emit auto-unblock event for notification
            from app.services.event_emitter import emit_auto_unblock_triggered, emit_terminal_unblocked
            for entry in successfully_unblocked_entries:
                await emit_auto_unblock_triggered(entry.ip_address, entry.mac_address or "")
                await emit_terminal_unblocked(entry.ip_address, entry.mac_address or "", "system")

            # Audit log for auto-unblock (before commit so it's persisted in the same transaction)
            terminal_list = [{"ip_address": d["ip_address"], "mac_address": d["mac_address"]} for d in details]
            await self.log_action("system", "auto_unblock_terminal", "terminal", None, {
                "message": f"Auto-unblocked {unblocked} compliant terminals",
                "unblocked": unblocked,
                "skipped": skipped,
                "terminals": terminal_list[:50],
                "total_terminals": len(terminal_list),
            }, ip_address="System")
            await self.db.commit()

        return AutoUnblockResult(
            total_auto_blocked=len(auto_blocked_entries),
            unblocked=unblocked,
            skipped=skipped,
            errors=errors,
            details=details if len(details) <= 100 else None,
            message="All blocked terminals are still non-compliant" if unblocked == 0 and skipped > 0 else None,
        )

    # ------------------------------------------------------------------
    # Whitelist Matching
    # ------------------------------------------------------------------
    async def _check_whitelist(self, ip_address: str, mac_address: str) -> dict | None:
        """Check if IP+MAC matches any whitelist entry. Returns match result dict or None."""
        whitelist_data = await self._load_whitelist_cache()
        return self._match_whitelist_in_memory(whitelist_data, ip_address, mac_address)

    def _match_whitelist_in_memory(
        self, whitelist_data: list[dict], ip_address: str, mac_address: str
    ) -> dict | None:
        """Match IP+MAC against in-memory whitelist data.
        Returns dict with "match_type" ("mac"/"ip"/"both") and "comments" (str or None),
        or None if no match."""
        normalized_mac = mac_address.upper().replace(":", "").replace("-", "").replace(".", "") if mac_address else ""

        for entry in whitelist_data:
            # MAC-only whitelist entry: match by MAC only
            if entry.get("pattern_type") == "mac_only":
                if entry.get("mac_address"):
                    entry_mac = entry["mac_address"].upper().replace(":", "").replace("-", "").replace(".", "")
                    if entry_mac == normalized_mac:
                        return {"match_type": "mac", "comments": entry.get("comments")}
                continue

            # Check IP pattern match
            ip_match = False
            if entry.get("ip_pattern"):
                ip_match = self._ip_matches_pattern(ip_address, entry["ip_pattern"], entry.get("pattern_type", "single_ip"))

            # Check MAC match
            mac_match = False
            if entry.get("mac_address"):
                entry_mac = entry["mac_address"].upper().replace(":", "").replace("-", "").replace(".", "")
                mac_match = entry_mac == normalized_mac

            # If both IP and MAC are specified, both must match
            # If only IP is specified, IP must match
            # If only MAC is specified, MAC must match
            if entry.get("ip_pattern") and entry.get("mac_address"):
                if ip_match and mac_match:
                    return {"match_type": "both", "comments": entry.get("comments")}
            elif entry.get("ip_pattern"):
                if ip_match:
                    return {"match_type": "ip", "comments": entry.get("comments")}
            elif entry.get("mac_address") and mac_match:
                return {"match_type": "mac", "comments": entry.get("comments")}

        return None

    def _ip_matches_pattern(self, ip_address: str, ip_pattern: str, pattern_type: str) -> bool:
        """Check if an IP address matches a pattern (single IP, CIDR, or IP range)"""
        try:
            target_ip = ipaddress.IPv4Address(ip_address)

            if pattern_type == "single_ip":
                return ip_address == ip_pattern
            elif pattern_type == "cidr":
                network = ipaddress.IPv4Network(ip_pattern, strict=False)
                return target_ip in network
            elif pattern_type == "ip_range":
                return self._ip_in_range(ip_address, ip_pattern)
            elif pattern_type == "both":
                if '/' in ip_pattern:
                    if ip_pattern.endswith("/32"):
                        return ip_address == ip_pattern[:-3]
                    network = ipaddress.IPv4Network(ip_pattern, strict=False)
                    return target_ip in network
                elif '-' in ip_pattern:
                    return self._ip_in_range(ip_address, ip_pattern)
                else:
                    return ip_address == ip_pattern
            else:
                if '/' in ip_pattern:
                    network = ipaddress.IPv4Network(ip_pattern, strict=False)
                    return target_ip in network
                elif '-' in ip_pattern:
                    return self._ip_in_range(ip_address, ip_pattern)
                else:
                    return ip_address == ip_pattern
        except (ValueError, TypeError) as e:
            logger.debug(f"IP pattern match failed for {ip_address} against {ip_pattern}: {e}")
            return ip_address == ip_pattern

    def _ip_in_range(self, ip_address: str, ip_range: str) -> bool:
        """Check if IP is in a range like 192.168.1.1-100"""
        import re
        match = re.match(r'^(\d+\.\d+\.\d+)\.(\d+)-(\d+)$', ip_range)
        if not match:
            return False

        prefix = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))

        try:
            target = ipaddress.IPv4Address(ip_address)
            # Check if target IP is in the same /24 subnet
            if not str(target).startswith(prefix + "."):
                return False
            last_octet = int(str(target).split(".")[-1])
            return start <= last_octet <= end
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # IPGuard Matching
    # ------------------------------------------------------------------
    async def _check_ipguard(self, ip_address: str, mac_address: str) -> bool:
        """Check if IP+MAC matches any IPGuard baseline entry"""
        ipguard_data = await self._load_all_ipguard_cache()
        return self._match_ipguard_in_memory(ipguard_data, ip_address, mac_address)

    def _match_ipguard_in_memory(
        self, ipguard_data: dict[str, list[dict]], ip_address: str, mac_address: str
    ) -> bool:
        """Match IP+MAC against in-memory IPGuard data from all sources"""
        normalized_mac = mac_address.upper().replace(":", "-")

        for _source_tag, entries in ipguard_data.items():
            for entry in entries:
                entry_mac = entry.get("mac_address", "").upper().replace(":", "-")
                if entry.get("ip_address") == ip_address and entry_mac == normalized_mac:
                    return True
        return False

    # ------------------------------------------------------------------
    # Cache Loading
    # ------------------------------------------------------------------
    async def _load_whitelist_cache(self) -> list[dict]:
        """Load all whitelist data, from Redis cache or database"""
        try:
            redis = await _get_redis()
            cached = await redis.get(WHITELIST_CACHE_KEY)
            if cached:
                data = json.loads(cached if isinstance(cached, str) else cached.decode())
                return data
        except Exception:
            pass

        # Load from database
        stmt = select(Whitelist)
        result = await self.db.execute(stmt)
        entries = result.scalars().all()

        data = []
        for entry in entries:
            data.append({
                "mac_address": entry.mac_address,
                "ip_pattern": entry.ip_pattern,
                "pattern_type": entry.pattern_type,
                "comments": entry.comments,
            })

        # Cache to Redis
        try:
            redis = await _get_redis()
            whitelist_ttl = await get_config_value("cache_whitelist_ttl", WHITELIST_CACHE_TTL)
            await redis.setex(WHITELIST_CACHE_KEY, whitelist_ttl, json.dumps(data))
        except Exception:
            pass

        return data

    async def _load_all_ipguard_cache(self) -> dict[str, list[dict]]:
        """Load all IPGuard data from Redis cache or database"""
        result_data = {}

        # Find all compliance baselines
        stmt = select(ComplianceBaseline)
        db_result = await self.db.execute(stmt)
        baselines = db_result.scalars().all()

        for baseline in baselines:
            cache_key = f"{IPGUARD_CACHE_PREFIX}{baseline.tag}"
            try:
                redis = await _get_redis()
                cached = await redis.get(cache_key)
                if cached:
                    data = json.loads(cached if isinstance(cached, str) else cached.decode())
                    result_data[baseline.tag] = data
                    continue
            except Exception:
                pass

            # If not in cache, try to sync
            try:
                sync_result = await self.sync_ipguard_data(baseline.tag)
                if sync_result.get("success"):
                    # Load again from cache after sync
                    try:
                        redis = await _get_redis()
                        cached = await redis.get(cache_key)
                        if cached:
                            data = json.loads(cached if isinstance(cached, str) else cached.decode())
                            result_data[baseline.tag] = data
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Failed to sync IPGuard data for '{baseline.tag}': {str(e)}")

            # If still no data, try loading from backup cache
            if baseline.tag not in result_data:
                backup_key = f"{IPGUARD_BACKUP_CACHE_PREFIX}{baseline.tag}"
                try:
                    redis = await _get_redis()
                    backup = await redis.get(backup_key)
                    if backup:
                        data = json.loads(backup if isinstance(backup, str) else backup.decode())
                        result_data[baseline.tag] = data
                        logger.warning(
                            f"IPGuard cache expired and sync failed for '{baseline.tag}', "
                            f"using backup data ({len(data)} entries)"
                        )
                    else:
                        logger.error(
                            f"IPGuard data unavailable for '{baseline.tag}': "
                            f"cache expired, sync failed, no backup. Skipping this source."
                        )
                except Exception as backup_err:
                    logger.error(
                        f"Failed to load backup IPGuard data for '{baseline.tag}': {backup_err}"
                    )

        return result_data

    # ------------------------------------------------------------------
    # Firewall Operations
    # ------------------------------------------------------------------
    async def _block_on_firewall(
        self, ip_address: str, firewall_tag: str, block_time: str = "30d",
        reason: str = "Auto-blocked: non-compliant"
    ) -> bool:
        """Block an IP on the specified firewall via permanent blacklist (synchronous)"""
        try:
            stmt = select(DataSource).where(
                (DataSource.tag == firewall_tag) & (DataSource.type == "sangfor")
            )
            result = await self.db.execute(stmt)
            fw_source = result.scalar_one_or_none()

            if not fw_source or not fw_source.enabled:
                logger.warning(f"Firewall '{firewall_tag}' not found or disabled")
                await self.log_action("system", "firewall_block", "firewall", firewall_tag, {
                    "message": f"Failed to block IP {ip_address} on firewall {firewall_tag}: firewall not found or disabled",
                    "ip_address": ip_address,
                    "firewall_tag": firewall_tag,
                    "success": False,
                    "error": "firewall_not_found_or_disabled",
                }, ip_address="System")
                return False

            from app.core.crypto import decrypt_config
            from app.services.sangfor_service import SangforService
            config = fw_source.config
            if config:
                config = decrypt_config(config)
            
            svc = await SangforService.get_cached_service(
                base_url=config.get("base_url", ""),
                username=config.get("username", ""),
                password=config.get("password", ""),
                verify_ssl=config.get("verify_ssl", True),
                ca_bundle=config.get("ca_bundle", ""),
            )

            result = await svc.block_ip(
                [ip_address],
                source_tag=firewall_tag,
                reason=reason,
            )
            success = result.get("code") == 0
            if success:
                logger.info(f"Blocked {ip_address} on firewall '{firewall_tag}'")
            else:
                logger.error(f"Failed to block {ip_address} on firewall '{firewall_tag}': {result.get('message', 'unknown error')}")
            await self.log_action("system", "firewall_block", "firewall", firewall_tag, {
                "message": f"Blocked IP {ip_address} on firewall {firewall_tag}" if success else f"Failed to block IP {ip_address} on firewall {firewall_tag}: {result.get('message', 'unknown error')}",
                "ip_address": ip_address,
                "firewall_tag": firewall_tag,
                "success": success,
                "reason": reason,
            }, ip_address="System")
            return success
        except Exception as e:
            logger.error(f"Failed to block {ip_address} on firewall '{firewall_tag}': {str(e)}")
            await self.log_action("system", "firewall_block", "firewall", firewall_tag, {
                "message": f"Failed to block IP {ip_address} on firewall {firewall_tag}: {str(e)}",
                "ip_address": ip_address,
                "firewall_tag": firewall_tag,
                "success": False,
                "error": str(e),
            }, ip_address="System")
            return False

    async def _unblock_on_firewall(self, ip_address: str, firewall_tag: str) -> bool:
        """Unblock an IP on the specified firewall (synchronous)"""
        try:
            stmt = select(DataSource).where(
                (DataSource.tag == firewall_tag) & (DataSource.type == "sangfor")
            )
            result = await self.db.execute(stmt)
            fw_source = result.scalar_one_or_none()

            if not fw_source or not fw_source.enabled:
                logger.warning(f"Firewall '{firewall_tag}' not found or disabled")
                await self.log_action("system", "firewall_unblock", "firewall", firewall_tag, {
                    "message": f"Failed to unblock IP {ip_address} on firewall {firewall_tag}: firewall not found or disabled",
                    "ip_address": ip_address,
                    "firewall_tag": firewall_tag,
                    "success": False,
                    "error": "firewall_not_found_or_disabled",
                }, ip_address="System")
                return False

            from app.core.crypto import decrypt_config
            from app.services.sangfor_service import SangforService
            config = fw_source.config
            if config:
                config = decrypt_config(config)
            
            svc = await SangforService.get_cached_service(
                base_url=config.get("base_url", ""),
                username=config.get("username", ""),
                password=config.get("password", ""),
                verify_ssl=config.get("verify_ssl", True),
                ca_bundle=config.get("ca_bundle", ""),
            )

            result = await svc.unblock_ip([{"srcIP": ip_address}])
            success = result.get("code") == 0
            if success:
                logger.info(f"Unblocked {ip_address} on firewall '{firewall_tag}'")
            else:
                logger.error(f"Failed to unblock {ip_address} on firewall '{firewall_tag}': {result.get('message', 'unknown error')}")
            await self.log_action("system", "firewall_unblock", "firewall", firewall_tag, {
                "message": f"Unblocked IP {ip_address} on firewall {firewall_tag}" if success else f"Failed to unblock IP {ip_address} on firewall {firewall_tag}: {result.get('message', 'unknown error')}",
                "ip_address": ip_address,
                "firewall_tag": firewall_tag,
                "success": success,
            }, ip_address="System")
            return success
        except Exception as e:
            logger.error(f"Failed to unblock {ip_address} on firewall '{firewall_tag}': {str(e)}")
            await self.log_action("system", "firewall_unblock", "firewall", firewall_tag, {
                "message": f"Failed to unblock IP {ip_address} on firewall {firewall_tag}: {str(e)}",
                "ip_address": ip_address,
                "firewall_tag": firewall_tag,
                "success": False,
                "error": str(e),
            }, ip_address="System")
            return False

    # ------------------------------------------------------------------
    # Whitelist Cache Invalidation
    # ------------------------------------------------------------------
    async def invalidate_whitelist_cache(self):
        """Invalidate the whitelist cache (call when whitelist is modified)"""
        try:
            redis = await _get_redis()
            await redis.delete(WHITELIST_CACHE_KEY)
        except Exception:
            pass

    async def _apply_compliance_result(
        self,
        terminal: Terminal,
        new_compliance: str,
        new_wl_match_type: str | None,
        wl_comments: str | None,
        ip_addr: str,
        mac_addr: str,
    ) -> dict:
        """
        Apply compliance result to a single terminal.
        
        This is the shared method for updating terminal compliance status,
        ensuring consistent behavior across all compliance check paths.
        
        Args:
            terminal: The terminal to update
            new_compliance: The new compliance status (bypass/compliant/non_compliant)
            new_wl_match_type: The whitelist match type (ip/mac) or None
            wl_comments: The whitelist comments or None
            ip_addr: IP address string
            mac_addr: MAC address string
        
        Returns:
            dict: {"status_changed": bool, "new_compliance": str, "unblocked": bool}
        """
        status_changed = terminal.compliance_status != new_compliance
        unblocked = False
        mac_norm = mac_addr.replace('-', '').replace(':', '').replace('.', '').upper() if mac_addr else None

        if new_compliance == "bypass":
            wl_comment_str = f"Whitelist: {wl_comments}" if wl_comments else None
            
            if wl_comment_str:
                if terminal.comments and "Whitelist: " in terminal.comments:
                    old_wl_start = terminal.comments.find("Whitelist: ")
                    semicolon_pos = terminal.comments.find(";", old_wl_start)
                    if semicolon_pos > old_wl_start:
                        old_wl_end = semicolon_pos
                        terminal.comments = terminal.comments[:old_wl_start] + wl_comment_str + terminal.comments[old_wl_end:]
                    else:
                        terminal.comments = terminal.comments[:old_wl_start] + wl_comment_str
                elif terminal.comments:
                    terminal.comments = f"{terminal.comments}; {wl_comment_str}"
                else:
                    terminal.comments = wl_comment_str
            elif terminal.comments and "Whitelist: " in terminal.comments:
                old_wl_start = terminal.comments.find("Whitelist: ")
                semicolon_pos = terminal.comments.find(";", old_wl_start)
                if semicolon_pos > old_wl_start:
                    terminal.comments = terminal.comments[:old_wl_start].rstrip("; ") + terminal.comments[semicolon_pos+1:].lstrip()
                else:
                    terminal.comments = terminal.comments[:old_wl_start].rstrip("; ")
        elif terminal.comments and "Whitelist: " in terminal.comments:
            old_wl_start = terminal.comments.find("Whitelist: ")
            semicolon_pos = terminal.comments.find(";", old_wl_start)
            if semicolon_pos > old_wl_start:
                terminal.comments = terminal.comments[:old_wl_start].rstrip("; ") + terminal.comments[semicolon_pos+1:].lstrip()
            else:
                terminal.comments = terminal.comments[:old_wl_start].rstrip("; ")

        old_compliance = terminal.compliance_status
        terminal.compliance_status = new_compliance
        terminal.wl_match_type = new_wl_match_type

        if status_changed:
            await self.log_action("system", "compliance_status_changed", "terminal",
                                f"{ip_addr}_{mac_addr}", {
                                    "message": f"Terminal compliance status changed from {old_compliance} to {new_compliance}",
                                    "ip_address": ip_addr,
                                    "mac_address": mac_addr,
                                    "old_compliance": old_compliance,
                                    "new_compliance": new_compliance,
                                    "wl_match_type": new_wl_match_type,
                                }, ip_address="System")

            if new_compliance == "bypass":
                pass
            elif new_compliance == "compliant":
                from app.services.notification_aggregator import get_notification_aggregator
                from app.services.notification_channels.base import NotificationEvent
                import uuid
                from datetime import datetime
                aggregator = await get_notification_aggregator()
                event = NotificationEvent(
                    id=str(uuid.uuid4()),
                    type="terminal.compliant",
                    timestamp=datetime.now(),
                    data={"ip_address": ip_addr, "mac_address": mac_addr},
                    source="system",
                    severity="info",
                )
                await aggregator.add_event(event)
            else:
                from app.services.notification_aggregator import get_notification_aggregator
                from app.services.notification_channels.base import NotificationEvent
                import uuid
                from datetime import datetime
                aggregator = await get_notification_aggregator()
                event1 = NotificationEvent(
                    id=str(uuid.uuid4()),
                    type="alert.policy_violation",
                    timestamp=datetime.now(),
                    data={"policy_name": "Terminal Compliance Policy", "terminal_ip": ip_addr, "mac_address": mac_addr, "source_tag": terminal.source_tag},
                    source="system",
                    severity="error",
                )
                event2 = NotificationEvent(
                    id=str(uuid.uuid4()),
                    type="terminal.non_compliant",
                    timestamp=datetime.now(),
                    data={"ip_address": ip_addr, "mac_address": mac_addr, "reasons": ["Non-compliant terminal detected"]},
                    source="system",
                    severity="warning",
                )
                await aggregator.add_event(event1)
                await aggregator.add_event(event2)

            if terminal.status == "blocked" and new_compliance in ("bypass", "compliant"):
                fw_tags = await self._get_bound_firewall_tags(terminal.source_tag)
                if fw_tags:
                    successful_fw_tags = []
                    failed_fw_tags = []
                    
                    for fw_tag in fw_tags:
                        try:
                            success = await self._unblock_on_firewall(ip_addr, fw_tag)
                            if success:
                                successful_fw_tags.append(fw_tag)
                            else:
                                failed_fw_tags.append(fw_tag)
                                logger.warning(f"Failed to auto-unblock {ip_addr} on firewall '{fw_tag}'")
                        except Exception as e:
                            failed_fw_tags.append(fw_tag)
                            logger.warning(f"Error auto-unblocking {ip_addr} on firewall '{fw_tag}': {e}")
                    
                    if successful_fw_tags:
                        terminal.status = "unblocked"
                        terminal.firewall_tag = None
                        unblocked = True
                        fw_info = ",".join(successful_fw_tags)
                        unblock_comment = f"Auto-unblocked by TAM from firewall [{fw_info}]"
                        if failed_fw_tags:
                            unblock_comment += f" (failed on: {','.join(failed_fw_tags)})"
                        if terminal.comments:
                            terminal.comments = f"{terminal.comments}; {unblock_comment}"
                        else:
                            terminal.comments = unblock_comment
                        
                        bl_stmt = select(Blacklist).where(
                            (Blacklist.ip_address == ip_addr) &
                            (Blacklist.mac_address_normalized == mac_norm) &
                            (Blacklist.unblocked_at.is_(None)) &
                            (Blacklist.auto_unblocked == False)
                        )
                        bl_result = await self.db.execute(bl_stmt)
                        bl_entries = bl_result.scalars().all()
                        for bl_entry in bl_entries:
                            bl_entry.auto_unblocked = True
                            bl_entry.unblocked_at = datetime.now(UTC)
                        
                        if failed_fw_tags:
                            logger.warning(f"Partially auto-unblocked {ip_addr} (now {new_compliance}): succeeded on [{fw_info}], failed on [{','.join(failed_fw_tags)}]")
                        else:
                            logger.info(f"Auto-unblocked {ip_addr} (now {new_compliance}) from firewall(s) '{fw_info}'")
                    else:
                        logger.warning(f"Auto-unblock failed for {ip_addr} on all firewalls, keeping blocked status")
                else:
                    terminal.status = "unblocked"
                    terminal.firewall_tag = None
                    unblocked = True

            # Check if terminal needs (re-)block: non-compliant AND no active blacklist entry
            # This handles the case where a terminal was blocked, became compliant (auto-unblocked),
            # then became non-compliant again - the terminal status may still be "blocked" from
            # the previous block, but the blacklist entry was auto-unblocked and needs recreation.
            bl_active_stmt = select(Blacklist).where(
                (Blacklist.ip_address == ip_addr) &
                (Blacklist.mac_address_normalized == mac_norm) &
                (Blacklist.auto_unblocked == False) &
                (Blacklist.unblocked_at.is_(None))
            )
            bl_active_result = await self.db.execute(bl_active_stmt)
            has_active_blacklist = bl_active_result.scalar_one_or_none() is not None

            if new_compliance == "non_compliant" and not has_active_blacklist:
                fw_tags = await self._get_bound_firewall_tags(terminal.source_tag)
                if fw_tags:
                    # Check if terminal is already blocked on all required firewalls
                    # (handles re-block after auto-unblock: terminal may still be blocked on firewall)
                    already_blocked = (
                        terminal.status == "blocked" and
                        terminal.firewall_tag is not None and
                        all(fw in (terminal.firewall_tag or "").split(",") for fw in fw_tags)
                    )
                    
                    all_block_success = True
                    if not already_blocked:
                        for fw_tag in fw_tags:
                            try:
                                success = await self._block_on_firewall(
                                    ip_addr, fw_tag,
                                    reason="Auto-blocked: compliance recalculation"
                                )
                                if not success:
                                    all_block_success = False
                                    logger.warning(f"Failed to auto-block {ip_addr} on firewall '{fw_tag}'")
                            except Exception as e:
                                all_block_success = False
                                logger.warning(f"Error auto-blocking {ip_addr} on firewall '{fw_tag}': {e}")
                    else:
                        logger.info(f"Terminal {ip_addr} already blocked on firewall(s), recreating blacklist entry")

                    if all_block_success:
                        terminal.status = "blocked"
                        terminal.firewall_tag = fw_tags[0] if len(fw_tags) == 1 else ",".join(fw_tags)
                        fw_info = ",".join(fw_tags)
                        block_comment = f"Auto-blocked by TAM on firewall [{fw_info}]"
                        if terminal.comments:
                            terminal.comments = f"{terminal.comments}; {block_comment}"
                        else:
                            terminal.comments = block_comment
                        import re
                        block_time = await self._get_block_time()
                        match = re.match(r'^(\d+)([dhm])$', block_time.lower())
                        td = timedelta(days=30)
                        if match:
                            value = int(match.group(1))
                            unit = match.group(2)
                            if unit == 'd':
                                td = timedelta(days=value)
                            elif unit == 'h':
                                td = timedelta(hours=value)
                            elif unit == 'm':
                                td = timedelta(minutes=value)
                        
                        # Check for existing blacklist entry (idempotency)
                        existing_bl_stmt = select(Blacklist).where(
                            (Blacklist.ip_address == ip_addr) &
                            (Blacklist.mac_address_normalized == mac_norm) &
                            (Blacklist.unblocked_at.is_(None)) &
                            (Blacklist.auto_unblocked == False)
                        )
                        existing_bl_result = await self.db.execute(existing_bl_stmt)
                        existing_bl = existing_bl_result.scalar_one_or_none()
                        
                        if existing_bl:
                            logger.info(f"IP {ip_addr} MAC {mac_addr} already in blacklist, skipping")
                        else:
                            for fw_tag in fw_tags:
                                bl_entry = Blacklist(
                                    ip_address=ip_addr,
                                    mac_address=mac_addr,
                                    mac_address_normalized=mac_norm,
                                    reason="Auto-blocked: non-compliant (compliance recalculation)",
                                    blocked_by="system",
                                    expires_at=datetime.now(UTC) + td,
                                    source_tag=terminal.source_tag,
                                    firewall_tag=fw_tag,
                                    is_auto_blocked=True,
                                    auto_unblocked=False,
                                )
                                try:
                                    self.db.add(bl_entry)
                                    await self.db.flush()
                                except IntegrityError:
                                    await self.db.rollback()
                                    logger.warning(f"Duplicate blacklist entry for {ip_addr} MAC {mac_addr} during recalculation, skipping")
                                    break
                            else:
                                logger.info(f"Auto-blocked {ip_addr} (now non_compliant) on firewall(s) '{fw_info}'")
        else:
            if terminal.status == "blocked" and not terminal.firewall_tag:
                fw_tags = await self._get_bound_firewall_tags(terminal.source_tag)
                if fw_tags:
                    terminal.firewall_tag = fw_tags[0] if len(fw_tags) == 1 else ",".join(fw_tags)

        if terminal.status != "blocked":
            terminal.firewall_tag = None

        return {"status_changed": status_changed, "new_compliance": new_compliance, "unblocked": unblocked}

    async def recalculate_all_compliance(self) -> dict:
        """Recalculate compliance status for all existing terminals.

        Called after whitelist changes (add/delete) to update terminal
        compliance_status in real-time instead of waiting for next sync.
        Also handles auto-unblock for terminals that become compliant
        while currently blocked on firewall.

        Uses distributed lock to prevent concurrent recalculation which
        can cause inconsistent terminal states.

        Returns:
            dict with counts: total, bypass, compliant, non_compliant,
            unchanged, unblocked (auto-unblocked from blocked state)
        """
        lock_token = await _acquire_compliance_lock()
        if not lock_token:
            logger.warning("Compliance recalculation skipped: another instance is already running")
            return {"total": 0, "bypass": 0, "compliant": 0, "non_compliant": 0, "unchanged": 0, "unblocked": 0, "skipped": True}

        try:
            start_time = datetime.now(UTC)
            logger.info(f"Starting compliance recalculation at {start_time.isoformat()}")

            whitelist_data = await self._load_whitelist_cache()
            ipguard_data = await self._load_all_ipguard_cache()

            logger.debug(f"Loaded {len(whitelist_data)} whitelist entries")
            ipguard_total = sum(len(v) for v in ipguard_data.values())
            logger.debug(f"Loaded {ipguard_total} IPGuard entries from {len(ipguard_data)} sources")

            # If IPGuard data is completely unavailable, abort recalculation
            # to prevent false non_compliant judgments
            if ipguard_total == 0:
                logger.warning(
                    "Compliance recalculation skipped: IPGuard data unavailable. "
                    "Terminal compliance statuses remain unchanged."
                )
                await _release_compliance_lock(lock_token)
                return {
                    "total": 0, "bypass": 0, "compliant": 0,
                    "non_compliant": 0, "unchanged": 0, "unblocked": 0,
                    "skipped": True, "reason": "ipguard_data_unavailable",
                }

            stmt = select(Terminal)
            result = await self.db.execute(stmt)
            terminals = result.scalars().all()

            logger.info(f"Found {len(terminals)} terminals to recalculate")

            if not terminals:
                logger.info("No terminals found, returning early")
                return {"total": 0, "bypass": 0, "compliant": 0, "non_compliant": 0, "unchanged": 0, "unblocked": 0}

            BATCH_SIZE = 100
            bypass_count = 0
            compliant_count = 0
            non_compliant_count = 0
            unchanged_count = 0
            unblocked_count = 0

            for batch_start in range(0, len(terminals), BATCH_SIZE):
                batch_terminals = terminals[batch_start:batch_start + BATCH_SIZE]
                batch_num = batch_start // BATCH_SIZE + 1
                total_batches = (len(terminals) + BATCH_SIZE - 1) // BATCH_SIZE

                logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(batch_terminals)} terminals)")

                for idx, terminal in enumerate(batch_terminals):
                    ip_addr = terminal.ip_address or ""
                    mac_addr = terminal.mac_address or ""
                    old_compliance = terminal.compliance_status

                    wl_result = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)
                    ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

                    if wl_result:
                        new_compliance = "bypass"
                        new_wl_match_type = wl_result.get("match_type")
                        wl_comments = wl_result.get("comments")
                        terminal.non_compliant_confirm_count = 0
                    elif ig_match:
                        new_compliance = "compliant"
                        new_wl_match_type = None
                        wl_comments = None
                        terminal.non_compliant_confirm_count = 0
                    else:
                        # IPGuard/whitelist both not matched
                        if old_compliance in ("non_compliant", "unknown"):
                            # Already non_compliant or new terminal → confirm immediately
                            new_compliance = "non_compliant"
                        else:
                            # Was compliant/bypass → require confirmation cycles
                            # to avoid false transitions from IPGuard data fluctuations
                            confirm_threshold = await self._get_confirm_threshold()
                            terminal.non_compliant_confirm_count += 1
                            if terminal.non_compliant_confirm_count >= confirm_threshold:
                                new_compliance = "non_compliant"
                                terminal.non_compliant_confirm_count = 0
                            else:
                                # Keep original status, don't trigger block/unblock
                                new_compliance = old_compliance
                                logger.debug(
                                    f"Terminal {ip_addr}/{mac_addr}: pending non_compliant confirmation "
                                    f"({terminal.non_compliant_confirm_count}/{confirm_threshold})"
                                )
                        new_wl_match_type = None
                        wl_comments = None

                    if old_compliance != new_compliance:
                        logger.debug(
                            f"Terminal[{batch_start + idx}] {ip_addr}/{mac_addr}: "
                            f"{old_compliance} → {new_compliance} "
                            f"(whitelist={bool(wl_result)}, ipguard={ig_match})"
                        )

                    result = await self._apply_compliance_result(
                        terminal, new_compliance, new_wl_match_type, wl_comments, ip_addr, mac_addr
                    )

                    if result["status_changed"]:
                        if new_compliance == "bypass":
                            bypass_count += 1
                        elif new_compliance == "compliant":
                            compliant_count += 1
                        else:
                            non_compliant_count += 1

                        if result["unblocked"]:
                            unblocked_count += 1
                    else:
                        unchanged_count += 1

                await self.db.flush()
                await self.db.commit()
                logger.debug(f"Batch {batch_num}/{total_batches} committed")

            end_time = datetime.now(UTC)
            duration_ms = (end_time - start_time).total_seconds() * 1000

            if non_compliant_count > 0 or unblocked_count > 0 or bypass_count > 0 or compliant_count > 0:
                await self.log_action("system", "recalculate_compliance", "terminal", None, {
                    "message": f"Compliance recalculation: {len(terminals)} total, "
                               f"{bypass_count} → bypass, {compliant_count} → compliant, "
                               f"{non_compliant_count} → non_compliant, {unblocked_count} auto-unblocked",
                    "total": len(terminals),
                    "bypass": bypass_count,
                    "compliant": compliant_count,
                    "non_compliant": non_compliant_count,
                    "unchanged": unchanged_count,
                    "unblocked": unblocked_count,
                    "duration_ms": round(duration_ms, 2),
                    "whitelist_entries": len(whitelist_data),
                    "ipguard_entries": ipguard_total,
                }, ip_address="System")

            logger.info(
                f"Compliance recalculation complete: {len(terminals)} total, "
                f"{bypass_count} → bypass, {compliant_count} → compliant, "
                f"{non_compliant_count} → non_compliant, {unchanged_count} unchanged, "
                f"{unblocked_count} auto-unblocked, duration={duration_ms:.2f}ms"
            )

            return {
                "total": len(terminals),
                "bypass": bypass_count,
                "compliant": compliant_count,
                "non_compliant": non_compliant_count,
                "unchanged": unchanged_count,
                "unblocked": unblocked_count,
                "duration_ms": round(duration_ms, 2),
            }
        finally:
            await _release_compliance_lock(lock_token)

    async def _get_bound_firewall_tag(self, source_tag: str) -> str | None:
        """Find the firewall data source tag bound to the given ARP source tag.

        Uses DataSourceBinding table to find the correct firewall for
        a terminal's ARP source, ensuring the right firewall is used
        for block/unblock operations.

        Note: Returns only the first matching firewall tag. For multi-firewall
        support, use _get_bound_firewall_tags() instead.
        """
        try:
            from app.models.data_source import DataSourceBinding
            stmt = select(DataSourceBinding.firewall_tag).where(
                DataSourceBinding.arp_source_tag == source_tag
            )
            result = await self.db.execute(stmt)
            row = result.first()
            return row[0] if row else None
        except Exception:
            return None

    async def _get_bound_firewall_tags(self, source_tag: str) -> list[str]:
        """Find all firewall data source tags bound to the given ARP source tag.

        Uses DataSourceBinding table to find all firewalls for
        a terminal's ARP source, ensuring block/unblock operations
        are executed on all bound firewalls.
        """
        try:
            from app.services.data_source_service import DataSourceService
            ds_service = DataSourceService(self.db)
            return await ds_service.get_firewall_tags_for_arp(source_tag)
        except Exception:
            return []

    async def _get_block_time(self) -> str:
        """Get the configured block_time for auto-block operations.

        Reads from ConfigService, defaults to '30d'.
        """
        try:
            from app.services.config_service import ConfigService
            config_service = ConfigService(self.db)
            return await config_service.get("block_time", "30d")
        except Exception:
            return "30d"

    async def _get_confirm_threshold(self) -> int:
        """Get compliance transition confirm threshold from system config.

        Number of consecutive non_compliant detections required before
        changing a terminal from compliant/bypass to non_compliant.
        Default is 2 (requires 2 consecutive sync cycles to confirm).
        """
        try:
            from app.services.config_service import ConfigService
            config_service = ConfigService(self.db)
            value = await config_service.get("compliance_confirm_threshold", "2")
            threshold = int(value)
            return max(1, min(10, threshold))
        except Exception:
            return 2

    async def log_action(self, username: str, action: str, resource_type: str,
                         resource_id: str | None, details: dict,
                         ip_address: str = None, resource_name: str = None):
        """Log an audit action with JSON details"""
        audit_log = AuditLog(
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id or "",
            resource_name=resource_name,
            details=json.dumps(details, ensure_ascii=False),
            ip_address=ip_address,
        )
        self.db.add(audit_log)
