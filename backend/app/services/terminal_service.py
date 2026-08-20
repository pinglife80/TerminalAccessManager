import base64
import contextlib
import ipaddress
import json
import os
import re
from datetime import datetime, timedelta, UTC
from typing import Any

import pytz

from loguru import logger
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blacklist import Blacklist
from app.models.data_source import DataSource
from app.models.log import AuditLog
from app.models.terminal import Terminal, TerminalStatus
from app.models.whitelist import Whitelist
from app.schemas.terminal import AuditLogQuery, BlacklistQuery, TerminalQuery, WhitelistQuery
from app.core.crypto import decrypt_config
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
    tz_name = os.environ.get("TZ", "Asia/Shanghai")
    tz = pytz.timezone(tz_name)
    
    if start_date:
        try:
            naive_start = datetime.strptime(start_date, "%Y-%m-%d")
            start_dt = tz.localize(naive_start)
            conditions.append(lambda col: col >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            naive_end = datetime.strptime(end_date, "%Y-%m-%d")
            end_dt = tz.localize(naive_end.replace(hour=23, minute=59, second=59))
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
            if ip_input.endswith("/32"):
                return "single_ip"
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

            # Whitelist count - count terminals with compliance_status='bypass' instead of Whitelist entries
            whitelisted = compliance_counts.get("bypass", 0)

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

            # Both MAC and IP entry
            if normalized_mac and ip_address:
                pattern_type = "both"

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
                old_mac = existing.mac_address
                old_ip_pattern = existing.ip_pattern
                old_comments = existing.comments
                
                existing.comments = comments
                if normalized_mac:
                    existing.mac_address = normalized_mac
                    existing.mac_address_normalized = _normalize_mac(normalized_mac)
                if ip_pattern:
                    existing.ip_pattern = ip_pattern
                    existing.pattern_type = pattern_type
                
                log_details = {
                    "message": f"Updated whitelist entry {old_mac or old_ip_pattern}",
                    "old_mac_address": old_mac,
                    "new_mac_address": normalized_mac,
                    "old_ip_pattern": old_ip_pattern,
                    "new_ip_pattern": ip_pattern,
                    "old_comments": old_comments,
                    "new_comments": comments,
                }
                resource_id = str(existing.id)
                await self.log_action(username, "whitelist_update", "whitelist", resource_id, log_details)
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
                
                log_details = {
                    "message": f"Created whitelist entry for {normalized_mac or ip_pattern}",
                    "mac_address": normalized_mac,
                    "ip_pattern": ip_pattern,
                    "pattern_type": pattern_type,
                    "comments": comments,
                }
                resource_id = normalized_mac or ip_pattern
                await self.log_action(username, "whitelist_create", "whitelist", resource_id, log_details)

            # Invalidate whitelist cache and recalculate compliance for all terminals
            try:
                from app.services.compliance_service import ComplianceService
                compliance_svc = ComplianceService(self.db)
                await compliance_svc.invalidate_whitelist_cache()
                recalc_result = await compliance_svc.recalculate_all_compliance()
                logger.info(f"Whitelist add triggered compliance recalculation: {recalc_result}")
            except Exception as e:
                logger.warning(f"Failed to recalculate compliance after whitelist add: {e}")

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
            cleaned_identifier = identifier.replace('-', '').replace(':', '').replace('.', '').upper()
            deleted_entries = []

            if '.' in identifier:
                base_ip = identifier.split('/')[0]
                stmt = select(Whitelist).where(
                    ((Whitelist.ip_pattern == identifier) |
                     (Whitelist.ip_pattern == base_ip) |
                     (Whitelist.ip_pattern == f"{base_ip}/32")) &
                    (Whitelist.pattern_type.in_(["single_ip", "cidr", "both", "ip_range"]))
                )
                result = await self.db.execute(stmt)
                entries = result.scalars().all()

                if entries:
                    for entry in entries:
                        deleted_entries.append(entry)
                        await self.db.delete(entry)
            elif len(cleaned_identifier) == 12 and cleaned_identifier.isalnum():
                normalized_mac = _normalize_mac(identifier)
                stmt = select(Whitelist).where(Whitelist.mac_address_normalized == normalized_mac)
                result = await self.db.execute(stmt)
                entries = result.scalars().all()

                if entries:
                    for entry in entries:
                        deleted_entries.append(entry)
                        await self.db.delete(entry)
            else:
                stmt = select(Whitelist).where(Whitelist.ip_pattern == identifier)
                result = await self.db.execute(stmt)
                entries = result.scalars().all()

                if entries:
                    for entry in entries:
                        deleted_entries.append(entry)
                        await self.db.delete(entry)

            if deleted_entries:
                try:
                    from app.services.compliance_service import ComplianceService
                    compliance_svc = ComplianceService(self.db)
                    await compliance_svc.invalidate_whitelist_cache()
                    recalc_result = await compliance_svc.recalculate_all_compliance()
                    logger.info(f"Whitelist delete triggered compliance recalculation: {recalc_result}")
                except Exception as e:
                    logger.warning(f"Failed to recalculate compliance after whitelist delete: {e}")

                for entry in deleted_entries:
                    log_details_parts = []
                    if entry.mac_address:
                        log_details_parts.append(f"MAC {entry.mac_address}")
                    if entry.ip_pattern:
                        log_details_parts.append(f"IP {entry.ip_pattern}")

                    log_details = {
                        "message": f"Deleted whitelist entry {entry.id}",
                        "deleted_mac_address": entry.mac_address,
                        "deleted_ip_pattern": entry.ip_pattern,
                        "deleted_pattern_type": entry.pattern_type,
                        "deleted_comments": entry.comments,
                    }

                    resource_id = str(entry.id)
                    await self.log_action(username, "whitelist_delete", "whitelist", resource_id, log_details)

                await self.db.commit()
                return True

            return False

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting from whitelist: {str(e)}")
            raise

    # ------------------------------------------------------------------
    # Whitelist Import
    # ------------------------------------------------------------------

    async def import_whitelist_csv(
        self,
        file_content: str,
        mode: str = "skip",
        validate_only: bool = False,
        username: str = "",
    ) -> dict:
        """Import whitelist entries from CSV content.

        Args:
            file_content: Raw CSV text content
            mode: 'skip' (skip duplicates) or 'overwrite' (update existing)
            validate_only: If True, only validate without writing to DB
            username: Operator username for audit logging

        Returns:
            dict with success_count, skipped_count, failed_count, errors, mode, total_processed
        """
        import csv
        import io

        from sqlalchemy.exc import IntegrityError

        result = {
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "errors": [],
            "mode": mode,
            "total_processed": 0,
        }

        if mode not in ("skip", "overwrite"):
            mode = "skip"
            result["mode"] = mode

        MAX_ROWS = 10000
        reader = csv.DictReader(io.StringIO(file_content))

        if not reader.fieldnames:
            result["errors"].append({
                "row": 0,
                "reason": "CSV file has no header row",
                "data": {},
            })
            return result

        row_num = 1
        processed = 0

        for row in reader:
            row_num += 1
            if processed >= MAX_ROWS:
                result["errors"].append({
                    "row": row_num,
                    "reason": f"Maximum import limit ({MAX_ROWS} rows) exceeded, remaining rows skipped",
                    "data": {},
                })
                result["failed_count"] += 1
                break

            raw_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}

            mac_raw = raw_row.get("mac address", raw_row.get("mac", "")).strip()
            ip_raw = raw_row.get("ip pattern", raw_row.get("ip", "")).strip()
            comments = raw_row.get("comments", "").strip()

            if not mac_raw and not ip_raw:
                result["failed_count"] += 1
                result["errors"].append({
                    "row": row_num,
                    "reason": "MAC Address and IP Pattern cannot both be empty",
                    "data": raw_row,
                })
                continue

            normalized_mac = None
            if mac_raw:
                normalized_mac = _normalize_mac(mac_raw)
                if not self._validate_mac_format(mac_raw):
                    result["failed_count"] += 1
                    result["errors"].append({
                        "row": row_num,
                        "reason": f"Invalid MAC address format: '{mac_raw}'",
                        "data": raw_row,
                    })
                    continue

            ip_pattern = None
            if ip_raw:
                ip_pattern = ip_raw
                if not self._validate_ip_pattern(ip_raw):
                    result["failed_count"] += 1
                    result["errors"].append({
                        "row": row_num,
                        "reason": f"Invalid IP pattern: '{ip_raw}'",
                        "data": raw_row,
                    })
                    continue

            if not comments:
                comments = "Imported from CSV"

            if validate_only:
                result["total_processed"] += 1
                result["success_count"] += 1
                processed += 1
                continue

            try:
                pattern_type = self._determine_pattern_type(normalized_mac, ip_pattern)

                existing = await self._find_existing_whitelist(normalized_mac, ip_pattern)

                if existing:
                    if mode == "skip":
                        result["skipped_count"] += 1
                        result["total_processed"] += 1
                        processed += 1
                        continue
                    elif mode == "overwrite":
                        async with self.db.begin_nested() as nested:
                            existing.comments = comments
                            await nested.commit()
                        result["success_count"] += 1
                        result["total_processed"] += 1
                        processed += 1
                        continue

                async with self.db.begin_nested() as nested:
                    entry = Whitelist(
                        mac_address=normalized_mac,
                        mac_address_normalized=_normalize_mac(normalized_mac) if normalized_mac else None,
                        ip_pattern=ip_pattern,
                        pattern_type=pattern_type,
                        comments=comments,
                        added_by=username or "import",
                    )
                    self.db.add(entry)
                    await nested.commit()

                result["success_count"] += 1
                result["total_processed"] += 1
                processed += 1

            except IntegrityError as e:
                result["failed_count"] += 1
                result["errors"].append({
                    "row": row_num,
                    "reason": f"Database constraint violation: {str(e)}",
                    "data": raw_row,
                })
            except Exception as e:
                result["failed_count"] += 1
                result["errors"].append({
                    "row": row_num,
                    "reason": str(e),
                    "data": raw_row,
                })

        if not validate_only and result["success_count"] > 0:
            try:
                from app.services.compliance_service import ComplianceService
                compliance_svc = ComplianceService(self.db)
                await compliance_svc.invalidate_whitelist_cache()
                await compliance_svc.recalculate_all_compliance()
            except Exception as e:
                logger.warning(f"Failed to recalculate compliance after import: {e}")

            log_details = {
                "message": f"Imported {result['success_count']} whitelist entries from CSV",
                "mode": mode,
                "success_count": result["success_count"],
                "skipped_count": result["skipped_count"],
                "failed_count": result["failed_count"],
                "total_processed": result["total_processed"],
            }
            await self.log_action(username, "whitelist_import", "whitelist", "bulk_import", log_details)

            await self.db.commit()

        return result

    async def import_whitelist_from_backup(
        self,
        file_bytes: bytes,
        ext: str,
        mode: str = "skip",
        validate_only: bool = False,
        username: str = "",
    ) -> dict:
        """Import whitelist entries from a backup file (ZIP or JSON format).

        Args:
            file_bytes: Raw file bytes
            ext: File extension ('.zip' or '.json')
            mode: 'skip' (skip duplicates) or 'overwrite' (update existing)
            validate_only: If True, only validate without writing to DB
            username: Operator username for audit logging

        Returns:
            dict with success_count, skipped_count, failed_count, errors, mode, total_processed
        """
        import tempfile
        import zipfile

        result = {
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "errors": [],
            "mode": mode,
            "total_processed": 0,
        }

        if mode not in ("skip", "overwrite"):
            mode = "skip"
            result["mode"] = mode

        whitelist_data = None

        if ext == ".json":
            try:
                text = file_bytes.decode("utf-8-sig")
                whitelist_data = json.loads(text)
            except json.JSONDecodeError as e:
                result["errors"].append({
                    "row": 0,
                    "reason": f"Invalid JSON format: {str(e)}",
                    "data": {},
                })
                result["failed_count"] = 1
                return result

        elif ext == ".zip":
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    import io as _io
                    zip_buffer = _io.BytesIO(file_bytes)
                    with zipfile.ZipFile(zip_buffer, "r") as zipf:
                        zipf.extractall(temp_dir)

                    whitelist_file = os.path.join(temp_dir, "whitelist", "whitelist.json")
                    if not os.path.exists(whitelist_file):
                        whitelist_file = os.path.join(temp_dir, "whitelist.json")

                    if not os.path.exists(whitelist_file):
                        result["errors"].append({
                            "row": 0,
                            "reason": "No whitelist.json found in backup ZIP file",
                            "data": {},
                        })
                        result["failed_count"] = 1
                        return result

                    with open(whitelist_file, "r", encoding="utf-8") as f:
                        whitelist_data = json.load(f)
            except zipfile.BadZipFile:
                result["errors"].append({
                    "row": 0,
                    "reason": "Invalid ZIP file format",
                    "data": {},
                })
                result["failed_count"] = 1
                return result
            except Exception as e:
                result["errors"].append({
                    "row": 0,
                    "reason": f"Failed to extract ZIP: {str(e)}",
                    "data": {},
                })
                result["failed_count"] = 1
                return result

        if not isinstance(whitelist_data, list):
            result["errors"].append({
                "row": 0,
                "reason": "Invalid whitelist data format: expected a JSON array",
                "data": {},
            })
            result["failed_count"] = 1
            return result

        MAX_ROWS = 10000
        row_num = 1

        for item in whitelist_data:
            row_num += 1
            if result.get("total_processed", 0) >= MAX_ROWS:
                result["errors"].append({
                    "row": row_num,
                    "reason": f"Maximum import limit ({MAX_ROWS} rows) exceeded",
                    "data": {},
                })
                result["failed_count"] += 1
                break

            raw_row = item if isinstance(item, dict) else {}

            mac_raw = (raw_row.get("mac_address", raw_row.get("mac", "")) or "").strip()
            ip_raw = (raw_row.get("ip_pattern", raw_row.get("ip", "")) or "").strip()
            comments = (raw_row.get("comments", "") or "").strip()

            if not mac_raw and not ip_raw:
                result["failed_count"] += 1
                result["errors"].append({
                    "row": row_num,
                    "reason": "MAC Address and IP Pattern cannot both be empty",
                    "data": raw_row,
                })
                continue

            normalized_mac = None
            if mac_raw:
                normalized_mac = _normalize_mac(mac_raw)
                if not self._validate_mac_format(mac_raw):
                    result["failed_count"] += 1
                    result["errors"].append({
                        "row": row_num,
                        "reason": f"Invalid MAC address format: '{mac_raw}'",
                        "data": raw_row,
                    })
                    continue

            ip_pattern = None
            if ip_raw:
                ip_pattern = ip_raw
                if not self._validate_ip_pattern(ip_raw):
                    result["failed_count"] += 1
                    result["errors"].append({
                        "row": row_num,
                        "reason": f"Invalid IP pattern: '{ip_raw}'",
                        "data": raw_row,
                    })
                    continue

            if not comments:
                comments = "Imported from backup"

            if validate_only:
                result["total_processed"] = result.get("total_processed", 0) + 1
                result["success_count"] = result.get("success_count", 0) + 1
                continue

            try:
                pattern_type = self._determine_pattern_type(normalized_mac, ip_pattern)

                existing = await self._find_existing_whitelist(normalized_mac, ip_pattern)

                if existing:
                    if mode == "skip":
                        result["skipped_count"] += 1
                        result["total_processed"] = result.get("total_processed", 0) + 1
                        continue
                    elif mode == "overwrite":
                        async with self.db.begin_nested() as nested:
                            existing.comments = comments
                            await nested.commit()
                        result["success_count"] += 1
                        result["total_processed"] = result.get("total_processed", 0) + 1
                        continue

                async with self.db.begin_nested() as nested:
                    entry = Whitelist(
                        mac_address=normalized_mac,
                        mac_address_normalized=_normalize_mac(normalized_mac) if normalized_mac else None,
                        ip_pattern=ip_pattern,
                        pattern_type=pattern_type,
                        comments=comments,
                        added_by=username or "import",
                    )
                    self.db.add(entry)
                    await nested.commit()

                result["success_count"] += 1
                result["total_processed"] = result.get("total_processed", 0) + 1

            except Exception as e:
                result["failed_count"] += 1
                result["errors"].append({
                    "row": row_num,
                    "reason": str(e),
                    "data": raw_row,
                })

        if not validate_only and result["success_count"] > 0:
            try:
                from app.services.compliance_service import ComplianceService
                compliance_svc = ComplianceService(self.db)
                await compliance_svc.invalidate_whitelist_cache()
                await compliance_svc.recalculate_all_compliance()
            except Exception as e:
                logger.warning(f"Failed to recalculate compliance after backup import: {e}")

            log_details = {
                "message": f"Imported {result['success_count']} whitelist entries from backup",
                "mode": mode,
                "success_count": result["success_count"],
                "skipped_count": result["skipped_count"],
                "failed_count": result["failed_count"],
                "total_processed": result["total_processed"],
            }
            await self.log_action(username, "whitelist_import", "whitelist", "bulk_import", log_details)

            await self.db.commit()

        return result

    def _validate_mac_format(self, mac: str) -> bool:
        """Validate MAC address format"""
        import re
        pattern = r'^([0-9A-Fa-f]{2}[:.-]){5}[0-9A-Fa-f]{2}$'
        return bool(re.match(pattern, mac))

    def _validate_ip_pattern(self, ip_str: str) -> bool:
        """Validate IP/CIDR/range pattern"""
        import ipaddress
        import re
        try:
            if '-' in ip_str:
                range_match = re.match(r'^(\d+\.\d+\.\d+)\.(\d+)-(\d+)$', ip_str)
                if range_match:
                    prefix = range_match.group(1)
                    start = int(range_match.group(2))
                    end = int(range_match.group(3))
                    if start > end:
                        return False
                    if end > 255:
                        return False
                    ipaddress.ip_address(f"{prefix}.{start}")
                    return True
                cidr_range_match = re.match(r'^(.+)/(\d+)$', ip_str)
                if cidr_range_match:
                    range_part = cidr_range_match.group(1)
                    subnet_bits = int(cidr_range_match.group(2))
                    if subnet_bits < 0 or subnet_bits > 32:
                        return False
                    inner_match = re.match(r'^(\d+\.\d+\.\d+)\.(\d+)-(\d+)$', range_part)
                    if inner_match:
                        prefix = inner_match.group(1)
                        start = int(inner_match.group(2))
                        end = int(inner_match.group(3))
                        if start > end or end > 255:
                            return False
                        ipaddress.ip_network(f"{prefix}.0/{subnet_bits}", strict=False)
                        return True
                    return False
                return False
            elif '/' in ip_str:
                ipaddress.ip_network(ip_str, strict=False)
                return True
            else:
                ipaddress.ip_address(ip_str)
                return True
        except (ValueError, TypeError):
            return False
        return False

    def _determine_pattern_type(self, normalized_mac: str | None, ip_pattern: str | None) -> str:
        """Determine pattern type from MAC and IP"""
        if normalized_mac and ip_pattern:
            return "both"
        elif normalized_mac:
            return "mac_only"
        elif ip_pattern:
            if '/' in ip_pattern:
                return "cidr"
            elif '-' in ip_pattern:
                return "ip_range"
            else:
                return "single_ip"
        return "mac_only"

    async def _find_existing_whitelist(
        self, normalized_mac: str | None, ip_pattern: str | None
    ) -> Whitelist | None:
        """Find an existing whitelist entry matching the given MAC and/or IP"""
        if normalized_mac and ip_pattern:
            stmt = select(Whitelist).where(
                (Whitelist.mac_address == normalized_mac) &
                (Whitelist.ip_pattern == ip_pattern)
            )
        elif normalized_mac:
            stmt = select(Whitelist).where(
                (Whitelist.mac_address == normalized_mac) &
                (Whitelist.ip_pattern.is_(None))
            )
        elif ip_pattern:
            stmt = select(Whitelist).where(
                (Whitelist.ip_pattern == ip_pattern) &
                (Whitelist.mac_address.is_(None))
            )
        else:
            return None

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Blacklist
    # ------------------------------------------------------------------
    async def get_blacklist(self, query: BlacklistQuery | None = None,
                            skip: int = 0, limit: int = 50) -> list[Blacklist]:
        """Get blacklist entries with optional search and date filtering.
        Default shows only active (not unblocked) records."""
        conditions = []

        from datetime import datetime, UTC

        # Status filtering: default to active only (not unblocked and not expired)
        _active_filter = and_(
            Blacklist.auto_unblocked == False,
            Blacklist.unblocked_at.is_(None),
            or_(
                Blacklist.expires_at >= datetime.now(UTC),
                Blacklist.expires_at.is_(None),
            )
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

        from datetime import datetime, UTC

        # Status filtering: default to active only (not unblocked and not expired)
        _active_filter = and_(
            Blacklist.auto_unblocked == False,
            Blacklist.unblocked_at.is_(None),
            or_(
                Blacklist.expires_at >= datetime.now(UTC),
                Blacklist.expires_at.is_(None),
            )
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
            Blacklist.unblocked_at.is_(None),
            or_(
                Blacklist.expires_at >= datetime.now(UTC),
                Blacklist.expires_at.is_(None),
            )
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

            # 1. Batch-load all affected Terminals by MAC (1 query instead of N)
            # MAC is the stable identifier (IP may change due to DHCP)
            all_mac_norms = list(set(e.mac_address_normalized for e in expired_entries if e.mac_address_normalized))
            terminal_by_mac = {}  # mac_norm -> Terminal
            if all_mac_norms:
                t_stmt = select(Terminal).where(Terminal.mac_address_normalized.in_(all_mac_norms))
                t_result = await self.db.execute(t_stmt)
                for t in t_result.scalars().all():
                    if t.mac_address_normalized:
                        terminal_by_mac[t.mac_address_normalized] = t

            # 2. Batch-check for active blocks per MAC (1 query instead of N)
            # A terminal should only be unblocked if it has NO active entries on ANY firewall
            active_block_macs = set()
            if all_mac_norms:
                active_stmt = select(Blacklist.mac_address_normalized).where(
                    (Blacklist.mac_address_normalized.in_(all_mac_norms)) &
                    (Blacklist.unblocked_at.is_(None)) &
                    (Blacklist.auto_unblocked == False) &
                    (or_(
                        Blacklist.expires_at >= now,
                        Blacklist.expires_at.is_(None),
                    ))
                )
                active_result = await self.db.execute(active_stmt)
                active_block_macs = set(row[0] for row in active_result.all() if row[0])

            # 3. Pre-resolve SangforService instances by firewall_tag
            #    (1 query per unique tag instead of 1 query per entry)
            sangfor_cache = {}
            unique_fw_tags = set(e.firewall_tag for e in expired_entries if e.firewall_tag)
            for fw_tag in unique_fw_tags:
                sangfor_cache[fw_tag] = await self._get_sangfor_service_by_tag(fw_tag)

            # --- Process entries using pre-loaded data ---
            count = 0
            failed_unblock_ips = set()  # Track IPs where Sangfor unblock failed
            processed_macs = set()  # Track which terminals we've already updated to avoid duplicate work

            try:
                for entry in expired_entries:
                    mac_norm = entry.mac_address_normalized

                    # Check if this MAC still has active blocks on ANY firewall (using pre-loaded set)
                    has_other_active = mac_norm in active_block_macs if mac_norm else False

                    if has_other_active:
                        # This MAC still has other active block entries — don't unblock on firewall,
                        # just mark this expired entry as unblocked
                        entry.unblocked_at = datetime.now(UTC)
                        entry.unblocked_by = "system"
                        count += 1
                        continue

                    # Restore terminal status if this was the last active block for this MAC
                    if mac_norm and mac_norm not in processed_macs:
                        terminal = terminal_by_mac.get(mac_norm)
                        if terminal and terminal.status == "blocked":
                            terminal.status = TerminalStatus.UNBLOCKED.value
                            # Reset compliance_status to "unknown" so the next
                            # scheduled compliance check will re-evaluate it.
                            terminal.compliance_status = "unknown"
                            terminal.firewall_tag = None
                        processed_macs.add(mac_norm)

                    # Try to unblock on Sangfor (using cached service)
                    fw_tag = entry.firewall_tag
                    svc = sangfor_cache.get(fw_tag) if fw_tag else None
                    sangfor_unblock_success = True  # Default to True; only False on explicit failure

                    if entry.ip_address and fw_tag and svc and svc.base_url:
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
                    elif not fw_tag:
                        # Orphaned entry without firewall_tag (migration 035 should have cleaned these)
                        logger.warning(f"Expired entry {entry.id} for IP {entry.ip_address} has no firewall_tag - marking unblocked anyway")

                    if sangfor_unblock_success:
                        entry.unblocked_at = datetime.now(UTC)
                        entry.unblocked_by = "system"
                        count += 1
                    else:
                        # Sangfor unblock failed — do NOT mark as unblocked
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
