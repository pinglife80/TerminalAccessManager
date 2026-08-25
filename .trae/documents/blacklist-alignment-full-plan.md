# 黑名单管理全面对齐文档实施方案

## Summary

基于 `blacklist_management_improvement.md` 与用户确认（「全面对齐文档」+「标签作为表格筛选条件」+「混合方案」），补齐尚未实现的优化点，并让统计卡片可点击筛选。已实现且无需改动的部分：reason 细化、重试 API。本方案新增：

1. 模型新增操作跟踪字段 + 迁移
2. 补齐第 5 项统计「成功解封 success_unblocked」
3. 黑名单表格新增「状态」徽章列（含重试次数与失败原因悬停）
4. 封禁/解封逻辑记录操作状态
5. 统计卡片可点击筛选/跳转/弹窗

## 已核实结论（Phase 1 探索）

- 模型 `Blacklist` 无 `last_operation_*`/`retry_count` 字段（[blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/blacklist.py)）。
- `get_blacklist_stats` 仅返回 4 类，缺 `success_unblocked`（[terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1461-L1535)）。
- 前端 4 张统计卡片为纯 `<div>`，无 `onClick`（[Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L147-L193)）。
- reason 细化已在 [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py) 全路径实现（block/unblock/reconciliation/retry）。
- `detail` JSON 字段在文档中标注「可选」，本次不实现。
- 最新迁移版本为 `035_blacklist_fix_sync`，新迁移定为 `036_blacklist_operation_tracking`。
- 黑名单列表/导出默认 `status='active'`；`get_blacklist`/`get_blacklist_count` 已支持 `active|unblocked|all`。
- 终端页 [Terminals.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx) 用 `useState` 维护筛选，尚未读取 URL 参数。

## 统计五项的数据源映射（关键决策）

| 统计项 | 数据来源 | 点击行为 |
|---|---|---|
| 成功封锁 success_blocked | 黑名单 active 条目 | 前端 category=success_blocked → 表格筛选 active |
| 成功解封 success_unblocked | 黑名单 unblocked 条目 | category=success_unblocked → 表格筛选 unblocked |
| 等待重试解封 pending_retry_unblock | active 条目 + 终端已合规/bypass | category=pending_retry_unblock → 表格 JOIN 筛选 |
| 等待重试封锁 pending_retry_block | 终端（non_compliant+unblocked，无黑名单记录） | 跳转 `/terminals?compliance_status=non_compliant&status=unblocked` |
| 防火墙错误 firewall_errors | 防火墙名称列表（非条目） | 弹窗列出失败防火墙名 |

## Proposed Changes

### 一、后端

#### 1. 模型 [blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/blacklist.py)
新增 5 个字段：
- `last_operation_type = Column(String(20), nullable=True)` — 'block'/'unblock'
- `last_operation_status = Column(String(20), nullable=True)` — 'success'/'failed'
- `last_operation_error = Column(Text, nullable=True)`
- `last_operation_at = Column(DateTime(timezone=True), nullable=True)`
- `retry_count = Column(Integer, default=0, server_default='0', nullable=False)`

#### 2. 新增迁移 `backend/alembic/versions/036_blacklist_operation_tracking.py`
- `revision='036_blacklist_operation_tracking'`，`down_revision='035_blacklist_fix_sync'`
- 用 `op.add_column` 添加上述 5 列（`retry_count` 带 `server_default='0'`）
- `downgrade()` 用 `op.drop_column` 移除

#### 3. Schema [terminal.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/terminal.py)
- `BlacklistResponse` 新增 `last_operation_type/status/error/at`、`retry_count` 字段（`from_attributes=True` 已启用，ORM 自动映射）
- `BlacklistQuery` 新增 `category: str | None = None`

#### 4. [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py)
- `get_blacklist_stats`：新增第 ③ 项后插入 `success_unblocked`（统计 `auto_unblocked==True or unblocked_at IS NOT NULL` 的条目数），返回字典加入该键。
- `get_blacklist` / `get_blacklist_count`：支持 `query.category`，复用现有 status 逻辑：
  - `success_blocked` → active filter（同现状）
  - `success_unblocked` → unblocked filter（同现状）
  - `pending_retry_unblock` → active filter + `join(Terminal, Terminal.ip_address == Blacklist.ip_address)` + `Terminal.compliance_status.in_(["compliant","bypass"])`
  - 无 category 保持默认 active
- `retry_unblock`：
  - 成功分支（[L1587-L1591](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1587-L1591)）设置 `last_operation_type='unblock'`、`last_operation_status='success'`、`last_operation_at=now`
  - 失败分支（[L1584-L1585](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1584-L1585)）与异常分支（[L1580-L1582](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1580-L1582)）在返回前设置 `last_operation_type='unblock'`、`last_operation_status='failed'`、`last_operation_error=err`、`retry_count += 1`、`last_operation_at=now` 并 `commit`

#### 5. [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py)
在下列 Blacklist 创建/解封处补充操作跟踪字段（`last_operation_type/status/at`）：
- `auto_block` 创建条目（约 [L588-L599](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L588-L599)）→ `('block','success',now)`
- `auto_unblock` 全量解封（约 [L852-L855](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L852-L855)）与部分解封（约 [L923-L926](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L923-L926)）→ `('unblock','success',now)`
- `_apply_compliance_result` 解封（约 [L1754-L1757](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1754-L1757)）→ `('unblock','success',now)`
- `_apply_compliance_result` 重封创建（约 [L1881-L1892](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1881-L1892)）→ `('block','success',now)`

#### 6. [main.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L459-L470)
retry-block 创建 Blacklist 处补充 `last_operation_type='block', last_operation_status='success', last_operation_at=now`。

#### 7. [firewall_reconciliation_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L301-L313)
对账补建 Blacklist 处补充 `last_operation_type='block', last_operation_status='success', last_operation_at=now`。

#### 8. 端点 [blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/blacklist.py)
`GET /blacklist/` 增加 `category: str = Query(None)`，透传到 `BlacklistQuery`（导出接口保持不变）。

### 二、前端

#### 9. [useTerminalData.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/hooks/useTerminalData.ts)
- `BlacklistEntry` 新增 `last_operation_type/status/error/at`、`retry_count`
- `BlacklistStats` 新增 `success_unblocked: number`
- `BlacklistSearchParams` 新增 `category?: string`，`useBlacklist` 透传

#### 10. [Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx)
- 新增 `category` state、`useNavigate`
- 统计卡片改为可点击（`button` 语义 / `cursor-pointer` + `onClick`），并高亮当前选中项：
  - 成功封锁 → `setCategory('success_blocked')`
  - 成功解封 → `setCategory('success_unblocked')`（新增第 5 张卡片，图标如 `Unlock`/`ShieldCheck`）
  - 等待重试解封 → `setCategory('pending_retry_unblock')`
  - 等待重试封锁 → `navigate('/terminals?compliance_status=non_compliant&status=unblocked')`
  - 防火墙错误 → 打开 `firewallErrorsModal`
- `useBlacklist` 增加 `category` 参数，切页时重置 `currentPage`
- 表格新增「状态」列：根据 `last_operation_status` 渲染成功/失败徽章；`retry_count>0` 时追加重试次数徽章；`last_operation_status==='failed'` 时用 `title` 悬停显示 `last_operation_error`（先移除上一轮删掉的 TYPE/Blocked By 列后，本列插入到「防火墙」之后，空状态 `colSpan` 相应 +1 为 8）
- 新增 `firewallErrorsModal` 复用现有 `Modal` 组件，列出 `stats.firewall_errors`

#### 11. [Terminals.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx)
- 用 `useSearchParams` 在组件挂载时读取 `compliance_status`、`status`，初始化 `filterCompliance`、`filterStatus`，实现跳转预置筛选

#### 12. i18n [zh.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/zh.ts) / en.ts / ja.ts
新增 `blacklist` 命名空间键：
- `statsSuccessUnblocked`（成功解封 / Successfully Unblocked）
- `status`（状态 / Status）
- `opSuccess`（成功 / Success）、`opFailed`（失败 / Failed）
- `retryCount`（重试 {count} 次）
- `firewallErrorsTitle`（防火墙错误 / Firewall Errors）、`noFirewallErrors`（无错误）
- `pendingRetryBlockHint`（该分类为终端数据，点击跳转终端管理）

## Assumptions & Decisions

- `detail` JSON 字段（文档标「可选」）不实现，避免过度设计。
- `last_operation_*` 跟踪落在黑名单条目级；「等待重试封锁」因无黑名单记录，通过跳转终端页呈现，不在黑名单表冗余跟踪。
- 对账补建 `last_operation_type='block'`（补建即写入一条封锁记录）。
- 新迁移不写业务数据回填，仅加列；历史条目 `last_operation_*` 为 NULL、`retry_count=0`，前端对 NULL 显示默认「—」。
- i18n 三语言文件同步新增，保持一致。

## Verification

1. 后端：`alembic upgrade head` 成功，`\d blacklist` 含新列。
2. `GET /blacklist/stats` 返回含 `success_unblocked` 的 5 类计数。
3. `GET /blacklist/?category=pending_retry_unblock` 仅返回 active 且终端已合规/bypass 的条目；`success_blocked`/`success_unblocked` 正确过滤。
4. 前端构建/lint 无 TS 报错；黑名单页 5 张卡片均可点击，3 类筛选表格、1 类跳转终端页预置筛选、1 类弹窗列防火墙名。
5. 手动触发一次解封失败（如禁用防火墙后重试解封），确认条目 `retry_count` 递增、表格「状态」列显示失败徽章 + 悬停错误信息。
6. 运行 `./manage.sh update` 重新构建并验证容器指纹，确认部署生效。