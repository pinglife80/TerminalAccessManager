"""
Firewall Reconciliation Service

Service for reconciling firewall blocked IPs with database blacklist entries.
Ensures that the firewall state and database state remain synchronized.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Set, Tuple

from loguru import logger
from sqlalchemy import select, delete, or_
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
        
        Returns:
            Dict with reconciliation results:
                - firewall_ip_count: Number of blocked IPs on firewall
                - db_entry_count: Number of active blacklist entries in DB
                - missing_in_db: IPs on firewall but not in DB
                - missing_in_firewall: IPs in DB but not on firewall
                - created_in_db: Number of entries created in DB
                - marked_unblocked: Number of entries marked as unblocked
                - unblocked_on_firewall: Number of IPs unblocked on firewall
        """
        results = {
            "firewall_ip_count": 0,
            "db_entry_count": 0,
            "missing_in_db": [],
            "missing_in_firewall": [],
            "created_in_db": 0,
            "marked_unblocked": 0,
            "unblocked_on_firewall": 0,
            "errors": [],
        }

        try:
            firewall_ips = await self._get_firewall_blocked_ips()
            db_entries = await self._get_db_active_blacklist()

            results["firewall_ip_count"] = len(firewall_ips)
            results["db_entry_count"] = len(db_entries)

            firewall_ip_set = set(firewall_ips)
            db_ip_set = set(e[0] for e in db_entries)

            missing_in_db = sorted(firewall_ip_set - db_ip_set)
            missing_in_firewall = sorted(db_ip_set - firewall_ip_set)

            results["missing_in_db"] = missing_in_db
            results["missing_in_firewall"] = missing_in_firewall

            if missing_in_db:
                logger.warning(f"Found {len(missing_in_db)} IPs blocked on firewall but not in database")
                created = await self._create_db_entries(missing_in_db)
                results["created_in_db"] = created

            if missing_in_firewall:
                logger.warning(f"Found {len(missing_in_firewall)} IPs in database but not blocked on firewall")
                
                if len(firewall_ips) == 0 and len(db_entries) > 0:
                    logger.warning("Firewall returned 0 blocked IPs but database has active entries - this may indicate API failure. Skipping database updates to prevent data loss.")
                else:
                    unblocked, marked = await self._unblock_from_firewall(missing_in_firewall)
                    results["unblocked_on_firewall"] = unblocked
                    results["marked_unblocked"] = marked

            if not missing_in_db and not missing_in_firewall:
                logger.info("Firewall and database are fully synchronized")

        except Exception as e:
            logger.error(f"Firewall reconciliation failed: {str(e)}")
            results["errors"].append(str(e))

        return results

    async def _get_firewall_blocked_ips(self) -> List[str]:
        """Get all blocked IPs from all configured Sangfor firewalls"""
        all_ips = set()

        stmt = select(DataSource).where(
            (DataSource.type == "sangfor") & (DataSource.enabled == True)
        )
        result = await self.db.execute(stmt)
        firewalls = result.scalars().all()

        for fw in firewalls:
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

                if response and isinstance(response, dict):
                    logger.debug(f"Raw response code: {response.get('code')}, message: {response.get('message')}")
                    data = response.get("data", {})
                    logger.debug(f"Data type: {type(data).__name__}, data: {str(data)[:200]}")
                    if isinstance(data, dict):
                        items = data.get("items", [])
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    ip = item.get("url") or item.get("srcIP") or item.get("ip")
                                    if ip:
                                        all_ips.add(ip)
                        else:
                            logger.error(f"Items is not a list: {type(items).__name__}")
                    else:
                        logger.error(f"Data is not a dict: {type(data).__name__}")

                logger.info(f"Retrieved {len(all_ips)} blocked IPs from firewall '{fw.tag}'")
            except Exception as e:
                logger.error(f"Failed to get blocked IPs from firewall '{fw.tag}': {str(e)}")

        return list(all_ips)

    async def _get_db_active_blacklist(self) -> List[Tuple[str, str, str]]:
        """Get all active blacklist entries (ip_address, mac_address, firewall_tag)"""
        from datetime import datetime, UTC

        stmt = select(
            Blacklist.ip_address,
            Blacklist.mac_address,
            Blacklist.firewall_tag
        ).where(
            (Blacklist.unblocked_at.is_(None)) &
            (Blacklist.auto_unblocked == False) &
            (or_(
                Blacklist.expires_at >= datetime.now(UTC),
                Blacklist.expires_at.is_(None),
            ))
        )
        result = await self.db.execute(stmt)
        return result.all()

    async def _create_db_entries(self, ip_addresses: List[str]) -> int:
        """Create blacklist entries and terminal records for IPs missing in database"""
        created = 0

        for ip_address in ip_addresses:
            try:
                stmt = select(Terminal).where(Terminal.ip_address == ip_address)
                result = await self.db.execute(stmt)
                terminal = result.scalar_one_or_none()

                if not terminal:
                    terminal = Terminal(
                        ip_address=ip_address,
                        status=TerminalStatus.BLOCKED.value,
                        compliance_status="non_compliant",
                        last_seen=datetime.now(UTC),
                    )
                    self.db.add(terminal)

                else:
                    terminal.status = TerminalStatus.BLOCKED.value
                    terminal.compliance_status = "non_compliant"

                stmt = select(Blacklist).where(
                    (Blacklist.ip_address == ip_address) &
                    (Blacklist.unblocked_at.is_(None)) &
                    (Blacklist.auto_unblocked == False)
                )
                result = await self.db.execute(stmt)
                existing_bl = result.scalar_one_or_none()

                if not existing_bl:
                    bl_entry = Blacklist(
                        ip_address=ip_address,
                        blocked_by="system",
                        blocked_at=datetime.now(UTC),
                        expires_at=datetime.now(UTC) + timedelta(days=30),
                        source_tag="reconciliation",
                        is_auto_blocked=True,
                        auto_unblocked=False,
                        reason="Reconciliation: IP blocked on firewall but not in database",
                    )
                    self.db.add(bl_entry)
                    created += 1

            except Exception as e:
                logger.error(f"Failed to create DB entry for {ip_address}: {str(e)}")

        if created > 0:
            await self.db.commit()
            logger.info(f"Created {created} blacklist entries during reconciliation")

        return created

    async def _unblock_from_firewall(self, ip_addresses: List[str]) -> Tuple[int, int]:
        """
        Unblock IPs on firewall that are in database but not on firewall.
        
        Returns:
            Tuple of (number of IPs unblocked on firewall, number of entries marked unblocked)
        """
        unblocked = 0
        marked = 0

        stmt = select(DataSource).where(
            (DataSource.type == "sangfor") & (DataSource.enabled == True)
        )
        result = await self.db.execute(stmt)
        firewalls = result.scalars().all()

        for ip_address in ip_addresses:
            try:
                firewall_unblocked = False

                for fw in firewalls:
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

                        response = await svc.unblock_ip([{"srcIP": ip_address}])

                        if response and response.get("code") == 0:
                            firewall_unblocked = True
                            break

                    except Exception as e:
                        logger.warning(f"Failed to unblock {ip_address} on firewall '{fw.tag}': {str(e)}")

                stmt = select(Blacklist).where(
                    (Blacklist.ip_address == ip_address) &
                    (Blacklist.unblocked_at.is_(None)) &
                    (Blacklist.auto_unblocked == False)
                )
                result = await self.db.execute(stmt)
                bl_entries = result.scalars().all()

                for entry in bl_entries:
                    entry.auto_unblocked = True
                    entry.unblocked_at = datetime.now(UTC)
                    entry.unblocked_by = "system"
                    marked += 1

                stmt = select(Terminal).where(Terminal.ip_address == ip_address)
                result = await self.db.execute(stmt)
                terminals = result.scalars().all()

                for terminal in terminals:
                    terminal.status = TerminalStatus.UNBLOCKED.value
                    terminal.compliance_status = "unknown"
                    terminal.firewall_tag = None

                if firewall_unblocked:
                    unblocked += 1

            except Exception as e:
                logger.error(f"Failed to unblock {ip_address}: {str(e)}")

        if marked > 0:
            await self.db.commit()
            logger.info(f"Marked {marked} blacklist entries as unblocked during reconciliation")

        return (unblocked, marked)