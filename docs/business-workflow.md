# TerminalAccessManager 业务流程文档

> 文档版本：v3.16.0  更新日期：2026-08-25
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
10. [v3.10.0 变更记录](#10-v3100-变更记录)
11. [防火墙对账流程](#11-防火墙对账流程v314-新增)
12. [后台调度任务周期汇总](#12-后台调度任务周期汇总v314-新增)

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
    mac_address_normalized = Column(String(12), nullable=False, index=True)  # Unique per MAC (v3.12+)
    status = Column(String(20), default="unblocked", index=True)
    compliance_status = Column(String(20), default="unknown", index=True)
    source_tag = Column(String(50), nullable=True, index=True)
    firewall_tag = Column(String(50), nullable=True, index=True)
    non_compliant_confirm_count = Column(Integer, default=0)  # Downgrade confirm counter
    compliant_confirm_count = Column(Integer, default=0)      # Upgrade confirm counter (v3.12+)
    ip_changed_at = Column(DateTime(timezone=True), nullable=True)  # Last IP change timestamp (v3.12+)

    __table_args__ = (
        UniqueConstraint('mac_address_normalized', name='uq_terminal_mac'),  # MAC is unique key (v3.12+)
    )
```

> **v3.12 重要变更**：终端记录以 MAC 地址为唯一标识，不再以 (IP, MAC) 联合主键。DHCP 换 IP 时更新现有记录而非新建，双网卡终端每个 MAC 独立一条记录。

---

## 3. 合规判定流程

### 3.1 流程概述

合规判定流程根据白名单、合规范围条件（Scope）和 IPGuard 基线数据，判定终端是否合规。

### 3.2 判定逻辑

```
终端信息 → 白名单匹配 → Scope范围条件检查 → IPGuard匹配 → 状态确认计数 → 合规状态更新
```

### 3.3 判定规则

| 条件 | 合规状态 | 说明 |
|------|---------|------|
| 匹配白名单 | `bypass` | 终端在白名单中，跳过合规检查 |
| 在Scope范围内 + IP匹配IPGuard | `compliant` | 命中Scope条件，忽略MAC仅用IP匹配IPGuard基线 |
| MAC匹配IPGuard + IP匹配 | `compliant` | 正常IP+MAC双重匹配IPGuard基线 |
| 不匹配任何 | `non_compliant` | 终端不在白名单和IPGuard中，不合规 |
| 未检查/IP变更宽限期 | `unknown`/保持原状态 | 终端刚采集或在IP变更宽限期内 |

### 3.4 合规范围条件（Scope）类型

v3.11 新增，v3.12 拆分 MAC 前缀类型：

| Scope类型 | 匹配对象 | 命中后行为 |
|-----------|---------|-----------|
| `ip_cidr` | 终端IP | 忽略MAC，仅用IP匹配IPGuard |
| `ip_range` | 终端IP（范围） | 忽略MAC，仅用IP匹配IPGuard |
| `mac_prefix_arp` | ARP采集的终端MAC前缀 | 忽略MAC，仅用IP匹配IPGuard |
| `mac_prefix_ipguard` | IPGuard基线中的MAC前缀 | 正常IP+MAC匹配，用于区分IPGuard基线中的特定设备类型 |

### 3.5 三层防震荡机制（v3.12 增强）

#### 背景

IPGuard 基线数据中的 `AGENT.AGT_IP_MAC_STR` 字段记录 agent 当前上报的 IP+MAC 绑定关系。当终端 DHCP 续租、agent 重连、双网卡切换或 IPGuard/ARP 同步时序不一致时，单次检查结果可能瞬态不匹配，导致"合规振荡"（终端在合规/不合规之间频繁翻转，引发防火墙反复封堵/解封）。

v3.12 引入三层防震荡保护彻底解决该问题：

#### 第一层：对称确认计数

`recalculate_all_compliance` 中对**所有状态翻转**引入双向对称确认计数：

| 终端当前状态 | 单次判定结果 | 行为 |
|-------------|-------------|------|
| 任意状态（含unknown/bypass） | non_compliant | 计数器 `non_compliant_confirm_count +1`，未达阈值**保持原状态**；达到阈值（默认 2 次≈10分钟）后变更为 non_compliant |
| non_compliant | compliant/bypass | 计数器 `compliant_confirm_count +1`，未达阈值保持 non_compliant；达到阈值后变更为 compliant/bypass |
| 任意状态 | 与当前状态一致 | 反向计数器归零 |

> **说明**：v3.12 起 unknown/bypass 状态首次不匹配不再立即封禁，统一需要连续 N 次确认，防止瞬态误判。

#### 第二层：双向冷却期

- 自动封禁后 10 分钟内不执行自动解封
- 自动解封后 10 分钟内不执行自动重新封禁
- 利用 blacklist 表中的 `blocked_at`/`unblocked_at` 时间戳判断，无需额外字段
- 手动操作不受冷却期限制

#### 第三层：IP变更宽限期

- ARP 采集发现 IP 变更时，记录 `ip_changed_at` 时间戳，**不立即重置**合规状态为 unknown
- IP 变更后 10 分钟宽限期内：即使 IPGuard 不匹配也保持原合规状态，等待 IPGuard 基线同步新 IP-MAC 映射
- 宽限期内仍累计不匹配计数，宽限期结束后正常按确认计数逻辑处理

#### action-state 一致性（自动解封同步写 compliance_status）

自动解封（`auto_unblock_compliant`）解封防火墙的同时，**同步写入 `compliance_status`**，并对两种命中类型分别设置：

| 命中的恢复依据 | 解封后 `compliance_status` |
|--------------|---------------------------|
| 白名单命中（bypass） | `bypass` |
| IPGuard 基线命中 | `compliant` |

并同步清零双侧确认计数，避免解封后留下 `non_compliant + unblocked` 的中间态（该中间态会被 retry-block 在冷却期后重新封禁，且让"非合规数 > 封锁数"，违反 `non_compliant ⇒ blocked` 不变量）。

> **v3.13/v3.14 变更**：早期版本这里是「解耦（不解封只改防火墙、compliance_status 交给下一轮）」；为避免中间态导致统计错乱与被重封，现改为「action-state 一致性」——解封动作与合规状态同步落地。

#### 配置项

| 配置键 | 默认值 | 取值范围 | 说明 |
|--------|--------|---------|------|
| `compliance_confirm_threshold` | 2 | 1-10 | 所有状态翻转（升级/降级）所需连续确认次数 |
| 冷却期（硬编码） | 10分钟 | - | 自动封禁/解封后最小间隔，可后续配置化 |
| IP变更宽限期（硬编码） | 10分钟 | - | DHCP换IP后等待IPGuard同步时间，可后续配置化 |

#### 相关数据

- 数据库字段：
  - `terminals.non_compliant_confirm_count`（INTEGER, NOT NULL, DEFAULT 0）- 降级确认计数
  - `terminals.compliant_confirm_count`（INTEGER, NOT NULL, DEFAULT 0）- 升级确认计数（v3.12+）
  - `terminals.ip_changed_at`（DATETIME(timezone), nullable）- 最近IP变更时间（v3.12+）
  - `terminals.mac_address_normalized` 唯一约束 `uq_terminal_mac`（v3.12+）
- 迁移脚本：
  - `032_mac_prefix_scope_type_split.py` - MAC前缀类型拆分
  - `033_terminal_mac_unique.py` - MAC唯一约束与数据去重
  - `034_compliance_oscillation_fixes.py` - 新增对称计数和IP变更时间戳字段

### 3.6 双网卡终端处理（v3.12+）

- 终端同时连接有线+无线网络时，ARP采集会获取到两个独立的 (MAC, IP) 对
- v3.12 起每个 MAC 对应一条独立的 Terminal 记录，分别进行合规判断
- IPGuard 基线中双网卡记录格式为：`MAC1(IP1)MAC2(IP2)...`，合规解析时正确展开为独立的 (MAC, IP) 对条目
- 合规匹配时：MAC1+IP1 和 MAC2+IP2 分别独立匹配，任一匹配即该 MAC 对应的记录合规；不匹配的 MAC 独立进入确认计数流程

### 3.7 执行步骤

```python
def _match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr):
    # 按MAC、IP、IP范围顺序匹配白名单
    # 返回匹配结果或None

def _match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr, ipguard_mac_prefixes=None):
    # 在IPGuard数据中查找终端，支持IPGuard MAC前缀匹配
    # 正确解析多MAC-IP对格式 "MAC1(IP1)MAC2(IP2)..."
    # 返回匹配结果或None

# 判定逻辑（v3.12 含三层防震荡机制）
if wl_result:
    current_check_status = "bypass"
    ...
elif ig_match:
    current_check_status = "compliant"
    ...
else:
    current_check_status = "non_compliant"

# IP变更宽限期检查
if in_ip_grace_period and current_check_status == "non_compliant":
    hold current state, increment non_compliant_confirm_count
elif current_check_status == old_compliance:
    reset opposite counter
elif current_check_status == "non_compliant":
    # 降级：需连续 N 次确认（任意状态，含unknown/bypass）
    terminal.non_compliant_confirm_count += 1
    terminal.compliant_confirm_count = 0
    if non_compliant_confirm_count >= confirm_threshold:
        new_compliance = "non_compliant"
else:
    # 升级：需连续 N 次确认
    terminal.compliant_confirm_count += 1
    terminal.non_compliant_confirm_count = 0
    if compliant_confirm_count >= confirm_threshold:
        new_compliance = current_check_status

# 冷却期检查：封禁/解封操作前检查是否在10分钟冷却期内
```

### 3.8 触发时机

| 触发场景 | 说明 |
|---------|------|
| ARP数据采集完成 | 新采集的终端自动触发合规检查，使用 `_apply_compliance_result` 共享方法 |
| 白名单变更 | 添加/删除白名单条目后触发全量重算，使用 `_apply_compliance_result` 共享方法 |
| 定时合规检查 | 定期检查所有终端合规状态，使用对称确认计数更新状态 |
| Scope条件变更 | 合规范围条件变更后失效缓存，下一轮检查使用新条件 |
| IPGuard同步完成 | v3.12起基线数据更新后**不立即**触发全量重算，由下一轮定时合规检查自然使用新缓存，避免时序竞争 |
| 定时自动解封 | 定期检查已封禁终端是否恢复合规，冷却期保护下执行解封 |
| 手动触发 | 通过API手动触发合规重算 |

### 3.9 统一合规应用方法

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
| `block_time` | string | 封锁时长（可配置，默认 30d；支持 1h/6h/12h/1d/3d/7d/15d/30d） |
| `firewall_tag` | string | 防火墙标签 |
| `is_auto_blocked` | boolean | 是否自动封锁 |
| `expires_at` | datetime | 封锁过期时间 |

### 4.5 定时合规检查调度器：四段式流程（v3.7.0 新增，v3.13/v3.14 完善）

#### 背景

防火墙 API 调用失败后，终端会停留在 `non_compliant + unblocked` 状态。原调度器只查 `unknown` 终端，不会重试已标记 `non_compliant` 但封堵失败的终端，导致非合规终端数大于已封堵终端数，且陈旧中间态无法自愈。

#### 机制说明

`scheduled_compliance_check`（默认每 300 秒）每个周期按顺序执行四段：

| 段 | 处理内容 | 判断/动作 |
|----|---------|----------|
| ① unknown 检查 + auto_block | 对 `compliance_status=unknown` 的终端执行合规判定，判定为 non_compliant 的触发自动封锁 | 走三层防震荡确认计数 |
| ② retry-block（重试封锁） | 扫描 `non_compliant + unblocked` 中间态终端，**忽略冷却期强制重新封锁** | 封锁前先做白名单权威预检：命中白名单的终端自愈为 `bypass` 并单独提交，不回滚进封锁批次 |
| ③ 周期性全量重算 | `recalculate_all_compliance()` 全量自愈，修复卡死/陈旧状态 | 每周期执行（自愈 stale 状态） |
| ④ 全局合规率告警 | 统计合规率，低于阈值触发 `COMPLIANCE_RATE_LOW` 告警 | 阈值来自系统配置（默认 80%），危险比例默认 50% |

```python
# ②retry-block 中间态扫描口径（仅启用的 arp_ssh/arp_api 数据源）
retry_stmt = select(Terminal).where(
    source_tag IN (启用 arp_ssh/arp_api) &
    (Terminal.compliance_status == "non_compliant") &
    (Terminal.status == "unblocked")
)
```

| 扫描周期 | 扫描条件 | 处理动作 |
|---------|---------|---------|
| 300 秒（`scheduler_compliance_check_interval`） | `non_compliant AND unblocked` | 强制重新调用防火墙封堵 API（忽略冷却期） |

> **说明**：该机制确保防火墙 API 瞬时失败（网络抖动、设备重启等）不会导致终端永久停留在未封堵状态；retry-block 对已存在的 `non_compliant + unblocked` 中间态直接强制封锁，尽快修复历史中间态。

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
    # v3.14 新增：黑名单操作追踪字段（迁移 036）
    last_operation_type = Column(String(20), nullable=True)     # block / unblock
    last_operation_status = Column(String(20), nullable=True)   # success / failed
    last_operation_error = Column(Text, nullable=True)          # 失败原因
    last_operation_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)    # 重试次数
```

### 6.2 黑名单状态

| 状态 | 条件 | 说明 |
|------|------|------|
| 活跃 | `auto_unblocked == False AND unblocked_at IS NULL` | 终端仍被封锁 |
| 已解封 | `auto_unblocked == True OR unblocked_at IS NOT NULL` | 终端已解封，记录保留用于审计 |

> **注意：** v3.6.6 统一了黑名单筛选逻辑，同时考虑 `auto_unblocked` 和 `unblocked_at` 两个字段，避免历史数据中 `auto_unblocked=True` 但 `unblocked_at IS NULL` 的记录被遗漏。

> **对账补建条目（v3.13+）**：防火墙对账从防火墙实际封锁列表补建的 Blacklist 条目，若找不到终端记录，则 `mac_address`/`mac_address_normalized` 为 NULL、`source_tag="reconciliation"`。这类 NULL-MAC 条目在终端匹配 / 统计口径中回退到 IP 匹配（见 [§11 防火墙对账流程](#11-防火墙对账流程v314-新增)）。

### 6.3 黑名单过期清除流程

系统定时扫描已到过期时间的活跃封禁条目，在防火墙上解封后同步数据库与终端状态，并触发合规重算。核心实现在 `terminal_service.py::cleanup_expired_blacklist`。

#### 6.3.1 触发时机

由后台任务 `cleanup_expired_blacklist()`（`main.py`）驱动：

- **周期**：每轮间隔取系统配置 `scheduler_firewall_query_interval`（默认 300 秒），经 `_get_scheduler_interval` 读取并 clamp 到 30–86400 秒；`while True` 循环持续运行。
- **并发控制**：每轮执行前经两层保护——
  - 暂停开关：Redis 键 `scheduler:ctrl:firewall_query` 为 `paused` 时本轮跳过（`_is_task_paused`）。
  - 分布式锁：Redis 键 `scheduler:lock:firewall_query` 以 `SET NX EX` 抢占，抢不到即跳过，避免多实例重复执行（`_acquire_task_lock`）。
- **异常隔离**：整体 try/except，出错仅记日志 `[source=scheduler]`，不影响下一轮。

> 该任务名沿用 `firewall_query` 与 `scheduler_firewall_query_interval` 配置键，但实际执行的是「黑名单过期清除」，非防火墙查询。

#### 6.3.2 判断标准

| 判定项 | 条件 | 说明 |
|------|------|------|
| 过期条目（待清理） | `expires_at < now` 且 `auto_unblocked == False` | 已到过期时间且尚未自动解封 |
| 仍活跃条目（同 MAC 反向依据） | `unblocked_at IS NULL` 且 `auto_unblocked == False` 且（`expires_at >= now` 或 `expires_at IS NULL`） | 存在即代表该终端仍有其它有效封锁 |
| 永久封禁 | `expires_at IS NULL` | 永不纳入自动过期清理（`expires_at < now` 对 NULL 不成立） |

#### 6.3.3 执行流程

```
定时任务触发 → 查询过期条目 → 批量预加载 → 逐条处理(同行活跃检查 + 防火墙解封) → 提交审计 → 触发合规重算
```

1. **查询过期条目**：`expires_at < now AND auto_unblocked == False`；为空直接返回 0。
2. **批量预加载（避免 N+1）**：
   - 按 `mac_address_normalized` 一次性加载所有受影响终端（MAC 为稳定标识，应对 DHCP 换 IP）。
   - 一次性查 `active_block_macs`（这些 MAC 仍存在其它活跃封锁）。
   - 按 `firewall_tag` 预解析 `SangforService` 实例并缓存。
3. **逐条处理**：
   - **同 MAC 仍有其它活跃封锁**（`mac_address_normalized in active_block_macs`）→ 仅标记本条 `unblocked_at=now`、`unblocked_by="system"`，**不在防火墙上真正解封**（防止多防火墙场景误解封其它仍有效条目）。
   - **是本 MAC 最后一条活跃封锁** → 若终端当前 `status == "blocked"`，则恢复 `status=unblocked`、`compliance_status=unknown`、`firewall_tag=None`（非 blocked 终端不改状态；`processed_macs` 去重，避免同一 MAC 重复更新）。
   - **防火墙解封**：
     - 成功 → 标记 `unblocked_at/by`，计数 +1。
     - 失败（防火墙禁用/缺失 / API 返回 `code != 0` / 异常）→ **不标记解封**，将 `expires_at` 延后 `now + 30min` 供下一轮重试，保证 DB 与防火墙状态一致；记录进失败清单。
     - 无 `firewall_tag` 的孤儿条目 → 记 warning 但仍标记解封。
4. **提交 + 审计**：`count > 0` 时写入审计日志（含清理数量与失败 IP 列表），`commit`。
5. **合规重算**：提交后触发 `recalculate_all_compliance()`，让因解封而状态变为 `unknown` 的终端尽快被重新评估，仍不合规的重新入封，形成闭环。

```python
async def cleanup_expired_blacklist(self) -> int:
    now = datetime.now(UTC)
    # 已过期且尚未自动解封
    stmt = select(Blacklist).where(
        (Blacklist.expires_at < now) &
        (Blacklist.auto_unblocked == False)
    )
    expired_entries = result.scalars().all()
    ...
    # 逐条处理
    for entry in expired_entries:
        if entry.mac_address_normalized in active_block_macs:
            # 同 MAC 仍有其它活跃封锁：仅软删除本条，防火墙保留
            entry.unblocked_at = now
            entry.unblocked_by = "system"
            continue
        # 本 MAC 最后一条活跃封锁：恢复终端 + 防火墙解封
        ...
        if not unblock_success:
            # 解封失败：延后 30 分钟重试，保持 DB 与防火墙一致
            entry.expires_at = now + timedelta(minutes=30)
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
| `block_time` | string | 封锁时长（可配置，默认 30d；系统设置页配默认值，auto-block 弹窗可逐次指定） |
| `compliance_confirm_threshold` | int | compliant/bypass → non_compliant 翻转确认阈值（默认2，范围1-10，v3.7.0新增） |
| `non_compliant_confirm_count` | int | 终端连续判定为 non_compliant 的计数器（数据库字段，v3.7.0新增） |
| `IPGUARD_CACHE_TTL` | int | IPGuard 缓存 TTL（v3.7.0 调整为 900 秒，1.5 倍同步间隔） |

### 8.4 黑名单操作追踪参数（v3.14 新增）

| 参数 | 类型 | 说明 |
|------|------|------|
| `last_operation_type` | string | 最近一次封锁/解封操作类型（block/unblock） |
| `last_operation_status` | string | 最近一次操作结果（success/failed） |
| `last_operation_error` | text | 最近一次操作失败原因 |
| `last_operation_at` | datetime | 最近一次操作时间 |
| `retry_count` | int | 重试封锁次数 |

### 8.5 对账与调度相关参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `reconcile:latest` | Redis key | TTL 1h | 最新防火墙对账结果缓存（由对账任务 / 手动触发写入，黑名单页 stats 从缓存读取，不对接防火墙实时查询） |
| 对账 0-IP 保护 | 逻辑 | 硬编码 | 防火墙返回 0 条但 DB 有活跃条目时，单点探测区分「列表类接口异常」与「外部清空」，均保守跳过以防丢失 |
| 对账 cooling-window | 逻辑 | 硬编码 | 无需（对账只改 `status`，不改 `compliance_status`；合规状态由三层防震荡逻辑独立守护） |

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

---

## 11. 防火墙对账流程（v3.14 新增）

### 11.1 流程概述

防火墙对账用于消除「防火墙实际封锁状态」与「数据库黑名单」之间的偏差，保证三处（仪表盘 / 终端页 / 黑名单页 / 防火墙）封锁计数一致。

> **核心原则**：**防火墙实际状态是封锁状态的唯一事实源**；对账只更新 `status`（防火墙实际封锁态），**永不改动 `compliance_status`**（后者仅由合规判定逻辑 + 三层防震荡机制决定）。

### 11.2 触发时机

| 触发方式 | 周期 / 动作 |
|---------|------------|
| 后台任务 `firewall_reconciliation()` | 硬编码 **300 秒**（不读配置） |
| 手动触发 `POST /system/firewall-reconciliation` | 立即执行一次 |
| 结果缓存 | 写入 Redis `reconcile:latest`（TTL 1h），供黑名单页 stats 读取 |

### 11.3 对账节点与判断标准

按每个启用的防火墙（`type=sangfor`）独立执行，避免跨防火墙污染：

| 节点 | 触发条件 | 判断标准与动作 |
|------|---------|---------------|
| **① 补建 DB 缺失（最高优先级）** | 防火墙有封锁 IP 但 DB 无该防火墙的活跃黑名单 | `_create_db_entries_for_firewall`：补建条目；若终端命中白名单（bypass）则**跳过并告警**（防止误封白名单终端、交由合规重算安全解封） |
| **② DB 有但防火墙缺 → 重新封锁** | DB 活跃条目中的 IP 不在防火墙封锁列表 | `_reblock_on_firewall` 重新调用封堵 API |
| **③ 0-IP 保护** | 防火墙返回 0 条但 DB 有该防火墙活跃条目 | 单点探测（`_find_blacklist_entry`）区分「列表类接口异常」与「外部清空」；两种情况都**保守跳过**该防火墙，防数据丢失 |
| **④ 孤立 blocked 自愈** | 终端 `status=blocked` 但无活跃黑名单背书 | `_repair_stale_terminal_status`：重置为 `unblocked`（按 MAC 归一化匹配，NULL-MAC 回退 IP）；**不改 `compliance_status`** |

### 11.4 返回结果

- `firewall_ip_count`：所有防火墙实际封锁 IP 总数
- `db_entry_count`：DB 活跃黑名单条目数
- `created_in_db` / `reblocked_on_firewall`：本周期补建/重封数量
- `firewall_errors`：`[{tag, error}]` 结构化错误（含 0-IP 保护、查询失败等），供前端弹窗展示

---

## 12. 后台调度任务周期汇总（v3.14 新增）

后台任务全部在 `main.py` lifespan 中通过 `asyncio.create_task` 启动（见 `main.py#L763-L770`），受 Redis 分布式锁与暂停开关保护；配置类间隔经 `_get_scheduler_interval`（clamp 30–86400s）读取。

| 后台任务 | 默认周期 | 是否可配 | 配置键 / 说明 |
|---------|---------|---------|--------------|
| `scheduled_arp_collection` | 300s (5min) | ✅ | `scheduler_arp_collection_interval` |
| `scheduled_ipguard_sync` | 600s (10min) | ✅ | `scheduler_ipguard_sync_interval` |
| `scheduled_compliance_check` | 300s (5min) | ✅ | `scheduler_compliance_check_interval`（四段式见 §4.5） |
| `scheduled_auto_unblock` | 600s (10min) | ✅ | `scheduler_auto_unblock_interval` |
| `cleanup_expired_blacklist` | 300s (5min) | ✅ | `scheduler_firewall_query_interval` |
| `firewall_reconciliation` | 300s (5min) | ❌ 硬编码 | `main.py#L179` |
| `cleanup_expired_logs` | 86400s (24h) | ❌ 硬编码 | `main.py#L131`；保留天数 `audit_log_retention_days`（默认 90）可配 |
| `scheduled_backup` | 60s 轮询 + cron | ⚠️ 轮询硬编码 | `main.py#L583` poll=60s；真实执行由 `backup_config.schedule` cron 决定 |