import base64
import contextlib
import ipaddress
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blacklist import Blacklist
from app.models.data_source import DataSource
from app.models.log import AuditLog
from app.models.terminal import Terminal, TerminalStatus
from app.models.whitelist import Whitelist
from app.schemas.terminal import AuditLogQuery, BlacklistQuery, TerminalQuery, WhitelistQuery
from app.services.sangfor_service import SangforService


def _escape_like(value: str) -> str:
    """Escape LIKE wildcard characters (% and _) in search values to prevent wildcard injection."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _normalize_mac(mac: str) -> str:
    """Normalize MAC address by removing all separators and uppercasing"""
    return mac.replace(':', '').replace('-', '').replace('.', '').upper()


def _parse_date_range(start_date: str | None, end_date: str | None):
    """Parse date range strings into datetime objects for filtering"""
    conditions = []
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
            conditions.append(lambda col: col >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=UTC
            )
            conditions.append(lambda col: col <= end_dt)
        except ValueError:
            pass
    return conditions


def _parse_block_time(block_time: str) -> timedelta:
    """Parse block time string (e.g. '15d', '7d', '1h', '30m') into timedelta"""
    match = re.match(r'^(\d+)([dhm])$', block_time.lower())
    if not match:
        return timedelta(days=30)
    value = int(match.group(1))
    unit = match.group(2)
    if unit == 'd':
        return timedelta(days=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    return timedelta(days=30)


class IPAddressParser:
    """Utility class to parse and expand IP addresses, CIDR subnets, and IP ranges"""

    @staticmethod
    def parse_ip_input(ip_input: str) -> list[str]:
        """Parse IP input and return list of IP addresses"""
        ip_input = ip_input.strip()

        if '/' in ip_input:
            if '-' in ip_input:
                return IPAddressParser._parse_ip_range_with_subnet(ip_input)
            else:
                return IPAddressParser._parse_cidr(ip_input)
        elif '-' in ip_input:
            return IPAddressParser._parse_ip_range(ip_input)
        else:
            return [ip_input]

    @staticmethod
    def _parse_cidr(cidr: str) -> list[str]:
        """Parse CIDR notation and return list of IP addresses"""
        try:
            network = ipaddress.IPv4Network(cidr, strict=False)
            return [str(ip) for ip in network.hosts()]
        except ValueError:
            raise ValueError(f"Invalid CIDR notation: {cidr}")

    @staticmethod
    def _parse_ip_range(ip_range: str) -> list[str]:
        """Parse IP range like 192.168.1.1-100"""
        match = re.match(r'^(\d+\.\d+\.\d+)\.(\d+)-(\d+)$', ip_range)
        if not match:
            raise ValueError(f"Invalid IP range format: {ip_range}. Expected: 192.168.1.1-100")

        prefix = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))

        if start > end:
            raise ValueError(f"Invalid IP range: start ({start}) > end ({end})")
        if end > 255:
            raise ValueError(f"IP range end ({end}) exceeds 255")

        return [f"{prefix}.{i}" for i in range(start, end + 1)]

    @staticmethod
    def _parse_ip_range_with_subnet(ip_range: str) -> list[str]:
        """Parse IP range with subnet like 192.168.1.1-100/24"""
        subnet_match = re.match(r'^(.+)/(\d+)$', ip_range)
        if not subnet_match:
            raise ValueError(f"Invalid IP range with subnet: {ip_range}")

        range_part = subnet_match.group(1)
        subnet_bits = int(subnet_match.group(2))

        match = re.match(r'^(\d+\.\d+\.\d+)\.(\d+)-(\d+)$', range_part)
        if not match:
            raise ValueError(f"Invalid IP range format: {range_part}")

        prefix = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3))

        if start > end:
            raise ValueError(f"Invalid IP range: start ({start}) > end ({end})")
        if end > 255:
            raise ValueError(f"IP range end ({end}) exceeds 255")

        ip_addresses = [f"{prefix}.{i}" for i in range(start, end + 1)]

        try:
            network = ipaddress.IPv4Network(f"{prefix}.0/{subnet_bits}", strict=False)
            return [ip for ip in ip_addresses if ipaddress.IPv4Address(ip) in network]
        except ValueError:
            raise ValueError(f"Invalid subnet: /{subnet_bits}")

    @staticmethod
    def validate_ip(ip: str) -> bool:
        """Validate a single IP address"""
        try:
            ipaddress.IPv4Address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def detect_pattern_type(ip_input: str) -> str:
        """Detect the pattern type of an IP input string"""
        ip_input = ip_input.strip()
        if '/' in ip_input:
            return "cidr"
        elif '-' in ip_input:
            return "ip_range"
        else:
            return "single_ip"


class TerminalService:
    """Service for terminal management operations"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.sangfor = SangforService()

    # ------------------------------------------------------------------
    # Firewall helpers (multi-firewall support)
    # ------------------------------------------------------------------
    async def _get_sangfor_service_by_tag(self, firewall_tag: str) -> SangforService | None:
        """Get a SangforService instance configured from a DataSource entry"""
        stmt = select(DataSource).where(
            (DataSource.tag == firewall_tag) & (DataSource.type == "sangfor")
        )
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()

        if not source or not source.enabled:
            return None

        config = source.config
        if config:
            config = decrypt_config(config)
        return await SangforService.get_cached_service(
            base_url=config.get("base_url", ""),
            username=config.get("username", ""),
            password=config.get("password", ""),
            verify_ssl=config.get("verify_ssl", True),
            ca_bundle=config.get("ca_bundle", ""),
        )

    async def _get_all_sangfor_tags(self) -> list[str]:
        """Get all enabled Sangfor firewall tags"""
        stmt = select(DataSource.tag).where(
            (DataSource.type == "sangfor") & (DataSource.enabled == True)
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    async def get_stats(self) -> dict:
        """Get dashboard statistics with efficient database queries"""
        try:
            # Total terminals (ARP source only)
            total_result = await self.db.execute(
                select(func.count()).select_from(Terminal).where(Terminal.source == 'arp')
            )
            total = total_result.scalar() or 0

            # Count by compliance_status
            compliance_result = await self.db.execute(
                select(Terminal.compliance_status, func.count())
                .where(Terminal.source == 'arp')
                .group_by(Terminal.compliance_status)
            )
            compliance_counts = dict(compliance_result.all())

            # Count by status
            status_result = await self.db.execute(
                select(Terminal.status, func.count())
                .where(Terminal.source == 'arp')
                .group_by(Terminal.status)
            )
            status_counts = dict(status_result.all())

            # Whitelist count
            whitelist_result = await self.db.execute(select(func.count()).select_from(Whitelist))
            whitelisted = whitelist_result.scalar() or 0

            return {
                "total": total,
                "whitelisted": whitelisted,
                "blocked": status_counts.get(TerminalStatus.BLOCKED.value, 0),
                "unblocked": status_counts.get(TerminalStatus.UNBLOCKED.value, 0),
                "compliant": compliance_counts.get("compliant", 0),
                "bypass": compliance_counts.get("bypass", 0),
                "non_compliant": compliance_counts.get("non_compliant", 0),
                "unknown": compliance_counts.get("unknown", 0),
            }
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            raise

    async def get_system_status(self) -> dict:
        """Get system status including Sangfor AF and data source connectivity"""
        import asyncio

        from app.core.config import settings

        # Check Sangfor AF connectivity via DataSource table (with timeout)
        sangfor_status = {"connected": False, "error": None}
        try:
            from app.core.crypto import decrypt_config
            from app.models.data_source import DataSource

            stmt = select(DataSource).where(DataSource.type == "sangfor", DataSource.enabled == True)
            result = await self.db.execute(stmt)
            sangfor_sources = result.scalars().all()

            if sangfor_sources:
                for source in sangfor_sources:
                    try:
                        config = source.config
                        if config:
                            config = decrypt_config(config)
                        svc = SangforService(
                            base_url=config.get("base_url", ""),
                            username=config.get("username", ""),
                            password=config.get("password", ""),
                        )
                        # Add timeout to connection test (max 3 seconds)
                        try:
                            connected = await asyncio.wait_for(svc.test_connection(), timeout=3.0)
                            if connected:
                                sangfor_status = {"connected": True, "error": None}
                                await svc.close()
                                break
                            else:
                                sangfor_status["error"] = f"Connection test failed for '{source.tag}'"
                        except TimeoutError:
                            sangfor_status["error"] = f"Connection timeout for '{source.tag}'"
                            await svc.close()
                            continue
                        await svc.close()
                    except Exception as e:
                        sangfor_status["error"] = f"Sangfor '{source.tag}': {str(e)}"
            else:
                sangfor_status["error"] = "No Sangfor AF data source configured"
        except Exception as e:
            sangfor_status["error"] = str(e)

        # Check network scanner (ARP data source) status
        network_scanner_status = "pending"
        try:
            from app.models.data_source import DataSource as DS

            stmt = select(DS).where(
                DS.type.in_(["arp_ssh", "arp_api"]),
                DS.enabled == True,
            )
            result = await self.db.execute(stmt)
            arp_sources = result.scalars().all()

            if arp_sources:
                # If any ARP source has synced successfully, mark as connected
                any_synced = any(s.last_sync_status == "success" for s in arp_sources)
                if any_synced:
                    network_scanner_status = "connected"
                else:
                    network_scanner_status = "error"
            else:
                network_scanner_status = "pending"
        except Exception:
            pass

        import time

        from app.api.v1.endpoints.system import start_time

        uptime_seconds = max(0, time.time() - start_time)
        days = int(uptime_seconds // (24 * 3600))
        hours = int((uptime_seconds % (24 * 3600)) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        return {
            "backend_api": "connected",
            "database": "healthy",
            "sangfor": sangfor_status,
            "network_scanner": network_scanner_status,
            "uptime": uptime_str,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        }

    # ------------------------------------------------------------------
    # Terminals
    # ------------------------------------------------------------------
    async def get_invalid_macs(self, skip: int = 0, limit: int = 50) -> list[Terminal]:
        """Get unblocked MAC addresses with pagination"""
        try:
            stmt = (
                select(Terminal)
                .where(Terminal.status == TerminalStatus.UNBLOCKED.value)
                .order_by(desc(Terminal.timestamp))
                .offset(skip)
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Error getting invalid MACs: {str(e)}")
            raise

    async def search_macs(self, query: TerminalQuery) -> list[Terminal]:
        """Search MAC addresses by various criteria including date range"""
        try:
            conditions = []

            # IP and MAC use OR logic with fuzzy matching
            ip_mac_conditions = []
            if query.ip:
                ip_mac_conditions.append(Terminal.ip_address.ilike(f"%{_escape_like(query.ip)}%"))
            if query.mac:
                # Strip all separators for format-agnostic MAC matching
                mac_clean = _normalize_mac(query.mac)
                ip_mac_conditions.append(Terminal.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"))

            if ip_mac_conditions:
                conditions.append(or_(*ip_mac_conditions))

            if query.status:
                conditions.append(Terminal.status == query.status)

            if query.compliance_status:
                conditions.append(Terminal.compliance_status == query.compliance_status)

            if query.source_tag:
                conditions.append(Terminal.source_tag == query.source_tag)

            # Firewall tag filter via Blacklist subquery
            if query.firewall_tag:
                fw_subquery = (
                    select(Blacklist.ip_address)
                    .where(Blacklist.firewall_tag == query.firewall_tag)
                    .correlate(Terminal)
                )
                conditions.append(Terminal.ip_address.in_(fw_subquery))

            # Date range filtering
            date_conditions = _parse_date_range(query.start_date, query.end_date)
            for dc in date_conditions:
                conditions.append(dc(Terminal.timestamp))

            stmt = (
                select(Terminal)
                .where(and_(*conditions) if conditions else True)
                .order_by(desc(Terminal.timestamp))
                .offset(query.skip)
                .limit(query.limit)
            )

            result = await self.db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Error searching MACs: {str(e)}")
            raise

    async def search_macs_count(self, query: TerminalQuery) -> int:
        """Get total count of MAC addresses matching search criteria"""
        try:
            conditions = []

            # Same conditions as search_macs
            ip_mac_conditions = []
            if query.ip:
                ip_mac_conditions.append(Terminal.ip_address.ilike(f"%{_escape_like(query.ip)}%"))
            if query.mac:
                # Strip all separators for format-agnostic MAC matching
                mac_clean = _normalize_mac(query.mac)
                ip_mac_conditions.append(Terminal.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"))

            if ip_mac_conditions:
                conditions.append(or_(*ip_mac_conditions))

            if query.status:
                conditions.append(Terminal.status == query.status)

            if query.compliance_status:
                conditions.append(Terminal.compliance_status == query.compliance_status)

            if query.source_tag:
                conditions.append(Terminal.source_tag == query.source_tag)

            # Firewall tag filter via Blacklist subquery
            if query.firewall_tag:
                fw_subquery = (
                    select(Blacklist.ip_address)
                    .where(Blacklist.firewall_tag == query.firewall_tag)
                    .correlate(Terminal)
                )
                conditions.append(Terminal.ip_address.in_(fw_subquery))

            # Date range filtering
            date_conditions = _parse_date_range(query.start_date, query.end_date)
            for dc in date_conditions:
                conditions.append(dc(Terminal.timestamp))

            stmt = (
                select(func.count(Terminal.id))
                .where(and_(*conditions) if conditions else True)
            )

            result = await self.db.execute(stmt)
            return result.scalar() or 0

        except Exception as e:
            logger.error(f"Error counting MACs: {str(e)}")
            raise

# ------------------------------------------------------------------
    # Whitelist
    # ------------------------------------------------------------------
    async def get_whitelist(self, query: WhitelistQuery | None = None,
                            skip: int = 0, limit: int = 50) -> list[Whitelist]:
        """Get whitelist entries with optional search and date filtering"""
        conditions = []

        if query:
            # Search by MAC, IP pattern, or comments
            if query.search:
                # Format-agnostic MAC matching using normalized column
                mac_clean = _normalize_mac(query.search)
                conditions.append(
                    or_(
                        Whitelist.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"),
                        Whitelist.ip_pattern.ilike(f"%{_escape_like(query.search)}%"),
                        Whitelist.comments.ilike(f"%{_escape_like(query.search)}%"),
                    )
                )

            # Date range filtering
            date_conditions = _parse_date_range(query.start_date, query.end_date)
            for dc in date_conditions:
                conditions.append(dc(Whitelist.created_at))

            skip = query.skip
            limit = query.limit

        stmt = (
            select(Whitelist)
            .where(and_(*conditions) if conditions else True)
            .order_by(desc(Whitelist.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_whitelist_count(self, query: WhitelistQuery | None = None) -> int:
        """Get total count of whitelist entries matching search criteria"""
        conditions = []

        if query:
            # Search by MAC, IP pattern, or comments
            if query.search:
                mac_clean = _normalize_mac(query.search)
                conditions.append(
                    or_(
                        Whitelist.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"),
                        Whitelist.ip_pattern.ilike(f"%{_escape_like(query.search)}%"),
                        Whitelist.comments.ilike(f"%{_escape_like(query.search)}%"),
                    )
                )

            # Date range filtering
            date_conditions = _parse_date_range(query.start_date, query.end_date)
            for dc in date_conditions:
                conditions.append(dc(Whitelist.created_at))

        stmt = (
            select(func.count(Whitelist.id))
            .where(and_(*conditions) if conditions else True)
        )

        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def add_to_whitelist(self, mac_address: str = None, ip_address: str = None,
                                comments: str = "", username: str = "") -> dict:
        """Add to whitelist by MAC address, IP address, CIDR subnet, or IP range.

        Instead of expanding CIDR/IP ranges into multiple records,
        the original pattern is stored as ip_pattern with a pattern_type field.
        """
        try:
            normalized_mac = None

            if mac_address:
                normalized_mac = self._normalize_mac(mac_address)

            # Determine pattern type and store the original pattern
            ip_pattern = None
            pattern_type = "single_ip"

            if ip_address:
                ip_pattern = ip_address.strip()
                pattern_type = IPAddressParser.detect_pattern_type(ip_address)

            # MAC-only entry
            if normalized_mac and not ip_address:
                pattern_type = "mac_only"

            # Check for existing entry
            existing = None
            if normalized_mac and ip_pattern:
                stmt = select(Whitelist).where(
                    (Whitelist.mac_address == normalized_mac) &
                    (Whitelist.ip_pattern == ip_pattern)
                )
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()
            elif normalized_mac:
                stmt = select(Whitelist).where(
                    (Whitelist.mac_address == normalized_mac) &
                    (Whitelist.ip_pattern.is_(None))
                )
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()
            elif ip_pattern:
                stmt = select(Whitelist).where(
                    (Whitelist.ip_pattern == ip_pattern) &
                    (Whitelist.mac_address.is_(None))
                )
                result = await self.db.execute(stmt)
                existing = result.scalar_one_or_none()

            if existing:
                existing.comments = comments
                if normalized_mac:
                    existing.mac_address = normalized_mac
                    existing.mac_address_normalized = _normalize_mac(normalized_mac)
                if ip_pattern:
                    existing.ip_pattern = ip_pattern
                    existing.pattern_type = pattern_type
            else:
                whitelist_entry = Whitelist(
                    mac_address=normalized_mac,
                    mac_address_normalized=_normalize_mac(normalized_mac) if normalized_mac else None,
                    ip_pattern=ip_pattern,
                    pattern_type=pattern_type,
                    comments=comments,
                    added_by=username
                )
                self.db.add(whitelist_entry)

            # Invalidate whitelist cache and recalculate compliance for all terminals
            try:
                from app.services.compliance_service import ComplianceService
                compliance_svc = ComplianceService(self.db)
                await compliance_svc.invalidate_whitelist_cache()
                recalc_result = await compliance_svc.recalculate_all_compliance()
                logger.info(f"Whitelist add triggered compliance recalculation: {recalc_result}")
            except Exception as e:
                logger.warning(f"Failed to recalculate compliance after whitelist add: {e}")

            # Build log details
            if ip_address and mac_address:
                log_details = {"message": f"Added MAC {normalized_mac} and IP pattern {ip_pattern} ({pattern_type}) to whitelist",
                               "mac": normalized_mac, "ip_pattern": ip_pattern, "match_type": pattern_type}
                resource_id = normalized_mac
            elif ip_address:
                log_details = {"message": f"Added IP pattern {ip_pattern} ({pattern_type}) to whitelist",
                               "ip_pattern": ip_pattern, "match_type": pattern_type}
                resource_id = ip_pattern
            elif mac_address:
                log_details = {"message": f"Added MAC {normalized_mac} to whitelist",
                               "mac": normalized_mac}
                resource_id = normalized_mac
            else:
                log_details = {"message": "Added entry to whitelist"}
                resource_id = None
            await self.log_action(username, "add_whitelist", "whitelist", resource_id, log_details)

            await self.db.commit()

            return {
                "success": True,
                "added": 1,
                "skipped": 0,
                "errors": [],
                "message": f"Successfully added terminal to whitelist (pattern: {pattern_type})"
            }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding to whitelist: {str(e)}")
            raise

    async def delete_from_whitelist(self, identifier: str, username: str) -> bool:
        """Delete from whitelist by MAC address or IP pattern"""
        try:
            whitelist_entry = None

            cleaned_identifier = identifier.replace('-', '').replace(':', '').replace('.', '').upper()

            if '.' in identifier:
                stmt = select(Whitelist).where(Whitelist.ip_pattern == identifier)
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()
            elif len(cleaned_identifier) == 12 and cleaned_identifier.isalnum():
                normalized_mac = _normalize_mac(identifier)
                stmt = select(Whitelist).where(Whitelist.mac_address_normalized == normalized_mac)
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()
            else:
                stmt = select(Whitelist).where(Whitelist.ip_pattern == identifier)
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()

            if not whitelist_entry and '.' not in identifier and len(cleaned_identifier) == 12 and cleaned_identifier.isalnum():
                normalized_mac = _normalize_mac(identifier)
                stmt = select(Whitelist).where(
                    (Whitelist.mac_address_normalized == normalized_mac) &
                    (Whitelist.ip_pattern.is_not(None))
                )
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()

            if not whitelist_entry:
                stmt = select(Whitelist).where(
                    (Whitelist.ip_pattern == identifier) &
                    (Whitelist.mac_address_normalized.is_not(None))
                )
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()

            if whitelist_entry:
                mac_address = whitelist_entry.mac_address
                ip_pattern = whitelist_entry.ip_pattern

                await self.db.delete(whitelist_entry)

                try:
                    from app.services.compliance_service import ComplianceService
                    compliance_svc = ComplianceService(self.db)
                    await compliance_svc.invalidate_whitelist_cache()
                    recalc_result = await compliance_svc.recalculate_all_compliance()
                    logger.info(f"Whitelist delete triggered compliance recalculation: {recalc_result}")
                except Exception as e:
                    logger.warning(f"Failed to recalculate compliance after whitelist delete: {e}")

                log_details_parts = []
                if whitelist_entry.mac_address:
                    log_details_parts.append(f"MAC {whitelist_entry.mac_address}")
                if whitelist_entry.ip_pattern:
                    log_details_parts.append(f"IP {whitelist_entry.ip_pattern}")

                log_details = {"message": f"Removed {' and '.join(log_details_parts)} from whitelist"}
                if whitelist_entry.mac_address:
                    log_details["mac"] = whitelist_entry.mac_address
                if whitelist_entry.ip_pattern:
                    log_details["ip_pattern"] = whitelist_entry.ip_pattern

                resource_id = whitelist_entry.mac_address if whitelist_entry.mac_address else whitelist_entry.ip_pattern
                await self.log_action(username, "remove_whitelist", "whitelist", resource_id, log_details)

                await self.db.commit()
                return True

            return False

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting from whitelist: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Blacklist
    # ------------------------------------------------------------------
    async def get_blacklist(self, query: BlacklistQuery | None = None,
                            skip: int = 0, limit: int = 50) -> list[Blacklist]:
        """Get blacklist entries with optional search and date filtering.
        Default shows only active (not unblocked) records."""
        conditions = []

        # Status filtering: default to active only
        _active_filter = and_(
            Blacklist.auto_unblocked == False,
            Blacklist.unblocked_at.is_(None)
        )
        _unblocked_filter = or_(
            Blacklist.auto_unblocked == True,
            Blacklist.unblocked_at.is_not(None)
        )
        if query and query.status:
            if query.status == 'active':
                conditions.append(_active_filter)
            elif query.status == 'unblocked':
                conditions.append(_unblocked_filter)
            # 'all' or other values: no filter
        else:
            # Default: only show active (not unblocked) records
            conditions.append(_active_filter)

        if query:
            # Search by MAC or IP
            if query.search:
                # Format-agnostic MAC matching using normalized column
                mac_clean = _normalize_mac(query.search)
                conditions.append(
                    or_(
                        Blacklist.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"),
                        Blacklist.ip_address.ilike(f"%{_escape_like(query.search)}%"),
                    )
                )

            # Date range filtering
            date_conditions = _parse_date_range(query.start_date, query.end_date)
            for dc in date_conditions:
                conditions.append(dc(Blacklist.blocked_at))

            skip = query.skip
            limit = query.limit

        stmt = (
            select(Blacklist)
            .where(and_(*conditions) if conditions else True)
            .order_by(desc(Blacklist.blocked_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_blacklist_count(self, query: BlacklistQuery | None = None) -> int:
        """Get total count of blacklist entries matching search criteria.
        Default counts only active (not unblocked) records."""
        conditions = []

        # Status filtering: default to active only
        _active_filter = and_(
            Blacklist.auto_unblocked == False,
            Blacklist.unblocked_at.is_(None)
        )
        _unblocked_filter = or_(
            Blacklist.auto_unblocked == True,
            Blacklist.unblocked_at.is_not(None)
        )
        if query and query.status:
            if query.status == 'active':
                conditions.append(_active_filter)
            elif query.status == 'unblocked':
                conditions.append(_unblocked_filter)
        else:
            conditions.append(_active_filter)

        if query:
            # Search by MAC or IP
            if query.search:
                mac_clean = _normalize_mac(query.search)
                conditions.append(
                    or_(
                        Blacklist.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"),
                        Blacklist.ip_address.ilike(f"%{_escape_like(query.search)}%"),
                    )
                )

            # Date range filtering
            date_conditions = _parse_date_range(query.start_date, query.end_date)
            for dc in date_conditions:
                conditions.append(dc(Blacklist.blocked_at))

        stmt = (
            select(func.count(Blacklist.id))
            .where(and_(*conditions) if conditions else True)
        )

        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_blacklist_stats(self) -> dict:
        """Get global blacklist statistics based on active (not unblocked) records."""
        from sqlalchemy import case
        from datetime import datetime, UTC

        base_filter = and_(
            Blacklist.auto_unblocked == False,
            Blacklist.unblocked_at.is_(None)
        )

        stmt = select(
            func.count(Blacklist.id).label('total_active'),
            func.count(case((Blacklist.is_auto_blocked == True, 1))).label('auto_blocked'),
            func.count(case((Blacklist.is_auto_blocked == False, 1))).label('manual_blocked'),
            func.count(case(
                ((Blacklist.expires_at.is_not(None)) & (Blacklist.expires_at < datetime.now(UTC)), 1)
            )).label('expired'),
        ).where(base_filter)

        result = await self.db.execute(stmt)
        row = result.one()

        total_active = row.total_active or 0
        expired = row.expired or 0
        return {
            "total_active": total_active,
            "auto_blocked": row.auto_blocked or 0,
            "manual_blocked": row.manual_blocked or 0,
            "expired": expired,
            "active_blocks": total_active - expired,
        }

    async def check_blacklist(
        self,
        mac_addresses: list[str] | None = None,
        ip_addresses: list[str] | None = None,
    ) -> list[dict]:
        """Batch-check which MAC/IP addresses are currently active in the blacklist.

        Returns only matching entries with mac_address, ip_address, firewall_tag.
        Active = auto_unblocked == False AND (expires_at >= now OR expires_at IS NULL).
        Uses indexed IN() queries for O(1) DB round-trip regardless of input size.
        """
        now = datetime.now(UTC)

        # Normalize and deduplicate MACs (12-char uppercase for mac_address_normalized column)
        normalized_macs: set[str] = set()
        if mac_addresses:
            for mac in mac_addresses:
                if mac:
                    normalized = _normalize_mac(mac)
                    if normalized:
                        normalized_macs.add(normalized)

        # Deduplicate IPs
        unique_ips: set[str] = set()
        if ip_addresses:
            unique_ips = {ip for ip in ip_addresses if ip}

        # Build match conditions: mac IN (...) OR ip IN (...)
        match_conditions = []
        if normalized_macs:
            match_conditions.append(Blacklist.mac_address_normalized.in_(normalized_macs))
        if unique_ips:
            match_conditions.append(Blacklist.ip_address.in_(unique_ips))

        if not match_conditions:
            return []

        stmt = select(
            Blacklist.mac_address,
            Blacklist.ip_address,
            Blacklist.firewall_tag,
        ).where(
            and_(
                Blacklist.auto_unblocked == False,  # noqa: E712
                or_(
                    Blacklist.expires_at >= now,
                    Blacklist.expires_at.is_(None),
                ),
                or_(*match_conditions),
            )
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            {
                "mac_address": row[0],
                "ip_address": row[1],
                "firewall_tag": row[2],
            }
            for row in rows
        ]

    async def cleanup_expired_blacklist(self) -> int:
        """Remove expired blacklist entries and restore terminal status.
        Returns the number of entries cleaned up."""
        try:
            now = datetime.now(UTC)
            stmt = select(Blacklist).where(
                (Blacklist.expires_at < now) &
                (Blacklist.auto_unblocked == False)
            )
            result = await self.db.execute(stmt)
            expired_entries = result.scalars().all()

            if not expired_entries:
                return 0

            # --- Batch-load all data upfront to avoid N+1 queries ---

            # 1. Batch-load all affected Terminals (1 query instead of N)
            all_ips = list(set(e.ip_address for e in expired_entries if e.ip_address))
            terminal_map = {}  # (ip_address, mac_address) -> list of Terminal
            if all_ips:
                t_stmt = select(Terminal).where(Terminal.ip_address.in_(all_ips))
                t_result = await self.db.execute(t_stmt)
                for t in t_result.scalars().all():
                    key = (t.ip_address, t.mac_address)
                    if key not in terminal_map:
                        terminal_map[key] = []
                    terminal_map[key].append(t)

            # 2. Batch-check for active blocks per unique IP (1 query instead of N)
            active_block_ips = set()
            if all_ips:
                active_stmt = select(Blacklist.ip_address).where(
                    (Blacklist.ip_address.in_(all_ips)) &
                    (Blacklist.expires_at >= now) &
                    (Blacklist.auto_unblocked == False)
                )
                active_result = await self.db.execute(active_stmt)
                active_block_ips = set(row[0] for row in active_result.all())

            # 3. Pre-resolve SangforService instances by firewall_tag
            #    (1 query per unique tag instead of 1 query per entry)
            sangfor_cache = {}
            unique_fw_tags = set(e.firewall_tag for e in expired_entries if e.firewall_tag)
            for fw_tag in unique_fw_tags:
                sangfor_cache[fw_tag] = await self._get_sangfor_service_by_tag(fw_tag)

            # --- Process entries using pre-loaded data ---
            count = 0
            failed_unblock_ips = set()  # Track IPs where Sangfor unblock failed

            try:
                for entry in expired_entries:
                    # Check if IP has active blocks (using pre-loaded set)
                    if entry.ip_address and entry.ip_address in active_block_ips:
                        # IP still has active blocks — don't unblock on firewall,
                        # just mark the expired entry as unblocked
                        entry.unblocked_at = datetime.now(UTC)
                        entry.unblocked_by = "system"
                        count += 1
                        continue

                    # Restore terminal status and reset compliance for re-evaluation
                    # (using pre-loaded map instead of per-entry query)
                    if entry.ip_address:
                        key = (entry.ip_address, entry.mac_address)
                        mac_records = terminal_map.get(key, [])
                        for record in mac_records:
                            if record.status == "blocked":  # Only reset if still blocked
                                record.status = TerminalStatus.UNBLOCKED.value
                                # Reset compliance_status to "unknown" so the next
                                # scheduled compliance check will re-evaluate it.
                                record.compliance_status = "unknown"

                    # Try to unblock on Sangfor (using cached service)
                    fw_tag = entry.firewall_tag
                    svc = sangfor_cache.get(fw_tag) if fw_tag else None
                    sangfor_unblock_success = True  # Default to True; only False on explicit failure

                    if entry.ip_address and svc and svc.base_url:
                        try:
                            response = await svc.unblock_ip([{"srcIP": entry.ip_address}])
                            if response.get('code') != 0:
                                sangfor_unblock_success = False
                                logger.warning(
                                    f"Sangfor unblock failed for {entry.ip_address} on firewall '{fw_tag}': "
                                    f"{response.get('message')}. Keeping blacklist entry for consistency."
                                )
                                failed_unblock_ips.add(entry.ip_address)
                        except Exception as e:
                            sangfor_unblock_success = False
                            logger.warning(
                                f"Sangfor API error when unblocking {entry.ip_address} on firewall '{fw_tag}': {e}. "
                                f"Keeping blacklist entry for consistency."
                            )
                            failed_unblock_ips.add(entry.ip_address)
                    elif fw_tag and not svc:
                        # Firewall exists in tag but is disabled or missing — cannot safely unblock
                        sangfor_unblock_success = False
                        logger.warning(
                            f"Cannot unblock {entry.ip_address}: firewall '{fw_tag}' is disabled or missing. "
                            f"Keeping blacklist entry for consistency."
                        )
                        failed_unblock_ips.add(entry.ip_address)

                    if sangfor_unblock_success:
                        entry.unblocked_at = datetime.now(UTC)
                        entry.unblocked_by = "system"
                        count += 1
                    else:
                        # Sangfor unblock failed — do NOT delete the blacklist entry
                        # to maintain consistency between local DB and firewall.
                        # The entry will be retried on the next cleanup cycle.
                        # Extend expires_at slightly to avoid immediate retry loop.
                        entry.expires_at = now + timedelta(minutes=30)
                        count += 1  # Still count as processed
            finally:
                # Close all cached SangforService instances
                for svc in sangfor_cache.values():
                    if svc:
                        with contextlib.suppress(Exception):
                            await svc.close()

            if count > 0:
                await self.log_action("system", "cleanup_expired_blacklist", "blacklist", None,
                                      {"message": f"Cleaned up {count} expired blacklist entries",
                                       "failed_unblock_ips": list(failed_unblock_ips) if failed_unblock_ips else None,
                                       "count": count, "expired_count": len(expired_entries)})
                await self.db.commit()

                # Trigger compliance re-evaluation for affected terminals
                # so that non-compliant ones get re-blocked promptly
                try:
                    from app.services.compliance_service import ComplianceService
                    compliance_svc = ComplianceService(self.db)
                    await compliance_svc.recalculate_all_compliance()
                    logger.info("Post-cleanup compliance recalculation completed")
                except Exception as e:
                    logger.warning(f"Post-cleanup compliance recalculation failed: {e}")

            return count
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error cleaning up expired blacklist: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Audit Logs
    # ------------------------------------------------------------------
    @staticmethod
    def _encode_cursor(timestamp: datetime, record_id: int) -> str:
        """Encode a cursor from timestamp and id for keyset pagination"""
        payload = json.dumps({"ts": timestamp.isoformat(), "id": record_id})
        return base64.urlsafe_b64encode(payload.encode()).decode()

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, int]:
        """Decode a cursor back to timestamp and id"""
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload["ts"]), payload["id"]

    async def search_audit_logs(self, query: AuditLogQuery) -> tuple[list[AuditLog], str | None]:
        """Search audit logs by various criteria including date range and keyword.
        Returns (logs, next_cursor) where next_cursor is set if more results exist."""
        conditions = []

        if query.username:
            conditions.append(AuditLog.username == query.username)

        if query.action:
            conditions.append(AuditLog.action == query.action)

        # Keyword search across IP, username, action, and details
        if query.search:
            conditions.append(
                or_(
                    AuditLog.ip_address.ilike(f"%{_escape_like(query.search)}%"),
                    AuditLog.username.ilike(f"%{_escape_like(query.search)}%"),
                    AuditLog.action.ilike(f"%{_escape_like(query.search)}%"),
                    AuditLog.details.ilike(f"%{_escape_like(query.search)}%"),
                )
            )

        # Date range filtering
        date_conditions = _parse_date_range(query.start_date, query.end_date)
        for dc in date_conditions:
            conditions.append(dc(AuditLog.timestamp))

        # Keyset pagination: use cursor instead of offset when provided
        if query.cursor:
            try:
                cursor_ts, cursor_id = self._decode_cursor(query.cursor)
                # (timestamp, id) < (cursor_ts, cursor_id) for DESC order
                conditions.append(
                    or_(
                        AuditLog.timestamp < cursor_ts,
                        and_(AuditLog.timestamp == cursor_ts, AuditLog.id < cursor_id)
                    )
                )
            except Exception:
                logger.warning(f"Invalid cursor format: {query.cursor}, falling back to offset")

        where_clause = and_(*conditions) if conditions else True

        # Fetch limit+1 to determine if there's a next page
        stmt = (
            select(AuditLog)
            .where(where_clause)
            .order_by(desc(AuditLog.timestamp), desc(AuditLog.id))
            .limit(query.limit + 1)
        )

        # Fall back to offset if no cursor
        if not query.cursor:
            stmt = stmt.offset(query.skip)

        result = await self.db.execute(stmt)
        logs = result.scalars().all()

        # Determine next_cursor
        next_cursor = None
        if len(logs) > query.limit:
            logs = logs[:query.limit]  # Trim the extra record
            last = logs[-1]
            next_cursor = self._encode_cursor(last.timestamp, last.id)

        return logs, next_cursor

    async def search_audit_logs_count(self, query: AuditLogQuery) -> int:
        """Get total count of audit logs matching search criteria"""
        conditions = []

        if query.username:
            conditions.append(AuditLog.username == query.username)

        if query.action:
            conditions.append(AuditLog.action == query.action)

        # Keyword search across IP, username, action, and details
        if query.search:
            conditions.append(
                or_(
                    AuditLog.ip_address.ilike(f"%{_escape_like(query.search)}%"),
                    AuditLog.username.ilike(f"%{_escape_like(query.search)}%"),
                    AuditLog.action.ilike(f"%{_escape_like(query.search)}%"),
                    AuditLog.details.ilike(f"%{_escape_like(query.search)}%"),
                )
            )

        # Date range filtering
        date_conditions = _parse_date_range(query.start_date, query.end_date)
        for dc in date_conditions:
            conditions.append(dc(AuditLog.timestamp))

        stmt = (
            select(func.count(AuditLog.id))
            .where(and_(*conditions) if conditions else True)
        )

        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def log_action(self, username: str, action: str, resource_type: str,
                         resource_id: str, details: dict[str, Any],
                         ip_address: str = None, resource_name: str = None):
        """Log an audit action with JSON details"""
        audit_log = AuditLog(
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=json.dumps(details, ensure_ascii=False),
            ip_address=ip_address,
        )
        self.db.add(audit_log)

    @staticmethod
    def _normalize_mac(mac: str) -> str:
        """Normalize MAC address format to XX-XX-XX-XX-XX-XX"""
        mac_clean = mac.replace('-', '').replace(':', '').replace('.', '').upper()
        formatted = '-'.join(mac_clean[i:i+2] for i in range(0, len(mac_clean), 2))
        return formatted
