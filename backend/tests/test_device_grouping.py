"""Device grouping (按物理设备归组) tests.

Verifies the dual-NIC unified compliance judgment implemented behind the
`device_grouping_enabled` gray-release flag:

  * judgment mode `any`: 任一网卡命中 IPGuard 基线 → 整机所有记录判合规
  * block granularity `device`: 整机不合规 → 封禁同设备全部可见 IP

Uses the same mock-DB / mock-Redis conventions as test_compliance_service.py.
"""

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.compliance_service import ComplianceService
from tests.test_compliance_service import (
    apply_result_mocks,
    create_mock_blacklist,
    create_mock_terminal,
    make_result,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_terminal_exclusion_rules():
    """Stub exclusion rules to empty so scripted DB sequences stay aligned."""
    from app.services.terminal_exclusion_service import TerminalExclusionService

    with patch.object(
        TerminalExclusionService, "load_active_rules", AsyncMock(return_value=[])
    ):
        yield


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
    t.comments = ""
    return t


# ---------------------------------------------------------------------------
# Shared helpers for auto_block / auto_unblock traceability tests
# ---------------------------------------------------------------------------

def _result(one=None, all_rows=None, scalars_all=None):
    """Build a MagicMock SQLAlchemy result (see test_compliance_service.make_result)."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = one
    r.all.return_value = [] if all_rows is None else all_rows
    _scalars = MagicMock()
    _scalars.all.return_value = [] if scalars_all is None else scalars_all
    r.scalars.return_value = _scalars
    return r


def _scripted_execute(results):
    """Return an AsyncMock execute popping scripted results; exhausted -> empty."""
    queue = list(results)

    async def side_effect(stmt):
        if queue:
            return queue.pop(0)
        return _result(one=None)

    return AsyncMock(side_effect=side_effect)


def _inserted_blacklists(mock_db):
    """Collect Blacklist INSERT payloads (pg_insert) from mock_db.execute calls."""
    entries = []
    for call in mock_db.execute.call_args_list:
        stmt = call.args[0] if call.args else None
        table = getattr(stmt, "table", None)
        if table is None or getattr(table, "name", None) != "blacklist":
            continue
        entries.append(SimpleNamespace(**dict(stmt.compile().params)))
    return entries


@contextlib.contextmanager
def _auto_block_env(service, mock_db, terminals, expansion, grouping_enabled):
    """Patch every collaborator auto_block_non_compliant touches."""
    fw_source = MagicMock()
    fw_source.enabled = True
    fw_source.config = {"base_url": "https://fw.example.com", "username": "admin", "password": "pass"}
    mock_db.execute = _scripted_execute([
        _result(all_rows=[]),               # existing active blacklist pairs
        _result(scalars_all=terminals),     # non-compliant terminals
        _result(one=fw_source),             # firewall data source lookup
    ])
    service._is_device_grouping_enabled = AsyncMock(return_value=grouping_enabled)
    service._is_device_block_granularity_device = AsyncMock(return_value=True)
    service._expand_non_compliant_to_device = AsyncMock(
        return_value=(terminals, expansion)
    )
    service.log_action = AsyncMock()
    service._record_audit_inline = MagicMock()

    mock_sangfor = MagicMock()
    mock_sangfor.block_ip = AsyncMock(return_value={"code": 0})
    mock_sangfor.close = AsyncMock()

    with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
         patch("app.services.sangfor_service.SangforService", return_value=mock_sangfor), \
         patch("app.core.crypto.decrypt_config", return_value={
             "base_url": "https://fw.example.com", "username": "admin",
             "password": "pass", "verify_ssl": True, "ca_bundle": "",
         }), \
         patch.object(service, "_get_block_time", return_value="30d"), \
         patch.object(service, "_load_whitelist_cache", return_value=[]), \
         patch.object(service, "_load_scope_cache", return_value=[]), \
         patch.object(service, "_load_all_ipguard_cache", return_value={}):
        ds_instance = MagicMock()
        ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=["fw1"])
        ds_cls.return_value = ds_instance
        yield


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

        expanded, expansion = await service._expand_non_compliant_to_device([non_compliant], "lab")

        seen_ips = {e.ip_address for e in expanded}
        assert seen_ips == {"10.8.11.80", "10.8.27.19"}
        # 原记录自身不重复并入。
        assert len(expanded) == 2
        # 仅连带扩展出的兄弟条目记录触发源，原条目不在 map 中。
        assert set(expansion) == {sibling.id}
        assert expansion[sibling.id] == {
            "device_id": "101",
            "trigger_terminal_id": non_compliant.id,
            "trigger_ip": "10.8.11.80",
        }

    @pytest.mark.asyncio
    async def test_expand_no_device_id_returns_unchanged(self, service, mock_db):
        entry = _mk_term("10.8.11.80", "C8-B2-9B-FA-03-BB", device_id=None, id_=1)

        expanded, expansion = await service._expand_non_compliant_to_device([entry], "lab")

        assert expanded == [entry]
        assert expansion == {}
        mock_db.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# Traceability: block/unblock reasons + audit details
# ---------------------------------------------------------------------------

class TestDeviceGroupingTraceability:
    """设备归组连带效果在封锁原因、解封原因与审计中可识别、可追溯。"""

    TRIGGER_IP = "10.8.11.80"
    TRIGGER_MAC = "C8-B2-9B-FA-03-BB"
    SIBLING_IP = "10.8.27.19"
    SIBLING_MAC = "00-E0-4C-68-01-02"
    DEVICE_ID = "101"

    def _pair(self):
        trigger = _mk_term(self.TRIGGER_IP, self.TRIGGER_MAC, self.DEVICE_ID, id_=1)
        sibling = _mk_term(self.SIBLING_IP, self.SIBLING_MAC, self.DEVICE_ID, id_=2)
        return trigger, sibling

    def _expansion(self, trigger):
        return {2: {
            "device_id": self.DEVICE_ID,
            "trigger_terminal_id": trigger.id,
            "trigger_ip": trigger.ip_address,
        }}

    def _firewall_block_details(self, service, ip=None):
        details = []
        for call in service.log_action.call_args_list:
            args = call.args
            if len(args) < 5 or args[1] != "firewall_block":
                continue
            if ip is None or args[4].get("ip_address") == ip:
                details.append(args[4])
        return details

    def _summary_details(self, service):
        return service._record_audit_inline.call_args.args[4]

    @pytest.mark.asyncio
    async def test_block_reason_marks_device_grouped_side_effect(self, service, mock_db):
        """T1：连带条目 reason 标注触发源，触发条目保持原判定文案。"""
        trigger, sibling = self._pair()
        with _auto_block_env(service, mock_db, [trigger, sibling], self._expansion(trigger), True):
            result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 2
        reasons = {e.ip_address: e.reason for e in _inserted_blacklists(mock_db)}
        assert "设备归组连带" in reasons[self.SIBLING_IP]
        assert self.TRIGGER_IP in reasons[self.SIBLING_IP]
        assert self.DEVICE_ID in reasons[self.SIBLING_IP]
        assert "设备归组连带" not in reasons[self.TRIGGER_IP]

    @pytest.mark.asyncio
    async def test_firewall_block_audit_carries_device_fields(self, service, mock_db):
        """T2：扩展条目审计含 device_id / 连带标记 / 触发源；触发条目无触发源字段。"""
        trigger, sibling = self._pair()
        with _auto_block_env(service, mock_db, [trigger, sibling], self._expansion(trigger), True):
            await service.auto_block_non_compliant("lab")

        sibling_details = self._firewall_block_details(service, self.SIBLING_IP)
        assert sibling_details
        for d in sibling_details:
            assert d["device_id"] == self.DEVICE_ID
            assert d["device_grouped"] is True
            assert d["device_grouped_expanded"] is True
            assert d["expanded_trigger_ip"] == self.TRIGGER_IP
            assert d["expanded_trigger_terminal_id"] == trigger.id

        trigger_details = self._firewall_block_details(service, self.TRIGGER_IP)
        assert trigger_details
        for d in trigger_details:
            assert d["device_id"] == self.DEVICE_ID
            assert d["device_grouped"] is True
            assert d["device_grouped_expanded"] is False
            assert "expanded_trigger_ip" not in d

    @pytest.mark.asyncio
    async def test_summary_audit_reports_expansion(self, service, mock_db):
        """T4：汇总审计 terminals[] 带 device_id，device_expanded 计数正确。"""
        trigger, sibling = self._pair()
        with _auto_block_env(service, mock_db, [trigger, sibling], self._expansion(trigger), True):
            await service.auto_block_non_compliant("lab")

        details = self._summary_details(service)
        assert details["device_expanded"] == 1
        by_ip = {t["ip_address"]: t for t in details["terminals"]}
        assert by_ip[self.SIBLING_IP]["device_id"] == self.DEVICE_ID
        assert by_ip[self.SIBLING_IP]["expanded_trigger_ip"] == self.TRIGGER_IP
        assert by_ip[self.TRIGGER_IP]["device_id"] == self.DEVICE_ID
        assert by_ip[self.TRIGGER_IP]["device_grouped"] is True
        assert "expanded_trigger_ip" not in by_ip[self.TRIGGER_IP]

    @pytest.mark.asyncio
    async def test_non_grouped_block_keeps_legacy_reason_and_audit(self, service, mock_db):
        """T3/T6：归组关闭（无扩展）时 reason 与审计字段与旧版一致。

        即使终端残留了历史 device_id（关闭开关后不清列），也不得写入设备字段。
        """
        single = _mk_term(self.TRIGGER_IP, self.TRIGGER_MAC, self.DEVICE_ID, id_=1)
        with _auto_block_env(service, mock_db, [single], {}, False):
            result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 1
        entries = _inserted_blacklists(mock_db)
        assert entries[0].reason == "IP 和 MAC 都不合规"

        for d in self._firewall_block_details(service):
            assert "device_id" not in d
            assert "device_grouped" not in d
            assert "device_grouped_expanded" not in d

        summary = self._summary_details(service)
        assert "device_expanded" not in summary
        assert all("device_id" not in t for t in summary["terminals"])

    @pytest.mark.asyncio
    async def test_unblock_reason_marks_device_grouped_decision(self, service, mock_db):
        """T5：设备归组判定合规时，解封原因追加设备标记，审计带 device_id。"""
        bl_entry = create_mock_blacklist(
            ip=self.TRIGGER_IP, mac=self.TRIGGER_MAC, firewall_tag="fw1",
        )
        terminal = create_mock_terminal(
            ip=self.TRIGGER_IP, mac=self.TRIGGER_MAC,
            status="blocked", compliance_status="non_compliant",
            source_tag="lab", firewall_tag="fw1",
        )
        terminal.device_id = self.DEVICE_ID
        service._is_device_grouping_enabled = AsyncMock(return_value=True)
        service._load_device_grouping_cache = AsyncMock(return_value=({}, {self.DEVICE_ID}))

        results = [
            make_result(one=None),                # unblock cooldown check
            make_result(scalars_all=[bl_entry]),  # blacklist entries for this terminal
            make_result(all_rows=[]),             # active blacklist query
        ]
        with apply_result_mocks(service, mock_db, results):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None, self.TRIGGER_IP, self.TRIGGER_MAC,
            )

        assert result["unblocked"] is True
        assert bl_entry.unblock_reason == f"合规解封（设备归组判定：设备 {self.DEVICE_ID} 合规）"
        assert result["audit"]["details"]["device_id"] == self.DEVICE_ID
        assert result["audit"]["details"]["device_grouped"] is True

    @pytest.mark.asyncio
    async def test_whitelist_unblock_reason_has_no_device_marker(self, service, mock_db):
        """白名单解封保持原文案；归组关闭时解封审计不带设备字段。"""
        bl_entry = create_mock_blacklist(
            ip=self.TRIGGER_IP, mac=self.TRIGGER_MAC, firewall_tag="fw1",
        )
        terminal = create_mock_terminal(
            ip=self.TRIGGER_IP, mac=self.TRIGGER_MAC,
            status="blocked", compliance_status="non_compliant",
            source_tag="lab", firewall_tag="fw1",
        )
        terminal.device_id = self.DEVICE_ID
        service._is_device_grouping_enabled = AsyncMock(return_value=False)

        results = [
            make_result(scalars_all=[bl_entry]),
            make_result(all_rows=[]),
        ]
        with apply_result_mocks(service, mock_db, results):
            result = await service._apply_compliance_result(
                terminal, "bypass", "mac", "test", self.TRIGGER_IP, self.TRIGGER_MAC,
            )

        assert bl_entry.unblock_reason == "加入白名单"
        assert "device_id" not in result["audit"]["details"]
        assert "device_grouped" not in result["audit"]["details"]