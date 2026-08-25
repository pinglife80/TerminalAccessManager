# 黑名单管理改进方案

## 问题分析

当前的黑名单管理存在两个问题：
1. ❌ `Database Active` 和 `Firewall Actual Block` 只是简单的数字对比，无实际操作价值
2. ❌ `reason` 字段没有明确区分是 IP 不合规、MAC 不合规还是都不合规
3. ❌ **自动解封时没有设置 reason！** 现在的代码只设置了 `auto_unblocked = True` 和 `unblocked_at`，但没有说明解封原因

## 改进方案

---

### 第一部分：更有实际意义的统计展示

#### 1.1 新增字段跟踪状态

在 `Blacklist` 模型中新增字段：
```python
last_operation_type = Column(String(20), nullable=True)  # 'block' 或 'unblock'
last_operation_status = Column(String(20), nullable=True)  # 'success' 或 'failed'
last_operation_error = Column(Text, nullable=True)  # 失败原因
last_operation_at = Column(DateTime(timezone=True), nullable=True)  # 最后操作时间
retry_count = Column(Integer, default=0)  # 重试次数
```

#### 1.2 有实际意义的统计展示

替换现有的统计卡片，改为：

| 统计项 | 说明 | 颜色 |
|--------|------|------|
| **成功封锁** | 已在防火墙成功封锁的条目 | 🟢 绿色 |
| **等待重试封锁** | 封锁失败，等待下一次重试 | 🟡 黄色 |
| **成功解封** | 已在防火墙成功解封的条目 | 🔵 蓝色 |
| **等待重试解封** | 解封失败，等待下一次重试 | 🟠 橙色 |
| **防火墙错误** | 无法连接或查询的防火墙 | 🔴 红色 |

#### 1.3 表格状态列增强

在黑名单列表中新增：
- **状态徽章**：显示当前操作状态和重试次数
- **错误信息**：鼠标悬停显示失败原因
- **快速重试**：为失败条目提供单独的重试按钮

---

### 第二部分：原因细化

#### 2.1 细化 reason 字段

在封锁/解封时，根据实际合规情况设置详细的 reason：

| 场景 | reason | 说明 |
|------|--------|------|
| **自动封锁** | 'IP 和 MAC 都不合规' | 两者都不匹配 |
| **自动封锁** | 'IP 不合规，MAC 合规' | 仅 IP 不匹配 |
| **自动封锁** | 'MAC 不合规，IP 合规' | 仅 MAC 不匹配 |
| **自动解封** | '加入白名单' | 白名单匹配自动解封 |
| **自动解封** | 'IP 和 MAC 都合规' | 两者都匹配 |
| **自动解封** | 'IP 合规，MAC 不合规' | 仅 IP 匹配 |
| **自动解封** | 'MAC 合规，IP 不合规' | 仅 MAC 匹配 |
| **对账补建** | 'Reconciliation: IP blocked on firewall \'{fw_tag}\' but missing in DB' | 对账时发现防火墙有但 DB 没有 |
| **对账重封** | 保持原有 reason，或 'Reconciliation: re-block (DB says should be blocked)' | 对账时发现 DB 应被封锁但防火墙没有 |
| **重试封锁** | 'Auto-blocked: non-compliant (retry)' | retry-block 任务重新封锁 |

#### 2.2 新增 detail 字段（可选）

可以新增一个 `detail` 字段存储更详细的 JSON 数据：
```python
detail = Column(JSON, nullable=True)  # 详细信息，如：
# {
#   "ip_compliant": true,
#   "mac_compliant": false,
#   "whitelist_match": null,
#   "ipguard_match": "10.8.10.28"
# }
```

---

### 第三部分：后端修改

#### 3.1 更新 `get_blacklist_stats`
返回新的统计结构：
```python
{
    "success_blocked": 0,      # 成功封锁
    "pending_retry_block": 0,  # 等待重试封锁
    "success_unblocked": 0,    # 成功解封
    "pending_retry_unblock": 0,# 等待重试解封
    "firewall_errors": [],     # 有问题的防火墙列表
    ...
}
```

#### 3.2 更新封禁/解封逻辑
在 `ComplianceService` 的 `auto_block_non_compliant` 和 `auto_unblock_compliant` 中：
- 根据实际合规情况设置详细的 reason
- 在 `SangforService` 中记录操作状态

#### 3.3 新增重试 API
```
POST /blacklist/{id}/retry
- 手动重试单个条目
```

---

## 修改文件清单

### 后端
1. `backend/app/models/blacklist.py` - 新增字段
2. `backend/app/services/compliance_service.py` - 细化 reason
3. `backend/app/services/terminal_service.py` - 更新统计逻辑
4. `backend/app/services/sangfor_service.py` - 更新操作状态记录
5. `backend/app/api/v1/endpoints/blacklist.py` - 新增重试 API

### 前端
6. `frontend/src/pages/Blacklist.tsx` - 更新前端展示
7. `frontend/src/hooks/useTerminalData.ts` - 更新类型定义
8. `frontend/src/i18n/locales/*.ts` - 更新翻译

---

## 数据库迁移

新增 Alembic 迁移文件：
```python
# 添加新字段
op.add_column('blacklist', sa.Column('last_operation_type', sa.String(20), nullable=True))
op.add_column('blacklist', sa.Column('last_operation_status', sa.String(20), nullable=True))
op.add_column('blacklist', sa.Column('last_operation_error', sa.Text(), nullable=True))
op.add_column('blacklist', sa.Column('last_operation_at', sa.DateTime(timezone=True), nullable=True))
op.add_column('blacklist', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
```

---

## 下一步

等待你的确认，然后开始实施！
