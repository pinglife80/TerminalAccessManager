"""端到端集成测试：排除规则与白名单同时存在时的完整采集链路。

与单元测试不同，这里不 mock `batch_check_compliance`，而是使用真实的
Whitelist / TerminalExclusion / Terminal 数据表，跑通：

    ARP 条目 -> 排除规则过滤（入库前）-> 白名单/合规判定
             -> terminals 落库 -> 仪表盘统计（get_stats）

以及合规重算链路（recalculate_all_compliance）中对排除终端的跳过守卫。

仅 mock 系统外部依赖：Redis、事件推送、审计落库、IPGuard 远端数据。
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.blacklist import Blacklist
from app.models.compliance_baseline import ComplianceBaseline
from app.models.compliance_scope import ComplianceScope
from app.models.data_source import DataSource
from app.models.system_config import SystemConfig
from app.models.terminal import Terminal
from app.models.terminal_exclusion import TerminalExclusion
from app.models.whitelist import Whitelist
from app.services.arp_collector_service import ArpCollectorService
from app.services.compliance_service import ComplianceService
from app.services.terminal_exclusion_service import TerminalExclusionService
from app.services.terminal_service import TerminalService

TABLES = [
    Terminal.__table__,
    Whitelist.__table__,
    Blacklist.__table__,
    TerminalExclusion.__table__,
    DataSource.__table__,
    SystemConfig.__table__,
    ComplianceBaseline.__table__,
    ComplianceScope.__table__,
]


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def external_patches():
    """Patch every non-database dependency used by the collection chain."""
    return [
        # Redis 不可用时应回落到数据库读取白名单，而不是报错中断
        patch(
            "app.services.compliance_service._get_redis",
            AsyncMock(side_effect=RuntimeError("redis unavailable in integration test")),
        ),
        patch("app.services.compliance_service.ComplianceService.log_action", AsyncMock()),
        patch("app.services.event_emitter.emit_terminal_online", AsyncMock()),
        patch("app.services.event_emitter.emit_terminal_offline", AsyncMock()),
    ]


async def _seed_source_and_rules(db):
    db.add(DataSource(name="lab-switch", type="arp_api", tag="lab", config={}, enabled=True))
    db.add_all([
        # 白名单：厂商 MAC 前缀 + 单 IP
        Whitelist(
            mac_address="00:11:22", mac_address_normalized="001122",
            pattern_type="mac_prefix", comments="vendor OU whitelist", added_by="tester",
        ),
        Whitelist(
            ip_pattern="10.60.0.1", pattern_type="single_ip",
            comments="lab workstation whitelist", added_by="tester",
        ),
        # 排除规则：CIDR / MAC 前缀 / IP 段
        TerminalExclusion(
            ip_pattern="10.70.0.0/24", ip_pattern_type="cidr",
            comments="test-net CIDR", created_by="tester",
        ),
        TerminalExclusion(
            mac_address="0A:0B:0C", mac_pattern_type="mac_prefix",
            comments="vendor OU excluded", created_by="tester",
        ),
        TerminalExclusion(
            ip_pattern="10.90.0.10-20", ip_pattern_type="ip_range",
            comments="printer range", created_by="tester",
        ),
    ])
    await db.commit()


@pytest.mark.asyncio
async def test_collection_flow_with_exclusion_and_whitelist(session):
    """排除规则生效且不抬高白名单统计；白名单终端的合规结果仍为 bypass。"""
    await _seed_source_and_rules(session)

    entries = [
        # 同时命中「排除 CIDR」与「白名单 MAC 前缀」：若不排除，它将以 bypass 入库并抬高白名单数
        {"ip_address": "10.70.0.5", "mac_address": "00:11:22:33:44:01"},
        # 仅命中排除规则（MAC 前缀）
        {"ip_address": "10.80.0.1", "mac_address": "0a:0b:0c:00:00:01"},
        # 仅命中排除规则（IP 段）
        {"ip_address": "10.90.0.15", "mac_address": "aa:bb:cc:00:00:01"},
        # 不在排除范围，且命中白名单单 IP → 应为 bypass
        {"ip_address": "10.60.0.1", "mac_address": "aa:bb:cc:00:00:02"},
        # 不在排除范围，也不在白名单 → 正常入库并参与合规判定
        {"ip_address": "10.60.0.2", "mac_address": "aa:bb:cc:00:00:03"},
    ]

    patches = external_patches()
    stack = [p.start() for p in patches]
    try:
        result = await ArpCollectorService(session).process_arp_entries(entries, "lab")
    finally:
        for p in patches:
            p.stop()

    # --- 采集结果 ---------------------------------------------------------
    assert result.success is True
    assert result.entries_added == 2
    assert result.entries_excluded == 3
    assert "excluded 3" in result.message

    # --- 终端库内容：排除项完全不存在 ------------------------------------
    rows = (await session.execute(select(Terminal))).scalars().all()
    by_ip = {row.ip_address: row for row in rows}
    assert set(by_ip) == {"10.60.0.1", "10.60.0.2"}

    # --- 合规计算结果 -----------------------------------------------------
    assert by_ip["10.60.0.1"].compliance_status == "bypass"
    assert by_ip["10.60.0.1"].wl_match_type == "ip"
    assert by_ip["10.60.0.2"].compliance_status != "bypass"

    # --- 统计口径：白名单只统计真实入库的 bypass 终端 ----------------------
    stats = await TerminalService(session).get_stats()
    assert stats["total"] == 2
    assert stats["whitelisted"] == 1
    assert stats["blocked"] == 0


@pytest.mark.asyncio
async def test_recalculation_skips_excluded_leftover_and_updates_whitelist(session):
    """重算链路：白名单终端转为 bypass，命中排除规则的遗留终端被跳过且状态不变。"""
    db = session
    db.add(DataSource(name="lab-switch", type="arp_api", tag="lab", config={}, enabled=True))
    db.add(Whitelist(
        ip_pattern="10.60.0.1", pattern_type="single_ip",
        comments="lab workstation whitelist", added_by="tester",
    ))
    db.add(TerminalExclusion(
        ip_pattern="10.70.0.0/24", ip_pattern_type="cidr",
        comments="test-net CIDR", created_by="tester",
    ))
    db.add_all([
        # 白名单终端：compliant -> bypass
        Terminal(
            ip_address="10.60.0.1", mac_address="AA-AA-AA-00-00-02",
            mac_address_normalized="AAAAAA000002", source_tag="lab", source="arp",
            compliance_status="compliant", status="unblocked",
            updated_at=datetime.now(UTC),
        ),
        # 命中排除规则的遗留终端（已封锁，规则创建时故意保留）；
        # 这里刻意不打 excluded_by_rule 标记，模拟加标记列之前的历史行，
        # 用于验证重算守卫独立于统计标记生效。
        Terminal(
            ip_address="10.70.0.9", mac_address="00-11-22-33-44-09",
            mac_address_normalized="001122334409", source_tag="lab", source="arp",
            compliance_status="non_compliant", status="blocked",
            updated_at=datetime.now(UTC),
        ),
    ])
    db.add(Blacklist(
        ip_address="10.70.0.9", mac_address="00-11-22-33-44-09",
        mac_address_normalized="001122334409", blocked_by="tester",
        reason="pre-existing block", expires_at=datetime.now(UTC) + timedelta(days=1),
    ))
    await db.commit()

    patches = external_patches() + [
        patch(
            "app.services.compliance_service._acquire_compliance_lock",
            AsyncMock(return_value="test-lock-token"),
        ),
        patch("app.services.compliance_service._release_compliance_lock", AsyncMock()),
        # IPGuard 正常数据（非空，否则重算整体跳过）
        patch.object(
            ComplianceService, "_load_all_ipguard_cache",
            AsyncMock(return_value={"ig-lab": [
                {"ip_address": "10.60.0.1", "mac_address": "AA-AA-AA-00-00-02"},
            ]}),
        ),
        patch.object(ComplianceService, "_is_ipguard_cache_stale", AsyncMock(return_value=False)),
        patch.object(ComplianceService, "_is_device_grouping_enabled", AsyncMock(return_value=False)),
    ]
    for p in patches:
        p.start()
    try:
        outcome = await ComplianceService(db).recalculate_all_compliance()
    finally:
        for p in patches:
            p.stop()

    assert outcome["total"] == 2
    assert outcome["bypass"] == 1
    assert outcome["excluded_skip_count"] == 1
    assert outcome["unchanged"] == 0

    rows = (await db.execute(select(Terminal))).scalars().all()
    by_ip = {row.ip_address: row for row in rows}
    # 白名单终端被重算为 bypass
    assert by_ip["10.60.0.1"].compliance_status == "bypass"
    # 排除遗留终端完全未被触碰
    assert by_ip["10.70.0.9"].compliance_status == "non_compliant"
    assert by_ip["10.70.0.9"].status == "blocked"

    stats = await TerminalService(db).get_stats()
    assert stats["total"] == 2
    assert stats["whitelisted"] == 1
    assert stats["non_compliant"] == 1
    assert stats["blocked"] == 1


@pytest.mark.asyncio
async def test_retained_excluded_terminal_is_flagged_and_filtered_from_stats(session):
    """采集时命中排除规则但已封锁的终端被保留并打标，且不计入终端统计。"""
    db = session
    db.add(DataSource(name="lab-switch", type="arp_api", tag="lab", config={}, enabled=True))
    db.add(TerminalExclusion(
        ip_pattern="10.70.0.0/24", ip_pattern_type="cidr",
        comments="test-net CIDR", created_by="tester",
    ))
    db.add(Terminal(
        ip_address="10.70.0.9", mac_address="00-11-22-33-44-09",
        mac_address_normalized="001122334409", source_tag="lab", source="arp",
        compliance_status="non_compliant", status="blocked",
        updated_at=datetime.now(UTC),
    ))
    db.add(Blacklist(
        ip_address="10.70.0.9", mac_address="00-11-22-33-44-09",
        mac_address_normalized="001122334409", blocked_by="tester",
        reason="pre-existing block", expires_at=datetime.now(UTC) + timedelta(days=1),
    ))
    await db.commit()

    # 打标前（历史行）该记录仍计入统计
    assert (await TerminalService(db).get_stats())["total"] == 1

    entries = [
        # 命中排除规则且已封锁：保留，但必须打 excluded_by_rule 标记
        {"ip_address": "10.70.0.9", "mac_address": "00:11:22:33:44:09"},
        # 正常终端：入库并计入统计
        {"ip_address": "10.60.0.2", "mac_address": "aa:bb:cc:00:00:03"},
    ]
    patches = external_patches()
    for p in patches:
        p.start()
    try:
        result = await ArpCollectorService(db).process_arp_entries(entries, "lab")
    finally:
        for p in patches:
            p.stop()

    assert result.entries_added == 1
    assert result.entries_excluded == 1

    rows = (await db.execute(select(Terminal))).scalars().all()
    by_ip = {row.ip_address: row for row in rows}
    assert set(by_ip) == {"10.70.0.9", "10.60.0.2"}
    assert by_ip["10.70.0.9"].status == "blocked"
    assert by_ip["10.70.0.9"].excluded_by_rule is True
    assert by_ip["10.60.0.2"].excluded_by_rule is False

    stats = await TerminalService(db).get_stats()
    # 合规轴只统计未被排除的终端
    assert stats["total"] == 1
    assert stats["whitelisted"] == 0
    assert stats["non_compliant"] == 0
    # 封锁轴仍是防火墙真实状态，保留的已封锁 IP 依然计入
    assert stats["blocked"] == 1


@pytest.mark.asyncio
async def test_disabling_rule_clears_flag_and_restores_stats(session):
    """规则停用后保留行标记被回收、统计恢复；重新启用后再次打标。"""
    db = session
    db.add(DataSource(name="lab-switch", type="arp_api", tag="lab", config={}, enabled=True))
    rule = TerminalExclusion(
        ip_pattern="10.70.0.0/24", ip_pattern_type="cidr",
        comments="test-net CIDR", created_by="tester",
    )
    db.add(rule)
    db.add_all([
        # 被排除但已封锁而保留的终端（已打标）
        Terminal(
            ip_address="10.70.0.9", mac_address="00-11-22-33-44-09",
            mac_address_normalized="001122334409", source_tag="lab", source="arp",
            compliance_status="non_compliant", status="blocked",
            excluded_by_rule=True, updated_at=datetime.now(UTC),
        ),
        # 正常终端
        Terminal(
            ip_address="10.60.0.2", mac_address="AA-BB-CC-00-00-03",
            mac_address_normalized="AABBCC000003", source_tag="lab", source="arp",
            compliance_status="unknown", status="unblocked",
            updated_at=datetime.now(UTC),
        ),
    ])
    await db.commit()
    await db.refresh(rule)

    assert (await TerminalService(db).get_stats())["total"] == 1

    service = TerminalExclusionService(db)
    toggled, impact = await service.toggle_rule(rule.id)
    assert toggled.is_active is False
    assert impact is None

    rows = (await db.execute(select(Terminal))).scalars().all()
    by_ip = {row.ip_address: row for row in rows}
    assert by_ip["10.70.0.9"].excluded_by_rule is False

    stats = await TerminalService(db).get_stats()
    assert stats["total"] == 2
    assert stats["non_compliant"] == 1

    # 重新启用：保留行再次被命中并打标
    toggled, impact = await service.toggle_rule(rule.id)
    assert toggled.is_active is True
    assert impact is not None
    assert impact.matched == 1
    assert impact.retained == 1

    rows = (await db.execute(select(Terminal))).scalars().all()
    by_ip = {row.ip_address: row for row in rows}
    assert by_ip["10.70.0.9"].excluded_by_rule is True

    stats = await TerminalService(db).get_stats()
    assert stats["total"] == 1
