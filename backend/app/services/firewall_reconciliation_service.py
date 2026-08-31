"""
Firewall Reconciliation Service

Service for reconciling firewall blocked IPs with database blacklist entries.
Ensures that the firewall state and database state remain synchronized.

Key principle: Firewall actual state is the authoritative source of truth for blocked status.
Reconciliation runs PER FIREWALL independently to avoid cross-firewall corruption:
- Adds missing Blacklist entries for IPs that are blocked on firewall but missing in DB (highest priority)
- Re-blocks IPs on firewall that exist in DB but are missing from firewall (DB says should be blocked)
- Never unblocks based solely on reconciliation mismatch
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Set

from loguru import logger
from sqlalchemy import select, or_, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_config
from app.models.blacklist import Blacklist
from app.models.data_source import DataSource
from app.models.terminal import Terminal, TerminalStatus
from app.services.sangfor_service import SangforService


class FirewallReconciliationService:
    """Service for reconciling firewall blocked IPs with database blacklist"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def reconcile(self) -> Dict[str, Any]:
        """
        Reconcile firewall status with database.
        Reconciliation runs PER FIREWALL independently to avoid cross-firewall corruption.

        Returns:
            Dict with reconciliation results:
                - firewall_ip_count: Total blocked IPs across all firewalls
                - db_entry_count: Total active blacklist entries in DB
                - missing_in_db: IPs blocked on firewall but missing DB entries
                - missing_in_firewall: IPs in DB but missing on firewall (re-blocked)
                - created_in_db: Number of entries created in DB
                - reblocked_on_firewall: Number of IPs re-blocked on firewall
                - firewall_errors: List of {tag, error} dicts for firewalls that failed to query
        """
        results = {
            "firewall_ip_count": 0,
            "db_entry_count": 0,
            "missing_in_db": [],
            "missing_in_firewall": [],
            "created_in_db": 0,
            "reblocked_on_firewall": 0,
            "firewall_errors": [],
            "errors": [],
        }

        try:
            # Get enabled firewalls
            stmt = select(DataSource).where(
                (DataSource.type == "sangfor") & (DataSource.enabled == True)
            )
            fw_result = await self.db.execute(stmt)
            firewalls = fw_result.scalars().all()

            if not firewalls:
                logger.info("No enabled firewalls found for reconciliation")
                await self._repair_stale_terminal_status()
                return results

            # Get all active DB entries grouped by firewall_tag
            db_entries_by_fw = await self._get_db_active_blacklist_by_firewall()
            total_db_entries = sum(len(entries) for entries in db_entries_by_fw.values())
            results["db_entry_count"] = total_db_entries

            all_fw_ips = set()
            total_created = 0
            total_reblocked = 0

            for fw in firewalls:
                fw_tag = fw.tag
                try:
                    config = fw.config
                    if config:
                        config = decrypt_config(config)

                    svc = await SangforService.get_cached_service(
                        base_url=config.get("base_url", ""),
                        username=config.get("username", ""),
                        password=config.get("password", ""),
                        verify_ssl=config.get("verify_ssl", True),
                        ca_bundle=config.get("ca_bundle", ""),
                    )

                    response = await svc.get_blocked_ips()
                    fw_ips = self._parse_blocked_ips(response)

                    # Safety: if API returns 0 IPs but we expect some, log warning and skip this firewall
                    # This prevents clearing database when firewall API is temporarily down
                    db_count_for_fw = len(db_entries_by_fw.get(fw_tag, set()))
                    if len(fw_ips) == 0 and db_count_for_fw > 0:
                        # Probe with a known DB IP to distinguish "list API anomaly"
                        # from "blacklist externally wiped / unknown state".
                        probe_ip = next(iter(db_entries_by_fw[fw_tag]))
                        probe_hit = False
                        try:
                            probe_hit = await svc._find_blacklist_entry(probe_ip) is not None
                        except Exception as probe_err:
                            logger.warning(
                                f"Probe query for '{fw_tag}' failed: {type(probe_err).__name__}: {probe_err}"
                            )
                        reason = None
                        if probe_hit:
                            reason = "返回0个封锁IP但数据库存在活跃条目，单点探测命中，疑似列表接口异常（已跳过对账以防数据丢失）"
                            logger.warning(
                                f"Firewall '{fw_tag}' returned 0 blocked IPs but database has {db_count_for_fw} "
                                f"active entries. Probe: '{probe_ip}' FOUND via single-query API, so the LIST "
                                f"API appears faulty. Skipping reconciliation for this firewall to prevent data loss."
                            )
                        else:
                            reason = "返回0个封锁IP但数据库存在活跃条目，单点探测未命中，无法区分外部清空与接口故障（已保守跳过对账以防数据丢失）"
                            logger.warning(
                                f"Firewall '{fw_tag}' returned 0 blocked IPs but database has {db_count_for_fw} "
                                f"active entries. Probe: '{probe_ip}' NOT found via single-query API either - "
                                f"cannot distinguish external wipe from API failure. Conservatively skipping "
                                f"reconciliation for this firewall to prevent data loss."
                            )
                        results["firewall_errors"].append({"tag": fw_tag, "error": reason})
                        continue

                    all_fw_ips.update(fw_ips)
                    results["firewall_ip_count"] += len(fw_ips)

                    db_ips_for_fw = db_entries_by_fw.get(fw_tag, set())

                    # IPs on firewall but NOT in DB for this firewall → create DB entries
                    missing_in_db = fw_ips - db_ips_for_fw
                    if missing_in_db:
                        logger.info(f"Firewall '{fw_tag}': {len(missing_in_db)} IPs blocked but missing in DB, creating entries")
                        created = await self._create_db_entries_for_firewall(fw_tag, missing_in_db)
                        total_created += created
                        results["missing_in_db"].extend([(fw_tag, ip) for ip in sorted(missing_in_db)])

                    # IPs in DB for this firewall but NOT on firewall → re-block on firewall
                    missing_in_fw = db_ips_for_fw - fw_ips
                    if missing_in_fw:
                        logger.info(f"Firewall '{fw_tag}': {len(missing_in_fw)} IPs in DB but not blocked on firewall, re-blocking")
                        reblocked = await self._reblock_on_firewall(fw_tag, svc, missing_in_fw)
                        total_reblocked += reblocked
                        results["missing_in_firewall"].extend([(fw_tag, ip) for ip in sorted(missing_in_fw)])

                    if not missing_in_db and not missing_in_fw:
                        logger.info(f"Firewall '{fw_tag}': fully synchronized ({len(fw_ips)} IPs)")

                except Exception as e:
                    logger.error(f"Failed to reconcile firewall '{fw_tag}': {str(e)}")
                    results["firewall_errors"].append({"tag": fw_tag, "error": str(e)})
                    results["errors"].append(f"{fw_tag}: {str(e)}")

            results["created_in_db"] = total_created
            results["reblocked_on_firewall"] = total_reblocked

            if total_created > 0 or total_reblocked > 0:
                await self.db.commit()
                logger.info(f"Reconciliation complete: created {total_created} DB entries, re-blocked {total_reblocked} IPs on firewalls")
            else:
                logger.info("Reconciliation complete: firewall and database are in sync")

        except Exception as e:
            logger.error(f"Firewall reconciliation failed: {str(e)}")
            results["errors"].append(str(e))

        # Self-heal orphaned 'blocked' terminals (status='blocked' but no active
        # blacklist backing), regardless of whether any firewall query failed above.
        try:
            await self._repair_stale_terminal_status()
        except Exception as heal_err:
            logger.error(f"Failed to self-heal stale terminal status: {heal_err}")

        return results

    async def _repair_stale_terminal_status(self) -> int:
        """Reset terminals whose status='blocked' but have no active blacklist backing.

        Only fixes the Terminal.status drift vs active blacklist (the single source
        of truth for "blocked"). Does NOT modify compliance_status - that is owned
        solely by the compliance calculation logic (three-layer anti-oscillation).

        Matching: primary by normalized MAC; fallback to IP for NULL-MAC
        reconciliation-created entries (avoid wrongly resetting genuinely-blocked
        terminals whose blacklist entry has no MAC).
        """
        _now = datetime.now(UTC)
        active_bl = (
            select(Blacklist.id).where(
                (Blacklist.auto_unblocked == False) &
                (Blacklist.unblocked_at.is_(None)) &
                or_(
                    Blacklist.expires_at >= _now,
                    Blacklist.expires_at.is_(None),
                ) &
                or_(
                    and_(
                        Blacklist.mac_address_normalized.is_not(None),
                        Blacklist.mac_address_normalized == Terminal.mac_address_normalized,
                    ),
                    and_(
                        Blacklist.mac_address_normalized.is_(None),
                        Blacklist.ip_address == Terminal.ip_address,
                    ),
                )
            )
        )
        stmt = select(Terminal).where(
            (Terminal.status == TerminalStatus.BLOCKED.value) &
            (~exists(active_bl))
        )
        result = await self.db.execute(stmt)
        terminals = result.scalars().all()
        fixed = 0
        for t in terminals:
            t.status = TerminalStatus.UNBLOCKED.value
            t.firewall_tag = None
            if t.compliance_status == "non_compliant":
                # Lost its blacklist backing but still non_compliant: mark as
                # block_failed so retry-block can re-block it (not a permanent backlog).
                t.block_state = "block_failed"
            else:
                t.block_state = None
            fixed += 1
        if fixed:
            await self.db.commit()
            logger.info(f"Self-healed {fixed} orphaned 'blocked' terminals (no active blacklist backing)")
        return fixed

    def _parse_blocked_ips(self, response: Any) -> Set[str]:
        """Parse blocked IPs from Sangfor API response"""
        ips = set()
        if not response or not isinstance(response, dict):
            return ips

        data = response.get("data", {})
        if not isinstance(data, dict):
            return ips

        items = data.get("items", [])
        if not isinstance(items, list):
            return ips

        for item in items:
            if isinstance(item, dict):
                ip = item.get("url") or item.get("srcIP") or item.get("ip")
                if ip:
                    ips.add(ip)
        return ips

    async def _get_db_active_blacklist_by_firewall(self) -> Dict[str, Set[str]]:
        """
        Get all active blacklist entries grouped by firewall_tag.
        Returns: {fw_tag: set of ip_address}
        """
        from datetime import datetime, UTC

        stmt = select(
            Blacklist.ip_address,
            Blacklist.mac_address,
            Blacklist.mac_address_normalized,
            Blacklist.firewall_tag,
        ).where(
            (Blacklist.unblocked_at.is_(None)) &
            (Blacklist.auto_unblocked == False) &
            (Blacklist.firewall_tag.isnot(None)) &
            (or_(
                Blacklist.expires_at >= datetime.now(UTC),
                Blacklist.expires_at.is_(None),
            ))
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        by_fw: Dict[str, Set[str]] = {}
        for ip, mac, mac_norm, fw_tag in rows:
            if fw_tag not in by_fw:
                by_fw[fw_tag] = set()
            # Store IP for set comparison
            by_fw[fw_tag].add(ip)
        return by_fw

    async def _create_db_entries_for_firewall(self, fw_tag: str, ip_addresses: Set[str]) -> int:
        """
        Create blacklist entries for IPs found blocked on a specific firewall
        but missing from the database for that firewall.
        Attempts to find MAC address via current Terminal records.

        Safety: Skips whitelisted (bypass) terminals to prevent oscillation.
        If a whitelisted terminal is found blocked on firewall, log warning but do NOT
        create Blacklist entry - let compliance recalculation with cooldown handle unblock safely.
        """
        created = 0

        # Default block duration for reconciliation-created entries (follows system config)
        from app.services.config_service import ConfigService
        from app.services.terminal_service import _parse_block_time
        block_delta = _parse_block_time(await ConfigService(self.db).get("block_time") or "30d")

        # Load whitelist for safety check
        from app.services.compliance_service import ComplianceService
        _svc = ComplianceService(self.db)
        whitelist_data = await _svc._load_whitelist_cache()

        for ip_address in ip_addresses:
            try:
                # Find terminal by IP address (best effort - prefer most recently updated).
                # An IP may be shared by multiple terminals (DHCP reuse), so use first()
                # instead of scalar_one_or_none() which raises MultipleResultsFound.
                term_stmt = select(Terminal).where(
                    Terminal.ip_address == ip_address
                ).order_by(Terminal.timestamp.desc()).limit(1)
                term_result = await self.db.execute(term_stmt)
                terminal = term_result.scalars().first()

                mac_address = None
                mac_norm = None
                source_tag = None

                if terminal:
                    mac_address = terminal.mac_address
                    mac_norm = terminal.mac_address_normalized
                    source_tag = terminal.source_tag

                    # Update terminal firewall status to reflect actual firewall state
                    # IMPORTANT: ONLY update 'status' field (firewall actual state),
                    # NEVER modify 'compliance_status' here - that is solely the
                    # responsibility of compliance recalculation logic with anti-oscillation.
                    if terminal.status != TerminalStatus.BLOCKED.value:
                        terminal.status = TerminalStatus.BLOCKED.value

                    # Safety check: if terminal is whitelisted (bypass), do NOT create Blacklist entry.
                    # This prevents oscillation when a whitelisted terminal is erroneously blocked.
                    # Compliance recalculation with cooldown will handle unblock safely.
                    wl_match = _svc._match_whitelist_in_memory(
                        whitelist_data, ip_address, mac_address or ""
                    )
                    if wl_match and terminal.compliance_status == "bypass":
                        logger.warning(
                            f"Reconciliation: IP {ip_address} blocked on firewall '{fw_tag}' "
                            f"but terminal is whitelisted (bypass). Skipping Blacklist creation "
                            f"to prevent oscillation - will be unblocked by compliance recalculation."
                        )
                        continue
                else:
                    logger.warning(
                        f"Reconciliation: IP {ip_address} blocked on firewall '{fw_tag}' "
                        f"but no terminal record found - creating blacklist entry without MAC"
                    )

                # Check for existing entry
                existing_stmt = select(Blacklist).where(
                    (Blacklist.ip_address == ip_address) &
                    (Blacklist.firewall_tag == fw_tag) &
                    (Blacklist.unblocked_at.is_(None)) &
                    (Blacklist.auto_unblocked == False)
                )
                existing_result = await self.db.execute(existing_stmt)
                existing_bl = existing_result.scalar_one_or_none()

                if existing_bl:
                    # Already exists (maybe added during reconciliation by another path)
                    continue

                bl_entry = Blacklist(
                    ip_address=ip_address,
                    mac_address=mac_address,
                    mac_address_normalized=mac_norm,
                    blocked_by="system",
                    blocked_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + block_delta,
                    source_tag=source_tag or "reconciliation",
                    firewall_tag=fw_tag,
                    is_auto_blocked=True,
                    auto_unblocked=False,
                    reason=f"Reconciliation: IP blocked on firewall '{fw_tag}' but missing in DB",
                    last_operation_type="block",
                    last_operation_status="success",
                    last_operation_at=datetime.now(UTC),
                )
                self.db.add(bl_entry)
                await self.db.flush()
                created += 1

            except Exception as e:
                logger.error(f"Failed to create DB entry for {ip_address} on firewall '{fw_tag}': {str(e)}")

        return created

    async def _reblock_on_firewall(
        self, fw_tag: str, svc: SangforService, ip_addresses: Set[str]
    ) -> int:
        """
        Re-block IPs on a firewall that are marked as blocked in active DB entries
        but are currently missing from the firewall's blocklist.
        This handles cases where firewall may have lost blocks due to restart or policy sync.
        """
        reblocked = 0

        for ip_address in ip_addresses:
            try:
                # Find the blacklist entry to get reason.
                # An IP may have multiple active entries with different MACs
                # (DHCP IP reuse across terminals), so use first() instead of
                # scalar_one_or_none() which raises MultipleResultsFound.
                bl_stmt = select(Blacklist).where(
                    (Blacklist.ip_address == ip_address) &
                    (Blacklist.firewall_tag == fw_tag) &
                    (Blacklist.unblocked_at.is_(None)) &
                    (Blacklist.auto_unblocked == False)
                ).limit(1)
                bl_result = await self.db.execute(bl_stmt)
                bl_entry = bl_result.scalars().first()

                reason = "Reconciliation: re-block (DB says should be blocked)"
                if bl_entry and bl_entry.reason:
                    reason = bl_entry.reason

                result = await svc.block_ip(
                    [ip_address],
                    source_tag=fw_tag,
                    reason=reason
                )

                if result.get("code") == 0:
                    reblocked += 1
                    logger.info(f"Re-blocked {ip_address} on firewall '{fw_tag}' during reconciliation")
                else:
                    error_msg = result.get("message", "unknown error")
                    logger.warning(f"Failed to re-block {ip_address} on firewall '{fw_tag}': {error_msg}")

            except Exception as e:
                logger.error(f"Error re-blocking {ip_address} on firewall '{fw_tag}': {str(e)}")

        return reblocked
