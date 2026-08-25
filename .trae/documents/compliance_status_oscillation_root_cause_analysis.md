# 合规状态频繁震荡根因分析与修复方案

## 问题现象

终端在 `compliant`/`bypass` → `non_compliant` → `blocked` → `unblocked` → `compliant`/`bypass` 之间快速循环切换，导致防火墙反复封禁/解封，严重影响网络可用性。

---

## 根因分析（按严重程度排序）

### 🔴 根因 1：bypass → non_compliant 降级阈值硬编码为 1（立即切换）

**文件**：[compliance_service.py:1693-1697](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1693-L1697)

```python
elif old_compliance == "bypass":
    terminal.non_compliant_confirm_count += 1
    if terminal.non_compliant_confirm_count >= 1:  # ❌ 硬编码为1，立即降级！
        new_compliance = "non_compliant"
        terminal.non_compliant_confirm_count = 0
```

**问题**：从白名单 bypass 状态降级到 non_compliant 时，只需要 1 次检查不匹配就立即封禁，而从 compliant 降级使用配置的 `compliance_confirm_threshold`（默认 2 次）。白名单匹配一旦出现瞬时不一致（缓存更新时序、短暂网络波动），立即触发封禁。

---

### 🔴 根因 2：auto_unblock 直接强制设置合规状态，绕过确认计数机制

**文件**：[compliance_service.py:766-770](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L766-L770)

```python
for record in mac_records:
    record.status = "unblocked"
    record.firewall_tag = None
    record.compliance_status = "bypass" if wl_match else "compliant"  # ❌ 直接强制设置！
```

**问题**：`auto_unblock_compliant()` 在解封时，**绕过了** `recalculate_all_compliance` 中的确认计数逻辑，直接将 `compliance_status` 设置为 `bypass` 或 `compliant`。这导致：
1. 解封后下一轮合规重计算时，新状态是 `compliant`/`bypass`
2. 如果此时 IPGuard 数据恰好有同步延迟或瞬态不匹配
3. 从 `bypass` → `non_compliant` 只需 1 次（根因1），立即重新封禁
4. 封禁后下一轮 auto_unblock 又发现匹配，再次解封...形成无限循环

---

### 🔴 根因 3：IP 变更重置为 unknown 后，unknown → non_compliant 无确认阈值

**文件**：[compliance_service.py:1691-1692](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1691-L1692)

```python
if old_compliance in ("non_compliant", "unknown"):
    new_compliance = "non_compliant"  # ❌ unknown 状态下第一次不匹配就直接非合规！
```

**联动问题**：
- ARP 采集发现 IP 变化（DHCP 续租、网卡重连）时，将 `compliance_status` 重置为 `unknown`
- [arp_collector_service.py:317-318](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L317-L318)
- 下一轮合规检查时，unknown 状态第一次检查不匹配就直接 non_compliant，无需确认
- 如果 IPGuard 基线中该 MAC-IP 对尚未同步（IPGuard 同步周期默认 10 分钟，ARP 采集 5 分钟），就会误封禁
- 等 IPGuard 同步完成后发现匹配，auto_unblock 解封，又回到 compliant，形成震荡

---

### 🟠 根因 4：main.py 中 scheduled_compliance_check 的 result_lookup 仍用 IP 作为 key（MAC 唯一化改造后未更新）

**文件**：[main.py:286-305](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L286-L305)

```python
result_lookup = {}
for item in result.details.get("bypass", []):
    result_lookup[item.get("ip_address")] = { ... }  # ❌ key 是 IP 而不是 normalized MAC！
```

**问题**：
- 在 MAC 唯一化改造后，`arp_collector_service.py` 中已经改为用 MAC 作为 result_lookup 的 key，但 `main.py` 的 `scheduled_compliance_check` 任务中**没有同步更新**
- 双网卡场景：同一 IP 可能先后对应不同 MAC，result_lookup[ip] 会覆盖，导致结果应用错误
- 更严重的是：应用结果时第 309 行 `r = result_lookup.get(entry.ip_address)`，当同一 MAC 换新 IP 后，用新 IP 查不到旧 IP 的结果，静默失败，状态保持 unknown 或错误状态

---

### 🟠 根因 5：IPGuard 同步后立即全量重算，与 ARP 采集存在时序竞争

**文件**：[main.py:225-231](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L225-L231)

```python
await service.sync_ipguard_data(baseline.tag)
# 立即触发全量合规重计算！
result = await service.recalculate_all_compliance()
```

**时序问题**：
- 默认调度间隔：ARP 采集 300s，IPGuard 同步 600s，合规检查 300s，自动解封 600s
- IPGuard 同步完成后**立即**触发全量重算，但此时最新的 ARP 数据可能还没采集到（两个任务并行启动，时序不确定）
- 导致：IPGuard 中有新的 IP-MAC 映射，但 Terminal 表中还是旧 IP → 不匹配 → non_compliant → 封禁
- 5 分钟后 ARP 采集更新了新 IP → 匹配 → compliant → 解封
- 下一轮 IPGuard 同步又触发重算...循环

---

### 🟠 根因 6：封禁/解封操作无冷却期/迟滞保护

**问题**：
- 状态一旦切换达到阈值，立即同步调用防火墙 API 执行封禁/解封
- 没有最小操作间隔保护（比如：解封后 N 分钟内不再因为同一终端的状态波动重新封禁）
- 没有类似网络协议中"hold-down"（抑制）机制
- 防火墙 API 调用失败时的重试逻辑（main.py:334-400）也没有冷却期

---

### 🟡 根因 7：auto_unblock 黑名单分组 key 使用原始 (ip, mac) 而非 normalized MAC

**文件**：[compliance_service.py:673-675](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L673-L675)

```python
for entry in auto_blocked_entries:
    key = (entry.ip_address or "", entry.mac_address or "")  # ❌ 未 normalized
    entry_groups[key].append(entry)
```

**问题**：
- 黑名单历史条目可能保存了不同格式的 MAC（冒号分隔、横杠分隔、小写/大写）
- 导致同一物理终端的多个防火墙封禁条目被拆分到不同的 key 组中
- 部分防火墙已解封，部分未解封，Terminal 状态与防火墙实际状态不一致
- 后续重试逻辑可能重复处理

---

### 🟡 根因 8：confirm_count 反向重置过于激进

**问题**：
- 只要任何一次检查匹配白名单或 IPGuard，`non_compliant_confirm_count` 立即重置为 0
- 没有"持续 N 次匹配才确认合规"的对称机制
- 这导致从 non_compliant 回到 compliant 也只需要 1 次匹配，状态抖动敏感

---

## 震荡链路示例（典型场景）

```
T0:     终端 MAC1 因 DHCP 换 IP: IP_old → IP_new
T0+5m:  ARP 采集发现 IP 变化 → compliance_status 重置为 unknown
T0+5m:  合规检查 unknown 状态 → IPGuard 中 MAC1 还对应 IP_old → 不匹配 → non_compliant（无阈值，立即生效）
T0+5m:  合规检查发现 non_compliant 且未封禁 → 调用防火墙 API 封禁 IP_new
T0+10m: IPGuard 同步完成，缓存中 MAC1 对应 IP_new
T0+10m: IPGuard 同步后立即触发 recalculate_all_compliance → MAC1+IP_new 匹配 → compliant
T0+10m: _apply_compliance_result 发现 blocked→compliant → 调用防火墙 API 解封 IP_new
T0+15m: 下一轮合规检查，如果此时 IPGuard 缓存恰好失效或同步中，瞬态不匹配
T0+15m: bypass/compliant → non_compliant 只需 1 次确认（根因1）→ 再次封禁
...循环往复
```

---

## 修复方案

### Phase 1: 紧急修复（阻断震荡链路）

#### Fix 1: 统一所有降级路径的确认阈值，bypass 降级不再硬编码为 1
- 文件：`compliance_service.py`
- 修改点：将 bypass 降级路径改为使用配置的 `compliance_confirm_threshold`
- 新增 `bypass` 状态使用相同的确认阈值，不再特权

#### Fix 2: auto_unblock 不要直接设置 compliance_status，仅更新防火墙状态
- 文件：`compliance_service.py`
- 修改点：`auto_unblock_compliant` 方法中，解封成功后**不要直接修改** `record.compliance_status`
- 改为：只更新 `record.status = "unblocked"` 和 `record.firewall_tag = None`
- 合规状态由下一轮 `recalculate_all_compliance` 或 `scheduled_compliance_check` 按照确认计数逻辑正常更新
- 这是最关键的修复：解封和状态变更解耦

#### Fix 3: unknown 状态首次非合规也需要确认计数
- 文件：`compliance_service.py`
- 修改点：`old_compliance in ("non_compliant", "unknown")` 分支中，unknown 也需要走 confirm_threshold 逻辑
- 新增终端/IP 变更后的 unknown 状态，第一次不匹配不立即封禁

#### Fix 4: 修复 main.py 中 scheduled_compliance_check 的 result_lookup key 为 MAC
- 文件：`main.py`
- 修改点：将 result_lookup 的 key 从 `ip_address` 改为 normalized MAC，与 arp_collector_service 保持一致

### Phase 2: 稳定性增强（消除时序竞争）

#### Fix 5: IPGuard 同步后不要立即全量重算，延迟到下一轮 ARP 采集后
- 文件：`main.py`
- 修改点：移除 IPGuard 同步后立即调用 `recalculate_all_compliance` 的逻辑
- IPGuard 缓存更新后，下一次定时合规检查/ARP采集后合规检查自然会使用新数据
- 避免在 ARP 数据尚未更新时用新基线检查旧状态

#### Fix 6: 增加封禁/解封冷却机制（hold-down timer）
- 在 Terminal 模型中新增 `last_block_change_at` 字段
- 封禁后 N 分钟（可配置，默认 10 分钟）内不自动解封
- 解封后 N 分钟内不自动重新封禁
- 防止状态在防火墙 API 调用层面频繁震荡

#### Fix 7: auto_unblock 分组 key 使用 normalized MAC
- 文件：`compliance_service.py`
- 修改点：分组 key 从 `(ip, raw_mac)` 改为 `normalized_mac`
- 同一终端的多个防火墙条目（多防火墙绑定）正确分组，原子处理

### Phase 3: 健壮性提升（可选优化）

#### Fix 8: 对称的 confirm 机制（合规也需要确认）
- 新增 `compliant_confirm_count`，从 non_compliant 回到 compliant/bypass 也需要连续 N 次匹配
- 防止瞬态匹配触发解封后又立即不匹配

#### Fix 9: 增加状态变更审计详细日志
- 每次 confirm_count 增减都记录日志
- 记录触发封禁/解封的具体原因（白名单匹配/IPGuard匹配/阈值达到）

#### Fix 10: IP 变更时不立即重置为 unknown，除非持续多轮未匹配
- DHCP 续租常见场景：IP 短时间内切换后可能又切回
- IP 变更后先保持原状态 N 个采集周期，如果持续多轮新IP不匹配再重置

---

## 修改文件清单

| 文件 | 修改类型 |
|------|---------|
| `backend/app/services/compliance_service.py` | 修复确认阈值、auto_unblock 逻辑、unknown 处理、分组 key |
| `backend/app/main.py` | 修复 result_lookup key、移除 IPGuard 同步后立即重算 |
| `backend/app/models/terminal.py` | 新增 `last_block_change_at` 字段（Phase 2） |
| `backend/alembic/versions/034_terminal_block_cooldown.py` | 新迁移脚本（Phase 2） |

---

## 风险评估

| 风险 | 缓解措施 |
|------|---------|
| 确认阈值变大导致非合规终端封禁延迟 | 默认阈值保持为 2 次（约 10 分钟），可配置 |
| 冷却期延长导致真正合规的终端解封变慢 | 冷却期默认 10 分钟，仅对自动操作生效，手动操作不受限 |
| 移除立即重算导致 IPGuard 更新后生效变慢 | 合规检查默认 5 分钟一次，最多延迟 5 分钟，可接受 |

---

## 验证方案

修复后验证：
1. 检查审计日志确认：同一终端在 1 小时内合规状态变更不超过 1 次
2. 确认从 non_compliant 到 compliant/bypass 需要连续匹配达到阈值
3. 确认 auto_unblock 后不再立即设置 compliance_status，而是等待下一轮合规检查
4. 双网卡/DHCP换IP场景下不再出现 5 分钟级别的封禁/解封循环
5. 防火墙封禁/解封 API 调用频率显著下降
