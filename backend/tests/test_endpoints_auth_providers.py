"""6C HTTP API endpoint layer — /api/v1/auth/providers integration tests.

Covers authentication-provider CRUD plus the public ``/available`` listing.
Provider creation is exercised with the always-registered ``local`` type, and
the LDAP config-preservation branch is covered on update.
"""
import pytest

from app.models.auth_config import AuthConfig


def _make_provider(**overrides) -> AuthConfig:
    defaults = dict(
        name="feishu",
        provider_type="oauth_feishu",
        config={"app_id": "x"},
        enabled=True,
        priority=100,
        description=None,
        created_by="testadmin",
    )
    defaults.update(overrides)
    return AuthConfig(**defaults)


async def _seed(db, *providers) -> None:
    for p in providers:
        db.add(p)
    await db.commit()


class TestAvailableProviders:
    @pytest.mark.asyncio
    async def test_local_always_present(self, api_db, api_client):
        resp = await api_client.get("/api/v1/auth/providers/available")
        assert resp.status_code == 200
        data = resp.json()
        assert any(p["id"] == "local" for p in data)

    @pytest.mark.asyncio
    async def test_enabled_providers_listed(self, api_db, api_client):
        await _seed(api_db, _make_provider(provider_type="ldap", name="Corp LDAP", enabled=True))
        resp = await api_client.get("/api/v1/auth/providers/available")
        assert resp.status_code == 200
        data = resp.json()
        assert any(p["provider_type"] == "ldap" for p in data)


class TestListProviders:
    @pytest.mark.asyncio
    async def test_empty(self, api_db, api_client):
        resp = await api_client.get("/api/v1/auth/providers")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_lists_providers(self, api_db, api_client):
        await _seed(api_db, _make_provider())
        resp = await api_client.get("/api/v1/auth/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "feishu"


class TestCreateProvider:
    @pytest.mark.asyncio
    async def test_create_local(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/auth/providers",
            json={"name": "Local", "provider_type": "local", "config": {},
                  "enabled": True, "priority": 1},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Local"
        assert resp.json()["provider_type"] == "local"

    @pytest.mark.asyncio
    async def test_unsupported_type_rejected(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/auth/providers",
            json={"name": "X", "provider_type": "nonexistent", "config": {}},
        )
        assert resp.status_code == 400
        assert "Unsupported provider type" in resp.json()["detail"]


class TestGetProvider:
    @pytest.mark.asyncio
    async def test_found(self, api_db, api_client):
        p = _make_provider()
        await _seed(api_db, p)
        resp = await api_client.get(f"/api/v1/auth/providers/{p.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "feishu"

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.get("/api/v1/auth/providers/9999")
        assert resp.status_code == 404


class TestUpdateProvider:
    @pytest.mark.asyncio
    async def test_update_name(self, api_db, api_client):
        p = _make_provider()
        await _seed(api_db, p)
        resp = await api_client.put(
            f"/api/v1/auth/providers/{p.id}",
            json={"name": "renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

    @pytest.mark.asyncio
    async def test_ldap_bind_password_preserved(self, api_db, api_client):
        p = _make_provider(provider_type="ldap", config={"bind_password": "secret"})
        await _seed(api_db, p)
        resp = await api_client.put(
            f"/api/v1/auth/providers/{p.id}",
            json={"config": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["bind_password"] == "secret"


class TestDeleteProvider:
    @pytest.mark.asyncio
    async def test_delete(self, api_db, api_client):
        p = _make_provider()
        await _seed(api_db, p)
        resp = await api_client.delete(f"/api/v1/auth/providers/{p.id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.delete("/api/v1/auth/providers/9999")
        assert resp.status_code == 404