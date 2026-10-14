"""6C HTTP API endpoint layer — /api/v1/stats integration tests.

Covers the dashboard statistics endpoint and the system-status endpoint, both
of which aggregate over ``Terminal`` / ``Blacklist`` / ``DataSource`` rows via
``TerminalService.get_stats()`` / ``get_system_status()``.
"""
from datetime import datetime

import pytest

from app.models.blacklist import Blacklist
from app.models.data_source import DataSource
from app.models.terminal import Terminal


def _make_terminal(**overrides) -> Terminal:
    defaults = dict(
        ip_address="192.168.1.100",
        mac_address="AA:BB:CC:DD:EE:FF",
        mac_address_normalized="AABBCCDDEEFF",
        status="unblocked",
        source="arp",
        source_tag="arp_lab",
        compliance_status="unknown",
        timestamp=datetime(2026, 8, 20, 12, 0, 0),
    )
    defaults.update(overrides)
    return Terminal(**defaults)


def _make_arp_source(tag="arp_lab", enabled=True, last_sync_status=None) -> DataSource:
    return DataSource(
        name=f"source-{tag}",
        type="arp_ssh",
        tag=tag,
        config={},
        enabled=enabled,
        last_sync_status=last_sync_status,
    )


def _make_blacklist(**overrides) -> Blacklist:
    defaults = dict(
        ip_address="10.0.0.1",
        mac_address="AA:BB:CC:DD:EE:FF",
        mac_address_normalized="AABBCCDDEEFF",
        reason="non-compliant",
        blocked_by="system",
        blocked_at=datetime(2026, 8, 20, 12, 0, 0),
        auto_unblocked=False,
    )
    defaults.update(overrides)
    return Blacklist(**defaults)


async def _seed(db, *objs) -> None:
    for o in objs:
        db.add(o)
    await db.commit()


class TestGetDashboardStats:
    @pytest.mark.asyncio
    async def test_empty_returns_zeros(self, api_db, api_client):
        resp = await api_client.get("/api/v1/stats/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["blocked"] == 0
        assert data["non_compliant"] == 0
        assert data["bypass"] == 0

    @pytest.mark.asyncio
    async def test_total_counts_only_enabled_arp_terminals(self, api_db, api_client):
        # Only terminals belonging to *enabled* ARP sources are counted.
        await _seed(
            api_db,
            _make_arp_source("arp_enabled", enabled=True),
            _make_arp_source("arp_disabled", enabled=False),
            _make_terminal(ip_address="192.168.1.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001", source_tag="arp_enabled"),
            _make_terminal(ip_address="192.168.1.2", mac_address="AA:00:00:00:00:02",
                           mac_address_normalized="AA0000000002", source_tag="arp_enabled"),
            _make_terminal(ip_address="192.168.1.3", mac_address="AA:00:00:00:00:03",
                           mac_address_normalized="AA0000000003", source_tag="arp_disabled"),
        )
        resp = await api_client.get("/api/v1/stats/")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    @pytest.mark.asyncio
    async def test_blocked_counts_distinct_active_ips(self, api_db, api_client):
        await _seed(
            api_db,
            # Two entries sharing one active IP -> counts once.
            _make_blacklist(ip_address="10.0.0.1", mac_address="AA:00:00:00:00:01",
                            mac_address_normalized="AA0000000001", firewall_tag="fw1"),
            _make_blacklist(ip_address="10.0.0.1", mac_address="AA:00:00:00:00:02",
                            mac_address_normalized="AA0000000002", firewall_tag="fw2"),
            _make_blacklist(ip_address="10.0.0.2", mac_address="AA:00:00:00:00:03",
                            mac_address_normalized="AA0000000003"),
            # Auto-unblocked -> not counted.
            _make_blacklist(ip_address="10.0.0.3", mac_address="AA:00:00:00:00:04",
                            mac_address_normalized="AA0000000004", auto_unblocked=True),
        )
        resp = await api_client.get("/api/v1/stats/")
        assert resp.status_code == 200
        assert resp.json()["blocked"] == 2

    @pytest.mark.asyncio
    async def test_non_compliant_counts_all_non_compliant_terminals(self, api_db, api_client):
        await _seed(
            api_db,
            _make_arp_source("arp_lab", enabled=True),
            # non_compliant + blocked -> counted.
            _make_terminal(ip_address="192.168.1.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001",
                           compliance_status="non_compliant", status="blocked"),
            # non_compliant + unblocked -> also counted (compliance axis · terminal count).
            _make_terminal(ip_address="192.168.1.2", mac_address="AA:00:00:00:00:02",
                           mac_address_normalized="AA0000000002",
                           compliance_status="non_compliant", status="unblocked"),
        )
        resp = await api_client.get("/api/v1/stats/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["non_compliant"] == 2
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_bypass_terminal_counted_as_whitelisted(self, api_db, api_client):
        await _seed(
            api_db,
            _make_arp_source("arp_lab", enabled=True),
            _make_terminal(ip_address="192.168.1.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001", compliance_status="bypass"),
        )
        resp = await api_client.get("/api/v1/stats/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["whitelisted"] == 1
        assert data["bypass"] == 1


class TestGetSystemStatus:
    @pytest.mark.asyncio
    async def test_no_sources_defaults(self, api_db, api_client):
        resp = await api_client.get("/api/v1/stats/system-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["backend_api"] == "connected"
        assert data["database"] == "healthy"
        # No Sangfor source -> not connected + explanatory error.
        assert data["sangfor"]["connected"] is False
        assert "No Sangfor" in data["sangfor"]["error"]
        # No ARP source -> pending.
        assert data["network_scanner"] == "pending"

    @pytest.mark.asyncio
    async def test_arp_synced_sets_network_scanner_connected(self, api_db, api_client):
        await _seed(api_db, _make_arp_source("arp_lab", enabled=True, last_sync_status="success"))
        resp = await api_client.get("/api/v1/stats/system-status")
        assert resp.status_code == 200
        assert resp.json()["network_scanner"] == "connected"