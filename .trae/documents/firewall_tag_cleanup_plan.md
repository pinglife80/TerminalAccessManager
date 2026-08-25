# Firewall Tag 业务逻辑修复方案

## 一、问题分析

### 当前业务逻辑

`firewall_tag` 字段的含义是"终端被封锁在哪个防火墙上"，因此合理的业务逻辑应该是：
- **只有 `status = 'blocked'` 的终端才应该有 `firewall_tag` 值**
- **任何非 blocked 状态（unblocked/active）的终端都不应该有 `firewall_tag`**

### 当前代码问题

通过分析代码，发现以下问题：

**问题1：防火墙解除封锁失败时状态不一致**
在 `compliance_service.py` 第1218-1267行：
```python
if terminal.status == "blocked" and new_compliance in ("bypass", "compliant"):
    # ... 尝试解除封锁
    if successful_fw_tags:
        terminal.status = "unblocked"
        terminal.firewall_tag = None  # 成功时清除
    else:
        logger.warning(f"Auto-unblock failed...")
        # 失败时：status 保持 blocked，firewall_tag 保持不变（这是正确的）
```

**问题2：状态变更时未同步清除 firewall_tag**
当终端状态通过其他途径变为 unblocked 时，`firewall_tag` 可能没有被清除：
- 手动解除封锁
- 数据同步导致状态变更
- 合规重算时的边界情况

**问题3：前端显示逻辑**
前端直接显示 `firewall_tag` 字段，没有验证终端状态是否为 blocked。

## 二、修复方案

### 修复策略

**原则**：`firewall_tag` 的存在必须与 `status = 'blocked'` 严格关联

**修改内容**：

#### 1. 后端服务 - compliance_service.py

在 `_apply_compliance_result` 函数中，当终端状态变为非 blocked 时，强制清除 `firewall_tag`：

```python
# 在设置 terminal.status = "unblocked" 的地方，同时清除 firewall_tag
# 确保无论通过何种途径解除封锁，firewall_tag 都会被清除
if terminal.status != "blocked":
    terminal.firewall_tag = None
```

#### 2. 后端服务 - 添加状态变更时的自动清理

在终端状态变更的所有入口点，确保 `firewall_tag` 与状态保持一致：
- 手动解除封锁 API
- 自动解除封锁逻辑
- 数据同步服务

#### 3. 前端显示优化

在前端显示 `firewall_tag` 时，增加状态检查：
- 只有当终端状态为 blocked 时才显示 firewall_tag
- 其他状态显示 "-"

#### 4. 数据修复脚本

提供一个数据库修复脚本，清理现有数据中状态与 firewall_tag 不一致的记录：
```sql
UPDATE terminals SET firewall_tag = NULL WHERE status != 'blocked' AND firewall_tag IS NOT NULL;
```

## 三、修改文件清单

### 后端修改

1. **`backend/app/services/compliance_service.py`**（第1218-1271行）
   - 在所有设置 `terminal.status = "unblocked"` 的地方，确保同时设置 `terminal.firewall_tag = None`

2. **`backend/app/services/terminal_service.py`**
   - 查找手动解除封锁的逻辑，确保清除 firewall_tag

3. **`backend/app/api/v1/endpoints/terminals.py`**
   - 查找解除封锁相关的 API，确保清除 firewall_tag

### 前端修改

1. **`frontend/src/pages/Terminals.tsx`**（第828-831行，第966-970行）
   - 修改 firewall_tag 的显示逻辑，只在 blocked 状态时显示

## 四、实施步骤

### 步骤1：修改 compliance_service.py

确保所有状态变更为 unblocked 的路径都清除 firewall_tag。

### 步骤2：修改 terminal_service.py

检查手动解除封锁逻辑，确保一致性。

### 步骤3：修改前端显示逻辑

在表格和详情模态框中，只在 blocked 状态时显示 firewall_tag。

### 步骤4：数据修复

执行数据库修复脚本，清理历史数据。

### 步骤5：验证测试

1. 创建一个非合规终端，确认被封锁后有 firewall_tag
2. 将该终端添加到白名单，确认状态变为 bypass/unblocked，firewall_tag 被清除
3. 测试手动解除封锁，确认 firewall_tag 被清除
4. 验证前端只在 blocked 状态时显示 firewall_tag

## 五、风险处理

### 风险1：现有数据不一致

**处理方案**：执行数据修复脚本，清理所有非 blocked 状态但有 firewall_tag 的记录。

### 风险2：防火墙解除封锁失败

**处理方案**：当防火墙解除失败时，终端保持 blocked 状态，firewall_tag 保留，这是正确的行为。

### 风险3：多防火墙场景

**处理方案**：当前逻辑已经支持多防火墙（用逗号分隔），修复后仍然支持。

## 六、验证方案

### 业务层面验证

1. **正常封锁流程**：
   - 创建非合规终端 → 自动封锁 → 状态=blocked，firewall_tag=xxx ✓

2. **白名单放行流程**：
   - 被封锁终端添加到白名单 → 合规重算 → 状态=unblocked，firewall_tag=null ✓

3. **手动解除封锁**：
   - 手动解除封锁 → 状态=unblocked，firewall_tag=null ✓

4. **前端显示验证**：
   - blocked 状态显示 firewall_tag ✓
   - unblocked/bypass/compliant 状态不显示 firewall_tag ✓

### 技术层面验证

1. **API 验证**：
   - 调用解除封锁 API 后，检查返回的 firewall_tag 是否为 null

2. **数据库验证**：
   - 查询 `SELECT * FROM terminals WHERE status != 'blocked' AND firewall_tag IS NOT NULL;`
   - 预期结果：0 条记录

3. **合规重算验证**：
   - 添加白名单后触发合规重算，检查被放行终端的 firewall_tag 是否被清除
