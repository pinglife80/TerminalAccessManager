"""Tests for terminal_service.py pure helpers and IP/pattern parsing utilities.

Covers the module-level helper functions, IPAddressParser, and TerminalService
validation/encoding methods that previously had no dedicated coverage.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from app.services.terminal_service import (
    IPAddressParser,
    TerminalService,
    _parse_block_time,
    _parse_date_range,
)


class TestParseBlockTime:
    """Test _parse_block_time duration parsing."""

    def test_days(self):
        assert _parse_block_time("15d") == timedelta(days=15)

    def test_hours(self):
        assert _parse_block_time("6h") == timedelta(hours=6)

    def test_minutes(self):
        assert _parse_block_time("30m") == timedelta(minutes=30)

    def test_uppercase_unit(self):
        assert _parse_block_time("7D") == timedelta(days=7)

    def test_uppercase_value(self):
        assert _parse_block_time("2H") == timedelta(hours=2)

    def test_invalid_returns_default_30d(self):
        assert _parse_block_time("invalid") == timedelta(days=30)

    def test_empty_returns_default_30d(self):
        assert _parse_block_time("") == timedelta(days=30)

    def test_multiple_chars_returns_default(self):
        assert _parse_block_time("15dd") == timedelta(days=30)

    def test_unsupported_unit_returns_default(self):
        assert _parse_block_time("15w") == timedelta(days=30)


class TestParseDateRange:
    """Test _parse_date_range condition construction."""

    def _aware(self, *args):
        tz_name = os.environ.get("TZ", "Asia/Shanghai")
        tz = pytz.timezone(tz_name)
        return tz.localize(datetime(*args))

    def test_no_dates_returns_empty(self):
        assert _parse_date_range(None, None) == []

    def test_valid_start_date_produces_condition(self):
        conditions = _parse_date_range("2026-01-15", None)
        assert len(conditions) == 1
        assert conditions[0](self._aware(2026, 1, 16, 0, 0, 0)) is True
        assert conditions[0](self._aware(2026, 1, 14, 0, 0, 0)) is False

    def test_valid_end_date_caps_to_end_of_day(self):
        conditions = _parse_date_range(None, "2026-01-15")
        assert len(conditions) == 1
        assert conditions[0](self._aware(2026, 1, 15, 23, 59, 59)) is True
        assert conditions[0](self._aware(2026, 1, 16, 0, 0, 0)) is False

    def test_both_dates_produce_two_conditions(self):
        conditions = _parse_date_range("2026-01-01", "2026-01-31")
        assert len(conditions) == 2

    def test_invalid_start_date_is_silently_ignored(self):
        assert _parse_date_range("not-a-date", None) == []

    def test_invalid_end_date_is_ignored(self):
        assert _parse_date_range(None, "2026/01/31") == []


class TestIPAddressParser:
    """Test IPAddressParser static parsing methods."""

    # ---- parse_ip_input dispatch ----
    def test_single_ip(self):
        assert IPAddressParser.parse_ip_input("192.168.1.1") == ["192.168.1.1"]

    def test_cidr_dispatch(self):
        assert IPAddressParser.parse_ip_input("192.168.1.0/30") == ["192.168.1.1", "192.168.1.2"]

    def test_range_dispatch(self):
        assert IPAddressParser.parse_ip_input("192.168.1.1-3") == [
            "192.168.1.1",
            "192.168.1.2",
            "192.168.1.3",
        ]

    def test_range_with_subnet_dispatch(self):
        result = IPAddressParser.parse_ip_input("192.168.1.1-3/24")
        assert result == ["192.168.1.1", "192.168.1.2", "192.168.1.3"]

    def test_leading_trailing_whitespace_stripped(self):
        assert IPAddressParser.parse_ip_input("  192.168.1.1  ") == ["192.168.1.1"]

    # ---- _parse_cidr ----
    def test_parse_cidr_hosts(self):
        assert IPAddressParser._parse_cidr("192.168.1.0/30") == ["192.168.1.1", "192.168.1.2"]

    def test_parse_cidr_invalid_raises(self):
        with pytest.raises(ValueError):
            IPAddressParser._parse_cidr("999.1.1.0/24")

    # ---- _parse_ip_range ----
    def test_parse_ip_range(self):
        assert IPAddressParser._parse_ip_range("192.168.1.5-7") == [
            "192.168.1.5",
            "192.168.1.6",
            "192.168.1.7",
        ]

    def test_parse_ip_range_start_greater_than_end(self):
        with pytest.raises(ValueError):
            IPAddressParser._parse_ip_range("192.168.1.7-5")

    def test_parse_ip_range_end_exceeds_255(self):
        with pytest.raises(ValueError):
            IPAddressParser._parse_ip_range("192.168.1.250-256")

    def test_parse_ip_range_bad_format(self):
        with pytest.raises(ValueError):
            IPAddressParser._parse_ip_range("192.168.1-3")

    # ---- _parse_ip_range_with_subnet ----
    def test_parse_ip_range_with_subnet(self):
        assert IPAddressParser._parse_ip_range_with_subnet("192.168.1.1-3/24") == [
            "192.168.1.1",
            "192.168.1.2",
            "192.168.1.3",
        ]

    def test_parse_ip_range_with_subnet_filters_out_of_network(self):
        # /30 covers 192.168.1.0-3; .4 and .5 are outside and filtered out.
        result = IPAddressParser._parse_ip_range_with_subnet("192.168.1.1-5/30")
        assert result == ["192.168.1.1", "192.168.1.2", "192.168.1.3"]

    def test_parse_ip_range_with_invalid_subnet_raises(self):
        with pytest.raises(ValueError):
            IPAddressParser._parse_ip_range_with_subnet("192.168.1.1-3/33")

    def test_parse_ip_range_with_subnet_bad_format(self):
        with pytest.raises(ValueError):
            IPAddressParser._parse_ip_range_with_subnet("192.168.1.1-3")

    # ---- validate_ip ----
    def test_validate_ip_valid(self):
        assert IPAddressParser.validate_ip("192.168.1.1") is True

    def test_validate_ip_invalid(self):
        assert IPAddressParser.validate_ip("999.1.1.1") is False

    def test_validate_ip_malformed(self):
        assert IPAddressParser.validate_ip("not-an-ip") is False

    # ---- detect_pattern_type ----
    def test_detect_single_ip(self):
        assert IPAddressParser.detect_pattern_type("192.168.1.1") == "single_ip"

    def test_detect_cidr(self):
        assert IPAddressParser.detect_pattern_type("192.168.1.0/24") == "cidr"

    def test_detect_single_ip_host_route(self):
        assert IPAddressParser.detect_pattern_type("192.168.1.1/32") == "single_ip"

    def test_detect_ip_range(self):
        assert IPAddressParser.detect_pattern_type("192.168.1.1-10") == "ip_range"


class TestTerminalServiceValidation:
    """Test TerminalService validation and encoding helpers."""

    # ---- _validate_mac_format ----
    def test_mac_colon_format(self):
        assert TerminalService._validate_mac_format(None, "AA:BB:CC:DD:EE:FF") is True

    def test_mac_dash_format(self):
        assert TerminalService._validate_mac_format(None, "AA-BB-CC-DD-EE-FF") is True

    def test_mac_dot_format(self):
        # _validate_mac_format only accepts 6 groups of 2 hex (e.g. AA.BB.CC.DD.EE.FF)
        assert TerminalService._validate_mac_format(None, "AA.BB.CC.DD.EE.FF") is True

    def test_mac_dot_four_hex_groups_rejected(self):
        # Cisco 4-hex-group dot format (AABB.CCDD.EEFF) is normalized elsewhere but rejected here
        assert TerminalService._validate_mac_format(None, "AABB.CCDD.EEFF") is False

    def test_mac_lowercase_hex(self):
        assert TerminalService._validate_mac_format(None, "aa:bb:cc:dd:ee:ff") is True

    def test_mac_too_short(self):
        assert TerminalService._validate_mac_format(None, "AA:BB:CC:DD:EE") is False

    def test_mac_invalid(self):
        assert TerminalService._validate_mac_format(None, "not-a-mac") is False

    # ---- _validate_ip_pattern ----
    def test_ip_pattern_single(self):
        assert TerminalService._validate_ip_pattern(None, "192.168.1.1") is True

    def test_ip_pattern_cidr(self):
        assert TerminalService._validate_ip_pattern(None, "192.168.1.0/24") is True

    def test_ip_pattern_range(self):
        assert TerminalService._validate_ip_pattern(None, "192.168.1.1-10") is True

    def test_ip_pattern_range_with_subnet(self):
        assert TerminalService._validate_ip_pattern(None, "192.168.1.1-10/24") is True

    def test_ip_pattern_invalid_ip(self):
        assert TerminalService._validate_ip_pattern(None, "999.1.1.1") is False

    def test_ip_pattern_range_start_gt_end(self):
        assert TerminalService._validate_ip_pattern(None, "192.168.1.10-5") is False

    def test_ip_pattern_range_end_gt_255(self):
        assert TerminalService._validate_ip_pattern(None, "192.168.1.250-256") is False

    def test_ip_pattern_invalid_subnet(self):
        assert TerminalService._validate_ip_pattern(None, "192.168.1.1-10/33") is False

    def test_ip_pattern_garbage(self):
        assert TerminalService._validate_ip_pattern(None, "garbage") is False

    # ---- _determine_pattern_type ----
    def test_determine_both(self):
        assert TerminalService._determine_pattern_type(None, "AABBCCDDEEFF", "192.168.1.1") == "both"

    def test_determine_mac_only(self):
        assert TerminalService._determine_pattern_type(None, "AABBCCDDEEFF", None) == "mac_only"

    def test_determine_cidr(self):
        assert TerminalService._determine_pattern_type(None, None, "192.168.1.0/24") == "cidr"

    def test_determine_ip_range(self):
        assert TerminalService._determine_pattern_type(None, None, "192.168.1.1-10") == "ip_range"

    def test_determine_single_ip(self):
        assert TerminalService._determine_pattern_type(None, None, "192.168.1.1") == "single_ip"

    def test_determine_none(self):
        assert TerminalService._determine_pattern_type(None, None, None) == "mac_only"

    # ---- cursor encode/decode ----
    def test_cursor_roundtrip(self):
        ts = datetime(2026, 1, 15, 10, 30, 0)
        cursor = TerminalService._encode_cursor(ts, 42)
        decoded_ts, decoded_id = TerminalService._decode_cursor(cursor)
        assert decoded_ts == ts
        assert decoded_id == 42

    def test_cursor_is_urlsafe(self):
        cursor = TerminalService._encode_cursor(datetime(2026, 1, 15), 1)
        assert isinstance(cursor, str)
        assert "+" not in cursor
        assert "/" not in cursor


class TestAddToWhitelistMatching:
    """Test add_to_whitelist immediate-apply matching branches.

    Covers mac_only / ip_only / both semantics for a single MAC that has two
    IPs (e.g. a bridged VM), verifying that each branch selects the correct
    terminal set and passes the correct wl_match_type to the compliance layer.
    """

    MAC = "AA:BB:CC:DD:EE:FF"

    def _terminal(self, ip, mac=MAC):
        t = MagicMock()
        t.ip_address = ip
        t.mac_address = mac
        t.mac_address_normalized = mac.replace(':', '').replace('-', '').replace('.', '').upper()
        return t

    def _matched_result(self, terminals):
        matched = MagicMock()
        matched.scalars.return_value.all.return_value = terminals
        return matched

    def _no_existing_result(self):
        existing = MagicMock()
        existing.scalar_one_or_none.return_value = None
        return existing

    def _compliance_mock(self):
        mock = MagicMock()
        mock.invalidate_whitelist_cache = AsyncMock()
        mock.apply_manual_whitelist_for_terminal = AsyncMock(return_value={"status": "bypass"})
        mock.recalculate_all_compliance = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_mac_only_applies_to_all_ips_sharing_mac(self, mock_async_session):
        """mac_only: one MAC with two IPs -> both terminals get bypass with wl_match_type='mac'."""
        t_100 = self._terminal("192.168.1.100")
        t_200 = self._terminal("192.168.1.200")

        mock_async_session.execute = AsyncMock(
            side_effect=[self._no_existing_result(), self._matched_result([t_100, t_200])]
        )
        compliance_mock = self._compliance_mock()
        svc = TerminalService(mock_async_session)

        with patch("app.services.compliance_service.ComplianceService", return_value=compliance_mock), \
             patch("app.services.event_emitter.emit_whitelist_changed", new=AsyncMock()):
            result = await svc.add_to_whitelist(mac_address=self.MAC, username="admin")

        assert result["success"] is True
        assert compliance_mock.apply_manual_whitelist_for_terminal.await_count == 2
        applied_terminals = [
            call.args[0] for call in compliance_mock.apply_manual_whitelist_for_terminal.await_args_list
        ]
        assert applied_terminals == [t_100, t_200]
        applied_types = [
            call.kwargs["wl_match_type"] for call in compliance_mock.apply_manual_whitelist_for_terminal.await_args_list
        ]
        assert applied_types == ["mac", "mac"]

    @pytest.mark.asyncio
    async def test_ip_only_applies_only_to_matching_ip(self, mock_async_session):
        """ip_only: same MAC with two IPs -> only the terminal holding the target IP is matched."""
        t_32 = self._terminal("10.8.14.32")
        t_100 = self._terminal("10.8.14.100")

        mock_async_session.execute = AsyncMock(
            side_effect=[self._no_existing_result(), self._matched_result([t_32])]
        )
        compliance_mock = self._compliance_mock()
        svc = TerminalService(mock_async_session)

        with patch("app.services.compliance_service.ComplianceService", return_value=compliance_mock), \
             patch("app.services.event_emitter.emit_whitelist_changed", new=AsyncMock()):
            result = await svc.add_to_whitelist(ip_address="10.8.14.32", username="admin")

        assert result["success"] is True
        assert compliance_mock.apply_manual_whitelist_for_terminal.await_count == 1
        call = compliance_mock.apply_manual_whitelist_for_terminal.await_args
        assert call.args[0] is t_32
        assert call.kwargs["wl_match_type"] == "ip"

    @pytest.mark.asyncio
    async def test_both_applies_only_to_exact_mac_ip_match(self, mock_async_session):
        """both: same MAC with two IPs -> only the exact (MAC, IP) pair is matched, not the sibling IP."""
        t_32 = self._terminal("10.8.14.32")
        t_100 = self._terminal("10.8.14.100")

        mock_async_session.execute = AsyncMock(
            side_effect=[self._no_existing_result(), self._matched_result([t_32])]
        )
        compliance_mock = self._compliance_mock()
        svc = TerminalService(mock_async_session)

        with patch("app.services.compliance_service.ComplianceService", return_value=compliance_mock), \
             patch("app.services.event_emitter.emit_whitelist_changed", new=AsyncMock()):
            result = await svc.add_to_whitelist(
                mac_address=self.MAC, ip_address="10.8.14.32", username="admin"
            )

        assert result["success"] is True
        assert compliance_mock.apply_manual_whitelist_for_terminal.await_count == 1
        call = compliance_mock.apply_manual_whitelist_for_terminal.await_args
        assert call.args[0] is t_32
        assert call.kwargs["wl_match_type"] == "both"