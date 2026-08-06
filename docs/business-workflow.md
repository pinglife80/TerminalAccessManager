# TerminalAccessManager 业务流程文档

> 文档版本：v3.10.0  更新日期：2026-08-06
>
> 本文档详细说明 TerminalAccessManager 的核心业务流程，包括数据采集、合规判定、封锁/解封的完整生命周期。

---

## 目录

1. [概述](#1-概述)
2. [数据采集流程](#2-数据采集流程)
3. [合规判定流程](#3-合规判定流程)
4. [自动封锁流程](#4-自动封锁流程)
5. [自动解封流程](#5-自动解封流程)
6. [黑名单管理流程](#6-黑名单管理流程)
7. [状态机流转图](#7-状态机流转图)
8. [关键参数说明](#8-关键参数说明)
9. [事件触发点汇总](#9-事件触发点汇总)

---

## 1. 概述

TerminalAccessManager 的核心业务流程由以下环节组成：

```
数据采集 → 合规判定 → 状态更新 → 封锁/解封 → 审计记录 → 通知事件
```

### 核心组件

| 组件 | 职责 | 关键文件 |
|------|------|---------|
| ARP采集服务 | 从网络设备采集终端IP/MAC信息 | `arp_collector_service.py` |
| 数据源服务 | 管理数据源配置和绑定关系 | `data_source_service.py` |
| 合规服务 | 执行合规判定和自动封锁/解封 | `compliance_service.py` |
| 终端服务 | 管理终端信息和封锁/解封操作 | `terminal_service.py` |
| 深信服服务 | 调用深信服AF防火墙API | `sangfor_service.py` |
| 事件发射器 | 发送通知事件 | `event_emitter.py` |

---

## 2. 数据采集流程

### 2.1 流程概述

数据采集流程负责从网络设备（交换机、路由器）获取终端的IP地址和MAC地址信息。

### 2.2 采集方式

| 采集方式 | 类型 | 说明 |
|---------|------|------|
| SSH采集 | `arp_ssh` | 通过SSH连接到网络设备执行命令获取ARP表 |
| API采集 | `arp_api` | 通过HTTP API获取终端信息 |

### 2.3 执行步骤

```
定时任务触发 → 建立连接 → 执行命令/调用API → 解析响应 → 保存终端记录 → 触发合规检查
```

### 2.4 关键参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `source_tag` | string | 数据源标识，用于绑定防火墙和追踪来源 |
| `ip_address` | string | 终端IP地址（IPv4/IPv6） |
| `mac_address` | string | 终端MAC地址 |
| `timestamp` | datetime | 采集时间戳 |
| `source` | string | 来源类型（arp/ipguard/whitelist/manual） |

### 2.5 数据模型

```python
class Terminal(Base):
    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False, index=True)
    mac_address_normalized = Column(String(12), nullable=True, index=True)
    status = Column(String(20), default="unblocked", index=True)
    compliance_status = Column(String(20), default="unknown", index=True)
    source_tag = Column(String(50), nullable=True, index=True)
    firewall_tag = Column(String(50), nullable=True, index=True)
```

---

## 3. 合规判定流程

### 3.1 流程概述

合规判定流程根据白名单和IPGuard基线数据，判定终端是否合规。

### 3.2 判定逻辑

```
终端信息 → 白名单匹配 → IPGuard匹配 → 合规状态更新
```

### 3.3 判定规则

| 条件 | 合规状态 | 说明 |
|------|---------|------|
| 匹配白名单 | `bypass` | 终端在白名单中，跳过合规检查 |
| 匹配IPGuard | `compliant` | 终端在IPGuard基线中，合规 |
| 不匹配任何 | `non_compliant` | 终端不在白名单和IPGuard中，不合规 |
| 未检查 | `unknown` | 终端刚采集，尚未执行合规检查 |

### 3.4 翻转确认机制（v3.7.0 新增）

#### 背景

IPGuard 基线数据中的 `AGENT.AGT_IP_MAC_STR` 字段记录 agent 当前上报的 IP+MAC 绑定关系。当终端 DHCP 续租或 agent 重连时该字段会更新，导致 TAM 的 IP+MAC 精确匹配瞬时失败。若直接采用单次同步结果判定合规状态，会产生"合规振荡"（终端在 compliant 与 non_compliant 之间频繁翻转，引发防火墙反复封堵/解封）。

#### 机制说明

`recalculate_all_compliance` 中对 compliant/bypass → non_compliant 的翻转引入 `non_compliant_confirm_count` 计数器：

| 终端当前状态 | 单次判定结果 | 行为 |
|-------------|-------------|------|
| unknown | non_compliant | **立即生效**，计数器不参与，触发封堵 |
| non_compliant | non_compliant | 保持 non_compliant，计数器归零 |
| compliant/bypass | non_compliant | 计数器 +1，未达阈值则**保持原状态**；达到阈值（默认 2）后变更为 non_compliant 并触发封堵 |
| 任意状态 | compliant/bypass | 计数器归零，正常变更状态 |

> **说明**：首次发现的新终端（unknown → non_compliant）不受确认机制影响，立即封堵，确保新接入的不合规终端能被及时处置。

#### 配置项

| 配置键 | 默认值 | 取值范围 | 说明 |
|--------|--------|---------|------|
| `compliance_confirm_threshold` | 2 | 1-10 | compliant/bypass → non_compliant 翻转所需连续确认次数 |

#### 相关数据

- 数据库字段：`terminals.non_compliant_confirm_count`（INTEGER, NOT NULL, DEFAULT 0）
- 迁移脚本：`backend/alembic/versions/029_terminal_non_compliant_confirm_count.py`

### 3.5 执行步骤

```python
def _match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr):
    # 按MAC、IP、IP范围顺序匹配白名单
    # 返回匹配结果或None

def _match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr):
    # 在IPGuard数据中查找终端
    # 返回匹配结果或None

# 判定逻辑（含翻转确认机制）
if wl_result:
    new_compliance = "bypass"
    terminal.non_compliant_confirm_count = 0
elif ig_match:
    new_compliance = "compliant"
    terminal.non_compliant_confirm_count = 0
else:
    if old_compliance in ("non_compliant", "unknown"):
        # 已是不合规或新终端：立即生效
        new_compliance = "non_compliant"
    else:
        # compliant/bypass → non_compliant：需连续 N 次确认
        terminal.non_compliant_confirm_count += 1
        if terminal.non_compliant_confirm_count >= confirm_threshold:
            new_compliance = "non_compliant"
            terminal.non_compliant_confirm_count = 0
        else:
            new_compliance = old_compliance  # 保持原状态
```

### 3.6 触发时机

| 触发场景 | 说明 |
|---------|------|
| ARP数据采集完成 | 新采集的终端自动触发合规检查，使用 `_apply_compliance_result` 共享方法 |
| 白名单变更 | 添加/删除白名单条目后触发全量重算，使用 `_apply_compliance_result` 共享方法 |
| IPGuard同步完成 | 基线数据更新后触发全量重算，使用 `_apply_compliance_result` 共享方法 |
| 定时合规检查 | 定期检查 `compliance_status="unknown"` 的终端，使用 `_apply_compliance_result` 共享方法 |
| 手动触发 | 通过API手动触发合规重算 |

### 3.7 统一合规应用方法

`_apply_compliance_result` 是所有合规检查路径共享的方法，确保行为一致性：

| 功能 | 说明 |
|------|------|
| 更新 compliance_status | 设置终端的合规状态 |
| 更新 wl_match_type | 设置白名单匹配类型 |
| 更新 comments | 同步白名单备注（`Whitelist: xxx`），支持替换旧备注 |
| 状态变更事件 | 合规状态变更时触发对应事件通知 |
| 自动解封 | 终端从 blocked 变为 compliant/bypass 时自动解封 |
| 自动封堵 | 终端变为 non_compliant 且未封锁时自动封堵 |

### 3.8 白名单备注管理

白名单条目支持备注（comment）字段，用于记录添加原因或管理信息。备注信息会同步写入匹配终端的 `remarks` 字段，便于在终端列表中追溯白名单来源。

### 3.8.1 白名单匹配类型

白名单支持以下匹配类型：

| 类型 | 说明 | 匹配条件 |
|------|------|---------|
| `mac_only` | 仅MAC匹配 | 只提供MAC地址 |
| `single_ip` | 单IP匹配 | 只提供单个IP（含/32 CIDR） |
| `cidr` | CIDR匹配 | 提供CIDR网段（非/32） |
| `ip_range` | IP范围匹配 | 提供IP范围（如 192.168.1.1-192.168.1.100） |
| `both` | MAC+IP双重匹配 | 同时提供MAC和IP地址 |

### 3.8.2 添加白名单

添加白名单条目时可填写备注（**必填**），系统会根据添加内容自动确定匹配类型：
- 仅 MAC 地址：匹配类型为 `mac_only`，匹配单个终端
- 仅 IP 地址（不含/32）：匹配类型为 `single_ip`，匹配单个终端
- IP 地址带/32：匹配类型为 `single_ip`，匹配单个终端
- CIDR 网段：匹配类型为 `cidr`，匹配网段内所有终端
- IP 范围：匹配类型为 `ip_range`，匹配范围内所有终端
- MAC + IP：匹配类型为 `both`，IP和MAC都必须匹配

### 3.8.3 删除白名单

删除白名单条目时，系统会自动清除关联终端的备注信息和 `wl_match_type`，确保备注与白名单状态一致：
- 通过 `_remove_whitelist_comment` 方法实现
- 支持 MAC/IP/CIDR/范围所有匹配类型的终端备注清除
- 仅清除由该白名单条目写入的备注，不影响其他来源的备注信息

---

## 4. 自动封锁流程

### 4.1 流程概述

自动封锁流程在合规判定完成后，对不合规终端执行自动封锁操作。

### 4.2 执行步骤

```
合规判定完成 → 筛选non_compliant终端 → 获取绑定防火墙 → 调用深信服API封锁 → 更新数据库 → 记录审计日志 → 发送通知事件
```

### 4.3 详细步骤

#### 步骤1：筛选不合规终端

```python
stmt = select(Terminal).where(
    (Terminal.source_tag == arp_source_tag) &
    (Terminal.compliance_status == "non_compliant") &
    (Terminal.status != "blocked")
)
```

#### 步骤2：获取绑定防火墙

```python
# 通过数据源绑定关系获取防火墙标签
firewall_tags = await ds_service.get_firewall_tags_for_arp(arp_source_tag)
```

#### 步骤3：调用深信服API

```python
response = await svc.block_ip(
    [entry.ip_address],
    source_tag=fw_tag,
    reason=f"Auto-blocked: non-compliant (source={arp_source_tag})"
)
```

#### 步骤4：更新数据库

```python
# 更新终端状态
entry.status = "blocked"
entry.firewall_tag = firewall_tags[0] if len(firewall_tags) == 1 else ",".join(firewall_tags)
# 注意：firewall_tag 仅在 status='blocked' 时设置

# 创建黑名单记录
blacklist_entry = Blacklist(
    ip_address=entry.ip_address,
    mac_address=entry.mac_address,
    reason=f"Auto-blocked: non-compliant (source={arp_source_tag})",
    blocked_by="system",
    expires_at=datetime.now(UTC) + timedelta(days=30),
    source_tag=arp_source_tag,
    firewall_tag=fw_tag,
    is_auto_blocked=True,
    auto_unblocked=False,
)
```

#### 步骤5：记录审计日志

```python
await self.log_action("system", "auto_block_terminal", "terminal", None, {
    "message": f"Auto-blocked {blocked} non-compliant terminals",
    "source_tag": arp_source_tag,
    "blocked": blocked,
    "terminals": terminal_list[:50],
    "total_terminals": len(terminal_list),
})
```

#### 步骤6：发送通知事件

```python
await emit_terminal_blocked(ip_address, mac_address, reason, blocked_by)
await emit_policy_violation(policy_name, terminal_ip, details)

# 封锁数量超过阈值时发送告警
if blocked > block_threshold:
    await emit_block_threshold_exceeded(block_threshold, blocked)

# v3.9.0: 发射自动封锁触发告警事件
await emit_auto_block_triggered(blocked, arp_source_tag, terminal_list)
```

### 4.4 关键参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `arp_source_tag` | string | ARP数据源标签 |
| `block_time` | string | 封锁时长（默认30d） |
| `firewall_tag` | string | 防火墙标签 |
| `is_auto_blocked` | boolean | 是否自动封锁 |
| `expires_at` | datetime | 封锁过期时间 |

### 4.5 封堵失败重试机制（v3.7.0 新增）

#### 背景

防火墙 API 调用失败后，终端会停留在 `non_compliant + unblocked` 状态。原 `scheduled_compliance_check` 调度器只查询 `unknown` 状态的终端，不会重试已标记 `non_compliant` 但封堵失败的终端，导致非合规终端数大于已封堵终端数。

#### 机制说明

`scheduled_compliance_check` 调度器在每次执行时，额外扫描 `non_compliant + unblocked` 的终端并重新调用防火墙封堵 API：

```python
# 封堵失败重试逻辑
retry_stmt = select(Terminal).where(
    (Terminal.source_tag == source.tag) &
    (Terminal.compliance_status == "non_compliant") &
    (Terminal.status == "unblocked")
)
retry_terminals = retry_stmt.scalars().all()
if retry_terminals:
    # 重新执行封堵操作
    ...
```

| 扫描周期 | 扫描条件 | 处理动作 |
|---------|---------|---------|
| 300 秒 | `compliance_status="non_compliant" AND status="unblocked"` | 重新调用防火墙封堵 API |

> **说明**：该机制确保防火墙 API 瞬时失败（网络抖动、设备重启等）不会导致终端永久停留在未封堵状态。重试与定时合规检查共享同一调度周期。

---

## 5. 自动解封流程

### 5.1 流程概述

自动解封流程在终端合规状态变为compliant或bypass后，执行自动解封操作。

### 5.2 执行步骤

```
合规重算完成 → 筛选已合规但仍被封锁的终端 → 获取绑定防火墙 → 调用深信服API解封 → 更新数据库 → 记录审计日志 → 发送通知事件
```

### 5.3 详细步骤

#### 步骤1：筛选待解封终端

```python
# 在compliance_service.py的recalculate_compliance中
if terminal.status == "blocked" and new_compliance in ("bypass", "compliant"):
    # 需要解封
```

#### 步骤2：调用深信服API解封

```python
success = await self._unblock_on_firewall(ip_addr, fw_tag)
```

#### 步骤3：更新数据库

```python
# 更新终端状态
terminal.status = "unblocked"
terminal.firewall_tag = None  # 状态变为非blocked时必须清除firewall_tag

# 更新黑名单记录（软删除）
bl_entry.unblocked_at = datetime.now(UTC)
bl_entry.unblocked_by = "system"
bl_entry.auto_unblocked = True
```

#### 步骤4：记录审计日志

```python
await self.log_action("system", "auto_unblock_terminal", "terminal", None, {
    "message": f"Auto-unblocked {unblocked_count} compliant terminals",
    "unblocked": unblocked_count,
})
```

#### 步骤5：发送通知事件

```python
await emit_terminal_unblocked(ip_address, mac_address, blocked_by)
await emit_terminal_compliant(ip_address, mac_address, source_tag)
```

### 5.4 关键参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `unblocked_at` | datetime | 解封时间戳 |
| `unblocked_by` | string | 解封操作人 |
| `auto_unblocked` | boolean | 是否自动解封 |

---

## 6. 黑名单管理流程

### 6.1 数据模型

```python
class Blacklist(Base):
    ip_address = Column(String(45), nullable=True, index=True)
    mac_address = Column(String(17), nullable=True, index=True)
    mac_address_normalized = Column(String(12), nullable=True, index=True)
    reason = Column(Text, nullable=True)
    blocked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    blocked_by = Column(String(50), nullable=False)
    source_tag = Column(String(50), nullable=True)
    firewall_tag = Column(String(50), nullable=True)
    is_auto_blocked = Column(Boolean, default=False)
    auto_unblocked = Column(Boolean, default=False)
    unblocked_at = Column(DateTime(timezone=True), nullable=True)
    unblocked_by = Column(String(50), nullable=True)
```

### 6.2 黑名单状态

| 状态 | 条件 | 说明 |
|------|------|------|
| 活跃 | `auto_unblocked == False AND unblocked_at IS NULL` | 终端仍被封锁 |
| 已解封 | `auto_unblocked == True OR unblocked_at IS NOT NULL` | 终端已解封，记录保留用于审计 |

> **注意：** v3.6.6 统一了黑名单筛选逻辑，同时考虑 `auto_unblocked` 和 `unblocked_at` 两个字段，避免历史数据中 `auto_unblocked=True` 但 `unblocked_at IS NULL` 的记录被遗漏。

### 6.3 清理流程

定时任务定期清理过期的黑名单记录：

```python
async def cleanup_expired_blacklist(self) -> int:
    # 查找已过期且未解封的记录
    stmt = select(Blacklist).where(
        (Blacklist.expires_at < now) &
        (Blacklist.unblocked_at.is_(None))
    )
    # 执行解封操作（软删除）
    for entry in expired_entries:
        entry.unblocked_at = datetime.now(UTC)
        entry.unblocked_by = "system"
```

---

## 7. 状态机流转图

### 7.1 终端状态机

```
                    ┌──────────────────┐
                    │    unknown       │
                    │  (新采集终端)     │
                    └────────┬─────────┘
                             │ 合规检查
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │   bypass    │  │  compliant  │  │non_compliant│
    │  (白名单)   │  │ (IPGuard)   │  │  (不合规)   │
    └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
           │                 │                 │
           │ 自动解封        │ 自动解封        │ 自动封锁
           ▼                 ▼                 ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │  unblocked  │  │  unblocked  │  │   blocked   │
    │   (正常)    │  │   (正常)    │  │  (已封锁)   │
    └─────────────┘  └─────────────┘  └──────┬──────┘
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                       合规变更         合规变更          封锁过期
                              │              │              │
                              └──────────────┴──────────────┘
                                             ▼
                                    ┌─────────────┐
                                    │  unblocked  │
                                    │   (正常)    │
                                    └─────────────┘
```

### 7.2 合规状态流转

| 当前状态 | 触发条件 | 新状态 | 备注 |
|---------|---------|--------|------|
| unknown | 白名单匹配 | bypass | 立即生效 |
| unknown | IPGuard匹配 | compliant | 立即生效 |
| unknown | 无匹配 | non_compliant | 立即生效，触发封堵 |
| non_compliant | 白名单添加 | bypass | 立即生效，触发解封 |
| non_compliant | IPGuard同步 | compliant | 立即生效，触发解封 |
| compliant | IPGuard移除 | non_compliant | **需连续 N 次确认**（v3.7.0），N 由 `compliance_confirm_threshold` 控制 |
| bypass | 白名单移除 | compliant/non_compliant | 立即生效；若变为 non_compliant 需连续 N 次确认 |

> **v3.7.0 变更**：compliant/bypass → non_compliant 的翻转不再立即生效，需连续 N 次同步确认（默认 2 次）后才正式变更状态，以消除 IPGuard 数据波动导致的合规振荡。详见 [3.4 翻转确认机制](#34-翻转确认机制v370-新增)。

---

## 8. 关键参数说明

### 8.1 终端相关参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 防火墙封锁状态：blocked/unblocked |
| `compliance_status` | string | 合规状态：compliant/bypass/non_compliant/unknown |
| `source_tag` | string | ARP数据源标签 |
| `firewall_tag` | string | 绑定的防火墙标签 |
| `wl_match_type` | string | 白名单匹配类型：mac/ip/both |

### 8.2 黑名单相关参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `is_auto_blocked` | boolean | 是否由系统自动封锁 |
| `auto_unblocked` | boolean | 是否由系统自动解封 |
| `unblocked_at` | datetime | 解封时间（软删除标识） |
| `unblocked_by` | string | 解封操作人 |
| `expires_at` | datetime | 封锁过期时间 |

### 8.3 合规判定相关参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `block_threshold` | int | 单次自动封锁阈值（默认50） |
| `block_time` | string | 封锁时长配置（默认30d） |
| `compliance_confirm_threshold` | int | compliant/bypass → non_compliant 翻转确认阈值（默认2，范围1-10，v3.7.0新增） |
| `non_compliant_confirm_count` | int | 终端连续判定为 non_compliant 的计数器（数据库字段，v3.7.0新增） |
| `IPGUARD_CACHE_TTL` | int | IPGuard 缓存 TTL（v3.7.0 调整为 900 秒，1.5 倍同步间隔） |

---

## 9. 事件触发点汇总

### 9.1 安全事件

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| LOGIN_SUCCESS | 用户登录成功 | auth.py |
| LOGIN_FAILED | 用户登录失败 | auth.py |
| LOGIN_LOCKED | 账户锁定 | auth.py |
| PASSWORD_CHANGED | 密码变更 | auth.py |
| PASSWORD_RESET | 密码重置 | auth.py |
| USER_CREATED | 用户创建 | auth.py |
| USER_DELETED | 用户删除 | auth.py |
| USER_UPDATED | 用户更新 | auth.py |

### 9.2 终端事件

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| TERMINAL_BLOCKED | 终端被封锁 | terminal_service.py, compliance_service.py |
| TERMINAL_UNBLOCKED | 终端被解封 | terminal_service.py, compliance_service.py |
| TERMINAL_COMPLIANT | 终端变为合规 | compliance_service.py |
| TERMINAL_NON_COMPLIANT | 终端变为不合规 | compliance_service.py |
| TERMINAL_ONLINE | 新终端上线 | arp_collector_service.py |
| TERMINAL_OFFLINE | 终端离线 | arp_collector_service.py |

### 9.3 系统事件

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| FIREWALL_CONNECTION_LOST | 防火墙连接断开 | compliance_service.py |
| FIREWALL_CONNECTION_RESTORED | 防火墙连接恢复 | data_source_service.py |
| BACKUP_COMPLETED | 备份完成 | backup_service.py |
| BACKUP_FAILED | 备份失败 | backup_service.py |

### 9.4 合规告警

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| AUTO_BLOCK_TRIGGERED | 自动封锁触发 | compliance_service.py |
| AUTO_UNBLOCK_TRIGGERED | 自动解封触发 | compliance_service.py |
| COMPLIANCE_RATE_LOW | 合规率低 | main.py |
| BLOCK_THRESHOLD_EXCEEDED | 封锁阈值超限 | compliance_service.py |
| POLICY_VIOLATION | 策略违规 | compliance_service.py |

> **v3.9.0 变更**：`AUTO_BLOCK_TRIGGERED` 事件在此版本中正式发射，之前版本虽有定义但未实际触发。

### 9.5 管理事件

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| CONFIG_CHANGED | 配置变更 | settings.py |
| ROLE_CHANGED | 角色变更 | roles.py |
| PERMISSION_CHANGED | 权限变更 | roles.py |

---

## 10. v3.10.0 变更记录

### 10.1 备份工作流变更

> v3.10.0 变更：
> - 备份工作流：白名单备份受 backup_whitelist 选项控制
> - 备份工作流：远程存储过期备份自动清理

### 10.2 合规率告警变更

> v3.10.0 变更：
> - 合规率告警：阈值从硬编码 0.8 改为系统配置项（默认 80%）
> - 合规率告警：危险比例从硬编码 0.5 改为系统配置项（默认 50%）
> - 合规率告警：修复量纲不一致 bug（0-100 vs 0-1）