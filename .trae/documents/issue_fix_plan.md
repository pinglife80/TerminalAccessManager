# 问题修复计划

## 问题概述

### 问题1：数据源管理中的ARP类型数据源添加中出现防火墙类型选项
**描述**：在数据源管理页面的"数据源"Tab中添加数据源时，类型选择下拉框中错误地包含了防火墙类型（Sangfor）选项。

**根因分析**：
- `DataSourcesTab.tsx` 组件（处理 ARP 数据源）中的添加/编辑模态框类型下拉框包含了三种类型：`arp_ssh`、`arp_api`、`sangfor`
- 但根据设计，ARP 数据源和防火墙数据源应该分开管理：
  - `DataSourcesTab.tsx`：管理 ARP 数据源（`arp_ssh`、`arp_api`）
  - `OperationSourceTab.tsx`：管理防火墙数据源（`sangfor`）
- 当前代码中 `DataSourcesTab.tsx` 的添加/编辑表单错误地包含了 `sangfor` 选项

**文件位置**：
- `frontend/src/components/datasources/DataSourcesTab.tsx` - 第 565 行和第 644 行的类型选择下拉框

---

### 问题2：审计日志管理中的分页导航栏与其他页面不一致
**描述**：审计日志页面的分页导航栏样式和交互方式与其他页面（如终端管理、黑名单管理）不同。

**根因分析**：
- 其他页面使用统一的 `Pagination.tsx` 组件（基于 offset 的分页）
- 审计日志页面使用自定义的游标分页（cursor-based pagination），实现了独立的分页导航逻辑
- 需要将审计日志页面的分页统一为 `Pagination.tsx` 组件

**文件位置**：
- `frontend/src/pages/AuditLogs.tsx` - 自定义分页导航逻辑（约第 680-720 行）
- `frontend/src/components/Pagination.tsx` - 标准分页组件
- `backend/app/api/v1/endpoints/logs.py` - 后端搜索接口（支持 cursor 和 offset 两种分页）

---

### 问题3：从备份数据中只恢复白名单管理数据
**描述**：需要从备份文件 `auto_pre_update_20260714_234325.sql` 中只恢复白名单（whitelist）相关数据。

**根因分析**：
- 备份文件可能包含完整的数据库备份
- 需要提取白名单相关的 SQL 语句（CREATE TABLE 和 INSERT INTO whitelist）
- 然后执行恢复操作

**文件位置**：
- 需要查找备份文件位置

---

## 解决方案

### 方案1：移除ARP数据源添加中的防火墙类型选项

**修改文件**：
- `frontend/src/components/datasources/DataSourcesTab.tsx`

**修改内容**：
1. 将添加数据源模态框中的类型下拉框选项从三种改为两种：
   - 移除 `<option value="sangfor">Sangfor</option>`
2. 将编辑数据源模态框中的类型下拉框选项同样改为两种

**验证**：
- 添加数据源时，类型下拉框只显示 `ARP SSH` 和 `ARP API`
- 防火墙数据源只能在"操作源"Tab中添加

---

### 方案2：统一审计日志分页导航为标准组件

**修改文件**：
- `frontend/src/pages/AuditLogs.tsx`

**修改内容**：
1. 将审计日志页面的自定义游标分页改为使用标准的 `Pagination.tsx` 组件
2. 使用后端提供的 offset 分页参数（`skip` 和 `limit`）而非 cursor 分页
3. 保留搜索和过滤功能，仅修改分页实现

**验证**：
- 审计日志页面的分页导航栏与其他页面风格一致
- 分页功能正常工作（首页、上一页、下一页、末页、页码跳转）

---

### 方案3：从备份文件中提取并恢复白名单数据

**步骤**：
1. 查找备份文件位置（backup 目录或 .manage/backup 目录）
2. 查看备份文件内容，确认 whitelist 表的结构和数据
3. 创建临时文件，提取白名单相关的 SQL 语句
4. 执行恢复操作

**验证**：
- 白名单数据成功恢复到数据库中
- 其他数据表不受影响

---

## 实施步骤

### 步骤1：修复数据源类型选项问题

```bash
# 编辑 DataSourcesTab.tsx，移除 sangfor 选项
vi frontend/src/components/datasources/DataSourcesTab.tsx
```

修改两处：
- 添加模态框（约第 565 行）
- 编辑模态框（约第 644 行）

---

### 步骤2：统一审计日志分页

```bash
# 编辑 AuditLogs.tsx，替换自定义分页为标准组件
vi frontend/src/pages/AuditLogs.tsx
```

需要修改的内容：
- 移除自定义的 cursor 分页逻辑
- 引入并使用 Pagination 组件
- 修改 API 调用参数，使用 skip/limit 替代 cursor

---

### 步骤3：恢复白名单数据

```bash
# 查找备份文件
find . -name "auto_pre_update_20260714_234325.sql"

# 提取白名单相关 SQL
grep -E "(CREATE TABLE.*whitelist|INSERT INTO.*whitelist)" backup.sql > whitelist_restore.sql

# 执行恢复
docker-compose exec db psql -U postgres -d tam -f whitelist_restore.sql
```

---

## 风险评估

| 问题 | 风险等级 | 风险描述 | 缓解措施 |
|------|---------|---------|---------|
| 问题1 | 低 | 无风险，仅修改前端展示 | 确保移除后不影响防火墙数据源管理 |
| 问题2 | 中 | 可能影响审计日志的深度分页性能 | 后端已支持 skip/limit，在数据量不大时性能可接受 |
| 问题3 | 低 | 备份文件可能不存在或格式不同 | 先检查备份文件内容再执行恢复 |

---

## 验证清单

- [ ] 数据源管理页面 ARP 数据源添加时类型下拉框只显示 ARP SSH 和 ARP API
- [ ] 防火墙数据源只能在"操作源"Tab中添加和管理
- [ ] 审计日志页面分页导航栏与其他页面风格一致
- [ ] 审计日志分页功能正常（首页、上一页、下一页、末页、页码跳转）
- [ ] 从备份文件中成功恢复白名单数据
- [ ] 恢复后白名单管理页面能正常显示恢复的数据

---

## 预计影响

- **问题1**：仅影响前端 UI，不影响后端 API
- **问题2**：影响前端审计日志页面的分页方式，后端 API 兼容两种分页方式
- **问题3**：仅影响数据库中的白名单数据，需谨慎操作

---

## 依赖关系

- 问题1 和问题2 可并行处理
- 问题3 需要先找到备份文件位置，然后执行恢复操作
