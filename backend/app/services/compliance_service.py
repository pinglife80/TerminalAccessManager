"""
Compliance Service

Core compliance checking logic:
- Check if IP+MAC is compliant against whitelist and IPGuard baseline
- Auto-block non-compliant terminals
- Auto-unblock terminals that have become compliant
- Redis caching for performance optimization
"""

import json
import ipaddress
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_, or_
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.terminal import Terminal
from app.models.whitelist import Whitelist
from app.models.blacklist import Blacklist
from app.models.data_source import DataSource, DataSourceBinding
from app.models.compliance_baseline import ComplianceBaseline
from app.schemas.data_source import (
    ComplianceCheckResult, AutoBlockResult, AutoUnblockResult,
)


# Redis cache key patterns and TTLs
IPGUARD_CACHE_PREFIX = "ipguard:"
IPGUARD_CACHE_TTL = 600  # 10 minutes
WHITELIST_CACHE_KEY = "whitelist:all"
WHITELIST_CACHE_TTL = 300  # 5 minutes


async def _get_redis():
    from app.core.security import get_redis_client
    return await get_redis_client()


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
        whitelist_match = await self._check_whitelist(ip_address, mac_address)
        if whitelist_match:
            whitelisted = True
            wl_match_type = whitelist_match
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

    async def batch_check_compliance(self, entries: List[dict]) -> ComplianceCheckResult:
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
            source_tag = entry.get("source_tag", "")

            # Check whitelist
            wl_match = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)

            # Check IPGuard
            ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

            if wl_match:
                entry["compliance_status"] = "bypass"
                entry["wl_match_type"] = wl_match  # "mac" or "ip" or "both"
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
            } if len(entries) <= 1000 else None,
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
        entries = []

        try:
            # Connect to IPGuard database and fetch data
            # IPGuard typically uses MySQL/MariaDB or SQL Server
            # We use asyncpg for PostgreSQL-compatible or raw connection
            import asyncpg

            host = config.get("host", "")
            port = config.get("port", 3306)
            username = config.get("username", "")
            password = config.get("password", "")
            database = config.get("database", "ipguard")

            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=username,
                password=password,
                database=database,
                timeout=30,
            )

            # Query IP+MAC mappings from IPGuard
            # The actual table/column names may vary by IPGuard version
            # This is a common schema for OCULAR3
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
            await redis.setex(
                cache_key,
                IPGUARD_CACHE_TTL,
                json.dumps(entries),
            )

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
        # First, get all currently blacklisted IPs for this source
        bl_stmt = select(Blacklist.ip_address).where(
            (Blacklist.source_tag == arp_source_tag) &
            (Blacklist.auto_unblocked == False)
        )
        bl_result = await self.db.execute(bl_stmt)
        blacklisted_ips = set(row[0] for row in bl_result.all())

        stmt = (
            select(Terminal)
            .where(
                (Terminal.source_tag == arp_source_tag) &
                (Terminal.compliance_status == "non_compliant") &
                (Terminal.status != "frozen")
            )
        )
        result = await self.db.execute(stmt)
        non_compliant_entries = result.scalars().all()

        # Filter out entries already in blacklist
        non_compliant_entries = [
            e for e in non_compliant_entries if e.ip_address not in blacklisted_ips
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

            # Block on each associated firewall
            all_success = True
            for fw_tag in firewall_tags:
                try:
                    success = await self._block_on_firewall(
                        entry.ip_address, fw_tag, block_time
                    )
                    if not success:
                        all_success = False
                        errors.append(
                            f"Failed to block {entry.ip_address} on firewall '{fw_tag}'"
                        )
                except Exception as e:
                    all_success = False
                    errors.append(
                        f"Error blocking {entry.ip_address} on firewall '{fw_tag}': {str(e)}"
                    )

            if all_success:
                # Update MAC status
                entry.status = "frozen"

                # Create a separate Blacklist record for each firewall
                import re
                from datetime import datetime, timedelta, timezone

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
                    blacklist_entry = Blacklist(
                        ip_address=entry.ip_address,
                        mac_address=entry.mac_address,
                        reason=f"Auto-blocked: non-compliant (source={arp_source_tag})",
                        blocked_by="system",
                        expires_at=datetime.now(timezone.utc) + td,
                        source_tag=arp_source_tag,
                        firewall_tag=fw_tag,
                        is_auto_blocked=True,
                        auto_unblocked=False,
                    )
                    self.db.add(blacklist_entry)

                blocked += 1

                details.append({
                    "ip_address": entry.ip_address,
                    "mac_address": entry.mac_address,
                    "action": "blocked",
                    "firewall_tags": firewall_tags,
                })
            else:
                skipped += 1

        if not dry_run and blocked > 0:
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

        1. Find Blacklist entries where is_auto_blocked=True and auto_unblocked=False
        2. Check if the IP+MAC is now compliant
        3. If compliant, call firewall API to unblock
        4. Mark auto_unblocked=True
        """
        stmt = (
            select(Blacklist)
            .where(
                (Blacklist.is_auto_blocked == True) &
                (Blacklist.auto_unblocked == False)
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

        unblocked = 0
        skipped = 0
        errors = []
        details = []

        for bl_entry in auto_blocked_entries:
            ip_addr = bl_entry.ip_address or ""
            mac_addr = bl_entry.mac_address or ""

            # Check if now compliant
            wl_match = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)
            ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

            if wl_match or ig_match:
                # Unblock on firewall
                fw_tag = bl_entry.firewall_tag
                if fw_tag:
                    try:
                        success = await self._unblock_on_firewall(ip_addr, fw_tag)
                        if not success:
                            errors.append(
                                f"Failed to unblock {ip_addr} on firewall '{fw_tag}'"
                            )
                            skipped += 1
                            continue
                    except Exception as e:
                        errors.append(
                            f"Error unblocking {ip_addr} on firewall '{fw_tag}': {str(e)}"
                        )
                        skipped += 1
                        continue

                # Mark as auto-unblocked
                bl_entry.auto_unblocked = True

                # Update MAC status
                if ip_addr:
                    mac_stmt = select(Terminal).where(Terminal.ip_address == ip_addr)
                    mac_result = await self.db.execute(mac_stmt)
                    mac_records = mac_result.scalars().all()
                    for record in mac_records:
                        record.status = "unfrozen"
                        record.compliance_status = "bypass" if wl_match else "compliant"
                        record.wl_match_type = wl_match if wl_match else None

                unblocked += 1
                details.append({
                    "ip_address": ip_addr,
                    "mac_address": mac_addr,
                    "action": "unblocked",
                    "reason": "now_compliant",
                })
            else:
                skipped += 1

        if unblocked > 0:
            await self.db.commit()

        return AutoUnblockResult(
            total_auto_blocked=len(auto_blocked_entries),
            unblocked=unblocked,
            skipped=skipped,
            errors=errors,
            details=details if len(details) <= 100 else None,
        )

    # ------------------------------------------------------------------
    # Whitelist Matching
    # ------------------------------------------------------------------
    async def _check_whitelist(self, ip_address: str, mac_address: str) -> Optional[str]:
        """Check if IP+MAC matches any whitelist entry. Returns match type or None."""
        whitelist_data = await self._load_whitelist_cache()
        return self._match_whitelist_in_memory(whitelist_data, ip_address, mac_address)

    def _match_whitelist_in_memory(
        self, whitelist_data: List[dict], ip_address: str, mac_address: str
    ) -> Optional[str]:
        """Match IP+MAC against in-memory whitelist data.
        Returns match type string ("mac", "ip", "both") or None if no match."""
        for entry in whitelist_data:
            # MAC-only whitelist entry: match by MAC only
            if entry.get("pattern_type") == "mac_only":
                if entry.get("mac_address") and entry["mac_address"].upper() == mac_address.upper().replace(":", "-"):
                    return "mac"
                continue

            # Check IP pattern match
            ip_match = False
            if entry.get("ip_pattern"):
                ip_match = self._ip_matches_pattern(ip_address, entry["ip_pattern"], entry.get("pattern_type", "single_ip"))

            # Check MAC match
            mac_match = False
            if entry.get("mac_address"):
                mac_match = entry["mac_address"].upper() == mac_address.upper().replace(":", "-")

            # If both IP and MAC are specified, both must match
            # If only IP is specified, IP must match
            # If only MAC is specified, MAC must match
            if entry.get("ip_pattern") and entry.get("mac_address"):
                if ip_match and mac_match:
                    return "both"
            elif entry.get("ip_pattern"):
                if ip_match:
                    return "ip"
            elif entry.get("mac_address"):
                if mac_match:
                    return "mac"

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
                # IP range format: 192.168.1.1-100
                return self._ip_in_range(ip_address, ip_pattern)
            else:
                return ip_address == ip_pattern
        except (ValueError, TypeError):
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
        self, ipguard_data: Dict[str, List[dict]], ip_address: str, mac_address: str
    ) -> bool:
        """Match IP+MAC against in-memory IPGuard data from all sources"""
        normalized_mac = mac_address.upper().replace(":", "-")

        for source_tag, entries in ipguard_data.items():
            for entry in entries:
                entry_mac = entry.get("mac_address", "").upper().replace(":", "-")
                if entry.get("ip_address") == ip_address and entry_mac == normalized_mac:
                    return True
        return False

    # ------------------------------------------------------------------
    # Cache Loading
    # ------------------------------------------------------------------
    async def _load_whitelist_cache(self) -> List[dict]:
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
            })

        # Cache to Redis
        try:
            redis = await _get_redis()
            await redis.setex(WHITELIST_CACHE_KEY, WHITELIST_CACHE_TTL, json.dumps(data))
        except Exception:
            pass

        return data

    async def _load_all_ipguard_cache(self) -> Dict[str, List[dict]]:
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

            # If still no data, use empty list
            if baseline.tag not in result_data:
                result_data[baseline.tag] = []

        return result_data

    # ------------------------------------------------------------------
    # Firewall Operations
    # ------------------------------------------------------------------
    async def _block_on_firewall(
        self, ip_address: str, firewall_tag: str, block_time: str = "30d"
    ) -> bool:
        """Block an IP on the specified firewall"""
        try:
            stmt = select(DataSource).where(
                (DataSource.tag == firewall_tag) & (DataSource.type == "sangfor")
            )
            result = await self.db.execute(stmt)
            fw_source = result.scalar_one_or_none()

            if not fw_source or not fw_source.enabled:
                logger.warning(f"Firewall '{firewall_tag}' not found or disabled")
                return False

            from app.services.sangfor_service import SangforService
            config = fw_source.config
            svc = SangforService(
                base_url=config.get("base_url", ""),
                username=config.get("username", ""),
                password=config.get("password", ""),
                verify_ssl=config.get("verify_ssl", True),
                ca_bundle=config.get("ca_bundle", ""),
            )

            response = await svc.block_ip([ip_address], block_time=block_time)
            await svc.close()

            return response.get("code") == 0
        except Exception as e:
            logger.error(f"Failed to block {ip_address} on firewall '{firewall_tag}': {str(e)}")
            return False

    async def _unblock_on_firewall(self, ip_address: str, firewall_tag: str) -> bool:
        """Unblock an IP on the specified firewall"""
        try:
            stmt = select(DataSource).where(
                (DataSource.tag == firewall_tag) & (DataSource.type == "sangfor")
            )
            result = await self.db.execute(stmt)
            fw_source = result.scalar_one_or_none()

            if not fw_source or not fw_source.enabled:
                logger.warning(f"Firewall '{firewall_tag}' not found or disabled")
                return False

            from app.services.sangfor_service import SangforService
            config = fw_source.config
            svc = SangforService(
                base_url=config.get("base_url", ""),
                username=config.get("username", ""),
                password=config.get("password", ""),
                verify_ssl=config.get("verify_ssl", True),
                ca_bundle=config.get("ca_bundle", ""),
            )

            response = await svc.unblock_ip([{"srcIP": ip_address}])
            await svc.close()

            return response.get("code") == 0
        except Exception as e:
            logger.error(f"Failed to unblock {ip_address} on firewall '{firewall_tag}': {str(e)}")
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
