"""6C HTTP API endpoint layer — /api/v1/blacklist integration tests."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.blacklist import Blacklist
from app.models.data_source import DataSource
from app.models.terminal import Terminal


def _make_blacklist(**overrides) -> Blacklist:
    defaults = dict(
        ip_address="192.168.1.100",
        mac_address="AA:BB:CC:DD:EE:FF",
        mac_address_normalized="AABBCCDDEEFF",
        firewall_tag="fw1",
        source_tag="arp_lab",
        blocked_by="system",
        reason="non-compliant",
        is_auto_blocked=True,
        auto_unblocked=False,
        blocked_at=datetime(2026, 8, 20, 12, 0, 0),
    )
    defaults.update(overrides)
    return Blacklist(**defaults)


async def _seed(db, *objs) -> None:
    for o in objs:
        db.add(o)
    await db.commit()


class TestBlacklistStats:
    @pytest.mark.asyncio
    async def test_empty(self, api_db, api_client):
        resp = await api_client.get("/api/v1/blacklist/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success_blocked"] == 0
        assert data["success_unblocked"] == 0
        assert data["pending_retry_unblock"] == 0

    @pytest.mark.asyncio
    async def test_success_blocked_counts_distinct_active_ips(self, api_db, api_client):
        await _seed(
            api_db,
            _make_blacklist(ip_address="10.0.0.1", mac_address="AA:00:00:00:00:01",
                            mac_address_normalized="AA0000000001"),
            _make_blacklist(ip_address="10.0.0.2", mac_address="AA:00:00:00:00:02",
                            mac_address_normalized="AA0000000002"),
            # Unblocked entry should NOT count toward success_blocked.
            _make_blacklist(ip_address="10.0.0.3", mac_address="AA:00:00:00:00:03",
                            mac_address_normalized="AA0000000003", auto_unblocked=True),
        )
        resp = await api_client.get("/api/v1/blacklist/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success_blocked"] == 2
        assert data["success_unblocked"] == 1


class TestListBlacklist:
    @pytest.mark.asyncio
    async def test_default_shows_only_active(self, api_db, api_client):
        await _seed(
            api_db,
            _make_blacklist(ip_address="10.0.0.1", mac_address="AA:00:00:00:00:01",
                            mac_address_normalized="AA0000000001"),
            _make_blacklist(ip_address="10.0.0.2", mac_address="AA:00:00:00:00:02",
                            mac_address_normalized="AA0000000002", auto_unblocked=True),
        )
        resp = await api_client.get("/api/v1/blacklist/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["ip_address"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_search_by_ip(self, api_db, api_client):
        await _seed(
            api_db,
            _make_blacklist(ip_address="172.16.0.1", mac_address="AA:00:00:00:00:01",
                            mac_address_normalized="AA0000000001"),
            _make_blacklist(ip_address="172.16.0.2", mac_address="AA:00:00:00:00:02",
                            mac_address_normalized="AA0000000002"),
        )
        resp = await api_client.get("/api/v1/blacklist/?search=172.16.0.1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["ip_address"] == "172.16.0.1"

    @pytest.mark.asyncio
    async def test_status_unblocked(self, api_db, api_client):
        await _seed(
            api_db,
            _make_blacklist(ip_address="10.0.0.1", mac_address="AA:00:00:00:00:01",
                            mac_address_normalized="AA0000000001"),
            _make_blacklist(ip_address="10.0.0.2", mac_address="AA:00:00:00:00:02",
                            mac_address_normalized="AA0000000002", auto_unblocked=True),
        )
        resp = await api_client.get("/api/v1/blacklist/?status=unblocked")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["ip_address"] == "10.0.0.2"


class TestCheckBlacklist:
    @pytest.mark.asyncio
    async def test_match_by_ip(self, api_db, api_client):
        await _seed(
            api_db,
            _make_blacklist(ip_address="10.0.0.1", mac_address="AA:00:00:00:00:01",
                            mac_address_normalized="AA0000000001", firewall_tag="fw1"),
        )
        resp = await api_client.post(
            "/api/v1/blacklist/check",
            json={"mac_addresses": [], "ip_addresses": ["10.0.0.1"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ip_address"] == "10.0.0.1"
        assert data[0]["firewall_tag"] == "fw1"

    @pytest.mark.asyncio
    async def test_match_by_mac_normalized(self, api_db, api_client):
        await _seed(
            api_db,
            _make_blacklist(mac_address="AA:BB:CC:DD:EE:FF", mac_address_normalized="AABBCCDDEEFF"),
        )
        resp = await api_client.post(
            "/api/v1/blacklist/check",
            json={"mac_addresses": ["aa:bb:cc:dd:ee:ff"], "ip_addresses": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["mac_address"] == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_no_match(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/blacklist/check",
            json={"mac_addresses": ["00:00:00:00:00:00"], "ip_addresses": ["1.2.3.4"]},
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestExportBlacklist:
    @pytest.mark.asyncio
    async def test_export_csv(self, api_db, api_client):
        await _seed(
            api_db,
            _make_blacklist(ip_address="10.1.1.1", mac_address="AA:BB:CC:DD:EE:FF",
                            mac_address_normalized="AABBCCDDEEFF"),
        )
        resp = await api_client.get("/api/v1/blacklist/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "blacklist.csv" in resp.headers["content-disposition"]
        body = resp.text
        assert "MAC Address" in body
        assert "AA:BB:CC:DD:EE:FF" in body
        assert "10.1.1.1" in body


class TestRetryUnblock:
    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.post("/api/v1/blacklist/9999/retry")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "条目不存在"

    @pytest.mark.asyncio
    async def test_already_unblocked(self, api_db, api_client):
        entry = _make_blacklist(auto_unblocked=True)
        await _seed(api_db, entry)
        resp = await api_client.post(f"/api/v1/blacklist/{entry.id}/retry")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "条目已解封"

    @pytest.mark.asyncio
    async def test_success(self, api_db, api_client):
        entry = _make_blacklist(
            ip_address="10.1.1.1",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
        )
        terminal = Terminal(
            ip_address="10.1.1.1",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            status="blocked",
            source="arp",
            source_tag="arp_lab",
            compliance_status="compliant",
            timestamp=datetime(2026, 8, 20, 12, 0, 0),
        )
        fw_source = DataSource(
            name="firewall1",
            type="sangfor",
            tag="fw1",
            config={"base_url": "https://fw", "username": "u", "password": "p",
                    "verify_ssl": True, "ca_bundle": ""},
            enabled=True,
        )
        await _seed(api_db, entry, terminal, fw_source)

        mock_svc = MagicMock()
        mock_svc.unblock_ip = AsyncMock(return_value={"code": 0})
        with patch("app.services.terminal_service.SangforService") as mock_svc_cls, \
             patch("app.services.terminal_service.decrypt_config", side_effect=lambda c: c):
            mock_svc_cls.get_cached_service = AsyncMock(return_value=mock_svc)
            resp = await api_client.post(f"/api/v1/blacklist/{entry.id}/retry")

        assert resp.status_code == 200
        assert resp.json() == {"success": True, "message": "解封成功"}

    @pytest.mark.asyncio
    async def test_non_compliant_terminal_rejected(self, api_db, api_client):
        entry = _make_blacklist(
            ip_address="10.1.1.1",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
        )
        terminal = Terminal(
            ip_address="10.1.1.1",
            mac_address="AA:BB:CC:DD:EE:FF",
            mac_address_normalized="AABBCCDDEEFF",
            status="blocked",
            source="arp",
            source_tag="arp_lab",
            compliance_status="non_compliant",
            timestamp=datetime(2026, 8, 20, 12, 0, 0),
        )
        fw_source = DataSource(
            name="firewall1", type="sangfor", tag="fw1",
            config={"base_url": "https://fw", "username": "u", "password": "p"},
            enabled=True,
        )
        await _seed(api_db, entry, terminal, fw_source)

        with patch("app.services.terminal_service.SangforService"):
            resp = await api_client.post(f"/api/v1/blacklist/{entry.id}/retry")

        assert resp.status_code == 400
        assert "不合规" in resp.json()["detail"]