# 合规业务逻辑修复计划

> 文档版本：v1.0  更新日期：2026-07-14

## 问题概述

用户报告了两个严重的业务逻辑问题：

### 问题1：手动封锁功能违反业务闭环设计
- **现象**：终端管理中存在手动封锁操作选项
- **影响**：打破系统合规自动检测的业务逻辑闭环，导致状态不一致

### 问题2：白名单IP合规状态错误
- **现象**：IP 10.8.30.130 和 10.8.31.90 在白名单范围内，但状态显示为 Unblocked、non_compliant
- **同时**：仍显示"加白"和"从黑名单移除"操作选项

---

## 根因分析

### 问题1根因：手动封锁API和前端操作逻辑存在

**后端**：
- `backend/app/api/v1/endpoints/terminals.py` 定义了 `POST /terminals/block/{ip_address}` 端点（L157-181）
- `backend/app/services/terminal_service.py` 实现了 `block_ip` 方法（L472+）

**前端**：
- `frontend/src/pages/Terminals.tsx` 中 `getTerminalActions` 函数（L43-87）允许对 `non_compliant` 且 `unblocked` 的终端执行手动封锁（L73-75）

**设计缺陷**：系统设计原则是合规检测自动执行封锁/解封，手动操作会破坏业务闭环。

---

### 问题2根因：MAC地址规范化不一致导致白名单匹配失败

这是一个**严重的代码逻辑缺陷**，涉及以下文件：

#### 1. 白名单存储时的MAC规范化（正确）

`backend/app/services/terminal_service.py` 的 `add_to_whitelist` 方法（L776-777）：
```python
if mac_address:
    normalized_mac = self._normalize_mac(mac_address)  # 移除所有分隔符，大写
```

存储到数据库的 `mac_address` 字段是**完全规范化的**（如 `AABBCCDDEEFF`）。

#### 2. 白名单匹配时的MAC处理（错误）

`backend/app/services/compliance_service.py` 的 `_match_whitelist_in_memory` 方法（L795, L807）：
```python
# 只做了部分转换：冒号 → 连字符
entry["mac_address"].upper() == mac_address.upper().replace(":", "-")
```

**问题**：终端MAC地址格式为 `AA:BB:CC:DD:EE:FF`，经过 `replace(":", "-")` 后变成 `AA-BB-CC-DD-EE-FF`，但数据库中存储的是 `AABBCCDDEEFF`，**两者无法匹配**！

#### 3. 前端操作逻辑错误

`frontend/src/pages/Terminals.tsx` 中：
- L73-75：对 `non_compliant` 且 `unblocked` 的终端显示"封锁"按钮
- L70-71：对 `non_compliant` 且 `unblocked` 且在黑名单中的终端显示"从黑名单移除"按钮

由于白名单匹配失败，本应是 `bypass` 状态的终端被错误标记为 `non_compliant`，导致显示了不应该出现的操作按钮。

---

## 修复方案

### 方案1：移除手动封锁功能

**后端修改**：
1. 删除 `backend/app/api/v1/endpoints/terminals.py` 中的 `POST /terminals/block/{ip_address}` 端点
2. 保留 `POST /terminals/unblock/{ip_address}` 端点（管理员紧急解封场景仍需要）

**前端修改**：
1. 修改 `frontend/src/pages/Terminals.tsx` 中 `getTerminalActions` 函数，移除 `canBlock: true` 的情况
2. 删除相关的封锁确认对话框和处理函数

---

### 方案2：修复MAC地址规范化匹配逻辑

**后端修改**：

修改 `backend/app/services/compliance_service.py` 的 `_match_whitelist_in_memory` 方法：

将：
```python
entry["mac_address"].upper() == mac_address.upper().replace(":", "-")
```

改为：
```python
# 使用与存储时相同的规范化逻辑
normalized_mac = mac_address.upper().replace(":", "").replace("-", "").replace(".", "")
entry["mac_address"].upper() == normalized_mac
```

或者引入 `_normalize_mac` 工具函数。

---

### 方案3：前端操作逻辑修正

修复 `frontend/src/pages/Terminals.tsx` 中 `getTerminalActions` 函数的逻辑：
- 对于 `bypass` 状态的终端，不应显示"加白"按钮（已在白名单中）
- 对于 `bypass` 状态的终端，不应显示"从黑名单移除"按钮（白名单终端不应在黑名单中）
- 移除所有手动封锁选项

---

## 修改文件清单

| 文件路径 | 修改内容 |
|---------|---------|
| `backend/app/api/v1/endpoints/terminals.py` | 删除手动封锁 API 端点 |
| `backend/app/services/compliance_service.py` | 修复 MAC 地址规范化匹配逻辑 |
| `frontend/src/pages/Terminals.tsx` | 移除手动封锁操作，修正白名单终端操作逻辑 |

---

## 验证方案

### 问题1验证
1. 确认 `POST /terminals/block/{ip_address}` 端点已不存在
2. 确认前端终端管理页面中不再显示"封锁"按钮

### 问题2验证
1. 添加白名单条目 `10.8.30.0/24`（CIDR 类型）
2. 验证 IP 10.8.30.130 的合规状态变为 `bypass`
3. 验证 IP 10.8.31.90（在 10.8.30.0/23 范围内）的合规状态变为 `bypass`
4. 验证这些终端不再显示"加白"和"从黑名单移除"操作按钮

---

## 风险评估

| 风险 | 等级 | 缓解措施 |
|-----|------|---------|
| 移除手动封锁影响紧急操作 | 低 | 保留手动解封功能作为应急出口 |
| MAC匹配修复可能影响现有白名单 | 低 | 使用与存储时相同的规范化逻辑，向后兼容 |
| 前端UI变更需要回归测试 | 中 | 验证所有终端状态下的操作按钮显示正确 |
