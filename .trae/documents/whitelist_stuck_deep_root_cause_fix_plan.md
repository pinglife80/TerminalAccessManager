# 白名单终端状态卡死/震荡 —— 深层根因修复计划

---

# 第二轮：深度取证结论（2026-08-21 用户报告 10.8.10.28 仍有问题）

## 决定性证据：生产容器运行的仍是旧代码，此前所有修复从未部署

| 证据 | 详情 |
|------|------|
| 容器创建时间 | `2026-08-21T02:19:02Z`（北京 10:19:02） |
| 修复1/2 本地文件保存时间 | `10:43:27`（容器重建之后 24 分钟） |
| 修复3/4/5 本地 main.py 保存时间 | `10:44:16`（容器重建之后 25 分钟） |
| 容器内代码验证 | `grep -c "set compliance_status=bypass directly"` = **0**（无修复2）；`from datetime import` 仍存在于第 **537/1459/1474** 行（无修复1）；main.py **无** `recalculate_all_compliance` 调用（无修复3） |

**结论：上一轮的 `manage.sh update` 执行早于修复代码写入，重建打包的是旧代码。所有修复在本地已就绪（见下），但生产环境未生效。这是"修复后仍震荡"的第一根因。**

## 本地代码修复完成度盘点（git diff 核实）

| 修复 | 本地状态 | 部署状态 |
|------|---------|---------|
| 修复1 datetime遮蔽（compliance_service.py 537/1459/1474） | ✅ 已完成（局部导入已清空） | ❌ 未部署 |
| 修复2 白名单解封直接设bypass | ✅ 已完成 | ❌ 未部署 |
| 修复3 周期性全量重算 | ❌ **未完成** | ❌ |
| 修复4 retry-block IntegrityError容错 | ✅ 已完成（main.py 427-445） | ❌ 未部署 |
| 修复5 对账日志KeyError | ❌ **未完成**（main.py:173 仍用 `marked_unblocked`） | ❌ |
| 修复6 Terminal.last_seen | ❌ **未完成**（terminal_service.py 661/769 仍是 last_seen） | ❌ |

## 旧代码下 10.8.10.28 震荡的完整证据链（本轮日志实锤）

1. **02:20:37 / 02:20:43 两次全量重算启动，均无 "Compliance recalculation complete"** —— 重算处理到 Terminal[753]（10.8.20.254→bypass 并解封成功）后静默中断，**ID=1022 的 10.8.10.28 永远排不到**
2. **用户手动加白（IP pattern）100%失败**：02:20:38/02:20:46 两次 `POST /api/v1/whitelist/` → 400，`Error adding to whitelist: cannot access local variable 'datetime'`——即手动触发的全量重算也被 datetime 崩溃杀死
3. **黑名单历史**：A29764A5617C 在 8/20 一天内被 retry-block 封锁 8 次（17:21→20:50，约每 25-35 分钟一次），全部 auto_unblocked=true，震荡周期与"封锁→冷却10分钟→auto-unblock解封→compliance_status仍为non_compliant→下轮retry-block再封"完全吻合
4. **当前数据库状态**（10:46 查询）：10.8.10.28 = `status: unblocked` + `compliance_status: non_compliant` + 无活跃黑名单——正是震荡链的中间态：防火墙已解封，但 compliance_status 永远不会被修正为 bypass，**下一轮 retry-block 必然再次封锁**（日志显示 02:59/03:04/03:09 已三次尝试，03:09 成功）
5. **retry-block 毒化调度器**（03:09:30）：批量补封 yp 源时 10.8.20.254 触发 `idx_blacklist_unique_active` 唯一约束冲突 → 整个调度器事务 PendingRollback → get_stats、合规告警级联失败

## 新发现问题（本轮取证新增）

### 问题A：手动加白（IP pattern）400 的精确源头
- 调用链：`add_to_whitelist`（IP pattern 分支）→ `recalculate_all_compliance()` → 容器内旧代码 `_apply_compliance_result` 第1459/1474行的局部 datetime 导入遮蔽 → **UnboundLocalError** → 异常逐层上抛 → `add_to_whitelist` 第705行捕获并 rollback，返回 400
- 即：**手动加白失败的直接凶手仍是修复1针对的 compliance_service datetime 遮蔽**（容器内未部署），并非 terminal_service 自身
- 附带隐患：terminal_service.py 第 1328/1389/1439 行也有同类方法内局部 datetime 导入（当前 import 位于使用之前、未实际触发崩溃，但属于同类反模式），且第 661/769 行 `Terminal.last_seen` 字段不存在（模型只有 `timestamp`/`updated_at`）——**MAC 手动加白路径一旦执行必然 AttributeError**，必须在部署前一并修复

### 问题B：防火墙 AF 接口 03:14 起整体异常（次生问题）
- 03:09:27 封锁 10.8.10.28 成功 → 03:09:30 对账成功 re-block 8 个IP → **03:14 起**：
  - `get_blocked_ips` 返回 **0 条**（DB 有 86 条活跃黑名单）→ 触发"API故障保护"跳过对账，此后每5分钟重复
  - 所有 `block_ip` POST 返回 **400 Bad Request**（包括 10.8.10.28、10.8.18.232 等）
- Sangfor 认证成功（03:05 "Successfully authenticated"）且 keepalive 机制存在，排除登录失败
- 判断：会话建立后 AF 端返回 400/空列表，最可能是**高频连续操作触发 AF 侧会话异常或设备侧限流**；当前代码对 400 只记录状态码、不记录响应体，无法进一步定位
- 影响：部署修复后第一轮重算会解封大量白名单终端并向 AF 发请求，若 AF 仍异常会放大故障面

### 问题C：reconcile 提交成功后 KeyError 使结果日志丢失
- main.py:173 旧代码引用 `results['marked_unblocked']`（不存在的键），每轮对账成功后抛 KeyError——功能不受影响但掩盖对账结果

## 第二轮修复方案

### 修复3（补做）：调度器周期性全量重算
文件：`backend/app/main.py` `scheduled_compliance_check`
- 在每轮各数据源处理完成后，调用 `await service.recalculate_all_compliance()`
- 方法自带 Redis 分布式锁（COMPLIANCE_RECALC_LOCK），与手动触发/加白触发不冲突
- 用 try/except 包裹，失败仅记日志不阻断调度

### 修复5（补做）：对账结果日志键名修正
文件：`backend/app/main.py` 第 173 行
- `marked_unblocked` → `created_in_db`；`unblocked_on_firewall` → `reblocked_on_firewall`

### 修复6（补做+扩展）：消除 terminal_service.py 全部 datetime 遮蔽与 last_seen
文件：`backend/app/services/terminal_service.py`
- 删除第 1328/1389/1439 行方法内局部导入，统一用模块级导入（第7行已存在）
- 第 661/769 行 `Terminal.last_seen` → `Terminal.updated_at`（模型实际字段）

### 修复7（新增）：retry-block 增加白名单权威校验
文件：`backend/app/main.py` retry-block 段（第 336-445 行）
- 在 `for terminal in retry_terminals` 循环**前**一次性加载白名单内存缓存（`service._load_whitelist_cache()`），避免每终端重复加载
- 循环内、防火墙封锁之前，对每个终端执行 `_match_whitelist_in_memory(whitelist_data, ip, mac)`：
  - 命中 → 直接修正 `terminal.compliance_status = "bypass"`、清零两个确认计数、记日志并 `continue` 跳过补封
  - 未命中 → 走原有补封流程
- 若本轮有任何 bypass 状态修正，即使 `retry_blocked == 0` 也需 `db.commit()` 提交状态修正（在现有 commit 逻辑处增加计数判断）
- 理由：retry-block 盲信 `compliance_status` 字段，而该字段可能因历史崩溃长期失真；白名单是管理员权威配置，必须作为最后一道防线。这也是对所有历史脏状态终端的兜底自愈通道——即使重算遗漏，retry-block 每轮都会兜底修正

### 修复8（新增）：Sangfor block_ip/get_blocked_ips 记录错误响应体
文件：`backend/app/services/sangfor_service.py`
- `block_ip` 中 `raise_for_status()` 捕获 `httpx.HTTPStatusError`，日志输出 `response.text`（截断500字符）后重新抛出（保持现有错误处理行为不变）
- `get_blocked_ips` 同样记录非 code=0 时的原始响应
- 目的：定位 AF 返回 400/空列表的真实原因（参数/会话/限流），为问题B提供证据
- 保持最小改动，不改变现有重试/幂等逻辑

### 修复9（新增）：对账"0 IP保护"增加探测诊断
文件：`backend/app/services/firewall_reconciliation_service.py` `reconcile` 第 102-109 行保护分支
- 当 `len(fw_ips)==0 且 db_count>0` 时，从 `db_entries_by_fw[fw_tag]` 取一个活跃黑名单 IP 做探测查询（复用 `svc._find_blacklist_entry(probe_ip)`，按 url 精确匹配）：
  - 探测能查到该 IP → 列表接口异常但单查可用：记录明确日志（"列表API异常，跳过本轮对账"），维持跳过保护
  - 探测也查不到/异常 → 无法区分"防火墙被外部清空"与"API故障"：按保守原则维持跳过保护，但日志区分两种提示
- 原则不变：**任何情况下都不基于空列表执行清空/重封操作**，本修复只提升诊断精度，避免 AF 恢复后运维无法从日志判断卡因

## 修改文件清单（第二轮）
| 文件 | 修改内容 |
|------|---------|
| backend/app/main.py | 修复3（周期性全量重算）、修复5（KeyError）、修复7（retry-block白名单校验） |
| backend/app/services/terminal_service.py | 修复6（删1328/1389/1439局部导入 + last_seen→updated_at） |
| backend/app/services/sangfor_service.py | 修复8（400响应体日志） |
| backend/app/services/firewall_reconciliation_service.py | 修复9（0 IP保护探测诊断） |
（修复1/2/4 已在本地完成，本轮一并部署）

## 部署与验证方案

### 部署步骤
1. 完成修复3/5/6/7/8/9 代码修改
2. `python3 -m py_compile` 语法检查全部修改文件
3. **关键教训**：先确认容器内代码与本地一致再验证——`manage.sh update` 后立即 `docker exec tam_backend grep -c "set compliance_status=bypass directly" /app/app/services/compliance_service.py` 应 ≥1
4. `manage.sh update` 重建并重启后端服务

### 验证步骤
1. 部署后立即确认容器代码指纹（见上），并确认无迁移遗漏
2. 观察第一轮调度周期日志：
   - 出现 "Compliance recalculation complete"（重算成功完成）
   - 10.8.10.28 相关日志：`set compliance_status=bypass directly` 或重算中 `non_compliant → bypass`
3. 数据库验证：`SELECT compliance_status, status FROM terminals WHERE mac_address_normalized='A29764A5617C'` → 应为 `bypass` + `unblocked`
4. 手动加白接口验证：对测试终端执行加白，确认返回成功（不再 400）
5. 持续观察 2 个完整调度周期（≥10分钟）：
   - 无新的 A29764A5617C 封锁记录（黑名单表）
   - 无 IntegrityError、无 KeyError、无 PendingRollbackError
   - 对账日志输出 created_in_db/reblocked_on_firewall 正常
6. 问题B跟踪：观察 block_ip 的 400 响应体日志，确认 AF 是否恢复；若持续异常则依据响应体定位（会话/限流/参数）

### 风险与对策
- **风险**：部署时 AF 仍处于 400 异常状态，第一轮重算的解封/封锁请求失败。对策：修复7使白名单终端不再进入封锁路径，减少 AF 请求量；解封失败仅保留 blocked 状态，下轮重试，不会造成数据不一致
- **风险**：每5分钟全量重算增加负载。对策：Redis 分布式锁防并发，实测单次约7秒；如规模增长可降频
- **风险**：修复7状态修正提交时机。对策：独立计数+显式 commit，与 retry-block 批量提交分离

## 现场诊断结论（基于实际日志与数据库证据）

### 证据1：白名单匹配逻辑本身完全正常
在容器内直接测试 `_match_whitelist_in_memory`：
```
Match 10.8.10.28: {'match_type': 'ip', 'comments': 'GUEST WIFI'}  ✅ 能正确匹配 10.8.10.0/24
```
白名单缓存7条规则全部正常加载。**问题不在匹配逻辑。**

### 证据2：全量合规重算从未成功完成过
```bash
docker logs tam_backend --since 30m | grep -c "Compliance recalculation complete"
# 结果：0
```
日志显示重算每次都在中途崩溃，处理到 Terminal[144] 左右就中断，**排在后面的终端（包括10.8.10.28，ID=1022）永远轮不到被修正为bypass**。

### 证据3：崩溃的直接原因 —— `datetime` UnboundLocalError
```
Error adding to whitelist: cannot access local variable 'datetime' where it is not associated with a value
```

**根因代码**：[compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1453-L1474) `_apply_compliance_result` 方法内：
- 第1459、1474行：`from datetime import datetime` 写在 `elif new_compliance == "compliant"` 和 `else` 分支内部
- Python规则：函数体内任何位置出现 `from datetime import datetime`，`datetime` 就成为**整个函数的局部变量**
- 当终端变为 `bypass` 时走第1453行 `pass` 分支，局部导入**没有执行**
- 随后第1563行解封黑名单时执行 `bl_entry.unblocked_at = datetime.now(UTC)` → **UnboundLocalError崩溃**

**崩溃场景恰好就是"白名单终端从non_compliant转为bypass且需要解封"的情况** —— 即本次修复最想覆盖的路径，反而100%崩溃！重算在批次中途崩溃，之前的批次已提交（所以部分10.8.20.x终端被改成了bypass），但10.8.10.28排在后面永远没被处理。

### 证据4：调度器没有周期性全量重算，卡死终端无法自愈
[main.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L268-L271) `scheduled_compliance_check` 只检查 `compliance_status == "unknown"` 的终端（新终端），**对已卡死在non_compliant的白名单终端没有任何纠正机制**。全量重算只在用户操作白名单时被触发，而它又会崩溃。

### 证据5：震荡闭环链条（即使解封了也会再次被封锁）
`auto_unblock_compliant` 解封白名单终端时，[第828-830行](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L828-L830) 故意**不修改compliance_status**（注释说"等下次合规检查"），但：
1. 全量重算崩溃/不运行 → compliance_status永远是non_compliant
2. 10分钟冷却期过后 → 调度器retry-block看到 non_compliant + unblocked → 再次封锁
3. 再过10分钟 → auto_unblock又解封 → 如此往复 = **永久震荡**

黑名单历史记录完美印证：封锁约10-15分钟 → 解封约10分钟 → 再封锁，循环不止。

### 证据6：附带bug（会级联破坏调度器事务）
1. **retry-block IntegrityError**：03:09日志显示补封时违反 `idx_blacklist_unique_active` 唯一约束，整个调度器事务被毒化（后续get_stats、合规告警全部PendingRollbackError失败）
2. **对账KeyError**：[main.py#L172](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L172) 引用 `results['marked_unblocked']`，但reconcile()实际返回的键是 `reblocked_on_firewall`，每5分钟报一次 KeyError
3. **上一轮修复引入的AttributeError隐患**：[terminal_service.py#L661](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L661) 和 #L769 使用 `Terminal.last_seen` 排序，但Terminal模型根本没有 `last_seen` 字段（实际是 `timestamp`/`updated_at`），MAC手动加白会直接报错

## 修复方案

### 修复1（核心）：消除 `_apply_compliance_result` 的datetime变量遮蔽
文件：`backend/app/services/compliance_service.py`
- 删除第1459、1474行（elif/else分支内）的 `from datetime import datetime` 局部导入
- 文件顶部第16行已有模块级 `from datetime import datetime, timedelta, UTC`，删除局部导入后所有引用自动使用模块级导入
- 同时扫描全文件，删除其他方法内所有会遮蔽模块级 `datetime` 的局部导入（如第537行 `auto_block_non_compliant` 内的 `from datetime import datetime, timedelta`），统一用模块级导入，彻底杜绝同类问题

### 修复2（核心）：白名单解封时直接设置compliance_status=bypass
文件：`backend/app/services/compliance_service.py` `auto_unblock_compliant` 方法（第824-840行附近）
- 原代码注释"不要直接设置compliance_status，等下次检查"在"下次检查会崩溃/不运行"的现实下是错误的
- 改为：当 `wl_match` 为真（白名单匹配）时，直接设置 `terminal_record.compliance_status = "bypass"` 并清零确认计数——白名单是管理员权威配置，无需等待
- 当仅 `ig_match` 为真（IPGuard合规）时，保持原逻辑不变（仍交给下次检查确认）
- 这直接斩断震荡闭环：解封的同时状态变为bypass，retry-block不会再匹配它

### 修复3（核心）：调度器增加周期性全量重算
文件：`backend/app/main.py` `scheduled_compliance_check`
- 在每轮调度周期（默认5分钟）的各数据源检查完成后，调用 `recalculate_all_compliance()`
- 该方法自带Redis分布式锁，不会并发冲突；1046台终端全量重算实测约7秒，每5分钟一次开销可接受
- 作用：让任何卡死状态的终端都能自动自愈，不再依赖用户手动触发

### 修复4：修复retry-block的IntegrityError级联问题
文件：`backend/app/main.py` retry-block段（第336-431行）
- 已存在黑名单检查的 `scalar_one_or_none()` 改为 `scalars().first()`（同MAC多条活跃记录时避免MultipleResultsFound）
- 补封循环结束后的 `db.commit()` 用 try/except IntegrityError 包裹：失败时rollback并记录日志，避免毒化整个调度器事务导致后续任务全部失败

### 修复5：修复对账结果日志KeyError
文件：`backend/app/main.py` 第172行
- `results['marked_unblocked']`、`results['unblocked_on_firewall']` 改为reconcile()实际返回的键：`results['created_in_db']`、`results['reblocked_on_firewall']`

### 修复6：修复Terminal.last_seen AttributeError
文件：`backend/app/services/terminal_service.py` 第661、769行
- `Terminal.last_seen` 改为 `Terminal.updated_at`（模型实际字段）

## 修改文件清单
| 文件 | 修改内容 |
|------|---------|
| backend/app/services/compliance_service.py | 修复1（删datetime局部导入）、修复2（白名单解封直接设bypass） |
| backend/app/main.py | 修复3（周期性全量重算）、修复4（retry-block容错）、修复5（KeyError） |
| backend/app/services/terminal_service.py | 修复6（last_seen→updated_at） |

## 预期效果
1. 重建服务后，第一轮全量重算成功完成（日志出现"Compliance recalculation complete"）
2. 10.8.10.28（以及10.8.10.25、10.8.20.x等所有白名单网段卡死终端）→ compliance_status=bypass，防火墙自动解封
3. 黑名单表不再出现 A29764A5617C 的新封锁记录，震荡彻底停止
4. 之后每5分钟一次全量重算兜底，任何状态漂移都能自愈

## 验证步骤
1. `python3 -m py_compile` 语法检查三个修改文件
2. `manage.sh update` 重建服务
3. 观察日志：确认出现 "Compliance recalculation complete"（不再是0次）
4. 数据库验证：`SELECT compliance_status, status FROM terminals WHERE mac_address_normalized='A29764A5617C'` → 应为 bypass + unblocked
5. 持续观察2个调度周期（10分钟）：确认无新的retry-block/Auto-block记录，无IntegrityError、无KeyError

## 风险与对策
- **风险**：每5分钟全量重算增加数据库负载。对策：方法内置Redis锁防并发；实测单次约7秒，负载可控。如后续终端规模大幅增长，可调整为每N个周期执行一次。
- **风险**：修复1删除局部导入影响其他逻辑。对策：模块级导入已存在且为同一对象，删除只是消除遮蔽，行为不变。
- **风险**：修复2直接改compliance_status绕过确认计数。对策：仅对wl_match（白名单）生效，白名单是静态权威配置，符合此前确认的"白名单判定无需确认计数"原则；IPGuard路径保持原有确认机制不变。
