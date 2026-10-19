"""
Unit tests for ComplianceScopeService and the scope-cache invalidation helper.

All DB operations are mocked via the shared AsyncSession mock factory; Redis is
mocked via conftest's autouse get_redis_client patch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.compliance_scope import ComplianceScope
from app.schemas.compliance_scope import ComplianceScopeCreate, ComplianceScopeUpdate
from app.services.compliance_scope_service import (
    SCOPE_CACHE_KEY,
    ComplianceScopeService,
    invalidate_scope_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(scalar=None, rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    if rows is not None:
        result.scalars.return_value.all.return_value = rows
    return result


def make_scope(id_=1, scope_type="ip_cidr", scope_value="192.168.0.0/24",
               is_active=True, description=None):
    s = MagicMock(spec=ComplianceScope)
    s.id = id_
    s.scope_type = scope_type
    s.scope_value = scope_value
    s.description = description
    s.is_active = is_active
    s.created_by = "admin"
    return s


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(mock_async_session):
    return mock_async_session


@pytest.fixture
def service(mock_db):
    return ComplianceScopeService(mock_db)


# ===========================================================================
# invalidate_scope_cache
# ===========================================================================

class TestInvalidateScopeCache:
    @pytest.mark.asyncio
    async def test_success_deletes_key(self, mock_redis):
        mock_redis._data[SCOPE_CACHE_KEY] = "x"
        await invalidate_scope_cache()
        assert SCOPE_CACHE_KEY not in mock_redis._data

    @pytest.mark.asyncio
    async def test_failure_swallowed(self):
        with patch("app.core.security.get_redis_client", side_effect=Exception("boom")):
            await invalidate_scope_cache()  # must not raise


# ===========================================================================
# list_scopes / get_scope
# ===========================================================================

class TestListScopes:
    @pytest.mark.asyncio
    async def test_no_filter(self, service, mock_db):
        rows = [make_scope(1), make_scope(2)]
        mock_db.execute = AsyncMock(return_value=make_result(rows=rows))
        result = await service.list_scopes()
        assert result == rows

    @pytest.mark.asyncio
    async def test_active_filter(self, service, mock_db):
        rows = [make_scope(1)]
        mock_db.execute = AsyncMock(return_value=make_result(rows=rows))
        result = await service.list_scopes(is_active=True)
        assert result == rows


class TestGetScope:
    @pytest.mark.asyncio
    async def test_found(self, service, mock_db):
        scope = make_scope(1)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=scope))
        assert await service.get_scope(1) is scope

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.get_scope(99) is None


# ===========================================================================
# create_scope
# ===========================================================================

class TestCreateScope:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        data = ComplianceScopeCreate(scope_type="ip_cidr", scope_value="192.168.0.0/24")
        with patch("app.services.compliance_scope_service.invalidate_scope_cache") as inval:
            scope = await service.create_scope(data, "admin")

        assert isinstance(scope, ComplianceScope)
        assert scope.scope_value == "192.168.0.0/24"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        inval.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_value_raises(self, service, mock_db):
        data = ComplianceScopeCreate(scope_type="ip_cidr", scope_value="192.168.1.0/33")
        with patch("app.services.compliance_scope_service.invalidate_scope_cache") as inval:
            with pytest.raises(ValueError):
                await service.create_scope(data, "admin")

        mock_db.add.assert_not_called()
        inval.assert_not_called()


# ===========================================================================
# update_scope
# ===========================================================================

class TestUpdateScope:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        data = ComplianceScopeUpdate(description="new")
        assert await service.update_scope(99, data) is None

    @pytest.mark.asyncio
    async def test_success_with_type_change(self, service, mock_db):
        scope = make_scope(1, scope_type="ip_cidr", scope_value="192.168.0.0/24")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=scope))
        data = ComplianceScopeUpdate(scope_type="ip_cidr", scope_value="192.168.1.0/24")

        with patch("app.services.compliance_scope_service.invalidate_scope_cache") as inval:
            result = await service.update_scope(1, data)

        assert result is scope
        assert scope.scope_value == "192.168.1.0/24"
        mock_db.commit.assert_called_once()
        inval.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_without_type_change_skips_validate(self, service, mock_db):
        scope = make_scope(1)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=scope))
        data = ComplianceScopeUpdate(description="only description")

        with patch("app.services.compliance_scope_service.invalidate_scope_cache"), \
             patch.object(ComplianceScopeService, "_validate_scope_value") as validate:
            result = await service.update_scope(1, data)

        assert result is scope
        validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_value_raises(self, service, mock_db):
        scope = make_scope(1)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=scope))
        data = ComplianceScopeUpdate(scope_type="ip_cidr", scope_value="192.168.1.0/33")

        with pytest.raises(ValueError):
            await service.update_scope(1, data)


# ===========================================================================
# delete_scope / toggle_scope
# ===========================================================================

class TestDeleteScope:
    @pytest.mark.asyncio
    async def test_found(self, service, mock_db):
        scope = make_scope(1)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=scope))
        with patch("app.services.compliance_scope_service.invalidate_scope_cache") as inval:
            assert await service.delete_scope(1) is True
        mock_db.delete.assert_called_once_with(scope)
        inval.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.delete_scope(99) is False
        mock_db.delete.assert_not_called()


class TestToggleScope:
    @pytest.mark.asyncio
    async def test_found_flips_status(self, service, mock_db):
        scope = make_scope(1, is_active=True)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=scope))
        with patch("app.services.compliance_scope_service.invalidate_scope_cache") as inval:
            result = await service.toggle_scope(1)
        assert result is scope
        assert scope.is_active is False
        inval.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.toggle_scope(99) is None


# ===========================================================================
# _validate_scope_value
# ===========================================================================

class TestValidateScopeValue:
    def test_empty_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ComplianceScopeService._validate_scope_value("ip_cidr", "")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            ComplianceScopeService._validate_scope_value("ip_cidr", "   ")

    def test_ip_cidr_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr", "192.168.1.0/24") is None

    def test_ip_cidr_broad_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr", "10.0.0.0/16") is None

    def test_ip_cidr_full_range_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr", "0.0.0.0/0") is None

    def test_ip_cidr_class_a_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr", "10.0.0.0/8") is None

    def test_ip_cidr_host_route_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr", "192.168.1.5/32") is None

    def test_ip_cidr_prefix_too_large(self):
        with pytest.raises(ValueError, match="Invalid IP CIDR format"):
            ComplianceScopeService._validate_scope_value("ip_cidr", "192.168.1.0/33")

    def test_ip_cidr_prefix_negative(self):
        with pytest.raises(ValueError, match="Invalid IP CIDR format"):
            ComplianceScopeService._validate_scope_value("ip_cidr", "192.168.1.0/-1")

    def test_ip_cidr_prefix_non_integer(self):
        with pytest.raises(ValueError, match="Invalid IP CIDR format"):
            ComplianceScopeService._validate_scope_value("ip_cidr", "192.168.1.0/abc")

    def test_ip_cidr_missing_prefix(self):
        with pytest.raises(ValueError, match="Invalid IP CIDR format"):
            ComplianceScopeService._validate_scope_value("ip_cidr", "192.168.1.0")

    def test_ip_cidr_invalid(self):
        with pytest.raises(ValueError, match="Invalid IP CIDR format"):
            ComplianceScopeService._validate_scope_value("ip_cidr", "999.999.999.999/24")

    def test_ip_range_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_range", "0.0.0.1-255") is None

    def test_ip_range_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid IP range format"):
            ComplianceScopeService._validate_scope_value("ip_range", "192.168.1.1")

    def test_ip_range_start_greater_than_end(self):
        with pytest.raises(ValueError, match="greater than end"):
            ComplianceScopeService._validate_scope_value("ip_range", "0.0.0.255-1")

    def test_ip_range_invalid_ip(self):
        with pytest.raises(ValueError, match="Invalid IP range"):
            ComplianceScopeService._validate_scope_value("ip_range", "999.999.999.999-1")

    def test_ip_range_end_exceeds_255(self):
        with pytest.raises(ValueError, match="exceeds 255"):
            ComplianceScopeService._validate_scope_value("ip_range", "192.168.1.1-256")

    def test_mac_prefix_valid(self):
        assert ComplianceScopeService._validate_scope_value("mac_prefix_arp", "AA:BB:CC") is None

    def test_mac_prefix_too_few_segments(self):
        with pytest.raises(ValueError, match="3-5 segments"):
            ComplianceScopeService._validate_scope_value("mac_prefix_ipguard", "AA:BB")

    def test_mac_prefix_too_many_segments(self):
        with pytest.raises(ValueError, match="3-5 segments"):
            ComplianceScopeService._validate_scope_value("mac_prefix_arp", "AA:BB:CC:DD:EE:FF")

    def test_mac_prefix_invalid_segment(self):
        with pytest.raises(ValueError, match="Invalid MAC prefix segment"):
            ComplianceScopeService._validate_scope_value("mac_prefix_arp", "AA:GG:CC")

    def test_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown scope type"):
            ComplianceScopeService._validate_scope_value("bogus", "whatever")

    def test_ip_cidr_any_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr_any", "192.168.1.0/24") is None

    def test_ip_cidr_any_broad_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr_any", "10.0.0.0/16") is None

    def test_ip_cidr_any_host_route_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_cidr_any", "192.168.1.5/32") is None

    def test_ip_cidr_any_prefix_invalid(self):
        with pytest.raises(ValueError, match="Invalid IP CIDR format"):
            ComplianceScopeService._validate_scope_value("ip_cidr_any", "192.168.1.0/33")

    def test_ip_cidr_any_invalid(self):
        with pytest.raises(ValueError, match="Invalid IP CIDR format"):
            ComplianceScopeService._validate_scope_value("ip_cidr_any", "999.999.999.999/24")

    def test_ip_range_any_valid(self):
        assert ComplianceScopeService._validate_scope_value("ip_range_any", "0.0.0.1-255") is None

    def test_ip_range_any_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid IP range format"):
            ComplianceScopeService._validate_scope_value("ip_range_any", "192.168.1.1")

    def test_mac_prefix_any_valid(self):
        assert ComplianceScopeService._validate_scope_value("mac_prefix_any", "AA:BB:CC") is None

    def test_mac_prefix_any_too_few_segments(self):
        with pytest.raises(ValueError, match="3-5 segments"):
            ComplianceScopeService._validate_scope_value("mac_prefix_any", "AA:BB")


class TestSchemaAcceptsOrScopeTypes:
    def test_or_scope_types_accepted(self):
        for st in ("ip_cidr_any", "ip_range_any", "mac_prefix_any"):
            data = ComplianceScopeCreate(scope_type=st, scope_value="x")
            assert data.scope_type == st

    def test_unknown_type_rejected(self):
        with pytest.raises(ValueError):
            ComplianceScopeCreate(scope_type="bogus", scope_value="x")