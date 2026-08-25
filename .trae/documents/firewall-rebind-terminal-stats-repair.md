# 防火墙绑定解绑/重新绑定导致终端统计错乱 — 修复计划

> 文档版本：v1.0  更新日期：2026-08-24

## 1. 问题背景

2026-08-24 14:14，用户在对「数据源管理」中的防火墙绑定（ARP 源 `yp` ↔ 防火墙 `af`）执行「删除并重新绑定」后，终端管理的统计与筛选结果完全错乱：

- 存在「合规 + 封锁」与「非合规 + 封锁」两种状态的终端；
- 条件筛选结果与状态统计标签上的数字对不上；
- 防火墙上实际没有任何被封锁条目；
- 黑名单管理也没有任何统计数据。

## 2. 当前状态实测（已通过数据库确认）

| 项目 | 值 |
|---|---|
| 数据源 | `arp_ssh/yp`（启用）、`sangfor/af`（启用） |
| 绑定关系 | `yp → af`（id=2，`created_at=2026-08-24 14:14:07`） |
| 终端（全部 `source=arp`、`source_tag=yp`） | 共 1159 条 |

终端状态分布（`compliance_status` × `status`）：

| compliance_status | status | 数量 | firewall_tag |
|---|---|---|---|
| bypass | unblocked | 758 | — |
| compliant | unblocked | 303 | — |
| **compliant** | **blocked** | **88** | af |
| **non_compliant** | **blocked** | **10** | af |

活动黑名单（`auto_unblocked=false AND unblocked_at IS NULL`）：**0 条**。

### 由此产生的统计矛盾

1. `TerminalService.get_stats()` 的 `blocked` = `count(DISTINCT ip)` 活动黑名单 = **0**；
   但终端管理中 `status=blocked` 的终端共有 **98** 条 → 「封堵」卡片（0）与「已封锁状态」筛选（98）严重对不上。
2. `status=blocked` 的 98 条终端（88 合规 + 10 非合规）在 `firewall_tag='af'`，但黑名单为 0、防火墙实际也无封锁条目 → 是**孤立的「伪封锁」状态**。
3. 黑名单管理页统计（`get_blacklist_stats`）全部为 0，与「存在被封锁终端」的页面表现矛盾。

## 3. 根因分析

核心矛盾：**`Terminal.status`（防火墙实际封锁态）与黑名单/防火墙实际状态发生了不可自愈的漂移**。

### 3.1 触发链路

解绑 `safe_delete_binding`（[data_source_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/data_source_service.py#L487-L592)）做三件事：
1. 在防火墙上批量解封（`svc.unblock_ip`）；
2. 按黑名单条目逐个回写终端状态（只有能匹配到终端的才被置为 `unblocked`/`unknown`）；
3. 删除该绑定的黑名单条目、删除绑定，然后 `recalculate_all_compliance()`。

随后重新绑定 `create_binding` 只插入 `DataSourceBinding` 记录，**不做任何状态重算**。

### 3.2 三个具体缺陷

1. **终端匹配不可靠**（`safe_delete_binding` L536-L538）：
   用 `Terminal.mac_address == bl_entry.mac_address` 原始字符串等值匹配，而未使用系统统一口径 `mac_address_normalized`；MAC 大小写/分隔符不一致即匹配失败。黑名单 `mac_address` 为 NULL 的对账补建条目更是永远匹配不到。→ 导致大量终端 `status='blocked'` 未被重置，其黑名单条目却已被删除。

2. **重新绑定不触发重算**（`create_binding` L805-L837）：插入绑定后即返回，未像解绑那样触发 `recalculate_all_compliance()`/合规重算，导致残留的伪封锁状态得不到纠正。

3. **缺少「孤立 blocked 状态」的自愈机制**：
   - 防火墙对账 `FirewallReconciliationService.reconcile()` 只处理黑名单与防火墙 IP 的差异，不触碰 `Terminal.status`；
   - `auto_unblock_compliant()` 以黑名单条目为驱动力（黑名单已空 → 直接返回，不做任何事）。
   - 因此 `status='blocked'` 但没有黑名单背书、且防火墙无实际封锁的终端，成为无人修复的孤儿。

### 3.3 附加潜在缺陷（顺带修复）

`_apply_compliance_result`（[compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1813-L1817)）中，当 `non_compliant` 终端已无绑定防火墙（`fw_tags=[]`）时，`missing_fw_tags=[]` 会误入 `if not missing_fw_tags` 分支，把终端标记为 `status='blocked'` 且 `firewall_tag=""`、不写黑名单 → 制造新的伪封锁。

## 4. 修复方案

分两部分：**A. 代码修复（防止复发）** + **B. 数据修复（一次性纠正在线数据）**。

### 4.1 代码修复

#### (1) `backend/app/services/data_source_service.py` — `safe_delete_binding`

将终端匹配改为统一口径 `mac_address_normalized`，并处理 NULL-MAC 回退：

```python
# 替换 L536-L539 的原始等值匹配
mac_norm = (
    bl_entry.mac_address.replace('-', '').replace(':', '').replace('.', '').upper()
    if bl_entry.mac_address else None
)
terminal_stmt = select(Terminal)
if mac_norm:
    terminal_stmt = terminal_stmt.where(Terminal.mac_address_normalized == mac_norm)
else:
    terminal_stmt = terminal_stmt.where(Terminal.ip_address == bl_entry.ip_address)
```

并在删除黑名单后可选增加「终态清扫」：对 `source_tag == arp_tag` 且 `status == 'blocked'`、但已无活动黑名单背书的终端，复用 4.1(4) 的自愈逻辑重置为 `unblocked`（若匹配修复后仍有极少数遗漏，由 4.1(4) 周期性自愈兜底，此处可选）。

#### (2) `backend/app/services/data_source_service.py` — `create_binding`

绑定创建并提交后，触发合规重算（与 `safe_delete_binding` 已有做法一致）：

```python
# 在 commit + refresh 之后
from app.services.compliance_service import ComplianceService
try:
    cs = ComplianceService(self.db)
    await cs.recalculate_all_compliance()
except Exception as e:
    logger.warning(f"Failed to recalculate compliance after binding creation: {e}")
```

> 目标：重新绑定后立即重建终端合规/封锁态的对应关系，不留残留。

#### (3) `backend/app/services/compliance_service.py` — `_apply_compliance_result`

修复空 `fw_tags` 下的伪封锁（L1813-L1817）：当 `non_compliant` 但无绑定防火墙时，不得标记 `status='blocked'`，保持 `unblocked`（交由后续 retry-block 在防火墙实际可封锁时处理）：

```python
if new_compliance == "non_compliant":
    fw_tags = await self._get_bound_firewall_tags(terminal.source_tag)
    if not fw_tags:
        # 无绑定防火墙：不可封锁，不得伪造 blocked 状态
        terminal.status = "unblocked"
        terminal.firewall_tag = None
    else:
        missing_fw_tags = [fw for fw in fw_tags if fw not in active_fw_tags]
        if not missing_fw_tags:
            ...
        else:
            ...
```

#### (4) 新增「孤立 blocked 状态自愈」方法

在 `backend/app/services/firewall_reconciliation_service.py` 中新增方法 `_repair_stale_terminal_status()`，并在 `reconcile()` 两处 `return results` 之前都调用（含「无启用防火墙」的提前返回分支），确保自愈始终执行：

```python
async def _repair_stale_terminal_status(self) -> int:
    """将 status='blocked' 但无活动黑名单背书的终端重置为 unblocked。

    只修正 Terminal.status（防火墙实际封锁态）与活动黑名单脱节的库内不一致；
    不修改 compliance_status —— 其由合规计算逻辑（三层防抖）唯一决定，
    避免破坏既有防振荡机制（项目约束：对账只能改 status，不得改 compliance_status）。

    匹配口径：活动黑名单以「MAC 归一化匹配」为主，对 MAC 为 NULL 的对账补建条目
    回退用 IP 匹配，避免误重置真实被封锁但黑名单缺 MAC 的终端。
    返回修复条数。"""
    from sqlalchemy import and_, exists

    _now = datetime.now(UTC)
    active_bl = (
        select(Blacklist.id).where(
            (Blacklist.auto_unblocked == False) &
            (Blacklist.unblocked_at.is_(None)) &
            or_(
                Blacklist.expires_at >= _now,
                Blacklist.expires_at.is_(None),
            ) &
            or_(
                and_(
                    Blacklist.mac_address_normalized.is_not(None),
                    Blacklist.mac_address_normalized == Terminal.mac_address_normalized,
                ),
                and_(
                    Blacklist.mac_address_normalized.is_(None),
                    Blacklist.ip_address == Terminal.ip_address,
                ),
            )
        )
    )
    stmt = select(Terminal).where(
        (Terminal.status == TerminalStatus.BLOCKED.value) &
        (~exists(active_bl))
    )
    result = await self.db.execute(stmt)
    terminals = result.scalars().all()
    fixed = 0
    for t in terminals:
        t.status = TerminalStatus.UNBLOCKED.value
        t.firewall_tag = None
        fixed += 1
    if fixed:
        await self.db.commit()
        logger.info(f"Self-healed {fixed} orphaned 'blocked' terminals (no active blacklist backing)")
    return fixed
```

> 连线：`reconcile()` 已导入 `select, or_`（[firewall_reconciliation_service.py L18](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L18)），需补充 `and_, exists`；`TerminalStatus` 已导入（L24）。该方法随对账调度与手动 `POST /system/firewall-reconciliation` 一并执行，实现周期性自愈。重置后：
> - 原 `compliant + blocked`（88 条）→ `compliant + unblocked`（正确，合规终端本不应封锁）。
> - 原 `non_compliant + blocked`（10 条）→ `non_compliant + unblocked`，由调度器 retry-block / `auto_block_non_compliant` 在已重新绑定的防火墙 `af` 上重新封锁并新建黑名单条目。

### 4.2 数据修复（一次性）

代码部署后，执行以下顺序即可自动纠正在线数据（无需手写裸 SQL）：

1. `./manage.sh update` 重建并重启后端。
2. 触发一次手动对账：`POST /api/v1/system/firewall-reconciliation`。
   - 因防火墙当前实际无封锁条目且黑名单为空，`_repair_stale_terminal_status()` 会把上述 98 条孤立 `blocked` 终端的 `status` 重置为 `unblocked`、`firewall_tag=NULL`（`compliance_status` 保持原值不变）。
3. 触发一次合规重算（若 `create_binding` 补触发后尚未自动执行），或等待下一个 `scheduled_compliance_check` 周期（≤300s）：
   - 原 88 条 `compliant` → 已由自愈重置为 `compliant + unblocked`（正确）。
   - 原 10 条 `non_compliant` → 已由自愈重置为 `non_compliant + unblocked`（待重试封锁），由调度器 retry-block / `auto_block_non_compliant` 在已重新绑定的防火墙 `af` 上重新封锁，并**新建黑名单条目**。

## 5. 决策与假设

- **「封锁」唯一真相口径**：以「活动黑名单（`auto_unblocked=false AND unblocked_at IS NULL`）」为封锁事实源，`Terminal.status` 只作为其镜像。这与既有 `get_stats` 中 `blocked = count(DISTINCT ip of active blacklist)` 的口径一致。
- **自愈不违反防火墙权威原则**：本修复只纠正「`Terminal.status` 与黑名单/防火墙实际状态脱节」的库内不一致（把无任何封锁背书的 `blocked` 还原为 `unblocked`），不做任何基于对账差异的主动解封；防火墙上的真实封锁仍由对账 `_reblock_on_firewall` 保障。
- **自愈只改 `status`，不动 `compliance_status`**：遵循项目约束「对账服务只能更新 status 字段，compliance_status 由合规计算三层防抖逻辑唯一决定」。因此 88 条 `compliant+blocked` 重置后为 `compliant+unblocked`（终态即正确），10 条 `non_compliant+blocked` 重置后为 `non_compliant+unblocked`（合法中间态 `pending_retry_block`，由 retry-block 在有绑定防火墙时重新封锁）——两者都不需要重置合规状态即可回到一致态。
- **不新增数据库迁移**：仅使用现有字段，无 schema 变更。

## 6. 验证步骤

修复后需逐项核验（对齐用户关注的「筛选结果 vs 统计标签」口径）：

1. **数据库一致性**：
   - `SELECT count(*) FROM terminals WHERE status='blocked' AND NOT EXISTS (活动黑名单同 MAC)` 应为 **0**。
   - 活动黑名单 `count(*)` 应等于「非合规+已封锁」终端数（原 10 条在重新封锁后产生 10 条黑名单）。
2. **仪表盘**：`blocked` = 活动黑名单去重 IP 数；`non_compliant` = `non_compliant AND blocked` 数；两者与终端页/黑名单页一致。
3. **终端页筛选**：`status=blocked` 的筛选结果数 = 仪表盘 `blocked`（去重 IP）口径对应的终端数；`compliance_status=non_compliant` 结果数 = 仪表盘 `non_compliant`。
4. **黑名单页**：统计卡片与列表条目一致，`防火墙异常` 卡片为 0（对账成功）。
5. **防火墙实际态**：`af` 上重新封锁的 IP 清单与黑名单 `firewall_tag='af'` 条目一致。
6. **回归**：重新触发一次「解绑→重新绑定」，观察解绑即时清理、重新绑定即时重算，不再产生残留伪封锁。