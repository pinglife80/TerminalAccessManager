# 防火墙与数据库同步差异问题分析与修复计划

> 创建日期：2026-07-16
> 问题描述：防火墙黑名单显示 147 条，数据库/Web 页面显示 146 条

---

## 一、问题分析

### 1.1 现象对比

| 统计来源 | 数值 |
|---------|------|
| 防火墙黑名单 | 147 |
| 数据库活跃黑名单 | 146 |
| Web 页面所有显示 | 146 |

### 1.2 根因分析

通过差异检查脚本发现：

**防火墙中有但数据库中缺失的 IP：**
- `10.8.19.175`

**数据库中有但防火墙中缺失的 IP：**
- 无

### 1.3 差异原因

该 IP `10.8.19.175` 可能是通过以下方式被添加到防火墙但未同步到数据库：
1. **防火墙手动操作**：管理员直接在防火墙 Web 界面添加了该 IP
2. **防火墙 API 调用**：通过防火墙 API 直接添加，但未经过系统的正常封锁流程
3. **之前的对账记录删除**：在之前删除 12 条 reconciliation 类型记录时，可能误删了相关记录

### 1.4 额外发现

**代码 Bug**：`cli.py` 第1674行解析防火墙返回数据时出错：
```python
# 原代码（错误）
blocked_count = len(result.get("data", []))

# 修复后
blocked_count = len(result.get("data", {}).get("items", []))
```

防火墙 API 返回格式为 `{"data": {"items": [...]}}`，原代码错误地将 `data` 当作列表处理，导致显示数量错误。

---

## 二、修复方案

### 2.1 已修复的代码问题

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `backend/cli.py` | 修复防火墙查询结果解析逻辑 | ✅ 已完成 |
| `backend/app/services/terminal_service.py` | 添加 `decrypt_config` 导入 | ✅ 已完成 |

### 2.2 数据库修复

需要将缺失的 IP `10.8.19.175` 添加到数据库中。

**步骤1：查询终端信息**
```sql
SELECT id, ip_address, mac_address, status 
FROM terminals 
WHERE ip_address = '10.8.19.175';
```

**步骤2：添加黑名单记录**
```sql
INSERT INTO blacklist (
    ip_address,
    mac_address,
    mac_address_normalized,
    firewall_tag,
    blocked_by,
    blocked_at,
    expires_at,
    source_tag,
    is_auto_blocked,
    auto_unblocked,
    reason
) VALUES (
    '10.8.19.175',
    '',
    '',
    'af-changning',
    'system',
    NOW(),
    NOW() + INTERVAL '30 days',
    'reconciliation',
    TRUE,
    FALSE,
    'Reconciliation: IP blocked on firewall but not in database'
);
```

**步骤3：更新终端状态（如果存在）**
```sql
UPDATE terminals 
SET status = 'blocked' 
WHERE ip_address = '10.8.19.175' 
  AND status != 'blocked';
```

### 2.3 触发防火墙对账

执行防火墙对账任务，确保数据库与防火墙状态完全同步：
```bash
./manage.sh scheduler trigger compliance_check
```

---

## 三、验证方案

### 3.1 数据库验证

```sql
-- 验证黑名单总数（应为 147）
SELECT COUNT(*) FROM blacklist 
WHERE auto_unblocked = FALSE 
  AND unblocked_at IS NULL
  AND (expires_at >= NOW() OR expires_at IS NULL);

-- 验证新增 IP 是否存在
SELECT id, ip_address, source_tag, is_auto_blocked 
FROM blacklist 
WHERE ip_address = '10.8.19.175';
```

### 3.2 防火墙验证

```bash
./manage.sh scheduler trigger firewall_query
# 预期结果：147 条
```

### 3.3 前端验证

- 黑名单管理页面条目数应为 147
- Dashboard 封锁统计应为 147
- 终端管理封锁终端数应为 147
- 防火墙实际封锁数应为 147

---

## 四、风险评估

| 风险 | 等级 | 描述 | 缓解措施 |
|------|------|------|---------|
| 数据不一致 | 低 | 添加记录后可能与终端状态不同步 | 更新终端状态 |
| 重复记录 | 低 | 可能创建重复的黑名单记录 | 添加前检查是否已存在 |
| 防火墙解封 | 低 | 添加记录后防火墙可能自动解封 | 执行对账任务确认 |

---

## 五、检查清单

- [ ] 执行 SQL 查询终端信息
- [ ] 添加黑名单记录到数据库
- [ ] 更新终端状态（如果存在）
- [ ] 验证数据库黑名单总数（147）
- [ ] 触发防火墙查询验证（147）
- [ ] 前端页面验证显示一致性
