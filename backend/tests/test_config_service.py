"""
Unit tests for the system configuration service.

Redis is mocked via conftest's autouse get_redis_client patch (in-memory dict),
and the DB session is the shared AsyncSession mock factory.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models.system_config import SystemConfig
from app.schemas.system_config import (
    ConfigValueType,
    ConfigUpdateResult,
    SystemConfigUpdate,
)
from app.services import config_service as cs
from app.services.config_service import (
    ConfigService,
    _cache_key,
    _parse_value,
    get_config_value,
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


def make_config(key="k", value="v", value_type="string", is_readonly=False,
                category="general", id_=1):
    c = MagicMock(spec=SystemConfig)
    c.id = id_
    c.key = key
    c.value = value
    c.value_type = value_type
    c.is_readonly = is_readonly
    c.category = category
    c.description = None
    c.updated_by = None
    c.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    c.updated_at = datetime(2024, 1, 1, tzinfo=UTC)
    return c


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(mock_async_session):
    return mock_async_session


@pytest.fixture
def service(mock_db):
    return ConfigService(mock_db)


# ===========================================================================
# _parse_value
# ===========================================================================

class TestParseValue:
    def test_int(self):
        assert _parse_value("42", ConfigValueType.INT) == 42

    def test_bool_true(self):
        assert _parse_value("true", ConfigValueType.BOOL) is True

    def test_bool_false(self):
        assert _parse_value("0", ConfigValueType.BOOL) is False

    def test_json(self):
        assert _parse_value('{"a": 1}', ConfigValueType.JSON) == {"a": 1}

    def test_string_fallback(self):
        assert _parse_value("hello", "string") == "hello"


# ===========================================================================
# _validate_value
# ===========================================================================

class TestValidateValue:
    def test_int_valid(self, service):
        assert service._validate_value("5", ConfigValueType.INT) is None

    def test_int_negative(self, service):
        assert service._validate_value("-1", ConfigValueType.INT) == "Value must be a non-negative integer"

    def test_int_invalid(self, service):
        assert service._validate_value("abc", ConfigValueType.INT) is not None

    def test_bool_valid(self, service):
        assert service._validate_value("true", ConfigValueType.BOOL) is None

    def test_bool_invalid(self, service):
        assert service._validate_value("maybe", ConfigValueType.BOOL) == "Value must be true/false"

    def test_json_valid(self, service):
        assert service._validate_value('{"a": 1}', ConfigValueType.JSON) is None

    def test_json_invalid(self, service):
        # json.JSONDecodeError is a ValueError subclass, so it hits the ValueError branch
        assert service._validate_value("{bad", ConfigValueType.JSON) is not None


# ===========================================================================
# get / get_typed / get_value
# ===========================================================================

class TestGet:
    @pytest.mark.asyncio
    async def test_redis_hit(self, service, mock_db, mock_redis):
        mock_redis._data[_cache_key("foo")] = "bar"
        assert await service.get("foo") == "bar"

    @pytest.mark.asyncio
    async def test_redis_hit_bytes_decoded(self, service, mock_db, mock_redis):
        mock_redis._data[_cache_key("foo")] = b"bar"
        assert await service.get("foo") == "bar"

    @pytest.mark.asyncio
    async def test_db_hit(self, service, mock_db, mock_redis):
        config = make_config(key="foo", value="dbval")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=config))
        assert await service.get("foo") == "dbval"
        # value cached into redis
        assert mock_redis._data.get(_cache_key("foo")) == "dbval"

    @pytest.mark.asyncio
    async def test_env_fallback(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        result = await service.get("max_login_attempts")
        assert result == str(settings.MAX_LOGIN_ATTEMPTS)

    @pytest.mark.asyncio
    async def test_none_when_no_source(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.get("no_such_key_anywhere") is None

    @pytest.mark.asyncio
    async def test_redis_exception_falls_through_to_db(self, service, mock_db):
        config = make_config(key="foo", value="dbval")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=config))
        with patch("app.services.config_service._get_redis", AsyncMock(side_effect=Exception("boom"))):
            assert await service.get("foo") == "dbval"


class TestGetTyped:
    @pytest.mark.asyncio
    async def test_default_when_none(self, service, mock_db):
        with patch.object(service, "get", AsyncMock(return_value=None)):
            assert await service.get_typed("foo", default=42) == 42

    @pytest.mark.asyncio
    async def test_int_parse(self, service, mock_db):
        with patch.object(service, "get", AsyncMock(return_value="7")):
            mock_db.execute = AsyncMock(return_value=make_result(scalar=ConfigValueType.INT))
            assert await service.get_typed("foo", default=0) == 7

    @pytest.mark.asyncio
    async def test_parse_error_returns_default(self, service, mock_db):
        with patch.object(service, "get", AsyncMock(return_value="abc")):
            mock_db.execute = AsyncMock(return_value=make_result(scalar=ConfigValueType.INT))
            assert await service.get_typed("foo", default=0) == 0


class TestGetValue:
    @pytest.mark.asyncio
    async def test_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar="v"))
        assert await service.get_value("foo") == "v"

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.get_value("foo") is None


# ===========================================================================
# set / batch_update
# ===========================================================================

class TestSet:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        r = await service.set("foo", "bar")
        assert r.success is False
        assert "not found" in r.message

    @pytest.mark.asyncio
    async def test_readonly(self, service, mock_db):
        config = make_config(key="foo", value="old", is_readonly=True)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=config))
        r = await service.set("foo", "bar")
        assert r.success is False
        assert "read-only" in r.message

    @pytest.mark.asyncio
    async def test_invalid_value(self, service, mock_db):
        config = make_config(key="foo", value="5", value_type="int")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=config))
        r = await service.set("foo", "abc")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        config = make_config(key="foo", value="5", value_type="int")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=config))
        r = await service.set("foo", "10", "admin")
        assert r.success is True
        assert config.value == "10"
        assert config.updated_by == "admin"
        mock_db.commit.assert_called_once()


class TestBatchUpdate:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        updates = [SystemConfigUpdate(key="nokey", value="x")]
        with patch.object(service, "set", AsyncMock()) as set_mock:
            results = await service.batch_update(updates, "admin")

        assert len(results) == 1
        assert results[0].success is False
        assert "not found" in results[0].message
        set_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_readonly(self, service, mock_db):
        config = make_config(key="k1", value="x", is_readonly=True)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=config))
        updates = [SystemConfigUpdate(key="k1", value="y")]
        with patch.object(service, "set", AsyncMock()) as set_mock:
            results = await service.batch_update(updates, "admin")

        assert len(results) == 1
        assert results[0].success is False
        assert "read-only" in results[0].message
        set_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_aborts(self, service, mock_db):
        config1 = make_config(key="k1", value="5", value_type="int")
        config2 = make_config(key="k2", value="x", value_type="int")
        mock_db.execute = AsyncMock(side_effect=[make_result(scalar=config1), make_result(scalar=config2)])

        updates = [
            SystemConfigUpdate(key="k1", value="10"),
            SystemConfigUpdate(key="k2", value="abc"),  # invalid int
        ]
        with patch.object(service, "set", AsyncMock()) as set_mock:
            results = await service.batch_update(updates, "admin")

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].key == "k2"
        set_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_valid_applies(self, service, mock_db):
        config = make_config(key="k1", value="5", value_type="int")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=config))

        updates = [
            SystemConfigUpdate(key="k1", value="10"),
            SystemConfigUpdate(key="k1", value="20"),
        ]
        with patch.object(service, "set", AsyncMock(return_value=ConfigUpdateResult(key="x", success=True))) as set_mock:
            results = await service.batch_update(updates, "admin")

        assert len(results) == 2
        assert all(r.success for r in results)
        assert set_mock.call_count == 2


# ===========================================================================
# seed_defaults
# ===========================================================================

class TestSeedDefaults:
    @pytest.mark.asyncio
    async def test_all_new_seeds_everything(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        count = await service.seed_defaults()
        assert count == len(ConfigService.DEFAULT_CONFIGS)
        mock_db.commit.assert_called_once()
        assert mock_db.add.call_count == len(ConfigService.DEFAULT_CONFIGS)

    @pytest.mark.asyncio
    async def test_all_existing_skips(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=object()))
        count = await service.seed_defaults()
        assert count == 0
        mock_db.commit.assert_not_called()
        mock_db.add.assert_not_called()


# ===========================================================================
# list_all / get_all_grouped
# ===========================================================================

class TestListAll:
    @pytest.mark.asyncio
    async def test_no_category(self, service, mock_db):
        config = make_config(key="foo", value="bar", category="general", value_type="string")
        mock_db.execute = AsyncMock(return_value=make_result(rows=[config]))
        result = await service.list_all()
        assert len(result) == 1
        assert result[0].key == "foo"

    @pytest.mark.asyncio
    async def test_with_category(self, service, mock_db):
        config = make_config(key="foo", value="bar", category="security")
        mock_db.execute = AsyncMock(return_value=make_result(rows=[config]))
        result = await service.list_all(category="security")
        assert len(result) == 1


class TestGetAllGrouped:
    @pytest.mark.asyncio
    async def test_returns_defaults_when_empty(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(rows=[]))
        resp = await service.get_all_grouped()
        assert resp.security.max_login_attempts == 5
        assert resp.compliance.block_time == "30d"
        assert resp.branding.app_name == "Terminal Access Manager"

    @pytest.mark.asyncio
    async def test_parses_value_type(self, service, mock_db):
        c = MagicMock()
        c.key = "max_login_attempts"
        c.value = "7"
        c.value_type = "int"
        with patch.object(service, "list_all", AsyncMock(return_value=[c])):
            resp = await service.get_all_grouped()
        assert resp.security.max_login_attempts == 7


# ===========================================================================
# _invalidate_all_cache
# ===========================================================================

class TestInvalidateAllCache:
    @pytest.mark.asyncio
    async def test_deletes_scanned_keys(self, service, mock_redis):
        async def fake_scan_iter(match=None):
            yield f"{cs.CONFIG_CACHE_PREFIX}a"
            yield f"{cs.CONFIG_CACHE_PREFIX}b"

        mock_redis.scan_iter = fake_scan_iter
        delete_mock = AsyncMock()
        mock_redis.delete = delete_mock

        result = await service._invalidate_all_cache()

        assert result is None
        assert delete_mock.await_count == 2


# ===========================================================================
# module-level get_config_value
# ===========================================================================

class TestModuleGetConfigValue:
    @pytest.mark.asyncio
    async def test_redis_hit_int(self, mock_redis):
        mock_redis._data[_cache_key("rate_limit_per_minute")] = "120"
        result = await get_config_value("rate_limit_per_minute", default=60)
        assert result == 120

    @pytest.mark.asyncio
    async def test_redis_hit_bool(self, mock_redis):
        mock_redis._data[_cache_key("allow_registration")] = "true"
        result = await get_config_value("allow_registration", default=False)
        assert result is True

    @pytest.mark.asyncio
    async def test_db_hit_int(self, mock_redis, mock_async_session):
        config = make_config(key="rate_limit_per_minute", value="120", value_type="int")
        mock_async_session.execute = AsyncMock(return_value=make_result(scalar=config))

        async def fake_get_db():
            yield mock_async_session

        with patch("app.core.database.get_db", side_effect=fake_get_db):
            result = await get_config_value("rate_limit_per_minute", default=60)

        assert result == 120
        # value cached into redis
        assert mock_redis._data.get(_cache_key("rate_limit_per_minute")) == "120"

    @pytest.mark.asyncio
    async def test_env_fallback(self, mock_redis, mock_async_session):
        with patch("app.core.database.get_db", side_effect=Exception("no db")):
            result = await get_config_value("max_login_attempts", default=5)
        assert result == settings.MAX_LOGIN_ATTEMPTS