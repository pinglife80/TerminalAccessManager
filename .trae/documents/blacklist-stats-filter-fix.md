# 黑名单管理数据统计与筛选逻辑修复计划

## 问题概述

用户反馈黑名单管理中存在两个问题：
1. **Unblocked 标签筛选不出数据**：点击 Unblocked Tab 后列表为空
2. **同一终端出现重复条目**：如 10.8.110.192 同时存在一条 Blocked 记录和一条带 Unblocked 标记的记录

## 根因分析

### 问题1：Unblocked Tab 筛选不出数据

**筛选条件不匹配**：
- 后端筛选逻辑（[terminal_service.py:980-981](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L980-L981)）：`status == 'unblocked'` → `Blacklist.unblocked_at.is_not(None)`
- 前端 UI 标签显示（[Blacklist.tsx:413](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L413)）：基于 `item.auto_unblocked`

**历史数据不一致**：`unblocked_at` 字段在 migration 024 中新增（[024_blacklist_soft_delete.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/alembic/versions/024_blacklist_soft_delete.py)），在此之前的自动解封记录只有 `auto_unblocked = True` 但 `unblocked_at IS NULL`。这些记录在 UI 上显示 "Unblocked" 标签（因为 `auto_unblocked = True`），但在 Unblocked Tab 中查不到（因为 `unblocked_at IS NULL`）。

### 问题2：同一终端重复条目

**设计行为**：每次封锁都会创建新的 Blacklist 记录（[compliance_service.py:480-492](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L480-L492)），用于审计历史。当终端经历 封锁→解封→再封锁 时，会产生多条记录：
- 记录A：`auto_unblocked=True`（已解封的历史记录）
- 记录B：`auto_unblocked=False, unblocked_at=NULL`（当前活跃封锁）

在 "All" Tab 中两条记录都会显示，这是审计需要。但统计数据基于当前页数据计算，导致混乱。

### 问题3：统计数据基于当前页（附带发现）

[Blacklist.tsx:286-329](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L286-L329) 中，除 "Blocked Devices" 使用 `totalFromServer` 外，其余4个统计（autoBlocked、manualBlocked、expiredBlocks、activeBlocks）都基于 `filteredBlacklist`（当前页数据）计算，多页时数据不准确。

## 修复方案

### 修改1：后端筛选逻辑修复

**文件**：[backend/app/services/terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py)

**位置**：`get_blacklist()` (L976-L985) 和 `get_blacklist_count()` (L1023-L1030)

**修改内容**：统一 active/unblocked 的筛选条件，同时考虑 `auto_unblocked` 和 `unblocked_at` 两个字段：

```python
# Status filtering: default to active only
if query and query.status:
    if query.status == 'active':
        # Active = not unblocked (both fields must indicate active)
        conditions.append(
            and_(
                Blacklist.auto_unblocked == False,
                Blacklist.unblocked_at.is_(None)
            )
        )
    elif query.status == 'unblocked':
        # Unblocked = either field indicates unblocked
        conditions.append(
            or_(
                Blacklist.auto_unblocked == True,
                Blacklist.unblocked_at.is_not(None)
            )
        )
    # 'all' or other values: no filter
else:
    # Default: only show active (not unblocked) records
    conditions.append(
        and_(
            Blacklist.auto_unblocked == False,
            Blacklist.unblocked_at.is_(None)
        )
    )
```

需要在文件顶部确认已导入 `and_`, `or_`（当前 `or_` 已导入，需确认 `and_`）。

### 修改2：数据迁移修复历史数据

**文件**：新建 `backend/alembic/versions/026_blacklist_fix_unblocked_at.py`

**修改内容**：为所有 `auto_unblocked = True AND unblocked_at IS NULL` 的记录设置 `unblocked_at = blocked_at`（使用封锁时间作为近似解封时间）：

```python
"""Fix historical unblocked_at for auto-unblocked blacklist entries

Revision ID: 026_blacklist_fix_unblocked_at
Revises: 025_terminal_updated_at
"""
from alembic import op
import sqlalchemy as sa

revision = '026_blacklist_fix_unblocked_at'
down_revision = '025_terminal_updated_at'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Set unblocked_at for records that were auto-unblocked but missing the timestamp
    op.execute(
        "UPDATE blacklist SET unblocked_at = blocked_at "
        "WHERE auto_unblocked = true AND unblocked_at IS NULL"
    )
    # Also fix manually unblocked records (unblocked_by set but unblocked_at missing)
    op.execute(
        "UPDATE blacklist SET unblocked_at = blocked_at "
        "WHERE unblocked_by IS NOT NULL AND unblocked_at IS NULL"
    )

def downgrade() -> None:
    # Cannot restore NULL values reliably, no-op
    pass
```

### 修改3：后端新增黑名单统计接口

**文件**：[backend/app/api/v1/endpoints/blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/blacklist.py)

**新增**：`GET /blacklist/stats` 接口，返回服务端全局统计：

```python
@router.get("/stats")
async def get_blacklist_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:read"))
):
    """Get blacklist statistics (server-side global counts for active entries)"""
    service = TerminalService(db)
    stats = await service.get_blacklist_stats()
    return stats
```

### 修改4：后端新增统计 Service 方法

**文件**：[backend/app/services/terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py)

**新增**：`get_blacklist_stats()` 方法，基于 active 记录计算全局统计：

```python
async def get_blacklist_stats(self) -> dict:
    """Get global blacklist statistics based on active (not unblocked) records."""
    from sqlalchemy import func, case
    from datetime import datetime, UTC

    base_filter = and_(
        Blacklist.auto_unblocked == False,
        Blacklist.unblocked_at.is_(None)
    )

    stmt = select(
        func.count(Blacklist.id).label('total_active'),
        func.count(case((Blacklist.is_auto_blocked == True, 1))).label('auto_blocked'),
        func.count(case((Blacklist.is_auto_blocked == False, 1))).label('manual_blocked'),
        func.count(case(
            ((Blacklist.expires_at.is_not(None)) & (Blacklist.expires_at < datetime.now(UTC)), 1)
        )).label('expired'),
    ).where(base_filter)

    result = await self.db.execute(stmt)
    row = result.one()

    return {
        "total_active": row.total_active or 0,
        "auto_blocked": row.auto_blocked or 0,
        "manual_blocked": row.manual_blocked or 0,
        "expired": row.expired or 0,
        "active_blocks": (row.total_active or 0) - (row.expired or 0),
    }
```

### 修改5：前端使用服务端统计数据

**文件**：[frontend/src/pages/Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx)

**修改内容**：
1. 新增 `useBlacklistStats` hook 调用 `/blacklist/stats` 接口
2. 将统计卡片（L286-L329）中的客户端计算替换为服务端数据
3. 统计数据仅在 "active" Tab 下显示全局统计；在 "unblocked"/"all" Tab 下隐藏子统计或显示对应的服务端统计

### 修改6：前端 Unblocked 标签显示一致性

**文件**：[frontend/src/pages/Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L413)

**修改内容**：将 Unblocked 标签的显示条件从 `item.auto_unblocked` 改为 `item.auto_unblocked || item.unblocked_at`，与后端筛选逻辑保持一致：

```jsx
{(item.auto_unblocked || item.unblocked_at) && (
  <span className="ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
    {t('blacklist.unblockedLabel')}
  </span>
)}
```

## 执行顺序

1. 修改2：创建数据迁移脚本（026）
2. 修改1：修复后端筛选逻辑
3. 修改4：新增统计 Service 方法
4. 修改3：新增统计 API 接口
5. 修改5：前端使用服务端统计
6. 修改6：前端标签一致性
7. 运行 `./manage.sh -y update` 构建部署
8. 验证测试

## 验证步骤

1. **Unblocked Tab 验证**：点击 Unblocked Tab，确认能筛选出已解封记录（包括历史 `unblocked_at` 为空但 `auto_unblocked=True` 的记录）
2. **Active Tab 验证**：确认 Active Tab 只显示当前活跃封锁记录，不包含已解封记录
3. **All Tab 验证**：确认 All Tab 显示所有记录，已解封记录显示 Unblocked 标签
4. **重复条目验证**：确认 10.8.110.192 在 Active Tab 只显示1条（当前封锁），在 Unblocked Tab 显示历史解封记录
5. **统计验证**：确认统计数字与实际数据一致，不随翻页变化
6. **数据迁移验证**：确认所有 `auto_unblocked=True` 的记录都有 `unblocked_at` 值

## 影响分析

- **筛选逻辑修改**：仅影响 Blacklist 查询，不影响其他模块
- **数据迁移**：只更新 `unblocked_at IS NULL` 的已解封记录，不影响活跃记录
- **新增统计接口**：新增 API 端点，不影响现有接口
- **前端修改**：仅影响 Blacklist 页面显示
