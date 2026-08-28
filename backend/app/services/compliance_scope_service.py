import ipaddress
import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance_scope import ComplianceScope
from app.schemas.compliance_scope import ComplianceScopeCreate, ComplianceScopeUpdate

logger = logging.getLogger(__name__)

SCOPE_CACHE_KEY = "compliance_scope:all"


async def invalidate_scope_cache():
    """Invalidate the scope cache after any scope change"""
    try:
        from app.core.security import get_redis_client
        redis = await get_redis_client()
        await redis.delete(SCOPE_CACHE_KEY)
        logger.info("Invalidated compliance scope cache")
    except Exception as e:
        logger.warning(f"Failed to invalidate scope cache: {e}")


class ComplianceScopeService:
    """Service for managing compliance calculation scopes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_scopes(self, is_active: Optional[bool] = None) -> list[ComplianceScope]:
        stmt = select(ComplianceScope).order_by(ComplianceScope.created_at.desc())
        if is_active is not None:
            stmt = stmt.where(ComplianceScope.is_active == is_active)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_scope(self, scope_id: int) -> Optional[ComplianceScope]:
        stmt = select(ComplianceScope).where(ComplianceScope.id == scope_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_scope(self, data: ComplianceScopeCreate, username: str) -> ComplianceScope:
        self._validate_scope_value(data.scope_type, data.scope_value)
        scope = ComplianceScope(
            scope_type=data.scope_type,
            scope_value=data.scope_value,
            description=data.description,
            is_active=True,
            created_by=username,
        )
        self.db.add(scope)
        await self.db.commit()
        await self.db.refresh(scope)
        await invalidate_scope_cache()
        logger.info(f"Created compliance scope: {data.scope_type}={data.scope_value} by {username}")
        return scope

    async def update_scope(
        self, scope_id: int, data: ComplianceScopeUpdate
    ) -> Optional[ComplianceScope]:
        scope = await self.get_scope(scope_id)
        if not scope:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if "scope_type" in update_data or "scope_value" in update_data:
            new_type = update_data.get("scope_type", scope.scope_type)
            new_value = update_data.get("scope_value", scope.scope_value)
            self._validate_scope_value(new_type, new_value)
        for key, value in update_data.items():
            setattr(scope, key, value)
        await self.db.commit()
        await self.db.refresh(scope)
        await invalidate_scope_cache()
        return scope

    async def delete_scope(self, scope_id: int) -> bool:
        scope = await self.get_scope(scope_id)
        if not scope:
            return False
        await self.db.delete(scope)
        await self.db.commit()
        await invalidate_scope_cache()
        logger.info(f"Deleted compliance scope: id={scope_id}")
        return True

    async def toggle_scope(self, scope_id: int) -> Optional[ComplianceScope]:
        scope = await self.get_scope(scope_id)
        if not scope:
            return None
        scope.is_active = not scope.is_active
        await self.db.commit()
        await self.db.refresh(scope)
        await invalidate_scope_cache()
        return scope

    @staticmethod
    def _validate_scope_value(scope_type: str, scope_value: str) -> None:
        """Validate the scope value format."""
        if not scope_value or not scope_value.strip():
            raise ValueError("Scope value cannot be empty")
        scope_value = scope_value.strip()

        if scope_type == "ip_cidr":
            try:
                network = ipaddress.ip_network(scope_value, strict=False)
                if network.prefixlen < 24:
                    raise ValueError(
                        f"CIDR prefix /{network.prefixlen} is too broad (min /24)"
                    )
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid IP CIDR format: '{scope_value}': {e}")

        elif scope_type == "ip_range":
            # Format: "192.168.1.1-255" = prefix "192.168.1" with start/end last octets.
            # This matches _parse_ip_range / _ip_in_range convention elsewhere.
            match = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})-(\d{1,3})$", scope_value)
            if not match:
                raise ValueError(
                    f"Invalid IP range format: '{scope_value}'. Expected format: 192.168.1.1-255"
                )
            prefix = match.group(1)
            start = int(match.group(2))
            end = int(match.group(3))

            # Validate the prefix is a valid IPv4 address (catches 999.999.999.x etc.)
            try:
                ipaddress.IPv4Address(f"{prefix}.1")
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid IP range: '{scope_value}': {e}")

            if start > end:
                raise ValueError(
                    f"Invalid IP range: start IP (start={start}) is greater than end IP (end={end})"
                )
            if end > 255:
                raise ValueError(f"IP range end ({end}) exceeds 255")

        elif scope_type in ("mac_prefix_arp", "mac_prefix_ipguard"):
            segments = scope_value.upper().split(":")
            if len(segments) < 3 or len(segments) > 5:
                raise ValueError(
                    f"MAC prefix must have 3-5 segments (e.g., AA:BB:CC), got {len(segments)} segments"
                )
            for seg in segments:
                if not re.match(r"^[0-9A-F]{2}$", seg):
                    raise ValueError(
                        f"Invalid MAC prefix segment: '{seg}'. Each segment must be 2 hex characters"
                    )

        else:
            raise ValueError(f"Unknown scope type: '{scope_type}'")
