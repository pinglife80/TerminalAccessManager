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

from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.data_source import DataSource
from app.models.terminal import Terminal, TerminalStatus
from app.schemas.data_source import ComplianceCheckResult, SyncResult
from app.services.arp_collector_service import ArpCollectorService


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


def make_exec_result(scalar=None, rows=None):
    """Build a mock SQLAlchemy Result supporting scalar_one_or_none / scalars().all()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    if rows is not None:
        result.scalars.return_value.all.return_value = rows
    return result


def set_exec_sequence(mock_db, results):
    """Make mock_db.execute replay a fixed sequence of Result mocks."""
    it = iter(results)

    async def _side_effect(stmt):
        try:
            return next(it)
        except StopIteration:
            return make_exec_result()

    mock_db.execute = AsyncMock(side_effect=_side_effect)


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
        stale.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[stale]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
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
        recent.updated_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[recent]),
            ],
        )

        fixed_now = datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)  # 60s ago
        with patch("app.core.timezone.now_utc", return_value=fixed_now), \
             patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline:
            await service.process_arp_entries(entries, "lab")

        offline.assert_not_called()

    @pytest.mark.asyncio
    async def test_offline_detection_skip_null_updated_at(self, service, mock_db):
        entries = [{"ip_address": "10.0.0.1", "mac_address": "aa:bb:cc:dd:ee:ff"}]
        existing = make_terminal(ip="10.0.0.1", mac_norm="AABBCCDDEEFF")
        null_ts = make_terminal(ip="10.0.0.2", mac_norm="112233445566")  # updated_at None

        set_exec_sequence(
            mock_db,
            [
                make_exec_result(scalar=existing),
                make_exec_result(rows=[]),
                make_exec_result(rows=[null_ts]),
            ],
        )

        with patch("app.services.config_service.get_config_value", AsyncMock(side_effect=[300, 3])), \
             patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()) as offline:
            await service.process_arp_entries(entries, "lab")

        offline.assert_not_called()


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