"""
Comprehensive unit tests for FirewallReconciliationService.

All database calls and external Sangfor API calls are mocked so the tests
do NOT require Docker, PostgreSQL, or Redis to be running.

Key principles under test:
- Firewall actual state is the authoritative source of truth for "blocked".
- Reconciliation runs PER FIREWALL independently.
- Missing DB entries are created; missing firewall blocks are re-blocked.
- Never unblocks based solely on reconciliation mismatch.
- 0-IP responses are probed and conservatively skipped to prevent data loss.
- Only Terminal.status (firewall block state) is repaired; compliance_status is
  owned exclusively by the compliance calculation logic.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.blacklist import Blacklist
from app.models.terminal import Terminal, TerminalStatus
from app.services.firewall_reconciliation_service import FirewallReconciliationService
from app.services.sangfor_service import SangforService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_firewall(tag="fw1", config=None):
    """Create a mock enabled Sangfor DataSource."""
    fw = MagicMock()
    fw.type = "sangfor"
    fw.tag = tag
    fw.enabled = True
    fw.config = config if config is not None else {
        "base_url": "https://fw.example.com",
        "username": "admin",
        "password": "secret",
    }
    return fw


def make_terminal(
    ip="10.0.0.1",
    mac="AA:BB:CC:DD:EE:FF",
    status="unblocked",
    compliance_status="unknown",
    source_tag="lab",
    mac_norm="AABBCCDDEEFF",
):
    """Create a mock Terminal object."""
    t = MagicMock(spec=Terminal)
    t.ip_address = ip
    t.mac_address = mac
    t.mac_address_normalized = mac_norm
    t.status = status
    t.compliance_status = compliance_status
    t.source_tag = source_tag
    t.firewall_tag = None
    return t


def make_blacklist(ip="10.0.0.1", firewall_tag="fw1", reason=None):
    """Create a mock active Blacklist entry."""
    b = MagicMock(spec=Blacklist)
    b.ip_address = ip
    b.firewall_tag = firewall_tag
    b.reason = reason
    b.auto_unblocked = False
    b.unblocked_at = None
    return b


def created_blacklists(mock_db):
    """Return value objects for Blacklist INSERTs passed to db.execute.

    The production code inserts via ``pg_insert(Blacklist).values(...)`` executed
    through ``db.execute`` instead of ``db.add``. Each returned object exposes the
    inserted column values as attributes (e.g. ``.mac_address``).
    """
    entries = []
    for call in mock_db.execute.call_args_list:
        stmt = call.args[0] if call.args else None
        table = getattr(stmt, "table", None)
        if table is None or getattr(table, "name", None) != "blacklist":
            continue
        entries.append(SimpleNamespace(**dict(stmt.compile().params)))
    return entries


def blocked_ips_response(ips):
    """Build a Sangfor get_blocked_ips response dict."""
    return {"code": 0, "data": {"items": [{"url": ip} for ip in ips]}}


def make_sangfor_service(ips=(), find_entry=None, block_result=None):
    """Create a mock SangforService with async API methods."""
    svc = MagicMock()
    svc.get_blocked_ips = AsyncMock(return_value=blocked_ips_response(ips))
    svc._find_blacklist_entry = AsyncMock(return_value=find_entry)
    svc.block_ip = AsyncMock(
        return_value=block_result if block_result is not None else {"code": 0}
    )
    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(mock_async_session):
    """Mock AsyncSession with correct sync/async method split."""
    return mock_async_session


@pytest.fixture
def service(mock_db):
    """FirewallReconciliationService backed by a mock AsyncSession."""
    return FirewallReconciliationService(mock_db)


@pytest.fixture
def reconcile_env(mock_db):
    """Reconcile environment with common externals patched.

    Patches the module-level ``decrypt_config`` import and the Sangfor
    ``get_cached_service`` classmethod so reconcile() can run without a
    real firewall.
    """
    service = FirewallReconciliationService(mock_db)
    mock_sangfor = make_sangfor_service()
    with patch(
        "app.services.firewall_reconciliation_service.decrypt_config",
        return_value={
            "base_url": "https://fw.example.com",
            "username": "admin",
            "password": "secret",
            "verify_ssl": True,
            "ca_bundle": "",
        },
    ), patch.object(
        SangforService, "get_cached_service", new=AsyncMock(return_value=mock_sangfor)
    ):
        yield SimpleNamespace(service=service, sangfor=mock_sangfor)


# ===========================================================================
# TestParseBlockedIps
# ===========================================================================

class TestParseBlockedIps:
    def test_invalid_responses_return_empty(self, service):
        assert service._parse_blocked_ips(None) == set()
        assert service._parse_blocked_ips("not-a-dict") == set()
        assert service._parse_blocked_ips({}) == set()
        assert service._parse_blocked_ips({"data": "x"}) == set()
        assert service._parse_blocked_ips({"data": {"items": "x"}}) == set()

    def test_parses_url_items(self, service):
        response = {"data": {"items": [{"url": "1.1.1.1"}, {"url": "2.2.2.2"}]}}
        assert service._parse_blocked_ips(response) == {"1.1.1.1", "2.2.2.2"}

    def test_falls_back_to_srcIP_and_ip(self, service):
        response = {
            "data": {
                "items": [
                    {"srcIP": "3.3.3.3"},
                    {"ip": "4.4.4.4"},
                    {"url": "5.5.5.5"},
                ]
            }
        }
        assert service._parse_blocked_ips(response) == {"3.3.3.3", "4.4.4.4", "5.5.5.5"}

    def test_skips_items_without_ip(self, service):
        response = {"data": {"items": [{"foo": "bar"}, "not-a-dict", {"url": "6.6.6.6"}]}}
        assert service._parse_blocked_ips(response) == {"6.6.6.6"}


# ===========================================================================
# TestRepairStaleTerminalStatus
# ===========================================================================

class TestRepairStaleTerminalStatus:
    @pytest.mark.asyncio
    async def test_no_orphaned_terminals_returns_zero(self, service, mock_db):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        fixed = await service._repair_stale_terminal_status()

        assert fixed == 0
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_orphaned_blocked_terminal(self, service, mock_db):
        terminal = make_terminal(status="blocked", compliance_status="non_compliant")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [terminal]
        mock_db.execute = AsyncMock(return_value=result)

        fixed = await service._repair_stale_terminal_status()

        assert fixed == 1
        assert terminal.status == TerminalStatus.UNBLOCKED.value
        assert terminal.firewall_tag is None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_modify_compliance_status(self, service, mock_db):
        terminal = make_terminal(status="blocked", compliance_status="non_compliant")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [terminal]
        mock_db.execute = AsyncMock(return_value=result)

        await service._repair_stale_terminal_status()

        # Compliance status is owned solely by compliance calculation logic.
        assert terminal.compliance_status == "non_compliant"


# ===========================================================================
# TestGetDbActiveBlacklistByFirewall
# ===========================================================================

class TestGetDbActiveBlacklistByFirewall:
    @pytest.mark.asyncio
    async def test_groups_by_firewall_tag(self, service, mock_db):
        result = MagicMock()
        result.all.return_value = [
            ("10.0.0.1", "aa:bb:cc:dd:ee:ff", "AABBCCDDEEFF", "fw1"),
            ("10.0.0.2", "aa:bb:cc:dd:ee:ff", "AABBCCDDEEFF", "fw2"),
            ("10.0.0.3", "aa:bb:cc:dd:ee:ff", "AABBCCDDEEFF", "fw1"),
        ]
        mock_db.execute = AsyncMock(return_value=result)

        grouped = await service._get_db_active_blacklist_by_firewall()

        assert grouped == {"fw1": {"10.0.0.1", "10.0.0.3"}, "fw2": {"10.0.0.2"}}

    @pytest.mark.asyncio
    async def test_empty_rows_return_empty_dict(self, service, mock_db):
        result = MagicMock()
        result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        grouped = await service._get_db_active_blacklist_by_firewall()

        assert grouped == {}


# ===========================================================================
# TestCreateDbEntriesForFirewall
# ===========================================================================

class TestCreateDbEntriesForFirewall:
    def _patch_deps(self, whitelist_match=None):
        """Patch ConfigService and ComplianceService used inside the method."""
        config_svc = MagicMock()
        config_svc.get = AsyncMock(return_value="30d")
        comp_svc = MagicMock()
        comp_svc._load_whitelist_cache = AsyncMock(return_value=[])
        comp_svc._match_whitelist_in_memory = MagicMock(return_value=whitelist_match)
        return (
            patch("app.services.config_service.ConfigService", return_value=config_svc),
            patch("app.services.compliance_service.ComplianceService", return_value=comp_svc),
        )

    @pytest.mark.asyncio
    async def test_creates_entry_with_terminal(self, service, mock_db):
        terminal = make_terminal(status="unblocked")
        term_result = MagicMock()
        term_result.scalars.return_value.first.return_value = terminal
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        calls = iter([term_result, existing_result])

        async def side_effect(stmt):
            return next(calls, MagicMock())

        mock_db.execute = AsyncMock(side_effect=side_effect)

        with self._patch_deps()[0], self._patch_deps()[1]:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 1
        assert terminal.status == TerminalStatus.BLOCKED.value

        bl_objs = created_blacklists(mock_db)
        assert len(bl_objs) == 1
        entry = bl_objs[0]
        assert entry.mac_address == "AA:BB:CC:DD:EE:FF"
        assert entry.mac_address_normalized == "AABBCCDDEEFF"
        assert entry.source_tag == "lab"
        assert entry.firewall_tag == "fw1"

    @pytest.mark.asyncio
    async def test_creates_entry_without_terminal(self, service, mock_db):
        term_result = MagicMock()
        term_result.scalars.return_value.first.return_value = None
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        calls = iter([term_result, existing_result])

        async def side_effect(stmt):
            return next(calls, MagicMock())

        mock_db.execute = AsyncMock(side_effect=side_effect)

        with self._patch_deps()[0], self._patch_deps()[1]:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 1
        bl_objs = created_blacklists(mock_db)
        assert len(bl_objs) == 1
        entry = bl_objs[0]
        assert entry.mac_address is None
        assert entry.mac_address_normalized is None
        assert entry.source_tag == "reconciliation"

    @pytest.mark.asyncio
    async def test_skips_whitelisted_bypass_terminal(self, service, mock_db):
        terminal = make_terminal(status="unblocked", compliance_status="bypass")
        term_result = MagicMock()
        term_result.scalar_one_or_none.return_value = terminal

        mock_db.execute = AsyncMock(return_value=term_result)

        p1, p2 = self._patch_deps(whitelist_match={"match_type": "mac"})
        with p1, p2:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 0
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_existing_entry(self, service, mock_db):
        terminal = make_terminal(status="unblocked")
        term_result = MagicMock()
        term_result.scalar_one_or_none.return_value = terminal
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = make_blacklist()

        calls = iter([term_result, existing_result])

        async def side_effect(stmt):
            return next(calls, MagicMock())

        mock_db.execute = AsyncMock(side_effect=side_effect)

        with self._patch_deps()[0], self._patch_deps()[1]:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 0
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_when_whitelisted_but_not_bypass(self, service, mock_db):
        # Whitelist match only skips when compliance_status == "bypass".
        terminal = make_terminal(status="blocked", compliance_status="compliant")
        term_result = MagicMock()
        term_result.scalar_one_or_none.return_value = terminal
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        calls = iter([term_result, existing_result])

        async def side_effect(stmt):
            return next(calls, MagicMock())

        mock_db.execute = AsyncMock(side_effect=side_effect)

        p1, p2 = self._patch_deps(whitelist_match={"match_type": "ip"})
        with p1, p2:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 1

    @pytest.mark.asyncio
    async def test_unknown_terminal_converges_to_non_compliant(self, service, mock_db):
        # A Pending Check (unknown) terminal discovered on the firewall is de-facto
        # non-compliant, so reconciliation must converge it and create the DB entry.
        terminal = make_terminal(status="unblocked", compliance_status="unknown")
        term_result = MagicMock()
        term_result.scalars.return_value.first.return_value = terminal
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        calls = iter([term_result, existing_result])

        async def side_effect(stmt):
            return next(calls, MagicMock())

        mock_db.execute = AsyncMock(side_effect=side_effect)

        with self._patch_deps()[0], self._patch_deps()[1]:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 1
        assert terminal.status == TerminalStatus.BLOCKED.value
        assert terminal.compliance_status == "non_compliant"
        assert terminal.wl_match_type is None

    @pytest.mark.asyncio
    async def test_unknown_terminal_with_whitelist_converges_to_bypass(self, service, mock_db):
        # A Pending Check (unknown) terminal whose IP matches a whitelist must converge
        # to 'bypass' and skip Blacklist creation (no active block for whitelisted IP).
        terminal = make_terminal(status="unblocked", compliance_status="unknown")
        term_result = MagicMock()
        term_result.scalars.return_value.first.return_value = terminal

        mock_db.execute = AsyncMock(return_value=term_result)

        p1, p2 = self._patch_deps(whitelist_match={"match_type": "mac"})
        with p1, p2:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 0
        assert terminal.compliance_status == "bypass"
        assert terminal.wl_match_type == "mac"
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_entry_exception_isolated(self, service, mock_db):
        # A DB error for one IP must not crash the whole method.
        mock_db.execute = AsyncMock(side_effect=Exception("db error"))

        with self._patch_deps()[0], self._patch_deps()[1]:
            created = await service._create_db_entries_for_firewall("fw1", {"10.0.0.1"})

        assert created == 0
        mock_db.add.assert_not_called()


# ===========================================================================
# TestReblockOnFirewall
# ===========================================================================

class TestReblockOnFirewall:
    @pytest.mark.asyncio
    async def test_reblock_success(self, service):
        bl_result = MagicMock()
        bl_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=bl_result)

        svc = make_sangfor_service(block_result={"code": 0})

        reblocked = await service._reblock_on_firewall("fw1", svc, {"10.0.0.1"})

        assert reblocked == 1
        svc.block_ip.assert_called_once()

    @pytest.mark.asyncio
    async def test_reblock_failure(self, service):
        bl_result = MagicMock()
        bl_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=bl_result)

        svc = make_sangfor_service(block_result={"code": 1, "message": "boom"})

        reblocked = await service._reblock_on_firewall("fw1", svc, {"10.0.0.1"})

        assert reblocked == 0

    @pytest.mark.asyncio
    async def test_reblock_uses_blacklist_reason(self, service):
        bl_result = MagicMock()
        bl_result.scalars.return_value.first.return_value = make_blacklist(
            reason="Reconciliation: re-block (DB says should be blocked)"
        )
        service.db.execute = AsyncMock(return_value=bl_result)

        svc = make_sangfor_service(block_result={"code": 0})

        await service._reblock_on_firewall("fw1", svc, {"10.0.0.1"})

        svc.block_ip.assert_called_once()
        kwargs = svc.block_ip.call_args.kwargs
        assert kwargs["reason"] == "Reconciliation: re-block (DB says should be blocked)"
        assert kwargs["source_tag"] == "fw1"

    @pytest.mark.asyncio
    async def test_reblock_without_blacklist_entry_uses_default_reason(self, service):
        bl_result = MagicMock()
        bl_result.scalars.return_value.first.return_value = None
        service.db.execute = AsyncMock(return_value=bl_result)

        svc = make_sangfor_service(block_result={"code": 0})

        await service._reblock_on_firewall("fw1", svc, {"10.0.0.1"})

        kwargs = svc.block_ip.call_args.kwargs
        assert kwargs["reason"] == "Reconciliation: re-block (DB says should be blocked)"

    @pytest.mark.asyncio
    async def test_reblock_exception_isolated(self, service):
        bl_result = MagicMock()
        bl_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=bl_result)

        svc = make_sangfor_service()
        svc.block_ip = AsyncMock(side_effect=Exception("block failed"))

        reblocked = await service._reblock_on_firewall("fw1", svc, {"10.0.0.1"})

        assert reblocked == 0

    @pytest.mark.asyncio
    async def test_reblock_unknown_terminal_converges_to_non_compliant(self, service):
        # Re-blocking an 'unknown' (Pending Check) terminal that was 'unblocked' must
        # flip it to blocked AND converge compliance to non_compliant (blocked ⟺ non_compliant).
        terminal = make_terminal(status="unblocked", compliance_status="unknown")
        bl_entry = make_blacklist(reason="test reason")

        bl_result = MagicMock()
        bl_result.scalars.return_value.first.return_value = bl_entry
        term_result = MagicMock()
        term_result.scalars.return_value.first.return_value = terminal

        calls = iter([bl_result, term_result])

        async def side_effect(stmt):
            return next(calls, MagicMock())

        service.db.execute = AsyncMock(side_effect=side_effect)
        svc = make_sangfor_service(block_result={"code": 0})

        reblocked = await service._reblock_on_firewall("fw1", svc, {"10.0.0.1"})

        assert reblocked == 1
        assert terminal.status == TerminalStatus.BLOCKED.value
        assert terminal.firewall_tag == "fw1"
        assert terminal.compliance_status == "non_compliant"
        assert terminal.wl_match_type is None

    @pytest.mark.asyncio
    async def test_reblock_already_blocked_unknown_terminal_converges(self, service):
        # A legacy 'blocked + unknown' terminal re-blocked here must still converge to
        # non_compliant, even though its status was already 'blocked' (no status flip).
        terminal = make_terminal(status="blocked", compliance_status="unknown")
        bl_entry = make_blacklist(reason="test reason")

        bl_result = MagicMock()
        bl_result.scalars.return_value.first.return_value = bl_entry
        term_result = MagicMock()
        term_result.scalars.return_value.first.return_value = terminal

        calls = iter([bl_result, term_result])

        async def side_effect(stmt):
            return next(calls, MagicMock())

        service.db.execute = AsyncMock(side_effect=side_effect)
        svc = make_sangfor_service(block_result={"code": 0})

        reblocked = await service._reblock_on_firewall("fw1", svc, {"10.0.0.1"})

        assert reblocked == 1
        assert terminal.status == TerminalStatus.BLOCKED.value
        assert terminal.compliance_status == "non_compliant"
        assert terminal.wl_match_type is None


# ===========================================================================
# TestReconcile
# ===========================================================================

class TestReconcile:
    @pytest.mark.asyncio
    async def test_no_firewalls_returns_empty(self, reconcile_env):
        service = reconcile_env.service
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(return_value=fw_result)

        with patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)) as repair:
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 0
        assert result["db_entry_count"] == 0
        assert result["created_in_db"] == 0
        assert result["reblocked_on_firewall"] == 0
        repair.assert_called_once()

    @pytest.mark.asyncio
    async def test_fully_synchronized(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response(["10.0.0.1"])
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock()) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock()) as reblock:
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 1
        assert result["db_entry_count"] == 1
        assert result["created_in_db"] == 0
        assert result["reblocked_on_firewall"] == 0
        create.assert_not_called()
        reblock.assert_not_called()
        service.db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_in_db_creates(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response(["10.0.0.1", "10.0.0.2"])
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock(return_value=2)) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock()) as reblock:
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 2
        assert result["created_in_db"] == 2
        assert result["missing_in_db"] == [("fw1", "10.0.0.2")]
        create.assert_called_once_with("fw1", {"10.0.0.2"})
        reblock.assert_not_called()
        service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_in_firewall_reblocks(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response(["10.0.0.1"])
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1", "10.0.0.2"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock()) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock(return_value=1)) as reblock:
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 1
        assert result["reblocked_on_firewall"] == 1
        assert result["missing_in_firewall"] == [("fw1", "10.0.0.2")]
        reblock.assert_called_once()
        create.assert_not_called()
        service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_zero_ip_probe_hit_skips(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response([])
        )
        reconcile_env.sangfor._find_blacklist_entry = AsyncMock(
            return_value={"url": "10.0.0.1", "description": "TAM-lab-x"}
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock()) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock()) as reblock:
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 0
        assert result["created_in_db"] == 0
        assert result["reblocked_on_firewall"] == 0
        assert len(result["firewall_errors"]) == 1
        assert result["firewall_errors"][0]["tag"] == "fw1"
        assert "列表接口异常" in result["firewall_errors"][0]["error"]
        create.assert_not_called()
        reblock.assert_not_called()
        service.db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_probe_ip_uses_full_ip(self, reconcile_env):
        # Regression: probe must use the full IP from db_entries_by_fw, not the
        # first character (next(iter(...))[0] bug -> "10.0.0.1" became "1").
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response([])
        )
        reconcile_env.sangfor._find_blacklist_entry = AsyncMock(
            return_value={"url": "10.0.0.1"}
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock()) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock()) as reblock:
            await service.reconcile()

        # Probe must be queried with the full IP, not the single char "1".
        reconcile_env.sangfor._find_blacklist_entry.assert_called_once_with("10.0.0.1")
        create.assert_not_called()
        reblock.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_ip_probe_miss_skips(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response([])
        )
        reconcile_env.sangfor._find_blacklist_entry = AsyncMock(return_value=None)

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock()) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock()) as reblock:
            result = await service.reconcile()

        assert len(result["firewall_errors"]) == 1
        assert "未命中" in result["firewall_errors"][0]["error"]
        create.assert_not_called()
        reblock.assert_not_called()
        service.db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_firewall_query_exception_captured(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(side_effect=Exception("boom"))

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)) as repair:
            result = await service.reconcile()

        assert len(result["firewall_errors"]) == 1
        assert result["firewall_errors"][0]["tag"] == "fw1"
        assert result["firewall_errors"][0]["error"] == "boom"
        assert len(result["errors"]) == 1
        # Self-heal still runs even when a firewall query fails.
        repair.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_firewalls_aggregate(self, reconcile_env):
        service = reconcile_env.service
        fw1 = make_firewall("fw1")
        fw2 = make_firewall("fw2")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw1, fw2]
        service.db.execute = AsyncMock(return_value=fw_result)

        # First firewall returns its IP; second firewall returns its own IP.
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            side_effect=[
                blocked_ips_response(["10.0.0.1"]),
                blocked_ips_response(["10.0.0.2"]),
            ]
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}, "fw2": {"10.0.0.2"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock()) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock()) as reblock:
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 2
        assert result["db_entry_count"] == 2
        create.assert_not_called()
        reblock.assert_not_called()
        service.db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_ip_probe_error_skips(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response([])
        )
        reconcile_env.sangfor._find_blacklist_entry = AsyncMock(
            side_effect=Exception("probe fail")
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)), \
           patch.object(service, "_create_db_entries_for_firewall", AsyncMock()) as create, \
           patch.object(service, "_reblock_on_firewall", AsyncMock()) as reblock:
            result = await service.reconcile()

        # Probe failure leaves probe_hit False, so the miss reason is reported.
        assert len(result["firewall_errors"]) == 1
        assert "未命中" in result["firewall_errors"][0]["error"]
        create.assert_not_called()
        reblock.assert_not_called()

    @pytest.mark.asyncio
    async def test_outer_exception_captured(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(side_effect=Exception("db group fail")),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)) as repair:
            result = await service.reconcile()

        assert "db group fail" in result["errors"][0]
        repair.assert_called_once()

    @pytest.mark.asyncio
    async def test_repair_exception_does_not_crash(self, reconcile_env):
        service = reconcile_env.service
        fw = make_firewall("fw1")
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response(["10.0.0.1"])
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(
            service, "_repair_stale_terminal_status",
            AsyncMock(side_effect=Exception("heal fail")),
        ):
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_config_falsy_branch(self, reconcile_env):
        # A falsy (empty) config skips decryption and still reconciles.
        service = reconcile_env.service
        fw = make_firewall("fw1", config={})
        fw_result = MagicMock()
        fw_result.scalars.return_value.all.return_value = [fw]
        service.db.execute = AsyncMock(return_value=fw_result)
        reconcile_env.sangfor.get_blocked_ips = AsyncMock(
            return_value=blocked_ips_response(["10.0.0.1"])
        )

        with patch.object(
            service, "_get_db_active_blacklist_by_firewall",
            AsyncMock(return_value={"fw1": {"10.0.0.1"}}),
        ), patch.object(service, "_repair_stale_terminal_status", AsyncMock(return_value=0)):
            result = await service.reconcile()

        assert result["firewall_ip_count"] == 1