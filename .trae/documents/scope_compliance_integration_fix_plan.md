# 合规计算 Scope 条件集成全面修复方案

## 全面评估结果

### 评估范围

对所有涉及合规计算的方法进行了完整排查，覆盖以下文件和方法：

#### compliance_service.py 方法评估

| 方法 | 行号 | Scope 集成 | 评估结果 |
|------|------|-----------|----------|
| `check_compliance()` | L102 | ✅ 已有 | 单次实时检查，白名单→scope→IPGuard |
| `batch_check_compliance()` | L152 | ✅ 已有 | 批量检查，白名单→scope→IPGuard |
| `auto_unblock_compliant()` | L633 | ✅ 已有 | 自动解封，已集成 scope 条件 |
| `auto_block_non_compliant()` | L377 | N/A | 直接查询 DB 中 `compliance_status='non_compliant'`，无需实时计算 |
| `_check_whitelist()` | L819 | N/A | 白名单匹配本身，不涉及 IPGuard 策略选择 |
| `_check_ipguard()` | L924 | N/A | 内部方法，依赖调用方传入的策略 |
| `_check_ipguard_ip_only()` | L942 | N/A | IP-only 匹配专用方法，正确 |
| **`recalculate_all_compliance()`** | **L1559** | **❌ 缺失** | **全量重算，未加载 scope 数据，始终使用 IP+MAC 匹配** |
| `_apply_compliance_result()` | L1280 | N/A | 结果写入，不涉及计算 |
| `_load_scope_cache()` | L960 | ✅ 已有 | scope 缓存加载方法 |
| `_check_in_scope()` | L994 | ✅ 已有 | scope 匹配判断方法 |

#### 定时/异步任务评估

| 任务 | 文件 | 调用方法 | Scope 集成 |
|------|------|----------|-----------|
| `scheduled_compliance_check` | main.py:248 | `batch_check_compliance()` | ✅ 已有 |
| `scheduled_auto_unblock` | main.py:442 | `auto_unblock_compliant()` | ✅ 已有 |
| `arp_collector_service` | arp_collector_service.py:354 | `batch_check_compliance()` | ✅ 已有 |

#### CRUD 触发的合规重算

| 触发场景 | 文件 | 调用方法 | Scope 集成 |
|----------|------|----------|-----------|
| 白名单新增 | terminal_service.py:652 | `recalculate_all_compliance()` | ❌ 缺失 |
| 白名单删除 | terminal_service.py:718 | `recalculate_all_compliance()` | ❌ 缺失 |
| 白名单导入 | terminal_service.py:920 | `recalculate_all_compliance()` | ❌ 缺失 |
| 白名单备份导入 | terminal_service.py:1145 | `recalculate_all_compliance()` | ❌ 缺失 |
| Scope 条件变更 | 需确认 | 触发 `recalculate_all_compliance()` | ❌ 缺失（因 recalculate 本身缺失） |

---

### 核心 Bug：`recalculate_all_compliance()` 缺少 Scope 集成

**位置**: [compliance_service.py#L1559-L1678](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1559-L1678)

#### 问题 1：未加载 scope 数据（L1583-1584）

```python
# 当前代码（第1583-1584行）：
whitelist_data = await self._load_whitelist_cache()
ipguard_data = await self._load_all_ipguard_cache()
# ❌ 缺少: scope_data = await self._load_scope_cache()
```

#### 问题 2：未根据 scope 条件选择 IPGuard 匹配策略（L1634）

```python
# 当前代码（第1634行）：
ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)
# ❌ 始终使用 IP+MAC 匹配，不考虑 scope 条件
# ✅ 应为：
# use_ip_only = self._check_in_scope(scope_data, ip_addr, mac_addr)
# if use_ip_only:
#     ig_match = self._match_ipguard_ip_only_in_memory(ipguard_data, ip_addr)
# else:
#     ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)
```

#### 问题 3：延迟确认机制导致 bypass 状态残留（L1646-1665）

```python
# 当前代码（第1646-1661行）：
if old_compliance in ("compliant", "bypass"):
    confirm_threshold = await self._get_confirm_threshold()
    terminal.non_compliant_confirm_count += 1
    if terminal.non_compliant_confirm_count >= confirm_threshold:
        new_compliance = "non_compliant"
    else:
        new_compliance = old_compliance  # ← 保持 bypass！
```

当白名单删除后，终端需要经过 `confirm_threshold` 个确认周期才会从 bypass 变为 non_compliant。在此期间终端继续显示 bypass。

---

### 修复方案

#### 变更文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/compliance_service.py` | 修改 | 修复 `recalculate_all_compliance()` 方法 |

#### 修改步骤

##### Step 1: 加载 scope 数据

在第1584行后添加 scope 数据加载：

```python
# Line 1583-1584 (existing):
whitelist_data = await self._load_whitelist_cache()
ipguard_data = await self._load_all_ipguard_cache()

# Add after Line 1584:
scope_data = await self._load_scope_cache()
```

##### Step 2: 根据 scope 条件选择 IPGuard 匹配策略

修改第1634行，根据 scope 条件选择匹配策略：

```python
# Line 1634 (current):
ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

# Replace with:
use_ip_only = self._check_in_scope(scope_data, ip_addr, mac_addr)
if use_ip_only:
    ig_match = self._match_ipguard_ip_only_in_memory(ipguard_data, ip_addr)
else:
    ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)
```

##### Step 3: 修复延迟确认逻辑（bypass 状态快速降级）

当终端在白名单检查后已不在白名单中（`wl_result` 为 None），且旧状态是 bypass 时，应跳过延迟确认，立即变为 non_compliant 或进入确认流程：

```python
# Lines 1646-1667 (current):
else:
    # IPGuard/whitelist both not matched
    if old_compliance in ("non_compliant", "unknown"):
        # Already non_compliant or new terminal → confirm immediately
        new_compliance = "non_compliant"
    else:
        # Was compliant/bypass → require confirmation cycles
        confirm_threshold = await self._get_confirm_threshold()
        terminal.non_compliant_confirm_count += 1
        if terminal.non_compliant_confirm_count >= confirm_threshold:
            new_compliance = "non_compliant"
            terminal.non_compliant_confirm_count = 0
        else:
            new_compliance = old_compliance
    new_wl_match_type = None
    wl_comments = None

# Replace with:
else:
    # IPGuard/whitelist both not matched
    if old_compliance in ("non_compliant", "unknown"):
        new_compliance = "non_compliant"
    elif old_compliance == "bypass":
        # Terminal was bypassed (in whitelist), but whitelist no longer matches
        # Fast-track: require only 1 confirmation cycle instead of full threshold
        terminal.non_compliant_confirm_count += 1
        if terminal.non_compliant_confirm_count >= 1:
            new_compliance = "non_compliant"
            terminal.non_compliant_confirm_count = 0
        else:
            new_compliance = old_compliance
    else:
        # Was compliant → require full confirmation cycles
        confirm_threshold = await self._get_confirm_threshold()
        terminal.non_compliant_confirm_count += 1
        if terminal.non_compliant_confirm_count >= confirm_threshold:
            new_compliance = "non_compliant"
            terminal.non_compliant_confirm_count = 0
        else:
            new_compliance = old_compliance
    new_wl_match_type = None
    wl_comments = None
```

##### Step 4: 确认辅助方法存在

需要确认 `_match_ipguard_ip_only_in_memory` 方法存在。已通过检查，在第780行附近。

---

### 风险评估

| 风险项 | 等级 | 说明 |
|--------|------|------|
| Scope 数据为空 | 低 | 空列表 `[]` 表示无限定范围，所有终端走默认 IP+MAC 匹配 |
| Bypass 状态快速降级 | 中 | 原来需 3-5 个确认周期，现改为 1 个周期。白名单删除后，终端将在下一次重算时立即变为 non_compliant |
| 数据一致性 | 低 | `recalculate_all_compliance` 使用分布式锁防止并发，无竞争风险 |
| 性能影响 | 极低 | 仅增加一次 scope 缓存加载（Redis GET），不影响性能 |

### 验证方式

1. Python 语法检查通过
2. 添加日志：scope 数据加载、匹配策略选择
3. 模拟场景：
   - 场景A：终端在 scope 范围内 + IP 匹配 IPGuard → compliant
   - 场景B：终端在 scope 范围内 + IP 不匹配 IPGuard → non_compliant
   - 场景C：终端不在 scope 范围内 + IP+MAC 匹配 IPGuard → compliant
   - 场景D：终端不在 scope 范围内 + IP+MAC 不匹配 → non_compliant
   - 场景E：终端在白名单中 → bypass（不受 scope 影响）
   - 场景F：终端删除白名单后 → bypass → non_compliant（1个周期）
4. Docker 构建和健康检查通过
