"""6C HTTP API endpoint layer — /api/v1/terminals integration tests.

Each test seeds an in-memory SQLite database (via ``api_db``) and drives the
real FastAPI app (via ``api_client``) with a superuser auth override, exercising
both route wiring and the underlying ``TerminalService`` query code end-to-end.
"""
from datetime import datetime

import pytest

from app.models.terminal import Terminal


def _make_terminal(**overrides) -> Terminal:
    """Build a Terminal ORM object with deterministic defaults."""
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


async def _seed(db, *terminals) -> None:
    for t in terminals:
        db.add(t)
    await db.commit()


class TestListTerminals:
    @pytest.mark.asyncio
    async def test_empty_list(self, api_db, api_client):
        resp = await api_client.get("/api/v1/terminals/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_returns_only_unblocked(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(ip_address="192.168.1.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001", status="unblocked"),
            _make_terminal(ip_address="192.168.1.2", mac_address="AA:00:00:00:00:02",
                           mac_address_normalized="AA0000000002", status="blocked"),
        )
        resp = await api_client.get("/api/v1/terminals/")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["ip_address"] == "192.168.1.1"
        assert items[0]["status"] == "unblocked"

    @pytest.mark.asyncio
    async def test_pagination(self, api_db, api_client):
        terminals = [
            _make_terminal(ip_address=f"192.168.1.{i}",
                           mac_address=f"AA:00:00:00:00:{i:02X}",
                           mac_address_normalized=f"AA00000000{i:02X}",
                           timestamp=datetime(2026, 8, 20, 12, 0, i))
            for i in range(1, 6)
        ]
        await _seed(api_db, *terminals)

        resp = await api_client.get("/api/v1/terminals/?skip=1&limit=2")
        assert resp.status_code == 200
        items = resp.json()
        # Ordered by timestamp desc, so the first page skips the newest.
        assert len(items) == 2
        assert items[0]["ip_address"] == "192.168.1.4"


class TestSearchTerminals:
    @pytest.mark.asyncio
    async def test_no_filter_returns_total_and_items(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(ip_address="192.168.1.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001"),
            _make_terminal(ip_address="192.168.1.2", mac_address="AA:00:00:00:00:02",
                           mac_address_normalized="AA0000000002"),
        )
        resp = await api_client.get("/api/v1/terminals/search")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["skip"] == 0
        assert data["limit"] == 50

    @pytest.mark.asyncio
    async def test_filter_by_ip(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(ip_address="10.0.0.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001"),
            _make_terminal(ip_address="10.0.0.2", mac_address="AA:00:00:00:00:02",
                           mac_address_normalized="AA0000000002"),
        )
        resp = await api_client.get("/api/v1/terminals/search?ip=10.0.0.1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["ip_address"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_filter_by_mac_format_agnostic(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(mac_address="AA:BB:CC:DD:EE:FF", mac_address_normalized="AABBCCDDEEFF"),
            _make_terminal(mac_address="11:22:33:44:55:66", mac_address_normalized="112233445566"),
        )
        # Colons / case should be normalized before matching.
        resp = await api_client.get("/api/v1/terminals/search?mac=aa-bb-cc-dd-ee-ff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["mac_address"] == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_filter_by_status(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(ip_address="192.168.1.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001", status="blocked"),
            _make_terminal(ip_address="192.168.1.2", mac_address="AA:00:00:00:00:02",
                           mac_address_normalized="AA0000000002", status="unblocked"),
        )
        resp = await api_client.get("/api/v1/terminals/search?status=blocked")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_filter_by_compliance_status(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(ip_address="192.168.1.1", mac_address="AA:00:00:00:00:01",
                           mac_address_normalized="AA0000000001", compliance_status="non_compliant"),
            _make_terminal(ip_address="192.168.1.2", mac_address="AA:00:00:00:00:02",
                           mac_address_normalized="AA0000000002", compliance_status="compliant"),
        )
        resp = await api_client.get("/api/v1/terminals/search?compliance_status=non_compliant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["compliance_status"] == "non_compliant"


class TestGetTerminalByID:
    @pytest.mark.asyncio
    async def test_found(self, api_db, api_client):
        t = _make_terminal()
        await _seed(api_db, t)
        resp = await api_client.get(f"/api/v1/terminals/{t.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == t.id
        assert body["ip_address"] == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.get("/api/v1/terminals/9999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Terminal record not found"


class TestSearchTerminalsDedup:
    """Dedup / duplicate checking filters (dedup_dim + dedup_mode)."""

    @pytest.mark.asyncio
    async def test_dedup_by_ip_returns_latest_per_ip(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(
                ip_address="10.0.0.9",
                mac_address="AA:00:00:00:00:01",
                mac_address_normalized="AA0000000001",
                timestamp=datetime(2026, 8, 20, 10, 0, 0),
            ),
            _make_terminal(
                ip_address="10.0.0.9",
                mac_address="AA:00:00:00:00:02",
                mac_address_normalized="AA0000000002",
                timestamp=datetime(2026, 8, 20, 12, 0, 0),
            ),
        )
        resp = await api_client.get(
            "/api/v1/terminals/search?dedup_dim=ip&dedup_mode=dedup"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        # Latest timestamp wins.
        assert data["items"][0]["mac_address"] == "AA:00:00:00:00:02"

    @pytest.mark.asyncio
    async def test_duplicates_by_ip_returns_only_duplicate_ips(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(
                ip_address="10.0.0.10",
                mac_address="AA:00:00:00:00:01",
                mac_address_normalized="AA0000000001",
            ),
            _make_terminal(
                ip_address="10.0.0.10",
                mac_address="AA:00:00:00:00:02",
                mac_address_normalized="AA0000000002",
            ),
            _make_terminal(
                ip_address="10.0.0.11",
                mac_address="AA:00:00:00:00:03",
                mac_address_normalized="AA0000000003",
            ),
        )
        resp = await api_client.get(
            "/api/v1/terminals/search?dedup_dim=ip&dedup_mode=duplicates"
        )
        assert resp.status_code == 200
        data = resp.json()
        # Only the two rows sharing 10.0.0.10; unique IP 10.0.0.11 is excluded.
        assert data["total"] == 2
        assert {item["ip_address"] for item in data["items"]} == {"10.0.0.10"}

    @pytest.mark.asyncio
    async def test_dedup_by_both_falls_back_to_ip(self, api_db, api_client):
        # "both" dedup currently partitions by IP (composite (IP, MAC) rows are always distinct).
        await _seed(
            api_db,
            _make_terminal(
                ip_address="10.0.0.12",
                mac_address="AA:00:00:00:00:01",
                mac_address_normalized="AA0000000001",
                timestamp=datetime(2026, 8, 20, 10, 0, 0),
            ),
            _make_terminal(
                ip_address="10.0.0.12",
                mac_address="AA:00:00:00:00:02",
                mac_address_normalized="AA0000000002",
                timestamp=datetime(2026, 8, 20, 12, 0, 0),
            ),
            _make_terminal(
                ip_address="10.0.0.13",
                mac_address="AA:00:00:00:00:03",
                mac_address_normalized="AA0000000003",
                timestamp=datetime(2026, 8, 20, 13, 0, 0),
            ),
        )
        resp = await api_client.get(
            "/api/v1/terminals/search?dedup_dim=both&dedup_mode=dedup"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert {item["ip_address"] for item in data["items"]} == {"10.0.0.12", "10.0.0.13"}

    @pytest.mark.asyncio
    async def test_no_dim_ignores_dedup_mode(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(
                ip_address="10.0.0.14",
                mac_address="AA:00:00:00:00:01",
                mac_address_normalized="AA0000000001",
            ),
            _make_terminal(
                ip_address="10.0.0.14",
                mac_address="AA:00:00:00:00:02",
                mac_address_normalized="AA0000000002",
            ),
        )
        resp = await api_client.get(
            "/api/v1/terminals/search?dedup_mode=dedup"
        )
        assert resp.status_code == 200
        data = resp.json()
        # Without dedup_dim, behaves like normal search.
        assert data["total"] == 2


class TestExportTerminals:
    @pytest.mark.asyncio
    async def test_export_csv(self, api_db, api_client):
        await _seed(
            api_db,
            _make_terminal(ip_address="10.1.1.1", mac_address="AA:BB:CC:DD:EE:FF",
                           mac_address_normalized="AABBCCDDEEFF", status="blocked"),
        )
        resp = await api_client.get("/api/v1/terminals/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "terminals.csv" in resp.headers["content-disposition"]
        body = resp.text
        assert "MAC Address" in body
        assert "AA:BB:CC:DD:EE:FF" in body
        assert "10.1.1.1" in body