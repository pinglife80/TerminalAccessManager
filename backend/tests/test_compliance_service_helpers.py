"""Supplementary tests for ComplianceService helper methods and pure functions.

Covers the IP/range/scope matching helpers, IPGuard in-memory matching,
unblock reason building, and config getter methods that were previously
uncovered by test_compliance_service.py.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.compliance_service import ComplianceService


@pytest.fixture
def service():
    """ComplianceService backed by a plain MagicMock (pure funcs don't touch db)."""
    return ComplianceService(MagicMock())


# ---------------------------------------------------------------------------
# _ip_matches_pattern
# ---------------------------------------------------------------------------

class TestIpMatchesPattern:
    def test_single_ip_match(self, service):
        assert service._ip_matches_pattern("192.168.1.1", "192.168.1.1", "single_ip") is True

    def test_single_ip_mismatch(self, service):
        assert service._ip_matches_pattern("192.168.1.2", "192.168.1.1", "single_ip") is False

    def test_cidr_match(self, service):
        assert service._ip_matches_pattern("192.168.1.10", "192.168.1.0/24", "cidr") is True

    def test_cidr_mismatch(self, service):
        assert service._ip_matches_pattern("192.168.2.10", "192.168.1.0/24", "cidr") is False

    def test_ip_range_match(self, service):
        assert service._ip_matches_pattern("192.168.1.50", "192.168.1.1-100", "ip_range") is True

    def test_ip_range_mismatch(self, service):
        assert service._ip_matches_pattern("192.168.1.150", "192.168.1.1-100", "ip_range") is False

    def test_both_type_host_route(self, service):
        assert service._ip_matches_pattern("192.168.1.1", "192.168.1.1/32", "both") is True

    def test_both_type_cidr(self, service):
        assert service._ip_matches_pattern("192.168.1.10", "192.168.1.0/24", "both") is True

    def test_both_type_range(self, service):
        assert service._ip_matches_pattern("192.168.1.50", "192.168.1.1-100", "both") is True

    def test_both_type_single_ip(self, service):
        assert service._ip_matches_pattern("192.168.1.1", "192.168.1.1", "both") is True

    def test_unknown_type_cidr(self, service):
        assert service._ip_matches_pattern("192.168.1.10", "192.168.1.0/24", "other") is True

    def test_unknown_type_range(self, service):
        assert service._ip_matches_pattern("192.168.1.50", "192.168.1.1-100", "other") is True

    def test_unknown_type_single_ip(self, service):
        assert service._ip_matches_pattern("192.168.1.1", "192.168.1.1", "other") is True

    def test_invalid_ip_falls_back_to_equality(self, service):
        # IPv4Address("bad") raises -> returns ip_address == ip_pattern
        assert service._ip_matches_pattern("bad", "bad", "single_ip") is True

    def test_invalid_ip_equality_false(self, service):
        assert service._ip_matches_pattern("bad", "other", "single_ip") is False


# ---------------------------------------------------------------------------
# _ip_in_range
# ---------------------------------------------------------------------------

class TestIpInRange:
    def test_in_range(self, service):
        assert service._ip_in_range("192.168.1.50", "192.168.1.1-100") is True

    def test_below_range(self, service):
        assert service._ip_in_range("192.168.1.0", "192.168.1.1-100") is False

    def test_above_range(self, service):
        assert service._ip_in_range("192.168.1.101", "192.168.1.1-100") is False

    def test_boundary_start(self, service):
        assert service._ip_in_range("192.168.1.1", "192.168.1.1-100") is True

    def test_boundary_end(self, service):
        assert service._ip_in_range("192.168.1.100", "192.168.1.1-100") is True

    def test_different_prefix(self, service):
        assert service._ip_in_range("192.168.2.50", "192.168.1.1-100") is False

    def test_malformed_range(self, service):
        assert service._ip_in_range("192.168.1.50", "192.168.1.1") is False  # no dash

    def test_invalid_ip(self, service):
        assert service._ip_in_range("bad", "192.168.1.1-100") is False


# ---------------------------------------------------------------------------
# _match_ipguard_in_memory
# ---------------------------------------------------------------------------

class TestMatchIpguardInMemory:
    def test_exact_ip_mac_match(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_in_memory(data, "10.0.0.1", "AA:BB:CC:DD:EE:FF") == (True, True, True)

    def test_ip_match_with_mac_prefix(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_in_memory(data, "10.0.0.1", "11:22:33:44:55:66", ["AA:BB:CC"]) == (True, True, True)

    def test_ip_match_mac_mismatch_no_prefix(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_in_memory(data, "10.0.0.1", "11:22:33:44:55:66") == (False, True, False)

    def test_mac_match_different_ip(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_in_memory(data, "10.0.0.99", "AA:BB:CC:DD:EE:FF") == (False, False, True)

    def test_no_match(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_in_memory(data, "10.0.0.99", "11:22:33:44:55:66") == (False, False, False)

    def test_empty_data(self, service):
        assert service._match_ipguard_in_memory({}, "10.0.0.1", "AA:BB:CC:DD:EE:FF") == (False, False, False)

    def test_none_mac(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_in_memory(data, "10.0.0.1", None) == (False, True, False)

    def test_mac_dash_delimiter_normalized(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA-BB-CC-DD-EE-FF"}]}
        assert service._match_ipguard_in_memory(data, "10.0.0.1", "AA:BB:CC:DD:EE:FF") == (True, True, True)


# ---------------------------------------------------------------------------
# _match_ipguard_ip_only_in_memory
# ---------------------------------------------------------------------------

class TestMatchIpguardIpOnlyInMemory:
    def test_ip_match(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_ip_only_in_memory(data, "10.0.0.1") is True

    def test_ip_mismatch(self, service):
        data = {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        assert service._match_ipguard_ip_only_in_memory(data, "10.0.0.99") is False

    def test_empty_data(self, service):
        assert service._match_ipguard_ip_only_in_memory({}, "10.0.0.1") is False


# ---------------------------------------------------------------------------
# _match_ipguard_or_in_memory
# ---------------------------------------------------------------------------

class TestMatchIpguardOrInMemory:
    def _data(self):
        return {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}

    def test_ip_only_matches(self, service):
        assert service._match_ipguard_or_in_memory(self._data(), "10.0.0.1", "11:22:33:44:55:66") is True

    def test_mac_only_matches(self, service):
        assert service._match_ipguard_or_in_memory(self._data(), "10.0.0.99", "AA:BB:CC:DD:EE:FF") is True

    def test_both_match(self, service):
        assert service._match_ipguard_or_in_memory(self._data(), "10.0.0.1", "AA:BB:CC:DD:EE:FF") is True

    def test_neither_matches(self, service):
        assert service._match_ipguard_or_in_memory(self._data(), "10.0.0.99", "11:22:33:44:55:66") is False

    def test_empty_data(self, service):
        assert service._match_ipguard_or_in_memory({}, "10.0.0.1", "AA:BB:CC:DD:EE:FF") is False


# ---------------------------------------------------------------------------
# _build_unblock_reason
# ---------------------------------------------------------------------------

class TestBuildUnblockReason:
    def _data(self):
        return {"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}

    def test_whitelist_match(self, service):
        assert service._build_unblock_reason(True, False, False, self._data(), "10.0.0.1", "AA:BB:CC:DD:EE:FF", None) == "加入白名单"

    def test_ip_only(self, service):
        assert service._build_unblock_reason(False, True, False, self._data(), "10.0.0.1", "AA:BB:CC:DD:EE:FF", None) == "IP 合规"

    def test_ip_and_mac_compliant(self, service):
        assert service._build_unblock_reason(False, False, False, self._data(), "10.0.0.1", "AA:BB:CC:DD:EE:FF", None) == "IP 和 MAC 都合规"

    def test_ip_compliant_mac_not(self, service):
        assert service._build_unblock_reason(False, False, False, self._data(), "10.0.0.1", "11:22:33:44:55:66", None) == "IP 合规，MAC 不合规"

    def test_mac_compliant_ip_not(self, service):
        assert service._build_unblock_reason(False, False, False, self._data(), "10.0.0.99", "AA:BB:CC:DD:EE:FF", None) == "MAC 合规，IP 不合规"

    def test_neither_compliant(self, service):
        assert service._build_unblock_reason(False, False, False, self._data(), "10.0.0.99", "11:22:33:44:55:66", None) == "合规解封"

    def test_or_match_ip_only(self, service):
        assert service._build_unblock_reason(False, False, True, self._data(), "10.0.0.1", "11:22:33:44:55:66", None) == "IP 合规，MAC 不合规"

    def test_or_match_mac_only(self, service):
        assert service._build_unblock_reason(False, False, True, self._data(), "10.0.0.99", "AA:BB:CC:DD:EE:FF", None) == "MAC 合规，IP 不合规"

    def test_or_match_both(self, service):
        assert service._build_unblock_reason(False, False, True, self._data(), "10.0.0.1", "AA:BB:CC:DD:EE:FF", None) == "IP 和 MAC 都合规"

    def test_or_not_mislabeled_as_ip_only(self, service):
        assert service._build_unblock_reason(False, True, True, self._data(), "10.0.0.1", "11:22:33:44:55:66", None) == "IP 合规，MAC 不合规"


# ---------------------------------------------------------------------------
# _mac_matches_any_prefix / _extract_ipguard_mac_prefixes
# ---------------------------------------------------------------------------

class TestMacMatchesAnyPrefix:
    def test_match(self):
        assert ComplianceService._mac_matches_any_prefix("AABBCCDDEEFF", ["AABBCC"]) is True

    def test_no_match(self):
        assert ComplianceService._mac_matches_any_prefix("AABBCCDDEEFF", ["FFEEDD"]) is False

    def test_empty_mac(self):
        assert ComplianceService._mac_matches_any_prefix("", ["AABBCC"]) is False

    def test_none_mac(self):
        assert ComplianceService._mac_matches_any_prefix(None, ["AABBCC"]) is False

    def test_empty_prefixes(self):
        assert ComplianceService._mac_matches_any_prefix("AABBCCDDEEFF", []) is False

    def test_delimiter_normalized(self):
        assert ComplianceService._mac_matches_any_prefix("AA-BB-CC-DD-EE-FF", ["AA:BB:CC"]) is True

    def test_prefix_shorter_than_mac_ok(self):
        assert ComplianceService._mac_matches_any_prefix("AABBCCDDEEFF", ["AABB"]) is True


class TestExtractIpguardMacPrefixes:
    def test_extract(self):
        scope = [
            {"scope_type": "mac_prefix_ipguard", "scope_value": "AABBCC"},
            {"scope_type": "ip_cidr", "scope_value": "10.0.0.0/8"},
            {"scope_type": "mac_prefix_ipguard", "scope_value": "DDEEFF"},
        ]
        assert ComplianceService._extract_ipguard_mac_prefixes(scope) == ["AABBCC", "DDEEFF"]

    def test_no_ipguard_prefixes(self):
        scope = [{"scope_type": "ip_cidr", "scope_value": "10.0.0.0/8"}]
        assert ComplianceService._extract_ipguard_mac_prefixes(scope) == []

    def test_empty_scope(self):
        assert ComplianceService._extract_ipguard_mac_prefixes([]) == []


# ---------------------------------------------------------------------------
# _check_terminal_in_arp_scope
# ---------------------------------------------------------------------------

class TestCheckTerminalInArpScope:
    def test_empty_scope(self, service):
        assert service._check_terminal_in_arp_scope([], "10.0.0.1", "AA:BB:CC:DD:EE:FF") is False

    def test_ip_cidr_match(self, service):
        scope = [{"scope_type": "ip_cidr", "scope_value": "10.0.0.0/8"}]
        assert service._check_terminal_in_arp_scope(scope, "10.1.2.3", "AA:BB:CC:DD:EE:FF") is True

    def test_ip_cidr_mismatch(self, service):
        scope = [{"scope_type": "ip_cidr", "scope_value": "10.0.0.0/8"}]
        assert service._check_terminal_in_arp_scope(scope, "192.168.1.1", "AA:BB:CC:DD:EE:FF") is False

    def test_ip_range_match(self, service):
        scope = [{"scope_type": "ip_range", "scope_value": "10.0.0.1-100"}]
        assert service._check_terminal_in_arp_scope(scope, "10.0.0.50", "AA:BB:CC:DD:EE:FF") is True

    def test_ip_range_mismatch(self, service):
        scope = [{"scope_type": "ip_range", "scope_value": "10.0.0.1-100"}]
        assert service._check_terminal_in_arp_scope(scope, "10.0.0.200", "AA:BB:CC:DD:EE:FF") is False

    def test_mac_prefix_arp_match(self, service):
        scope = [{"scope_type": "mac_prefix_arp", "scope_value": "AA:BB:CC"}]
        assert service._check_terminal_in_arp_scope(scope, "10.0.0.1", "AA:BB:CC:DD:EE:FF") is True

    def test_mac_prefix_arp_mismatch(self, service):
        scope = [{"scope_type": "mac_prefix_arp", "scope_value": "AA:BB:CC"}]
        assert service._check_terminal_in_arp_scope(scope, "10.0.0.1", "FF:EE:DD:CC:BB:AA") is False

    def test_invalid_scope_value_continues(self, service):
        scope = [{"scope_type": "ip_cidr", "scope_value": "not-a-cidr"}]
        assert service._check_terminal_in_arp_scope(scope, "10.0.0.1", "AA:BB:CC:DD:EE:FF") is False


# ---------------------------------------------------------------------------
# _check_terminal_in_or_scope
# ---------------------------------------------------------------------------

class TestCheckTerminalInOrScope:
    def test_empty_scope(self, service):
        assert service._check_terminal_in_or_scope([], "10.0.0.1", "AA:BB:CC:DD:EE:FF") is False

    def test_ip_cidr_any_match(self, service):
        scope = [{"scope_type": "ip_cidr_any", "scope_value": "10.0.0.0/8"}]
        assert service._check_terminal_in_or_scope(scope, "10.1.2.3", "AA:BB:CC:DD:EE:FF") is True

    def test_ip_cidr_any_mismatch(self, service):
        scope = [{"scope_type": "ip_cidr_any", "scope_value": "10.0.0.0/8"}]
        assert service._check_terminal_in_or_scope(scope, "192.168.1.1", "AA:BB:CC:DD:EE:FF") is False

    def test_ip_range_any_match(self, service):
        scope = [{"scope_type": "ip_range_any", "scope_value": "10.0.0.1-100"}]
        assert service._check_terminal_in_or_scope(scope, "10.0.0.50", "AA:BB:CC:DD:EE:FF") is True

    def test_ip_range_any_mismatch(self, service):
        scope = [{"scope_type": "ip_range_any", "scope_value": "10.0.0.1-100"}]
        assert service._check_terminal_in_or_scope(scope, "10.0.0.200", "AA:BB:CC:DD:EE:FF") is False

    def test_mac_prefix_any_match(self, service):
        scope = [{"scope_type": "mac_prefix_any", "scope_value": "AA:BB:CC"}]
        assert service._check_terminal_in_or_scope(scope, "10.0.0.1", "AA:BB:CC:DD:EE:FF") is True

    def test_mac_prefix_any_mismatch(self, service):
        scope = [{"scope_type": "mac_prefix_any", "scope_value": "AA:BB:CC"}]
        assert service._check_terminal_in_or_scope(scope, "10.0.0.1", "FF:EE:DD:CC:BB:AA") is False

    def test_invalid_scope_value_continues(self, service):
        scope = [{"scope_type": "ip_cidr_any", "scope_value": "not-a-cidr"}]
        assert service._check_terminal_in_or_scope(scope, "10.0.0.1", "AA:BB:CC:DD:EE:FF") is False


# ---------------------------------------------------------------------------
# _match_whitelist_in_memory — supplementary branches
# ---------------------------------------------------------------------------

class TestMatchWhitelistSupplementary:
    def test_mac_only_entry(self, service):
        data = [{"pattern_type": "mac_only", "mac_address": "AA:BB:CC:DD:EE:FF", "ip_pattern": None, "comments": None}]
        result = service._match_whitelist_in_memory(data, "10.0.0.1", "AA:BB:CC:DD:EE:FF")
        assert result == {"match_type": "mac", "comments": None}

    def test_both_ip_and_mac(self, service):
        data = [
            {
                "pattern_type": "single_ip",
                "mac_address": "AA:BB:CC:DD:00:01",
                "ip_pattern": "192.168.1.1",
                "comments": "x",
            }
        ]
        result = service._match_whitelist_in_memory(data, "192.168.1.1", "AA:BB:CC:DD:00:01")
        assert result == {"match_type": "both", "comments": "x"}

    def test_ip_only_entry_with_comments(self, service):
        data = [{"pattern_type": "single_ip", "mac_address": None, "ip_pattern": "192.168.1.1", "comments": "c"}]
        result = service._match_whitelist_in_memory(data, "192.168.1.1", "AA:BB:CC:DD:EE:FF")
        assert result == {"match_type": "ip", "comments": "c"}

    def test_mac_only_entry_wrong_mac(self, service):
        data = [{"pattern_type": "mac_only", "mac_address": "AA:BB:CC:DD:EE:FF", "ip_pattern": None, "comments": None}]
        assert service._match_whitelist_in_memory(data, "10.0.0.1", "11:22:33:44:55:66") is None


# ---------------------------------------------------------------------------
# check_compliance / batch_check_compliance
# ---------------------------------------------------------------------------

class TestCheckComplianceEntry:
    @pytest.fixture
    def svc(self, service):
        return service

    async def test_bypass(self, svc):
        svc._check_whitelist = AsyncMock(return_value={"match_type": "mac", "comments": None})
        svc._load_scope_cache = AsyncMock(return_value=[])
        svc._check_ipguard = AsyncMock(return_value=True)
        result = await svc.check_compliance("10.0.0.1", "AA:BB:CC:DD:EE:FF")
        assert result["compliance_status"] == "bypass"
        assert result["whitelisted"] is True
        assert result["wl_match_type"] == "mac"

    async def test_compliant(self, svc):
        svc._check_whitelist = AsyncMock(return_value=None)
        svc._load_scope_cache = AsyncMock(return_value=[])
        svc._check_ipguard = AsyncMock(return_value=True)
        result = await svc.check_compliance("10.0.0.1", "AA:BB:CC:DD:EE:FF")
        assert result["compliance_status"] == "compliant"

    async def test_non_compliant(self, svc):
        svc._check_whitelist = AsyncMock(return_value=None)
        svc._load_scope_cache = AsyncMock(return_value=[])
        svc._check_ipguard = AsyncMock(return_value=False)
        result = await svc.check_compliance("10.0.0.1", "AA:BB:CC:DD:EE:FF")
        assert result["compliance_status"] == "non_compliant"

    async def test_use_ip_only_strategy(self, svc):
        svc._check_whitelist = AsyncMock(return_value=None)
        svc._load_scope_cache = AsyncMock(return_value=[{"scope_type": "ip_cidr", "scope_value": "10.0.0.0/8"}])
        svc._check_ipguard_ip_only = AsyncMock(return_value=True)
        result = await svc.check_compliance("10.0.0.1", "AA:BB:CC:DD:EE:FF")
        assert result["compliance_status"] == "compliant"
        svc._check_ipguard_ip_only.assert_awaited_once_with("10.0.0.1")

    async def test_use_or_strategy(self, svc):
        svc._check_whitelist = AsyncMock(return_value=None)
        svc._load_scope_cache = AsyncMock(return_value=[{"scope_type": "ip_cidr_any", "scope_value": "10.0.0.0/8"}])
        svc._check_ipguard_or = AsyncMock(return_value=True)
        result = await svc.check_compliance("10.0.0.1", "AA:BB:CC:DD:EE:FF")
        assert result["compliance_status"] == "compliant"
        svc._check_ipguard_or.assert_awaited_once_with("10.0.0.1", "AA:BB:CC:DD:EE:FF")

    async def test_or_scope_takes_priority_over_ip_only(self, svc):
        svc._check_whitelist = AsyncMock(return_value=None)
        svc._load_scope_cache = AsyncMock(return_value=[
            {"scope_type": "ip_cidr", "scope_value": "10.0.0.0/8"},
            {"scope_type": "ip_cidr_any", "scope_value": "10.0.0.0/8"},
        ])
        svc._check_ipguard_or = AsyncMock(return_value=True)
        svc._check_ipguard_ip_only = AsyncMock(return_value=True)
        result = await svc.check_compliance("10.0.0.1", "AA:BB:CC:DD:EE:FF")
        assert result["compliance_status"] == "compliant"
        svc._check_ipguard_or.assert_awaited_once_with("10.0.0.1", "AA:BB:CC:DD:EE:FF")
        svc._check_ipguard_ip_only.assert_not_awaited()


class TestBatchCheckCompliance:
    async def test_batch_classification(self, service):
        service._load_whitelist_cache = AsyncMock(
            return_value=[{"pattern_type": "single_ip", "mac_address": None, "ip_pattern": "10.0.0.1", "comments": None}]
        )
        service._load_scope_cache = AsyncMock(return_value=[])
        service._load_all_ipguard_cache = AsyncMock(
            return_value={"sg": [{"ip_address": "10.0.0.2", "mac_address": "AA:BB:CC:DD:00:02"}]}
        )
        entries = [
            {"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:00:01"},  # whitelist -> bypass
            {"ip_address": "10.0.0.2", "mac_address": "AA:BB:CC:DD:00:02"},  # ipguard -> compliant
            {"ip_address": "10.0.0.3", "mac_address": "AA:BB:CC:DD:00:03"},  # neither -> non_compliant
        ]
        result = await service.batch_check_compliance(entries)
        assert result.total_checked == 3
        assert result.bypass == 1
        assert result.compliant == 1
        assert result.non_compliant == 1

    async def test_batch_or_strategy_four_scenarios(self, service):
        service._load_whitelist_cache = AsyncMock(return_value=[])
        service._load_scope_cache = AsyncMock(
            return_value=[{"scope_type": "ip_cidr_any", "scope_value": "10.0.0.0/8"}]
        )
        service._load_all_ipguard_cache = AsyncMock(
            return_value={"sg": [{"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"}]}
        )
        entries = [
            {"ip_address": "10.0.0.1", "mac_address": "AA:BB:CC:DD:EE:FF"},  # both -> compliant (OR)
            {"ip_address": "10.0.0.1", "mac_address": "11:22:33:44:55:66"},  # IP only -> compliant (OR)
            {"ip_address": "10.0.0.99", "mac_address": "AA:BB:CC:DD:EE:FF"},  # MAC only -> compliant (OR)
            {"ip_address": "10.0.0.99", "mac_address": "11:22:33:44:55:66"},  # neither -> non_compliant
        ]
        result = await service.batch_check_compliance(entries)
        assert result.total_checked == 4
        assert result.compliant == 3
        assert result.non_compliant == 1
        assert result.bypass == 0


# ---------------------------------------------------------------------------
# Config getter methods
# ---------------------------------------------------------------------------

class TestConfigGetters:
    async def test_get_block_time(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="15d")
            assert await service._get_block_time() == "15d"

    async def test_get_block_time_none_defaults_30d(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value=None)
            assert await service._get_block_time() == "30d"

    async def test_get_confirm_threshold_clamp_low(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="0")
            assert await service._get_confirm_threshold() == 1

    async def test_get_confirm_threshold_clamp_high(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="999")
            assert await service._get_confirm_threshold() == 10

    async def test_get_confirm_threshold_valid(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="5")
            assert await service._get_confirm_threshold() == 5

    async def test_get_ipguard_stale_threshold_clamp_low(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="1")
            assert await service._get_ipguard_stale_threshold_minutes() == 5

    async def test_get_cooldown_minutes_clamp_high(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="999")
            assert await service._get_cooldown_minutes() == 60

    async def test_get_ip_grace_minutes_valid(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="25")
            assert await service._get_ip_grace_minutes() == 25

    async def test_get_whitelist_miss_threshold_clamp_low(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="0")
            assert await service._get_whitelist_miss_threshold() == 2

    async def test_get_whitelist_miss_threshold_valid(self, service):
        with patch("app.services.config_service.ConfigService") as MockCfg:
            MockCfg.return_value.get = AsyncMock(return_value="8")
            assert await service._get_whitelist_miss_threshold() == 8

    async def test_config_exception_falls_back_to_default(self, service):
        with patch("app.services.config_service.ConfigService", side_effect=RuntimeError("boom")):
            assert await service._get_block_time() == "30d"
            assert await service._get_confirm_threshold() == 2
            assert await service._get_cooldown_minutes() == 10


# ---------------------------------------------------------------------------
# _is_ipguard_cache_stale
# ---------------------------------------------------------------------------

class TestIsIpguardCacheStale:
    def _baseline(self, last_sync_at):
        b = MagicMock()
        b.last_sync_at = last_sync_at
        return b

    def _setup_db(self, service, baselines):
        result = MagicMock()
        result.scalars.return_value.all.return_value = baselines
        service.db = MagicMock()
        service.db.execute = AsyncMock(return_value=result)
        service._get_ipguard_stale_threshold_minutes = AsyncMock(return_value=12)

    async def test_no_baselines(self, service):
        self._setup_db(service, [])
        assert await service._is_ipguard_cache_stale() is True

    async def test_never_synced(self, service):
        self._setup_db(service, [self._baseline(None)])
        assert await service._is_ipguard_cache_stale() is True

    async def test_recent_sync_not_stale(self, service):
        self._setup_db(service, [self._baseline(datetime.now(UTC) - timedelta(minutes=5))])
        assert await service._is_ipguard_cache_stale() is False

    async def test_old_sync_is_stale(self, service):
        self._setup_db(service, [self._baseline(datetime.now(UTC) - timedelta(minutes=20))])
        assert await service._is_ipguard_cache_stale() is True

    async def test_naive_timestamp_treated_as_utc(self, service):
        # naive timestamp that actually represents UTC (avoids local-timezone flakiness)
        naive_utc = (datetime.now(UTC) - timedelta(minutes=20)).replace(tzinfo=None)
        self._setup_db(service, [self._baseline(naive_utc)])
        assert await service._is_ipguard_cache_stale() is True

    async def test_newest_among_multiple(self, service):
        baselines = [
            self._baseline(datetime.now(UTC) - timedelta(minutes=50)),
            self._baseline(datetime.now(UTC) - timedelta(minutes=5)),
        ]
        self._setup_db(service, baselines)
        assert await service._is_ipguard_cache_stale() is False


# ---------------------------------------------------------------------------
# Scope 场景：同 IP 多 MAC / 同 MAC 多 IP 验证
#
# 用 batch_check_compliance（自包含决策入口）验证分析结论与实际行为一致。
# 基线约定：
#   - 10.0.0.10 <-> AA:BB:CC:DD:00:01（精确配对，基线 MAC 前缀 AA:BB:CC）
#   - 10.0.0.30 / 10.0.0.40 <-> AA:BB:CC:DD:00:03（同一 MAC 漫游两个 IP）
# ---------------------------------------------------------------------------

def _ipguard_baseline():
    return {
        "sg": [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},
            {"ip_address": "10.0.0.30", "mac_address": "AA:BB:CC:DD:00:03"},
            {"ip_address": "10.0.0.40", "mac_address": "AA:BB:CC:DD:00:03"},
        ],
    }


async def _run_batch(service, scope, entries, ipguard=None):
    """Run batch_check_compliance with a fixed whitelist-empty + given scope/baseline."""
    service._load_whitelist_cache = AsyncMock(return_value=[])
    service._load_scope_cache = AsyncMock(return_value=scope)
    service._load_all_ipguard_cache = AsyncMock(return_value=ipguard or _ipguard_baseline())
    result = await service.batch_check_compliance(entries)
    statuses = {
        (e["ip_address"], e["mac_address"].upper()): e["compliance_status"] for e in entries
    }
    return result, statuses


class TestScopeIpCidr:
    """ip_cidr -> IP-only：同 IP 全 MAC 同结果；各 IP 独立（忽略 MAC）。"""

    async def test_same_ip_multi_mac_and_same_mac_multi_ip(self, service):
        scope = [{"scope_type": "ip_cidr", "scope_value": "10.0.0.0/24"}]
        entries = [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},  # IP 在基线 -> compliant
            {"ip_address": "10.0.0.10", "mac_address": "FF:EE:DD:CC:00:99"},  # 同 IP 假 MAC，仍 compliant
            {"ip_address": "10.0.0.30", "mac_address": "AA:BB:CC:DD:00:03"},  # IP 在基线 -> compliant
            {"ip_address": "10.0.0.50", "mac_address": "AA:BB:CC:DD:00:01"},  # MAC 在基线但该 IP 不在 -> non_compliant
            {"ip_address": "10.0.0.99", "mac_address": "AA:BB:CC:DD:00:03"},  # 同 MAC 漂移到新 IP -> non_compliant
        ]
        result, statuses = await _run_batch(service, scope, entries)

        assert result.compliant == 3
        assert result.non_compliant == 2
        assert statuses[("10.0.0.10", "AA:BB:CC:DD:00:01")] == "compliant"
        assert statuses[("10.0.0.10", "FF:EE:DD:CC:00:99")] == "compliant"
        assert statuses[("10.0.0.30", "AA:BB:CC:DD:00:03")] == "compliant"
        assert statuses[("10.0.0.50", "AA:BB:CC:DD:00:01")] == "non_compliant"
        assert statuses[("10.0.0.99", "AA:BB:CC:DD:00:03")] == "non_compliant"


class TestScopeIpRange:
    """ip_range -> IP-only：同 ip_cidr，仅范围由 CIDR 换成区间（前缀.末段格式）。"""

    async def test_same_ip_multi_mac_and_same_mac_multi_ip(self, service):
        scope = [{"scope_type": "ip_range", "scope_value": "10.0.0.1-100"}]
        entries = [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},  # compliant
            {"ip_address": "10.0.0.10", "mac_address": "FF:EE:DD:CC:00:99"},  # 同 IP 假 MAC，compliant
            {"ip_address": "10.0.0.30", "mac_address": "AA:BB:CC:DD:00:03"},  # compliant
            {"ip_address": "10.0.0.40", "mac_address": "AA:BB:CC:DD:00:03"},  # 兼容 MAC 第二个 IP，compliant
            {"ip_address": "10.0.0.50", "mac_address": "AA:BB:CC:DD:00:03"},  # 同 MAC 在范围内新 IP -> non_compliant
        ]
        result, statuses = await _run_batch(service, scope, entries)

        assert result.compliant == 4
        assert result.non_compliant == 1
        assert statuses[("10.0.0.50", "AA:BB:CC:DD:00:03")] == "non_compliant"


class TestScopeMacPrefixArp:
    """mac_prefix_arp -> IP-only（仅命中前缀的 MAC 触发）：同 IP 下分化。"""

    async def test_same_ip_multi_mac_and_same_mac_multi_ip(self, service):
        scope = [{"scope_type": "mac_prefix_arp", "scope_value": "AA:BB:CC"}]
        entries = [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},  # 前缀命中 + IP 在基线 -> compliant
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:99"},  # 前缀命中 + IP 在基线 -> compliant
            {"ip_address": "10.0.0.10", "mac_address": "FF:EE:DD:CC:BB:AA"},  # 前缀不命中 -> 回落 AND -> non_compliant
            {"ip_address": "10.0.0.30", "mac_address": "AA:BB:CC:DD:00:03"},  # 前缀命中 + IP 在基线 -> compliant
            {"ip_address": "10.0.0.50", "mac_address": "AA:BB:CC:DD:00:03"},  # 同 MAC 新 IP 不在基线 -> non_compliant
        ]
        result, statuses = await _run_batch(service, scope, entries)

        assert result.compliant == 3
        assert result.non_compliant == 2
        assert statuses[("10.0.0.10", "FF:EE:DD:CC:BB:AA")] == "non_compliant"
        assert statuses[("10.0.0.50", "AA:BB:CC:DD:00:03")] == "non_compliant"


class TestScopeIpCidrAny:
    """ip_cidr_any -> OR：IP 或 MAC 任一命中；MAC 跨 IP 命中即合规。"""

    async def test_same_ip_multi_mac_and_same_mac_multi_ip(self, service):
        scope = [{"scope_type": "ip_cidr_any", "scope_value": "10.0.0.0/24"}]
        entries = [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},  # both -> compliant
            {"ip_address": "10.0.0.10", "mac_address": "FF:EE:DD:CC:00:99"},  # IP 命中 -> compliant
            {"ip_address": "10.0.0.50", "mac_address": "AA:BB:CC:DD:00:01"},  # MAC 跨 IP 命中 -> compliant
            {"ip_address": "10.0.0.99", "mac_address": "AA:BB:CC:DD:00:03"},  # 同 MAC 跨 IP 命中 -> compliant
            {"ip_address": "10.0.0.99", "mac_address": "FF:EE:DD:CC:00:99"},  # 都不命中 -> non_compliant
        ]
        result, statuses = await _run_batch(service, scope, entries)

        assert result.compliant == 4
        assert result.non_compliant == 1
        assert statuses[("10.0.0.50", "AA:BB:CC:DD:00:01")] == "compliant"
        assert statuses[("10.0.0.99", "AA:BB:CC:DD:00:03")] == "compliant"


class TestScopeIpRangeAny:
    """ip_range_any -> OR：同 ip_cidr_any。"""

    async def test_same_ip_multi_mac_and_same_mac_multi_ip(self, service):
        scope = [{"scope_type": "ip_range_any", "scope_value": "10.0.0.1-100"}]
        entries = [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},  # compliant
            {"ip_address": "10.0.0.10", "mac_address": "FF:EE:DD:CC:00:99"},  # IP 命中 -> compliant
            {"ip_address": "10.0.0.40", "mac_address": "AA:BB:CC:DD:00:03"},  # compliant
            {"ip_address": "10.0.0.50", "mac_address": "AA:BB:CC:DD:00:03"},  # 同 MAC 跨 IP -> compliant
            {"ip_address": "10.0.0.50", "mac_address": "FF:EE:DD:CC:00:99"},  # 都不命中 -> non_compliant
        ]
        result, statuses = await _run_batch(service, scope, entries)

        assert result.compliant == 4
        assert result.non_compliant == 1
        assert statuses[("10.0.0.50", "AA:BB:CC:DD:00:03")] == "compliant"


class TestScopeMacPrefixAny:
    """mac_prefix_any -> OR（仅命中前缀的 MAC 触发）。"""

    async def test_same_ip_multi_mac_and_same_mac_multi_ip(self, service):
        scope = [{"scope_type": "mac_prefix_any", "scope_value": "AA:BB:CC"}]
        entries = [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},  # IP 命中 -> compliant
            {"ip_address": "10.0.0.50", "mac_address": "AA:BB:CC:DD:00:01"},  # 前缀命中 + MAC 跨 IP -> compliant
            {"ip_address": "10.0.0.99", "mac_address": "AA:BB:CC:DD:00:03"},  # 前缀命中 + MAC 跨 IP -> compliant
            {"ip_address": "10.0.0.50", "mac_address": "AA:BB:CC:DD:00:99"},  # 前缀命中但 IP/MAC 都不命中 -> non_compliant
            {"ip_address": "10.0.0.50", "mac_address": "FF:EE:DD:CC:BB:AA"},  # 前缀不命中 -> 回落 AND -> non_compliant
        ]
        result, statuses = await _run_batch(service, scope, entries)

        assert result.compliant == 3
        assert result.non_compliant == 2
        assert statuses[("10.0.0.50", "AA:BB:CC:DD:00:99")] == "non_compliant"
        assert statuses[("10.0.0.50", "FF:EE:DD:CC:BB:AA")] == "non_compliant"


class TestScopeMacPrefixIpguard:
    """mac_prefix_ipguard -> AND 扩展：同 IP 全 MAC 合；同 MAC 跨 IP 不合（与 OR 不同）。"""

    async def test_same_ip_multi_mac_and_same_mac_multi_ip(self, service):
        scope = [{"scope_type": "mac_prefix_ipguard", "scope_value": "AA:BB:CC"}]
        entries = [
            {"ip_address": "10.0.0.10", "mac_address": "AA:BB:CC:DD:00:01"},  # 精确配对 -> compliant
            {"ip_address": "10.0.0.10", "mac_address": "11:22:33:44:55:66"},  # IP 在基线 + 基线 MAC 前缀命中 -> compliant
            {"ip_address": "10.0.0.30", "mac_address": "AA:BB:CC:DD:00:03"},  # 精确配对 -> compliant
            {"ip_address": "10.0.0.30", "mac_address": "22:33:44:55:66:77"},  # IP 在基线 + 基线 MAC 前缀命中 -> compliant
            {"ip_address": "10.0.0.99", "mac_address": "AA:BB:CC:DD:00:01"},  # 同 MAC 跨 IP 但新 IP 不在基线 -> non_compliant
            {"ip_address": "10.0.0.99", "mac_address": "FF:EE:DD:CC:BB:AA"},  # 都不命中 -> non_compliant
        ]
        result, statuses = await _run_batch(service, scope, entries)

        assert result.compliant == 4
        assert result.non_compliant == 2
        assert statuses[("10.0.0.10", "11:22:33:44:55:66")] == "compliant"
        assert statuses[("10.0.0.99", "AA:BB:CC:DD:00:01")] == "non_compliant"