"""Unit tests for TerminalExclusionService validation and matching helpers."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.blacklist import Blacklist
from app.models.terminal import Terminal
from app.models.terminal_exclusion import TerminalExclusion
from app.schemas.terminal_exclusion import TerminalExclusionCreate
from app.services.compliance_service import ComplianceService
from app.services.terminal_exclusion_service import TerminalExclusionService

# ---------------------------------------------------------------------------
# validate_and_normalize
# ---------------------------------------------------------------------------

class TestValidation:
    def test_single_ip(self):
        values = TerminalExclusionService.validate_and_normalize(
            "single_ip", "192.168.1.10", None, None
        )
        assert values == {
            "ip_pattern": "192.168.1.10",
            "ip_pattern_type": "single_ip",
            "mac_address": None,
            "mac_pattern_type": None,
        }

    def test_cidr_normalized_to_network(self):
        values = TerminalExclusionService.validate_and_normalize(
            "cidr", "192.168.1.45/24", None, None
        )
        assert values["ip_pattern"] == "192.168.1.0/24"
        assert values["ip_pattern_type"] == "cidr"

    def test_ip_range(self):
        values = TerminalExclusionService.validate_and_normalize(
            "ip_range", "192.168.1.1-100", None, None
        )
        assert values["ip_pattern"] == "192.168.1.1-100"
        assert values["ip_pattern_type"] == "ip_range"

    def test_full_mac_formatted(self):
        values = TerminalExclusionService.validate_and_normalize(
            None, None, "mac", "aa-bb-cc-dd-ee-ff"
        )
        assert values["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert values["mac_pattern_type"] == "mac"

    def test_mac_prefix_formatted(self):
        values = TerminalExclusionService.validate_and_normalize(
            None, None, "mac_prefix", "aabbcc"
        )
        assert values["mac_address"] == "AA:BB:CC"
        assert values["mac_pattern_type"] == "mac_prefix"

    def test_ip_and_mac_together(self):
        values = TerminalExclusionService.validate_and_normalize(
            "single_ip", "10.0.0.1", "mac_prefix", "AA:BB:CC"
        )
        assert values["ip_pattern"] == "10.0.0.1"
        assert values["mac_address"] == "AA:BB:CC"

    def test_empty_conditions_rejected(self):
        with pytest.raises(ValueError, match="At least one"):
            TerminalExclusionService.validate_and_normalize(None, "  ", None, "")

    def test_ip_without_type_rejected(self):
        with pytest.raises(ValueError, match="IP condition type"):
            TerminalExclusionService.validate_and_normalize(None, "10.0.0.1", None, None)

    def test_mac_without_type_rejected(self):
        with pytest.raises(ValueError, match="MAC condition type"):
            TerminalExclusionService.validate_and_normalize(None, None, None, "AA:BB:CC")

    @pytest.mark.parametrize("value", ["10.0.0.999", "not-an-ip", "10.0.0"])
    def test_invalid_single_ip(self, value):
        with pytest.raises(ValueError, match="Invalid IP address"):
            TerminalExclusionService.validate_and_normalize("single_ip", value, None, None)

    @pytest.mark.parametrize("value", ["10.0.0.0", "10.0.0.0/33", "10.0.0.0/x"])
    def test_invalid_cidr(self, value):
        with pytest.raises(ValueError):
            TerminalExclusionService.validate_and_normalize("cidr", value, None, None)

    @pytest.mark.parametrize("value", ["10.0.0.1-300", "10.0.0.20-10", "10.0.0-10", "x.y.z.1-10"])
    def test_invalid_range(self, value):
        with pytest.raises(ValueError):
            TerminalExclusionService.validate_and_normalize("ip_range", value, None, None)

    @pytest.mark.parametrize("value", ["AA:BB", "AA:BB:CC:DD:EE:FF:00", "GG:BB:CC"])
    def test_invalid_mac_prefix(self, value):
        with pytest.raises(ValueError):
            TerminalExclusionService.validate_and_normalize(None, None, "mac_prefix", value)

    def test_invalid_full_mac(self):
        with pytest.raises(ValueError):
            TerminalExclusionService.validate_and_normalize(
                None, None, "mac", "AA:BB:CC"
            )


# ---------------------------------------------------------------------------
# match_ip / match_mac
# ---------------------------------------------------------------------------

class TestMatching:
    def test_single_ip_match(self):
        assert TerminalExclusionService.match_ip("192.168.1.10", "192.168.1.10", "single_ip")
        assert not TerminalExclusionService.match_ip(
            "192.168.1.11", "192.168.1.10", "single_ip"
        )

    def test_cidr_match(self):
        assert TerminalExclusionService.match_ip("192.168.1.200", "192.168.1.0/24", "cidr")
        assert not TerminalExclusionService.match_ip("192.168.2.1", "192.168.1.0/24", "cidr")

    def test_range_match(self):
        assert TerminalExclusionService.match_ip("192.168.1.100", "192.168.1.1-100", "ip_range")
        assert not TerminalExclusionService.match_ip(
            "192.168.1.101", "192.168.1.1-100", "ip_range"
        )
        # Prefix must match as a whole octet group, not a string prefix.
        assert not TerminalExclusionService.match_ip(
            "192.168.10.5", "192.168.1.1-255", "ip_range"
        )

    def test_invalid_ip_never_matches(self):
        assert not TerminalExclusionService.match_ip("", "192.168.1.0/24", "cidr")
        assert not TerminalExclusionService.match_ip("bogus", "192.168.1.0/24", "cidr")

    def test_mac_exact_match_ignores_format(self):
        assert TerminalExclusionService.match_mac(
            "aa-bb-cc-dd-ee-ff", "AA:BB:CC:DD:EE:FF", "mac"
        )
        assert not TerminalExclusionService.match_mac(
            "AA:BB:CC:DD:EE:00", "AA:BB:CC:DD:EE:FF", "mac"
        )

    def test_mac_prefix_match(self):
        assert TerminalExclusionService.match_mac(
            "AA:BB:CC:11:22:33", "AA:BB:CC", "mac_prefix"
        )
        assert not TerminalExclusionService.match_mac(
            "AA:BB:DD:11:22:33", "AA:BB:CC", "mac_prefix"
        )

    def test_rule_with_both_conditions_is_and(self):
        rule = {
            "ip_pattern": "192.168.1.0/24",
            "ip_pattern_type": "cidr",
            "mac_address": "AA:BB:CC",
            "mac_pattern_type": "mac_prefix",
        }
        assert TerminalExclusionService.matches_rule(
            rule, "192.168.1.5", "AA:BB:CC:00:00:01"
        )
        assert not TerminalExclusionService.matches_rule(
            rule, "192.168.1.5", "AA:BB:DD:00:00:01"
        )
        assert not TerminalExclusionService.matches_rule(
            rule, "10.0.0.5", "AA:BB:CC:00:00:01"
        )

    def test_rules_are_or(self):
        rules = [
            {
                "ip_pattern": "192.168.1.10",
                "ip_pattern_type": "single_ip",
                "mac_address": None,
                "mac_pattern_type": None,
            },
            {
                "ip_pattern": None,
                "ip_pattern_type": None,
                "mac_address": "AA:BB:CC",
                "mac_pattern_type": "mac_prefix",
            },
        ]
        assert TerminalExclusionService.matches_any(
            rules, "192.168.1.10", "11:22:33:44:55:66"
        )
        assert TerminalExclusionService.matches_any(
            rules, "10.0.0.1", "AA:BB:CC:44:55:66"
        )
        assert not TerminalExclusionService.matches_any(
            rules, "10.0.0.1", "11:22:33:44:55:66"
        )

    def test_empty_rule_never_matches(self):
        assert not TerminalExclusionService.matches_any(
            [], "10.0.0.1", "AA:BB:CC:DD:EE:FF"
        )


# ---------------------------------------------------------------------------
# IP range / CIDR boundary cases
# ---------------------------------------------------------------------------

class TestIpRangeBoundaries:
    @pytest.mark.parametrize("ip", ["10.0.0.1", "10.0.0.50", "10.0.0.100"])
    def test_range_is_inclusive_on_both_ends(self, ip):
        assert TerminalExclusionService.match_ip(ip, "10.0.0.1-100", "ip_range")

    @pytest.mark.parametrize("ip", ["10.0.0.0", "10.0.0.101", "10.0.1.1", "11.0.0.50"])
    def test_outside_range_does_not_match(self, ip):
        assert not TerminalExclusionService.match_ip(ip, "10.0.0.1-100", "ip_range")

    def test_single_host_range_matches_only_that_host(self):
        assert TerminalExclusionService.match_ip("10.0.0.5", "10.0.0.5-5", "ip_range")
        assert not TerminalExclusionService.match_ip("10.0.0.4", "10.0.0.5-5", "ip_range")
        assert not TerminalExclusionService.match_ip("10.0.0.6", "10.0.0.5-5", "ip_range")

    def test_range_accepts_full_last_octet_span(self):
        values = TerminalExclusionService.validate_and_normalize(
            "ip_range", "10.0.0.0-255", None, None
        )
        assert values["ip_pattern"] == "10.0.0.0-255"
        assert TerminalExclusionService.match_ip("10.0.0.255", values["ip_pattern"], "ip_range")

    def test_range_requires_same_three_octet_prefix(self):
        # 10.0.10.x 不能被 10.0.1.x-y 规则命中（前缀按整段比较）。
        assert not TerminalExclusionService.match_ip("10.0.10.5", "10.0.1.1-255", "ip_range")

    @pytest.mark.parametrize(
        "value",
        ["10.0.0.1-1-2", "10.0.0.", "10.0.0.1-", "10.0.0.-1", "10.0.0.1~10", " 10.0.0.1-10 "],
    )
    def test_malformed_range_is_rejected_or_trimmed(self, value):
        if value.strip() == value:
            with pytest.raises(ValueError):
                TerminalExclusionService.validate_and_normalize("ip_range", value, None, None)
        else:
            # 两端空白由校验层统一 strip 后接受。
            values = TerminalExclusionService.validate_and_normalize(
                "ip_range", value, None, None
            )
            assert values["ip_pattern"] == "10.0.0.1-10"

    def test_range_with_start_greater_than_end_is_rejected(self):
        with pytest.raises(ValueError, match="greater than end"):
            TerminalExclusionService.validate_and_normalize(
                "ip_range", "10.0.0.100-99", None, None
            )

    def test_range_with_end_above_255_is_rejected(self):
        with pytest.raises(ValueError, match="exceeds 255"):
            TerminalExclusionService.validate_and_normalize(
                "ip_range", "10.0.0.1-256", None, None
            )

    def test_range_does_not_match_ipv6(self):
        assert not TerminalExclusionService.match_ip("2001:db8::1", "10.0.0.1-100", "ip_range")


class TestCidrBoundaries:
    def test_slash_32_matches_single_host(self):
        assert TerminalExclusionService.match_ip("10.1.2.3", "10.1.2.3/32", "cidr")
        assert not TerminalExclusionService.match_ip("10.1.2.4", "10.1.2.3/32", "cidr")

    def test_slash_0_matches_every_ipv4(self):
        for ip in ("0.0.0.0", "10.1.2.3", "255.255.255.255"):
            assert TerminalExclusionService.match_ip(ip, "0.0.0.0/0", "cidr")

    def test_malformed_cidr_pattern_never_matches(self):
        assert not TerminalExclusionService.match_ip("10.1.2.3", "10.1.2.0/33", "cidr")
        assert not TerminalExclusionService.match_ip("10.1.2.3", "not-a-cidr", "cidr")

    def test_unknown_pattern_type_never_matches(self):
        assert not TerminalExclusionService.match_ip("10.1.2.3", "10.1.2.3", "bogus")


# ---------------------------------------------------------------------------
# MAC prefix boundary cases
# ---------------------------------------------------------------------------

class TestMacPrefixBoundaries:
    def test_one_byte_prefix_matches(self):
        assert TerminalExclusionService.match_mac(
            "AA:11:22:33:44:55", "AA", "mac_prefix"
        )
        assert not TerminalExclusionService.match_mac(
            "AB:11:22:33:44:55", "AA", "mac_prefix"
        )

    def test_prefix_is_case_and_separator_insensitive(self):
        for mac in ("aa-bb-cc-dd-ee-ff", "AA:BB:CC:DD:EE:FF", "aabb.ccdd.eeff", "AABBCCDDEEFF"):
            assert TerminalExclusionService.match_mac(mac, "aa:bb:cc", "mac_prefix")

    def test_prefix_must_align_to_hex_boundary(self):
        # 前缀 "AA:BB:C" 不能按字符串前缀命中 MAC；校验层只接受成对十六进制。
        with pytest.raises(ValueError):
            TerminalExclusionService.validate_and_normalize(
                None, None, "mac_prefix", "AA:BB:C"
            )

    def test_full_mac_as_prefix_equals_exact_match(self):
        assert TerminalExclusionService.match_mac(
            "AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:FF", "mac_prefix"
        )
        assert not TerminalExclusionService.match_mac(
            "AA:BB:CC:DD:EE:FE", "AA:BB:CC:DD:EE:FF", "mac_prefix"
        )

    def test_empty_or_invalid_mac_never_matches(self):
        assert not TerminalExclusionService.match_mac("", "AA:BB:CC", "mac_prefix")
        assert not TerminalExclusionService.match_mac("bogus", "AA:BB:CC", "mac_prefix")
        assert not TerminalExclusionService.match_mac("AA:BB:CC:DD:EE:FF", "", "mac_prefix")

    def test_unknown_pattern_type_never_matches(self):
        assert not TerminalExclusionService.match_mac(
            "AA:BB:CC:DD:EE:FF", "AA:BB:CC", "bogus"
        )

    def test_prefix_normalization_handles_dash_and_cisco_dot(self):
        values = TerminalExclusionService.validate_and_normalize(
            None, None, "mac_prefix", "aabb.ccdd"
        )
        assert values["mac_address"] == "AA:BB:CC:DD"
        assert TerminalExclusionService.match_mac(
            "AA-BB-CC-DD-11-22", values["mac_address"], "mac_prefix"
        )


# ---------------------------------------------------------------------------
# Rule combination: intra-rule AND, inter-rule OR
# ---------------------------------------------------------------------------

class TestRuleCombinations:
    def _rule(self, ip=None, ip_type=None, mac=None, mac_type=None):
        return {
            "ip_pattern": ip,
            "ip_pattern_type": ip_type,
            "mac_address": mac,
            "mac_pattern_type": mac_type,
        }

    def test_and_requires_both_conditions(self):
        rule = self._rule("10.0.0.0/24", "cidr", "AA:BB:CC", "mac_prefix")
        assert TerminalExclusionService.matches_rule(rule, "10.0.0.9", "AA:BB:CC:00:00:01")
        assert not TerminalExclusionService.matches_rule(rule, "10.0.0.9", "DD:EE:FF:00:00:01")
        assert not TerminalExclusionService.matches_rule(rule, "10.0.1.9", "AA:BB:CC:00:00:01")

    def test_and_with_range_and_full_mac(self):
        rule = self._rule("10.0.0.10-20", "ip_range", "AA:BB:CC:DD:EE:FF", "mac")
        assert TerminalExclusionService.matches_rule(rule, "10.0.0.20", "aa-bb-cc-dd-ee-ff")
        assert not TerminalExclusionService.matches_rule(rule, "10.0.0.21", "aa-bb-cc-dd-ee-ff")
        assert not TerminalExclusionService.matches_rule(rule, "10.0.0.20", "aa-bb-cc-dd-ee-fe")

    def test_rule_without_any_condition_never_matches(self):
        assert not TerminalExclusionService.matches_rule(
            self._rule(), "10.0.0.1", "AA:BB:CC:DD:EE:FF"
        )

    def test_rule_with_value_but_missing_type_never_matches(self):
        assert not TerminalExclusionService.matches_rule(
            self._rule(ip="10.0.0.1"), "10.0.0.1", "AA:BB:CC:DD:EE:FF"
        )
        assert not TerminalExclusionService.matches_rule(
            self._rule(mac="AA:BB:CC"), "10.0.0.1", "AA:BB:CC:DD:EE:FF"
        )

    def test_multiple_and_rules_are_ored(self):
        rules = [
            self._rule("10.0.0.0/24", "cidr", "AA:BB:CC", "mac_prefix"),
            self._rule("172.16.0.10-20", "ip_range", None, None),
            self._rule(None, None, "DE:AD:BE:EF", "mac_prefix"),
        ]
        # 第 1 条命中
        assert TerminalExclusionService.matches_any(rules, "10.0.0.7", "AA:BB:CC:00:00:01")
        # 第 2 条命中（IP 段）
        assert TerminalExclusionService.matches_any(rules, "172.16.0.15", "11:22:33:44:55:66")
        # 第 3 条命中（MAC 前缀）
        assert TerminalExclusionService.matches_any(rules, "8.8.8.8", "DE:AD:BE:EF:00:01")
        # 三条都不满足
        assert not TerminalExclusionService.matches_any(
            rules, "10.0.1.7", "11:22:33:44:55:66"
        )

    def test_and_rule_prevents_partial_or_match(self):
        # 第一条 AND 规则中 IP 命中但 MAC 不命中时，不能因「IP 相似」误排除到其他规则。
        rules = [
            self._rule("10.0.0.0/24", "cidr", "AA:BB:CC", "mac_prefix"),
            self._rule("192.168.5.5", "single_ip", None, None),
        ]
        assert not TerminalExclusionService.matches_any(
            rules, "10.0.0.7", "DD:EE:FF:00:00:01"
        )

    def test_first_match_returns_matching_rule(self):
        single_ip_rule = self._rule("10.0.0.1", "single_ip")
        prefix_rule = self._rule(None, None, "AA:BB:CC", "mac_prefix")
        rules = [single_ip_rule, prefix_rule]

        assert TerminalExclusionService.first_match(rules, "10.0.0.1", "11:22:33:44:55:66") is single_ip_rule
        assert TerminalExclusionService.first_match(rules, "10.0.0.2", "AA:BB:CC:11:22:33") is prefix_rule
        assert TerminalExclusionService.first_match(rules, "10.0.0.2", "11:22:33:44:55:66") is None

    def test_describe_rule_formats_conditions(self):
        assert TerminalExclusionService.describe_rule(
            self._rule("10.0.0.0/24", "cidr")
        ) == "IP cidr=10.0.0.0/24"
        assert TerminalExclusionService.describe_rule(
            self._rule(mac="AA:BB:CC", mac_type="mac_prefix")
        ) == "MAC mac_prefix=AA:BB:CC"
        assert TerminalExclusionService.describe_rule(
            self._rule("10.0.0.1-10", "ip_range", "AA:BB:CC:DD:EE:FF", "mac")
        ) == "IP ip_range=10.0.0.1-10 AND MAC mac=AA:BB:CC:DD:EE:FF"
        assert TerminalExclusionService.describe_rule(None) == "<none>"
        assert TerminalExclusionService.describe_rule(self._rule()) == "<empty>"



# ---------------------------------------------------------------------------
# Retroactive cleanup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_rule_purges_unblocked_and_keeps_blocked():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Terminal.__table__, Blacklist.__table__, TerminalExclusion.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all([
            Terminal(
                ip_address="192.168.1.10",
                mac_address="AA:BB:CC:00:00:01",
                mac_address_normalized="AABBCC000001",
                status="unblocked",
            ),
            Terminal(
                ip_address="192.168.1.11",
                mac_address="AA:BB:CC:00:00:02",
                mac_address_normalized="AABBCC000002",
                status="blocked",
            ),
            Terminal(
                ip_address="192.168.1.20",
                mac_address="DD:EE:FF:00:00:01",
                mac_address_normalized="DDEEFF000001",
                status="unblocked",
            ),
        ])
        await session.commit()

        service = TerminalExclusionService(session)
        rule, impact, unblock = await service.create_rule(
            TerminalExclusionCreate(
                mac_type="mac_prefix",
                mac_value="AA:BB:CC",
                comments="Printers",
            ),
            "tester",
        )

        assert rule.is_active is True
        assert impact.matched == 2
        assert impact.purgeable == 1
        assert impact.retained == 1
        assert impact.blocked == 1
        assert unblock is None

        remaining = (await session.execute(Terminal.__table__.select())).all()
        remaining_ips = {row.ip_address for row in remaining}
        assert remaining_ips == {"192.168.1.11", "192.168.1.20"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_active_blacklist_terminal_is_retained():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Terminal.__table__, Blacklist.__table__, TerminalExclusion.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all([
            Terminal(
                ip_address="10.0.0.5",
                mac_address="AA:BB:CC:DD:EE:FF",
                mac_address_normalized="AABBCCDDEEFF",
                status="unblocked",
            ),
            Blacklist(
                ip_address="10.0.0.5",
                mac_address="AA:BB:CC:DD:EE:FF",
                blocked_by="tester",
            ),
        ])
        await session.commit()

        service = TerminalExclusionService(session)
        _, impact, _ = await service.create_rule(
            TerminalExclusionCreate(
                ip_type="cidr",
                ip_value="10.0.0.0/24",
                comments="Servers",
            ),
            "tester",
        )

        assert impact.matched == 1
        assert impact.purgeable == 0
        assert impact.retained == 1
        assert impact.blocked == 0
        assert impact.samples[0].reason == "active_blacklist"

    await engine.dispose()


# ---------------------------------------------------------------------------
# Optional unblock of blocked terminals
# ---------------------------------------------------------------------------

async def _make_session(with_terminal: bool = True, **blacklist_kwargs):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Terminal.__table__, Blacklist.__table__, TerminalExclusion.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    if with_terminal:
        session.add(Terminal(
            ip_address="10.0.0.9",
            mac_address="AA:BB:CC:DD:EE:09",
            mac_address_normalized="AABBCCDDEE09",
            status="blocked",
            compliance_status="non_compliant",
        ))
    session.add(Blacklist(
        ip_address="10.0.0.9",
        mac_address="AA:BB:CC:DD:EE:09",
        mac_address_normalized="AABBCCDDEE09",
        blocked_by="tester",
        **blacklist_kwargs,
    ))
    await session.commit()
    return engine, session


def _rule_data(unblock: bool = True) -> TerminalExclusionCreate:
    return TerminalExclusionCreate(
        ip_type="single_ip",
        ip_value="10.0.0.9",
        comments="excluded printer",
        unblock_blocked=unblock,
    )


@pytest.mark.asyncio
async def test_unblock_blocked_terminal_success_removes_record():
    engine, session = await _make_session(firewall_tag="fw1")
    try:
        with (
            patch.object(
                ComplianceService, "_unblock_on_firewall", AsyncMock(return_value=True)
            ) as unblock_mock,
            patch("app.services.event_emitter.emit_terminal_unblocked", AsyncMock()),
        ):
            _, impact, unblock = await TerminalExclusionService(session).create_rule(
                _rule_data(), "operator"
            )

        assert impact.blocked == 1
        assert impact.retained == 0
        assert unblock is not None
        assert (unblock.requested, unblock.unblocked, unblock.failed, unblock.skipped) == (
            True, 1, 0, 0,
        )
        assert unblock.errors == []
        # 解封审计归属当前操作人，而不是固定 system。
        assert unblock_mock.await_args.kwargs["actor"] == "operator"

        terminals = (await session.execute(select(Terminal))).scalars().all()
        assert terminals == []

        entry = (await session.execute(select(Blacklist))).scalars().one()
        assert entry.auto_unblocked is True
        assert entry.unblock_reason == "excluded_by_rule"
        assert entry.last_operation_status == "success"
        assert entry.unblocked_at is not None
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unblock_failure_keeps_terminal_and_flag():
    engine, session = await _make_session(firewall_tag="fw1")
    try:
        with (
            patch.object(
                ComplianceService, "_unblock_on_firewall", AsyncMock(return_value=False)
            ),
            patch("app.services.event_emitter.emit_terminal_unblocked", AsyncMock()),
        ):
            _, impact, unblock = await TerminalExclusionService(session).create_rule(
                _rule_data(), "operator"
            )

        assert impact.retained == 1
        assert unblock is not None
        assert (unblock.unblocked, unblock.failed, unblock.skipped) == (0, 1, 0)
        assert unblock.errors

        terminal = (await session.execute(select(Terminal))).scalars().one()
        assert terminal.status == "blocked"
        assert terminal.excluded_by_rule is True

        entry = (await session.execute(select(Blacklist))).scalars().one()
        assert entry.auto_unblocked is False
        assert entry.unblock_reason is None
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unblock_skipped_without_firewall_binding():
    engine, session = await _make_session()  # 无 firewall_tag / source_tag
    try:
        with (
            patch.object(
                ComplianceService, "_unblock_on_firewall", AsyncMock(return_value=True)
            ) as unblock_mock,
            patch("app.services.event_emitter.emit_terminal_unblocked", AsyncMock()),
        ):
            _, impact, unblock = await TerminalExclusionService(session).create_rule(
                _rule_data(), "operator"
            )

        assert impact.retained == 1
        assert unblock is not None
        assert (unblock.unblocked, unblock.failed, unblock.skipped) == (0, 0, 1)
        assert "no firewall binding" in unblock.errors[0]
        unblock_mock.assert_not_awaited()

        assert (await session.execute(select(Terminal))).scalars().one().status == "blocked"
        assert (await session.execute(select(Blacklist))).scalars().one().auto_unblocked is False
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unblock_partial_multi_firewall_keeps_terminal():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [Terminal.__table__, Blacklist.__table__, TerminalExclusion.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(Terminal(
            ip_address="10.0.0.9",
            mac_address="AA:BB:CC:DD:EE:09",
            mac_address_normalized="AABBCCDDEE09",
            status="blocked",
            compliance_status="non_compliant",
        ))
        session.add_all([
            Blacklist(
                ip_address="10.0.0.9", mac_address="AA:BB:CC:DD:EE:09",
                mac_address_normalized="AABBCCDDEE09", blocked_by="tester",
                firewall_tag="fw1",
            ),
            Blacklist(
                ip_address="10.0.0.9", mac_address="AA:BB:CC:DD:EE:09",
                mac_address_normalized="AABBCCDDEE09", blocked_by="tester",
                firewall_tag="fw2",
            ),
        ])
        await session.commit()

        async def fake_unblock(ip, firewall_tag, *args, **kwargs):
            return firewall_tag == "fw1"

        with (
            patch.object(
                ComplianceService, "_unblock_on_firewall", AsyncMock(side_effect=fake_unblock)
            ),
            patch("app.services.event_emitter.emit_terminal_unblocked", AsyncMock()),
        ):
            _, impact, unblock = await TerminalExclusionService(session).create_rule(
                _rule_data(), "operator"
            )

        assert impact.retained == 1
        assert unblock is not None
        assert (unblock.unblocked, unblock.failed, unblock.skipped) == (0, 1, 0)
        assert (await session.execute(select(Terminal))).scalars().one().status == "blocked"

        entries = {
            entry.firewall_tag: entry
            for entry in (await session.execute(select(Blacklist))).scalars().all()
        }
        assert entries["fw1"].auto_unblocked is True
        assert entries["fw1"].unblock_reason == "excluded_by_rule（部分成功）"
        assert entries["fw2"].auto_unblocked is False

    await engine.dispose()
