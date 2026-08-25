# 黑名单「解封事件列」与「到期解封 reason」修复计划

> 文档版本：v1.0  更新日期：2026-08-25

## 一、摘要

1. 已确认两个终端 `10.8.13.141` / `10.8.15.88` 均因**周期内合规检查通过**（`auto_unblock_compliant`）自动解封，非到期解封。
2. 已确认到期解封（`cleanup_expired_blacklist`）当前**不写独立 reason**，到期解封记录在「原因」列仍显示原始封锁原因，口径缺失。
3. 本次变更分两部分：
   - **后端（最小修复）**：`cleanup_expired_blacklist` 补写 `reason = "封锁时间到期自动解封"`，并扩展单元测试。
   - **前端（新增列）**：黑名单列表新增「解封事件」列，展示**解封原因 + 解封时间**，使「成功解封」记录一眼可辨解封类型与时间。

## 二、现状分析

### 2.1 两终端解封判定（背景结论）

`blacklist` 表两条记录（`docker exec tam_db psql -U tam_admin -d tam_db`）：

| id | ip | reason | blocked_at | expires_at | is_auto_blocked | auto_unblocked | unblocked_at | unblocked_by | last_operation |
|----|----|--------|-----------|-----------|-----------------|----------------|--------------|--------------|----------------|
| 1489 | 10.8.15.88 | IP 和 MAC 都合规 | 10:24:04 | 11:24:04 | t | **t** | 10:38:43 | (空) | unblock / success |
| 1490 | 10.8.13.141 | IP 和 MAC 都合规 | 10:44:35 | 11:44:35 | t | **t** | 10:58:43 | (空) | unblock / success |

判定依据：`auto_unblocked=true`（仅合规解封置位）、`reason` 由 `_build_unblock_reason` 生成、`unblocked_at ≈ blocked_at + 14 分钟`（早于 `expires_at`）、`last_operation_type/status=unblock/success`（到期路径不写）、`unblocked_by` 为空（到期路径会写 `system`）。均指向合规解封。

### 2.2 到期解封 reason 缺失（需后端修复）

`cleanup_expired_blacklist` 在两处标记解封仅写 `unblocked_at` + `unblocked_by="system"`，不写 `reason`（见 [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1929-L1934) 与 [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1982-L1985)）。对比合规解封会覆写 `reason`（[compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L851-L871)）。

### 2.3 前端列表现状（需新增列）

黑名单列表当前列为：MAC / IP / 原因 / 防火墙 / 状态 / 封禁时间 / 过期时间 / 操作（见 [Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L359-L384)）。

「成功解封」（`success_unblocked`）是统计卡片分类，点击后 `category='success_unblocked'` 过滤（见 [Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L198-L212)），列表展示已解封记录。这些记录当前只在 `reason` 列体现解封原因（合规解封已覆写，到期解封需后端修复），缺少**解封时间**维度，无法一眼区分「合规提前解封」与「到期解封」。

数据已具备：后端 `BlacklistResponse` 含 `unblocked_at`、`reason`（[terminal.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/terminal.py#L122-L141)），前端 `BlacklistEntry` 已含 `unblocked_at`、`reason`（[useTerminalData.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/hooks/useTerminalData.ts#L30-L50)）。仅需前端加列，无需改接口字段。

## 三、修改方案

### 后端

#### 1. `backend/app/services/terminal_service.py` — `cleanup_expired_blacklist` 补写 reason

在两处标记解封分支补 `entry.reason = "封锁时间到期自动解封"`：

- 分支 A（存在其他有效封锁，仅标记本条到期解封）[terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1929-L1934)：
  ```python
  entry.unblocked_at = datetime.now(UTC)
  entry.unblocked_by = "system"
  entry.reason = "封锁时间到期自动解封"
  count += 1
  ```
- 分支 B（防火墙解封成功）[terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1982-L1985)：
  ```python
  entry.unblocked_at = datetime.now(UTC)
  entry.unblocked_by = "system"
  entry.reason = "封锁时间到期自动解封"
  count += 1
  ```

#### 2. `backend/tests/test_compliance_service.py` — 扩展断言

- [test_cleanup_checks_active_blocks](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/tests/test_compliance_service.py#L554-L608)（覆盖分支 A）在 `assert expired_entry.unblocked_by == "system"` 后新增：
  ```python
  assert expired_entry.reason == "封锁时间到期自动解封"
  ```
- [test_cleanup_only_resets_blocked_terminals](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/tests/test_compliance_service.py#L610-L676)（覆盖分支 B）末尾新增：
  ```python
  assert expired_entry.reason == "封锁时间到期自动解封"
  ```

### 前端

#### 3. `frontend/src/pages/Blacklist.tsx` — 新增「解封事件」列

- 表头：在「过期时间」`<th>`（[Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L378-L380)）之后、`<th>{t('common.actions')}</th>` 之前插入：
  ```tsx
  <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
    {t('blacklist.unblockEvent')}
  </th>
  ```
- 单元格：在「过期时间」`<td>`（[Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L456-L464)）之后、操作 `td` 之前插入：
  ```tsx
  <td className="px-4 sm:px-6 py-4">
    {(item.auto_unblocked || item.unblocked_at) ? (
      <div className="space-y-1">
        <div className="flex items-center gap-1.5">
          <Unlock className="h-3.5 w-3.5 text-green-600 flex-shrink-0" />
          <span className="text-sm text-foreground">{item.reason || '—'}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3.5 w-3.5 flex-shrink-0" />
          {formatDate(item.unblocked_at)}
        </div>
      </div>
    ) : (
      <span className="text-sm text-muted-foreground">—</span>
    )}
  </td>
  ```
- 空态 `colSpan`：由 `8` 改为 `9`（[Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L389)）。
- 图标依赖：`Unlock`、`Clock` 已在文件顶部第 4 行 import，无需新增。

#### 4. i18n 文案 — 新增 `blacklist.unblockEvent`（zh / en / ja）

- [zh.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/zh.ts) `blacklist` 段内（`statsSuccessUnblocked` 附近）新增：`unblockEvent: '解封事件'`
- [en.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/en.ts) 对应位置：`unblockEvent: 'Unblock Event'`
- [ja.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/ja.ts) 对应位置：`unblockEvent: 'ブロック解除イベント'`

## 四、假设与决策

- 解封原因复用 `reason` 字段（合规解封已覆写；到期解封本次修复后覆写为「封锁时间到期自动解封」）。新增「解封事件」列的解封原因部分即取 `item.reason`，因此该列与现有「原因」列在已解封记录上语义重叠，属**已知可接受权衡**（不引入 `block_reason`/`unblock_reason` 双字段，避免扩大改动面）。
- reason 文案沿用中文硬编码（与「加入白名单」「IP 和 MAC 都合规」等既有口径一致），不新增配置项。
- 列仅在已解封记录展示内容，未解封显示「—」；列结构全局固定，兼容默认 `active` 视图。
- 不变动 `auto_unblocked` 字段语义、不补 `last_operation_*`、不改详情弹窗（归属后续完整修复范畴）。

## 五、验证步骤

1. 后端定向单测：
   ```bash
   docker compose exec -T backend python -m pytest tests/test_compliance_service.py::TestCleanupExpiredBlacklist -v --tb=short
   ```
2. 前端类型构建（tsc + vite）：
   ```bash
   cd frontend && npm run build
   ```
3. 后端全量测试（可选，防回归）：
   ```bash
   ./manage.sh test
   ```
4. 本地重建并重启后端（仅重建+重启，不拉远端）：
   ```bash
   ./manage.sh update
   ```
5. 容器指纹确认后端代码已生效：
   ```bash
   docker exec tam_backend grep -n "封锁时间到期自动解封" /app/app/services/terminal_service.py
   ```
   应返回两处命中（分支 A / 分支 B）。
6. 前端 UI 验证：进入黑名单页，点击「成功解封」卡片 → 列表应出现「解封事件」列，已解封记录显示「解封原因 + 解封时间」，未解封记录显示「—」。
7. 业务链路验证（可选）：构造一条 `expires_at` 已过期的记录，触发 `cleanup_expired_blacklist`（后台任务或 CLI），确认其 `reason` 变为「封锁时间到期自动解封」、`unblocked_at` 已写，刷新页面该记录「解封事件」列正确显示。