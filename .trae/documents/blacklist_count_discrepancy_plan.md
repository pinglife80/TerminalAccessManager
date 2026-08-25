# 黑名单计数差异问题分析与修复计划

> 文档版本：v1.0 | 创建日期：2026-07-16
> 问题描述：防火墙黑名单146条，Dashboard显示146条，终端管理封锁终端146条，但黑名单管理条目显示158条

***

## 一、问题分析

### 1.1 现象对比

| 统计来源         | 数值  | 查询逻辑                                                         |
| ------------ | --- | ------------------------------------------------------------ |
| 防火墙黑名单       | 146 | 实际防火墙规则                                                      |
| Dashboard 统计 | 146 | `Terminal.status == 'blocked'`                               |
| 终端管理封锁终端     | 146 | `Terminal.status == 'blocked'`                               |
| 黑名单管理条目      | 158 | `Blacklist.auto_unblocked == False AND unblocked_at IS NULL` |

### 1.2 核心差异点

**关键发现**：`get_blacklist_count`（黑名单管理）与 `check_blacklist`（终端管理）使用了**不同的过滤条件**：

**`get_blacklist_count`**（`terminal_service.py:809-853`）：

```python
base_filter = and_(
    Blacklist.auto_unblocked == False,
    Blacklist.unblocked_at.is_(None)
)
# 没有检查 expires_at 是否过期！
```

**`check_blacklist`**（`terminal_service.py:887-947`）：

```python
and_(
    Blacklist.auto_unblocked == False,
    or_(
        Blacklist.expires_at >= now,      # 额外检查！
        Blacklist.expires_at.is_(None),
    ),
    or_(*match_conditions),
)
# 有过期时间检查！
```

### 1.3 根因结论

**数据库中存在 12 条已过期（`expires_at < now`）但未被清理的黑名单记录。**

这些记录满足：

* `auto_unblocked == False`（未标记自动解封）

* `unblocked_at IS NULL`（未记录解封时间）

* `expires_at < now`（已过期）

由于黑名单管理页面的统计**没有过滤过期记录**，所以显示 158 条（146 有效 + 12 过期）。

而终端管理页面通过 `check_blacklist` 查询，**过滤了过期记录**，所以只显示 146 条。

### 1.4 关于 "Manual" 类型记录的根因分析

**关键发现**：黑名单管理中显示的 12 条 Manual 类型记录，实际上是由**防火墙对账服务**（`firewall_reconciliation_service.py`）创建的，并非人工手动封锁。

**代码证据**（`firewall_reconciliation_service.py:186-197`）：

```python
if not existing_bl:
    bl_entry = Blacklist(
        ip_address=ip_address,
        blocked_by="system",           # 系统创建
        blocked_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=30),
        source_tag="reconciliation",   # 来源为对账
        is_auto_blocked=False,         # ← 问题！错误设置为 False
        auto_unblocked=False,
        reason="Reconciliation: IP blocked on firewall but not in database",
    )
```

**问题原因**：

1. 防火墙对账服务发现防火墙已有但数据库缺失的封锁记录时，会自动创建数据库条目
2. 创建时错误地设置 `is_auto_blocked=False`（应为 `True`，因为是系统自动创建）
3. 前端根据 `is_auto_blocked` 字段判断类型：`True` → "自动封禁"，`False` → "手动封禁"
4. 因此这些系统自动创建的对账记录被错误地显示为"手动封禁"

**为什么会有 12 条过期的 Manual 记录？**

* 这些记录是对账服务在 30 天前创建的（`expires_at=30 days`）

* 到期后 `expires_at < now`，但未被自动清理

* 由于 `is_auto_blocked=False`，这些记录不会参与合规自动解封流程

### 1.5 过期记录未清理的可能原因

1. **防火墙解封失败**：当终端 IP 仍有其他活跃封锁时，只标记 `unblocked_at`，不实际解封防火墙
2. **自动解封定时任务未执行**：定时任务可能因服务重启或调度问题未触发
3. **事务回滚**：防火墙解封成功但数据库更新失败，导致记录状态不一致
4. **对账记录未参与自动解封**：由于 `is_auto_blocked=False`，这些记录被排除在 `auto_unblock_compliant` 流程之外

***

## 二、修复方案

### 2.1 修改文件

| 文件                                                        | 修改内容                                                                                         |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `backend/app/services/terminal_service.py`                | 在 `get_blacklist_count`、`get_blacklist`、`get_blacklist_stats` 方法中添加过期时间过滤                    |
| `backend/app/services/firewall_reconciliation_service.py` | 修改 `_get_db_active_blacklist` 添加过期时间过滤；修改 `_create_db_entries` 将 `is_auto_blocked` 改为 `True` |

### 2.2 修复步骤

**步骤1：修改** **`get_blacklist`** **方法（第756-766行）**

原代码：

```python
# Status filtering: default to active only
_active_filter = and_(
    Blacklist.auto_unblocked == False,
    Blacklist.unblocked_at.is_(None)
)
```

修改为：

```python
from datetime import datetime, UTC

# Status filtering: default to active only (not unblocked and not expired)
_active_filter = and_(
    Blacklist.auto_unblocked == False,
    Blacklist.unblocked_at.is_(None),
    or_(
        Blacklist.expires_at >= datetime.now(UTC),
        Blacklist.expires_at.is_(None),
    )
)
```

**步骤2：修改** **`get_blacklist_count`** **方法（第813-823行）**

原代码：

```python
# Status filtering: default to active only
_active_filter = and_(
    Blacklist.auto_unblocked == False,
    Blacklist.unblocked_at.is_(None)
)
```

修改为：

```python
from datetime import datetime, UTC

# Status filtering: default to active only (not unblocked and not expired)
_active_filter = and_(
    Blacklist.auto_unblocked == False,
    Blacklist.unblocked_at.is_(None),
    or_(
        Blacklist.expires_at >= datetime.now(UTC),
        Blacklist.expires_at.is_(None),
    )
)
```

**步骤3：修改** **`get_blacklist_stats`** **方法（第860-863行）**

原代码：

```python
base_filter = and_(
    Blacklist.auto_unblocked == False,
    Blacklist.unblocked_at.is_(None)
)
```

修改为：

```python
base_filter = and_(
    Blacklist.auto_unblocked == False,
    Blacklist.unblocked_at.is_(None),
    or_(
        Blacklist.expires_at >= datetime.now(UTC),
        Blacklist.expires_at.is_(None),
    )
)
```

**步骤4：修改** **`_get_db_active_blacklist`** **方法（`firewall_reconciliation_service.py`** **第148-151行）**

原代码：

```python
).where(
    (Blacklist.unblocked_at.is_(None)) &
    (Blacklist.auto_unblocked == False)
)
```

修改为：

```python
from datetime import datetime, UTC

).where(
    (Blacklist.unblocked_at.is_(None)) &
    (Blacklist.auto_unblocked == False) &
    (or_(
        Blacklist.expires_at >= datetime.now(UTC),
        Blacklist.expires_at.is_(None),
    ))
)
```

**步骤5：修改** **`_create_db_entries`** **方法（`firewall_reconciliation_service.py`** **第186-197行）**

原代码：

```python
from datetime import datetime, UTC

).where(
    (Blacklist.unblocked_at.is_(None)) &
    (Blacklist.auto_unblocked == False) &
    (or_(
        Blacklist.expires_at >= datetime.now(UTC),
        Blacklist.expires_at.is_(None),
    ))
)
```

修改为：

```python
bl_entry = Blacklist(
    ip_address=ip_address,
    blocked_by="system",
    blocked_at=datetime.now(UTC),
    expires_at=datetime.now(UTC) + timedelta(days=30),
    source_tag="reconciliation",
    is_auto_blocked=True,          # ← 修正为 True
    auto_unblocked=False,
    reason="Reconciliation: IP blocked on firewall but not in database",
)
```

### 2.3 数据库数据修复

需要修复已存在的 12 条 Manual 类型记录，将其 `is_auto_blocked` 改为 `True`：

```sql
-- 将来源为 reconciliation 的记录标记为自动封禁
UPDATE blacklist 
SET is_auto_blocked = TRUE 
WHERE source_tag = 'reconciliation' 
  AND is_auto_blocked = FALSE;

-- 验证修复结果
SELECT COUNT(*) FROM blacklist 
WHERE source_tag = 'reconciliation' 
  AND is_auto_blocked = FALSE;
-- 预期结果：0
```

***

## 三、验证方案

### 3.1 数据库验证

```sql
-- 验证过期记录数量（预期：12）
SELECT COUNT(*) FROM blacklist 
WHERE auto_unblocked = FALSE 
  AND unblocked_at IS NULL 
  AND expires_at < NOW();

-- 验证有效记录数量（预期：146）
SELECT COUNT(*) FROM blacklist 
WHERE auto_unblocked = FALSE 
  AND unblocked_at IS NULL 
  AND (expires_at >= NOW() OR expires_at IS NULL);

-- 验证 Manual 类型记录来源（修复前：12 条来自 reconciliation）
SELECT source_tag, COUNT(*) FROM blacklist 
WHERE is_auto_blocked = FALSE 
  AND auto_unblocked = FALSE 
  AND unblocked_at IS NULL 
GROUP BY source_tag;

-- 验证数据库修复后 reconciliation 记录的 is_auto_blocked 状态
SELECT COUNT(*) FROM blacklist 
WHERE source_tag = 'reconciliation' 
  AND is_auto_blocked = FALSE;
-- 预期结果：0（修复后）
```

### 3.2 API 验证

```bash
# 获取黑名单统计（修复后 total_active 应为 146）
curl -H "Authorization: Bearer <token>" https://<host>/api/v1/blacklist/stats

# 获取黑名单列表（修复后 total 应为 146）
curl -H "Authorization: Bearer <token>" https://<host>/api/v1/blacklist/

# 获取黑名单统计详情（修复后 manual_blocked 应为 0）
curl -H "Authorization: Bearer <token>" https://<host>/api/v1/blacklist/stats
# 预期：manual_blocked: 0
```

### 3.3 前端验证

* 黑名单管理页面显示条目数应为 146

* Dashboard 封锁统计应为 146

* 终端管理封锁终端数应为 146

* 防火墙实际封锁数应为 146

* 黑名单管理中"手动封禁"类型记录应为 0

***

## 四、风险评估

| 风险      | 等级 | 描述                 | 缓解措施        |
| ------- | -- | ------------------ | ----------- |
| 数据统计变更  | 低  | 修改后黑名单管理显示数量减少     | 验证所有统计接口一致性 |
| 防火墙同步影响 | 低  | 修改后过期记录不再参与同步      | 过期记录已失效，不影响 |
| API 兼容性 | 无  | 仅修改过滤逻辑，不改变 API 结构 | 无兼容性问题      |

***

## 五、检查清单

* [ ] 修改 `get_blacklist` 方法添加过期时间过滤

* [ ] 修改 `get_blacklist_count` 方法添加过期时间过滤

* [ ] 修改 `get_blacklist_stats` 方法添加过期时间过滤

* [ ] 修改 `_get_db_active_blacklist` 方法添加过期时间过滤

* [ ] 修改 `_create_db_entries` 方法将 `is_auto_blocked` 改为 `True`

* [ ] 数据库执行 SQL 修复已存在的 reconciliation 记录

* [ ] 数据库验证过期记录数量（预期：12）

* [ ] 数据库验证 Manual 类型记录数量（预期：0）

* [ ] API 验证返回值（total\_active: 146, manual\_blocked: 0）

* [ ] 前端页面验证显示一致性

