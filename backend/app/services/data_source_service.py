"""
Data Source Service

CRUD operations for DataSource and DataSourceBinding,
plus connection testing functionality.
"""

import json
from typing import Optional, List, Dict, Any

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

    async def update_data_source(self, source_id: int, data: DataSourceUpdate) -> Optional[DataSource]:
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
            existing = await self._get_by_field(DataSource.tag, data.tag)
            if existing:
                raise ValueError(f"Data source with tag '{data.tag}' already exists")
            source.tag = data.tag

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

    async def get_data_source_by_id(self, source_id: int) -> Optional[DataSource]:
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

    async def get_data_source_by_tag(self, tag: str) -> Optional[DataSource]:
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
        type: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> List[DataSource]:
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
        self, source_id: int, status: str, error: Optional[str] = None
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
            stats = await svc.get_system_stats()
            await svc.close()
            return ConnectionTestResult(
                success=True,
                message="Sangfor AF connection successful",
                details={"cpu": stats.get("cpu"), "memory": stats.get("memory")},
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
        self, arp_source_tag: Optional[str] = None
    ) -> List[DataSourceBinding]:
        """List all bindings, optionally filtered by ARP source tag"""
        stmt = select(DataSourceBinding).order_by(DataSourceBinding.id)
        if arp_source_tag:
            stmt = stmt.where(DataSourceBinding.arp_source_tag == arp_source_tag)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_firewall_tags_for_arp(self, arp_source_tag: str) -> List[str]:
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
    async def _get_by_name_or_tag(self, name: str, tag: str) -> Optional[DataSource]:
        """Get a data source by name or tag"""
        stmt = select(DataSource).where(
            (DataSource.name == name) | (DataSource.tag == tag)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_by_field(self, field, value) -> Optional[DataSource]:
        """Get a data source by a specific field"""
        stmt = select(DataSource).where(field == value)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
