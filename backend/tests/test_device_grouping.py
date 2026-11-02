"""Device grouping (按物理设备归组) tests.

Verifies the dual-NIC unified compliance judgment implemented behind the
`device_grouping_enabled` gray-release flag:

  * judgment mode `any`: 任一网卡命中 IPGuard 基线 → 整机所有记录判合规
  * block granularity `device`: 整机不合规 → 封禁同设备全部可见 IP

Uses the same mock-DB / mock-Redis conventions as test_compliance_service.py.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.compliance_service import ComplianceService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(mock_async_session):
    """ComplianceService backing session (mock)."""
    return mock_async_session


@pytest.fixture
def service(mock_db):
    svc = ComplianceService(mock_db)
    # 旧用例无关的「IPGuard 已同步」闸默认就绪，本文件用例按需 patch。
    svc._is_ipguard_sync_ready = AsyncMock(return_value=True)
    return svc


def _mk_term(ip, mac, device_id, id_):
    """Minimal Terminal stand-in for _expand_non_compliant_to_device."""
    t = MagicMock()
    t.id = id_
    t.ip_address = ip
    t.mac_address = mac
    t.device_id = device_id
    t.status = "unblocked"
    return t


# ---------------------------------------------------------------------------
# Judgment unification (any mode)
# ---------------------------------------------------------------------------

class TestDeviceGroupingJudgment:
    """batch_check_compliance 的 device 级 `any` 判定口径。"""

    # 双网卡：有线 C8-B2-9B-FA-03-BB(10.8.11.80) + 无线 00-E0-4C-68-01-02(10.8.27.19)
    # IPGuard 基线仅收录「有线」网卡 —— 无线网卡在单网卡口径下会被独立判为非合规。
    WIRED_IP = "10.8.11.80"
    WIRED_MAC = "C8-B2-9B-FA-03-BB"
    WIRELESS_IP = "10.8.27.19"
    WIRELESS_MAC = "00-E0-4C-68-01-02"

    def _entries(self):
        return [
            {"ip_address": self.WIRED_IP, "mac_address": self.WIRED_MAC},
            {"ip_address": self.WIRELESS_IP, "mac_address": self.WIRELESS_MAC},
        ]

    async def _run(self, service, grouping_enabled, ipguard_data):
        service._is_device_grouping_enabled = AsyncMock(return_value=grouping_enabled)
        service._load_device_grouping_cache = AsyncMock(
            return_value=(
                {
                    "C8B29BFA03BB": "101",
                    "00E04C680102": "101",
                },
                {"101"},
            )
        )
        service._load_whitelist_cache = AsyncMock(return_value=[])
        service._load_scope_cache = AsyncMock(return_value=[])
        service._load_all_ipguard_cache = AsyncMock(return_value=ipguard_data)
        entries = self._entries()
        result = await service.batch_check_compliance(entries)
        return entries, result

    @pytest.mark.asyncio
    async def test_without_grouping_wireless_is_non_compliant(self, service):
        """基线回归：关闭归组时，无线网卡独立判为非合规（现行单网卡行为）。"""
        ipguard_data = {
            "lab": [{"ip_address": self.WIRED_IP, "mac_address": self.WIRED_MAC}],
        }
        entries, result = await self._run(service, grouping_enabled=False, ipguard_data=ipguard_data)

        assert result.non_compliant == 1
        compliant_ips = [e["ip_address"] for e in result.details["compliant"]]
        non_compliant_ips = [e["ip_address"] for e in result.details["non_compliant"]]
        assert self.WIRED_IP in compliant_ips
        assert self.WIRELESS_IP in non_compliant_ips

    @pytest.mark.asyncio
    async def test_any_mode_unifies_dual_nic(self, service):
        """归组开启（any）：无线网卡随设备一起判为合规。"""
        ipguard_data = {
            "lab": [{"ip_address": self.WIRED_IP, "mac_address": self.WIRED_MAC}],
        }
        entries, result = await self._run(service, grouping_enabled=True, ipguard_data=ipguard_data)

        assert result.non_compliant == 0
        assert result.compliant == 2
        # 两条记录都被盖上 device_id，且 ig_match 一律为 True（device 级命中）。
        for e in entries:
            assert e["device_id"] == "101"
            assert e["ig_match"] is True

    @pytest.mark.asyncio
    async def test_device_missing_from_baseline_stays_non_compliant(self, service):
        """整机不在基线：两个网卡都应判非合规（不会凭空合规）。"""
        service._is_device_grouping_enabled = AsyncMock(return_value=True)
        service._load_device_grouping_cache = AsyncMock(return_value=({}, set()))
        service._load_whitelist_cache = AsyncMock(return_value=[])
        service._load_scope_cache = AsyncMock(return_value=[])
        service._load_all_ipguard_cache = AsyncMock(
            return_value={"lab": [{"ip_address": "10.9.9.9", "mac_address": "AA-BB-CC-DD-EE-FF"}]}
        )
        entries = self._entries()
        result = await service.batch_check_compliance(entries)

        assert result.compliant == 0
        assert result.non_compliant == 2

    @pytest.mark.asyncio
    async def test_whitelist_still_wins_over_device_override(self, service):
        """白名单优先级最高：即使设备命中基线，白名单记录仍判 bypass。"""
        service._is_device_grouping_enabled = AsyncMock(return_value=True)
        service._load_device_grouping_cache = AsyncMock(
            return_value=({
                "C8B29BFA03BB": "101",
                "00E04C680102": "101",
            }, {"101"})
        )
        whitelist = [{"mac_address": self.WIRELESS_MAC, "pattern_type": "single_mac", "match_type": "mac"}]
        service._load_whitelist_cache = AsyncMock(return_value=whitelist)
        service._load_scope_cache = AsyncMock(return_value=[])
        service._load_all_ipguard_cache = AsyncMock(
            return_value={"lab": [{"ip_address": self.WIRED_IP, "mac_address": self.WIRED_MAC}]}
        )
        entries = self._entries()
        result = await service.batch_check_compliance(entries)

        # 无线网卡命中白名单 → bypass；有线网卡命中基线 → compliant。
        assert result.compliant == 1
        assert result.bypass == 1
        assert result.non_compliant == 0


# ---------------------------------------------------------------------------
# Block granularity (device)
# ---------------------------------------------------------------------------

class TestDeviceBlockGranularity:
    """device 封禁粒度：整机不合规 → 一并封禁同设备全部可见 IP。"""

    @pytest.mark.asyncio
    async def test_expand_adds_sibling_ips_of_same_device(self, service, mock_db):
        non_compliant = _mk_term("10.8.11.80", "C8-B2-9B-FA-03-BB", device_id="101", id_=1)
        sibling = _mk_term("10.8.27.19", "00-E0-4C-68-01-02", device_id="101", id_=2)

        # 数据库按 device_id IN(...) 已过滤到同设备(101)的两条记录，
        # 其中包含原 non_compliant 记录自身，用于校验去重逻辑。
        r = MagicMock()
        r.scalars.return_value.all.return_value = [non_compliant, sibling]
        mock_db.execute = AsyncMock(return_value=r)

        expanded = await service._expand_non_compliant_to_device([non_compliant], "lab")

        seen_ips = {e.ip_address for e in expanded}
        assert seen_ips == {"10.8.11.80", "10.8.27.19"}
        # 原记录自身不重复并入。
        assert len(expanded) == 2

    @pytest.mark.asyncio
    async def test_expand_no_device_id_returns_unchanged(self, service, mock_db):
        entry = _mk_term("10.8.11.80", "C8-B2-9B-FA-03-BB", device_id=None, id_=1)

        expanded = await service._expand_non_compliant_to_device([entry], "lab")

        assert expanded == [entry]
        mock_db.execute.assert_not_awaited()