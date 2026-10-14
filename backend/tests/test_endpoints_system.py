"""6C HTTP API endpoint layer — /api/v1/system integration tests.

Covers:
- system status / config read endpoints
- health probe (db/redis dependency verification, incl. failure paths)
- manual firewall reconciliation trigger (service mocked; incl. failure path)
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.endpoints.system import get_system_status
from app.core.config import settings


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fake_db_connect(db_ok: bool, error: str = "db down"):
    @asynccontextmanager
    async def _connect():
        conn = AsyncMock()
        if db_ok:
            conn.execute = AsyncMock(return_value=None)
        else:
            conn.execute = AsyncMock(side_effect=Exception(error))
        yield conn

    return _connect


def _fake_engine(db_ok: bool, error: str = "db down"):
    engine = MagicMock()
    engine.connect = _fake_db_connect(db_ok, error)
    return engine


def _fake_redis(redis_ok: bool, error: str = "redis down"):
    client = AsyncMock()
    if redis_ok:
        client.ping = AsyncMock(return_value=True)
    else:
        client.ping = AsyncMock(side_effect=Exception(error))
    client.close = AsyncMock(return_value=None)
    return client


class TestSystemStatus:
    @pytest.mark.asyncio
    async def test_status_returns_metadata(self, api_db, api_client):
        resp = await api_client.get("/api/v1/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data) >= {"uptime", "database", "version", "environment", "platform", "python_version"}
        assert data["database"] == "healthy"

    @pytest.mark.asyncio
    async def test_status_db_probe_unhealthy_branch(self, mock_async_session):
        # Direct-call to cover the /status DB-probe failure branch (the HTTP
        # path above always relies on a working in-memory DB).
        mock_async_session.execute = AsyncMock(side_effect=Exception("db down"))
        result = await get_system_status(
            db=mock_async_session,
            current_user=SimpleNamespace(id=1, username="testadmin", is_superuser=True),
        )
        assert result["database"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_config_returns_safe_values(self, api_db, api_client):
        resp = await api_client.get("/api/v1/system/config")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data) >= {"environment", "version", "debug", "log_level", "email_enabled", "metrics_enabled"}


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_all_dependencies_healthy(self, api_db, api_client):
        fake_engine = _fake_engine(db_ok=True)
        redis_client = _fake_redis(redis_ok=True)

        with patch("app.api.v1.endpoints.system.engine", fake_engine), \
             patch("redis.asyncio.from_url", return_value=redis_client):
            resp = await api_client.get("/api/v1/system/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["db"] == "ok"
        assert data["redis"] == "ok"
        assert data["version"] == settings.VERSION
        assert data["environment"] == settings.ENVIRONMENT

    @pytest.mark.asyncio
    async def test_db_down_non_production_details_error(self, api_db, api_client):
        fake_engine = _fake_engine(db_ok=False, error="db down")
        redis_client = _fake_redis(redis_ok=True)

        with patch("app.api.v1.endpoints.system.engine", fake_engine), \
             patch("redis.asyncio.from_url", return_value=redis_client):
            resp = await api_client.get("/api/v1/system/health")

        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["db"] == "error: db down"
        assert data["redis"] == "ok"

    @pytest.mark.asyncio
    async def test_db_down_production_hides_error_detail(self, api_db, api_client):
        fake_engine = _fake_engine(db_ok=False, error="db down")
        redis_client = _fake_redis(redis_ok=True)

        with patch("app.api.v1.endpoints.system.engine", fake_engine), \
             patch("redis.asyncio.from_url", return_value=redis_client), \
             patch.object(settings, "ENVIRONMENT", "production"):
            resp = await api_client.get("/api/v1/system/health")

        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["db"] == "error"
        assert data["redis"] == "ok"

    @pytest.mark.asyncio
    async def test_redis_down_non_production_details_error(self, api_db, api_client):
        fake_engine = _fake_engine(db_ok=True)
        redis_client = _fake_redis(redis_ok=False, error="redis down")

        with patch("app.api.v1.endpoints.system.engine", fake_engine), \
             patch("redis.asyncio.from_url", return_value=redis_client):
            resp = await api_client.get("/api/v1/system/health")

        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["db"] == "ok"
        assert data["redis"] == "error: redis down"

    @pytest.mark.asyncio
    async def test_redis_down_production_hides_error_detail(self, api_db, api_client):
        fake_engine = _fake_engine(db_ok=True)
        redis_client = _fake_redis(redis_ok=False, error="redis down")

        with patch("app.api.v1.endpoints.system.engine", fake_engine), \
             patch("redis.asyncio.from_url", return_value=redis_client), \
             patch.object(settings, "ENVIRONMENT", "production"):
            resp = await api_client.get("/api/v1/system/health")

        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["db"] == "ok"
        assert data["redis"] == "error"

    @pytest.mark.asyncio
    async def test_both_down_unhealthy(self, api_db, api_client):
        fake_engine = _fake_engine(db_ok=False, error="db down")
        redis_client = _fake_redis(redis_ok=False, error="redis down")

        with patch("app.api.v1.endpoints.system.engine", fake_engine), \
             patch("redis.asyncio.from_url", return_value=redis_client):
            resp = await api_client.get("/api/v1/system/health")

        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["db"] == "error: db down"
        assert data["redis"] == "error: redis down"


class TestFirewallReconciliation:
    @pytest.mark.asyncio
    async def test_triggers_reconciliation_and_caches(self, api_db, api_client):
        mock_recon = AsyncMock()
        mock_recon.reconcile = AsyncMock(return_value={"created": 1, "reblocked": 0})

        with patch(
            "app.services.firewall_reconciliation_service.FirewallReconciliationService",
            return_value=mock_recon,
        ), patch("app.main._cache_reconcile_result", new=AsyncMock()) as cache_fn:
            resp = await api_client.post("/api/v1/system/firewall-reconciliation")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "Firewall reconciliation completed"
        assert body["created"] == 1
        mock_recon.reconcile.assert_awaited_once()
        cache_fn.assert_awaited_once_with({"created": 1, "reblocked": 0})

    @pytest.mark.asyncio
    async def test_reconcile_failure_propagates(self, api_db, api_client):
        # The endpoint has no error handling: a reconcile failure must surface
        # (ASGITransport re-raises app exceptions by default in our test client).
        mock_recon = AsyncMock()
        mock_recon.reconcile = AsyncMock(side_effect=RuntimeError("reconcile boom"))

        with patch(
            "app.services.firewall_reconciliation_service.FirewallReconciliationService",
            return_value=mock_recon,
        ), patch("app.main._cache_reconcile_result", new=AsyncMock()) as cache_fn:
            with pytest.raises(RuntimeError, match="reconcile boom"):
                await api_client.post("/api/v1/system/firewall-reconciliation")

        cache_fn.assert_not_awaited()