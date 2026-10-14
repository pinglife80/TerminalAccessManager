"""6C HTTP API endpoint layer — /api/v1/whitelist integration tests."""
from datetime import datetime

import pytest

from app.models.whitelist import Whitelist


def _make_whitelist(**overrides) -> Whitelist:
    defaults = dict(
        mac_address="AA:BB:CC:DD:EE:FF",
        mac_address_normalized="AABBCCDDEEFF",
        ip_pattern=None,
        pattern_type="mac_only",
        comments="test entry",
        added_by="testadmin",
        created_at=datetime(2026, 8, 20, 12, 0, 0),
    )
    defaults.update(overrides)
    return Whitelist(**defaults)


async def _seed(db, *objs) -> None:
    for o in objs:
        db.add(o)
    await db.commit()


class TestListWhitelist:
    @pytest.mark.asyncio
    async def test_empty(self, api_db, api_client):
        resp = await api_client.get("/api/v1/whitelist/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_seeded(self, api_db, api_client):
        await _seed(
            api_db,
            _make_whitelist(mac_address="AA:00:00:00:00:01", mac_address_normalized="AA0000000001"),
            _make_whitelist(mac_address="AA:00:00:00:00:02", mac_address_normalized="AA0000000002"),
        )
        resp = await api_client.get("/api/v1/whitelist/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_search_by_comments(self, api_db, api_client):
        await _seed(
            api_db,
            _make_whitelist(mac_address="AA:00:00:00:00:01", mac_address_normalized="AA0000000001",
                            comments="production server"),
            _make_whitelist(mac_address="AA:00:00:00:00:02", mac_address_normalized="AA0000000002",
                            comments="dev machine"),
        )
        resp = await api_client.get("/api/v1/whitelist/?search=production")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["comments"] == "production server"


class TestAddWhitelist:
    @pytest.mark.asyncio
    async def test_add_mac_only(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/whitelist/",
            json={"mac_address": "AA:BB:CC:DD:EE:FF", "comments": "new whitelist"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["added"] == 1

    @pytest.mark.asyncio
    async def test_add_missing_comments_rejected(self, api_db, api_client):
        # WhitelistCreate requires `comments`.
        resp = await api_client.post(
            "/api/v1/whitelist/",
            json={"mac_address": "AA:BB:CC:DD:EE:FF"},
        )
        assert resp.status_code == 422


class TestDeleteWhitelist:
    @pytest.mark.asyncio
    async def test_delete_mac_only(self, api_db, api_client):
        await _seed(api_db, _make_whitelist())
        resp = await api_client.delete(
            "/api/v1/whitelist/", params={"identifier": "AA:BB:CC:DD:EE:FF"}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, api_db, api_client):
        resp = await api_client.delete(
            "/api/v1/whitelist/", params={"identifier": "00:11:22:33:44:55"}
        )
        assert resp.status_code == 404


class TestExportWhitelist:
    @pytest.mark.asyncio
    async def test_export_csv(self, api_db, api_client):
        await _seed(api_db, _make_whitelist())
        resp = await api_client.get("/api/v1/whitelist/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "whitelist.csv" in resp.headers["content-disposition"]
        body = resp.text
        assert "MAC Address" in body
        assert "AA:BB:CC:DD:EE:FF" in body


class TestImportWhitelist:
    @pytest.mark.asyncio
    async def test_invalid_extension_rejected(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/whitelist/import",
            files={"file": ("data.txt", b"not,allowed", "text/plain")},
            data={"mode": "skip"},
        )
        assert resp.status_code == 400
        assert "Invalid file extension" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_mode_rejected(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/whitelist/import",
            files={"file": ("data.csv", b"ID,MAC Address\n", "text/csv")},
            data={"mode": "merge"},
        )
        assert resp.status_code == 400
        assert "Invalid mode" in resp.json()["detail"]