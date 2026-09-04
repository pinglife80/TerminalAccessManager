> 文档版本：v1.1  更新日期：2026-09-04

# 系统诊断：ARP 漏采 / 通知缺失 / 终端双清单根因

## 摘要

本次为**诊断型任务，不修改任何代码**。针对用户提出的三个问题输出根因分析、排查手册与改进清单：

1. **ARP 漏采**（如交换机 ARP 表中有 `10.8.14.32` 但终端管理页从未出现）——根因**已确认**：`10.8.14.32` 与 `10.8.14.100` 共用**同一个 MAC**，而终端以 MAC 为唯一键（一 MAC 一条记录），导致该 IP 被折叠、永不作为独立终端展示（详见问题 1）。
2. **通知缺失**（只有"解封"和"IPGuard 数据源同步成功"能发出通知）——直接原因是**通知渠道的事件订阅列表 `events` 未勾选其它事件**，加上部分事件**根本没有触发点**（详见问题 2）。
3. **`10.8.19.194` 同时出现在"已封锁"和"待重试解封"两个清单**——是**统计口径的子集关系**加上调度错峰窗口，非 bug；其 reason 来自**对账服务补建**（详见问题 3）。

---

## 问题 1：ARP 数据获取漏采根因（已确认）

### 1.1 数据流链路（确认无隐藏过滤）

```
scheduled_arp_collection (main.py L202-220)
  └─ ArpCollectorService.run_scheduled_collection (arp_collector_service.py L479-518)
       └─ collect_from_ssh / collect_from_api (L31 / L192)
            └─ _parse_arp_output / _parse_api_response (L522 / L590)
                 └─ process_arp_entries (L266-474)
                      └─ Terminal upsert（按归一化 MAC 唯一）
```

已确认的代码事实：

- 终端查询 [GET /terminals/search](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/terminals.py) → `_terminal_base_conditions`（[terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L433-L472)）**默认不按 source_tag/enabled 过滤**；前端 [Terminals.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx#L84-L89) 默认 `filterSource='all'`、`filterStatus='all'`、`filterCompliance='all'`、`filterDedupDim=''`。故**只要落库就会出现在列表**（受 `pageSize=10` 分页影响，可能在后续页）。
- ARP 采集/解析/入库链路中**不存在**任何 IP 网段/排除/忽略过滤，也没有对终端的删除/清理逻辑。

### 1.2 根因：终端以 MAC 作为唯一主键（一 MAC 一条记录）

`process_arp_entries`（[arp_collector_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L266-L474)）以**归一化 MAC** 为唯一标识 upsert：

- L293：`mac_norm_key = 归一化后去掉分隔符的 12 位十六进制`
- L296-298：**同一批次内按 MAC 去重**，命中 `seen_macs` 直接 `continue`
- L302-306：用 `Terminal.mac_address_normalized == mac_norm_key` 判断是否已存在
- L308-325：已存在 → 只更新该行 `ip_address`（不新增行）
- L326-337：不存在 → 新增一行（`source_tag=source.tag`）

且 `Terminal` 表有唯一约束 `uq_terminal_mac`（[terminal.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/terminal.py#L50)），DB 层也保证一 MAC 一条记录。

**结论**：凡与某 MAC 关联的"第 2 个及之后"的 IP，都不会生成独立终端行——要么在批次内被 `seen_macs` 去重丢弃，要么被合并进既有行的 IP 字段。

### 1.3 已确认事实与触发场景

> 已确认事实：`10.8.14.32` 与 `10.8.14.100` 在交换机 ARP 表中映射到**同一个 MAC**。因此本问题命中上述"一 MAC 一条记录"机制，而非数据源/解析/MAC 缺失问题。

两个子场景：

1. **同 MAC 多 IP 共存于同一交换机 ARP 表（本例即为该情形）**
   - 采集同一批次时按 `seen_macs` 去重，该 MAC 只有"最先出现"的那条 IP 入库；`10.8.14.32` 与 `10.8.14.100` 中排序靠后的那个 IP 每次采集都被丢弃。
2. **该 MAC 已被其它 IP 占用**
   - 若该 MAC 已在 `terminals` 且 `ip_address` 为其它值，采集到 `10.8.14.32` 时走 L308-325 的"更新 IP"分支，仅覆盖 IP 而不新增行。

无论走哪个子场景，`terminals` 里该 MAC 只对应**一行**，`10.8.14.32` 与 `10.8.14.100` 只能显示其中一个，另一个 IP 永不作为独立终端出现。

### 1.4 佐证

[Terminals.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx#L218-L220) 注释明确提到"桥接虚拟机场景下同 MAC 不同 IP 的终端"，说明本部署确实存在"一个 MAC 对应多个 IP"的真实情况；而后端 `process_arp_entries` 仍强制"一 MAC 一条记录"，与前端注释表达的意图不一致。

### 1.5 本质结论

问题 1 的本质不是"采集漏了"，而是**终端唯一键仅用 MAC**（`mac_address_normalized` 唯一约束 + 批内 `seen_macs` 去重），导致"一个 MAC 对应多个 IP"时，多余 IP 无法作为独立终端展示。是否需要修复、以及如何把唯一键扩展为"MAC+IP（或 MAC+source_tag+IP）"以支持桥接多 IP 场景，属于后续评估，不在本次诊断范围。

---

## 问题 2：通知消息缺失改进清单

### 2.1 架构

```
emit_event() → NotificationService.emit() → 入 Redis notify:queue:main
  → NotificationWorkers 出队 → 按渠道订阅的 events 匹配 → 规则/模板 → 渠道 send() → 记日志/重试
```

关键闸门：`_get_subscribed_channels`（[notification_workers.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_workers.py#L66-L72)）只返回 `events` 列表包含该 `event_type` 的渠道；投递时（L257-266）若 `subscribed_channels` 为空，直接 drop，连 `notification_logs` 都不产生。

### 2.2 为什么只有两类能发通知

**不是代码特权，而是订阅配置问题**：worker 只在 `channel.events` 里精确匹配 `event_type` 才投递。当前 DB 中的通知渠道只勾选了 `terminal.unblocked` 与 `system.datasource_sync_success`，其它事件即使已 emit 也被静默丢弃。

同时代码里**没有任何默认渠道/默认订阅（无 seed 数据）**；前端新建渠道默认 `events: []`（`Notifications.tsx` L139），需管理员手动勾选。

### 2.3 缺失全景清单

**A. 已定义但从未被调用（永远发不出）的 emitter**

| 事件 | emitter 定义位置 |
|---|---|
| `system.error` | `event_emitter.py` L482 |
| `system.warning` | `event_emitter.py` L500 |
| `system.alert` | `event_emitter.py` L516 |
| `security.email_verified` | `event_emitter.py` L418 |
| `alert.auto_block_triggered` | `event_emitter.py` L574 |
| `alert.auto_unblock_triggered` | `event_emitter.py` L592 |
| `alert.policy_violation` | `event_emitter.py` L624 |

**B. 业务动作本身未接入通知（无任何 emit）**

| 业务动作 | 现状 |
|---|---|
| 封锁失败（block failed） | `auto_block_non_compliant` L664-665、`_apply_compliance_result` L2113-2133 只设 `block_state='block_failed'`，无 emit |
| 重试封锁（retry block） | `_apply_compliance_result` L2014-2133 成功后无 emit（对比主路径 L655-662 有 `emit_terminal_blocked`） |
| 白名单/黑名单变更 | `terminal_service.py` `add_to_whitelist` L639-812、`delete_from_whitelist` L814、`blacklist.py`/`whitelist.py` 只写审计日志，无 emit |
| 手动封锁/解封 | `terminal_service.py` 无手动 block/unblock 的 emit；`firewall_reconciliation_service.py` `_reblock_on_firewall` L396-459 也无 emit |

**C. 缺失的事件类型定义**

`EVENT_METADATA`（`notification_channels/event_types.py`）中**不存在**「whitelist changed / blacklist changed」等事件类型，无法配置订阅。

**D. 已正确接入 emit 的事件（仅供参考，均受订阅门控）**

`terminal.blocked` / `terminal.unblocked` / `terminal.compliant` / `terminal.non_compliant` / `terminal.online` / `terminal.offline` / 安全类（登录、密码、用户） / `admin.*` / `system.datasource_sync_*` / `system.firewall_connection_*` / `system.backup_*` / `alert.compliance_rate_*` / `alert.block_threshold`。

### 2.4 改进清单（建议优先级）

1. **补齐 A 类 7 个事件的调用点**（或删除无用 emitter）——尤其 `system.error/warning/alert` 当前完全无触发。
2. **B 类关键动作接入 emit**：封锁失败、重试封锁、白名单/黑名单变更、手动解封。
3. **C 类新增事件类型**：`whitelist.changed`、`blacklist.changed` 等，纳入 `EVENT_METADATA` 与前端勾选项。
4. **提供默认渠道/默认订阅**（seed 或首次初始化），避免"有事件但没订阅"导致漏发。
5. 统一 `send()` 返回类型与重试逻辑（沿用 `事件通知系统审计与修复计划.md` 中的 D1-D7 结论）。

---

## 问题 3：10.8.19.194 双清单 + 对账 reason 根因解释

### 3.1 reason 来源

`reason = "Reconciliation: IP blocked on firewall 'af' but missing in DB"` 由对账服务补建生成：

- 位置：[firewall_reconciliation_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L289-L394) `_create_db_entries_for_firewall`，其中 reason 在 **L382**。
- 含义：防火墙 `af`（DataSource.tag）上实际封锁了 `10.8.19.194`，但 DB 该防火墙维度下没有 active 黑名单，对账补建了这条 active 记录并写死该文案。
- 对账入口：`main.py` L175-199（每 300s）、手动脚本 `trigger_reconcile.py`、API `system.py` L114-117。

### 3.2 两个统计口径（子集关系，非互斥）

| 口径 | 过滤条件 | 定义位置 |
|---|---|---|
| `success_blocked` | `auto_unblocked=False AND unblocked_at IS NULL AND (expires_at>=now OR IS NULL)` | `terminal_service.py` L1620-1636 |
| `pending_retry_unblock` | 上述 `active_filter` **再叠加** `Terminal.compliance_status IN ('compliant','bypass')`，按终端身份去重 | L1641-1651 |

由于 `pending_retry_unblock` 的条件 = `success_blocked` 的条件**再叠加**合规条件，所以**任意满足「待重试解封」的记录必然也满足「已封锁」**——二者是包含关系，不是互斥，一条 active 记录可同时出现在两个清单。

### 3.3 为什么"短时间"同时出现

1. 对账补建出 active 黑名单行 → 立即满足 `success_blocked`。
2. 补建时**只写 `Terminal.status='blocked'`，绝不改 `compliance_status`**（L331-336）。若该终端已被/随后被合规计算判定为 `compliant`/`bypass`，则这条 active 行又满足 `pending_retry_unblock`。
3. 从"合规 terminal + active 黑名单"到"真正解封写回 `auto_unblocked=True` / `unblocked_at=now`"之间存在窗口：
   - 对账任务每 300s（`main.py` L179）、合规检查每 300s（L275）、自动解封每 600s（L574）。
   - 自动解封有 **cooldown（约 10 分钟）** 与"全防火墙成功才解封"门槛（`compliance_service.py` L801-827、L890-954）。
   - 若解封被 cooldown 跳过或防火墙解封失败，窗口更长。
4. `reason` 在 active 期间不会被改写，只有解封成功才被覆盖（自动解封 `compliance_service.py` L905；手动重试 `terminal_service.py` L1781）。因此在双清单中时，reason 仍保持对账文案。

### 3.4 结论

`10.8.19.194` 是**对账检测到防火墙 `af` 实际封锁但 DB 缺失后补建**的一条 active 黑名单；因其终端已（或紧接着）被判定为 `compliant`/`bypass`，这条 active 记录**既计入「已封锁」又计入「待重试解封」（后者为前者子集）**，直到自动解封成功写回解封字段才从两清单同时消失。

---

## 结论与建议

- 问题 1 已确认根因：`10.8.14.32` 与 `10.8.14.100` 共用同一 MAC，被"一 MAC 一条记录"机制折叠，二者只能显示其一。是否需要修复（把终端唯一键扩展为"MAC+IP"或"MAC+source_tag+IP"）属于后续评估，单独立项。
- 问题 2 已给出完整改进清单（2.4 节），可按需排期实施。
- 问题 3 为预期设计（子集口径 + 调度错峰），如需缩短中间态窗口，再单独评估。