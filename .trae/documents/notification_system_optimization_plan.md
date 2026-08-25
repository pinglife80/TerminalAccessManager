# 通知管理系统全面优化执行计划

## 一、审查结论摘要

对通知管理系统进行了全面深入的代码审查，涵盖 32 种事件类型、5 种通知渠道、规则引擎、模板渲染、日志记录和监控统计等所有功能点。

**核心发现：当前通知系统存在一个关键设计缺陷——`NotificationAggregator` 作为优先路径吞掉了所有事件，导致整个通知管道（worker、规则引擎、模板渲染、日志记录、多渠道分发）完全不工作。**

### 缺陷统计

| 优先级 | 类别 | 数量 |
|--------|------|------|
| P0（紧急） | 导致通知完全不可用 | 2 项 |
| P1（高） | 影响通知可靠性和时效性 | 2 项 |
| P2（中） | 功能完整性缺失 | 4 项 |
| P3（低） | 改进建议 | 3 项 |

---

## 二、分阶段实施计划

### 阶段 1：P0 紧急修复（通知完全不可用）

#### 任务 1.1：重构 emit_event() 移除聚合器优先路径

**根因：** `event_emitter.py` 中 `emit_event()` 先将事件投递到 `NotificationAggregator`，聚合器 `add_event()` 永远成功（不抛异常），导致 fallback 路径永远不触发，Worker 管道完全被绕过。

**修改文件：**
- `backend/app/services/event_emitter.py`

**修改方案：**
```
当前流程：emit_event → Aggregator.add_event() [永远成功] → return []
                                                    ↓ (永不触发 fallback)
                                              NotificationService.emit() → Worker 管道

目标流程：emit_event → NotificationService.emit() → Redis Queue → Worker 管道
```

具体修改 `emit_event()` 函数（L32-L94）：
1. 移除聚合器优先路径（L55-L71）
2. 将 `NotificationService.emit()` 作为主路径
3. 保留聚合器为可选的中间件层（后续 P2 阶段集成到 Worker 管道内）
4. 保留 fire-and-forget 语义和错误日志

**验证方法：**
- 重建后端后，在通知渠道页面测试发送测试通知
- 检查通知日志表是否有新记录
- 检查 Redis 队列是否有事件入队
- 检查后端日志确认 Worker 是否正常消费

#### 任务 1.2：修复事件类型字符串不匹配

**根因：** `emit_system_error()` 传入 `"system.system_error"`，但 `EventType.SYSTEM_ERROR` 的值是 `"system.error"`。同理 `system_warning` 和 `system_alert`。

**修改文件：**
- `backend/app/services/event_emitter.py`

**具体修改：**

| 函数 | 当前值 | 修正为 |
|------|--------|--------|
| `emit_system_error` (L481) | `"system.system_error"` | `"system.error"` |
| `emit_system_warning` (L498) | `"system.system_warning"` | `"system.warning"` |
| `emit_system_alert` (L515) | `"system.system_alert"` | `"system.alert"` |

**验证方法：**
- 检查 EventType 枚举值与传入值一致
- 在前端渠道配置中订阅 `system.error` 事件，触发系统错误后确认是否收到通知

---

### 阶段 2：P1 高优先级修复（通知可靠性）

#### 任务 2.1：修复升级规则 break 逻辑

**根因：** `notification_workers.py` L265-L277 中，`break` 语句在 `if rule.escalate_enabled:` 条件判断之外，导致无论规则是否启用升级，第一条规则被检查后就跳出循环。

**修改文件：**
- `backend/app/services/notification_workers.py`

**具体修改：**
```python
# 当前代码（L265-L277）：
for rule in rules.values():
    if rule.escalate_enabled:
        escalated = await rules_engine.check_escalation(...)
        if escalated:
            event.severity = rule.escalate_severity
            ...
        break   # ← 在 if 外面，始终执行

# 修正为：
for rule in rules.values():
    if rule.escalate_enabled:
        escalated = await rules_engine.check_escalation(...)
        if escalated:
            event.severity = rule.escalate_severity
            event.data["escalated"] = True
            logger.info(...)
        break  # ← 只有 escalate_enabled=True 时才 break
```

注意：这里的 `break` 逻辑本身是合理的（升级规则命中后不应继续检查其他规则），但需要确保只在 `escalate_enabled=True` 时才 break。

**验证方法：**
- 配置两条升级规则（不同 event_type 或 channel_name）
- 触发足够事件验证两条规则都能被检查

#### 任务 2.2：区分实时事件和聚合事件的发送策略

**根因：** `AGGREGATION_WINDOW = 300`（5 分钟）对关键运维告警事件不可接受。

**修改文件：**
- `backend/app/services/event_emitter.py`
- `backend/app/services/notification_channels/event_types.py`（可选：添加事件实时性元数据）

**修改方案：**
1. 在 `EVENT_METADATA` 中为每个事件类型添加 `"realtime": true/false` 标识
2. `realtime=true` 的事件直接走 Worker 管道，不经过聚合
3. `realtime=false` 的事件（如终端上下线批量通知）可配置聚合窗口
4. 默认所有 error/critical 级别事件为 realtime，info 级别可聚合

**验证方法：**
- 触发 `system.firewall_connection_lost` 等关键事件，确认 5 秒内（而非 5 分钟）收到通知

---

### 阶段 3：P2 中优先级修复（功能完整性）

#### 任务 3.1：添加缺失的事件发射调用点

**根因：** 32 种事件类型中仅 12 种有实际调用方，8 种已定义但从未被发射。

**修改文件：**

| 事件类型 | 调用方文件 | 发射时机 |
|----------|-----------|---------|
| `system.firewall_connection_lost` | `backend/app/services/firewall_service.py` | 防火墙连接检查失败时 |
| `system.firewall_connection_restored` | `backend/app/services/firewall_service.py` | 防火墙连接恢复时 |
| `system.backup_completed` | `backend/app/main.py` 或 `backup_service.py` | 定时备份完成后 |
| `system.backup_failed` | `backend/app/main.py` 或 `backup_service.py` | 定时备份失败后 |
| `alert.compliance_rate_low` | `backend/app/services/compliance_service.py` | 合规检查发现合规率低于阈值时 |
| `alert.compliance_rate_critical` | `backend/app/services/compliance_service.py` | 合规率严重低于阈值时 |
| `alert.block_threshold` | `backend/app/services/compliance_service.py` | 封禁数量超过阈值时 |
| `alert.policy_violation` | `backend/app/services/compliance_service.py` | 终端违反安全策略时 |

**验证方法：**
- 分别触发上述场景，检查通知日志是否生成对应记录

#### 任务 3.2：实现终端在线/离线周期性检测

**根因：** `TERMINAL_OFFLINE` 事件已定义但从未调用，`TERMINAL_ONLINE` 仅在首次发现新终端时触发一次。

**修改文件：**
- `backend/app/services/arp_collector_service.py`

**修改方案：**
1. 在 ARP 采集服务中维护"上次在线"终端集合
2. 每次 ARP 采集后，对比当前集合与上次集合
3. 新出现的终端 → 发射 `terminal.online`
4. 消失的终端 → 发射 `terminal.offline`
5. 为避免频繁通知，使用可配置的离线确认窗口（如连续 3 次未采集到才判定为离线）

**验证方法：**
- 断开某终端网络，等待 3 个采集周期后确认是否收到 `terminal.offline` 通知
- 恢复网络后确认是否收到 `terminal.online` 通知

#### 任务 3.3：重构聚合器为 Worker 管道内的可选步骤

**目标：** 将聚合器从"优先路径黑洞"重构为 Worker 管道内的可选中间件步骤。

**修改文件：**
- `backend/app/services/notification_workers.py`
- `backend/app/services/notification_aggregator.py`

**修改方案：**
```
Worker._deliver_notification() 流程（修改后）：
1. 加载订阅渠道列表
2. 加载规则（含通配符 *）
3. 检查升级规则（escalation）
4. 检查抑制规则（suppression）
5. [新增] 执行聚合（仅对配置为可聚合的事件类型）
   - 聚合窗口内的事件合并为一条通知
   - 非聚合事件直接传递
6. 渲染模板（Jinja2）
7. 渠道发送
8. 记录日志
```

**验证方法：**
- 高频事件（如 terminal.online）被合并发送
- 关键事件（如 system.firewall_connection_lost）不受聚合延迟影响

#### 任务 3.4：Jinja2 模板安全加固

**根因：** `jinja2.Environment(autoescape=False)` 允许模板中执行任意 Python 表达式。

**修改文件：**
- `backend/app/services/notification_logging.py`

**修改方案：**
1. 使用 `jinja2.sandbox.SandboxedEnvironment` 替代 `Environment`
2. 限制模板中可用的变量和过滤器
3. 或保持当前 `Environment` 但添加输入校验（管理员权限控制已足够）

**建议：** 由于模板编辑仅限管理员操作，当前风险可控。优先使用方案二：保留现有实现但添加变量白名单校验。

**验证方法：**
- 尝试在模板中注入 `{{ ''.__class__ }}` 等代码，确认被拒绝

---

### 阶段 4：P3 低优先级改进建议

#### 任务 4.1：添加事件发射覆盖率监控

**修改文件：**
- `backend/app/services/notification_service.py`
- `backend/app/api/v1/endpoints/notifications.py`

在统计 API 中添加"已发射事件类型"vs"已定义事件类型"的对比，帮助管理员了解哪些事件类型尚未被使用。

#### 任务 4.2：备份完成/失败事件对接

在 P0 修复通知管道后，立即在 `scheduled_backup()` 中添加 `emit_backup_completed()` / `emit_backup_failed()` 调用。

#### 任务 4.3：合规率告警对接

在 `scheduled_compliance_check()` 中添加合规率阈值检查和 `emit_compliance_alert()` 调用。

---

## 三、架构改进总览

### 修改后的目标架构

```
事件触发方
    │
    ▼
emit_event(event_type, data, source, severity)
    │
    ▼
NotificationService.emit()
    │
    ▼
Redis Queue (notify:queue:main)
    │
    ▼
NotificationWorkers._deliver_notification()
    │
    ├── 1. 加载订阅渠道列表（_get_subscribed_channels）
    ├── 2. 加载规则（get_rules_for_event，含通配符 *）
    ├── 3. 检查升级规则（check_escalation，命中后 break）
    ├── 4. 检查抑制规则（check_suppression）
    ├── 5. 执行可选聚合（仅聚合型事件）
    ├── 6. 渲染模板（Jinja2）
    ├── 7. 渠道发送（Email/Webhook/飞书/钉钉/企微）
    └── 8. 记录日志（log_sent / log_failed / log_suppressed）
```

### 涉及文件清单

| 文件 | 修改类型 | 阶段 |
|------|---------|------|
| `backend/app/services/event_emitter.py` | 重构 emit_event() + 修正字符串 | P0 |
| `backend/app/services/notification_workers.py` | 修复 break 逻辑 + 集成聚合步骤 | P1 + P2 |
| `backend/app/services/notification_logging.py` | Jinja2 安全加固 | P2 |
| `backend/app/services/notification_aggregator.py` | 重构为可选中间件 | P2 |
| `backend/app/services/notification_channels/event_types.py` | 添加实时性元数据 | P1 |
| `backend/app/main.py` | 对接备份事件发射 | P3 |
| `backend/app/services/compliance_service.py` | 对接合规率告警事件 | P3 |
| `backend/app/services/arp_collector_service.py` | 实现在线/离线检测 | P2 |
| `backend/app/services/firewall_service.py` | 对接防火墙事件发射 | P2 |

### 回滚策略

对于 P0 阶段的关键变更（emit_event 重构），采用以下回滚方案：
1. 在 `NotificationService.emit()` 中保留原聚合器路径作为 feature flag 控制的备选
2. 通过数据库配置项 `notification_use_aggregator` 控制走新管道还是原聚合器路径
3. 默认启用新管道（`notification_use_aggregator = false`）
4. 如遇问题可通过设置 `notification_use_aggregator = true` 临时回滚

### 风险评估

| 阶段 | 风险 | 缓解措施 |
|------|------|---------|
| P0 | 通知管道切换可能导致短暂通知丢失 | 灰度切换 + feature flag + 日志监控 |
| P1 | break 修复可能改变多规则场景行为 | 充分的单元测试覆盖 |
| P2 | 新事件发射点可能产生通知风暴 | 抑制规则 + 可配置阈值 |
| P3 | 低风险，渐进式实施 | 代码审查 |

---

## 四、验证矩阵

| 阶段 | 修复项 | 验证场景 | 预期结果 |
|------|--------|---------|---------|
| P0-1 | emit_event 重构 | 触发 terminal.blocked 事件 | 通知日志表新增记录，Worker 消费成功 |
| P0-1 | emit_event 重构 | 检查 Redis 队列 | 事件入队后被 Worker 消费 |
| P0-2 | 事件字符串修复 | 订阅 system.error 并触发 | 飞书/邮件渠道收到系统错误通知 |
| P1-1 | break 逻辑修复 | 配置 2 条升级规则 | 两条规则均被检查 |
| P1-2 | 实时事件策略 | 触发 firewall_connection_lost | 5 秒内收到通知 |
| P2-1 | 缺失事件对接 | 手动触发备份完成/失败 | 收到 backup_completed/failed 通知 |
| P2-2 | 在线离线检测 | 断开终端后恢复 | 收到 offline/online 通知 |
| P2-3 | 聚合器集成 | 高频 terminal.online 事件 | 被合并为单条通知 |
| P2-4 | Jinja2 安全 | 尝试注入恶意模板 | 被拒绝或安全处理 |

---

## 五、实施顺序

```
P0-1 (emit_event重构) → P0-2 (字符串修复)
    ↓
P1-1 (break修复) → P1-2 (实时事件策略)
    ↓
P2-1 (事件发射点) → P2-2 (在线离线检测) → P2-3 (聚合器集成) → P2-4 (Jinja2加固)
    ↓
P3-1 (覆盖率监控) → P3-2 (备份事件) → P3-3 (合规率告警)
```

每个阶段完成后进行完整的业务验证，确认无误后再进入下一阶段。