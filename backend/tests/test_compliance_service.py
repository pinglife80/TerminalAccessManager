"""
Comprehensive unit tests for ComplianceService.

All database calls and external API calls are mocked so the tests
do NOT require Docker, PostgreSQL, or Redis to be running.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timedelta, timezone

from app.services.compliance_service import ComplianceService
from app.models.terminal import Terminal, TerminalStatus
from app.models.blacklist import Blacklist
from app.models.whitelist import Whitelist


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
):
    """Create a mock Terminal object with sensible defaults."""
    t = MagicMock(spec=Terminal)
    t.ip_address = ip
    t.mac_address = mac
    t.status = status
    t.compliance_status = compliance_status
    t.source_tag = source_tag
    t.firewall_tag = firewall_tag
    t.comments = comments
    t.wl_match_type = wl_match_type
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
    b.expires_at = expires_at or datetime.now(timezone.utc) + timedelta(days=30)
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """AsyncMock for the database session."""
    return AsyncMock()


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
             patch.object(service, "_check_ipguard", return_value=True):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "compliant"
        assert "ipguard" in result["matched_sources"]
        assert result["whitelisted"] is False

    @pytest.mark.asyncio
    async def test_unknown_to_non_compliant(self, service):
        """Terminal with unknown status, no IPGuard match, no whitelist match -> non_compliant."""
        with patch.object(service, "_check_whitelist", return_value=None), \
             patch.object(service, "_check_ipguard", return_value=False):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "non_compliant"
        assert result["matched_sources"] == []
        assert result["whitelisted"] is False

    @pytest.mark.asyncio
    async def test_unknown_to_bypass(self, service):
        """Terminal with unknown status, matches whitelist -> bypass."""
        wl_result = {"match_type": "mac", "comments": "test device"}
        with patch.object(service, "_check_whitelist", return_value=wl_result), \
             patch.object(service, "_check_ipguard", return_value=True):
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
             patch.object(service, "_check_ipguard", return_value=False):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "non_compliant"

    @pytest.mark.asyncio
    async def test_non_compliant_to_bypass(self, service):
        """Terminal was non_compliant, added to whitelist -> bypass."""
        wl_result = {"match_type": "ip", "comments": "newly whitelisted"}
        with patch.object(service, "_check_whitelist", return_value=wl_result), \
             patch.object(service, "_check_ipguard", return_value=False):
            result = await service.check_compliance("192.168.1.100", "AA:BB:CC:DD:EE:FF")

        assert result["compliance_status"] == "bypass"
        assert result["whitelisted"] is True

    @pytest.mark.asyncio
    async def test_bypass_to_non_compliant(self, service):
        """Terminal was bypass, removed from whitelist -> non_compliant."""
        with patch.object(service, "_check_whitelist", return_value=None), \
             patch.object(service, "_check_ipguard", return_value=False):
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

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return nc_result_mock
            # Call 3+: DataSource queries for firewall resolution
            return ds_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        mock_sangfor = MagicMock()
        mock_sangfor.block_ip = AsyncMock(return_value={"code": 0})
        mock_sangfor.close = AsyncMock()

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch("app.services.sangfor_service.SangforService", return_value=mock_sangfor), \
             patch("app.core.crypto.decrypt_config", return_value={"base_url": "https://fw.example.com", "username": "admin", "password": "pass", "verify_ssl": True, "ca_bundle": ""}):
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
        terminal = create_mock_terminal(
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

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            elif call_count["n"] == 2:
                return nc_result_mock
            # Call 3+: DataSource queries for firewall resolution
            return ds_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        fw_tags = ["fw1", "fw2"]

        mock_sangfor = MagicMock()
        mock_sangfor.block_ip = AsyncMock(return_value={"code": 0})
        mock_sangfor.close = AsyncMock()

        with patch("app.services.data_source_service.DataSourceService") as ds_cls, \
             patch("app.services.sangfor_service.SangforService", return_value=mock_sangfor), \
             patch("app.core.crypto.decrypt_config", return_value={"base_url": "https://fw.example.com", "username": "admin", "password": "pass", "verify_ssl": True, "ca_bundle": ""}):
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
        term_result_mock.scalars.return_value.all.return_value = [terminal]

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

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bl_result_mock
            return MagicMock()

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        wl_data = [{"mac_address": "AA-BB-CC-DD-EE-FF", "ip_pattern": None, "pattern_type": "mac_only", "comments": None}]
        ig_data = {}

        unblock_results = {"fw1": True, "fw2": False}

        async def mock_unblock(ip, fw_tag):
            return unblock_results.get(fw_tag, False)

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
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
        term_result_mock.scalars.return_value.all.return_value = [terminal]

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
        now = datetime.now(timezone.utc)
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

        # Third query: active blocks for same IP (non-expired)
        active_entry = create_mock_blacklist(
            ip="192.168.1.100",
            mac="AA:BB:CC:DD:EE:FF",
            firewall_tag="fw1",
            expires_at=now + timedelta(days=1),
        )
        active_result_mock = MagicMock()
        active_result_mock.all.return_value = [("192.168.1.100",)]

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

        # The expired entry should be deleted from DB (not unblocked on firewall)
        mock_db.delete.assert_called_once_with(expired_entry)
        assert result >= 1

    @pytest.mark.asyncio
    async def test_cleanup_only_resets_blocked_terminals(self, ts_service, mock_db):
        """Expired cleanup only resets Terminal status when currently 'blocked'.

        If a terminal's status is already 'unblocked' (e.g. manually unblocked),
        the cleanup should not change it back to 'unblocked' again.
        """
        now = datetime.now(timezone.utc)
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
            result = await ts_service.cleanup_expired_blacklist()

        # Only the blocked terminal should have its status changed
        assert blocked_terminal.status == TerminalStatus.UNBLOCKED.value
        assert blocked_terminal.compliance_status == "unknown"
        # The unblocked terminal should remain unchanged
        assert unblocked_terminal.status == "unblocked"
        assert unblocked_terminal.compliance_status == "compliant"


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

        call_count = {"n": 0}

        async def execute_side_effect(stmt):
            call_count["n"] += 1
            return term_result_mock

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)

        # No whitelist, no IPGuard -> terminal becomes non_compliant -> auto-block
        wl_data = []
        ig_data = {}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
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
        ig_data = {}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
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
        ig_data = {}

        with patch.object(service, "_load_whitelist_cache", return_value=wl_data), \
             patch.object(service, "_load_all_ipguard_cache", return_value=ig_data), \
             patch.object(service, "_get_bound_firewall_tags", return_value=["fw1"]), \
             patch.object(service, "_unblock_on_firewall", return_value=True):

            result = await service.recalculate_all_compliance()

        assert result["bypass"] == 1
        assert result["unblocked"] == 1
        assert terminal.compliance_status == "bypass"
        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert bl_entry.auto_unblocked is True
