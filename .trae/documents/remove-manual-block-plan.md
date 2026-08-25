# 移除手动封锁和解封业务逻辑 - 实施计划

## 1. 问题分析

### 1.1 业务需求
系统核心业务逻辑闭环应为：**合规自动判断 → 自动封锁（不合规）/ 自动解封（合规）**。黑名单的封锁和解封都不应有人为操作干预。

### 1.2 当前状态
经过全面代码审查，当前系统中存在以下手动封锁/解封入口：

| 层级 | 文件 | 入口 | 类型 |
|------|------|------|------|
| 前端 | `frontend/src/pages/Blacklist.tsx` | 黑名单页面解封按钮 | 解封 |
| 前端 | `frontend/src/pages/Terminals.tsx` | 终端管理页面解封按钮 | 解封 |
| 后端API | `backend/app/api/v1/endpoints/terminals.py` | `POST /terminals/block/{ip}` | 封锁 |
| 后端API | `backend/app/api/v1/endpoints/terminals.py` | `POST /terminals/unblock/{ip}` | 解封 |
| 后端API | `backend/app/api/v1/endpoints/blacklist.py` | `POST /blacklist/` | 封锁（已废弃） |
| 后端API | `backend/app/api/v1/endpoints/blacklist.py` | `DELETE /blacklist/{identifier}` | 解封 |
| 后端服务 | `backend/app/services/terminal_service.py` | `block_ip` | 封锁 |
| 后端服务 | `backend/app/services/terminal_service.py` | `unblock_ip` | 解封 |
| 后端服务 | `backend/app/services/terminal_service.py` | `delete_from_blacklist` | 解封 |

### 1.3 风险评估

| 风险 | 等级 | 说明 |
|------|------|------|
| 误操作风险 | 高 | 人为解封不合规终端会破坏安全策略 |
| 审计追踪困难 | 中 | 手动操作分散在多个入口，难以统一追踪 |
| 业务闭环破坏 | 高 | 手动干预会绕过合规判定流程 |
| 文档不一致 | 低 | 文档仍描述手动操作流程 |

---

## 2. 实施步骤

### 2.1 前端修改

#### 步骤2.1.1：黑名单管理页面 - 移除解封操作

**文件**: `frontend/src/pages/Blacklist.tsx`

**修改内容**:
- 删除 `handleRemoveBlacklist` 函数（第72-77行）
- 删除删除确认模态框（第453-490行）
- 删除表格中解封按钮的渲染（查找包含 `handleRemoveBlacklist` 的按钮代码）
- 保留查看详情功能
- 保留导出功能

**预期效果**: 黑名单页面仅展示被封锁终端信息，无任何解封操作按钮。

#### 步骤2.1.2：终端管理页面 - 移除所有解封操作

**文件**: `frontend/src/pages/Terminals.tsx`

**修改内容**:
- 修改 `getTerminalActions` 函数，移除所有 `canUnblock: true` 的情况
- 移除解封按钮的渲染逻辑
- 合规终端（`compliant`）不应有任何封锁/解封/加白操作
- 仅保留查看功能

**预期效果**: 终端管理页面仅展示终端信息和合规状态，无任何封锁/解封操作按钮。

### 2.2 后端修改

#### 步骤2.2.1：终端管理 API - 移除手动封锁/解封端点

**文件**: `backend/app/api/v1/endpoints/terminals.py`

**修改内容**:
- 删除 `POST /terminals/block/{ip_address}` 端点（第108-152行）
- 删除 `POST /terminals/unblock/{ip_address}` 端点（第155-181行）
- 删除相关的依赖导入

**预期效果**: 外部无法通过 API 手动封锁或解封终端。

#### 步骤2.2.2：黑名单 API - 移除手动封锁/解封端点

**文件**: `backend/app/api/v1/endpoints/blacklist.py`

**修改内容**:
- 删除 `POST /blacklist/` 端点（已废弃，但仍需移除）
- 删除 `DELETE /blacklist/{identifier}` 端点（第106-126行）
- 删除相关的依赖导入

**预期效果**: 外部无法通过 API 手动添加或删除黑名单条目。

#### 步骤2.2.3：终端服务 - 移除手动封锁/解封方法

**文件**: `backend/app/services/terminal_service.py`

**修改内容**:
- 删除 `block_ip` 方法（约第472-560行）
- 删除 `unblock_ip` 方法（约第600-695行）
- 删除 `delete_from_blacklist` 方法（约第700-750行）
- 检查并更新调用这些方法的代码（主要是自动合规流程中的调用）

**注意事项**: 需要确认自动合规流程中使用的是相同方法还是独立实现。根据代码审查，自动合规流程使用的是 `compliance_service.py` 中的 `_block_on_firewall` 和 `_unblock_on_firewall` 方法，与手动操作方法不同。

### 2.3 文档更新

#### 步骤2.3.1：用户操作手册

**文件**: `docs/user-guide.md`

**修改内容**:
- 删除第6.5节"解封终端"（第352-357行）
- 删除第6.6节"手动封堵与自动封堵的区别"（第360-368行）
- 更新第6.1节"黑名单概述"，明确说明黑名单由系统自动管理
- 更新第6.2节"黑名单列表"，移除"手动封堵/自动封堵"相关描述

#### 步骤2.3.2：快速入门指南

**文件**: `docs/quick-start-guide.md`

**修改内容**:
- 删除第5节"解封终端"（第59-65行）

#### 步骤2.3.3：业务工作流文档

**文件**: `docs/business-workflow.md`

**修改内容**:
- 删除第6章"手动封锁/解封流程"（约第340-380行）
- 更新状态机流转图，移除手动操作的状态转换

#### 步骤2.3.4：API 文档

**文件**: `docs/api.md`

**修改内容**:
- 删除 `POST /terminals/block/{ip_address}` 文档（约第800-840行）
- 删除 `POST /terminals/unblock/{ip_address}` 文档（约第840-880行）
- 删除 `POST /blacklist/` 文档（约第1170-1210行）
- 删除 `DELETE /blacklist/{identifier}` 文档（约第1210-1250行）

---

## 3. 依赖关系与注意事项

### 3.1 依赖检查

| 依赖项 | 说明 | 影响 |
|--------|------|------|
| `compliance_service.py` | 自动合规流程使用独立方法 | 无影响 |
| `data_source_service.py` | 删除数据源/绑定时自动解封 | 需要保留，这是系统自动操作 |
| `sangfor_service.py` | 防火墙操作底层方法 | 需要保留，供自动流程使用 |

### 3.2 安全考虑

- 移除手动操作后，所有封锁/解封操作均由系统自动执行
- 如需临时豁免，用户仍可通过白名单管理实现
- 白名单终端将获得"豁免"状态，不会被自动封锁

### 3.3 向后兼容性

- 移除的 API 端点需要在文档中明确标记为已移除
- 前端修改后，旧版本前端无法正常使用（但前端和后端应同步更新）

---

## 4. 验证方案

### 4.1 前端验证

1. **黑名单管理页面**:
   - ✅ 无解封按钮
   - ✅ 无删除确认模态框
   - ✅ 仅显示查看详情和导出功能

2. **终端管理页面**:
   - ✅ 合规终端无任何操作按钮
   - ✅ 不合规终端无封锁/解封按钮
   - ✅ 白名单终端无移出白名单按钮

### 4.2 后端验证

1. **API 测试**:
   - ✅ `POST /terminals/block/{ip}` - 返回 404 或 405
   - ✅ `POST /terminals/unblock/{ip}` - 返回 404 或 405
   - ✅ `POST /blacklist/` - 返回 404 或 405
   - ✅ `DELETE /blacklist/{id}` - 返回 404 或 405

2. **自动流程验证**:
   - ✅ 合规重算后，不合规终端自动封锁
   - ✅ 合规重算后，合规终端自动解封
   - ✅ 数据源删除时自动解封终端

### 4.3 数据库验证

1. **黑名单记录**:
   - ✅ 新记录的 `is_auto_blocked` 均为 `True`
   - ✅ 解封记录的 `unblocked_by` 均为 `system`

---

## 5. 回滚方案

如果修改后出现问题，可执行以下回滚步骤：

1. **前端**: 恢复 `Blacklist.tsx` 和 `Terminals.tsx` 中的操作按钮代码
2. **后端**: 恢复被删除的 API 端点和服务方法
3. **文档**: 恢复被删除的文档章节

---

## 6. 代码提交计划

| 提交顺序 | 提交信息 | 包含文件 |
|----------|---------|---------|
| 1 | `fix(frontend): remove manual unblock button from blacklist page` | `frontend/src/pages/Blacklist.tsx` |
| 2 | `fix(frontend): remove all block/unblock actions from terminals page` | `frontend/src/pages/Terminals.tsx` |
| 3 | `fix(backend): remove manual block/unblock API endpoints` | `backend/app/api/v1/endpoints/terminals.py`, `backend/app/api/v1/endpoints/blacklist.py` |
| 4 | `fix(backend): remove manual block/unblock service methods` | `backend/app/services/terminal_service.py` |
| 5 | `docs: remove manual block/unblock documentation` | `docs/user-guide.md`, `docs/quick-start-guide.md`, `docs/business-workflow.md`, `docs/api.md` |

---

## 7. 总结

本计划将全面移除系统中所有手动封锁和解封的业务逻辑入口，确保系统核心业务闭环（合规自动判断 → 自动封锁/解封）的完整性和一致性。修改涉及前端页面、后端 API、后端服务和文档四个层面，共计约 10 个文件。