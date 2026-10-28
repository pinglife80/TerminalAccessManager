"""6C HTTP API endpoint layer — /api/v1/logs integration tests.

Covers audit-log listing, search (with cursor pagination), and CSV export,
exercising both the route wiring and ``TerminalService`` audit-log queries.
"""
from datetime import datetime

import pytest

from app.models.log import AuditLog


def _make_log(**overrides) -> AuditLog:
    defaults = dict(
        username="admin",
        action="login",
        resource_type="system",
        resource_id=None,
        resource_name=None,
        details='{"message": "test"}',
        ip_address="10.0.0.1",
        timestamp=datetime(2026, 8, 20, 12, 0, 0),
    )
    defaults.update(overrides)
    return AuditLog(**defaults)


async def _seed(db, *logs) -> None:
    for l in logs:
        db.add(l)
    await db.commit()


class TestSearchAuditLogs:
    @pytest.mark.asyncio
    async def test_filter_by_username(self, api_db, api_client):
        await _seed(
            api_db,
            _make_log(username="alice", action="login"),
            _make_log(username="bob", action="login"),
        )
        resp = await api_client.get("/api/v1/logs/search?username=alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_filter_by_action(self, api_db, api_client):
        await _seed(
            api_db,
            _make_log(action="login"),
            _make_log(action="export_audit_logs"),
        )
        resp = await api_client.get("/api/v1/logs/search?action=login")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["action"] == "login"

    @pytest.mark.asyncio
    async def test_keyword_search(self, api_db, api_client):
        await _seed(
            api_db,
            _make_log(username="alice", details='{"message": "blocked 10.9.9.9"}'),
            _make_log(username="bob", details='{"message": "other"}'),
        )
        resp = await api_client.get("/api/v1/logs/search?search=10.9.9.9")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_keyset_pagination_cursor(self, api_db, api_client):
        logs = [
            _make_log(
                action=f"action_{i}",
                timestamp=datetime(2026, 8, 20, 12, 0, i),
                ip_address=f"10.0.0.{i}",
            )
            for i in range(3)
        ]
        await _seed(api_db, *logs)

        first = await api_client.get("/api/v1/logs/search?limit=2&skip=0")
        first_data = first.json()
        assert first_data["total"] == 3
        assert len(first_data["items"]) == 2
        assert first_data["next_cursor"] is not None

        second = await api_client.get(
            f"/api/v1/logs/search?limit=2&cursor={first_data['next_cursor']}"
        )
        second_data = second.json()
        assert len(second_data["items"]) == 1
        assert second_data["items"][0]["action"] == "action_0"  # oldest


class TestExportAuditLogs:
    @pytest.mark.asyncio
    async def test_export_csv(self, api_db, api_client):
        await _seed(
            api_db,
            _make_log(username="alice", action="login", ip_address="10.1.1.1"),
        )
        resp = await api_client.get("/api/v1/logs/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "audit_logs.csv" in resp.headers["content-disposition"]
        body = resp.text
        assert "Username" in body
        assert "alice" in body
        assert "10.1.1.1" in body