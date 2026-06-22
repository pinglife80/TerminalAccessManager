# 黑名单管理页面显示已解封记录修复方案

## 问题

黑名单管理页面（Blacklist.tsx）查询后端 `GET /blacklist/` 时，**没有过滤 `auto_unblocked=True` 的记录**，导致已自动解封的历史记录以"Auto-blocked"状态出现在列表中，与终端实际合规且未封堵的状态矛盾。

**用户视角**：10.8.28.97 终端合规且未封堵，但黑名单页面仍显示一条 Auto-blocked 记录。

## 根因

1. **后端** `get_blacklist()` 和 `get_blacklist_count()` 查询时无 `auto_unblocked` 过滤条件，返回所有记录（含已解封）
2. **前端**统计卡片中"活跃封禁"仅基于 `expires_at` 判断过期，未考虑 `auto_unblocked` 状态
3. **前端**表格中已解封记录仍显示"解封"按钮，操作无意义

## 修复方案

### 修改 1：后端 `get_blacklist()` 默认过滤已解封记录

**文件**: `backend/app/services/terminal_service.py`

- `get_blacklist()` (第856行)：在查询条件中添加 `Blacklist.auto_unblocked == False`
- `get_blacklist_count()` (第892行)：同上

**逻辑**：黑名单管理页面默认只展示当前仍被封堵的活跃记录（`auto_unblocked=False`），已解封的历史记录不再出现。

### 修改 2：后端 `BlacklistQuery` 添加 `status` 筛选参数

**文件**: `backend/app/schemas/terminal.py`

- `BlacklistQuery` 添加 `status: str | None = None` 字段
  - `status="active"` → `auto_unblocked=False`（默认行为）
  - `status="unblocked"` → `auto_unblocked=True`（查看历史解封记录）
  - `status=None` → 不过滤（返回所有记录）

**文件**: `backend/app/api/v1/endpoints/blacklist.py`

- `get_blacklist` endpoint 添加 `status: str | None = Query(None)` 参数
- 传递给 service 层查询

**文件**: `backend/app/services/terminal_service.py`

- `get_blacklist()` 和 `get_blacklist_count()` 根据 `query.status` 添加对应过滤条件

### 修改 3：前端添加状态筛选 Tab

**文件**: `frontend/src/pages/Blacklist.tsx`

- 在搜索栏下方添加 Tab 切换：`活跃封堵` | `已解封` | `全部`
  - `活跃封堵`：传 `status=active`（默认）
  - `已解封`：传 `status=unblocked`
  - `全部`：不传 status 参数
- 统计卡片根据当前 Tab 动态调整：
  - `活跃封堵` Tab：显示当前5个统计卡片（总数、自动、手动、过期、活跃）
  - `已解封` Tab：显示解封相关统计（解封总数、自动解封、手动解封等）
  - `全部` Tab：显示全部统计
- 已解封记录行样式区分：降低不透明度 + 显示"已解封"标签
- 已解封记录隐藏"解封"按钮（已无意义）

### 修改 4：前端 API 参数传递

**文件**: `frontend/src/hooks/useTerminalData.ts`

- `BlacklistSearchParams` 接口添加 `status?: string` 字段
- `useBlacklist` hook 传递 `status` 参数到 API

### 修改 5：前端 i18n 添加翻译键

**文件**: `frontend/src/i18n/locales/zh.json` 和 `en.json`

- 添加 `blacklist.activeTab`、`blacklist.unblockedTab`、`blacklist.allTab`、`blacklist.unblocked` 等翻译

## 不修改的部分

- **Blacklist 模型**：不添加 `status` 字段，状态通过 `auto_unblocked` + `expires_at` 推断
- **解封逻辑**：`auto_unblocked=True` 软删除机制保持不变，这是审计追踪的设计
- **详情弹窗**：已有 `auto_unblocked` 展示，无需修改
- **CSV 导出**：已包含 `auto_unblocked` 字段，无需修改

## 影响评估

- **业务功能**：零破坏。默认行为从"显示全部"变为"只显示活跃封堵"，更符合用户预期
- **API 兼容性**：`status` 参数可选，默认 `None` 时行为不变（但建议默认改为 `active`）
- **数据库**：无 schema 变更，无需迁移

## 验证步骤

1. 启动开发环境，确认黑名单页面默认只显示活跃封堵记录
2. 切换到"已解封" Tab，确认能看到历史解封记录
3. 切换到"全部" Tab，确认能看到所有记录
4. 确认已解封记录不显示"解封"按钮
5. 确认统计卡片数值与 Tab 切换一致
6. 确认搜索和日期筛选在所有 Tab 下正常工作
