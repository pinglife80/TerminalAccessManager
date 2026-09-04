"""
Comprehensive unit tests for ComplianceService.

All database calls and external API calls are mocked so the tests
do NOT require Docker, PostgreSQL, or Redis to be running.
"""

import contextlib
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.blacklist import Blacklist
from app.models.terminal import Terminal, TerminalStatus
from app.models.whitelist import Whitelist
from app.services.compliance_service import (
    COMPLIANCE_RECALC_LOCK_KEY,
    COMPLIANCE_RECALC_LOCK_TTL,
    IPGUARD_BACKUP_CACHE_PREFIX,
    IPGUARD_CACHE_PREFIX,
    SCOPE_CACHE_KEY,
    WHITELIST_CACHE_KEY,
    ComplianceService,
    _acquire_compliance_lock,
    _release_compliance_lock,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_mock_terminal(
    ip="192.168.1.100",
    mac="AA:BB:CC:DD:EE:FF",
    status="unblocked",
    compliance_status="unknown",
    source_tag="lab",
    firewall_tag=None,
    comments="",
    wl_match_type=None,
    mac_address_normalized=None,
):
    """Create a mock Terminal object with sensible defaults."""
    # Plain MagicMock (no spec) keeps the mock flexible for attribute assignment.
    t = MagicMock()
    t.ip_address = ip
    t.mac_address = mac
    t.mac_address_normalized = mac_address_normalized or mac.replace(':', '').replace('-', '').replace('.', '').upper()
    t.status = status
    t.compliance_status = compliance_status
    t.source_tag = source_tag
    t.firewall_tag = firewall_tag
    t.comments = comments
    t.wl_match_type = wl_match_type
    t.non_compliant_confirm_count = 0
    t.compliant_confirm_count = 0
    t.ip_changed_at = None
    return t


def create_mock_blacklist(
    ip="192.168.1.100",
    mac="AA:BB:CC:DD:EE:FF",
    mac_normalized="AABBCCDDEEFF",
    firewall_tag="fw1",
    source_tag="lab",
    is_auto_blocked=True,
    auto_unblocked=False,
    expires_at=None,
):
    """Create a mock Blacklist object with sensible defaults."""
    b = MagicMock(spec=Blacklist)
    b.ip_address = ip
    b.mac_address = mac
    b.mac_address_normalized = mac_normalized
    b.firewall_tag = firewall_tag
    b.source_tag = source_tag
    b.is_auto_blocked = is_auto_blocked
    b.auto_unblocked = auto_unblocked
    b.expires_at = expires_at or datetime.now(UTC) + timedelta(days=30)
    b.reason = "Auto-blocked: non-compliant"
    b.blocked_by = "system"
    return b


def create_mock_whitelist(
    mac_address=None,
    ip_pattern=None,
    pattern_type="single_ip",
    comments=None,
):
    """Create a mock Whitelist object."""
    w = MagicMock(spec=Whitelist)
    w.mac_address = mac_address
    w.ip_pattern = ip_pattern
    w.pattern_type = pattern_type
    w.comments = comments
    return w


def make_result(one=None, all_rows=None, scalars_all=None):
    """Build a MagicMock SQLAlchemy result with the accessors _apply_compliance_result uses.

    - scalar_one_or_none() -> `one`
    - all()                 -> `all_rows`
    - scalars().all()       -> `scalars_all`
    """
    r = MagicMock()
    r.scalar_one_or_none.return_value = one
    r.all.return_value = [] if all_rows is None else all_rows
    if scalars_all is not None:
        _scalars = MagicMock()
        _scalars.all.return_value = scalars_all
        r.scalars.return_value = _scalars
    return r


def scripted_execute(results):
    """Return an AsyncMock execute that pops scripted results in order.

    Exhausted scripts fall back to an empty result so unexpected extra
    queries yield None / [] rather than a truthy MagicMock.
    """
    queue = list(results)

    async def side_effect(stmt):
        if queue:
            return queue.pop(0)
        return make_result(one=None, all_rows=[], scalars_all=[])

    return AsyncMock(side_effect=side_effect)


@contextlib.contextmanager
def apply_result_mocks(service, mock_db, results, **kw):
    """Patch _apply_compliance_result collaborators and script db.execute.

    Args:
        results: ordered list of result mocks for self.db.execute (see make_result).

    Keyword overrides (defaults in brackets):
        bound_fw_tags (["fw1"])        -> _get_bound_firewall_tags
        unblock_on_firewall (True)     -> bool or async callable
        block_on_firewall (True)       -> bool or async callable
        block_time ("30d")             -> _get_block_time
        cooldown_minutes (10)          -> _get_cooldown_minutes
        scope_data ([])                -> _load_scope_cache
        ipguard_data ({})              -> _load_all_ipguard_cache

    Yields a namespace whose emit_compliant / emit_non_compliant attributes are
    AsyncMocks patched onto app.services.event_emitter.
    """
    bound_fw_tags = kw.get("bound_fw_tags", ["fw1"])
    unblock = kw.get("unblock_on_firewall", True)
    block = kw.get("block_on_firewall", True)
    block_time = kw.get("block_time", "30d")
    cooldown = kw.get("cooldown_minutes", 10)
    scope = kw.get("scope_data", [])
    ipguard = kw.get("ipguard_data", {})

    mock_db.execute = scripted_execute(results)

    emit_compliant = AsyncMock()
    emit_non_compliant = AsyncMock()

    unblock_patch = (
        patch.object(service, "_unblock_on_firewall", side_effect=unblock)
        if callable(unblock)
        else patch.object(service, "_unblock_on_firewall", return_value=unblock)
    )
    block_patch = (
        patch.object(service, "_block_on_firewall", side_effect=block)
        if callable(block)
        else patch.object(service, "_block_on_firewall", return_value=block)
    )

    with patch.object(service, "log_action", return_value=None), \
         patch.object(service, "_get_bound_firewall_tags", return_value=bound_fw_tags), \
         patch.object(service, "_get_block_time", return_value=block_time), \
         patch.object(service, "_get_cooldown_minutes", return_value=cooldown), \
         patch.object(service, "_load_scope_cache", return_value=scope), \
         patch.object(service, "_load_all_ipguard_cache", return_value=ipguard), \
         unblock_patch, \
         block_patch, \
         patch("app.services.event_emitter.emit_terminal_compliant", emit_compliant), \
         patch("app.services.event_emitter.emit_terminal_non_compliant", emit_non_compliant):
        events = MagicMock()
        events.emit_compliant = emit_compliant
        events.emit_non_compliant = emit_non_compliant
        yield events


def created_blacklists(mock_db):
    """Return Blacklist instances passed to db.add during a test."""
    return [c[0][0] for c in mock_db.add.call_args_list if isinstance(c[0][0], Blacklist)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(mock_async_session):
    """Mock AsyncSession with correct sync/async method split."""
    return mock_async_session


@pytest.fixture
def service(mock_db):
    """ComplianceService instance backed by a mock DB."""
    return ComplianceService(mock_db)


# ===========================================================================
# TestComplianceStatusTransitions
# ===========================================================================

class TestComplianceStatusTransitions:
    """Tests for compliance_status transitions driven by check_compliance."""

    @pytest.mark.asyncio
    async def test_unknown_to_compliant(self, service):
        """Terminal with unknown status, matches IPGuard baseline -> compliant."""
        with patch.object(service, "_check_whitelist", return_value=None), \
             patch.object(service, "_check_ipguard", return_value=True), \
             patch.object(service, "_load_scope_cache", return_value=[]):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "compliant"
        assert "ipguard" in result["matched_sources"]
        assert result["whitelisted"] is False

    @pytest.mark.asyncio
    async def test_unknown_to_non_compliant(self, service):
        """Terminal with unknown status, no IPGuard match, no whitelist match -> non_compliant."""
        with patch.object(service, "_check_whitelist", return_value=None), \
             patch.object(service, "_check_ipguard", return_value=False), \
             patch.object(service, "_load_scope_cache", return_value=[]):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "non_compliant"
        assert result["matched_sources"] == []
        assert result["whitelisted"] is False

    @pytest.mark.asyncio
    async def test_unknown_to_bypass(self, service):
        """Terminal with unknown status, matches whitelist -> bypass."""
        wl_result = {"match_type": "mac", "comments": "test device"}
        with patch.object(service, "_check_whitelist", return_value=wl_result), \
             patch.object(service, "_check_ipguard", return_value=True), \
             patch.object(service, "_load_scope_cache", return_value=[]):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "bypass"
        assert result["whitelisted"] is True
        assert result["wl_match_type"] == "mac"
        # Even though IPGuard also matches, whitelist takes precedence
        assert "whitelist" in result["matched_sources"]

    @pytest.mark.asyncio
    async def test_compliant_to_non_compliant(self, service):
        """Terminal was compliant, IPGuard data changes -> non_compliant.

        Simulates a terminal that previously matched IPGuard but no longer does.
        """
        with patch.object(service, "_check_whitelist", return_value=None), \
             patch.object(service, "_check_ipguard", return_value=False), \
             patch.object(service, "_load_scope_cache", return_value=[]):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "non_compliant"

    @pytest.mark.asyncio
    async def test_non_compliant_to_bypass(self, service):
        """Terminal was non_compliant, added to whitelist -> bypass."""
        wl_result = {"match_type": "ip", "comments": "newly whitelisted"}
        with patch.object(service, "_check_whitelist", return_value=wl_result), \
             patch.object(service, "_check_ipguard", return_value=False), \
             patch.object(service, "_load_scope_cache", return_value=[]):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "bypass"
        assert result["whitelisted"] is True

    @pytest.mark.asyncio
    async def test_bypass_to_non_compliant(self, service):
        """Terminal was bypass, removed from whitelist -> non_compliant."""
        with patch.object(service, "_check_whitelist", return_value=None), \
             patch.object(service, "_check_ipguard", return_value=False), \
             patch.object(service, "_load_scope_cache", return_value=[]):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "non_compliant"
        assert result["whitelisted"] is False


# ===========================================================================
# TestAutoBlockTerminal
# ===========================================================================

class TestAutoBlockTerminal:
    """Tests for auto_block_non_compliant."""

    @pytest.mark.asyncio
    async def test_auto_block_creates_blacklist_with_mac_normalized(self, service, mock_db):
        """Auto-block creates Blacklist record with mac_address_normalized field."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        # Mock: no existing blacklisted IPs
        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []

        # Mock: non-compliant terminals
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]

        # Mock: DataSource query for firewall resolution
        mock_fw_source = MagicMock()
        mock_fw_source.enabled = True
        mock_fw_source.config = {"base_url": "https://fw.example.com", "username": "admin", "password": "pass"}
        ds_result_mock = MagicMock()
        ds_result_mock.scalar_one_or_none.return_value = mock_fw_source

        # Mock: idempotency check returns no existing blacklist entry
        idempotency_result_mock = MagicMock()
        idempotency_result_mock.scalar_one_or_none.return_value = None

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return nc_result_mock
            elif call_count["n"] == 3:
                # DataSource query for firewall resolution
                return ds_result_mock
            # Call 4+: idempotency check for existing blacklist entries
            return idempotency_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_sangfor = MagicMock()
        mock_sangfor.block_ip = AsyncMock(return_value={"code": 0})
        mock_sangfor.close = AsyncMock()

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch("app.services.sangfor_service.SangforService", return_value=mock_sangfor), \
             patch("app.core.crypto.decrypt_config", return_value={"base_url": "https://fw.example.com", "username": "admin", "password": "pass", "verify_ssl": True, "ca_bundle": ""}), \
             patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value={}):
            ds_instance = MagicMock()
            ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=["fw1"])
            ds_cls.return_value = ds_instance

            result = await service.auto_block_non_compliant("lab", block_time="30d")

        assert result.blocked == 1

        # Verify db.add was called with a Blacklist that has mac_address_normalized
        add_calls = mock_db.add.call_args_list
        blacklist_entries = [c[0][0] for c in add_calls if isinstance(c[0][0], Blacklist)]
        assert len(blacklist_entries) >= 1
        bl_entry = blacklist_entries[0]
        assert bl_entry.mac_address_normalized == "AABBCCDDEEFF"
        assert bl_entry.is_auto_blocked is True
        assert bl_entry.auto_unblocked is False
        assert bl_entry.firewall_tag == "fw1"

    @pytest.mark.asyncio
    async def test_auto_block_skips_already_blocked(self, service, mock_db):
        """Terminal already blocked -> no duplicate Blacklist record."""
        create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="blocked",  # Already blocked
        )

        # Mock: no existing blacklisted IPs
        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []

        # Mock: non-compliant terminals query returns empty because status == "blocked"
        # The SQL filter is Terminal.status != "blocked"
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = []

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            return nc_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 0
        assert result.total_non_compliant == 0

    @pytest.mark.asyncio
    async def test_auto_block_multiple_firewalls(self, service, mock_db):
        """Terminal has bindings to 2 firewalls -> Blacklist records created for both."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []

        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]

        # Mock: DataSource query for firewall resolution
        mock_fw_source = MagicMock()
        mock_fw_source.enabled = True
        mock_fw_source.config = {"base_url": "https://fw.example.com", "username": "admin", "password": "pass"}
        ds_result_mock = MagicMock()
        ds_result_mock.scalar_one_or_none.return_value = mock_fw_source

        # Mock: idempotency check returns no existing blacklist entry
        idempotency_result_mock = MagicMock()
        idempotency_result_mock.scalar_one_or_none.return_value = None

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return nc_result_mock
            elif call_count["n"] in (3, 4):
                # DataSource queries for firewall resolution (fw1, fw2)
                return ds_result_mock
            # Call 5+: idempotency check for existing blacklist entries
            return idempotency_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        fw_tags = ["fw1", "fw2"]

        mock_sangfor = MagicMock()
        mock_sangfor.block_ip = AsyncMock(return_value={"code": 0})
        mock_sangfor.close = AsyncMock()

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch("app.services.sangfor_service.SangforService", return_value=mock_sangfor), \
             patch("app.core.crypto.decrypt_config", return_value={"base_url": "https://fw.example.com", "username": "admin", "password": "pass", "verify_ssl": True, "ca_bundle": ""}), \
             patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value={}):
            ds_instance = MagicMock()
            ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=fw_tags)
            ds_cls.return_value = ds_instance

            result = await service.auto_block_non_compliant("lab", block_time="30d")

        assert result.blocked == 1

        # Verify two Blacklist entries were added (one per firewall)
        add_calls = mock_db.add.call_args_list
        blacklist_entries = [c[0][0] for c in add_calls if isinstance(c[0][0], Blacklist)]
        assert len(blacklist_entries) == 2
        fw_tags_in_entries = {e.firewall_tag for e in blacklist_entries}
        assert fw_tags_in_entries == {"fw1", "fw2"}

        # Verify terminal status updated
        assert terminal.status == "blocked"
        assert "fw1" in terminal.firewall_tag
        assert "fw2" in terminal.firewall_tag


# ===========================================================================
# TestAutoUnblockTerminal
# ===========================================================================

class TestAutoUnblockTerminal:
    """Tests for auto_unblock_compliant."""

    @pytest.mark.asyncio
    async def test_auto_unblock_marks_blacklist(self, service, mock_db):
        """Auto-unblock marks Blacklist as auto_unblocked=True."""
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )

        # Mock: query for auto-unblocked=False blacklist entries
        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry]

        # Mock: terminal query
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = terminal

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                # Terminal lookup query
                return term_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": None}]
        ig_data = {}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_unblock_on_firewall", return_value=True):

            result = await service.auto_unblock_compliant()

        assert result.unblocked == 1
        assert bl_entry.auto_unblocked is True
        assert terminal.status == "unblocked"

    @pytest.mark.asyncio
    async def test_auto_unblock_partial_failure_keeps_blocked(self, service, mock_db):
        """Multi-firewall unblock, one fails -> Terminal stays blocked."""
        bl_entry_fw1 = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        bl_entry_fw2 = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw2",
            auto_unblocked=False,
        )

        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry_fw1, bl_entry_fw2]

        # Mock: terminal lookup returns None (use blacklist entry IP/MAC for compliance check)
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = None

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                # Terminal lookup query
                return term_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": None}]
        ig_data = {}

        unblock_results = {"fw1": True, "fw2": False}

        async def mock_unblock(ip, fw_tag):
            return unblock_results.get(fw_tag, False)

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_unblock_on_firewall", side_effect=mock_unblock):

            result = await service.auto_unblock_compliant()

        # Terminal should NOT be unblocked because fw2 failed
        assert result.unblocked == 0
        # The successfully unblocked entry (fw1) should be marked
        assert bl_entry_fw1.auto_unblocked is True
        # The failed entry (fw2) should NOT be marked
        assert bl_entry_fw2.auto_unblocked is False

    @pytest.mark.asyncio
    async def test_auto_unblock_all_success_updates_terminal(self, service, mock_db):
        """Multi-firewall unblock, all succeed -> Terminal becomes unblocked."""
        bl_entry_fw1 = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        bl_entry_fw2 = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw2",
            auto_unblocked=False,
        )

        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry_fw1, bl_entry_fw2]

        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = terminal

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return term_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": None}]
        ig_data = {}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_unblock_on_firewall", return_value=True):

            result = await service.auto_unblock_compliant()

        assert result.unblocked == 1
        assert bl_entry_fw1.auto_unblocked is True
        assert bl_entry_fw2.auto_unblocked is True
        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert terminal.compliance_status == "bypass"


# ===========================================================================
# TestCleanupExpiredBlacklist
# ===========================================================================

class TestCleanupExpiredBlacklist:
    """Tests for cleanup_expired_blacklist in TerminalService.

    The cleanup logic lives in terminal_service.py but is tested here
    because it directly affects compliance state. We mock the DB and
    Sangfor service to avoid external dependencies.
    """

    @pytest.fixture
    def ts_service(self, mock_db):
        """TerminalService instance backed by a mock DB."""
        from app.services.terminal_service import TerminalService
        return TerminalService(mock_db)

    @pytest.mark.asyncio
    async def test_cleanup_skips_auto_unblocked(self, ts_service, mock_db):
        """Expired Blacklist with auto_unblocked=True -> skipped.

        The query filters on auto_unblocked == False, so auto-unblocked
        entries are never returned by the initial query.
        """
        # The query: Blacklist.expires_at < now AND auto_unblocked == False
        # An auto_unblocked=True entry should not appear in results.
        expired_result_mock = MagicMock()
        expired_result_mock.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(return_value=expired_result_mock)

        result = await ts_service.cleanup_expired_blacklist()

        assert result == 0
        # No delete calls should have been made
        mock_db.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_checks_active_blocks(self, ts_service, mock_db):
        """Expired Blacklist but IP has active block -> no firewall unblock.

        If an expired entry shares its IP with another non-expired, non-auto-unblocked
        Blacklist entry, the cleanup should only delete the expired entry from DB
        without calling the firewall unblock API.
        """
        now = datetime.now(UTC)
        expired_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            firewall_tag="fw1",
            expires_at=now - timedelta(hours=1),
        )

        # First query: expired entries
        expired_result_mock = MagicMock()
        expired_result_mock.scalars.return_value.all.return_value = [expired_entry]

        # Second query: batch-load terminals by IPs
        term_result_mock = MagicMock()
        term_result_mock.scalars.return_value.all.return_value = []

        # Third query: active blocks for the same MAC (non-expired)
        create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            firewall_tag="fw1",
            expires_at=now + timedelta(days=1),
        )
        active_result_mock = MagicMock()
        active_result_mock.all.return_value = [("AABBCCDDEEFF",)]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return expired_result_mock
            elif call_count["n"] == 2:
                return term_result_mock
            elif call_count["n"] == 3:
                return active_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch.object(ts_service, "_get_sangfor_service_by_tag", return_value=None):
            result = await ts_service.cleanup_expired_blacklist()

        # The expired entry should be marked as unblocked (soft delete, not unblocked on firewall)
        assert expired_entry.unblocked_at is not None
        assert expired_entry.unblocked_by == "system"
        assert expired_entry.reason == "封锁时间到期自动解封"
        assert result >= 1

    @pytest.mark.asyncio
    async def test_cleanup_only_resets_blocked_terminals(self, ts_service, mock_db):
        """Expired cleanup only resets Terminal status when currently 'blocked'.

        If a terminal's status is already 'unblocked' (e.g. manually unblocked),
        the cleanup should not change it back to 'unblocked' again.
        """
        now = datetime.now(UTC)
        expired_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            firewall_tag="fw1",
            expires_at=now - timedelta(hours=1),
        )

        # First query: expired entries
        expired_result_mock = MagicMock()
        expired_result_mock.scalars.return_value.all.return_value = [expired_entry]

        # Second query: batch-load terminals by IPs
        blocked_terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        unblocked_terminal = create_mock_terminal(
            ip="192.168.1.200",
            mac="11:22:33:44:55:66",
            status="unblocked",
            compliance_status="compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalars.return_value.all.return_value = [blocked_terminal, unblocked_terminal]

        # Third query: no active blocks for this IP
        active_result_mock = MagicMock()
        active_result_mock.all.return_value = []

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return expired_result_mock
            elif call_count["n"] == 2:
                return term_result_mock
            elif call_count["n"] == 3:
                return active_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_sangfor = MagicMock()
        mock_sangfor.base_url = "https://fw.example.com"
        mock_sangfor.unblock_ip = AsyncMock(return_value={"code": 0})
        mock_sangfor.close = AsyncMock()

        with patch.object(ts_service, "_get_sangfor_service_by_tag", return_value=mock_sangfor):
            await ts_service.cleanup_expired_blacklist()

        # Only the blocked terminal should have its status changed
        assert blocked_terminal.status == TerminalStatus.UNBLOCKED.value
        assert blocked_terminal.compliance_status == "unknown"
        # The unblocked terminal should remain unchanged
        assert unblocked_terminal.status == "unblocked"
        assert unblocked_terminal.compliance_status == "compliant"
        # Expired entry should carry the independent unblock reason
        assert expired_entry.reason == "封锁时间到期自动解封"


# ===========================================================================
# TestWhitelistMatching
# ===========================================================================

class TestWhitelistMatching:
    """Tests for _match_whitelist_in_memory and _ip_matches_pattern."""

    @pytest.mark.asyncio
    async def test_whitelist_match_by_mac(self, service):
        """Whitelist entry with MAC -> terminal with matching MAC matches."""
        whitelist_data = [
            {
                "mac_address": "AA-BB-CC-DD-EE-FF",
                "ip_pattern": None,
                "pattern_type": "mac_only",
                "comments": "test device",
            }
        ]
        result = service._match_whitelist_in_memory(
            whitelist_data, "192.168.1.100", "AA:BB:CC:DD:EE:FF"
        )
        assert result is not None
        assert result["match_type"] == "mac"

    @pytest.mark.asyncio
    async def test_whitelist_match_by_ip(self, service):
        """Whitelist entry with IP -> terminal with matching IP matches."""
        whitelist_data = [
            {
                "mac_address": None,
                "ip_pattern": "192.168.1.100",
                "pattern_type": "single_ip",
                "comments": None,
            }
        ]
        result = service._match_whitelist_in_memory(
            whitelist_data, "192.168.1.100", "AA:BB:CC:DD:EE:FF"
        )
        assert result is not None
        assert result["match_type"] == "ip"

    @pytest.mark.asyncio
    async def test_whitelist_match_by_cidr(self, service):
        """Whitelist entry with CIDR -> terminal with IP in CIDR matches."""
        whitelist_data = [
            {
                "mac_address": None,
                "ip_pattern": "192.168.1.0/24",
                "pattern_type": "cidr",
                "comments": "lab subnet",
            }
        ]
        result = service._match_whitelist_in_memory(
            whitelist_data, "192.168.1.100", "AA:BB:CC:DD:EE:FF"
        )
        assert result is not None
        assert result["match_type"] == "ip"

        # IP outside CIDR should not match
        result_outside = service._match_whitelist_in_memory(
            whitelist_data, "10.0.0.1", "AA:BB:CC:DD:EE:FF"
        )
        assert result_outside is None

    @pytest.mark.asyncio
    async def test_whitelist_no_match(self, service):
        """No matching whitelist entry -> no match."""
        whitelist_data = [
            {
                "mac_address": "11-22-33-44-55-66",
                "ip_pattern": None,
                "pattern_type": "mac_only",
                "comments": None,
            },
            {
                "mac_address": None,
                "ip_pattern": "10.0.0.1",
                "pattern_type": "single_ip",
                "comments": None,
            },
        ]
        result = service._match_whitelist_in_memory(
            whitelist_data, "192.168.1.100", "AA:BB:CC:DD:EE:FF"
        )
        assert result is None


# ===========================================================================
# TestRecalculateCompliance
# ===========================================================================

class TestRecalculateCompliance:
    """Tests for recalculate_all_compliance."""

    @pytest.mark.asyncio
    async def test_recalculate_auto_block_includes_mac_normalized(self, service, mock_db):
        """recalculate_all_compliance auto-block creates Blacklist with mac_address_normalized."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="unblocked",
            compliance_status="compliant",
            source_tag="lab",
        )

        # Mock: query all terminals
        term_result_mock = MagicMock()
        term_result_mock.scalars.return_value.all.return_value = [terminal]

        # Mock: subsequent DB queries inside _apply_compliance_result must return
        # empty results so the downgrade/block path proceeds (no cooldown skips).
        no_row_result = MagicMock()
        no_row_result.scalar_one_or_none.return_value = None

        empty_all_result = MagicMock()
        empty_all_result.all.return_value = []

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return term_result_mock      # select(Terminal) -> [terminal]
            elif call_count["n"] == 2:
                return no_row_result         # downgrade cooldown check -> None
            elif call_count["n"] == 3:
                return empty_all_result      # active blacklist lookup -> []
            elif call_count["n"] == 4:
                return no_row_result         # block cooldown check -> None
            return no_row_result             # idempotency check -> None

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        # No whitelist, no IPGuard match -> terminal becomes non_compliant -> auto-block.
        # IPGuard data must be non-empty (otherwise recalculation is skipped entirely).
        wl_data = []
        ig_data = {"lab": [{"ip_address": "10.0.0.99", "mac_address": "11-22-33-44-55-66"}]}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_is_ipguard_cache_stale", return_value=False), \
             patch.object(service, "_get_confirm_threshold", return_value=1), \
             patch.object(service, "_get_cooldown_minutes", return_value=10), \
             patch.object(service, "_get_bound_firewall_tags", return_value=["fw1"]), \
             patch.object(service, "_block_on_firewall", return_value=True), \
             patch.object(service, "_get_block_time", return_value="30d"):

            result = await service.recalculate_all_compliance()

        assert result["non_compliant"] == 1

        # Verify Blacklist entry was added with mac_address_normalized
        add_calls = mock_db.add.call_args_list
        blacklist_entries = [c[0][0] for c in add_calls if isinstance(c[0][0], Blacklist)]
        assert len(blacklist_entries) >= 1
        assert blacklist_entries[0].mac_address_normalized == "AABBCCDDEEFF"
        assert blacklist_entries[0].is_auto_blocked is True
        assert blacklist_entries[0].auto_unblocked is False

    @pytest.mark.asyncio
    async def test_recalculate_auto_unblock_handles_manual_block(self, service, mock_db):
        """recalculate auto-unblock marks both auto and manual Blacklist records.

        When a terminal becomes compliant and is currently blocked, the
        recalculate logic should mark matching Blacklist entries as
        auto_unblocked=True regardless of whether they were originally
        auto-blocked or manually blocked.
        """
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
        )

        term_result_mock = MagicMock()
        term_result_mock.scalars.return_value.all.return_value = [terminal]

        # Blacklist entries for this terminal (one auto, one manual)
        auto_bl = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            is_auto_blocked=True,
            auto_unblocked=False,
        )
        manual_bl = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            is_auto_blocked=False,
            auto_unblocked=False,
        )

        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [auto_bl, manual_bl]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return term_result_mock
            elif call_count["n"] == 2:
                # Blacklist lookup for marking auto_unblocked
                return bl_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        # Whitelist match -> terminal becomes bypass -> should be auto-unblocked
        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": "test"}]
        ig_data = {"lab": [{"ip_address": "10.0.0.99", "mac_address": "11-22-33-44-55-66"}]}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_is_ipguard_cache_stale", return_value=False), \
             patch.object(service, "_get_confirm_threshold", return_value=2), \
             patch.object(service, "_get_bound_firewall_tags", return_value=["fw1"]), \
             patch.object(service, "_unblock_on_firewall", return_value=True):

            result = await service.recalculate_all_compliance()

        assert result["unblocked"] == 1
        # Both auto and manual Blacklist entries should be marked as auto_unblocked
        assert auto_bl.auto_unblocked is True
        assert manual_bl.auto_unblocked is True
        assert terminal.status == "unblocked"

    @pytest.mark.asyncio
    async def test_recalculate_triggers_after_whitelist_add(self, service, mock_db):
        """Whitelist add triggers recalculation, bypass terminal gets auto-unblocked.

        Simulates the flow: a new whitelist entry is added, then
        recalculate_all_compliance is called. A previously blocked
        non-compliant terminal now matches the whitelist and should
        be auto-unblocked.
        """
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
        )

        term_result_mock = MagicMock()
        term_result_mock.scalars.return_value.all.return_value = [terminal]

        # Blacklist entries for this terminal
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return term_result_mock
            elif call_count["n"] == 2:
                return bl_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        # New whitelist entry matches this terminal
        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": "newly added"}]
        ig_data = {"lab": [{"ip_address": "10.0.0.99", "mac_address": "11-22-33-44-55-66"}]}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_is_ipguard_cache_stale", return_value=False), \
             patch.object(service, "_get_confirm_threshold", return_value=2), \
             patch.object(service, "_get_bound_firewall_tags", return_value=["fw1"]), \
             patch.object(service, "_unblock_on_firewall", return_value=True):

            result = await service.recalculate_all_compliance()

        assert result["bypass"] == 1
        assert result["unblocked"] == 1
        assert terminal.compliance_status == "bypass"
        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert bl_entry.auto_unblocked is True


# ===========================================================================
# _apply_compliance_result core state machine
# ===========================================================================

class TestApplyResultTransitions:
    """Direct unit tests for _apply_compliance_result status transitions."""

    @pytest.mark.asyncio
    async def test_bypass_transition_sets_status_and_comment(self, service, mock_db):
        """unknown -> bypass updates status, wl_match_type, and emits no event."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="unblocked",
            compliance_status="unknown",
            source_tag="lab",
        )

        # status_changed True -> active blacklist query only (no unblock/block)
        with apply_result_mocks(service, mock_db, [make_result(all_rows=[])]) as agg:
            result = await service._apply_compliance_result(
                terminal, "bypass", "mac", "test device",
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result == {"status_changed": True, "new_compliance": "bypass", "unblocked": False}
        assert terminal.compliance_status == "bypass"
        assert terminal.wl_match_type == "mac"
        assert terminal.comments == "Whitelist: test device"
        agg.emit_compliant.assert_not_awaited()
        agg.emit_non_compliant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_compliant_transition_emits_single_event(self, service, mock_db):
        """unknown -> compliant emits a single terminal.compliant event."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="unblocked",
            compliance_status="unknown",
            source_tag="lab",
        )

        with apply_result_mocks(service, mock_db, [make_result(all_rows=[])]) as agg:
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result == {"status_changed": True, "new_compliance": "compliant", "unblocked": False}
        assert terminal.compliance_status == "compliant"
        assert agg.emit_compliant.call_count == 1
        agg.emit_compliant.assert_awaited_once_with("192.168.1.100", "AA:BB:CC:DD:EE:FF")
        agg.emit_non_compliant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_compliant_transition_blocks_and_emits_event(self, service, mock_db):
        """compliant -> non_compliant blocks on fw1, creates blacklist, emits single event."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="unblocked",
            compliance_status="compliant",
            source_tag="lab",
        )

        results = [
            make_result(one=None),      # downgrade cooldown check -> None
            make_result(all_rows=[]),   # active blacklist fw tags -> []
            make_result(one=None),      # block cooldown check -> None
            make_result(one=None),      # block idempotency check -> None
        ]
        with apply_result_mocks(service, mock_db, results) as agg:
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["status_changed"] is True
        assert result["unblocked"] is False
        assert terminal.status == "blocked"
        assert terminal.firewall_tag == "fw1"
        assert agg.emit_non_compliant.call_count == 1
        agg.emit_non_compliant.assert_awaited_once_with(
            "192.168.1.100", "AA:BB:CC:DD:EE:FF", ["Non-compliant terminal detected"]
        )
        agg.emit_compliant.assert_not_awaited()

        bls = created_blacklists(mock_db)
        assert len(bls) == 1
        assert bls[0].mac_address_normalized == "AABBCCDDEEFF"
        assert bls[0].is_auto_blocked is True
        assert bls[0].auto_unblocked is False
        assert bls[0].reason == "IP 和 MAC 都不合规"


class TestApplyResultWhitelistComment:
    """Whitelist comment management within _apply_compliance_result."""

    @pytest.mark.asyncio
    async def test_bypass_appends_comment_to_existing(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="unknown", comments="existing note",
        )
        with apply_result_mocks(service, mock_db, [make_result(all_rows=[])]):
            await service._apply_compliance_result(
                terminal, "bypass", "mac", "test device",
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert terminal.comments == "existing note; Whitelist: test device"

    @pytest.mark.asyncio
    async def test_bypass_replaces_existing_whitelist_comment(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="unknown",
            comments="some; Whitelist: old device; other",
        )
        with apply_result_mocks(service, mock_db, [make_result(all_rows=[])]):
            await service._apply_compliance_result(
                terminal, "bypass", "mac", "new device",
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert terminal.comments == "some; Whitelist: new device; other"

    @pytest.mark.asyncio
    async def test_bypass_removes_whitelist_comment_when_no_comments(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="unknown",
            comments="Whitelist: old device",
        )
        with apply_result_mocks(service, mock_db, [make_result(all_rows=[])]):
            await service._apply_compliance_result(
                terminal, "bypass", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert terminal.comments == ""

    @pytest.mark.asyncio
    async def test_compliant_removes_whitelist_comment(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="unknown",
            comments="note; Whitelist: old device; tail",
        )
        with apply_result_mocks(service, mock_db, [make_result(all_rows=[])]):
            await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert "Whitelist" not in terminal.comments


class TestApplyResultCooldownDowngrade:
    """Cooldown pre-check prevents downgrade after a recent auto-unblock."""

    @pytest.mark.asyncio
    async def test_downgrade_skipped_after_recent_auto_unblock(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        # downgrade cooldown check returns a truthy recent-unblock row
        with apply_result_mocks(service, mock_db, [make_result(one=MagicMock())]):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result == {"status_changed": False, "new_compliance": "compliant", "unblocked": False}
        assert terminal.compliance_status == "compliant"
        assert created_blacklists(mock_db) == []


class TestApplyResultUnblock:
    """Unblock paths: blocked -> compliant / bypass, cooldown, failures."""

    @pytest.mark.asyncio
    async def test_blocked_to_compliant_unblocks_and_marks_blacklist(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )

        results = [
            make_result(one=None),                # unblock cooldown check -> None
            make_result(scalars_all=[bl_entry]),  # mark blacklist entries
            make_result(all_rows=[]),             # active blacklist query
        ]
        with apply_result_mocks(service, mock_db, results):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["unblocked"] is True
        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert bl_entry.auto_unblocked is True
        assert bl_entry.reason == "合规解封"

    @pytest.mark.asyncio
    async def test_blocked_to_bypass_unblocks_with_whitelist_reason(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )

        # bypass skips the unblock cooldown check entirely
        results = [
            make_result(scalars_all=[bl_entry]),  # mark blacklist entries
            make_result(all_rows=[]),             # active blacklist query
        ]
        with apply_result_mocks(service, mock_db, results):
            result = await service._apply_compliance_result(
                terminal, "bypass", "mac", "test",
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["unblocked"] is True
        assert bl_entry.auto_unblocked is True
        assert bl_entry.reason == "加入白名单"

    @pytest.mark.asyncio
    async def test_blocked_to_compliant_skips_unblock_on_cooldown(self, service, mock_db):
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )

        results = [
            make_result(one=MagicMock()),  # unblock cooldown -> recent auto-block (truthy)
            make_result(all_rows=[]),      # active blacklist query
        ]
        with apply_result_mocks(service, mock_db, results):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["unblocked"] is False
        assert terminal.status == "blocked"

    @pytest.mark.asyncio
    async def test_blocked_to_compliant_keeps_blocked_when_all_unblock_fail(self, service, mock_db):
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )

        results = [
            make_result(one=None),      # unblock cooldown -> None
            make_result(all_rows=[]),   # active blacklist query
        ]
        with apply_result_mocks(service, mock_db, results, unblock_on_firewall=False):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["unblocked"] is False
        assert terminal.status == "blocked"
        assert terminal.firewall_tag == "fw1"


class TestApplyResultBlock:
    """Block paths: no bound firewall, partial block, rollback, cooldown."""

    @pytest.mark.asyncio
    async def test_non_compliant_without_bound_firewall_stays_unblocked(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        results = [
            make_result(one=None),      # downgrade cooldown -> None
            make_result(all_rows=[]),   # active blacklist -> []
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=[]):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert created_blacklists(mock_db) == []

    @pytest.mark.asyncio
    async def test_non_compliant_blocks_only_missing_firewall(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        results = [
            make_result(one=None),               # downgrade cooldown -> None
            make_result(all_rows=[("fw1",)]),    # active blacklist -> {fw1}
            make_result(one=None),               # block cooldown -> None
            make_result(one=None),               # block idempotency (fw2) -> None
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=["fw1", "fw2"]):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.status == "blocked"
        assert "fw1" in terminal.firewall_tag
        assert "fw2" in terminal.firewall_tag

        bls = created_blacklists(mock_db)
        assert len(bls) == 1
        assert bls[0].firewall_tag == "fw2"

    @pytest.mark.asyncio
    async def test_non_compliant_block_failure_rolls_back_compliance(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        results = [
            make_result(one=None),      # downgrade cooldown -> None
            make_result(all_rows=[]),   # active blacklist -> []
            make_result(one=None),      # block cooldown -> None
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=["fw1"],
                                block_on_firewall=False):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        # compliance rolls back to original; no blacklist entry created
        assert terminal.compliance_status == "compliant"
        assert terminal.status == "unblocked"
        assert created_blacklists(mock_db) == []

    @pytest.mark.asyncio
    async def test_non_compliant_skips_block_on_cooldown(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        results = [
            make_result(one=None),       # downgrade cooldown -> None
            make_result(all_rows=[]),    # active blacklist -> []
            make_result(one=MagicMock()),  # block cooldown -> recent unblock (truthy)
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=["fw1"]):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        # status advanced to non_compliant but block was skipped by cooldown
        assert terminal.compliance_status == "non_compliant"
        assert terminal.status == "unblocked"
        assert created_blacklists(mock_db) == []


class TestApplyResultBlockReason:
    """Detailed block_reason derivation for non_compliant terminals."""

    BLOCK_RESULTS = [
        make_result(one=None),      # downgrade cooldown -> None
        make_result(all_rows=[]),   # active blacklist -> []
        make_result(one=None),      # block cooldown -> None
        make_result(one=None),      # block idempotency -> None
    ]

    @pytest.mark.asyncio
    async def test_ip_only_scope_reason(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        scope = [{"scope_type": "ip_cidr", "scope_value": "10.0.0.0/8"}]
        with apply_result_mocks(service, mock_db, self.BLOCK_RESULTS, scope_data=scope):
            await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "10.1.2.3", "AA:BB:CC:DD:EE:FF",
            )
        assert created_blacklists(mock_db)[0].reason == "IP 不合规"

    @pytest.mark.asyncio
    async def test_both_ip_and_mac_missing_reason(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        with apply_result_mocks(service, mock_db, self.BLOCK_RESULTS):
            await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert created_blacklists(mock_db)[0].reason == "IP 和 MAC 都不合规"

    @pytest.mark.asyncio
    async def test_ip_missing_mac_found_reason(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        ipguard = {"sg": [{"ip_address": "10.9.9.9", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        with apply_result_mocks(service, mock_db, self.BLOCK_RESULTS, ipguard_data=ipguard):
            await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert created_blacklists(mock_db)[0].reason == "IP 不合规，MAC 合规"

    @pytest.mark.asyncio
    async def test_ip_found_mac_missing_reason(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        ipguard = {"sg": [{"ip_address": "192.168.1.100", "mac_address": "11:22:33:44:55:66"}]}
        with apply_result_mocks(service, mock_db, self.BLOCK_RESULTS, ipguard_data=ipguard):
            await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert created_blacklists(mock_db)[0].reason == "MAC 不合规，IP 合规"


class TestApplyResultStatusUnchanged:
    """status_changed=False branch fixes stale firewall_tag / keeps state."""

    @pytest.mark.asyncio
    async def test_unchanged_blocked_terminal_gets_firewall_tag(self, service, mock_db):
        terminal = create_mock_terminal(
            status="blocked", compliance_status="compliant", source_tag="lab",
            firewall_tag=None,
        )
        with apply_result_mocks(service, mock_db, []):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["status_changed"] is False
        assert terminal.firewall_tag == "fw1"

    @pytest.mark.asyncio
    async def test_unchanged_unblocked_terminal_noop(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        with apply_result_mocks(service, mock_db, []):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result == {"status_changed": False, "new_compliance": "compliant", "unblocked": False}
        assert terminal.firewall_tag is None


class TestApplyResultCommentEdge:
    """Whitelist comment edge cases."""

    @pytest.mark.asyncio
    async def test_bypass_replaces_whitelist_comment_at_end(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="unknown",
            comments="some; Whitelist: old device",
        )
        with apply_result_mocks(service, mock_db, [make_result(all_rows=[])]):
            await service._apply_compliance_result(
                terminal, "bypass", "mac", "new device",
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert terminal.comments == "some; Whitelist: new device"


class TestApplyResultUnblockEdges:
    """Unblock edge branches: no bound firewall, partial failure."""

    @pytest.mark.asyncio
    async def test_blocked_to_compliant_no_bound_firewall_still_unblocks(self, service, mock_db):
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )
        results = [
            make_result(one=None),      # unblock cooldown -> None
            make_result(all_rows=[]),   # active blacklist query
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=[]):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["unblocked"] is True
        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None

    @pytest.mark.asyncio
    async def test_blocked_to_compliant_partial_unblock_failure(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )

        async def fake_unblock(ip, fw_tag):
            return fw_tag == "fw1"

        results = [
            make_result(one=None),                # unblock cooldown -> None
            make_result(scalars_all=[bl_entry]),  # mark blacklist entries
            make_result(all_rows=[]),             # active blacklist query
        ]
        with apply_result_mocks(service, mock_db, results,
                                bound_fw_tags=["fw1", "fw2"],
                                unblock_on_firewall=fake_unblock):
            result = await service._apply_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert result["unblocked"] is True
        assert terminal.status == "unblocked"
        assert "failed on: fw2" in terminal.comments
        assert bl_entry.auto_unblocked is True


class TestApplyResultBlockEdges:
    """Block edge branches: all-active, already-marked, idempotency skip."""

    @pytest.mark.asyncio
    async def test_non_compliant_all_firewalls_already_active(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        results = [
            make_result(one=None),               # downgrade cooldown -> None
            make_result(all_rows=[("fw1",)]),    # active blacklist -> {fw1}
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=["fw1"]):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.status == "blocked"
        assert terminal.firewall_tag == "fw1"
        assert created_blacklists(mock_db) == []

    @pytest.mark.asyncio
    async def test_non_compliant_skips_already_marked_blocked_firewall(self, service, mock_db):
        call = []

        async def fake_block(ip, fw_tag, reason="auto"):
            call.append(fw_tag)
            return True

        terminal = create_mock_terminal(
            status="blocked",
            compliance_status="compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )
        results = [
            make_result(one=None),      # downgrade cooldown -> None
            make_result(all_rows=[]),   # active blacklist -> []
            make_result(one=None),      # block cooldown -> None
            make_result(one=None),      # block idempotency -> None
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=["fw1"],
                                block_on_firewall=fake_block):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        # already marked blocked on fw1 -> block API NOT called, but blacklist reconciled
        assert call == []
        assert terminal.status == "blocked"
        assert len(created_blacklists(mock_db)) == 1

    @pytest.mark.asyncio
    async def test_non_compliant_idempotency_skips_existing_entry(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        results = [
            make_result(one=None),         # downgrade cooldown -> None
            make_result(all_rows=[]),      # active blacklist -> []
            make_result(one=None),         # block cooldown -> None
            make_result(one=MagicMock()),  # block idempotency -> existing (truthy)
        ]
        with apply_result_mocks(service, mock_db, results, bound_fw_tags=["fw1"]):
            result = await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.status == "blocked"
        assert created_blacklists(mock_db) == []


class TestApplyResultReasonEdge:
    """Remaining block_reason fallback branch."""

    @pytest.mark.asyncio
    async def test_ip_and_mac_found_in_different_entries_uses_default_reason(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="compliant", source_tag="lab",
        )
        ipguard = {"sg": [
            {"ip_address": "192.168.1.100", "mac_address": "11:22:33:44:55:66"},
            {"ip_address": "10.9.9.9", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ]}
        results = [
            make_result(one=None),      # downgrade cooldown -> None
            make_result(all_rows=[]),   # active blacklist -> []
            make_result(one=None),      # block cooldown -> None
            make_result(one=None),      # block idempotency -> None
        ]
        with apply_result_mocks(service, mock_db, results, ipguard_data=ipguard):
            await service._apply_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )
        assert created_blacklists(mock_db)[0].reason == "自动封锁：不合规"


# ===========================================================================
# apply_initial_compliance_result (first-discovery confirm-threshold path)
# ===========================================================================

class TestApplyInitialComplianceResult:
    """First-discovery path: non_compliant accumulates confirm count before blocking."""

    @pytest.mark.asyncio
    async def test_non_compliant_holds_below_threshold(self, service, mock_db):
        terminal = create_mock_terminal(compliance_status="unknown", source_tag="lab")
        with patch.object(service, "_get_confirm_threshold", return_value=3), \
             patch.object(service, "_apply_compliance_result", return_value={"status_changed": True}) as apply_mock:
            result = await service.apply_initial_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.non_compliant_confirm_count == 1
        assert terminal.compliant_confirm_count == 0
        assert result["status_changed"] is False
        assert result["new_compliance"] == "unknown"
        apply_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_compliant_reaches_threshold_then_applies(self, service, mock_db):
        terminal = create_mock_terminal(compliance_status="unknown", source_tag="lab")
        terminal.non_compliant_confirm_count = 2
        with patch.object(service, "_get_confirm_threshold", return_value=3), \
             patch.object(service, "_apply_compliance_result", return_value={"status_changed": True}) as apply_mock:
            await service.apply_initial_compliance_result(
                terminal, "non_compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.non_compliant_confirm_count == 0
        assert apply_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_compliant_resets_counter_and_applies(self, service, mock_db):
        terminal = create_mock_terminal(compliance_status="non_compliant", source_tag="lab")
        terminal.non_compliant_confirm_count = 5
        with patch.object(service, "_apply_compliance_result", return_value={"status_changed": True}) as apply_mock:
            await service.apply_initial_compliance_result(
                terminal, "compliant", None, None,
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.non_compliant_confirm_count == 0
        assert apply_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_bypass_resets_counter_and_applies(self, service, mock_db):
        terminal = create_mock_terminal(compliance_status="non_compliant", source_tag="lab")
        terminal.non_compliant_confirm_count = 3
        with patch.object(service, "_apply_compliance_result", return_value={"status_changed": True}) as apply_mock:
            await service.apply_initial_compliance_result(
                terminal, "bypass", "mac", "test",
                "192.168.1.100", "AA:BB:CC:DD:EE:FF",
            )

        assert terminal.non_compliant_confirm_count == 0
        assert apply_mock.await_count == 1


# ===========================================================================
# apply_manual_whitelist_for_terminal (manual whitelist + immediate unblock)
# ===========================================================================

class TestApplyManualWhitelist:
    """Manual whitelist immediately sets bypass and unblocks if currently blocked."""

    @pytest.mark.asyncio
    async def test_unblocked_terminal_sets_bypass_without_unblock(self, service, mock_db):
        terminal = create_mock_terminal(
            status="unblocked", compliance_status="non_compliant", source_tag="lab",
        )
        terminal.id = 1
        with patch.object(service, "invalidate_whitelist_cache", return_value=None), \
             patch.object(service, "log_action", return_value=None):
            result = await service.apply_manual_whitelist_for_terminal(
                terminal, "mac", "admin",
            )

        assert terminal.compliance_status == "bypass"
        assert terminal.wl_match_type == "mac"
        assert terminal.non_compliant_confirm_count == 0
        assert terminal.compliant_confirm_count == 0
        assert result["unblocked"] is False
        assert result["new_compliance"] == "bypass"
        assert result["old_compliance"] == "non_compliant"
        assert result["terminal_id"] == 1

    @pytest.mark.asyncio
    async def test_blocked_terminal_unblocks_and_marks_blacklist(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )
        terminal.id = 1
        mock_db.execute = scripted_execute([make_result(scalars_all=[bl_entry])])
        with patch.object(service, "invalidate_whitelist_cache", return_value=None), \
             patch.object(service, "log_action", return_value=None), \
             patch.object(service, "_unblock_on_firewall", return_value=True):
            result = await service.apply_manual_whitelist_for_terminal(
                terminal, "mac", "admin",
            )

        assert result["unblocked"] is True
        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert bl_entry.auto_unblocked is True
        assert bl_entry.reason == "加入白名单（手动）"
        assert bl_entry.unblocked_by == "admin"
        assert bl_entry.unblocked_at is not None

    @pytest.mark.asyncio
    async def test_blocked_terminal_resolves_firewall_via_binding(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag=None,
            auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag=None,
        )
        terminal.id = 1
        mock_db.execute = scripted_execute([make_result(scalars_all=[bl_entry])])
        with patch.object(service, "invalidate_whitelist_cache", return_value=None), \
             patch.object(service, "log_action", return_value=None), \
             patch.object(service, "_get_bound_firewall_tags", return_value=["fw1", "fw2"]), \
             patch.object(service, "_unblock_on_firewall", return_value=True):
            result = await service.apply_manual_whitelist_for_terminal(
                terminal, "ip", "admin",
            )

        assert result["unblocked"] is True
        assert terminal.status == "unblocked"
        assert bl_entry.auto_unblocked is True

    @pytest.mark.asyncio
    async def test_blocked_terminal_unblock_failure_keeps_blocked(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )
        terminal.id = 1
        mock_db.execute = scripted_execute([make_result(scalars_all=[bl_entry])])
        with patch.object(service, "invalidate_whitelist_cache", return_value=None), \
             patch.object(service, "log_action", return_value=None), \
             patch.object(service, "_unblock_on_firewall", return_value=False):
            result = await service.apply_manual_whitelist_for_terminal(
                terminal, "mac", "admin",
            )

        assert result["unblocked"] is False
        assert terminal.status == "blocked"
        assert terminal.firewall_tag == "fw1"
        assert bl_entry.auto_unblocked is False

    @pytest.mark.asyncio
    async def test_blocked_terminal_partial_unblock(self, service, mock_db):
        bl1 = create_mock_blacklist(
            ip="192.168.1.100", mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF", firewall_tag="fw1", auto_unblocked=False,
        )
        bl2 = create_mock_blacklist(
            ip="192.168.1.100", mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF", firewall_tag="fw2", auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1,fw2",
        )
        terminal.id = 1

        async def fake_unblock(ip, fw_tag):
            return fw_tag == "fw1"

        mock_db.execute = scripted_execute([make_result(scalars_all=[bl1, bl2])])
        with patch.object(service, "invalidate_whitelist_cache", return_value=None), \
             patch.object(service, "log_action", return_value=None), \
             patch.object(service, "_unblock_on_firewall", side_effect=fake_unblock):
            result = await service.apply_manual_whitelist_for_terminal(
                terminal, "mac", "admin",
            )

        assert result["unblocked"] is True
        assert terminal.status == "unblocked"
        assert bl1.auto_unblocked is True
        assert bl2.auto_unblocked is False

    @pytest.mark.asyncio
    async def test_blocked_terminal_unblock_exception_recorded(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
            source_tag="lab",
            firewall_tag="fw1",
        )
        terminal.id = 1

        async def fake_unblock(ip, fw_tag):
            raise RuntimeError("boom")

        mock_db.execute = scripted_execute([make_result(scalars_all=[bl_entry])])
        with patch.object(service, "invalidate_whitelist_cache", return_value=None), \
             patch.object(service, "log_action", return_value=None), \
             patch.object(service, "_unblock_on_firewall", side_effect=fake_unblock):
            result = await service.apply_manual_whitelist_for_terminal(
                terminal, "mac", "admin",
            )

        assert result["unblocked"] is False
        assert terminal.status == "blocked"
        assert bl_entry.auto_unblocked is False


# ===========================================================================
# Firewall block / unblock operations (_block_on_firewall / _unblock_on_firewall)
# ===========================================================================

def create_mock_fw_source(enabled=True, config=None):
    """Create a mock DataSource firewall entry for firewall ops tests."""
    s = MagicMock()
    s.enabled = enabled
    s.config = config
    return s


_DECRYPTED_CONFIG = {
    "base_url": "https://fw.example.com",
    "username": "admin",
    "password": "pass",
    "verify_ssl": True,
    "ca_bundle": "",
}


@contextlib.contextmanager
def firewall_ops_mocks(service, mock_db, fw_source, get_cached_side_effect=None):
    """Patch `_block_on_firewall` / `_unblock_on_firewall` collaborators.

    - db.execute returns `fw_source` as the firewall DataSource lookup.
    - patches decrypt_config, SangforService.get_cached_service, and log_action.
    - the mock Sangfor instance (`svc`) has block_ip/unblock_ip defaulting to
      `{"code": 0}`; tests may override them inside the context.
    """
    mock_db.execute = AsyncMock(return_value=make_result(one=fw_source))

    svc = MagicMock()
    svc.block_ip = AsyncMock(return_value={"code": 0})
    svc.unblock_ip = AsyncMock(return_value={"code": 0})

    get_cached = AsyncMock(return_value=svc)
    if get_cached_side_effect is not None:
        get_cached = AsyncMock(side_effect=get_cached_side_effect)

    with patch("app.core.crypto.decrypt_config", return_value=_DECRYPTED_CONFIG), \
         patch("app.services.sangfor_service.SangforService.get_cached_service", new=get_cached), \
         patch.object(service, "log_action") as log_mock:
        yield {"svc": svc, "log": log_mock}


class TestBlockOnFirewall:
    """Tests for `_block_on_firewall`."""

    @pytest.mark.asyncio
    async def test_firewall_not_found_returns_false(self, service, mock_db):
        with firewall_ops_mocks(service, mock_db, None) as m:
            result = await service._block_on_firewall("192.168.1.100", "fw1")

        assert result is False
        m["log"].assert_awaited_once()
        assert m["log"].await_args.args[4]["error"] == "firewall_not_found_or_disabled"

    @pytest.mark.asyncio
    async def test_firewall_disabled_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=False, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            result = await service._block_on_firewall("192.168.1.100", "fw1")

        assert result is False
        m["log"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_config_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config=None)
        with firewall_ops_mocks(service, mock_db, fw):
            result = await service._block_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            result = await service._block_on_firewall("192.168.1.100", "fw1")

        assert result is True
        m["svc"].block_ip.assert_awaited_once_with(
            ["192.168.1.100"], source_tag="fw1", reason="Auto-blocked: non-compliant"
        )

    @pytest.mark.asyncio
    async def test_failure_code_nonzero(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            m["svc"].block_ip = AsyncMock(return_value={"code": 1, "message": "boom"})
            result = await service._block_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_block_ip_exception_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            m["svc"].block_ip = AsyncMock(side_effect=RuntimeError("boom"))
            result = await service._block_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_cached_service_exception_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw, get_cached_side_effect=RuntimeError("boom")):
            result = await service._block_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_custom_reason_passed_to_block(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            result = await service._block_on_firewall(
                "192.168.1.100", "fw1", reason="custom reason"
            )

        assert result is True
        m["svc"].block_ip.assert_awaited_once_with(
            ["192.168.1.100"], source_tag="fw1", reason="custom reason"
        )


class TestUnblockOnFirewall:
    """Tests for `_unblock_on_firewall`."""

    @pytest.mark.asyncio
    async def test_firewall_not_found_returns_false(self, service, mock_db):
        with firewall_ops_mocks(service, mock_db, None) as m:
            result = await service._unblock_on_firewall("192.168.1.100", "fw1")

        assert result is False
        m["log"].assert_awaited_once()
        assert m["log"].await_args.args[4]["error"] == "firewall_not_found_or_disabled"

    @pytest.mark.asyncio
    async def test_firewall_disabled_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=False, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw):
            result = await service._unblock_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_empty_config_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config=None)
        with firewall_ops_mocks(service, mock_db, fw):
            result = await service._unblock_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            result = await service._unblock_on_firewall("192.168.1.100", "fw1")

        assert result is True
        m["svc"].unblock_ip.assert_awaited_once_with([{"srcIP": "192.168.1.100"}])

    @pytest.mark.asyncio
    async def test_failure_code_nonzero(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            m["svc"].unblock_ip = AsyncMock(return_value={"code": 1, "message": "boom"})
            result = await service._unblock_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_unblock_ip_exception_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw) as m:
            m["svc"].unblock_ip = AsyncMock(side_effect=RuntimeError("boom"))
            result = await service._unblock_on_firewall("192.168.1.100", "fw1")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_cached_service_exception_returns_false(self, service, mock_db):
        fw = create_mock_fw_source(enabled=True, config={"enc": "x"})
        with firewall_ops_mocks(service, mock_db, fw, get_cached_side_effect=RuntimeError("boom")):
            result = await service._unblock_on_firewall("192.168.1.100", "fw1")

        assert result is False


# ===========================================================================
# IPGuard data sync (sync_ipguard_data)
# ===========================================================================

def create_mock_baseline(enabled=True, config=None, tag="lab"):
    """Create a mock ComplianceBaseline for sync_ipguard_data tests."""
    b = MagicMock()
    b.enabled = enabled
    b.tag = tag
    b.config = config if config is not None else {
        "db_type": "postgresql",
        "host": "db.example.com",
        "port": 5432,
        "username": "user",
        "password": "pass",
        "database": "ipguard",
    }
    b.last_sync_status = None
    b.last_sync_at = None
    b.last_sync_error = None
    return b


@contextlib.contextmanager
def sync_ipguard_base_mocks():
    """Patch decrypt_config and get_config_value for sync_ipguard_data tests."""
    with patch("app.core.crypto.decrypt_config", side_effect=lambda c: c), \
         patch("app.services.compliance_service.get_config_value", new=AsyncMock(return_value=900)):
        yield


def _mock_baseline_lookup(mock_db, baseline):
    """Make db.execute return `baseline` via scalar_one_or_none()."""
    mock_db.execute = AsyncMock(return_value=make_result(one=baseline))


class TestSyncIpguardData:
    """Tests for `sync_ipguard_data`."""

    @pytest.mark.asyncio
    async def test_baseline_not_found_raises(self, service, mock_db):
        _mock_baseline_lookup(mock_db, None)

        with pytest.raises(ValueError, match="not found"):
            await service.sync_ipguard_data("missing")

    @pytest.mark.asyncio
    async def test_baseline_disabled_raises(self, service, mock_db):
        baseline = create_mock_baseline(enabled=False)
        _mock_baseline_lookup(mock_db, baseline)

        with pytest.raises(ValueError, match="disabled"):
            await service.sync_ipguard_data("lab")

    @pytest.mark.asyncio
    async def test_postgresql_sync_success(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline()
        _mock_baseline_lookup(mock_db, baseline)

        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[
            {"ip_address": "192.168.1.10", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ])
        conn.close = AsyncMock()

        with sync_ipguard_base_mocks(), \
             patch("asyncpg.connect", new=AsyncMock(return_value=conn)):
            result = await service.sync_ipguard_data("lab")

        assert result == {"success": True, "entries": 1, "message": "Synced 1 entries from IPGuard"}
        assert baseline.last_sync_status == "success"
        assert baseline.last_sync_error is None
        mock_db.commit.assert_awaited_once()
        # Primary + backup cache keys both populated with the same entries
        assert json.loads(mock_redis._data["ipguard:lab"]) == [
            {"ip_address": "192.168.1.10", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ]
        assert json.loads(mock_redis._data["ipguard:backup:lab"]) == [
            {"ip_address": "192.168.1.10", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ]

    @pytest.mark.asyncio
    async def test_mysql_sync_success(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(config={
            "db_type": "mysql", "host": "h", "port": 3306,
            "username": "u", "password": "p", "database": "db",
        })
        _mock_baseline_lookup(mock_db, baseline)

        cursor = MagicMock()
        cursor.execute = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[("192.168.1.20", "11:22:33:44:55:66")])
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        with sync_ipguard_base_mocks(), \
             patch("aiomysql.connect", new=AsyncMock(return_value=conn)):
            result = await service.sync_ipguard_data("lab")

        assert result["success"] is True
        assert result["entries"] == 1
        assert json.loads(mock_redis._data["ipguard:lab"]) == [
            {"ip_address": "192.168.1.20", "mac_address": "11:22:33:44:55:66"},
        ]
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mssql_sync_success_parses_mac_ip_pairs(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(config={
            "db_type": "mssql", "host": "h", "port": 1433,
            "username": "u", "password": "p", "database": "OCULAR3",
        })
        _mock_baseline_lookup(mock_db, baseline)

        cursor = MagicMock()
        # First pair has IP (kept); second pair has empty IP (skipped).
        cursor.__iter__.return_value = iter([
            ("AA:BB:CC:DD:EE:FF(192.168.1.30),11:22:33:44:55:66()",),
        ])

        conn = MagicMock()
        conn.cursor.return_value = cursor

        # Inject a fake pyodbc module to avoid importing the real extension
        # (which requires the system-level libodbc.so.2 unixODBC driver).
        fake_pyodbc = MagicMock()
        fake_pyodbc.connect = MagicMock(return_value=conn)

        with sync_ipguard_base_mocks(), \
             patch.dict("sys.modules", {"pyodbc": fake_pyodbc}):
            result = await service.sync_ipguard_data("lab")

        assert result["success"] is True
        assert result["entries"] == 1
        assert json.loads(mock_redis._data["ipguard:lab"]) == [
            {"ip_address": "192.168.1.30", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ]

    @pytest.mark.asyncio
    async def test_unknown_db_type_falls_back_to_postgresql(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(config={
            "db_type": "oracle", "host": "h", "port": 5432,
            "username": "u", "password": "p", "database": "db",
        })
        _mock_baseline_lookup(mock_db, baseline)

        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.close = AsyncMock()

        with sync_ipguard_base_mocks(), \
             patch("asyncpg.connect", new=AsyncMock(return_value=conn)) as connect_mock:
            result = await service.sync_ipguard_data("lab")

        assert result["success"] is True
        assert result["entries"] == 0
        # Unknown db_type still hits the postgresql (else) branch.
        connect_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_exception_marks_baseline_failed(self, service, mock_db):
        baseline = create_mock_baseline()
        _mock_baseline_lookup(mock_db, baseline)

        with sync_ipguard_base_mocks(), \
             patch("asyncpg.connect", new=AsyncMock(side_effect=ConnectionError("boom"))):
            result = await service.sync_ipguard_data("lab")

        assert result["success"] is False
        assert result["entries"] == 0
        assert "boom" in result["message"]
        assert baseline.last_sync_status == "failed"
        assert baseline.last_sync_error == "boom"
        mock_db.commit.assert_awaited_once()


# ===========================================================================
# Cache loading layer (_load_scope_cache / _load_whitelist_cache / _load_all_ipguard_cache)
# ===========================================================================

@contextlib.contextmanager
def patch_config_value(value=300):
    """Patch get_config_value in compliance_service to return a fixed TTL."""
    with patch("app.services.compliance_service.get_config_value", new=AsyncMock(return_value=value)):
        yield


class TestLoadScopeCache:
    """Tests for `_load_scope_cache`."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self, service, mock_db, mock_redis):
        payload = [{"id": 1, "scope_type": "ip_cidr", "scope_value": "10.0.0.0/8", "description": "internal"}]
        mock_redis._data[SCOPE_CACHE_KEY] = json.dumps(payload)

        data = await service._load_scope_cache()

        assert data == payload
        mock_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_loads_db_and_writes_cache(self, service, mock_db, mock_redis):
        entry = MagicMock()
        entry.id = 1
        entry.scope_type = "ip_cidr"
        entry.scope_value = "10.0.0.0/8"
        entry.description = "internal"
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[entry]))

        with patch_config_value(300):
            data = await service._load_scope_cache()

        assert data == [{"id": 1, "scope_type": "ip_cidr", "scope_value": "10.0.0.0/8", "description": "internal"}]
        assert json.loads(mock_redis._data[SCOPE_CACHE_KEY]) == data

    @pytest.mark.asyncio
    async def test_cache_hit_decodes_bytes(self, service, mock_db, mock_redis):
        payload = [{"id": 3, "scope_type": "mac_prefix_ipguard", "scope_value": "AABB", "description": ""}]
        mock_redis._data[SCOPE_CACHE_KEY] = json.dumps(payload).encode()

        data = await service._load_scope_cache()

        assert data == payload
        mock_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_read_error_falls_back_to_db(self, service, mock_db, mock_redis):
        async def _raise_get(key):
            raise ConnectionError("redis down")

        mock_redis.get = _raise_get

        entry = MagicMock()
        entry.id = 2
        entry.scope_type = "ip_range"
        entry.scope_value = "192.168.1.1-192.168.1.10"
        entry.description = "range"
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[entry]))

        with patch_config_value(300):
            data = await service._load_scope_cache()

        assert data == [{"id": 2, "scope_type": "ip_range", "scope_value": "192.168.1.1-192.168.1.10", "description": "range"}]


class TestLoadWhitelistCache:
    """Tests for `_load_whitelist_cache`."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db(self, service, mock_db, mock_redis):
        payload = [{"mac_address": "AA:BB:CC:DD:EE:FF", "ip_pattern": "192.168.1.0/24", "pattern_type": "cidr", "comments": "dev"}]
        mock_redis._data[WHITELIST_CACHE_KEY] = json.dumps(payload)

        data = await service._load_whitelist_cache()

        assert data == payload
        mock_db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_loads_db_and_writes_cache(self, service, mock_db, mock_redis):
        entry = MagicMock()
        entry.mac_address = "AA:BB:CC:DD:EE:FF"
        entry.ip_pattern = "192.168.1.0/24"
        entry.pattern_type = "cidr"
        entry.comments = "dev"
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[entry]))

        with patch_config_value(250):
            data = await service._load_whitelist_cache()

        assert data == [{"mac_address": "AA:BB:CC:DD:EE:FF", "ip_pattern": "192.168.1.0/24", "pattern_type": "cidr", "comments": "dev"}]
        assert json.loads(mock_redis._data[WHITELIST_CACHE_KEY]) == data

    @pytest.mark.asyncio
    async def test_redis_read_error_falls_back_to_db(self, service, mock_db, mock_redis):
        async def _raise_get(key):
            raise ConnectionError("redis down")

        mock_redis.get = _raise_get

        entry = MagicMock()
        entry.mac_address = "11:22:33:44:55:66"
        entry.ip_pattern = "10.0.0.1"
        entry.pattern_type = "single_ip"
        entry.comments = None
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[entry]))

        with patch_config_value():
            data = await service._load_whitelist_cache()

        assert data == [{"mac_address": "11:22:33:44:55:66", "ip_pattern": "10.0.0.1", "pattern_type": "single_ip", "comments": None}]


class TestLoadAllIpguardCache:
    """Tests for `_load_all_ipguard_cache`."""

    @pytest.mark.asyncio
    async def test_all_baselines_cache_hit(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[baseline]))
        mock_redis._data[f"{IPGUARD_CACHE_PREFIX}lab"] = json.dumps([
            {"ip_address": "192.168.1.10", "mac_address": "AA:BB:CC:DD:EE:FF"},
        ])

        with patch.object(service, "sync_ipguard_data", new=AsyncMock(return_value={"success": False})) as sync_mock:
            result = await service._load_all_ipguard_cache()

        assert result == {"lab": [{"ip_address": "192.168.1.10", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        sync_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_sync_success_reloads_cache(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[baseline]))

        async def fake_sync(tag):
            mock_redis._data[f"{IPGUARD_CACHE_PREFIX}{tag}"] = json.dumps([
                {"ip_address": "192.168.1.20", "mac_address": "11:22:33:44:55:66"},
            ])
            return {"success": True}

        with patch.object(service, "sync_ipguard_data", new=AsyncMock(side_effect=fake_sync)):
            result = await service._load_all_ipguard_cache()

        assert result == {"lab": [{"ip_address": "192.168.1.20", "mac_address": "11:22:33:44:55:66"}]}

    @pytest.mark.asyncio
    async def test_sync_success_but_cache_still_miss_uses_backup(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[baseline]))
        mock_redis._data[f"{IPGUARD_BACKUP_CACHE_PREFIX}lab"] = json.dumps([
            {"ip_address": "192.168.1.30", "mac_address": "AA:AA:AA:AA:AA:AA"},
        ])

        async def fake_sync(tag):
            return {"success": True}  # "succeeds" but does not populate cache

        with patch.object(service, "sync_ipguard_data", new=AsyncMock(side_effect=fake_sync)):
            result = await service._load_all_ipguard_cache()

        assert result["lab"] == [{"ip_address": "192.168.1.30", "mac_address": "AA:AA:AA:AA:AA:AA"}]

    @pytest.mark.asyncio
    async def test_sync_fails_uses_backup(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[baseline]))
        mock_redis._data[f"{IPGUARD_BACKUP_CACHE_PREFIX}lab"] = json.dumps([
            {"ip_address": "192.168.1.40", "mac_address": "BB:BB:BB:BB:BB:BB"},
        ])

        with patch.object(service, "sync_ipguard_data", new=AsyncMock(return_value={"success": False})):
            result = await service._load_all_ipguard_cache()

        assert result["lab"] == [{"ip_address": "192.168.1.40", "mac_address": "BB:BB:BB:BB:BB:BB"}]

    @pytest.mark.asyncio
    async def test_sync_raises_uses_backup(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[baseline]))
        mock_redis._data[f"{IPGUARD_BACKUP_CACHE_PREFIX}lab"] = json.dumps([
            {"ip_address": "192.168.1.50", "mac_address": "CC:CC:CC:CC:CC:CC"},
        ])

        with patch.object(service, "sync_ipguard_data", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await service._load_all_ipguard_cache()

        assert result["lab"] == [{"ip_address": "192.168.1.50", "mac_address": "CC:CC:CC:CC:CC:CC"}]

    @pytest.mark.asyncio
    async def test_sync_fails_and_no_backup_skips_source(self, service, mock_db, mock_redis):
        baseline = create_mock_baseline(tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[baseline]))

        with patch.object(service, "sync_ipguard_data", new=AsyncMock(return_value={"success": False})):
            result = await service._load_all_ipguard_cache()

        assert "lab" not in result

    @pytest.mark.asyncio
    async def test_multiple_baselines_mixed(self, service, mock_db, mock_redis):
        hit = create_mock_baseline(tag="hit")
        miss = create_mock_baseline(tag="miss")
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[hit, miss]))
        mock_redis._data[f"{IPGUARD_CACHE_PREFIX}hit"] = json.dumps([
            {"ip_address": "192.168.1.60", "mac_address": "DD:DD:DD:DD:DD:DD"},
        ])

        async def fake_sync(tag):
            mock_redis._data[f"{IPGUARD_CACHE_PREFIX}{tag}"] = json.dumps([
                {"ip_address": "192.168.1.70", "mac_address": "EE:EE:EE:EE:EE:EE"},
            ])
            return {"success": True}

        with patch.object(service, "sync_ipguard_data", new=AsyncMock(side_effect=fake_sync)):
            result = await service._load_all_ipguard_cache()

        assert result["hit"] == [{"ip_address": "192.168.1.60", "mac_address": "DD:DD:DD:DD:DD:DD"}]
        assert result["miss"] == [{"ip_address": "192.168.1.70", "mac_address": "EE:EE:EE:EE:EE:EE"}]


# ===========================================================================
# Distributed lock (_acquire_compliance_lock / _release_compliance_lock)
# ===========================================================================

class TestComplianceLock:
    """Tests for the module-level compliance recalculation lock helpers."""

    @pytest.mark.asyncio
    async def test_acquire_success_returns_token(self, mock_redis):
        token = await _acquire_compliance_lock()

        assert token is not None
        assert COMPLIANCE_RECALC_LOCK_KEY in mock_redis._data
        assert mock_redis._data[COMPLIANCE_RECALC_LOCK_KEY] == token

    @pytest.mark.asyncio
    async def test_acquire_already_held_returns_none(self, mock_redis):
        mock_redis._data[COMPLIANCE_RECALC_LOCK_KEY] = "existing"

        token = await _acquire_compliance_lock()

        assert token is None
        assert mock_redis._data[COMPLIANCE_RECALC_LOCK_KEY] == "existing"

    @pytest.mark.asyncio
    async def test_acquire_exception_returns_none(self, mock_redis):
        async def _raise_set(*args, **kwargs):
            raise ConnectionError("redis down")

        mock_redis.set = _raise_set

        token = await _acquire_compliance_lock()
        assert token is None

    @pytest.mark.asyncio
    async def test_release_matching_token_deletes(self, mock_redis):
        mock_redis._data[COMPLIANCE_RECALC_LOCK_KEY] = "tok"

        await _release_compliance_lock("tok")

        assert COMPLIANCE_RECALC_LOCK_KEY not in mock_redis._data

    @pytest.mark.asyncio
    async def test_release_non_matching_token_keeps(self, mock_redis):
        mock_redis._data[COMPLIANCE_RECALC_LOCK_KEY] = "other"

        await _release_compliance_lock("tok")

        assert mock_redis._data[COMPLIANCE_RECALC_LOCK_KEY] == "other"

    @pytest.mark.asyncio
    async def test_release_exception_suppressed(self, mock_redis):
        async def _raise_get(key):
            raise ConnectionError("redis down")

        mock_redis.get = _raise_get

        # Must not raise.
        await _release_compliance_lock("tok")


# ===========================================================================
# recalculate_all_compliance edge branches
# ===========================================================================

class TestRecalculateComplianceEdges:
    """Edge branches for recalculate_all_compliance."""

    @pytest.mark.asyncio
    async def test_skip_when_lock_not_acquired(self, service):
        with patch("app.services.compliance_service._acquire_compliance_lock", new=AsyncMock(return_value=None)), \
             patch("app.services.compliance_service._release_compliance_lock") as release_mock:
            result = await service.recalculate_all_compliance()

        assert result["skipped"] is True
        release_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_when_ipguard_data_unavailable(self, service):
        with patch("app.services.compliance_service._acquire_compliance_lock", new=AsyncMock(return_value="tok")), \
             patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value={}), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch("app.services.compliance_service._release_compliance_lock") as release_mock:
            result = await service.recalculate_all_compliance()

        assert result["skipped"] is True
        assert result["reason"] == "ipguard_data_unavailable"
        # The early-return branch releases the lock explicitly, and the outer
        # finally block releases it again (idempotent no-op). Assert the last call.
        release_mock.assert_awaited_with("tok")
        assert release_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_no_terminals_returns_zeros(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalars_all=[]))

        with patch("app.services.compliance_service._acquire_compliance_lock", new=AsyncMock(return_value="tok")), \
             patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value={"lab": [{"ip_address": "1.2.3.4", "mac_address": "AA-BB-CC-DD-EE-FF"}]}), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_is_ipguard_cache_stale", return_value=False), \
             patch("app.services.compliance_service._release_compliance_lock") as release_mock:
            result = await service.recalculate_all_compliance()

        assert result == {"total": 0, "bypass": 0, "compliant": 0, "non_compliant": 0, "unchanged": 0, "unblocked": 0}
        release_mock.assert_awaited_once_with("tok")

    @pytest.mark.asyncio
    async def test_cache_stale_holds_downgrade(self, service, mock_db):
        """When IPGuard cache is stale, a would-be downgrade is held (no false non_compliant)."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="unblocked",
            compliance_status="compliant",
        )

        term_result_mock = MagicMock()
        term_result_mock.scalars.return_value.all.return_value = [terminal]
        mock_db.execute = AsyncMock(return_value=term_result_mock)

        # IPGuard has data (so recalculate isn't "unavailable") but this
        # terminal's IP/MAC is NOT in it -> would otherwise downgrade.
        ig_data = {"lab": [{"ip_address": "10.0.0.99", "mac_address": "11-22-33-44-55-66"}]}

        with patch("app.services.compliance_service._acquire_compliance_lock", new=AsyncMock(return_value="tok")), \
             patch("app.services.compliance_service._release_compliance_lock"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_is_ipguard_cache_stale", return_value=True), \
             patch.object(service, "_get_confirm_threshold", return_value=2):
            result = await service.recalculate_all_compliance()

        assert result["total"] == 1
        assert result["unchanged"] == 1
        assert result["stale_skip_count"] == 1
        assert result["non_compliant"] == 0
        assert terminal.compliance_status == "compliant"

    @pytest.mark.asyncio
    async def test_bypass_transient_whitelist_miss_holds(self, service, mock_db):
        """A bypass terminal missing whitelist once is held (anti-oscillation), not downgraded."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="unblocked",
            compliance_status="bypass",
        )
        terminal.non_compliant_confirm_count = 0

        term_result_mock = MagicMock()
        term_result_mock.scalars.return_value.all.return_value = [terminal]
        mock_db.execute = AsyncMock(return_value=term_result_mock)

        ig_data = {"lab": [{"ip_address": "10.0.0.99", "mac_address": "11-22-33-44-55-66"}]}

        with patch("app.services.compliance_service._acquire_compliance_lock", new=AsyncMock(return_value="tok")), \
             patch("app.services.compliance_service._release_compliance_lock"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_is_ipguard_cache_stale", return_value=False), \
             patch.object(service, "_get_confirm_threshold", return_value=2), \
             patch.object(service, "_get_whitelist_miss_threshold", return_value=6):
            result = await service.recalculate_all_compliance()

        assert result["total"] == 1
        assert result["unchanged"] == 1
        assert result["non_compliant"] == 0
        assert terminal.compliance_status == "bypass"
        assert terminal.non_compliant_confirm_count == 1


# ===========================================================================
# auto_block_non_compliant finer branches
# ===========================================================================

class TestAutoBlockEdges:
    """Finer branches for auto_block_non_compliant."""

    @pytest.mark.asyncio
    async def test_whitelist_precheck_self_heals_to_bypass(self, service, mock_db):
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            return nc_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": None}]

        with patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=wl_data):
            result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 0
        assert result.total_non_compliant == 0
        assert terminal.compliance_status == "bypass"

    @pytest.mark.asyncio
    async def test_no_firewall_bindings_returns_skipped(self, service, mock_db):
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            return nc_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]):
            ds_instance = MagicMock()
            ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=[])
            ds_cls.return_value = ds_instance

            result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 0
        assert result.total_non_compliant == 1
        assert result.skipped == 1
        assert "No firewall bindings" in result.errors[0]

    @pytest.mark.asyncio
    async def test_dry_run_no_actual_block(self, service, mock_db):
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            return nc_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch("app.services.sangfor_service.SangforService") as sangfor_cls, \
             patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]):
            ds_instance = MagicMock()
            ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=["fw1"])
            ds_cls.return_value = ds_instance

            result = await service.auto_block_non_compliant("lab", dry_run=True)

        assert result.blocked == 1
        assert result.details[0]["action"] == "would_block"
        sangfor_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_block_service_unavailable_skipped(self, service, mock_db):
        """Bound firewall resolves to a disabled/missing source -> entry skipped."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]
        fw_result_mock = MagicMock()
        fw_result_mock.scalar_one_or_none.return_value = None  # firewall not found/disabled

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return nc_result_mock
            return fw_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]):
            ds_instance = MagicMock()
            ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=["fw1"])
            ds_cls.return_value = ds_instance

            result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 0
        assert result.skipped == 1
        assert result.total_non_compliant == 1
        assert "service not available" in result.errors[0]

    @pytest.mark.asyncio
    async def test_block_sangfor_failure_skipped(self, service, mock_db):
        """Sangfor block returns non-zero code -> terminal NOT blocked (skipped)."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        mock_fw_source = MagicMock()
        mock_fw_source.enabled = True
        mock_fw_source.config = {"base_url": "https://fw", "username": "a", "password": "b"}

        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]
        fw_result_mock = MagicMock()
        fw_result_mock.scalar_one_or_none.return_value = mock_fw_source

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return nc_result_mock
            return fw_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_sangfor = MagicMock()
        mock_sangfor.block_ip = AsyncMock(return_value={"code": 1, "message": "block failed"})
        mock_sangfor.close = AsyncMock()

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch("app.services.sangfor_service.SangforService", return_value=mock_sangfor), \
             patch("app.core.crypto.decrypt_config", return_value={"base_url": "https://fw", "username": "a", "password": "b", "verify_ssl": True, "ca_bundle": ""}), \
             patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]):
            ds_instance = MagicMock()
            ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=["fw1"])
            ds_cls.return_value = ds_instance

            result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 0
        assert result.skipped == 1
        assert result.total_non_compliant == 1

    @pytest.mark.asyncio
    async def test_block_reason_ip_missing_mac_found(self, service, mock_db):
        """Non-IP-only scope with IP missing but MAC present -> detailed block reason."""
        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            compliance_status="non_compliant",
            status="unblocked",
        )

        mock_fw_source = MagicMock()
        mock_fw_source.enabled = True
        mock_fw_source.config = {"base_url": "https://fw", "username": "a", "password": "b"}

        bl_result_mock = MagicMock()
        bl_result_mock.all.return_value = []
        nc_result_mock = MagicMock()
        nc_result_mock.scalars.return_value.all.return_value = [terminal]
        fw_result_mock = MagicMock()
        fw_result_mock.scalar_one_or_none.return_value = mock_fw_source
        idempotency_result_mock = MagicMock()
        idempotency_result_mock.scalar_one_or_none.return_value = None

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return nc_result_mock
            elif call_count["n"] == 3:
                return fw_result_mock
            return idempotency_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_sangfor = MagicMock()
        mock_sangfor.block_ip = AsyncMock(return_value={"code": 0})
        mock_sangfor.close = AsyncMock()

        # IPGuard knows this MAC but on a different IP -> ip_found=False, mac_found=True.
        ig_data = {"lab": [{"ip_address": "10.0.0.1", "mac_address": "AA-BB-CC-DD-EE-FF"}]}

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch("app.services.sangfor_service.SangforService", return_value=mock_sangfor), \
             patch("app.core.crypto.decrypt_config", return_value={"base_url": "https://fw", "username": "a", "password": "b", "verify_ssl": True, "ca_bundle": ""}), \
             patch.object(service, "_get_block_time", return_value="30d"), \
             patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data):
            ds_instance = MagicMock()
            ds_instance.get_firewall_tags_for_arp = AsyncMock(return_value=["fw1"])
            ds_cls.return_value = ds_instance

            result = await service.auto_block_non_compliant("lab")

        assert result.blocked == 1

        bl_entries = [c[0][0] for c in mock_db.add.call_args_list if isinstance(c[0][0], Blacklist)]
        assert len(bl_entries) == 1
        assert bl_entries[0].reason == "IP 不合规，MAC 合规"


# ===========================================================================
# auto_unblock_compliant finer branches
# ===========================================================================

class TestAutoUnblockEdges:
    """Finer branches for auto_unblock_compliant."""

    @pytest.mark.asyncio
    async def test_cooldown_skips_unblock(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry]

        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = terminal

        recent_block = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            is_auto_blocked=True,
            auto_unblocked=False,
        )
        recent_result_mock = MagicMock()
        recent_result_mock.scalar_one_or_none.return_value = recent_block

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return term_result_mock
            elif call_count["n"] == 3:
                return recent_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        ig_data = {"lab": [{"ip_address": "192.168.1.100", "mac_address": "AA-BB-CC-DD-EE-FF"}]}

        with patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_get_cooldown_minutes", return_value=10), \
             patch.object(service, "_unblock_on_firewall") as unblock_mock:
            result = await service.auto_unblock_compliant()

        assert result.unblocked == 0
        assert result.skipped == 1
        unblock_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ipguard_match_sets_compliant(self, service, mock_db):
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )
        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry]

        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = terminal

        recent_result_mock = MagicMock()
        recent_result_mock.scalar_one_or_none.return_value = None

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return term_result_mock
            elif call_count["n"] == 3:
                return recent_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        ig_data = {"lab": [{"ip_address": "192.168.1.100", "mac_address": "AA-BB-CC-DD-EE-FF"}]}

        with patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_get_cooldown_minutes", return_value=10), \
             patch.object(service, "_unblock_on_firewall", return_value=True):
            result = await service.auto_unblock_compliant()

        assert result.unblocked == 1
        assert terminal.status == "unblocked"
        assert terminal.compliance_status == "compliant"

    @pytest.mark.asyncio
    async def test_no_entries_returns_zeros(self, service, mock_db):
        """No active auto-unblocked entries -> early zero result."""
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=empty_result)

        result = await service.auto_unblock_compliant()

        assert result.total_auto_blocked == 0
        assert result.unblocked == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_null_mac_groups_by_ip_and_unblocks(self, service, mock_db):
        """NULL-MAC blacklist entries group by IP and still unblock via terminal lookup."""
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="",
            mac_normalized="",
            firewall_tag="fw1",
            auto_unblocked=False,
        )

        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry]

        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = terminal

        recent_result_mock = MagicMock()
        recent_result_mock.scalar_one_or_none.return_value = None

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return term_result_mock
            return recent_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        ig_data = {"lab": [{"ip_address": "192.168.1.100", "mac_address": "AA-BB-CC-DD-EE-FF"}]}

        with patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_get_cooldown_minutes", return_value=10), \
             patch.object(service, "_unblock_on_firewall", return_value=True):
            result = await service.auto_unblock_compliant()

        assert result.unblocked == 1
        assert terminal.status == "unblocked"
        assert bl_entry.auto_unblocked is True

    @pytest.mark.asyncio
    async def test_no_firewall_tag_resolves_binding_and_unblocks(self, service, mock_db):
        """Blacklist entry without firewall_tag resolves binding and unblocks on it."""
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag=None,
            source_tag="lab",
            auto_unblocked=False,
        )

        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry]

        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = terminal

        recent_result_mock = MagicMock()
        recent_result_mock.scalar_one_or_none.return_value = None

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return term_result_mock
            return recent_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        ig_data = {"lab": [{"ip_address": "192.168.1.100", "mac_address": "AA-BB-CC-DD-EE-FF"}]}

        with patch.object(service, "_load_whitelist_cache", return_value=[]), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_get_cooldown_minutes", return_value=10), \
             patch.object(service, "_get_bound_firewall_tags", return_value=["fw1"]), \
             patch.object(service, "_unblock_on_firewall", return_value=True) as unblock_mock:
            result = await service.auto_unblock_compliant()

        assert result.unblocked == 1
        assert terminal.status == "unblocked"
        assert bl_entry.auto_unblocked is True
        unblock_mock.assert_awaited_once_with("192.168.1.100", "fw1")

    @pytest.mark.asyncio
    async def test_whitelist_match_immediate_unblock_bypasses_cooldown(self, service, mock_db):
        """Whitelist match unblocks immediately (no cooldown, authoritative)."""
        bl_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            mac_normalized="AABBCCDDEEFF",
            firewall_tag="fw1",
            auto_unblocked=False,
        )

        bl_result_mock = MagicMock()
        bl_result_mock.scalars.return_value.all.return_value = [bl_entry]

        terminal = create_mock_terminal(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            status="blocked",
            compliance_status="non_compliant",
        )
        term_result_mock = MagicMock()
        term_result_mock.scalar_one_or_none.return_value = terminal

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            return term_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": "x"}]

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value={}), \
             patch.object(service, "_load_scope_cache", return_value=[]), \
             patch.object(service, "_get_cooldown_minutes", return_value=10) as cooldown_mock, \
             patch.object(service, "_unblock_on_firewall", return_value=True):
            result = await service.auto_unblock_compliant()

        assert result.unblocked == 1
        assert terminal.status == "unblocked"
        assert terminal.compliance_status == "bypass"
        cooldown_mock.assert_not_called()
