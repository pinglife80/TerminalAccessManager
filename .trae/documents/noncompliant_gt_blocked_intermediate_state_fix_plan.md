# 非合规数 > 封锁数 的中间态问题修复计划

## 一、问题与根因

**现象**：终端页非合规统计（96）大于 Dashboard/黑名单/防火墙的封锁统计（93/95）。

**取证结果（2026-08-21 14:30）**：
- non_compliant 终端 = 96，其中 93 个已封锁，**3 个处于 unblocked 状态**：
  - 10.8.11.199（38D57A44694B）、10.8.17.118（744CA1E0118F）、10.8.19.193（3CA6F6007226），均为 yp 源
- 这 3 个终端 14:26 刚被 `auto_unblock_compliant` 从防火墙解封，但 `compliance_status` 仍是 `non_compliant`
- 3 个终端当前都在 IPGuard 基线缓存中（1189 条里精确匹配到 IP+MAC）

**根因（代码实锤）**：[compliance_service.py auto_unblock_compliant L827-842](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L827-L842)

auto_unblock_compliant 解封后对 compliance_status 的处理不对称：
- **白名单匹配**：直接设 `compliance_status = "bypass"`（修复2已处理）✅
- **IPGuard 匹配**：`pass`——注释说"交给下次合规检查用确认计数机制"，**导致终端进入"已解封但仍是 non_compliant"的中间态** ❌

这个中间态造成三个后果：
1. **统计不一致**：非合规数（含中间态）> 封锁数，即用户看到的问题
2. **震荡隐患**：retry-block 只查 `non_compliant + unblocked`，中间态终端会在下轮被重新封锁（冷却期过后），形成封锁-解封循环
3. **确认计数永远追不上**：解封时清零 `non_compliant_confirm_count`，而全量重算需要连续 2 次 compliant 才把状态改为 compliant（当前 3 终端 compliant_confirm_count=1，还需 1 轮），期间窗口一直敞着

**本质**：auto_unblock 既然已经以 ig_match 为依据执行了解封，却不承认这个判定结果，属于判定与状态更新脱节。与白名单分支的处理原则（解封即更新状态）不一致。

## 二、修复方案

### 修改1（唯一代码修改）：IPGuard 匹配解封时同步设 compliance_status=compliant
文件：`backend/app/services/compliance_service.py` `auto_unblock_compliant` L838-842

将 IPGuard-only 匹配分支的 `pass` 改为：
```python
else:
    # IPGuard match: unblock was executed on the basis of this compliance
    # determination, so update compliance_status synchronously. Leaving it
    # as non_compliant creates an intermediate state that (1) inflates the
    # non-compliant count above the blocked count, and (2) gets re-blocked
    # by retry-block after cooldown, causing oscillation.
    terminal_record.compliance_status = "compliant"
    terminal_record.compliant_confirm_count = 0
    terminal_record.non_compliant_confirm_count = 0
    logger.info(
        f"Auto-unblock: set compliance_status=compliant directly for "
        f"{current_ip}/{current_mac} (IPGuard match)"
    )
```

与白名单分支（设 bypass）完全对称：解封动作本身已是权威判定，状态必须同步。

### 不改动的部分
- 确认计数机制在全量重算路径中保持不变（防震荡仍有效）
- 若终端后续真的变为非合规，重算会按确认计数重新封锁，属正常流程
- 2 条 NULL-MAC 对账条目继续保留（防火墙真实封锁映射）

## 三、验证步骤
1. `python3 -m py_compile backend/app/services/compliance_service.py`
2. `manage.sh update` 部署，部署后容器指纹验证：
   `docker exec tam_backend grep -c "set compliance_status=compliant directly" /app/app/services/compliance_service.py` ≥1
3. 观察下一轮调度周期日志：出现 `set compliance_status=compliant directly for 10.8.11.199/10.8.17.118/10.8.19.193`
4. 数据库验证：`SELECT count(*) FROM terminals WHERE compliance_status='non_compliant' AND status!='blocked'` → 应为 0
5. 口径一致性：非合规数 == blocked 终端数；黑名单活跃数 == 非合规数 + 2（NULL-MAC）；与防火墙实际数一致
6. 观察 2 个调度周期无新的这 3 个终端封锁记录

## 四、风险与对策
- **风险**：IPGuard 数据短暂错误导致误判 compliant。对策：IPGuard 基线由管理员维护同步，且若下轮终端不再匹配 IPGuard，重算确认计数会重新判定并封锁，自愈闭环完整
- **风险**：与对称确认计数机制理念冲突。对策：确认计数用于"状态漂移防护"，而 auto_unblock 是已执行的动作——动作与状态必须一致，这与白名单分支的处理原则统一
