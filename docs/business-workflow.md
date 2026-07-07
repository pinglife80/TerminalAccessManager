# TerminalAccessManager 业务流程文档

> 文档版本：v3.6.5 | 更新日期：2026-07-07
>
> 本文档详细说明 TerminalAccessManager 的核心业务流程，包括数据采集、合规判定、封锁/解封的完整生命周期。

---

## 目录

1. [概述](#1-概述)
2. [数据采集流程](#2-数据采集流程)
3. [合规判定流程](#3-合规判定流程)
4. [自动封锁流程](#4-自动封锁流程)
5. [自动解封流程](#5-自动解封流程)
6. [手动封锁/解封流程](#6-手动封锁解封流程)
7. [黑名单管理流程](#7-黑名单管理流程)
8. [状态机流转图](#8-状态机流转图)
9. [关键参数说明](#9-关键参数说明)

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

### 3.4 执行步骤

```python
def _match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr):
    # 按MAC、IP、IP范围顺序匹配白名单
    # 返回匹配结果或None

def _match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr):
    # 在IPGuard数据中查找终端
    # 返回匹配结果或None

# 判定逻辑
if wl_result:
    new_compliance = "bypass"
elif ig_match:
    new_compliance = "compliant"
else:
    new_compliance = "non_compliant"
```

### 3.5 触发时机

| 触发场景 | 说明 |
|---------|------|
| ARP数据采集完成 | 新采集的终端自动触发合规检查 |
| 白名单变更 | 添加/删除白名单条目后触发 |
| IPGuard同步完成 | 基线数据更新后触发 |
| 手动触发 | 通过API手动触发合规重算 |

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
```

### 4.4 关键参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `arp_source_tag` | string | ARP数据源标签 |
| `block_time` | string | 封锁时长（默认30d） |
| `firewall_tag` | string | 防火墙标签 |
| `is_auto_blocked` | boolean | 是否自动封锁 |
| `expires_at` | datetime | 封锁过期时间 |

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
terminal.firewall_tag = None

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

## 6. 手动封锁/解封流程

### 6.1 手动封锁流程

```
用户请求 → 验证权限 → 调用深信服API封锁 → 更新终端状态 → 创建黑名单记录 → 记录审计日志 → 发送通知事件
```

#### 关键代码位置

`terminal_service.py` → `block_ip()`

### 6.2 手动解封流程

```
用户请求 → 验证权限 → 调用深信服API解封 → 更新终端状态 → 更新黑名单记录（软删除） → 记录审计日志 → 发送通知事件
```

#### 关键代码位置

`terminal_service.py` → `unblock_ip()` / `delete_from_blacklist()`

### 6.3 与自动流程的区别

| 对比项 | 自动流程 | 手动流程 |
|--------|---------|---------|
| 触发方式 | 合规判定自动触发 | 用户手动操作 |
| `is_auto_blocked` | True | False |
| `blocked_by` | "system" | 用户名 |
| `unblocked_by` | "system" | 用户名 |

---

## 7. 黑名单管理流程

### 7.1 数据模型

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

### 7.2 黑名单状态

| 状态 | 条件 | 说明 |
|------|------|------|
| 活跃 | `unblocked_at is None` | 终端仍被封锁 |
| 已解封 | `unblocked_at is not None` | 终端已解封，记录保留用于审计 |

### 7.3 清理流程

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

## 8. 状态机流转图

### 8.1 终端状态机

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
                       手动解封         合规变更          封锁过期
                              │              │              │
                              └──────────────┴──────────────┘
                                             ▼
                                    ┌─────────────┐
                                    │  unblocked  │
                                    │   (正常)    │
                                    └─────────────┘
```

### 8.2 合规状态流转

| 当前状态 | 触发条件 | 新状态 |
|---------|---------|--------|
| unknown | 白名单匹配 | bypass |
| unknown | IPGuard匹配 | compliant |
| unknown | 无匹配 | non_compliant |
| non_compliant | 白名单添加 | bypass |
| non_compliant | IPGuard同步 | compliant |
| compliant | IPGuard移除 | non_compliant |
| bypass | 白名单移除 | compliant/non_compliant |

---

## 9. 关键参数说明

### 9.1 终端相关参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 防火墙封锁状态：blocked/unblocked |
| `compliance_status` | string | 合规状态：compliant/bypass/non_compliant/unknown |
| `source_tag` | string | ARP数据源标签 |
| `firewall_tag` | string | 绑定的防火墙标签 |
| `wl_match_type` | string | 白名单匹配类型：mac/ip/both |

### 9.2 黑名单相关参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `is_auto_blocked` | boolean | 是否由系统自动封锁 |
| `auto_unblocked` | boolean | 是否由系统自动解封 |
| `unblocked_at` | datetime | 解封时间（软删除标识） |
| `unblocked_by` | string | 解封操作人 |
| `expires_at` | datetime | 封锁过期时间 |

### 9.3 合规判定相关参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `block_threshold` | int | 单次自动封锁阈值（默认50） |
| `block_time` | string | 封锁时长配置（默认30d） |

---

## 10. 事件触发点汇总

### 10.1 安全事件

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

### 10.2 终端事件

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| TERMINAL_BLOCKED | 终端被封锁 | terminal_service.py, compliance_service.py |
| TERMINAL_UNBLOCKED | 终端被解封 | terminal_service.py, compliance_service.py |
| TERMINAL_COMPLIANT | 终端变为合规 | compliance_service.py |
| TERMINAL_NON_COMPLIANT | 终端变为不合规 | compliance_service.py |
| TERMINAL_ONLINE | 新终端上线 | arp_collector_service.py |

### 10.3 系统事件

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| FIREWALL_CONNECTION_LOST | 防火墙连接断开 | compliance_service.py |
| FIREWALL_CONNECTION_RESTORED | 防火墙连接恢复 | data_source_service.py |
| BACKUP_COMPLETED | 备份完成 | backup_service.py |
| BACKUP_FAILED | 备份失败 | backup_service.py |

### 10.4 合规告警

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| AUTO_BLOCK_TRIGGERED | 自动封锁触发 | compliance_service.py |
| AUTO_UNBLOCK_TRIGGERED | 自动解封触发 | compliance_service.py |
| COMPLIANCE_RATE_LOW | 合规率低 | main.py |
| BLOCK_THRESHOLD_EXCEEDED | 封锁阈值超限 | compliance_service.py |
| POLICY_VIOLATION | 策略违规 | compliance_service.py |

### 10.5 管理事件

| 事件类型 | 触发场景 | 触发位置 |
|---------|---------|---------|
| CONFIG_CHANGED | 配置变更 | settings.py |
| ROLE_CHANGED | 角色变更 | roles.py |
| PERMISSION_CHANGED | 权限变更 | roles.py |