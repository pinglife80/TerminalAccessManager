# 非合规终端必须被封锁：状态不变量修复计划

## 一、问题再定义

用户指出：终端管理页的「非合规数」=「已封锁的非合规终端」+「未封锁的非合规终端」。既然被封锁的终端中也可能包含合规/bypass/unknown 状态，那么**非合规数 > 封锁数**就意味着系统里存在「非合规但未封锁」的终端。这个状态从业务逻辑上不应该出现，更不应该被持久展示。

**核心不变量**：
```
compliance_status = 'non_compliant'  ⟹  status = 'blocked'
```

## 二、当前为什么会被打破

已定位到三个产生「non_compliant + unblocked」中间态的代码路径：

### 路径1：冷却期导致状态与动作分离（主因）
文件：`backend/app/services/compliance_service.py` `_apply_compliance_result` L1608-1642
- 终端刚被 auto-unblock 后 10 分钟内，如果重新判定为 non_compliant，代码会把 `compliance_status` 更新为 `non_compliant`，但因冷却期跳过 `block` 动作
- 结果：`compliance_status='non_compliant'` 但 `status='unblocked'`

### 路径2：封锁完全失败但状态已更新
文件：`backend/app/services/compliance_service.py` `_apply_compliance_result` L1644-1736
- `compliance_status` 已在 L1460 被设为 `non_compliant`，但如果所有防火墙 `_block_on_firewall` 都失败，则 `terminal.status` 保持 `unblocked`

### 路径3：auto_block_non_compliant 全部失败
文件：`backend/app/services/compliance_service.py` `auto_block_non_compliant` L609-610
- 该函数只查找 `compliance_status='non_compliant' AND status!='blocked'` 的终端。若所有防火墙封锁失败，terminal 保持 `non_compliant + unblocked`

## 三、修复方案

### 修复1：冷却期应阻止状态降级，而不是阻止封锁动作
文件：`backend/app/services/compliance_service.py` `_apply_compliance_result` L1459-1460 附近

修改逻辑：
1. 在把 `terminal.compliance_status` 设为 `non_compliant` 之前，先检查冷却期（最近 10 分钟是否刚被 auto-unblock）
2. 如果处于冷却期，**保持原 compliance_status 不变**（不降级为 non_compliant），直接 return
3. 冷却期结束后下一轮重算，若仍为非合规，再正常降级并同步封锁

这样防震荡机制仍然有效，但不会出现「已降级未封锁」的中间态。

### 修复2：non_compliant 降级后封锁失败必须回滚状态
文件：`backend/app/services/compliance_service.py` `_apply_compliance_result` L1608-1736

修改逻辑：
1. 方法开头保存 `old_compliance = terminal.compliance_status`
2. 当 `new_compliance == 'non_compliant'` 时，在尝试 block 之后：
   - 如果因冷却期跳过（修复1已处理，此处为兜底）或 block 完全失败
   - 则将 `terminal.compliance_status` 回滚为 `old_compliance`
   - 记录 warning 日志说明「因无法执行封锁，保持原合规状态」

保证：只有成功完成封锁，才允许 compliance_status 停留在 non_compliant。

### 修复3：auto_block_non_compliant 失败时回滚合规状态
文件：`backend/app/services/compliance_service.py` `auto_block_non_compliant` L480-610

修改逻辑：
1. 遍历 `non_compliant_entries` 之前，为每个 entry 记录调用前的 `compliance_status`（当前都是 non_compliant，但保留扩展性）
2. 处理完所有 entry 后，对 `blocked == 0` 且 `skipped > 0` 的 entry（即全部失败的），将其 `compliance_status` 回滚为 `"unknown"`
3. 这样它们不会被 terminal 页统计为非合规，下一轮 scheduled check 会重新 batch_check 并再次尝试封锁

### 修复4：retry-block 对已有中间态强制立即封锁（兜底）
文件：`backend/app/services/compliance_service.py` / `backend/app/main.py` retry-block 段

修改逻辑：
1. retry-block 查询 `compliance_status='non_compliant' AND status='unblocked'` 的终端
2. 对这些终端执行封锁时**忽略冷却期**（因为它们已经是非合规状态，不是新转换）
3. 这作为历史遗留/手动操作产生的中间态的最终兜底手段

### 修复5（前端最终防线）：非合规统计只统计已被封锁的
文件：`backend/app/services/terminal_service.py` `get_stats()`

修改逻辑：
- `non_compliant` 字段从 `compliance_status='non_compliant'` 计数改为 `compliance_status='non_compliant' AND status='blocked'` 计数
- 这样即使后端出现短暂中间态，前端统计也永远满足「非合规数 ≤ 封锁数」
- 这是与修复1-4配合的防御性措施，不改变状态机语义

## 四、不改动的部分

- 白名单解封直接设 bypass（已修复）
- IPGuard 解封直接设 compliant（已修复）
- 确认计数机制保持不变
- 冷却期时长（10分钟）保持不变
- 对账补建的 NULL-MAC 黑名单条目继续保留

## 五、验证步骤

1. `python3 -m py_compile backend/app/services/compliance_service.py backend/app/services/terminal_service.py`
2. `manage.sh update` 部署，容器指纹验证：
   - `docker exec tam_backend grep -c "rollback compliance_status" /app/app/services/compliance_service.py` ≥1
   - `docker exec tam_backend grep -c "cooldown.*skip.*downgrade" /app/app/services/compliance_service.py` ≥1
3. 数据库验证：`SELECT count(*) FROM terminals WHERE compliance_status='non_compliant' AND status!='blocked'` → 0
4. 模拟测试：构造一个刚 auto-unblock 的终端，下一轮重算时观察日志确认「Cooldown: skipping compliance downgrade」且 compliance_status 不变
5. 观察 2 个调度周期，确认无非合规未封锁终端新增
6. 页面验证：终端页非合规数 ≤ Dashboard 封锁数 ≤ 黑名单活跃数

## 六、风险与对策

- **风险**：防火墙 API 故障时，non_compliant 终端不被标记为非合规，可能漏掉告警。对策：系统会每 5 分钟重试；API 恢复后立即正确判定。这是「状态自洽」优先于「立即告警」的取舍。
- **风险**：冷却期内 actual non_compliant 终端显示为 compliant，管理员误以为没问题。对策：日志明确记录「Cooldown: skipping compliance downgrade」；冷却期仅 10 分钟，结束后立即纠正。
