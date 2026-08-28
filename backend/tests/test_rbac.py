"""Tests for RBAC permission system — get_user_permissions, invalidate_user_permissions, require_permission"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.security import (
    get_user_permissions,
    invalidate_user_permissions,
    require_permission,
)


@pytest.fixture
def mock_db(mock_async_session):
    """Mock AsyncSession with correct sync/async method split."""
    return mock_async_session


class TestGetUserPermissions:
    """Test get_user_permissions with Redis cache"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_permissions(self, mock_redis_patch, mock_db):
        """Should return permissions from Redis cache when available"""
        mock_redis = mock_redis_patch
        cached_perms = json.dumps(["terminal:read", "terminal:write"])
        await mock_redis.setex("user_perms:1", 300, cached_perms)

        result = await get_user_permissions(mock_db, user_id=1)
        assert result == {"terminal:read", "terminal:write"}

    @pytest.mark.asyncio
    async def test_cache_miss_queries_database(self, mock_redis_patch, mock_db):
        """Should query database when Redis cache is empty"""
        mock_redis = mock_redis_patch

        # Mock database query result
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = ["terminal:read", "whitelist:read"]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_user_permissions(mock_db, user_id=2)
        assert result == {"terminal:read", "whitelist:read"}
        # Should have cached the result
        cached = await mock_redis.get("user_perms:2")
        assert cached is not None
        assert set(json.loads(cached)) == {"terminal:read", "whitelist:read"}

    @pytest.mark.asyncio
    async def test_cache_miss_empty_permissions(self, mock_redis_patch, mock_db):
        """Should handle user with no permissions"""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_user_permissions(mock_db, user_id=99)
        assert result == set()

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_to_db(self, mock_db):
        """Should fall back to database when Redis is unavailable"""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = ["terminal:read"]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis down")):
            result = await get_user_permissions(mock_db, user_id=1)
            assert result == {"terminal:read"}


class TestInvalidateUserPermissions:
    """Test permission cache invalidation"""

    @pytest.mark.asyncio
    async def test_invalidate_removes_cache(self, mock_redis_patch):
        """Should remove cached permissions for a user"""
        mock_redis = mock_redis_patch
        await mock_redis.setex("user_perms:1", 300, json.dumps(["terminal:read"]))

        await invalidate_user_permissions(user_id=1)

        cached = await mock_redis.get("user_perms:1")
        assert cached is None

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_cache_no_error(self, mock_redis_patch):
        """Should not raise when invalidating non-existent cache"""
        await invalidate_user_permissions(user_id=999)

    @pytest.mark.asyncio
    async def test_invalidate_redis_unavailable_no_error(self):
        """Should not raise when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis down")):
            await invalidate_user_permissions(user_id=1)


class TestRequirePermission:
    """Test require_permission dependency factory"""

    @pytest.mark.asyncio
    async def test_superuser_always_passes(self, mock_db):
        """Superuser should pass any permission check"""
        checker = require_permission("any:permission")

        mock_user = MagicMock()
        mock_user.is_superuser = True
        mock_user.id = 1

        result = await checker(current_user=mock_user, db=mock_db)
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_user_with_permission_passes(self, mock_db):
        """User with the required permission should pass"""
        checker = require_permission("terminal:read")

        mock_user = MagicMock()
        mock_user.is_superuser = False
        mock_user.id = 1

        with patch("app.core.security.get_user_permissions", return_value={"terminal:read", "terminal:write"}):
            result = await checker(current_user=mock_user, db=mock_db)
            assert result == mock_user

    @pytest.mark.asyncio
    async def test_user_without_permission_denied(self, mock_db):
        """User without the required permission should get 403"""
        from fastapi import HTTPException

        checker = require_permission("role:write")

        mock_user = MagicMock()
        mock_user.is_superuser = False
        mock_user.id = 1

        with patch("app.core.security.get_user_permissions", return_value={"terminal:read"}):
            with pytest.raises(HTTPException) as exc_info:
                await checker(current_user=mock_user, db=mock_db)
            assert exc_info.value.status_code == 403
            assert "role:write" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_user_with_empty_permissions_denied(self, mock_db):
        """User with no permissions should be denied"""
        from fastapi import HTTPException

        checker = require_permission("terminal:read")

        mock_user = MagicMock()
        mock_user.is_superuser = False
        mock_user.id = 1

        with patch("app.core.security.get_user_permissions", return_value=set()):
            with pytest.raises(HTTPException) as exc_info:
                await checker(current_user=mock_user, db=mock_db)
            assert exc_info.value.status_code == 403
