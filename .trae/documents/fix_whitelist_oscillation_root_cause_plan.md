# 白名单终端状态震荡根因修复计划

## 根因定位

通过数据库查询确认：
- 终端 `10.8.10.28` (MAC: `A2:97:64:A5:61:7C`) 确实在白名单 `10.8.10.0/24` CIDR范围内
- 但当前状态：`compliance_status = 'non_compliant'`, `status = 'blocked'`, `wl_match_type = 'ip'`
- 矛盾点：`wl_match_type = 'ip'`说明代码**确实匹配到了白名单**，但状态却是`non_compliant`
- Blacklist历史显示：这个终端在今天反复被封锁→解封→封锁，周期大约15-25分钟

**根因：对称确认计数逻辑错误地应用到了白名单bypass判定**

代码位置：[compliance_service.py#L1836-L1886](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1836-L1886)

当前逻辑对**所有状态变化**一视同仁地使用对称确认计数（需要连续`confirm_threshold`次检查一致才变更状态）：
- bypass → non_compliant：需要连续N次检查不匹配白名单才降级
- non_compliant → bypass：需要连续N次检查匹配白名单才升级

**设计缺陷**：
- IPGuard基线数据是动态同步的，可能有延迟，需要确认计数防震荡是合理的
- **白名单是管理员静态配置的**，只要匹配到就是确定的，不需要确认计数！
- 问题在于：如果某一轮合规检查因为Redis缓存临时失效/重建、网络抖动、代码异常等原因导致`_match_whitelist_in_memory`临时返回None：
  1. 第一次不匹配 → `non_compliant_confirm_count = 1`
  2. 第二次又不匹配 → 降级到non_compliant → 触发自动封锁
  3. 第三次又匹配到白名单了 → 需要连续N次才能升级回bypass
  4. 如果升级过程中又有一次临时不匹配，计数重置 → 永远升不回去 → 震荡/卡死在non_compliant

从Blacklist历史看：
- 12:14封锁 → 17:11解封（5小时后才解封！）
- 17:21封锁 → 17:31解封
- 18:05封锁 → 18:20解封
- 18:39又封锁了（现在还没解封，wl_match_type='ip'但compliance_status='non_compliant'，就是卡在对称确认这里）

这完全解释了为什么白名单终端会在bypass/non_compliant之间来回震荡。

## 修复目标

**白名单匹配是权威判定，不需要任何对称确认计数：**
1. ✅ 只要当前检查匹配到白名单（`wl_result`不为None）→ **立即**设置`new_compliance = "bypass"`，不需要等确认计数
2. ✅ 如果终端已经是bypass状态，即使当前检查临时没匹配到白名单 → **不要立即降级**，而是进入白名单专属的冷却保护
3. ✅ 只有从bypass降级到非bypass时，才需要特殊处理：标记并告警，但不要因为单次检查失败就降级

## 修改方案

修改 [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py) 中 `recalculate_all_compliance` 方法（以及`batch_check_compliance`已经是对的，不需要confirm），主要修改对称确认计数部分：

**核心改动逻辑：**

```python
if wl_result:
    # WHITELIST MATCH IS AUTHORITATIVE - immediately bypass, no confirm count needed
    current_check_status = "bypass"
    new_wl_match_type = wl_result.get("match_type")
    wl_comments = wl_result.get("comments")
    # Immediate transition to bypass, reset all counters
    new_compliance = "bypass"
    terminal.compliant_confirm_count = 0
    terminal.non_compliant_confirm_count = 0
elif ig_match:
    # IPGuard match - still needs symmetric confirm for anti-oscillation
    current_check_status = "compliant"
    new_wl_match_type = None
    wl_comments = None
    # ... existing confirm count logic for compliant <-> non_compliant
else:
    current_check_status = "non_compliant"
    new_wl_match_type = None
    wl_comments = None
    # SPECIAL CASE: If currently bypass (whitelisted) but this check didn't match,
    # DO NOT downgrade immediately. This could be due to cache rebuild/transient error.
    # We only downgrade after MANY consecutive misses to avoid false positives.
    if old_compliance == "bypass":
        # Use a higher threshold (6 consecutive misses = ~30 minutes) before downgrading
        # a previously whitelisted terminal
        terminal.non_compliant_confirm_count += 1
        if terminal.non_compliant_confirm_count >= 6:
            new_compliance = "non_compliant"
            terminal.non_compliant_confirm_count = 0
            logger.warning(f"Terminal {ip_addr}/{mac_addr}: WHITELIST MISS {terminal.non_compliant_confirm_count} times, downgrading to non_compliant")
        else:
            # Stay bypass for now, log warning
            new_compliance = "bypass"  # keep bypass
            logger.debug(f"Terminal {ip_addr}/{mac_addr}: whitelist transient miss ({terminal.non_compliant_confirm_count}/6), holding bypass")
    else:
        # ... existing confirm count logic for non_compliant
```

关键点：
1. **匹配到白名单 → 立即bypass，不走确认计数**
2. **已经是bypass → 保护模式：需要连续6次检查（约30分钟）都匹配不到白名单才真正降级**，防止缓存临时失效导致误判
3. IPGuard基线匹配的对称确认逻辑保持不变（那是合理的防震荡）
4. IP变更宽限期逻辑保留

同样需要修改`auto_block_non_compliant`方法中的补封逻辑，确保bypass状态的终端永远不会被自动封锁。

## 修改步骤

1. 修改 `recalculate_all_compliance` 方法中的对称确认逻辑：
   - 匹配到白名单：立即设为bypass，重置计数
   - 已bypass临时不匹配：增加容错，需要6次连续不匹配才降级
   - IPGuard的对称确认逻辑保持不变

2. 检查并修改 `auto_block_non_compliant` 补封逻辑：
   - 确保`compliance_status == "bypass"`的终端永远不会被补封

3. Python语法检查

4. 验证：
   - 当前10.8.10.28应该在下次重算时立即回到bypass状态并解封
   - 白名单终端不应该再震荡
