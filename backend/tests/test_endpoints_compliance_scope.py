"""6C HTTP API endpoint layer — /api/v1/compliance-scope integration tests.

Thin wrappers over ``ComplianceScopeService``; these verify route wiring,
status codes, and the full request/response contract against a real DB.
"""
import pytest

from app.models.compliance_scope import ComplianceScope


def _make_scope(**overrides) -> ComplianceScope:
    defaults = dict(
        scope_type="ip_cidr",
        scope_value="192.168.0.0/24",
        description="lab subnet",
        is_active=True,
        created_by="testadmin",
    )
    defaults.update(overrides)
    return ComplianceScope(**defaults)


async def _seed(db, *scopes) -> None:
    for s in scopes:
        db.add(s)
    await db.commit()


class TestListScopes:
    @pytest.mark.asyncio
    async def test_empty(self, api_db, api_client):
        resp = await api_client.get("/api/v1/compliance-scope")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"items": [], "total": 0}

    @pytest.mark.asyncio
    async def test_returns_scopes(self, api_db, api_client):
        await _seed(api_db, _make_scope(), _make_scope(scope_type="mac_prefix_arp",
                                                       scope_value="AA:BB:CC"))
        resp = await api_client.get("/api/v1/compliance-scope")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2


class TestCreateScope:
    @pytest.mark.asyncio
    async def test_create_valid_cidr(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/compliance-scope",
            json={"scope_type": "ip_cidr", "scope_value": "10.0.0.0/24", "description": "x"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["scope_type"] == "ip_cidr"
        assert body["scope_value"] == "10.0.0.0/24"
        assert body["is_active"] is True
        assert body["created_by"] == "testadmin"

    @pytest.mark.asyncio
    async def test_create_invalid_value_rejected(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/compliance-scope",
            json={"scope_type": "ip_range", "scope_value": "10.0.0.300-400"},
        )
        assert resp.status_code == 400
        assert "range" in resp.json()["detail"]


class TestGetScope:
    @pytest.mark.asyncio
    async def test_found(self, api_db, api_client):
        s = _make_scope()
        await _seed(api_db, s)
        resp = await api_client.get(f"/api/v1/compliance-scope/{s.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == s.id

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.get("/api/v1/compliance-scope/9999")
        assert resp.status_code == 404


class TestUpdateScope:
    @pytest.mark.asyncio
    async def test_update_is_active(self, api_db, api_client):
        s = _make_scope()
        await _seed(api_db, s)
        resp = await api_client.put(
            f"/api/v1/compliance-scope/{s.id}",
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.put(
            "/api/v1/compliance-scope/9999",
            json={"is_active": False},
        )
        assert resp.status_code == 404


class TestDeleteScope:
    @pytest.mark.asyncio
    async def test_delete(self, api_db, api_client):
        s = _make_scope()
        await _seed(api_db, s)
        resp = await api_client.delete(f"/api/v1/compliance-scope/{s.id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.delete("/api/v1/compliance-scope/9999")
        assert resp.status_code == 404


class TestToggleScope:
    @pytest.mark.asyncio
    async def test_toggle_flips_active(self, api_db, api_client):
        s = _make_scope(is_active=True)
        await _seed(api_db, s)
        resp = await api_client.post(f"/api/v1/compliance-scope/{s.id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.post("/api/v1/compliance-scope/9999/toggle")
        assert resp.status_code == 404