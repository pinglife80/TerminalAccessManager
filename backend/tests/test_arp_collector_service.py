"""
Comprehensive unit tests for ArpCollectorService.

All database calls, external SSH/HTTP operations, and compliance checks are
mocked so the tests do NOT require Docker, PostgreSQL, Redis, or real switches.

Methods under test:
- _normalize_mac (static)
- _parse_arp_output
- _parse_api_response
- process_arp_entries (core upsert + compliance + offline detection)
- collect_from_ssh / collect_from_api
- run_scheduled_collection
"""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.data_source import DataSource
from app.models.terminal import Terminal, TerminalStatus
from app.models.terminal_exclusion import TerminalExclusion
from app.schemas.data_source import ComplianceCheckResult, SyncResult
from app.services.arp_collector_service import ArpCollectorService
from app.services.compliance_service import ComplianceService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_source(source_type="arp_ssh", tag="lab", config=None, id_=1, enabled=True):
    """Create a mock DataSource whose attributes mirror the real column names."""
    src = MagicMock(spec=DataSource)
    src.id = id_
    src.type = source_type
    src.tag = tag
    src.enabled = enabled
    if config is None:
        config = {
            "host": "10.0.0.254",
            "port": 22,
            "username": "admin",
            "password": "secret",
            "command": "display arp",
        }
    src.config = config
    return src


def make_terminal(ip="10.0.0.1", mac="AA-BB-CC-DD-EE-FF", mac_norm="AABBCCDDEEFF",
                  status="unblocked", compliance_status="unknown", source_tag="lab"):
    """Create a mock Terminal with commonly inspected attributes."""
    t = MagicMock(spec=Terminal)
    t.id = 1
    t.ip_address = ip
    t.mac_address = mac
    t.mac_address_normalized = mac_norm
    t.status = status
    t.compliance_status = compliance_status
    t.source_tag = source_tag
    t.source = "arp"
    t.updated_at = None
    t.ip_changed_at = None
    t.non_compliant_confirm_count = 0
    t.compliant_confirm_count = 0
    return t


def make_exclusion_rule(ip_pattern=None, ip_pattern_type=None,
                        mac_address=None, mac_pattern_type=None):
    """Create a mock TerminalExclusion with the attributes the service reads."""
    rule = MagicMock(spec=TerminalExclusion)
    rule.ip_pattern = ip_pattern
    rule.ip_pattern_type = ip_pattern_type
    rule.mac_address = mac_address
    rule.mac_pattern_type = mac_pattern_type
    return rule


def make_exec_result(scalar=None, rows=None):
    """Build a mock SQLAlchemy Result supporting scalar_one_or_none / scalars().all()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    if rows is not None:
        result.scalars.return_value.all.return_value = rows
    return result


def set_exec_sequence(mock_db, results, exclusion_rules=None, blacklist_ips=None,
                      preload_rows=None):
    """Make mock_db.execute replay a fixed sequence of Result mocks.

    The collector issues a terminal-exclusion query, an optional active
    blacklist query, then a MAC→IP pre-load query before the upsert loop.
    Feed empty results for those first so callers keep their fixed per-query
    order.
    """
    exclusion_rules = list(exclusion_rules or [])
    prefix = [make_exec_result(rows=exclusion_rules)]
    if exclusion_rules:
        blacklist_result = make_exec_result()
        blacklist_result.all.return_value = [
            (ip,) for ip in (blacklist_ips or [])
        ]
        prefix.append(blacklist_result)
    prefix.append(make_exec_result(rows=list(preload_rows or [])))
    results = prefix + list(results)
    it = iter(results)

    async def _side_effect(stmt):
        try:
            return next(it)
        except StopIteration:
            return make_exec_result()

    mock_db.execute = AsyncMock(side_effect=_side_effect)


def assert_logged_any(mock_logger, *substrings):
    """Assert at least one log call contains all given substrings."""
    for call in mock_logger.call_args_list:
        if all(s in str(call) for s in substrings):
            return
    raise AssertionError(
        f"No log entry containing {substrings!r}. Calls: {mock_logger.call_args_list}"
    )


def patch_ds_service():
    """Patch the DataSourceService constructor to return a controllable mock."""
    ds_mock = MagicMock()
    ds_mock.update_sync_status = AsyncMock()
    return patch(
        "app.services.data_source_service.DataSourceService", return_value=ds_mock
    ), ds_mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(mock_async_session):
    return mock_async_session


@pytest.fixture
def service(mock_db):
    return ArpCollectorService(mock_db)


# ===========================================================================
# TestNormalizeMac
# ===========================================================================

class TestNormalizeMac:
    def test_colon_format(self):
        assert ArpCollectorService._normalize_mac("aa:bb:cc:dd:ee:ff") == "AA-BB-CC-DD-EE-FF"

    def test_dash_format(self):
        assert ArpCollectorService._normalize_mac("aa-bb-cc-dd-ee-ff") == "AA-BB-CC-DD-EE-FF"

    def test_cisco_dot_format(self):
        assert ArpCollectorService._normalize_mac("aa11.bb22.cc33") == "AA-11-BB-22-CC-33"

    def test_unseparated_lowercase(self):
        assert ArpCollectorService._normalize_mac("aabbccddeeff") == "AA-BB-CC-DD-EE-FF"

    def test_invalid_short_length(self):
        assert ArpCollectorService._normalize_mac("aa:bb:cc") is None

    def test_invalid_non_alnum(self):
        assert ArpCollectorService._normalize_mac("aa-bb-cc-dd-ee-!") is None

    def test_empty(self):
        assert ArpCollectorService._normalize_mac("") is None


# ===========================================================================
# TestAsUtcTimestamp
# ===========================================================================

class TestAsUtcTimestamp:
    def test_naive_treated_as_utc(self):
        naive = datetime(2026, 1, 1, 0, 0, 0)
        utc = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert ArpCollectorService._as_utc_timestamp(naive) == ArpCollectorService._as_utc_timestamp(utc)

    def test_aware_preserves_offset(self):
        utc = datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC)
        shanghai = datetime(2026, 1, 1, 16, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        assert ArpCollectorService._as_utc_timestamp(utc) == ArpCollectorService._as_utc_timestamp(shanghai)


# ===========================================================================
# TestParseArpOutput
# ===========================================================================

class TestParseArpOutput:
    def test_cisco_format(self, service):
        out = "Internet  192.168.1.1   2   aa11.bb22.cc33  ARPA  Vlan10"
        assert service._parse_arp_output(out, "arp_ssh") == [
            {"ip_address": "192.168.1.1", "mac_address": "aa-11-bb-22-cc-33"}
        ]

    def test_huawei_format(self, service):
        out = "192.168.1.1  aa11-bb22-cc33  I  Vlanif10"
        assert service._parse_arp_output(out, "arp_ssh") == [
            {"ip_address": "192.168.1.1", "mac_address": "aa-11-bb-22-cc-33"}
        ]

    def test_generic_colon_format(self, service):
        out = "192.168.1.1  aa:bb:cc:dd:ee:ff"
        assert service._parse_arp_output(out, "arp_ssh") == [
            {"ip_address": "192.168.1.1", "mac_address": "AA-BB-CC-DD-EE-FF"}
        ]

    def test_empty_output(self, service):
        assert service._parse_arp_output("", "arp_ssh") == []

    def test_header_lines_ignored(self, service):
        out = (
            "Internet Address  Physical Address  Type\n"
            "192.168.1.1  aa:bb:cc:dd:ee:ff"
        )
        assert service._parse_arp_output(out, "arp_ssh") == [
            {"ip_address": "192.168.1.1", "mac_address": "AA-BB-CC-DD-EE-FF"}
        ]

    def test_multiple_entries(self, service):
        out = (
            "Internet  192.168.1.1   2   aa11.bb22.cc33  ARPA  Vlan10\n"
            "Internet  192.168.1.2   2   aa11.bb22.cc44  ARPA  Vlan10"
        )
        assert service._parse_arp_output(out, "arp_ssh") == [
            {"ip_address": "192.168.1.1", "mac_address": "aa-11-bb-22-cc-33"},
            {"ip_address": "192.168.1.2", "mac_address": "aa-11-bb-22-cc-44"},
        ]

    def test_line_without_ip_ignored(self, service):
        out = "This line has no IP address at all\n192.168.1.1  aa:bb:cc:dd:ee:ff"
        assert service._parse_arp_output(out, "arp_ssh") == [
            {"ip_address": "192.168.1.1", "mac_address": "AA-BB-CC-DD-EE-FF"}
        ]


# ===========================================================================
# TestParseApiResponse
# ===========================================================================

class TestParseApiResponse:
    def test_list_of_dicts(self, service):
        data = [{"ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        assert service._parse_api_response(data) == [
            {"ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"}
        ]

    def test_data_wrapper(self, service):
        data = {"data": [{"ip": "1.1.1.1", "mac": "aa:bb:cc:dd:ee:ff"}]}
        assert service._parse_api_response(data) == [
            {"ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"}
        ]

    def test_entries_wrapper(self, service):
        data = {"entries": [{"ip": "1.1.1.1", "mac": "aa:bb:cc:dd:ee:ff"}]}
        assert service._parse_api_response(data) == [
            {"ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"}
        ]

    def test_alias_fields(self, service):
        data = {"results": [{"ipv4_address": "1.1.1.1", "macAddress": "aa:bb:cc:dd:ee:ff"}]}
        assert service._parse_api_response(data) == [
            {"ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"}
        ]

    def test_non_dict_items_skipped(self, service):
        data = {"data": [{"ip": "1.1.1.1", "mac": "aa:bb:cc:dd:ee:ff"}, "bad", 123]}
        assert service._parse_api_response(data) == [
            {"ip_address": "1.1.1.1", "mac_address": "aa:bb:cc:dd:ee:ff"}
        ]

    def test_non_list_non_dict(self, service):
        assert service._parse_api_response("x") == []

    def test_dict_without_wrapper(self, service):
        assert service._parse_api_response({"foo": "bar"}) == []

    def test_missing_mac_skipped(self, service):
        assert service._parse_api_response({"data": [{"ip": "1.1.1.1"}]}) == []

    def test_missing_ip_skipped(self, service):
        assert service._parse_api_response({"data": [{"mac": "aa:bb:cc:dd:ee:ff"}]}) == []


# ===========================================================================
# TestProcessArpEntries
# ===========================================================================

class TestProcessArpEntries:
    @pytest.mark.asyncio
    async def test_empty_entries(self, service, mock_db):
        # No upsert loop: only batch-check + offline queries run.
        set_exec_sequence(mock_db, [make_exec_result(rows=[]), make_exec_result(rows=[])])
        with patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            result = await service.process_arp_entries([], "lab")

        assert result.success is True
        assert result.entries_processed == 0
        assert result.entries_added == 0
        assert result.entries_updated == 0
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_new_terminal(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),      # upsert -> new
                make_exec_result(rows=[]),           # batch check
                make_exec_result(rows=[]),           # offline
            ],
        )
        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()) as online, \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_added == 1
        assert result.entries_updated == 0
        online.assert_called_once()

        added = mock_db.add.call_args.args[0]
        assert isinstance(added, Terminal)
        assert added.ip_address == "10.0.0.1"
        assert added.mac_address_normalized == "AABBCCDDEEFF"
        assert added.status == TerminalStatus.UNBLOCKED.value
        assert added.compliance_status == "unknown"
        assert added.source_tag == "lab"
        assert added.ip_changed_at is None
        # 一次性 ARP 记录也必须带有最后采集时间，否则离线检测会永久跳过它。
        assert added.updated_at is not None

    @pytest.mark.asyncio
    async def test_updates_existing_terminal_same_ip(self, service, mock_db):
        existing = make_terminal(ip="10.0.0.1")
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
        )
        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()) as online, \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_updated == 1
        assert result.entries_added == 0
        assert existing.ip_changed_at is None
        online.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_terminal_clears_stale_device_id(self, service, mock_db):
        """当前映射不含该 MAC → 清空残留 device_id，避免设备归组误判合规。"""
        existing = make_terminal(ip="10.0.0.1")
        existing.device_id = "3786"
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
        )
        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch.object(
                 ComplianceService, "_is_device_grouping_enabled",
                 AsyncMock(return_value=True),
             ), \
             patch.object(
                 ComplianceService, "_load_device_grouping_cache",
                 AsyncMock(return_value=({"B0BE835CCE41": "101"}, {"101"})),
             ):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_updated == 1
        assert existing.device_id is None

    @pytest.mark.asyncio
    async def test_existing_terminal_keeps_device_id_when_mapping_unavailable(self, service, mock_db):
        """注册表不可用（空映射）→ 保留原 device_id，避免误清全量关联。"""
        existing = make_terminal(ip="10.0.0.1")
        existing.device_id = "3786"
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
        )
        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch.object(
                 ComplianceService, "_is_device_grouping_enabled",
                 AsyncMock(return_value=True),
             ), \
             patch.object(
                 ComplianceService, "_load_device_grouping_cache",
                 AsyncMock(return_value=({}, set())),
             ):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_updated == 1
        assert existing.device_id == "3786"

    @pytest.mark.asyncio
    async def test_same_mac_new_ip_marks_ip_changed_at(self, service, mock_db):
        # Same MAC at a different IP is an IP migration: the new record must be
        # marked ip_changed_at so the compliance grace period holds downgrades.
        old = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        entries = [{"ip_address": "10.0.0.2", "mac_address": "aa:bb:cc:dd:ee:ff"}]

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),  # upsert (.2) -> new record
                make_exec_result(rows=[]),      # batch check
                make_exec_result(rows=[]),      # offline
            ],
            preload_rows=[old],                 # MAC presently at .1
        )

        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()) as online, \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.arp_collector_service.logger.info") as info_logger:
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_added == 1
        added = mock_db.add.call_args.args[0]
        assert added.ip_address == "10.0.0.2"
        assert added.ip_changed_at is not None
        online.assert_called_once()
        # 多 IP/MAC 震荡排查：IP 迁移必须记录 MAC、新 IP、旧 IP。
        assert_logged_any(
            info_logger, "ARP IP-migration", "AABBCCDDEEFF", "10.0.0.2", "10.0.0.1"
        )

    @pytest.mark.asyncio
    async def test_same_mac_new_ip_creates_new_record(self, service, mock_db):
        # Composite (MAC, IP) identity: a MAC appearing at a new IP is a new
        # record rather than an in-place IP update of the previous record.
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),  # (MAC, 10.0.0.1) not found
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
        )
        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()) as online, \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_added == 1
        assert result.entries_updated == 0
        online.assert_called_once()

    @pytest.mark.asyncio
    async def test_dedup_by_composite_identity(self, service, mock_db):
        # Composite (MAC, IP) identity: only exact (MAC, IP) duplicates are
        # deduped within a batch; same MAC on a different IP is a distinct record.
        entries = [
            {"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"},
            {"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ]
        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
        )
        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()) as online, \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_added == 1
        assert online.call_count == 1

    @pytest.mark.asyncio
    async def test_skips_empty_or_invalid_entries(self, service, mock_db):
        entries = [
            {"ip_address": "", "mac_address": "aa:bb:cc:dd:ee:ff"},
            {"ip_address": "10.0.0.1", "mac_address": ""},
            {"ip_address": "10.0.0.2", "mac_address": "aa:bb:cc"},
            {"ip_address": "10.0.0.3", "mac_address": "aa:bb:cc:dd:ee:ff"},
        ]
        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
        )
        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()) as online, \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_processed == 4
        assert result.entries_added == 1
        online.assert_called_once()

    @pytest.mark.asyncio
    async def test_entry_error_isolated(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        mock_db.execute = AsyncMock(side_effect=Exception("db boom"))

        result = await service.process_arp_entries(entries, "lab")

        assert result.success is True
        assert len(result.errors) == 2
        assert "Error processing" in result.errors[0]
        assert "Compliance check failed" in result.errors[1]

    @pytest.mark.asyncio
    async def test_apply_compliant_result(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        unchecked = make_terminal(ip="10.0.0.1", mac="AA-BB-CC-DD-EE-FF",
                                  mac_norm="AABBCCDDEEFF", compliance_status="unknown")

        check_result = ComplianceCheckResult(
            total_checked=1, compliant=1, bypass=0, non_compliant=0,
            details={"compliant": [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_address": "10.0.0.1"}]},
        )
        comp_svc = MagicMock()
        comp_svc.batch_check_compliance = AsyncMock(return_value=check_result)
        comp_svc.apply_initial_compliance_result = AsyncMock(return_value={})

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),        # upsert -> new
                make_exec_result(rows=[unchecked]),   # batch check
                make_exec_result(rows=[]),             # offline
            ],
        )

        with patch("app.services.compliance_service.ComplianceService", return_value=comp_svc), \
             patch("app.services.event_emitter.emit_terminal_online", AsyncMock()), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_added == 1
        comp_svc.batch_check_compliance.assert_called_once()
        comp_svc.apply_initial_compliance_result.assert_called_once()
        args = comp_svc.apply_initial_compliance_result.call_args.args
        assert args[0] is unchecked
        assert args[1] == "compliant"
        assert mock_db.commit.call_count == 2

    @pytest.mark.asyncio
    async def test_apply_bypass_and_non_compliant(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        unchecked_bypass = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        unchecked_nc = make_terminal(ip="10.0.0.2", mac_norm="112233445566")

        check_result = ComplianceCheckResult(
            total_checked=2, compliant=0, bypass=1, non_compliant=1,
            details={
                "bypass": [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_address": "10.0.0.1", "wl_match_type": "mac", "wl_comments": "lab pc"}],
                "non_compliant": [{"mac_address": "11-22-33-44-55-66", "ip_address": "10.0.0.2"}],
            },
        )
        comp_svc = MagicMock()
        comp_svc.batch_check_compliance = AsyncMock(return_value=check_result)
        comp_svc.apply_initial_compliance_result = AsyncMock(return_value={})

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),
                make_exec_result(rows=[unchecked_bypass, unchecked_nc]),
                make_exec_result(rows=[]),
            ],
        )

        with patch("app.services.compliance_service.ComplianceService", return_value=comp_svc), \
             patch("app.services.event_emitter.emit_terminal_online", AsyncMock()), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            await service.process_arp_entries(entries, "lab")

        assert comp_svc.apply_initial_compliance_result.call_count == 2
        calls = comp_svc.apply_initial_compliance_result.call_args_list
        statuses = {(c.args[0].mac_address_normalized, c.args[1]) for c in calls}
        assert statuses == {
            ("AABBCCDDEEFF", "bypass"),
            ("112233445566", "non_compliant"),
        }

    @pytest.mark.asyncio
    async def test_empty_compliance_details(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        unchecked = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")

        check_result = ComplianceCheckResult(
            total_checked=1, compliant=0, bypass=0, non_compliant=0, details=None
        )
        comp_svc = MagicMock()
        comp_svc.batch_check_compliance = AsyncMock(return_value=check_result)
        comp_svc.apply_initial_compliance_result = AsyncMock()

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),      # upsert -> new
                make_exec_result(rows=[unchecked]),  # batch check
                make_exec_result(rows=[]),           # offline
            ],
        )

        with patch("app.services.compliance_service.ComplianceService", return_value=comp_svc), \
             patch("app.services.event_emitter.emit_terminal_online", AsyncMock()), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            await service.process_arp_entries(entries, "lab")

        comp_svc.apply_initial_compliance_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_compliance_result_lookup_miss(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        unchecked = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")

        # details contain a different MAC, so the unchecked terminal has no lookup hit
        check_result = ComplianceCheckResult(
            total_checked=1, compliant=1, bypass=0, non_compliant=0,
            details={"compliant": [{"mac_address": "FF-EE-DD-CC-BB-AA"}]},
        )
        comp_svc = MagicMock()
        comp_svc.batch_check_compliance = AsyncMock(return_value=check_result)
        comp_svc.apply_initial_compliance_result = AsyncMock()

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),
                make_exec_result(rows=[unchecked]),
                make_exec_result(rows=[]),
            ],
        )

        with patch("app.services.compliance_service.ComplianceService", return_value=comp_svc), \
             patch("app.services.event_emitter.emit_terminal_online", AsyncMock()), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            await service.process_arp_entries(entries, "lab")

        comp_svc.apply_initial_compliance_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_unchecked_skips_compliance(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        comp_svc = MagicMock()
        comp_svc.batch_check_compliance = AsyncMock()

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=None),
                make_exec_result(rows=[]),  # no unchecked
                make_exec_result(rows=[]),
            ],
        )

        with patch("app.services.compliance_service.ComplianceService", return_value=comp_svc), \
             patch("app.services.event_emitter.emit_terminal_online", AsyncMock()), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])):
            await service.process_arp_entries(entries, "lab")

        comp_svc.batch_check_compliance.assert_not_called()
        assert mock_db.commit.call_count == 1

    @pytest.mark.asyncio
    async def test_offline_detection_emits(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        stale = make_terminal(ip="10.0.0.2", mac_norm="112233445566")
        stale.updated_at = datetime(2025, 1, 1, tzinfo=UTC)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[stale]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
        with patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline:
            await service.process_arp_entries(entries, "lab")

        offline.assert_called_once_with(ip_address="10.0.0.2", mac_address=stale.mac_address or "")

    @pytest.mark.asyncio
    async def test_offline_detection_not_stale_no_emit(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        recent = make_terminal(ip="10.0.0.2", mac_norm="112233445566")
        recent.updated_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[recent]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)  # 60s ago
        with patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline:
            await service.process_arp_entries(entries, "lab")

        offline.assert_not_called()

    @pytest.mark.asyncio
    async def test_offline_detection_uses_timestamp_when_updated_at_null(self, service, mock_db):
        """历史记录 updated_at 为 NULL 时，用 timestamp 兜底判断离线。

        新记录此前不写 updated_at，导致只被采集一次的记录永远不会被标记
        离线；这里验证兜底逻辑会正常发出离线事件并写入 block_state。
        """
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        null_ts = make_terminal(ip="10.0.0.2", mac_norm="112233445566")  # updated_at None
        null_ts.timestamp = datetime(2025, 1, 1, tzinfo=UTC)
        null_ts.block_state = None

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[null_ts]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
        with patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline:
            await service.process_arp_entries(entries, "lab")

        assert null_ts.block_state == "offline"
        offline.assert_called_once_with(ip_address="10.0.0.2", mac_address=null_ts.mac_address or "")

    @pytest.mark.asyncio
    async def test_one_off_duplicate_ip_record_is_marked_offline(self, service, mock_db):
        """同一 MAC 曾短暂出现在两个 IP：只被采集一次的记录必须离线。

        复现 10.8.18.183/92-70-FA-71-63-DB 场景：同一批采集创建了 .136 与
        .183 两条记录，之后只重新采集到 .136；.183 记录 updated_at 为 NULL，
        必须通过 timestamp 兜底标记离线，避免持续参与合规重算。
        """
        entries = [{"ip_address": "10.0.0.136", "mac_address": "92:70:fa:71:63:db"}]
        seen = make_terminal(ip="10.0.0.136", mac="92-70-FA-71-63-DB", mac_norm="9270FA7163DB")
        seen.block_state = None
        one_off = make_terminal(ip="10.0.0.183", mac="92-70-FA-71-63-DB", mac_norm="9270FA7163DB")
        one_off.updated_at = None
        one_off.timestamp = datetime(2025, 1, 1, tzinfo=UTC)
        one_off.block_state = None

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=seen),
                make_exec_result(rows=[]),
                make_exec_result(rows=[seen, one_off]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
        with patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline:
            await service.process_arp_entries(entries, "lab")

        assert one_off.block_state == "offline"
        offline.assert_called_once_with(
            ip_address="10.0.0.183", mac_address="92-70-FA-71-63-DB"
        )

    @pytest.mark.asyncio
    async def test_offline_detection_marks_block_state(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        stale = make_terminal(ip="10.0.0.2", mac_norm="112233445566")
        stale.block_state = None
        stale.updated_at = datetime(2025, 1, 1, tzinfo=UTC)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[stale]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
        with patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline, \
             patch("app.services.arp_collector_service.logger.info") as info_logger:
            await service.process_arp_entries(entries, "lab")

        assert stale.block_state == "offline"
        offline.assert_called_once()
        # 离线标记必须记录 ip/mac 与标记动作，便于排查陈旧记录去向。
        assert_logged_any(info_logger, "ARP offline", "10.0.0.2", "marked offline")

    @pytest.mark.asyncio
    async def test_offline_commit_failure_emits_no_audit(self, service, mock_db):
        """点1 failure path: persisting the online/offline block_state change fails,
        so the terminal_online/terminal_offline audit must NOT be emitted — the
        audit must never precede the committed business state."""
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        stale = make_terminal(ip="10.0.0.2", mac_norm="112233445566")
        stale.block_state = None
        stale.updated_at = datetime(2025, 1, 1, tzinfo=UTC)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[stale]),
            ],
        )

        # Commit #1 = upsert persists (succeeds), #2 = block_state persists (fails).
        mock_db.commit = AsyncMock(side_effect=[None, RuntimeError("db commit failed")])

        # The deferred-audit emitter is the ComplianceService used inside the
        # online/offline block; capture it so we can assert it is never invoked.
        audit_svc = MagicMock()
        audit_svc.log_action = AsyncMock()

        fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
        with patch("app.services.compliance_service.ComplianceService", return_value=audit_svc), \
             patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()):
            await service.process_arp_entries(entries, "lab")

        # The offline-detection block swallows the commit error and returns a
        # normal SyncResult; crucially, the audit emit is gated behind a
        # successful commit, so it must never have run.
        audit_svc.log_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_offline_detection_skips_blocked(self, service, mock_db):
        """Blocked records are not re-marked offline — their block is IP-level and
        must be left for reconciliation (old-IP release is handled in P1-a)."""
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        stale = make_terminal(ip="10.0.0.2", mac_norm="112233445566")
        stale.block_state = None
        stale.status = "blocked"
        stale.updated_at = datetime(2025, 1, 1, tzinfo=UTC)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[stale]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
        with patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline:
            await service.process_arp_entries(entries, "lab")

        assert stale.block_state is None
        offline.assert_called_once()  # still emits offline event, but no block_state mutation

    @pytest.mark.asyncio
    async def test_online_clears_offline_mark(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        existing.block_state = "offline"
        existing.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[existing]),
            ],
        )

        with patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline, \
             patch("app.services.arp_collector_service.logger.info") as info_logger:
            await service.process_arp_entries(entries, "lab")

        assert existing.block_state is None
        offline.assert_not_called()
        # 在线清除 offline 标记必须留痕，便于确认设备重新上线。
        assert_logged_any(info_logger, "ARP online", "AA-BB-CC-DD-EE-FF", "cleared offline mark")

    @pytest.mark.asyncio
    async def test_online_clears_offline_mark_and_resets_mac_confirm_counts(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        existing.block_state = "offline"
        existing.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

        sibling = make_terminal(ip="10.0.0.2", mac_norm="AABBCCDDEEFF")
        sibling.non_compliant_confirm_count = 3
        sibling.compliant_confirm_count = 2

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),   # upsert lookup
                make_exec_result(rows=[]),           # unchecked entries query
                make_exec_result(rows=[existing]),   # all_terminals (offline detection)
                make_exec_result(rows=[sibling]),    # sibling query by MAC (B2 clear)
            ],
        )

        with patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline, \
             patch("app.services.arp_collector_service.logger.info") as info_logger:
            await service.process_arp_entries(entries, "lab")

        assert existing.block_state is None
        # 方向 B（B2）：重新上线时按 MAC 清零兄弟记录确认计数，防止跨在线窗口
        # 累积陈旧的瞬时漏同步证据导致合规终端被误降级。
        assert sibling.non_compliant_confirm_count == 0
        assert sibling.compliant_confirm_count == 0
        offline.assert_not_called()
        assert_logged_any(info_logger, "ARP online", "AA-BB-CC-DD-EE-FF", "cleared offline mark")

    @pytest.mark.asyncio
    async def test_exclusion_rule_skips_entry_without_persisting(self, service, mock_db):
        # 命中排除规则的条目在入库前被丢弃：既不写 terminals，也不进入合规计算。
        entries = [{"ip_address": "10.9.9.9", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        rule = make_exclusion_rule(ip_pattern="10.9.9.0/24", ip_pattern_type="cidr")

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(rows=[]),  # compliance batch check
                make_exec_result(rows=[]),  # offline detection
            ],
            exclusion_rules=[rule],
        )

        with patch("app.services.event_emitter.emit_terminal_online", AsyncMock()) as online, \
             patch(
                 "app.services.compliance_service.ComplianceService.batch_check_compliance",
                 AsyncMock(),
             ) as batch_check:
            result = await service.process_arp_entries(entries, "lab")

        assert result.entries_added == 0
        assert result.entries_excluded == 1
        assert "excluded 1" in result.message
        mock_db.add.assert_not_called()
        online.assert_not_called()
        batch_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_exclusion_rule_purges_stale_unblocked_row(self, service, mock_db):
        # 规则建立后残留的未封锁记录在采集时自愈删除。
        entries = [{"ip_address": "10.9.9.9", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        rule = make_exclusion_rule(mac_address="AA-BB-CC-DD-EE-FF", mac_pattern_type="mac")
        stale = make_terminal(ip="10.9.9.9", mac_norm="AABBCCDDEEFF")

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=stale),  # stale lookup
                make_exec_result(rows=[]),       # compliance batch check
                make_exec_result(rows=[]),       # offline detection
            ],
            exclusion_rules=[rule],
        )

        result = await service.process_arp_entries(entries, "lab")

        assert result.entries_excluded == 1
        mock_db.delete.assert_awaited_once_with(stale)

    @pytest.mark.asyncio
    async def test_exclusion_rule_keeps_blocked_row(self, service, mock_db):
        # 已封锁终端保留：防火墙状态与黑名单一致性优先。
        entries = [{"ip_address": "10.9.9.9", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        rule = make_exclusion_rule(ip_pattern="10.9.9.9", ip_pattern_type="single_ip")
        stale = make_terminal(ip="10.9.9.9", mac_norm="AABBCCDDEEFF", status="blocked")

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=stale),
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
            exclusion_rules=[rule],
        )

        result = await service.process_arp_entries(entries, "lab")

        assert result.entries_excluded == 1
        mock_db.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exclusion_rule_keeps_actively_blacklisted_row(self, service, mock_db):
        # 存在有效黑名单的终端即使命中规则也保留，避免黑名单统计口径失真。
        entries = [{"ip_address": "10.9.9.9", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        rule = make_exclusion_rule(ip_pattern="10.9.9.0/24", ip_pattern_type="cidr")
        stale = make_terminal(ip="10.9.9.9", mac_norm="AABBCCDDEEFF")

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=stale),
                make_exec_result(rows=[]),
                make_exec_result(rows=[]),
            ],
            exclusion_rules=[rule],
            blacklist_ips=["10.9.9.9"],
        )

        result = await service.process_arp_entries(entries, "lab")

        assert result.entries_excluded == 1
        mock_db.delete.assert_not_awaited()


# ===========================================================================
# TestCollectFromApi
# ===========================================================================

class TestCollectFromApi:
    def _make_client(self, json_data):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=json_data)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(return_value=resp)
        client.post = AsyncMock(return_value=resp)
        return client

    def _api_source(self, **overrides):
        config = {"url": "http://api.example.com/arp", "method": "GET"}
        config.update(overrides)
        return make_source(source_type="arp_api", config=config)

    @pytest.mark.asyncio
    async def test_success_entries(self, service):
        source = self._api_source()
        client = self._make_client([{"ip": "1.1.1.1", "mac": "aa:bb:cc:dd:ee:ff"}])
        p, ds_mock = patch_ds_service()
        sync_ok = SyncResult(success=True, message="ok", entries_processed=1)

        with patch("httpx.AsyncClient", return_value=client), p, \
             patch.object(service, "process_arp_entries", AsyncMock(return_value=sync_ok)) as proc:
            result = await service.collect_from_api(source)

        assert result is sync_ok
        proc.assert_called_once()
        ds_mock.update_sync_status.assert_called_once_with(source.id, "success")

    @pytest.mark.asyncio
    async def test_no_entries(self, service):
        source = self._api_source()
        client = self._make_client([])
        p, ds_mock = patch_ds_service()

        with patch("httpx.AsyncClient", return_value=client), p:
            result = await service.collect_from_api(source)

        assert result.success is True
        assert result.entries_processed == 0
        ds_mock.update_sync_status.assert_called_once_with(source.id, "success")

    @pytest.mark.asyncio
    async def test_post_method(self, service):
        source = self._api_source(method="POST")
        client = self._make_client([])
        p, _ = patch_ds_service()

        with patch("httpx.AsyncClient", return_value=client), p:
            await service.collect_from_api(source)

        client.post.assert_called_once()
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_bearer_auth_header(self, service):
        source = self._api_source(auth_type="bearer", token="tok123", headers={})
        client = self._make_client([])
        p, _ = patch_ds_service()

        with patch("httpx.AsyncClient", return_value=client), p:
            await service.collect_from_api(source)

        assert source.config["headers"]["Authorization"] == "Bearer tok123"

    @pytest.mark.asyncio
    async def test_custom_header_auth(self, service):
        source = self._api_source(auth_type="header", token="tok456", header_name="X-Custom", headers={})
        client = self._make_client([])
        p, _ = patch_ds_service()

        with patch("httpx.AsyncClient", return_value=client), p:
            await service.collect_from_api(source)

        assert source.config["headers"]["X-Custom"] == "tok456"

    @pytest.mark.asyncio
    async def test_exception(self, service):
        source = self._api_source()
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.get = AsyncMock(side_effect=Exception("http boom"))
        p, ds_mock = patch_ds_service()

        with patch("httpx.AsyncClient", return_value=client), p:
            result = await service.collect_from_api(source)

        assert result.success is False
        assert result.message == "API collection failed: http boom"
        ds_mock.update_sync_status.assert_called_once_with(
            source.id, "failed", "API collection failed: http boom"
        )


# ===========================================================================
# TestCollectFromSsh
# ===========================================================================

class TestCollectFromSsh:
    @pytest.mark.asyncio
    async def test_success_entries(self, service):
        source = make_source(source_type="arp_ssh")
        p, ds_mock = patch_ds_service()
        sync_ok = SyncResult(success=True, message="ok", entries_processed=1)

        with patch("asyncio.to_thread", AsyncMock(return_value="raw output")), p, \
             patch.object(service, "_parse_arp_output", return_value=[
                 {"ip_address": "1.1.1.1", "mac_address": "AA-11-BB-22-CC-33"}
             ]), \
             patch.object(service, "process_arp_entries", AsyncMock(return_value=sync_ok)) as proc:
            result = await service.collect_from_ssh(source)

        assert result is sync_ok
        proc.assert_called_once()
        ds_mock.update_sync_status.assert_called_once_with(source.id, "success")

    @pytest.mark.asyncio
    async def test_no_entries(self, service):
        source = make_source(source_type="arp_ssh")
        p, ds_mock = patch_ds_service()

        with patch("asyncio.to_thread", AsyncMock(return_value="no ips")), p, \
             patch.object(service, "_parse_arp_output", return_value=[]):
            result = await service.collect_from_ssh(source)

        assert result.success is True
        assert result.entries_processed == 0
        ds_mock.update_sync_status.assert_called_once_with(source.id, "success")

    @pytest.mark.asyncio
    async def test_import_error(self, service):
        source = make_source(source_type="arp_ssh")
        p, ds_mock = patch_ds_service()

        with patch("asyncio.to_thread", AsyncMock(side_effect=ImportError("netmiko"))), p:
            result = await service.collect_from_ssh(source)

        assert result.success is False
        assert result.message == "netmiko library not installed"
        ds_mock.update_sync_status.assert_called_once_with(
            source.id, "failed", "netmiko library not installed"
        )

    @pytest.mark.asyncio
    async def test_generic_exception(self, service):
        source = make_source(source_type="arp_ssh")
        p, ds_mock = patch_ds_service()

        with patch("asyncio.to_thread", AsyncMock(side_effect=Exception("boom"))), p:
            result = await service.collect_from_ssh(source)

        assert result.success is False
        assert result.message == "SSH collection failed: boom"
        ds_mock.update_sync_status.assert_called_once_with(
            source.id, "failed", "SSH collection failed: boom"
        )


# ===========================================================================
# TestRunScheduledCollection
# ===========================================================================

class TestRunScheduledCollection:
    def _set_sources(self, mock_db, sources):
        result = MagicMock()
        result.scalars.return_value.all.return_value = sources
        mock_db.execute = AsyncMock(return_value=result)

    @pytest.mark.asyncio
    async def test_no_sources(self, service, mock_db):
        self._set_sources(mock_db, [])
        with patch.object(service, "collect_from_ssh", AsyncMock()) as ssh, \
             patch.object(service, "collect_from_api", AsyncMock()) as api:
            await service.run_scheduled_collection()

        ssh.assert_not_called()
        api.assert_not_called()

    @pytest.mark.asyncio
    async def test_collect_ssh(self, service, mock_db):
        src = make_source(source_type="arp_ssh", tag="s1")
        self._set_sources(mock_db, [src])
        sync_ok = SyncResult(success=True, message="ok")

        with patch.object(service, "collect_from_ssh", AsyncMock(return_value=sync_ok)) as coll, \
             patch.object(service, "collect_from_api", AsyncMock()) as api, \
             patch("app.core.crypto.decrypt_config", return_value=src.config):
            await service.run_scheduled_collection()

        coll.assert_called_once_with(src)
        api.assert_not_called()

    @pytest.mark.asyncio
    async def test_collect_api(self, service, mock_db):
        src = make_source(source_type="arp_api", tag="a1", config={"url": "http://x"})
        self._set_sources(mock_db, [src])
        sync_ok = SyncResult(success=True, message="ok")

        with patch.object(service, "collect_from_api", AsyncMock(return_value=sync_ok)) as coll, \
             patch.object(service, "collect_from_ssh", AsyncMock()) as ssh, \
             patch("app.core.crypto.decrypt_config", return_value=src.config):
            await service.run_scheduled_collection()

        coll.assert_called_once_with(src)
        ssh.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_unknown_type(self, service, mock_db):
        src = make_source(source_type="sangfor", tag="fw", config={"key": "v"})
        self._set_sources(mock_db, [src])

        with patch.object(service, "collect_from_ssh", AsyncMock()) as ssh, \
             patch.object(service, "collect_from_api", AsyncMock()) as api, \
             patch("app.core.crypto.decrypt_config", return_value=src.config):
            await service.run_scheduled_collection()

        ssh.assert_not_called()
        api.assert_not_called()

    @pytest.mark.asyncio
    async def test_source_exception_isolated(self, service, mock_db):
        src1 = make_source(source_type="arp_ssh", tag="s1")
        src2 = make_source(source_type="arp_ssh", tag="s2")
        self._set_sources(mock_db, [src1, src2])

        with patch.object(
            service, "collect_from_ssh",
            AsyncMock(side_effect=[Exception("boom"), SyncResult(success=True, message="ok")]),
        ) as coll, \
             patch("app.core.crypto.decrypt_config", return_value={"host": "x"}):
            await service.run_scheduled_collection()

        assert coll.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_source_config_skips_decrypt(self, service, mock_db):
        src = make_source(source_type="arp_ssh", tag="s1")
        src.config = None  # empty config -> decrypt skipped
        self._set_sources(mock_db, [src])

        with patch.object(service, "collect_from_ssh", AsyncMock(return_value=SyncResult(success=True, message="ok"))) as ssh, \
             patch.object(service, "collect_from_api", AsyncMock()) as api, \
             patch("app.core.crypto.decrypt_config") as decrypt:
            await service.run_scheduled_collection()

        ssh.assert_called_once_with(src)
        api.assert_not_called()
        decrypt.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_result_errors_logged(self, service, mock_db):
        src = make_source(source_type="arp_ssh", tag="s1")
        self._set_sources(mock_db, [src])

        sync_err = SyncResult(success=False, message="fail", errors=["err1", "err2"])
        with patch.object(service, "collect_from_ssh", AsyncMock(return_value=sync_err)) as ssh, \
             patch.object(service, "collect_from_api", AsyncMock()) as api, \
             patch("app.core.crypto.decrypt_config", return_value=src.config), \
             patch("app.services.arp_collector_service.logger.error") as err_logger:
            await service.run_scheduled_collection()

        ssh.assert_called_once_with(src)
        api.assert_not_called()
        err_logger.assert_any_call("  Error: err1")
        err_logger.assert_any_call("  Error: err2")
