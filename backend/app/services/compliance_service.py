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
from app.models.terminal import Terminal, TerminalStatus
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
SCOPE_CACHE_KEY = "compliance_scope:all"
SCOPE_CACHE_TTL = 300  # 5 minutes

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
        2. Check scope conditions (determines IP-only vs IP+MAC strategy)
        3. Check IPGuard baseline data (with scope-determined strategy) -> compliant
        4. Neither matches -> non_compliant

        Returns: {"compliance_status": str, "matched_sources": [...], "whitelisted": bool, "wl_match_type": Optional[str]}
        """
        matched_sources = []
        whitelisted = False
        wl_match_type = None

        # 1. Check whitelist (pre-filter)
        whitelist_result = await self._check_whitelist(ip_address, mac_address)
        if whitelist_result:
            whitelisted = True
            wl_match_type = whitelist_result.get("match_type")
            matched_sources.append("whitelist")

        # 2. Check scope conditions (strategy selection)
        scope_data = await self._load_scope_cache()
        use_ip_only = self._check_terminal_in_arp_scope(scope_data, ip_address, mac_address)
        ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)

        # 3. Check IPGuard baseline (with scope-determined strategy)
        if use_ip_only:
            ipguard_match = await self._check_ipguard_ip_only(ip_address)
        else:
            ipguard_match = await self._check_ipguard(ip_address, mac_address, ipguard_mac_prefixes)

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

        Performance optimization: load all whitelist, scope, and IPGuard data into memory at once.

        Args:
            entries: List of {"ip_address": str, "mac_address": str, "source_tag": str}

        Returns:
            ComplianceCheckResult with counts and details
        """
        # Load all data into memory once
        whitelist_data = await self._load_whitelist_cache()
        scope_data = await self._load_scope_cache()
        ipguard_data = await self._load_all_ipguard_cache()
        ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)

        compliant_list = []
        non_compliant_list = []
        bypass_list = []

        for entry in entries:
            ip_addr = entry.get("ip_address", "")
            mac_addr = entry.get("mac_address", "")

            # Check whitelist (pre-filter)
            wl_result = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)

            # Check scope conditions (strategy selection)
            use_ip_only = self._check_terminal_in_arp_scope(scope_data, ip_addr, mac_addr)

            # Check IPGuard (with scope-determined strategy)
            if use_ip_only:
                ig_match = self._match_ipguard_ip_only_in_memory(ipguard_data, ip_addr)
                entry["use_ip_only"] = True
            else:
                ig_match, ip_found, mac_found = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr, ipguard_mac_prefixes)
                entry["use_ip_only"] = False
                entry["ip_found"] = ip_found
                entry["mac_found"] = mac_found

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
        # Read configured block_time (default '30d') so residual auto-block
        # follows the same configurable duration as the main block path.
        block_time = await self._get_block_time()

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

        # Authoritative whitelist pre-check: whitelist is admin-configured truth;
        # compliance_status may be stale due to historical crashes, so never block a
        # whitelist-matched terminal here. Self-heal it to bypass and skip blocking.
        if non_compliant_entries:
            whitelist_data = await self._load_whitelist_cache()
            whitelist_fixed = 0
            entries_to_block = []
            for entry in non_compliant_entries:
                wl_hit = self._match_whitelist_in_memory(
                    whitelist_data, entry.ip_address or "", entry.mac_address or ""
                )
                if wl_hit:
                    entry.compliance_status = "bypass"
                    entry.compliant_confirm_count = 0
                    entry.non_compliant_confirm_count = 0
                    whitelist_fixed += 1
                    logger.info(
                        f"Auto-block skipped for {entry.ip_address}/{entry.mac_address}: "
                        f"whitelist match ({wl_hit.get('match_type')}), "
                        f"compliance_status set to bypass"
                    )
                else:
                    entries_to_block.append(entry)
            if whitelist_fixed > 0:
                await self.db.flush()
            non_compliant_entries = entries_to_block

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
            # Per-entry: track success per firewall independently
            entry_errors = []
            successfully_blocked_fw = []
            for fw_tag in firewall_tags:
                svc = sangfor_services.get(fw_tag)
                if not svc:
                    msg = f"Failed to block {entry.ip_address} on firewall '{fw_tag}': service not available"
                    entry_errors.append(msg)
                    errors.append(msg)
                    continue
                try:
                    result = await svc.block_ip(
                        [entry.ip_address],
                        source_tag=fw_tag,
                        reason=f"Auto-blocked: non-compliant (source={arp_source_tag})"
                    )
                    if result.get("code") == 0:
                        successfully_blocked_fw.append(fw_tag)
                        logger.debug(f"Blocked {entry.ip_address} on firewall '{fw_tag}'")
                    else:
                        error_msg = result.get("message", "unknown error")
                        msg = f"Failed to block {entry.ip_address} on firewall '{fw_tag}': {error_msg}"
                        entry_errors.append(msg)
                        errors.append(msg)
                except Exception as e:
                    msg = f"Error blocking {entry.ip_address} on firewall '{fw_tag}': {str(e)}"
                    entry_errors.append(msg)
                    errors.append(msg)

            any_success = len(successfully_blocked_fw) > 0

            if any_success:
                # Update MAC status
                entry.status = "blocked"
                entry.firewall_tag = successfully_blocked_fw[0] if len(successfully_blocked_fw) == 1 else ",".join(successfully_blocked_fw)
                # Update comments with block info
                fw_info = ",".join(successfully_blocked_fw)
                block_comment = f"Auto-blocked by TAM on firewall [{fw_info}]"
                if entry.comments:
                    entry.comments = f"{entry.comments}; {block_comment}"
                else:
                    entry.comments = block_comment

                # Create a separate Blacklist record only for firewalls that succeeded
                import re

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

                mac_norm = entry.mac_address.replace('-', '').replace(':', '').replace('.', '').upper() if entry.mac_address else None
                
                # Calculate detailed block reason (mirrors _apply_compliance_result)
                block_reason = "自动封锁：不合规"
                scope_data = await self._load_scope_cache()
                use_ip_only = self._check_terminal_in_arp_scope(scope_data, entry.ip_address, entry.mac_address)
                ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)

                if use_ip_only:
                    block_reason = "IP 不合规"
                else:
                    ipguard_data = await self._load_all_ipguard_cache()
                    _, ip_found, mac_found = self._match_ipguard_in_memory(
                        ipguard_data, entry.ip_address, entry.mac_address, ipguard_mac_prefixes
                    )

                    if not ip_found and not mac_found:
                        block_reason = "IP 和 MAC 都不合规"
                    elif not ip_found and mac_found:
                        block_reason = "IP 不合规，MAC 合规"
                    elif ip_found and not mac_found:
                        block_reason = "MAC 不合规，IP 合规"
                    else:
                        block_reason = "自动封锁：不合规"
                
                for fw_tag in successfully_blocked_fw:
                    # Check for existing entry (idempotency per firewall)
                    existing_stmt = select(Blacklist).where(
                        (Blacklist.ip_address == entry.ip_address) &
                        (Blacklist.mac_address_normalized == mac_norm) &
                        (Blacklist.firewall_tag == fw_tag) &
                        (Blacklist.unblocked_at.is_(None)) &
                        (Blacklist.auto_unblocked == False)
                    )
                    existing_result = await self.db.execute(existing_stmt)
                    existing_bl = existing_result.scalar_one_or_none()
                    if existing_bl:
                        logger.debug(f"Blacklist entry already exists for {entry.ip_address} MAC {entry.mac_address} on firewall '{fw_tag}', skipping")
                        continue

                    blacklist_entry = Blacklist(
                        ip_address=entry.ip_address,
                        mac_address=entry.mac_address,
                        mac_address_normalized=mac_norm,
                        reason=block_reason,
                        blocked_by="system",
                        expires_at=datetime.now(UTC) + td,
                        source_tag=arp_source_tag,
                        firewall_tag=fw_tag,
                        is_auto_blocked=True,
                        auto_unblocked=False,
                        last_operation_type="block",
                        last_operation_status="success",
                        last_operation_at=datetime.now(UTC),
                    )
                    try:
                        self.db.add(blacklist_entry)
                        await self.db.flush()
                    except IntegrityError:
                        await self.db.rollback()
                        logger.warning(f"Integrity error creating blacklist entry for {entry.ip_address} MAC {entry.mac_address} on firewall '{fw_tag}', skipping")
                        continue

                blocked += 1

                details.append({
                    "ip_address": entry.ip_address,
                    "mac_address": entry.mac_address,
                    "action": "blocked",
                    "firewall_tags": successfully_blocked_fw,
                    "errors": entry_errors if entry_errors else None,
                })

                # Emit terminal.blocked event for notification dispatch.
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
        scope_data = await self._load_scope_cache()
        ipguard_data = await self._load_all_ipguard_cache()
        ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)

        # Group entries by normalized MAC (IP may change due to DHCP,
        # MAC is the stable identifier for a network interface).
        # Process all firewall entries for a given terminal atomically —
        # only mark unblocked if ALL firewalls succeed.
        from collections import defaultdict
        entry_groups = defaultdict(list)
        for entry in auto_blocked_entries:
            # Normalize MAC for consistent grouping regardless of format
            raw_mac = entry.mac_address or ""
            mac_norm_key = raw_mac.replace('-', '').replace(':', '').replace('.', '').upper()
            # NULL-MAC entries (from firewall reconciliation) share the empty MAC;
            # group them by IP instead so distinct terminals don't collapse into one bucket.
            key = mac_norm_key if mac_norm_key else (entry.ip_address or "")
            entry_groups[key].append(entry)

        unblocked = 0
        skipped = 0
        errors = []
        details = []

        for group_key, entries in entry_groups.items():
            # Recover the normalized MAC for this group (empty for NULL-MAC groups).
            group_mac_norm = (
                entries[0].mac_address.replace('-', '').replace(':', '').replace('.', '').upper()
                if entries[0].mac_address else ""
            )

            # Lookup current terminal record: by MAC for MAC-bearing groups, by IP for
            # NULL-MAC groups (IP may have changed since block due to DHCP for MAC groups).
            if group_mac_norm:
                mac_stmt = select(Terminal).where(
                    Terminal.mac_address_normalized == group_mac_norm
                )
                mac_result = await self.db.execute(mac_stmt)
                terminal_record = mac_result.scalar_one_or_none()
            else:
                fallback_ip = entries[0].ip_address or ""
                ip_stmt = select(Terminal).where(Terminal.ip_address == fallback_ip)
                ip_result = await self.db.execute(ip_stmt)
                terminal_record = ip_result.scalar_one_or_none()

            # Use current terminal IP for compliance check; fall back to blacklist IP
            if terminal_record:
                current_ip = terminal_record.ip_address or ""
                current_mac = terminal_record.mac_address or ""
            else:
                # Terminal record may have been deleted, use first blacklist entry
                current_ip = entries[0].ip_address or ""
                current_mac = entries[0].mac_address or ""

            # Check if now compliant using CURRENT IP (important after DHCP change)
            wl_match = self._match_whitelist_in_memory(whitelist_data, current_ip, current_mac)
            use_ip_only = self._check_terminal_in_arp_scope(scope_data, current_ip, current_mac)
            if use_ip_only:
                ig_match = self._match_ipguard_ip_only_in_memory(ipguard_data, current_ip)
            else:
                ig_match, _, _ = self._match_ipguard_in_memory(ipguard_data, current_ip, current_mac, ipguard_mac_prefixes)

            if not (wl_match or ig_match):
                skipped += len(entries)
                continue

            # Cooldown protection: skip auto-unblock if this MAC was recently auto-blocked
            # within the cooldown period (default 10 minutes), to prevent rapid oscillation.
            # EXCEPTION: If whitelist matches, unblock immediately (bypass cooldown) -
            # whitelist is authoritative admin decision.
            _cooldown_skip_unblock = False
            if not wl_match:
                try:
                    cooldown_minutes = await self._get_cooldown_minutes()
                    cooldown_cutoff = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
                    bl_recent_block_stmt = select(Blacklist).where(
                        (Blacklist.mac_address_normalized == group_mac_norm) &
                        (Blacklist.is_auto_blocked == True) &
                        (Blacklist.blocked_at >= cooldown_cutoff) &
                        (Blacklist.auto_unblocked == False)
                    )
                    recent_block_result = await self.db.execute(bl_recent_block_stmt)
                    recent_block = recent_block_result.scalar_one_or_none()
                    if recent_block:
                        _cooldown_skip_unblock = True
                        skipped += len(entries)
                        logger.info(
                            f"Cooldown: skipping auto-unblock for MAC {group_mac_norm} - "
                            f"recently auto-blocked at {recent_block.blocked_at}, "
                            f"cooldown={cooldown_minutes}min"
                        )
                        continue
                except Exception:
                    pass  # Cooldown check failure should not prevent unblocking

            # Try to unblock on ALL firewalls for this terminal.
            # IMPORTANT: Unblock each firewall using the IP that was originally blocked
            # (stored in the blacklist entry), because that's the IP on the firewall's blocklist.
            all_success = True
            successfully_unblocked_entries = []

            for bl_entry in entries:
                blocked_ip = bl_entry.ip_address or current_ip
                fw_tag = bl_entry.firewall_tag
                if fw_tag:
                    try:
                        success = await self._unblock_on_firewall(blocked_ip, fw_tag)
                        if success:
                            successfully_unblocked_entries.append(bl_entry)
                        else:
                            all_success = False
                            errors.append(
                                f"Failed to unblock {blocked_ip} on firewall '{fw_tag}'"
                            )
                    except (ConnectionError, TimeoutError) as e:
                        all_success = False
                        errors.append(
                            f"Error unblocking {blocked_ip} on firewall '{fw_tag}': {str(e)}"
                        )
                        from app.services.event_emitter import emit_firewall_connection_lost
                        await emit_firewall_connection_lost(fw_tag, str(e))
                    except Exception as e:
                        all_success = False
                        errors.append(
                            f"Error unblocking {blocked_ip} on firewall '{fw_tag}': {str(e)}"
                        )
                else:
                    # No firewall_tag on blacklist entry — try to find binding
                    # via the terminal's source_tag (use multi-firewall method)
                    if bl_entry.source_tag:
                        fw_tags = await self._get_bound_firewall_tags(bl_entry.source_tag)
                        binding_success = True
                        for ft in fw_tags:
                            try:
                                success = await self._unblock_on_firewall(blocked_ip, ft)
                                if not success:
                                    binding_success = False
                                    all_success = False
                                    errors.append(
                                        f"Failed to unblock {blocked_ip} on firewall '{ft}' (resolved from binding)"
                                    )
                            except Exception as e:
                                binding_success = False
                                all_success = False
                                errors.append(
                                    f"Error unblocking {blocked_ip} on firewall '{ft}': {str(e)}"
                                )
                        if binding_success:
                            successfully_unblocked_entries.append(bl_entry)
                    else:
                        # No firewall at all, just mark as unblocked in DB
                        successfully_unblocked_entries.append(bl_entry)

            if all_success:
                # All firewalls unblocked — update Terminal and mark all entries
                # Determine unblock reason (IP/MAC combination, consistent with block)
                unblock_reason = self._build_unblock_reason(
                    bool(wl_match), use_ip_only, ipguard_data, current_ip, current_mac, ipguard_mac_prefixes
                )
                
                logger.info(
                    f"Auto-unblock: Setting reason for {len(successfully_unblocked_entries)} entries: "
                    f"reason='{unblock_reason}', current_ip={current_ip}, current_mac={current_mac}, "
                    f"wl_match={wl_match is not None}, use_ip_only={use_ip_only}, ig_match={ig_match}"
                )
                
                for bl_entry in successfully_unblocked_entries:
                    bl_entry.auto_unblocked = True
                    bl_entry.unblocked_at = datetime.now(UTC)
                    bl_entry.reason = unblock_reason
                    bl_entry.last_operation_type = "unblock"
                    bl_entry.last_operation_status = "success"
                    bl_entry.last_operation_at = datetime.now(UTC)
                    logger.debug(
                        f"Auto-unblock: Updated blacklist entry id={bl_entry.id}, ip={bl_entry.ip_address}, "
                        f"mac={bl_entry.mac_address}, reason='{unblock_reason}'"
                    )

                if terminal_record:
                    # Update terminal firewall status
                    terminal_record.status = "unblocked"
                    terminal_record.firewall_tag = None  # Clear firewall tag on unblock
                    if wl_match:
                        # Whitelist match is authoritative (static admin configuration):
                        # set compliance_status=bypass immediately so that retry-block
                        # won't re-block this terminal and the oscillation loop is broken.
                        terminal_record.compliance_status = "bypass"
                        terminal_record.compliant_confirm_count = 0
                        terminal_record.non_compliant_confirm_count = 0
                        logger.info(
                            f"Auto-unblock: set compliance_status=bypass directly for "
                            f"{current_ip}/{current_mac} (whitelist match: {wl_match})"
                        )
                    else:
                        # IPGuard match: unblock was executed on the basis of this
                        # compliance determination, so update compliance_status
                        # synchronously. Leaving it as non_compliant creates an
                        # intermediate state that (1) inflates the non-compliant
                        # count above the blocked count, and (2) gets re-blocked
                        # by retry-block after cooldown, causing oscillation.
                        terminal_record.compliance_status = "compliant"
                        terminal_record.compliant_confirm_count = 0
                        terminal_record.non_compliant_confirm_count = 0
                        logger.info(
                            f"Auto-unblock: set compliance_status=compliant directly for "
                            f"{current_ip}/{current_mac} (IPGuard match)"
                        )
                    terminal_record.wl_match_type = wl_match.get("match_type") if isinstance(wl_match, dict) else None
                    # Reset confirm count so next check will properly re-evaluate
                    terminal_record.non_compliant_confirm_count = 0
                    # Update comments with unblock info
                    resolved_fw = entries[0].firewall_tag or "N/A"
                    unblock_comment = f"Auto-unblocked by TAM from firewall [{resolved_fw}]"
                    if terminal_record.comments:
                        terminal_record.comments = f"{terminal_record.comments}; {unblock_comment}"
                    else:
                        terminal_record.comments = unblock_comment

                unblocked += 1
                details.append({
                    "ip_address": current_ip,
                    "mac_address": current_mac,
                    "action": "unblocked",
                    "reason": "now_compliant",
                })
            else:
                # Partial failure — only mark successfully unblocked entries
                # but leave Terminal status as blocked since some firewalls
                # still hold the block
                # Determine unblock reason for partial success (IP/MAC combination, consistent with block)
                partial_unblock_reason = self._build_unblock_reason(
                    bool(wl_match), use_ip_only, ipguard_data, current_ip, current_mac, ipguard_mac_prefixes
                ) + "（部分成功）"
                
                logger.info(
                    f"Auto-unblock (partial): Setting reason for {len(successfully_unblocked_entries)} entries: "
                    f"reason='{partial_unblock_reason}', current_ip={current_ip}, current_mac={current_mac}, "
                    f"wl_match={wl_match is not None}, use_ip_only={use_ip_only}"
                )
                
                for bl_entry in successfully_unblocked_entries:
                    bl_entry.auto_unblocked = True
                    bl_entry.unblocked_at = datetime.now(UTC)
                    bl_entry.reason = partial_unblock_reason
                    bl_entry.last_operation_type = "unblock"
                    bl_entry.last_operation_status = "success"
                    bl_entry.last_operation_at = datetime.now(UTC)
                    logger.debug(
                        f"Auto-unblock (partial): Updated blacklist entry id={bl_entry.id}, ip={bl_entry.ip_address}, "
                        f"mac={bl_entry.mac_address}, reason='{partial_unblock_reason}'"
                    )
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
    async def _check_ipguard(self, ip_address: str, mac_address: str, ipguard_mac_prefixes: list[str] | None = None) -> bool:
        """Check if IP+MAC matches any IPGuard baseline entry"""
        ipguard_data = await self._load_all_ipguard_cache()
        is_compliant, _, _ = self._match_ipguard_in_memory(ipguard_data, ip_address, mac_address, ipguard_mac_prefixes)
        return is_compliant

    def _match_ipguard_in_memory(
        self, ipguard_data: dict[str, list[dict]], ip_address: str, mac_address: str,
        ipguard_mac_prefixes: list[str] | None = None,
    ) -> tuple[bool, bool, bool]:
        """Match IP+MAC against in-memory IPGuard data from all sources.

        Matching order:
        1. Exact IP+MAC match
        2. IP match + IPGuard entry MAC matches any mac_prefix_ipguard scope

        Returns:
            tuple: (is_compliant, is_ip_match, is_mac_match)
        """
        normalized_mac = mac_address.upper().replace(":", "-") if mac_address else ""
        ip_found = False
        mac_found = False

        for _source_tag, entries in ipguard_data.items():
            for entry in entries:
                entry_ip = entry.get("ip_address")
                entry_mac = entry.get("mac_address", "").upper().replace(":", "-")

                if entry_ip == ip_address:
                    ip_found = True
                    # 1. Exact IP+MAC match
                    if entry_mac == normalized_mac:
                        return (True, True, True)
                    # 2. IP match + IPGuard MAC prefix match
                    if ipguard_mac_prefixes and self._mac_matches_any_prefix(entry_mac, ipguard_mac_prefixes):
                        return (True, True, True)

                # Check if MAC matches any entry (even with different IP)
                if entry_mac == normalized_mac:
                    mac_found = True

        # If we got here, no full match. Check what parts matched.
        is_compliant = False
        return (is_compliant, ip_found, mac_found)

    async def _check_ipguard_ip_only(self, ip_address: str) -> bool:
        """Check IP-only match against IPGuard baseline data"""
        ipguard_data = await self._load_all_ipguard_cache()
        return self._match_ipguard_ip_only_in_memory(ipguard_data, ip_address)

    def _match_ipguard_ip_only_in_memory(
        self, ipguard_data: dict[str, list[dict]], ip_address: str
    ) -> bool:
        """Match IP-only against in-memory IPGuard data (ignore MAC)"""
        for _source_tag, entries in ipguard_data.items():
            for entry in entries:
                if entry.get("ip_address") == ip_address:
                    return True
        return False

    def _build_unblock_reason(
        self,
        wl_match: bool,
        use_ip_only: bool,
        ipguard_data: dict[str, list[dict]],
        current_ip: str,
        current_mac: str,
        ipguard_mac_prefixes: list[str] | None,
    ) -> str:
        """Build a detailed unblock reason, mirroring the block-side IP/MAC breakdown.

        Whitelist matches always unblock with '加入白名单'. For IPGuard compliance,
        the reason reflects whether the IP, MAC, or both matched the baseline, so the
        unblock reason stays consistent with the block reason granularity.
        """
        if wl_match:
            return "加入白名单"
        if use_ip_only:
            return "IP 合规"
        _, ip_found, mac_found = self._match_ipguard_in_memory(
            ipguard_data, current_ip, current_mac, ipguard_mac_prefixes
        )
        if ip_found and mac_found:
            return "IP 和 MAC 都合规"
        if ip_found and not mac_found:
            return "IP 合规，MAC 不合规"
        if not ip_found and mac_found:
            return "MAC 合规，IP 不合规"
        return "合规解封"

    # ------------------------------------------------------------------
    # Scope Conditions
    # ------------------------------------------------------------------
    async def _load_scope_cache(self) -> list[dict]:
        """Load all active compliance scope conditions from Redis cache or database"""
        try:
            redis = await _get_redis()
            cached = await redis.get(SCOPE_CACHE_KEY)
            if cached:
                data = json.loads(cached if isinstance(cached, str) else cached.decode())
                return data
        except Exception:
            pass

        from app.models.compliance_scope import ComplianceScope as ComplianceScopeModel
        stmt = select(ComplianceScopeModel).where(ComplianceScopeModel.is_active == True)
        result = await self.db.execute(stmt)
        entries = result.scalars().all()

        data = []
        for entry in entries:
            data.append({
                "id": entry.id,
                "scope_type": entry.scope_type,
                "scope_value": entry.scope_value,
                "description": entry.description,
            })

        try:
            redis = await _get_redis()
            scope_ttl = await get_config_value("cache_scope_ttl", WHITELIST_CACHE_TTL)
            await redis.setex(SCOPE_CACHE_KEY, scope_ttl, json.dumps(data))
        except Exception:
            pass

        return data

    @staticmethod
    def _mac_matches_any_prefix(mac: str, prefixes: list[str]) -> bool:
        """Check if a MAC address matches any of the given prefixes.
        Both mac and prefixes should already be normalized (uppercase, no separators).
        """
        if not mac or not prefixes:
            return False
        normalized_mac = mac.upper().replace(":", "").replace("-", "")
        for prefix in prefixes:
            norm_prefix = prefix.upper().replace(":", "").replace("-", "")
            if len(normalized_mac) >= len(norm_prefix) and normalized_mac.startswith(norm_prefix):
                return True
        return False

    @staticmethod
    def _extract_ipguard_mac_prefixes(scope_data: list[dict]) -> list[str]:
        """Extract mac_prefix_ipguard values from scope data."""
        prefixes = []
        for scope in scope_data:
            if scope.get("scope_type") == "mac_prefix_ipguard":
                prefixes.append(scope.get("scope_value", ""))
        return prefixes

    def _check_terminal_in_arp_scope(self, scope_data: list[dict], ip_address: str, mac_address: str) -> bool:
        """
        Check if terminal falls within any ARP-level scope condition (ip_cidr, ip_range, mac_prefix_arp).
        Returns True if the terminal should use IP-only strategy.
        """
        if not scope_data:
            return False

        for scope in scope_data:
            scope_type = scope.get("scope_type", "")
            scope_value = scope.get("scope_value", "")

            if scope_type == "ip_cidr":
                try:
                    network = ipaddress.ip_network(scope_value, strict=False)
                    ip = ipaddress.ip_address(ip_address)
                    if ip in network:
                        return True
                except (ValueError, TypeError):
                    continue

            elif scope_type == "ip_range":
                try:
                    start_ip_str, end_ip_str = scope_value.split("-")
                    start_ip = int(ipaddress.IPv4Address(start_ip_str))
                    end_ip = int(ipaddress.IPv4Address(end_ip_str))
                    ip_val = int(ipaddress.IPv4Address(ip_address))
                    if start_ip <= ip_val <= end_ip:
                        return True
                except (ValueError, TypeError):
                    continue

            elif scope_type == "mac_prefix_arp":
                try:
                    if self._mac_matches_any_prefix(mac_address, [scope_value]):
                        return True
                except (ValueError, TypeError):
                    continue

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

    async def apply_initial_compliance_result(
        self,
        terminal: Terminal,
        new_compliance: str,
        new_wl_match_type: str | None,
        wl_comments: str | None,
        ip_addr: str,
        mac_addr: str,
    ) -> dict:
        """Apply compliance result for a newly discovered (unknown) terminal.

        Mirrors the confirm-threshold logic in recalculate_all_compliance so the
        first-discovery path no longer blocks non_compliant terminals instantly:

        - bypass: authoritative whitelist match, applied immediately.
        - compliant: applied immediately (prompt upgrade has no block risk).
        - non_compliant: accumulates non_compliant_confirm_count; only downgrades
          and blocks once the count reaches compliance_confirm_threshold.
        """
        if new_compliance == "non_compliant":
            terminal.non_compliant_confirm_count = (terminal.non_compliant_confirm_count or 0) + 1
            terminal.compliant_confirm_count = 0
            threshold = await self._get_confirm_threshold()
            if terminal.non_compliant_confirm_count < threshold:
                logger.info(
                    f"First-discovery {ip_addr}/{mac_addr}: non_compliant confirm "
                    f"{terminal.non_compliant_confirm_count}/{threshold}, holding "
                    f"(not blocking yet)"
                )
                return {"status_changed": False, "new_compliance": terminal.compliance_status, "unblocked": False}
            terminal.non_compliant_confirm_count = 0
        elif new_compliance in ("compliant", "bypass"):
            terminal.non_compliant_confirm_count = 0

        return await self._apply_compliance_result(
            terminal, new_compliance, new_wl_match_type, wl_comments, ip_addr, mac_addr
        )

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

        _block_failed = False
        _cooldown_skip_downgrade = False

        old_compliance = terminal.compliance_status
        
        # Get detailed match info for non-compliant terminals
        block_reason = "自动封锁：不合规"
        if new_compliance == "non_compliant":
            scope_data = await self._load_scope_cache()
            use_ip_only = self._check_terminal_in_arp_scope(scope_data, ip_addr, mac_addr)
            ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)
            
            if use_ip_only:
                # IP-only scope, just say IP is non-compliant
                block_reason = "IP 不合规"
            else:
                # Get detailed match info
                ipguard_data = await self._load_all_ipguard_cache()
                _, ip_found, mac_found = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr, ipguard_mac_prefixes)
                
                if not ip_found and not mac_found:
                    block_reason = "IP 和 MAC 都不合规"
                elif not ip_found and mac_found:
                    block_reason = "IP 不合规，MAC 合规"
                elif ip_found and not mac_found:
                    block_reason = "MAC 不合规，IP 合规"
                else:
                    block_reason = "自动封锁：不合规"

        # Pre-check: cooling period for downgrade to non_compliant (prevent intermediate state)
        if new_compliance == "non_compliant":
            try:
                cooldown_minutes = await self._get_cooldown_minutes()
                cooldown_cutoff = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
                bl_recent_stmt = select(Blacklist).where(
                    (Blacklist.mac_address_normalized == mac_norm) &
                    (Blacklist.auto_unblocked == True) &
                    (Blacklist.unblocked_at.isnot(None)) &
                    (Blacklist.unblocked_at >= cooldown_cutoff)
                )
                recent_result = await self.db.execute(bl_recent_stmt)
                recent_unblock = recent_result.scalar_one_or_none()
                if recent_unblock:
                    _cooldown_skip_downgrade = True
                    logger.info(
                        f"Cooldown: skipping compliance downgrade for {ip_addr}/{mac_addr} - "
                        f"recently auto-unblocked at {recent_unblock.unblocked_at}, "
                        f"cooldown={cooldown_minutes}min"
                    )
            except Exception:
                pass

        if _cooldown_skip_downgrade:
            # Keep original compliance status to avoid intermediate state
            return {"status_changed": False, "new_compliance": old_compliance, "unblocked": False}

        # Normal processing
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
                # Cooldown protection: skip auto-unblock if this MAC was recently auto-blocked
                # within the cooldown period (default 10 minutes), to prevent rapid oscillation.
                # EXCEPTION: Bypass (whitelist) always unblocks immediately - whitelist is authoritative.
                _cooldown_skip_unblock = False
                if new_compliance != "bypass":
                    try:
                        cooldown_minutes = await self._get_cooldown_minutes()
                        cooldown_cutoff = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
                        bl_recent_block_stmt = select(Blacklist).where(
                            (Blacklist.mac_address_normalized == mac_norm) &
                            (Blacklist.is_auto_blocked == True) &
                            (Blacklist.blocked_at >= cooldown_cutoff) &
                            (Blacklist.auto_unblocked == False)
                        )
                        recent_block_result = await self.db.execute(bl_recent_block_stmt)
                        recent_block = recent_block_result.scalar_one_or_none()
                        if recent_block:
                            _cooldown_skip_unblock = True
                            logger.info(
                                f"Cooldown: skipping auto-unblock for {ip_addr}/{mac_addr} - "
                                f"recently auto-blocked at {recent_block.blocked_at}, "
                                f"cooldown={cooldown_minutes}min"
                            )
                    except Exception:
                        pass  # Cooldown check failure should not prevent unblocking

                if not _cooldown_skip_unblock:
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
                            
                            # Determine unblock reason based on new compliance status
                            # (IP/MAC combination, consistent with block)
                            if new_compliance == "bypass":
                                compliance_unblock_reason = "加入白名单"
                            else:
                                scope_data = await self._load_scope_cache()
                                use_ip_only = self._check_terminal_in_arp_scope(scope_data, ip_addr, mac_addr)
                                ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)
                                ipguard_data = await self._load_all_ipguard_cache()
                                compliance_unblock_reason = self._build_unblock_reason(
                                    False, use_ip_only, ipguard_data, ip_addr, mac_addr, ipguard_mac_prefixes
                                )
                            
                            logger.info(
                                f"_apply_compliance_result: Setting reason for unblock: "
                                f"reason='{compliance_unblock_reason}', ip={ip_addr}, mac={mac_addr}, "
                                f"new_compliance={new_compliance}, old_status={terminal.status}"
                            )
                            
                            # Query by MAC only (IP may change due to DHCP)
                            bl_stmt = select(Blacklist).where(
                                (Blacklist.mac_address_normalized == mac_norm) &
                                (Blacklist.unblocked_at.is_(None)) &
                                (Blacklist.auto_unblocked == False)
                            )
                            bl_result = await self.db.execute(bl_stmt)
                            bl_entries = bl_result.scalars().all()
                            for bl_entry in bl_entries:
                                bl_entry.auto_unblocked = True
                                bl_entry.unblocked_at = datetime.now(UTC)
                                bl_entry.reason = compliance_unblock_reason
                                bl_entry.last_operation_type = "unblock"
                                bl_entry.last_operation_status = "success"
                                bl_entry.last_operation_at = datetime.now(UTC)
                                logger.debug(
                                    f"_apply_compliance_result: Updated blacklist entry id={bl_entry.id}, "
                                    f"ip={bl_entry.ip_address}, mac={bl_entry.mac_address}, reason='{compliance_unblock_reason}'"
                                )
                            
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

            # Check if terminal needs (re-)block: non-compliant AND no active blacklist entry on ALL required firewalls
            # This handles the case where a terminal was blocked, became compliant (auto-unblocked),
            # then became non-compliant again - the terminal status may still be "blocked" from
            # the previous block, but the blacklist entry was auto-unblocked and needs recreation.
            # Query by MAC only (IP may change due to DHCP; blacklist entries may have stale IP).
            bl_active_stmt = select(Blacklist.firewall_tag).where(
                (Blacklist.mac_address_normalized == mac_norm) &
                (Blacklist.auto_unblocked == False) &
                (Blacklist.unblocked_at.is_(None))
            )
            bl_active_result = await self.db.execute(bl_active_stmt)
            active_fw_tags = {row[0] for row in bl_active_result.all()}

            # Cooldown protection: skip auto-block if terminal was recently auto-unblocked
            # within the cooldown period (default 10 minutes), to prevent rapid oscillation.
            _cooldown_skip_block = False
            if new_compliance == "non_compliant":
                # Check if missing entries on any required firewall
                fw_tags = await self._get_bound_firewall_tags(terminal.source_tag)
                missing_fw_tags = [fw for fw in fw_tags if fw not in active_fw_tags]

                if not missing_fw_tags:
                    if not fw_tags:
                        # No bound firewall: cannot block, do NOT forge blocked status.
                        terminal.status = "unblocked"
                        terminal.firewall_tag = None
                    elif terminal.status != "blocked":
                        # All firewalls already have active entries, ensure terminal status is correct
                        terminal.status = "blocked"
                        terminal.firewall_tag = fw_tags[0] if len(fw_tags) == 1 else ",".join(fw_tags)
                else:
                    # Need to block on missing firewalls
                    try:
                        cooldown_minutes = await self._get_cooldown_minutes()
                        cooldown_cutoff = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
                        bl_recent_stmt = select(Blacklist).where(
                            (Blacklist.mac_address_normalized == mac_norm) &
                            (Blacklist.auto_unblocked == True) &
                            (Blacklist.unblocked_at.isnot(None)) &
                            (Blacklist.unblocked_at >= cooldown_cutoff)
                        )
                        recent_result = await self.db.execute(bl_recent_stmt)
                        recent_unblock = recent_result.scalar_one_or_none()
                        if recent_unblock:
                            _cooldown_skip_block = True
                            logger.info(
                                f"Cooldown: skipping auto-block for {ip_addr}/{mac_addr} - "
                                f"recently auto-unblocked at {recent_unblock.unblocked_at}, "
                                f"cooldown={cooldown_minutes}min"
                            )
                    except Exception:
                        pass  # Cooldown check failure should not block blocking

                    if not _cooldown_skip_block:
                        successfully_blocked_fw = []
                        block_errors = []
                        for fw_tag in missing_fw_tags:
                            try:
                                # Check if actually already blocked on firewall (terminal status may be stale)
                                already_blocked_on_fw = (
                                    terminal.status == "blocked" and
                                    terminal.firewall_tag and fw_tag in terminal.firewall_tag.split(",")
                                )
                                if already_blocked_on_fw:
                                    successfully_blocked_fw.append(fw_tag)
                                    logger.debug(f"Terminal {ip_addr} already marked blocked on firewall '{fw_tag}'")
                                    continue

                                success = await self._block_on_firewall(
                                    ip_addr, fw_tag,
                                    reason="Auto-blocked: compliance recalculation"
                                )
                                if success:
                                    successfully_blocked_fw.append(fw_tag)
                                else:
                                    block_errors.append(f"Failed to block {ip_addr} on firewall '{fw_tag}'")
                                    logger.warning(f"Failed to auto-block {ip_addr} on firewall '{fw_tag}'")
                            except Exception as e:
                                block_errors.append(f"Error blocking {ip_addr} on firewall '{fw_tag}': {e}")
                                logger.warning(f"Error auto-blocking {ip_addr} on firewall '{fw_tag}': {e}")

                        # Create Blacklist entries only for successfully blocked firewalls
                        if successfully_blocked_fw:
                            # Parse block duration
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

                            for fw_tag in successfully_blocked_fw:
                                # Double-check idempotency per firewall
                                existing_check = select(Blacklist).where(
                                    (Blacklist.ip_address == ip_addr) &
                                    (Blacklist.mac_address_normalized == mac_norm) &
                                    (Blacklist.firewall_tag == fw_tag) &
                                    (Blacklist.unblocked_at.is_(None)) &
                                    (Blacklist.auto_unblocked == False)
                                )
                                existing_result = await self.db.execute(existing_check)
                                if existing_result.scalar_one_or_none():
                                    continue

                                bl_entry = Blacklist(
                                    ip_address=ip_addr,
                                    mac_address=mac_addr,
                                    mac_address_normalized=mac_norm,
                                    reason=block_reason,
                                    blocked_by="system",
                                    expires_at=datetime.now(UTC) + td,
                                    source_tag=terminal.source_tag,
                                    firewall_tag=fw_tag,
                                    is_auto_blocked=True,
                                    auto_unblocked=False,
                                    last_operation_type="block",
                                    last_operation_status="success",
                                    last_operation_at=datetime.now(UTC),
                                )
                                try:
                                    self.db.add(bl_entry)
                                    await self.db.flush()
                                except IntegrityError:
                                    await self.db.rollback()
                                    logger.warning(f"Integrity error creating blacklist entry for {ip_addr} MAC {mac_addr} on firewall '{fw_tag}' during recalculation")
                                    continue

                            # Update terminal status with ALL active firewalls
                            all_active_fw = list(active_fw_tags | set(successfully_blocked_fw))
                            terminal.status = "blocked"
                            terminal.firewall_tag = all_active_fw[0] if len(all_active_fw) == 1 else ",".join(all_active_fw)
                            fw_info = ",".join(successfully_blocked_fw)
                            block_comment = f"Auto-blocked by TAM on firewall [{fw_info}]"
                            if terminal.comments:
                                terminal.comments = f"{terminal.comments}; {block_comment}"
                            else:
                                terminal.comments = block_comment

                            if block_errors:
                                logger.warning(f"Partial block for {ip_addr}: succeeded on {successfully_blocked_fw}, failed: {block_errors}")
                            else:
                                logger.info(f"Auto-blocked {ip_addr} (now non_compliant) on firewall(s) '{fw_info}'")
                        else:
                            # All firewall blocks failed, rollback compliance status to old value
                            terminal.compliance_status = old_compliance
                            logger.warning(
                                f"Rollback compliance status to {old_compliance} for {ip_addr}/{mac_addr} - "
                                f"failed to block on all required firewalls"
                            )
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
            scope_data = await self._load_scope_cache()
            ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)

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

            ipguard_cache_stale = await self._is_ipguard_cache_stale()
            if ipguard_cache_stale:
                logger.warning("IPGuard cache is stale; downgrades to non_compliant will be held this cycle")

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
            corrected_count = 0
            stale_skip_count = 0

            for batch_start in range(0, len(terminals), BATCH_SIZE):
                batch_terminals = terminals[batch_start:batch_start + BATCH_SIZE]
                batch_num = batch_start // BATCH_SIZE + 1
                total_batches = (len(terminals) + BATCH_SIZE - 1) // BATCH_SIZE

                logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(batch_terminals)} terminals)")

                for idx, terminal in enumerate(batch_terminals):
                    ip_addr = terminal.ip_address or ""
                    mac_addr = terminal.mac_address or ""
                    old_compliance = terminal.compliance_status
                    confirm_threshold = await self._get_confirm_threshold()

                    wl_result = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)
                    use_ip_only = self._check_terminal_in_arp_scope(scope_data, ip_addr, mac_addr)
                    if use_ip_only:
                        ig_match = self._match_ipguard_ip_only_in_memory(ipguard_data, ip_addr)
                    else:
                        ig_match, _, _ = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr, ipguard_mac_prefixes)

                    # Initialize compliant_confirm_count if not present (handles pre-migration records)
                    if not hasattr(terminal, 'compliant_confirm_count') or terminal.compliant_confirm_count is None:
                        terminal.compliant_confirm_count = 0

                    new_compliance = old_compliance  # default: stay

                    # ---- IP change grace period ----
                    # If IP was recently changed (within ~10min), do NOT downgrade non-bypass
                    # terminals to non_compliant yet to wait for IPGuard baseline to catch up.
                    in_ip_grace_period = False
                    if terminal.ip_changed_at is not None and old_compliance != "bypass":
                        grace_minutes = await self._get_ip_grace_minutes()
                        grace_cutoff = datetime.now(UTC) - timedelta(minutes=grace_minutes)
                        if terminal.ip_changed_at >= grace_cutoff:
                            in_ip_grace_period = True

                    # ---- Determine new compliance status ----
                    if wl_result:
                        # WHITELIST MATCH IS AUTHORITATIVE - immediately bypass, NO confirm count needed.
                        # Whitelist is static admin configuration, no oscillation risk from this decision.
                        current_check_status = "bypass"
                        new_wl_match_type = wl_result.get("match_type")
                        wl_comments = wl_result.get("comments")
                        new_compliance = "bypass"
                        terminal.compliant_confirm_count = 0
                        terminal.non_compliant_confirm_count = 0
                    elif not in_ip_grace_period and ig_match:
                        current_check_status = "compliant"
                        new_wl_match_type = None
                        wl_comments = None

                        # IPGuard match - symmetric confirm for anti-oscillation
                        if current_check_status == old_compliance:
                            terminal.non_compliant_confirm_count = 0
                        else:
                            terminal.compliant_confirm_count += 1
                            terminal.non_compliant_confirm_count = 0
                            if terminal.compliant_confirm_count >= confirm_threshold:
                                new_compliance = "compliant"
                                terminal.compliant_confirm_count = 0
                                logger.info(
                                    f"Terminal[{batch_start + idx}] {ip_addr}/{mac_addr}: "
                                    f"CONFIRMED upgrade non_compliant → compliant after {confirm_threshold} checks"
                                )
                            else:
                                new_compliance = old_compliance  # hold
                    elif not in_ip_grace_period:
                        if ipguard_cache_stale:
                            current_check_status = "compliant"
                            new_wl_match_type = None
                            wl_comments = None
                            new_compliance = old_compliance  # hold, cache stale -> no downgrade
                            stale_skip_count += 1
                        else:
                            current_check_status = "non_compliant"
                            new_wl_match_type = None
                            wl_comments = None

                            if old_compliance == "bypass":
                                # SPECIAL PROTECTION: Currently whitelisted but this check missed whitelist.
                                # Require 6 CONSECUTIVE misses (~30 minutes) before downgrading,
                                # to avoid false positives from transient cache failures.
                                terminal.non_compliant_confirm_count += 1
                                whitelist_miss_threshold = await self._get_whitelist_miss_threshold()
                                if terminal.non_compliant_confirm_count >= whitelist_miss_threshold:
                                    new_compliance = "non_compliant"
                                    terminal.non_compliant_confirm_count = 0
                                    logger.warning(
                                        f"Terminal[{batch_start + idx}] {ip_addr}/{mac_addr}: "
                                        f"WHITELIST MISS {whitelist_miss_threshold} consecutive times, "
                                        f"downgrading bypass → non_compliant"
                                    )
                                else:
                                    new_compliance = "bypass"  # hold bypass
                                    logger.debug(
                                        f"Terminal[{batch_start + idx}] {ip_addr}/{mac_addr}: "
                                        f"whitelist transient miss ({terminal.non_compliant_confirm_count}/{whitelist_miss_threshold}), "
                                        f"holding bypass"
                                    )
                            else:
                                # Normal downgrade path with confirm threshold
                                if current_check_status == old_compliance:
                                    terminal.compliant_confirm_count = 0
                                else:
                                    terminal.non_compliant_confirm_count += 1
                                    terminal.compliant_confirm_count = 0
                                    if terminal.non_compliant_confirm_count >= confirm_threshold:
                                        new_compliance = "non_compliant"
                                        terminal.non_compliant_confirm_count = 0
                                        logger.info(
                                            f"Terminal[{batch_start + idx}] {ip_addr}/{mac_addr}: "
                                            f"CONFIRMED downgrade {old_compliance} → non_compliant after {confirm_threshold} checks"
                                        )
                                    else:
                                        new_compliance = old_compliance  # hold

                    if old_compliance != new_compliance:
                        logger.info(
                            f"Terminal[{batch_start + idx}] {ip_addr}/{mac_addr}: "
                            f"{old_compliance} → {new_compliance} "
                            f"(whitelist={bool(wl_result)}, ipguard={ig_match}, grace={in_ip_grace_period})"
                        )
                        if old_compliance == "compliant" and new_compliance == "non_compliant":
                            corrected_count += 1
                            logger.warning(
                                f"Terminal[{batch_start + idx}] {ip_addr}/{mac_addr}: "
                                f"misclassification corrected (compliant → non_compliant, ipguard={ig_match})"
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
                               f"{non_compliant_count} → non_compliant, {corrected_count} corrected, "
                               f"{stale_skip_count} stale-held, {unblocked_count} auto-unblocked",
                    "total": len(terminals),
                    "bypass": bypass_count,
                    "compliant": compliant_count,
                    "non_compliant": non_compliant_count,
                    "corrected": corrected_count,
                    "stale_skip_count": stale_skip_count,
                    "ipguard_cache_stale": ipguard_cache_stale,
                    "unchanged": unchanged_count,
                    "unblocked": unblocked_count,
                    "duration_ms": round(duration_ms, 2),
                    "whitelist_entries": len(whitelist_data),
                    "ipguard_entries": ipguard_total,
                }, ip_address="System")

            logger.info(
                f"Compliance recalculation complete: {len(terminals)} total, "
                f"{bypass_count} → bypass, {compliant_count} → compliant, "
                f"{non_compliant_count} → non_compliant, {corrected_count} corrected, "
                f"{stale_skip_count} stale-held, {unchanged_count} unchanged, "
                f"{unblocked_count} auto-unblocked, cache_stale={ipguard_cache_stale}, duration={duration_ms:.2f}ms"
            )

            return {
                "total": len(terminals),
                "bypass": bypass_count,
                "compliant": compliant_count,
                "non_compliant": non_compliant_count,
                "corrected": corrected_count,
                "stale_skip_count": stale_skip_count,
                "ipguard_cache_stale": ipguard_cache_stale,
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
            return await config_service.get("block_time") or "30d"
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
            value = await config_service.get("compliance_confirm_threshold") or "2"
            threshold = int(value)
            return max(1, min(10, threshold))
        except Exception:
            return 2

    async def _get_ipguard_stale_threshold_minutes(self) -> int:
        """Get IPGuard cache stale threshold from system config (default 12min)."""
        try:
            from app.services.config_service import ConfigService
            config_service = ConfigService(self.db)
            value = await config_service.get("ipguard_stale_threshold_minutes") or "12"
            threshold = int(value)
            return max(5, min(60, threshold))
        except Exception:
            return 12

    async def _get_cooldown_minutes(self) -> int:
        """Get compliance transition cooldown period from system config (default 10min)."""
        try:
            from app.services.config_service import ConfigService
            config_service = ConfigService(self.db)
            value = await config_service.get("compliance_cooldown_minutes") or "10"
            minutes = int(value)
            return max(1, min(60, minutes))
        except Exception:
            return 10

    async def _get_ip_grace_minutes(self) -> int:
        """Get IP change grace period from system config (default 10min)."""
        try:
            from app.services.config_service import ConfigService
            config_service = ConfigService(self.db)
            value = await config_service.get("compliance_ip_grace_minutes") or "10"
            minutes = int(value)
            return max(1, min(60, minutes))
        except Exception:
            return 10

    async def _get_whitelist_miss_threshold(self) -> int:
        """Get consecutive whitelist-miss threshold from system config (default 6)."""
        try:
            from app.services.config_service import ConfigService
            config_service = ConfigService(self.db)
            value = await config_service.get("compliance_whitelist_miss_threshold") or "6"
            threshold = int(value)
            return max(2, min(20, threshold))
        except Exception:
            return 6

    async def _is_ipguard_cache_stale(self) -> bool:
        """Return True if IPGuard cache is stale (last sync exceeds threshold)."""
        threshold = await self._get_ipguard_stale_threshold_minutes()
        stmt = select(ComplianceBaseline).where(ComplianceBaseline.enabled == True)
        result = await self.db.execute(stmt)
        baselines = result.scalars().all()
        if not baselines:
            return True
        sync_times = [b.last_sync_at for b in baselines if b.last_sync_at is not None]
        if not sync_times:
            return True  # never synced yet
        newest = max(sync_times)
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=UTC)
        age_minutes = (datetime.now(UTC) - newest).total_seconds() / 60.0
        return age_minutes > threshold

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

    async def apply_manual_whitelist_for_terminal(
        self,
        terminal,
        wl_match_type: str,
        wl_comments: str | None,
        username: str,
    ) -> dict:
        """Apply manual whitelist to a single terminal immediately.

        This bypasses cooldown protection because it's an explicit user action.
        - Sets compliance_status to bypass immediately
        - Unblocks on firewall if currently blocked, regardless of cooldown
        - Does NOT trigger full compliance recalculation

        Returns dict with status info.
        """
        from app.core.timezone import now_utc

        ip_addr = terminal.ip_address or ""
        mac_addr = terminal.mac_address or ""
        mac_norm = terminal.mac_address_normalized or (
            mac_addr.replace("-", "").replace(":", "").replace(".", "").upper() if mac_addr else ""
        )

        # Invalidate whitelist cache to ensure fresh state
        await self.invalidate_whitelist_cache()

        old_compliance = terminal.compliance_status
        old_status = terminal.status

        # Update terminal compliance fields immediately
        terminal.compliance_status = "bypass"
        terminal.wl_match_type = wl_match_type
        terminal.wl_comments = wl_comments
        # Reset anti-oscillation counters
        terminal.compliant_confirm_count = 0
        terminal.non_compliant_confirm_count = 0

        unblocked = False

        # If terminal is currently blocked, unblock immediately (bypass cooldown)
        if old_status == "blocked":
            logger.info(
                f"Manual whitelist: immediately unblocking {ip_addr}/{mac_addr} "
                f"on all firewalls (bypassing cooldown, triggered by user '{username}')"
            )

            # Query ALL active blacklist entries for this MAC
            bl_stmt = select(Blacklist).where(
                (Blacklist.mac_address_normalized == mac_norm) &
                (Blacklist.unblocked_at.is_(None)) &
                (Blacklist.auto_unblocked == False)
            )
            bl_result = await self.db.execute(bl_stmt)
            bl_entries = bl_result.scalars().all()

            successfully_unblocked = []
            unblock_errors = []

            for bl_entry in bl_entries:
                blocked_ip = bl_entry.ip_address or ip_addr
                fw_tag = bl_entry.firewall_tag

                if not fw_tag:
                    # Try to get firewall tag from source binding
                    fw_tags = await self._get_bound_firewall_tags(bl_entry.source_tag or terminal.source_tag)
                else:
                    fw_tags = [fw_tag]

                for ft in fw_tags:
                    try:
                        success = await self._unblock_on_firewall(blocked_ip, ft)
                        if success:
                            successfully_unblocked.append(bl_entry)
                            logger.info(
                                f"Manual whitelist: unblocked {blocked_ip} on firewall '{ft}' "
                                f"for MAC {mac_norm}"
                            )
                        else:
                            unblock_errors.append(
                                f"Failed to unblock {blocked_ip} on firewall '{ft}'"
                            )
                    except Exception as e:
                        unblock_errors.append(
                            f"Error unblocking {blocked_ip} on firewall '{ft}': {str(e)}"
                        )

            # Update successfully unblocked entries
            now = now_utc()
            logger.info(
                f"Manual whitelist: Setting reason for {len(successfully_unblocked)} entries: "
                f"reason='加入白名单（手动）', username={username}, ip={ip_addr}, mac={mac_addr}"
            )
            for bl_entry in successfully_unblocked:
                bl_entry.auto_unblocked = True
                bl_entry.unblocked_at = now
                bl_entry.unblocked_by = username
                bl_entry.reason = "加入白名单（手动）"
                logger.debug(
                    f"Manual whitelist: Updated blacklist entry id={bl_entry.id}, ip={bl_entry.ip_address}, "
                    f"mac={bl_entry.mac_address}, reason='加入白名单（手动）'"
                )

            if successfully_unblocked:
                terminal.status = TerminalStatus.UNBLOCKED.value
                terminal.firewall_tag = None
                terminal.unblocked_at = now
                unblocked = True

            # Audit log
            await self.log_action(
                username, "manual_whitelist_unblock", "terminal", str(terminal.id),
                {
                    "message": f"Manual whitelist applied: {ip_addr}/{mac_addr} - "
                               f"unblocked on {len(successfully_unblocked)} firewall(s)",
                    "ip_address": ip_addr,
                    "mac_address": mac_addr,
                    "old_compliance": old_compliance,
                    "old_status": old_status,
                    "unblocked_entries": len(successfully_unblocked),
                    "errors": unblock_errors,
                }
            )

            if unblock_errors:
                logger.warning(
                    f"Manual whitelist unblock for {ip_addr}/{mac_addr} "
                    f"had {len(unblock_errors)} errors: {unblock_errors}"
                )

        return {
            "terminal_id": terminal.id,
            "ip_address": ip_addr,
            "mac_address": mac_addr,
            "old_compliance": old_compliance,
            "new_compliance": "bypass",
            "old_status": old_status,
            "new_status": terminal.status,
            "unblocked": unblocked,
        }

