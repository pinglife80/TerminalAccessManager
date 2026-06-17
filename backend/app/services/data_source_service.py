"""
Data Source Service

CRUD operations for DataSource and DataSourceBinding,
plus connection testing functionality.
"""

import json

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.data_source import DataSource, DataSourceBinding
from app.schemas.data_source import (
    DataSourceCreate, DataSourceUpdate, ConnectionTestResult,
)
from app.core.crypto import encrypt_config, decrypt_config


class DataSourceService:
    """Service for managing data sources and their bindings"""

    VALID_TYPES = {"arp_ssh", "arp_api", "sangfor"}

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # DataSource CRUD
    # ------------------------------------------------------------------
    async def create_data_source(self, data: DataSourceCreate) -> DataSource:
        """Create a new data source"""
        if data.type not in self.VALID_TYPES:
            raise ValueError(f"Invalid data source type: {data.type}. Must be one of {self.VALID_TYPES}")

        # Check for duplicate name or tag
        existing = await self._get_by_name_or_tag(data.name, data.tag)
        if existing:
            if existing.name == data.name:
                raise ValueError(f"Data source with name '{data.name}' already exists")
            if existing.tag == data.tag:
                raise ValueError(f"Data source with tag '{data.tag}' already exists")

        source = DataSource(
            name=data.name,
            type=data.type,
            tag=data.tag,
            config=encrypt_config(data.config),
            enabled=data.enabled,
        )
        self.db.add(source)
        await self.db.commit()
        await self.db.refresh(source)
        logger.info(f"Created data source: {source.name} (tag={source.tag}, type={source.type})")
        return source

    async def update_data_source(self, source_id: int, data: DataSourceUpdate) -> DataSource | None:
        """Update an existing data source"""
        # Query directly without expunge — source must stay in session for updates
        stmt = select(DataSource).where(DataSource.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            return None

        if data.type is not None and data.type not in self.VALID_TYPES:
            raise ValueError(f"Invalid data source type: {data.type}")

        # Check for duplicate name/tag if being changed
        if data.name is not None and data.name != source.name:
            existing = await self._get_by_field(DataSource.name, data.name)
            if existing:
                raise ValueError(f"Data source with name '{data.name}' already exists")
            source.name = data.name

        if data.tag is not None and data.tag != source.tag:
            raise ValueError(
                f"Data source tag cannot be changed. Tag '{source.tag}' is referenced by terminals, "
                f"blacklist entries, and bindings. Please create a new data source with the desired tag "
                f"and delete the old one."
            )

        if data.type is not None:
            source.type = data.type
        if data.config is not None:
            source.config = encrypt_config(data.config)
        if data.enabled is not None:
            source.enabled = data.enabled

        await self.db.commit()
        await self.db.refresh(source)
        logger.info(f"Updated data source: {source.name} (id={source.id})")

        # Decrypt config for response (expunge after commit to avoid writing back)
        if source.config:
            self.db.expunge(source)
            source.config = decrypt_config(source.config)

        return source

    async def preview_delete_data_source(self, source_id: int) -> dict:
        """Preview the impact of deleting a data source without making any changes"""
        from app.models.terminal import Terminal
        from app.models.blacklist import Blacklist

        stmt = select(DataSource).where(DataSource.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            return {
                "can_delete": False,
                "warnings": [],
                "actions": [],
                "affected": {"terminals": 0, "blocked_terminals": 0, "blacklist_entries": 0, "bindings": 0, "compliant_terminals": 0},
                "reason": "Data source not found",
            }

        tag = source.tag
        source_type = source.type
        source_name = source.name

        # Count affected terminals
        terminal_stmt = select(Terminal).where(Terminal.source_tag == tag)
        terminal_result = await self.db.execute(terminal_stmt)
        terminals = terminal_result.scalars().all()
        terminal_count = len(terminals)
        blocked_count = sum(1 for t in terminals if t.status == "blocked")

        # Count affected blacklist entries
        bl_stmt = select(Blacklist).where(
            (Blacklist.source_tag == tag) | (Blacklist.firewall_tag == tag)
        )
        bl_result = await self.db.execute(bl_stmt)
        blacklist_entries = bl_result.scalars().all()
        bl_count = len(blacklist_entries)

        # Count affected bindings
        bind_stmt = select(DataSourceBinding).where(
            (DataSourceBinding.arp_source_tag == tag) | (DataSourceBinding.firewall_tag == tag)
        )
        bind_result = await self.db.execute(bind_stmt)
        bindings = bind_result.scalars().all()
        bind_count = len(bindings)

        # Build warnings and actions
        warnings = []
        actions = []

        if source_type in ("arp_ssh", "arp_api"):
            # ARP source deletion
            if terminal_count > 0:
                warnings.append(f"该数据源关联 {terminal_count} 个终端记录")
            if blocked_count > 0:
                warnings.append(f"其中 {blocked_count} 个终端当前处于已封堵状态")
            if bl_count > 0:
                warnings.append(f"该数据源关联 {bl_count} 条黑名单记录")
            if bind_count > 0:
                warnings.append(f"该数据源关联 {bind_count} 条绑定关系")

            if blocked_count > 0:
                # Find firewall tags for unblocking
                fw_tags = set()
                for bl in blacklist_entries:
                    if bl.firewall_tag:
                        fw_tags.add(bl.firewall_tag)
                for fw_tag in fw_tags:
                    actions.append(f"从防火墙 [{fw_tag}] 解封 {blocked_count} 个已封堵终端")
            if bl_count > 0:
                actions.append(f"删除 {bl_count} 条黑名单记录")
            if bind_count > 0:
                actions.append(f"删除 {bind_count} 条数据源绑定关系")
            actions.append(f"清理 Redis 缓存 (ipguard:{tag})")
            if terminal_count > 0:
                actions.append(f"删除 {terminal_count} 个终端记录")
            actions.append(f"删除数据源 [{source_name}]")

        elif source_type == "sangfor":
            # Sangfor firewall deletion
            if blocked_count > 0:
                warnings.append(f"该防火墙关联 {blocked_count} 个已封堵终端")
            if bl_count > 0:
                warnings.append(f"该防火墙关联 {bl_count} 条黑名单记录")
            if bind_count > 0:
                warnings.append(f"该防火墙关联 {bind_count} 条绑定关系")

            # Check firewall reachability for unblocking
            can_delete = True
            if blocked_count > 0:
                try:
                    from app.services.sangfor_service import SangforService
                    config = source.config
                    if config:
                        config = decrypt_config(config)
                    svc = SangforService(
                        base_url=config.get("base_url", ""),
                        username=config.get("username", ""),
                        password=config.get("password", ""),
                        verify_ssl=config.get("verify_ssl", True),
                        ca_bundle=config.get("ca_bundle", ""),
                    )
                    test_result = await svc.test_connection()
                    await svc.close()
                    if not test_result.get("success", False):
                        can_delete = False
                        warnings.append("防火墙当前不可达，无法执行解封操作")
                except Exception:
                    can_delete = False
                    warnings.append("防火墙连接失败，无法执行解封操作")

            if can_delete:
                if blocked_count > 0:
                    actions.append(f"从防火墙 [{tag}] 解封 {blocked_count} 个终端")
                if bl_count > 0:
                    actions.append(f"删除 {bl_count} 条黑名单记录")
                if bind_count > 0:
                    actions.append(f"删除 {bind_count} 条数据源绑定关系")
                actions.append(f"清理已封堵终端的 firewall_tag 引用")
                actions.append(f"删除数据源 [{source_name}]")
            else:
                actions.append("请确保防火墙连接正常后重试")

            return {
                "can_delete": can_delete,
                "warnings": warnings,
                "actions": actions,
                "affected": {
                    "terminals": terminal_count,
                    "blocked_terminals": blocked_count,
                    "blacklist_entries": bl_count,
                    "bindings": bind_count,
                    "compliant_terminals": 0,
                },
                "reason": None if can_delete else "防火墙不可达，无法安全解封已封堵终端",
            }

        return {
            "can_delete": True,
            "warnings": warnings,
            "actions": actions,
            "affected": {
                "terminals": terminal_count,
                "blocked_terminals": blocked_count,
                "blacklist_entries": bl_count,
                "bindings": bind_count,
                "compliant_terminals": 0,
            },
        }

    async def safe_delete_data_source(self, source_id: int, username: str = None, client_ip: str = None) -> bool:
        """Safely delete a data source with automatic cleanup of dependent data"""
        from app.models.terminal import Terminal
        from app.models.blacklist import Blacklist
        from app.services.terminal_service import TerminalService

        stmt = select(DataSource).where(DataSource.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            return False

        tag = source.tag
        source_type = source.type
        source_name = source.name

        # Step 1: For ARP sources, handle terminals and blacklist
        if source_type in ("arp_ssh", "arp_api"):
            # Unblock terminals on firewalls
            terminal_stmt = select(Terminal).where(
                (Terminal.source_tag == tag) & (Terminal.status == "blocked")
            )
            terminal_result = await self.db.execute(terminal_stmt)
            blocked_terminals = terminal_result.scalars().all()

            for terminal in blocked_terminals:
                # Find blacklist entries for this terminal (use normalized MAC for reliable matching)
                mac_norm = terminal.mac_address.replace('-', '').replace(':', '').replace('.', '').upper() if terminal.mac_address else None
                bl_stmt = select(Blacklist).where(
                    (Blacklist.ip_address == terminal.ip_address) &
                    (Blacklist.mac_address_normalized == mac_norm)
                )
                bl_result = await self.db.execute(bl_stmt)
                bl_entries = bl_result.scalars().all()

                # Group blacklist entries by firewall_tag for batch unblock
                fw_ip_map: dict[str, list[dict[str, str]]] = {}
                for bl_entry in bl_entries:
                    if bl_entry.firewall_tag:
                        fw_ip_map.setdefault(bl_entry.firewall_tag, []).append(
                            {"srcIP": bl_entry.ip_address}
                        )

                # Unblock on each firewall
                for fw_tag, ip_list in fw_ip_map.items():
                    try:
                        fw_source = await self.get_data_source_by_tag(fw_tag)
                        if fw_source and fw_source.type == "sangfor":
                            from app.services.sangfor_service import SangforService
                            fw_config = fw_source.config
                            if fw_config:
                                fw_config = decrypt_config(fw_config)
                            svc = SangforService(
                                base_url=fw_config.get("base_url", ""),
                                username=fw_config.get("username", ""),
                                password=fw_config.get("password", ""),
                                verify_ssl=fw_config.get("verify_ssl", True),
                                ca_bundle=fw_config.get("ca_bundle", ""),
                            )
                            await svc.unblock_ip(ip_list)
                            await svc.close()
                    except Exception as e:
                        logger.warning(f"Failed to unblock {terminal.ip_address} on {fw_tag}: {e}")

                # Update terminal status
                terminal.status = "unblocked"
                terminal.firewall_tag = None
                terminal.compliance_status = "unknown"
                terminal.comments = None

            # Delete all blacklist entries for this source
            await self.db.execute(
                delete(Blacklist).where(
                    (Blacklist.source_tag == tag) | (Blacklist.firewall_tag == tag)
                )
            )

            # Delete all terminals from this source
            await self.db.execute(
                delete(Terminal).where(Terminal.source_tag == tag)
            )

        # Step 2: For Sangfor firewalls, handle blocked terminals and blacklist
        elif source_type == "sangfor":
            # Find terminals blocked on this firewall
            terminal_stmt = select(Terminal).where(
                Terminal.firewall_tag.contains(tag)
            )
            terminal_result = await self.db.execute(terminal_stmt)
            affected_terminals = terminal_result.scalars().all()

            # Unblock on this firewall
            try:
                config = source.config
                if config:
                    config = decrypt_config(config)
                from app.services.sangfor_service import SangforService
                svc = SangforService(
                    base_url=config.get("base_url", ""),
                    username=config.get("username", ""),
                    password=config.get("password", ""),
                    verify_ssl=config.get("verify_ssl", True),
                    ca_bundle=config.get("ca_bundle", ""),
                )

                # Get blocked IPs from blacklist
                bl_stmt = select(Blacklist).where(Blacklist.firewall_tag == tag)
                bl_result = await self.db.execute(bl_stmt)
                bl_entries = bl_result.scalars().all()

                # Batch unblock
                ip_list = [{"srcIP": bl.ip_address} for bl in bl_entries if bl.ip_address]
                if ip_list:
                    try:
                        await svc.unblock_ip(ip_list)
                    except Exception as e:
                        logger.warning(f"Failed to unblock IPs on {tag}: {e}")

                await svc.close()
            except Exception as e:
                logger.warning(f"Failed to connect to Sangfor firewall {tag}: {e}")

            # Update terminal firewall_tag - remove this tag
            for terminal in affected_terminals:
                if terminal.firewall_tag:
                    tags = [t.strip() for t in terminal.firewall_tag.split(",") if t.strip() != tag]
                    if not tags:
                        terminal.firewall_tag = None
                        terminal.status = "unblocked"
                        terminal.compliance_status = "unknown"
                        terminal.comments = None
                    else:
                        terminal.firewall_tag = ",".join(tags)

            # Delete blacklist entries for this firewall
            await self.db.execute(
                delete(Blacklist).where(Blacklist.firewall_tag == tag)
            )

        # Step 3: Delete bindings (common for all types)
        await self.db.execute(
            delete(DataSourceBinding).where(
                (DataSourceBinding.arp_source_tag == tag) |
                (DataSourceBinding.firewall_tag == tag)
            )
        )

        # Step 4: Clean up Redis cache
        try:
            from app.core.security import get_redis_client
            redis_client = await get_redis_client()
            if redis_client:
                keys_to_delete = []
                for pattern in [f"ipguard:{tag}", f"arp:{tag}"]:
                    found = await redis_client.keys(pattern)
                    keys_to_delete.extend(found)
                if keys_to_delete:
                    await redis_client.delete(*keys_to_delete)
        except Exception as e:
            logger.warning(f"Failed to clean Redis cache for {tag}: {e}")

        # Step 5: Delete the data source
        await self.db.delete(source)
        await self.db.commit()

        # Step 6: Audit log
        if username:
            ts = TerminalService(self.db)
            await ts.log_action(
                username, "delete_datasource", "datasource", str(source_id),
                {"message": f"Safely deleted datasource with cleanup", "name": source_name, "tag": tag},
                ip_address=client_ip,
                resource_name=source_name,
            )

        logger.info(f"Safely deleted data source: {source_name} (tag={tag}, type={source_type})")
        return True

    async def preview_delete_binding(self, binding_id: int) -> dict:
        """Preview the impact of deleting a data source binding"""
        from app.models.terminal import Terminal
        from app.models.blacklist import Blacklist

        stmt = select(DataSourceBinding).where(DataSourceBinding.id == binding_id)
        result = await self.db.execute(stmt)
        binding = result.scalar_one_or_none()
        if not binding:
            return {
                "can_delete": False,
                "warnings": [],
                "actions": [],
                "affected": {"terminals": 0, "blocked_terminals": 0, "blacklist_entries": 0, "bindings": 0, "compliant_terminals": 0},
                "reason": "Binding not found",
            }

        arp_tag = binding.arp_source_tag
        fw_tag = binding.firewall_tag

        # Find blocked terminals from this ARP source that are blocked on this firewall
        bl_stmt = select(Blacklist).where(
            (Blacklist.source_tag == arp_tag) & (Blacklist.firewall_tag == fw_tag)
        )
        bl_result = await self.db.execute(bl_stmt)
        bl_entries = bl_result.scalars().all()
        bl_count = len(bl_entries)

        # Count distinct blocked IPs
        blocked_ips = set(bl.ip_address for bl in bl_entries)
        blocked_count = len(blocked_ips)

        warnings = []
        actions = []

        if blocked_count > 0:
            warnings.append(f"该绑定关联的 ARP 源下有 {blocked_count} 个终端在防火墙 [{fw_tag}] 上被封堵")
            warnings.append(f"删除后这些终端将从防火墙 [{fw_tag}] 解封")
            actions.append(f"从防火墙 [{fw_tag}] 解封 {blocked_count} 个终端")
            actions.append(f"删除 {bl_count} 条黑名单记录")

        actions.append("触发合规状态重算")
        actions.append(f"删除绑定关系 [{arp_tag} → {fw_tag}]")

        return {
            "can_delete": True,
            "warnings": warnings,
            "actions": actions,
            "affected": {
                "terminals": 0,
                "blocked_terminals": blocked_count,
                "blacklist_entries": bl_count,
                "bindings": 1,
                "compliant_terminals": 0,
            },
        }

    async def safe_delete_binding(self, binding_id: int, username: str = None, client_ip: str = None) -> bool:
        """Safely delete a binding with automatic cleanup"""
        from app.models.terminal import Terminal
        from app.models.blacklist import Blacklist
        from app.services.terminal_service import TerminalService

        stmt = select(DataSourceBinding).where(DataSourceBinding.id == binding_id)
        result = await self.db.execute(stmt)
        binding = result.scalar_one_or_none()
        if not binding:
            return False

        arp_tag = binding.arp_source_tag
        fw_tag = binding.firewall_tag

        # Step 1: Find and unblock terminals on this firewall
        bl_stmt = select(Blacklist).where(
            (Blacklist.source_tag == arp_tag) & (Blacklist.firewall_tag == fw_tag)
        )
        bl_result = await self.db.execute(bl_stmt)
        bl_entries = bl_result.scalars().all()

        # Unblock on firewall
        try:
            fw_source = await self.get_data_source_by_tag(fw_tag)
            if fw_source and fw_source.type == "sangfor":
                from app.services.sangfor_service import SangforService
                fw_config = fw_source.config
                if fw_config:
                    fw_config = decrypt_config(fw_config)
                svc = SangforService(
                    base_url=fw_config.get("base_url", ""),
                    username=fw_config.get("username", ""),
                    password=fw_config.get("password", ""),
                    verify_ssl=fw_config.get("verify_ssl", True),
                    ca_bundle=fw_config.get("ca_bundle", ""),
                )
                ip_list = [{"srcIP": bl.ip_address} for bl in bl_entries if bl.ip_address]
                if ip_list:
                    try:
                        await svc.unblock_ip(ip_list)
                    except Exception as e:
                        logger.warning(f"Failed to unblock IPs on {fw_tag}: {e}")
                await svc.close()
        except Exception as e:
            logger.warning(f"Failed to connect to firewall {fw_tag}: {e}")

        # Step 2: Update terminal status
        for bl_entry in bl_entries:
            terminal_stmt = select(Terminal).where(
                (Terminal.ip_address == bl_entry.ip_address) &
                (Terminal.mac_address == bl_entry.mac_address)
            )
            t_result = await self.db.execute(terminal_stmt)
            terminal = t_result.scalar_one_or_none()
            if terminal:
                # Check if terminal is blocked on other firewalls too (use normalized MAC)
                mac_norm = terminal.mac_address.replace('-', '').replace(':', '').replace('.', '').upper() if terminal.mac_address else None
                other_bl_stmt = select(Blacklist).where(
                    (Blacklist.ip_address == terminal.ip_address) &
                    (Blacklist.mac_address_normalized == mac_norm) &
                    (Blacklist.firewall_tag != fw_tag)
                )
                other_bl_result = await self.db.execute(other_bl_stmt)
                other_bl = other_bl_result.scalars().all()

                if not other_bl:
                    terminal.status = "unblocked"
                    terminal.firewall_tag = None
                    terminal.compliance_status = "unknown"
                    terminal.comments = None
                else:
                    # Still blocked on other firewalls - just remove this fw_tag
                    remaining_tags = [bl.firewall_tag for bl in other_bl if bl.firewall_tag]
                    if terminal.firewall_tag:
                        current_tags = [t.strip() for t in terminal.firewall_tag.split(",") if t.strip() != fw_tag]
                        terminal.firewall_tag = ",".join(current_tags) if current_tags else None

        # Step 3: Delete blacklist entries for this binding
        for bl_entry in bl_entries:
            await self.db.delete(bl_entry)

        # Step 4: Delete the binding
        await self.db.delete(binding)
        await self.db.commit()

        # Step 5: Trigger compliance recalculation
        try:
            from app.services.compliance_service import ComplianceService
            cs = ComplianceService(self.db)
            await cs.recalculate_all_compliance()
        except Exception as e:
            logger.warning(f"Failed to trigger compliance recalculation after binding deletion: {e}")

        # Step 6: Audit log
        if username:
            ts = TerminalService(self.db)
            await ts.log_action(
                username, "unbind_datasource", "datasource", str(binding_id),
                {"message": "Safely deleted datasource binding with cleanup", "arp_source_tag": arp_tag, "firewall_tag": fw_tag},
                ip_address=client_ip,
                resource_name=f"{arp_tag} -> {fw_tag}",
            )

        logger.info(f"Safely deleted binding: {arp_tag} -> {fw_tag}")
        return True

    async def delete_data_source(self, source_id: int) -> bool:
        """Delete a data source by ID"""
        # Query directly without expunge — source must stay in session for deletion
        stmt = select(DataSource).where(DataSource.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            return False

        # Also delete bindings referencing this source
        await self.db.execute(
            delete(DataSourceBinding).where(
                (DataSourceBinding.arp_source_tag == source.tag) |
                (DataSourceBinding.firewall_tag == source.tag)
            )
        )

        await self.db.delete(source)
        await self.db.commit()
        logger.info(f"Deleted data source: {source.name} (id={source.id})")
        return True

    async def get_data_source_by_id(self, source_id: int) -> DataSource | None:
        """Get a data source by ID"""
        stmt = select(DataSource).where(DataSource.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if source and source.config:
            # Use expunge to detach from session before modifying config,
            # preventing decrypted config from being written back to DB on commit
            self.db.expunge(source)
            source.config = decrypt_config(source.config)
        return source

    async def get_data_source_by_tag(self, tag: str) -> DataSource | None:
        """Get a data source by tag"""
        stmt = select(DataSource).where(DataSource.tag == tag)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if source and source.config:
            self.db.expunge(source)
            source.config = decrypt_config(source.config)
        return source

    async def list_data_sources(
        self,
        type: str | None = None,
        enabled: bool | None = None,
    ) -> list[DataSource]:
        """List all data sources with optional filtering"""
        stmt = select(DataSource).order_by(DataSource.id)
        if type:
            stmt = stmt.where(DataSource.type == type)
        if enabled is not None:
            stmt = stmt.where(DataSource.enabled == enabled)

        result = await self.db.execute(stmt)
        sources = result.scalars().all()
        for source in sources:
            if source.config:
                self.db.expunge(source)
                source.config = decrypt_config(source.config)
        return sources

    async def update_sync_status(
        self, source_id: int, status: str, error: str | None = None
    ) -> None:
        """Update the last sync status of a data source"""
        # Read directly from DB without expunge, so changes are tracked by session
        stmt = select(DataSource).where(DataSource.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if source:
            from datetime import datetime, timezone
            source.last_sync_at = datetime.now(timezone.utc)
            source.last_sync_status = status
            source.last_sync_error = error
            await self.db.commit()

    # ------------------------------------------------------------------
    # Connection Testing
    # ------------------------------------------------------------------
    async def test_connection(self, source_id: int) -> ConnectionTestResult:
        """Test the connection to a data source"""
        source = await self.get_data_source_by_id(source_id)
        if not source:
            return ConnectionTestResult(success=False, message="Data source not found")

        try:
            if source.type == "arp_ssh":
                return await self._test_ssh_connection(source)
            elif source.type == "arp_api":
                return await self._test_api_connection(source)
            elif source.type == "sangfor":
                return await self._test_sangfor_connection(source)
            else:
                return ConnectionTestResult(
                    success=False, message=f"Unknown data source type: {source.type}"
                )
        except Exception as e:
            logger.error(f"Connection test failed for {source.name}: {str(e)}")
            return ConnectionTestResult(
                success=False, message=f"Connection test failed: {str(e)}"
            )

    async def _test_ssh_connection(self, source: DataSource) -> ConnectionTestResult:
        """Test SSH connection to a switch"""
        config = source.config
        try:
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=config.get("host", ""),
                port=config.get("port", 22),
                username=config.get("username", ""),
                password=config.get("password", ""),
                timeout=10,
            )
            client.close()
            return ConnectionTestResult(success=True, message="SSH connection successful")
        except ImportError:
            return ConnectionTestResult(
                success=False, message="paramiko library not installed"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False, message=f"SSH connection failed: {str(e)}"
            )

    async def _test_api_connection(self, source: DataSource) -> ConnectionTestResult:
        """Test HTTP API connection"""
        import httpx
        config = source.config
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = config.get("headers", {})
                if config.get("auth_type") == "bearer" and config.get("token"):
                    headers["Authorization"] = f"Bearer {config['token']}"

                method = config.get("method", "GET").upper()
                url = config.get("url", "")

                if method == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.post(url, headers=headers)

                if response.status_code < 400:
                    return ConnectionTestResult(
                        success=True,
                        message=f"API connection successful (HTTP {response.status_code})",
                    )
                else:
                    return ConnectionTestResult(
                        success=False,
                        message=f"API returned HTTP {response.status_code}",
                    )
        except Exception as e:
            return ConnectionTestResult(
                success=False, message=f"API connection failed: {str(e)}"
            )

    async def _test_sangfor_connection(self, source: DataSource) -> ConnectionTestResult:
        """Test Sangfor AF API connection"""
        config = source.config
        try:
            from app.services.sangfor_service import SangforService
            svc = SangforService(
                base_url=config.get("base_url", ""),
                username=config.get("username", ""),
                password=config.get("password", ""),
                verify_ssl=config.get("verify_ssl", True),
                ca_bundle=config.get("ca_bundle", ""),
            )
            result = await svc.test_connection()
            await svc.close()
            return ConnectionTestResult(
                success=result["success"],
                message=result.get("message", "Sangfor AF connection test"),
                details=result.get("details"),
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False, message=f"Sangfor AF connection failed: {str(e)}"
            )

    # ------------------------------------------------------------------
    # DataSourceBinding CRUD
    # ------------------------------------------------------------------
    async def create_binding(self, arp_source_tag: str, firewall_tag: str) -> DataSourceBinding:
        """Create a binding between an ARP source and a firewall"""
        # Validate both tags exist
        arp_source = await self.get_data_source_by_tag(arp_source_tag)
        if not arp_source:
            raise ValueError(f"ARP data source with tag '{arp_source_tag}' not found")
        if arp_source.type not in ("arp_ssh", "arp_api"):
            raise ValueError(f"Data source '{arp_source_tag}' is not an ARP source (type={arp_source.type})")

        fw_source = await self.get_data_source_by_tag(firewall_tag)
        if not fw_source:
            raise ValueError(f"Firewall data source with tag '{firewall_tag}' not found")
        if fw_source.type != "sangfor":
            raise ValueError(f"Data source '{firewall_tag}' is not a firewall (type={fw_source.type})")

        # Check for duplicate binding
        stmt = select(DataSourceBinding).where(
            (DataSourceBinding.arp_source_tag == arp_source_tag) &
            (DataSourceBinding.firewall_tag == firewall_tag)
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Binding between '{arp_source_tag}' and '{firewall_tag}' already exists")

        binding = DataSourceBinding(
            arp_source_tag=arp_source_tag,
            firewall_tag=firewall_tag,
        )
        self.db.add(binding)
        await self.db.commit()
        await self.db.refresh(binding)
        logger.info(f"Created binding: {arp_source_tag} -> {firewall_tag}")
        return binding

    async def delete_binding(self, binding_id: int) -> bool:
        """Delete a binding by ID"""
        stmt = select(DataSourceBinding).where(DataSourceBinding.id == binding_id)
        result = await self.db.execute(stmt)
        binding = result.scalar_one_or_none()
        if not binding:
            return False

        await self.db.delete(binding)
        await self.db.commit()
        logger.info(f"Deleted binding: {binding.arp_source_tag} -> {binding.firewall_tag}")
        return True

    async def list_bindings(
        self, arp_source_tag: str | None = None
    ) -> list[DataSourceBinding]:
        """List all bindings, optionally filtered by ARP source tag"""
        stmt = select(DataSourceBinding).order_by(DataSourceBinding.id)
        if arp_source_tag:
            stmt = stmt.where(DataSourceBinding.arp_source_tag == arp_source_tag)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_firewall_tags_for_arp(self, arp_source_tag: str) -> list[str]:
        """Get all firewall tags associated with an ARP source"""
        stmt = (
            select(DataSourceBinding.firewall_tag)
            .where(DataSourceBinding.arp_source_tag == arp_source_tag)
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _get_by_name_or_tag(self, name: str, tag: str) -> DataSource | None:
        """Get a data source by name or tag"""
        stmt = select(DataSource).where(
            (DataSource.name == name) | (DataSource.tag == tag)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_by_field(self, field, value) -> DataSource | None:
        """Get a data source by a specific field"""
        stmt = select(DataSource).where(field == value)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
