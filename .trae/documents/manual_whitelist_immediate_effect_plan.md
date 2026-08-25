# 手动加白场景优化修复计划

## 现状问题分析

当前手动加白（`add_to_whitelist`）存在两个问题：

1. **性能问题**：添加白名单后调用`recalculate_all_compliance()`进行**全量合规重算**，但终端管理页面的手动加白只针对单个终端，全量重算浪费资源且响应慢。

2. **用户体验问题**：我们刚修复添加了10分钟自动解封冷却期，但**用户手动加白是明确的人工操作**，不应该受冷却期限制——用户加白就是希望立即解封，不能让用户等10分钟。

代码位置：[terminal_service.py#L647-L655](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L647-L655)

## 修复目标

针对**终端管理页面对单个终端执行手动加白**的场景（提供了MAC地址）：
- ✅ 不触发全量合规重算
- ✅ 立即更新该终端状态为`bypass`
- ✅ 如果终端已被封锁（`status == "blocked"`），**立即解封**，绕过冷却期
- ✅ 正确更新Blacklist记录状态
- ✅ 之后该终端不再参与自动合规计算/封锁/解封流程

对于**通用白名单添加**（仅IP/CIDR/IP范围，无MAC）：保留现有全量重算逻辑（因为可能匹配多个现有终端）。

## 需要修改的文件

### 1. `backend/app/services/compliance_service.py`
新增一个专用方法：`apply_manual_whitelist_for_terminal()`，用于处理单个终端的手动加白即时生效。

方法逻辑：
```
输入：terminal, wl_match_type, wl_comments, username
1. 失效白名单缓存（invalidate_whitelist_cache）
2. 设置 terminal.compliance_status = "bypass"
3. 设置 terminal.wl_match_type = wl_match_type
4. 设置 terminal.wl_comments = wl_comments
5. 重置防震荡计数（如果有pending状态）
6. 如果 terminal.status == "blocked"：
   a. 查询该MAC所有活跃Blacklist记录（unblocked_at IS NULL, auto_unblocked = false）
   b. 遍历每个Blacklist条目，调用_unblock_on_firewall()解封对应IP
   c. 更新所有解封成功的Blacklist条目：auto_unblocked = true, unblocked_at = now, unblocked_by = username
   d. 设置 terminal.status = "unblocked"
   e. terminal.firewall_tag = null
   f. 记录审计日志：manual_unblock_due_to_whitelist
7. 提交更改
```

关键点：**完全跳过冷却期检查**——因为这是用户明确的手动操作。

### 2. `backend/app/services/terminal_service.py`
修改`add_to_whitelist()`方法：

在创建/更新Whitelist记录后，区分两种情况：

**情况A：提供了normalized_mac（单终端加白，终端管理页面场景）**
- 按normalized_mac查询对应的Terminal记录
- 如果找到Terminal：调用新的`apply_manual_whitelist_for_terminal()`即时处理该终端
- 如果没找到Terminal（白名单先加了，终端还没被ARP采集到）：只失效缓存，不重算，等ARP采集时自动处理

**情况B：仅提供了ip_pattern（CIDR/范围，无MAC）**
- 保留现有逻辑：失效缓存 + `recalculate_all_compliance()`（因为可能匹配多个终端）

同样修改`delete_from_whitelist()`：
- 如果删除的是MAC白名单，查询该终端，设置compliance_status回"unknown"，下次合规重算自然重新判定
- 如果删除的是IP模式白名单，全量重算

### 3. 额外考虑：白名单CSV导入/备份恢复
这些批量操作场景保持全量重算不变。

## 修改步骤

1. 在ComplianceService中新增`apply_manual_whitelist_for_terminal()`方法，实现单终端即时加白+解封逻辑
2. 修改terminal_service.py中add_to_whitelist()，区分单MAC加白和IP模式加白
3. 修改terminal_service.py中delete_from_whitelist()，针对单MAC删除优化
4. 语法检查验证
5. 测试：
   - 对已封锁终端手动加白：确认立即解封
   - 对未封锁终端手动加白：确认状态立即变bypass
   - 添加CIDR白名单：确认仍全量重算
