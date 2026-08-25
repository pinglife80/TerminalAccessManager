# 删除 Manual 类型黑名单记录计划

> 创建日期：2026-07-16
> 目的：删除 12 条来源为 reconciliation 的 Manual 类型冗余黑名单记录

***

## 一、背景说明

### 1.1 问题描述

黑名单管理中存在 12 条类型为 "Manual（手动封禁）" 的记录，但系统的封锁和解封逻辑均为自动化，不存在人工手动封禁操作。

### 1.2 根因

这些记录是由**防火墙对账服务**（`firewall_reconciliation_service.py`）创建的，创建时错误地设置了 `is_auto_blocked=False`，导致前端显示为 "手动封禁"。

代码位置：`backend/app/services/firewall_reconciliation_service.py` 第193-202行

### 1.3 记录特征

* `source_tag = 'reconciliation'`

* `is_auto_blocked = FALSE`

* `auto_unblocked = FALSE`

* `unblocked_at IS NULL`

* `blocked_by = 'system'`

* `reason` 包含 "Reconciliation" 前缀

***

## 二、操作步骤

### 2.1 准备工作

**第一步：进入数据库 shell**

```bash
cd /home/dada/Codespace/TraeCN/TerminalAccessManager
./manage.sh shell db
```

### 2.2 查询确认

**第二步：查询待删除的记录（执行前必须确认）**

```sql
-- 查询所有 reconciliation 来源的 Manual 记录
SELECT 
    id,
    ip_address,
    mac_address,
    source_tag,
    firewall_tag,
    is_auto_blocked,
    blocked_at,
    expires_at,
    reason
FROM blacklist 
WHERE source_tag = 'reconciliation' 
  AND is_auto_blocked = FALSE
  AND auto_unblocked = FALSE
  AND unblocked_at IS NULL
ORDER BY blocked_at DESC;
```

**预期结果**：12 条记录

**第三步：验证这些 IP 是否仍在防火墙黑名单中**

```sql
-- 统计唯一 IP 数量
SELECT COUNT(DISTINCT ip_address) 
FROM blacklist 
WHERE source_tag = 'reconciliation' 
  AND is_auto_blocked = FALSE;
```

### 2.3 数据备份

**第四步：备份待删除的数据**

```bash
# 在宿主机执行（另开一个终端）
cd /home/dada/Codespace/TraeCN/TerminalAccessManager
./manage.sh backup backups/before_delete_reconciliation_$(date +%Y%m%d_%H%M%S).sql
```

### 2.4 执行删除

**第五步：删除记录**

```sql
-- 删除 reconciliation 来源的 Manual 类型记录
DELETE FROM blacklist 
WHERE source_tag = 'reconciliation' 
  AND is_auto_blocked = FALSE
  AND auto_unblocked = FALSE
  AND unblocked_at IS NULL;
```

### 2.5 验证结果

**第六步：验证删除结果**

```sql
-- 验证删除数量（应为 0）
SELECT COUNT(*) FROM blacklist 
WHERE source_tag = 'reconciliation' 
  AND is_auto_blocked = FALSE;

-- 验证总活跃记录数（应为 146）
SELECT COUNT(*) FROM blacklist 
WHERE auto_unblocked = FALSE 
  AND unblocked_at IS NULL
  AND (expires_at >= NOW() OR expires_at IS NULL);
```

***

## 三、风险与注意事项

### 3.1 风险评估

| 风险      | 等级 | 描述              | 缓解措施              |
| ------- | -- | --------------- | ----------------- |
| 误删数据    | 中  | 删除了不应该删除的记录     | 删除前备份 + 精确条件过滤    |
| 防火墙不同步  | 中  | 删除数据库记录后防火墙仍有封锁 | 删除后执行一次防火墙对账      |
| 终端状态不一致 | 低  | Terminal 表状态未更新 | 检查对应终端的 status 字段 |

### 3.2 注意事项

1. **必须先备份**：执行删除前必须运行 `./manage.sh backup` 备份数据库
2. **先查询确认**：执行 DELETE 前必须先执行 SELECT 确认记录数量和内容
3. **删除后验证**：删除后立即验证删除结果
4. **防火墙对账**：删除后建议执行一次防火墙对账，确保数据库与防火墙状态一致

### 3.3 回滚方案

如需回滚，使用备份文件恢复：

```bash
./manage.sh restore backups/before_delete_reconciliation_YYYYMMDD_HHMMSS.sql
```

***

## 四、后续操作

删除完成后，建议执行以下操作：

1. **运行防火墙对账**：确保数据库与防火墙状态一致

   ```bash
   # 通过 scheduler 触发对账任务
   ./manage.sh scheduler trigger firewall_reconciliation
   ```

2. **前端验证**：

   * 黑名单管理页面条目数应为 146

   * 黑名单管理中 "手动封禁" 类型记录应为 0

   * Dashboard 统计应与之前一致（146）

3. **检查终端状态**：确认被删除记录对应的终端状态是否正确

***

## 五、检查清单

* [ ] 进入数据库 shell

* [ ] 执行 SELECT 查询确认待删除记录（12条）

* [ ] 执行数据库备份

* [ ] 执行 DELETE 删除记录

* [ ] 验证删除结果（0条剩余）

* [ ] 验证总活跃记录数（146条）

* [ ] 执行防火墙对账

* [ ] 前端页面验证显示一致性

