import re
import json
import ipaddress
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from loguru import logger

from app.models.terminal import Terminal, TerminalStatus
from app.models.whitelist import Whitelist
from app.models.blacklist import Blacklist
from app.models.log import AuditLog
from app.models.data_source import DataSource
from app.schemas.terminal import TerminalQuery, WhitelistQuery, BlacklistQuery, AuditLogQuery
from app.services.sangfor_service import SangforService


def _parse_date_range(start_date: Optional[str], end_date: Optional[str]):
    """Parse date range strings into datetime objects for filtering"""
    conditions = []
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            conditions.append(lambda col: col >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
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
    def parse_ip_input(ip_input: str) -> List[str]:
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
    def _parse_cidr(cidr: str) -> List[str]:
        """Parse CIDR notation and return list of IP addresses"""
        try:
            network = ipaddress.IPv4Network(cidr, strict=False)
            return [str(ip) for ip in network.hosts()]
        except ValueError:
            raise ValueError(f"Invalid CIDR notation: {cidr}")

    @staticmethod
    def _parse_ip_range(ip_range: str) -> List[str]:
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
    def _parse_ip_range_with_subnet(ip_range: str) -> List[str]:
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
    async def _get_sangfor_service_by_tag(self, firewall_tag: str) -> Optional[SangforService]:
        """Get a SangforService instance configured from a DataSource entry"""
        stmt = select(DataSource).where(
            (DataSource.tag == firewall_tag) & (DataSource.type == "sangfor")
        )
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()

        if not source or not source.enabled:
            return None

        config = source.config
        return SangforService(
            base_url=config.get("base_url", ""),
            username=config.get("username", ""),
            password=config.get("password", ""),
            verify_ssl=config.get("verify_ssl", True),
            ca_bundle=config.get("ca_bundle", ""),
        )

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
                "blocked": status_counts.get(TerminalStatus.FROZEN.value, 0),
                "active": status_counts.get(TerminalStatus.ACTIVE.value, 0),
                "inactive": status_counts.get(TerminalStatus.INACTIVE.value, 0),
                "pending": status_counts.get(TerminalStatus.PENDING.value, 0),
                "compliant": compliance_counts.get("compliant", 0),
                "bypass": compliance_counts.get("bypass", 0),
                "non_compliant": compliance_counts.get("non_compliant", 0),
                "unknown": compliance_counts.get("unknown", 0),
            }
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            raise

    async def get_system_status(self) -> dict:
        """Get system status including Sangfor AF connectivity"""
        sangfor_status = {"connected": False, "cpu": None, "memory": None, "error": None}

        if self.sangfor.base_url:
            try:
                stats = await self.sangfor.get_system_stats()
                sangfor_status = {
                    "connected": True,
                    "cpu": stats.get("cpu"),
                    "memory": stats.get("memory"),
                    "error": None,
                }
            except Exception as e:
                sangfor_status["error"] = str(e)
            finally:
                await self.sangfor.close()
        else:
            sangfor_status["error"] = "Sangfor API not configured"

        return {
            "backend_api": "connected",
            "database": "connected",
            "sangfor": sangfor_status,
            "network_scanner": "pending",
        }

    # ------------------------------------------------------------------
    # Terminals
    # ------------------------------------------------------------------
    async def get_invalid_macs(self, skip: int = 0, limit: int = 50) -> List[Terminal]:
        """Get invalid (unfrozen) MAC addresses with pagination"""
        try:
            stmt = (
                select(Terminal)
                .where(Terminal.status == TerminalStatus.UNFROZEN.value)
                .order_by(desc(Terminal.timestamp))
                .offset(skip)
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            return result.scalars().all()

        except Exception as e:
            logger.error(f"Error getting invalid MACs: {str(e)}")
            raise

    async def search_macs(self, query: TerminalQuery) -> List[Terminal]:
        """Search MAC addresses by various criteria including date range"""
        try:
            conditions = []

            # IP and MAC use OR logic with fuzzy matching
            ip_mac_conditions = []
            if query.ip:
                ip_mac_conditions.append(Terminal.ip_address.ilike(f"%{query.ip}%"))
            if query.mac:
                # Strip all separators for format-agnostic MAC matching
                mac_clean = query.mac.replace('-', '').replace(':', '').replace('.', '').upper()
                # Use func.replace to strip separators from DB column too
                mac_col_stripped = func.replace(func.replace(func.replace(Terminal.mac_address, ':', ''), '-', ''), '.', '')
                ip_mac_conditions.append(mac_col_stripped.ilike(f"%{mac_clean}%"))

            if ip_mac_conditions:
                conditions.append(or_(*ip_mac_conditions))

            if query.status:
                conditions.append(Terminal.status == query.status)

            if query.compliance_status:
                conditions.append(Terminal.compliance_status == query.compliance_status)

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
                ip_mac_conditions.append(Terminal.ip_address.ilike(f"%{query.ip}%"))
            if query.mac:
                # Strip all separators for format-agnostic MAC matching
                mac_clean = query.mac.replace('-', '').replace(':', '').replace('.', '').upper()
                mac_col_stripped = func.replace(func.replace(func.replace(Terminal.mac_address, ':', ''), '-', ''), '.', '')
                ip_mac_conditions.append(mac_col_stripped.ilike(f"%{mac_clean}%"))

            if ip_mac_conditions:
                conditions.append(or_(*ip_mac_conditions))

            if query.status:
                conditions.append(Terminal.status == query.status)

            if query.compliance_status:
                conditions.append(Terminal.compliance_status == query.compliance_status)

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

    async def block_ip(self, ip_address: str, mac_address: str, username: str,
                        block_time: str = "30d", firewall_tag: Optional[str] = None) -> dict:
        """Block an IP address via Sangfor API and update database.

        Args:
            firewall_tag: If provided, use the specified firewall DataSource.
                         If None, fall back to global Sangfor config.
        """
        try:
            sangfor_svc = None
            if firewall_tag:
                sangfor_svc = await self._get_sangfor_service_by_tag(firewall_tag)

            # Call Sangfor API to block IP if configured
            sangfor_success = False
            svc = sangfor_svc or self.sangfor

            if svc and svc.base_url:
                try:
                    response = await svc.block_ip([ip_address], block_time=block_time)
                    sangfor_success = response.get('code') == 0
                    if not sangfor_success:
                        logger.warning(f"Sangfor block failed for {ip_address}: {response.get('message')}")
                except Exception as e:
                    logger.warning(f"Sangfor API error when blocking {ip_address}: {str(e)}")
                finally:
                    await svc.close()
            else:
                # Sangfor not configured, skip firewall operation
                sangfor_success = True

            if sangfor_success:
                # Update terminal status in database
                stmt = (
                    select(Terminal)
                    .where(Terminal.ip_address == ip_address)
                    .where(Terminal.mac_address == mac_address)
                )
                result = await self.db.execute(stmt)
                mac_record = result.scalar_one_or_none()

                if mac_record:
                    mac_record.status = TerminalStatus.FROZEN.value
                    mac_record.compliance_status = "non_compliant"

                # Add to blacklist with configurable expiration
                expires_at = datetime.now(timezone.utc) + _parse_block_time(block_time)
                blacklist_entry = Blacklist(
                    ip_address=ip_address,
                    mac_address=mac_address,
                    blocked_by=username,
                    expires_at=expires_at,
                    source_tag="manual",
                    firewall_tag=firewall_tag,
                    is_auto_blocked=False,
                    auto_unblocked=False,
                )
                self.db.add(blacklist_entry)

                # Log the action
                await self.log_action(username, "block_terminal", "mac", ip_address,
                                     {"message": f"Blocked IP {ip_address} (MAC: {mac_address}) for {block_time}",
                                      "ip": ip_address, "mac": mac_address, "duration": block_time})

                await self.db.commit()

                logger.info(f"Successfully blocked IP: {ip_address}")
                return {"success": True, "message": "IP blocked successfully"}
            else:
                error_msg = "Sangfor API block failed"
                logger.error(f"Sangfor API error: {error_msg}")
                return {"success": False, "message": f"Sangfor API error: {error_msg}"}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error blocking IP {ip_address}: {str(e)}")
            raise

    async def unblock_ip(self, ip_address: str, username: str,
                          firewall_tag: Optional[str] = None) -> dict:
        """Unblock an IP address via Sangfor API and update database.

        Args:
            firewall_tag: If provided, use the specified firewall DataSource.
                         If None, fall back to global Sangfor config.
        """
        try:
            sangfor_svc = None
            if firewall_tag:
                sangfor_svc = await self._get_sangfor_service_by_tag(firewall_tag)

            # Call Sangfor API to unblock IP if configured
            sangfor_success = False
            svc = sangfor_svc or self.sangfor

            if svc and svc.base_url:
                try:
                    response = await svc.unblock_ip([{"srcIP": ip_address}])
                    sangfor_success = response.get('code') == 0
                    if not sangfor_success:
                        logger.warning(f"Sangfor unblock failed for {ip_address}: {response.get('message')}")
                except Exception as e:
                    logger.warning(f"Sangfor API error when unblocking {ip_address}: {str(e)}")
                finally:
                    await svc.close()
            else:
                # Sangfor not configured, skip firewall operation
                sangfor_success = True

            if sangfor_success:
                # Update terminal status
                stmt = (
                    select(Terminal)
                    .where(Terminal.ip_address == ip_address)
                )
                result = await self.db.execute(stmt)
                mac_records = result.scalars().all()

                for record in mac_records:
                    record.status = TerminalStatus.UNFROZEN.value
                    record.compliance_status = "unknown"

                # Remove from blacklist (filter by firewall_tag if specified)
                stmt = select(Blacklist).where(Blacklist.ip_address == ip_address)
                if firewall_tag:
                    stmt = stmt.where(Blacklist.firewall_tag == firewall_tag)
                result = await self.db.execute(stmt)
                blacklist_entries = result.scalars().all()
                for entry in blacklist_entries:
                    await self.db.delete(entry)

                # Log the action
                await self.log_action(username, "unblock_terminal", "mac", ip_address,
                                     {"message": f"Unblocked IP {ip_address}",
                                      "ip": ip_address})

                await self.db.commit()

                logger.info(f"Successfully unblocked IP: {ip_address}")
                return {"success": True, "message": "IP unblocked successfully"}
            else:
                error_msg = "Sangfor API unblock failed"
                logger.error(f"Sangfor API error: {error_msg}")
                return {"success": False, "message": f"Sangfor API error: {error_msg}"}

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error unblocking IP {ip_address}: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Whitelist
    # ------------------------------------------------------------------
    async def get_whitelist(self, query: Optional[WhitelistQuery] = None,
                            skip: int = 0, limit: int = 50) -> List[Whitelist]:
        """Get whitelist entries with optional search and date filtering"""
        conditions = []

        if query:
            # Search by MAC, IP pattern, or comments
            if query.search:
                search_term = f"%{query.search}%"
                # Format-agnostic MAC matching: strip separators from both
                # the search term and the DB column before comparing
                mac_clean = query.search.replace('-', '').replace(':', '').replace('.', '').upper()
                mac_col_stripped = func.replace(func.replace(func.replace(Whitelist.mac_address, ':', ''), '-', ''), '.', '')
                conditions.append(
                    or_(
                        mac_col_stripped.ilike(f"%{mac_clean}%"),
                        Whitelist.ip_pattern.ilike(search_term),
                        Whitelist.comments.ilike(search_term),
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

    async def get_whitelist_count(self, query: Optional[WhitelistQuery] = None) -> int:
        """Get total count of whitelist entries matching search criteria"""
        conditions = []

        if query:
            # Search by MAC, IP pattern, or comments
            if query.search:
                search_term = f"%{query.search}%"
                mac_clean = query.search.replace('-', '').replace(':', '').replace('.', '').upper()
                mac_col_stripped = func.replace(func.replace(func.replace(Whitelist.mac_address, ':', ''), '-', ''), '.', '')
                conditions.append(
                    or_(
                        mac_col_stripped.ilike(f"%{mac_clean}%"),
                        Whitelist.ip_pattern.ilike(search_term),
                        Whitelist.comments.ilike(search_term),
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
                if ip_pattern:
                    existing.ip_pattern = ip_pattern
                    existing.pattern_type = pattern_type
            else:
                whitelist_entry = Whitelist(
                    mac_address=normalized_mac,
                    ip_pattern=ip_pattern,
                    pattern_type=pattern_type,
                    comments=comments,
                    added_by=username
                )
                self.db.add(whitelist_entry)

            # Remove terminal record from terminals when whitelisted
            if normalized_mac:
                stmt = select(Terminal).where(Terminal.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                mac_record = result.scalar_one_or_none()

                if mac_record:
                    await self.db.delete(mac_record)

            # Invalidate whitelist cache
            try:
                from app.services.compliance_service import ComplianceService
                compliance_svc = ComplianceService(self.db)
                await compliance_svc.invalidate_whitelist_cache()
            except Exception:
                pass

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

            if len(cleaned_identifier) == 12 and cleaned_identifier.isalnum():
                normalized_mac = self._normalize_mac(identifier)
                stmt = select(Whitelist).where(Whitelist.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()
            else:
                stmt = select(Whitelist).where(Whitelist.ip_pattern == identifier)
                result = await self.db.execute(stmt)
                whitelist_entry = result.scalar_one_or_none()

            if whitelist_entry:
                await self.db.delete(whitelist_entry)

                # Invalidate whitelist cache
                try:
                    from app.services.compliance_service import ComplianceService
                    compliance_svc = ComplianceService(self.db)
                    await compliance_svc.invalidate_whitelist_cache()
                except Exception:
                    pass

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
    async def get_blacklist(self, query: Optional[BlacklistQuery] = None,
                            skip: int = 0, limit: int = 50) -> List[Blacklist]:
        """Get blacklist entries with optional search and date filtering"""
        conditions = []

        if query:
            # Search by MAC or IP
            if query.search:
                search_term = f"%{query.search}%"
                # Format-agnostic MAC matching: strip separators from both
                # the search term and the DB column before comparing
                mac_clean = query.search.replace('-', '').replace(':', '').replace('.', '').upper()
                mac_col_stripped = func.replace(func.replace(func.replace(Blacklist.mac_address, ':', ''), '-', ''), '.', '')
                conditions.append(
                    or_(
                        mac_col_stripped.ilike(f"%{mac_clean}%"),
                        Blacklist.ip_address.ilike(search_term),
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

    async def get_blacklist_count(self, query: Optional[BlacklistQuery] = None) -> int:
        """Get total count of blacklist entries matching search criteria"""
        conditions = []

        if query:
            # Search by MAC or IP
            if query.search:
                search_term = f"%{query.search}%"
                mac_clean = query.search.replace('-', '').replace(':', '').replace('.', '').upper()
                mac_col_stripped = func.replace(func.replace(func.replace(Blacklist.mac_address, ':', ''), '-', ''), '.', '')
                conditions.append(
                    or_(
                        mac_col_stripped.ilike(f"%{mac_clean}%"),
                        Blacklist.ip_address.ilike(search_term),
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

    async def add_to_blacklist(self, ip_address: str = "", mac_address: str = None,
                                reason: str = "", username: str = "",
                                block_time: str = "30d",
                                firewall_tag: Optional[str] = None) -> dict:
        """Add to blacklist by IP address, MAC address, or both.
        Also calls Sangfor API to actually block the IP on the firewall.

        Args:
            firewall_tag: If provided, use the specified firewall DataSource.
        """
        try:
            normalized_mac = None
            if mac_address:
                normalized_mac = self._normalize_mac(mac_address)

            expires_at = datetime.now(timezone.utc) + _parse_block_time(block_time)

            # Call Sangfor API to block IP if available
            sangfor_success = False
            sangfor_svc = None
            if firewall_tag:
                sangfor_svc = await self._get_sangfor_service_by_tag(firewall_tag)

            svc = sangfor_svc or self.sangfor

            if ip_address and svc and svc.base_url:
                try:
                    response = await svc.block_ip([ip_address], block_time=block_time)
                    sangfor_success = response.get('code') == 0
                    if not sangfor_success:
                        logger.warning(f"Sangfor block failed for {ip_address}: {response.get('message')}")
                except Exception as e:
                    logger.warning(f"Sangfor API error when blocking {ip_address}: {str(e)}")
                finally:
                    await svc.close()

            # Update terminal status if exists
            if ip_address:
                stmt = select(Terminal).where(Terminal.ip_address == ip_address)
                result = await self.db.execute(stmt)
                mac_records = result.scalars().all()
                for record in mac_records:
                    record.status = TerminalStatus.FROZEN.value
                    record.compliance_status = "non_compliant"

            if normalized_mac:
                stmt = select(Terminal).where(Terminal.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                mac_record = result.scalar_one_or_none()
                if mac_record:
                    mac_record.status = TerminalStatus.FROZEN.value
                    mac_record.compliance_status = "non_compliant"

            # Add to blacklist
            blacklist_entry = Blacklist(
                ip_address=ip_address or None,
                mac_address=normalized_mac,
                reason=reason,
                expires_at=expires_at,
                blocked_by=username,
                source_tag="manual",
                firewall_tag=firewall_tag,
                is_auto_blocked=False,
                auto_unblocked=False,
            )
            self.db.add(blacklist_entry)

            log_details_parts = []
            if normalized_mac:
                log_details_parts.append(f"MAC {normalized_mac}")
            if ip_address:
                log_details_parts.append(f"IP {ip_address}")
            log_msg = f"Blocked {' and '.join(log_details_parts)}"
            if reason:
                log_msg += f" - {reason}"
            if not sangfor_success and ip_address and svc and svc.base_url:
                log_msg += " (Sangfor API block may have failed)"

            log_details = {"message": log_msg}
            if normalized_mac:
                log_details["mac"] = normalized_mac
            if ip_address:
                log_details["ip"] = ip_address
            if reason:
                log_details["reason"] = reason

            resource_id = normalized_mac if normalized_mac else ip_address
            await self.log_action(username, "block_blacklist", "blacklist", resource_id, log_details)

            await self.db.commit()

            return {
                "success": True,
                "message": "Successfully blocked terminal"
            }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding to blacklist: {str(e)}")
            raise

    async def delete_from_blacklist(self, identifier: str, username: str) -> bool:
        """Delete from blacklist by MAC address or IP address.
        Also calls Sangfor API to unblock the IP on the firewall."""
        try:
            blacklist_entry = None

            cleaned_identifier = identifier.replace('-', '').replace(':', '').replace('.', '').upper()

            if len(cleaned_identifier) == 12 and cleaned_identifier.isalnum():
                normalized_mac = self._normalize_mac(identifier)
                stmt = select(Blacklist).where(Blacklist.mac_address == normalized_mac)
                result = await self.db.execute(stmt)
                blacklist_entry = result.scalar_one_or_none()
            else:
                stmt = select(Blacklist).where(Blacklist.ip_address == identifier)
                result = await self.db.execute(stmt)
                blacklist_entry = result.scalar_one_or_none()

            if blacklist_entry:
                # Call Sangfor API to unblock IP if available
                fw_tag = blacklist_entry.firewall_tag
                sangfor_svc = None
                if fw_tag:
                    sangfor_svc = await self._get_sangfor_service_by_tag(fw_tag)

                svc = sangfor_svc or self.sangfor

                if blacklist_entry.ip_address and svc and svc.base_url:
                    try:
                        await svc.unblock_ip([{"srcIP": blacklist_entry.ip_address}])
                    except Exception as e:
                        logger.warning(f"Sangfor API error when unblocking {blacklist_entry.ip_address}: {str(e)}")
                    finally:
                        await svc.close()

                # Update terminal status back to unfrozen
                if blacklist_entry.ip_address:
                    stmt = select(Terminal).where(Terminal.ip_address == blacklist_entry.ip_address)
                    result = await self.db.execute(stmt)
                    mac_records = result.scalars().all()
                    for record in mac_records:
                        record.status = TerminalStatus.UNFROZEN.value
                        record.compliance_status = "unknown"

                if blacklist_entry.mac_address:
                    stmt = select(Terminal).where(Terminal.mac_address == blacklist_entry.mac_address)
                    result = await self.db.execute(stmt)
                    mac_record = result.scalar_one_or_none()
                    if mac_record:
                        mac_record.status = TerminalStatus.UNFROZEN.value
                        mac_record.compliance_status = "unknown"

                log_details_parts = []
                if blacklist_entry.mac_address:
                    log_details_parts.append(f"MAC {blacklist_entry.mac_address}")
                if blacklist_entry.ip_address:
                    log_details_parts.append(f"IP {blacklist_entry.ip_address}")

                log_details = {"message": f"Unblocked {' and '.join(log_details_parts)}"}
                if blacklist_entry.mac_address:
                    log_details["mac"] = blacklist_entry.mac_address
                if blacklist_entry.ip_address:
                    log_details["ip"] = blacklist_entry.ip_address

                resource_id = blacklist_entry.mac_address if blacklist_entry.mac_address else blacklist_entry.ip_address
                await self.log_action(username, "unblock_blacklist", "blacklist", resource_id, log_details)

                await self.db.delete(blacklist_entry)
                await self.db.commit()
                return True

            return False

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting from blacklist: {str(e)}")
            raise

    async def cleanup_expired_blacklist(self) -> int:
        """Remove expired blacklist entries and restore terminal status.
        Returns the number of entries cleaned up."""
        try:
            now = datetime.now(timezone.utc)
            stmt = select(Blacklist).where(Blacklist.expires_at < now)
            result = await self.db.execute(stmt)
            expired_entries = result.scalars().all()

            count = 0
            for entry in expired_entries:
                # Restore terminal status
                if entry.ip_address:
                    mac_stmt = select(Terminal).where(Terminal.ip_address == entry.ip_address)
                    mac_result = await self.db.execute(mac_stmt)
                    mac_records = mac_result.scalars().all()
                    for record in mac_records:
                        record.status = TerminalStatus.UNFROZEN.value

                # Try to unblock on Sangfor
                fw_tag = entry.firewall_tag
                sangfor_svc = None
                if fw_tag:
                    sangfor_svc = await self._get_sangfor_service_by_tag(fw_tag)

                svc = sangfor_svc or self.sangfor

                if entry.ip_address and svc and svc.base_url:
                    try:
                        await svc.unblock_ip([{"srcIP": entry.ip_address}])
                    except Exception:
                        pass
                    finally:
                        await svc.close()

                await self.db.delete(entry)
                count += 1

            if count > 0:
                await self.log_action("system", "cleanup_expired", "blacklist", None,
                                      {"message": f"Cleaned up {count} expired blacklist entries",
                                       "count": count})
                await self.db.commit()

            return count
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error cleaning up expired blacklist: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Audit Logs
    # ------------------------------------------------------------------
    async def search_audit_logs(self, query: AuditLogQuery) -> List[AuditLog]:
        """Search audit logs by various criteria including date range and keyword"""
        conditions = []

        if query.username:
            conditions.append(AuditLog.username == query.username)

        if query.action:
            conditions.append(AuditLog.action == query.action)

        # Keyword search across IP, username, and details
        if query.search:
            search_term = f"%{query.search}%"
            conditions.append(
                or_(
                    AuditLog.ip_address.ilike(search_term),
                    AuditLog.username.ilike(search_term),
                    AuditLog.details.ilike(search_term),
                )
            )

        # Date range filtering
        date_conditions = _parse_date_range(query.start_date, query.end_date)
        for dc in date_conditions:
            conditions.append(dc(AuditLog.timestamp))

        stmt = (
            select(AuditLog)
            .where(and_(*conditions) if conditions else True)
            .order_by(desc(AuditLog.timestamp))
            .offset(query.skip)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def search_audit_logs_count(self, query: AuditLogQuery) -> int:
        """Get total count of audit logs matching search criteria"""
        conditions = []

        if query.username:
            conditions.append(AuditLog.username == query.username)

        if query.action:
            conditions.append(AuditLog.action == query.action)

        # Keyword search across IP, username, and details
        if query.search:
            search_term = f"%{query.search}%"
            conditions.append(
                or_(
                    AuditLog.ip_address.ilike(search_term),
                    AuditLog.username.ilike(search_term),
                    AuditLog.details.ilike(search_term),
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
                         resource_id: str, details: Dict[str, Any],
                         ip_address: str = None):
        """Log an audit action with JSON details"""
        audit_log = AuditLog(
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
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
