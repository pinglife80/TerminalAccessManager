# 黑名单「到期自动解封」独立 reason 修复计划

> 文档版本：v1.0  更新日期：2026-08-25

## 一、摘要

1. 两个终端 `10.8.13.141` / `10.8.15.88` 的自动解封，均为**周期内合规检查通过**自动解封（`auto_unblock_compliant`），**不是**封锁时间到期解封。
2. 经代码分析确认：黑名单封锁时间到期后的自动解封（`cleanup_expired_blacklist`）**当前不写入独立 reason**，导致到期解封的黑名单记录在页面「原因」列仍显示原始封锁原因，与合规解封口径不一致。
3. 本次做**最小修复**：为到期解封补写独立 reason「封锁时间到期自动解封」，并扩展单元测试。

## 二、现状分析

### 2.1 两个终端解封原因判定

查询 `blacklist` 表（`docker exec tam_db psql -U tam_admin -d tam_db`）结果：

| id | ip | reason | blocked_at | expires_at | is_auto_blocked | auto_unblocked | unblocked_at | unblocked_by | last_operation |
|----|----|--------|-----------|-----------|-----------------|----------------|--------------|--------------|----------------|
| 1489 | 10.8.15.88 | IP 和 MAC 都合规 | 10:24:04 | 11:24:04 | t | **t** | 10:38:43 | (空) | unblock / success |
| 1490 | 10.8.13.141 | IP 和 MAC 都合规 | 10:44:35 | 11:44:35 | t | **t** | 10:58:43 | (空) | unblock / success |

**判定依据（均为合规解封，非到期）：**

1. `auto_unblocked = true`：该字段**仅**由合规解封 `auto_unblock_compliant` 置位；到期解封 `cleanup_expired_blacklist` 从不置位（见 [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L862-L864)）。
2. `reason = "IP 和 MAC 都合规"`：由 `_build_unblock_reason` 生成，是合规解封路径专属文案（见 [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1143-L1171)）；到期路径不写 reason。
3. `unblocked_at` ≈ `blocked_at + 14 分钟`，远早于 `expires_at`（= `blocked_at + 1h`），说明是周期内提前解封，而非等到到期。
4. `last_operation_type/status = unblock/success`：仅合规解封写入；到期解封不写。
5. `unblocked_by` 为空：合规解封不写 `unblocked_by`；到期解封会写 `unblocked_by="system"`。

> 附带结论：两终端 `expires_at = blocked_at + 1h`，说明当前系统内 `block_time` 配置为 `1h`（非默认 30d）。

### 2.2 到期解封 reason 现状（Q2 确认）

到期解封 `cleanup_expired_blacklist`（见 [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1866-L2021)）在标记解封的两处，仅写入：

- `entry.unblocked_at = datetime.now(UTC)`
- `entry.unblocked_by = "system"`

**未**写入 `reason`（保留原始封锁原因）、**未**置位 `auto_unblocked`、**未**写 `last_operation_*`。

对比合规解封 `auto_unblock_compliant` 会覆写 `reason`（见 [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L851-L871)）。

前端黑名单详情/列表直接展示 `reason`（见 [Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L534-L537)、[Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L417-L419)），因此到期解封的记录「原因」列仍显示原始封锁原因，属口径缺陷。

## 三、修改方案

### 修改 1：`backend/app/services/terminal_service.py`

在 `cleanup_expired_blacklist` 的两处标记解封分支，补写 `entry.reason = "封锁时间到期自动解封"`：

- 分支 A（存在其他有效封锁、仅标记本条到期解封），位于 [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1929-L1934)：
  ```python
  entry.unblocked_at = datetime.now(UTC)
  entry.unblocked_by = "system"
  entry.reason = "封锁时间到期自动解封"   # 新增
  count += 1
  ```
- 分支 B（防火墙解封成功），位于 [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1982-L1985)：
  ```python
  entry.unblocked_at = datetime.now(UTC)
  entry.unblocked_by = "system"
  entry.reason = "封锁时间到期自动解封"   # 新增
  count += 1
  ```

### 修改 2：`backend/tests/test_compliance_service.py`

- 在 [test_cleanup_checks_active_blocks](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/tests/test_compliance_service.py#L554-L608) 的断言中，紧随 `assert expired_entry.unblocked_by == "system"` 后新增：
  ```python
  assert expired_entry.reason == "封锁时间到期自动解封"
  ```
  （该用例覆盖「has_other_active」分支 A。）
- 另在 [test_cleanup_only_resets_blocked_terminals](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/tests/test_compliance_service.py#L610-L676) 末尾新增一条断言，覆盖「sangfor_unblock_success」分支 B：
  ```python
  assert expired_entry.reason == "封锁时间到期自动解封"
  ```

## 四、假设与决策

- reason 文案固定为「封锁时间到期自动解封」，与既有中文 reason（「加入白名单」「IP 和 MAC 都合规」等）口径一致；合规解封的 reason 同样是硬编码中文，故不引入配置项。
- 本次仅补 reason，**不**改 `auto_unblocked` 语义、**不**补 `last_operation_*`、**不**做前端展示区分（该部分归属「完整修复」范畴，本次不做）。
- 到期解封仍以 `auto_unblocked=false` + `unblocked_by="system"` 作为内部标识，仅补齐对外展示的 reason。

## 五、验证步骤

1. 单元测试（定向）：
   ```bash
   docker compose exec -T backend python -m pytest tests/test_compliance_service.py::TestCleanupExpiredBlacklist -v --tb=short
   ```
2. 全量测试（可选，确认无回归）：
   ```bash
   ./manage.sh test
   ```
3. 本地重建并重启后端（仅本地重建+重启，不拉取远端）：
   ```bash
   ./manage.sh update
   ```
4. 容器指纹验证代码已生效：
   ```bash
   docker exec tam_backend grep -n "封锁时间到期自动解封" /app/app/services/terminal_service.py
   ```
   应返回两处命中（分支 A / 分支 B）。
5. 业务链路验证（可选，需构造到期数据）：创建一条 `expires_at` 已过期的黑名单记录，触发 `cleanup_expired_blacklist`（后台任务或 CLI `cleanup_expired_blacklist`），确认该记录 `reason` 变为「封锁时间到期自动解封」、`unblocked_by=system`、`unblocked_at` 被写。