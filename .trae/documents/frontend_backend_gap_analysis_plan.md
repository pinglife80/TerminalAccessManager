# 后端已实现但前端未实现/实现不完整的功能审查报告（v2.0）

> 文档版本：v2.0  更新日期：2026-08-05
> 审查方式：逐文件代码阅读 + Grep 交叉验证 + 常量/接口比对

---

## 一、审查概述

### 审查范围
- **后端路由模块**：15 个（auth、auth_providers、ldap、backup、terminals、whitelist、blacklist、logs、stats、settings、data_sources、compliance_baselines、roles、notifications、system）
- **后端 API 端点**：100+ 个（通过 `@router.(get|post|put|delete|patch)` 逐一扫描）
- **前端页面**：18 个 TSX 页面
- **前端组件**：20+ 个 TSX 组件
- **前端 API 常量**：`constants.ts` 中 `API_ENDPOINTS` 共 69 个常量
- **前端路由**：`App.tsx` 中 17 条注册路由

### 审查结论分类
- **❌ 完全缺失**：后端 API 已实现 + 前端无任何调用或 UI
- **⚠️ 部分实现**：后端 API 已实现 + 前端有 UI 但缺少部分功能或使用不规范
- **✅ 已对齐**：前后端功能完整对齐

---

## 二、详细审查结果（v2.0 修正版）

### 2.1 ❌ 完全缺失的功能

#### (1) 合规配置子菜单（Compliance Configuration）
| 维度 | 详情 |
|------|------|
| **后端状态** | ✅ 完整实现 |
| **后端位置** | `backend/app/schemas/system_config.py` - `ConfigCategory.COMPLIANCE`、`ComplianceConfigResponse`、`AllConfigsResponse.compliance` |
| **后端 API** | `GET /settings/` 返回 compliance 分组；`PUT /settings/update` 支持更新 `compliance_confirm_threshold` |
| **前端状态** | ❌ 完全缺失 |
| **前端位置** | `frontend/src/pages/GeneralSettings.tsx`、`frontend/src/hooks/useTerminalData.ts` |
| **缺失详情** | ① `SECTION_FIELDS` 无 `compliance` 键（L27-L50）；② `flattenConfigs()` 不处理 `configs.compliance`（L53-L67）；③ `AllConfigs` 接口（`useTerminalData.ts` L351-L359）无 `compliance` 字段；④ 无合规配置 UI 区块 |
| **影响** | 合规状态翻转确认阈值（compliance_confirm_threshold）无法通过界面调整，运维需直接操作数据库 |

#### (2) 防火墙手动对账（Firewall Reconciliation）
| 维度 | 详情 |
|------|------|
| **后端状态** | ✅ 完整实现 |
| **后端位置** | `backend/app/api/v1/endpoints/system.py` L108-L123；`backend/app/services/firewall_reconciliation_service.py` |
| **后端 API** | `POST /system/firewall-reconciliation` |
| **前端状态** | ❌ 完全缺失 |
| **前端位置** | `constants.ts` 无 `FIREWALL_RECONCILIATION` 常量；无任何页面或按钮调用 |
| **缺失详情** | 无菜单入口、无按钮触发、无对账结果展示 |
| **影响** | 运维无法通过前端手动触发防火墙对账，需直接调用 API 或后端脚本 |

#### (3) 系统配置摘要 API
| 维度 | 详情 |
|------|------|
| **后端状态** | ✅ 完整实现 |
| **后端位置** | `backend/app/api/v1/endpoints/system.py` L55-L67 |
| **后端 API** | `GET /system/config`（返回 env、version、debug、log_level、email_enabled、metrics_enabled） |
| **前端状态** | ⚠️ 常量已定义但未使用 |
| **前端位置** | `constants.ts` L43 已定义 `SYSTEM_CONFIG: '/system/config'`，但前端从未调用 |
| **缺失详情** | SystemSettings 页面为导航卡片集合，未展示系统配置详情 |
| **影响** | 管理员无法在前端查看系统运行环境配置摘要 |

---

### 2.2 ⚠️ 部分实现的功能

#### (1) 通知单条日志重试
| 维度 | 详情 |
|------|------|
| **后端状态** | ✅ 完整实现 |
| **后端 API** | `POST /notifications/logs/{log_id}/retry`（L603-L618）、`POST /notifications/logs/retry-all`（L619-L628） |
| **前端常量** | ✅ 已定义 `NOTIFICATION_LOGS_RETRY`、`NOTIFICATION_LOGS_RETRY_ALL`（constants.ts L102-L103） |
| **前端"全部重试"** | ✅ 已在 `NotificationMonitor.tsx` L81-L92 实现 |
| **前端"单条重试"** | ❌ 缺失 |
| **缺失详情** | Notifications.tsx 日志标签页（L761-L793）每条日志仅有"归档"和"删除"按钮，无"重试"按钮（constants.ts L102 的 `NOTIFICATION_LOGS_RETRY` 未被任何代码引用） |
| **影响** | 无法对单条失败通知进行重试，只能通过 Monitor 页面批量重试 |

#### (2) LDAP API 常量未规范化
| 维度 | 详情 |
|------|------|
| **后端状态** | ✅ 完整实现 |
| **后端 API** | `POST /ldap/search`、`POST /ldap/import`、`GET /ldap/ous` |
| **前端常量** | ❌ 未在 `API_ENDPOINTS` 中定义 |
| **前端实现** | ⚠️ `LDAPImportModal.tsx`（L91、L109、L129、L172）使用内联字符串 `/ldap/ous`、`/ldap/search`、`/ldap/import` 调用 |
| **缺失详情** | 不符合项目 `constants.ts` 统一管理的规范 |
| **影响** | 维护成本高，修改 API 路径时容易遗漏 |

---

### 2.3 ✅ 已对齐的功能（经 v2.0 复核确认）

| 模块 | 后端 API | 前端页面/组件 | 状态 | 验证说明 |
|------|----------|--------------|------|----------|
| 认证登录/登出/刷新 | `/auth/*` | Login.tsx | ✅ | 登录页正常使用 |
| 用户管理 CRUD | `/auth/users/*` | Users.tsx | ✅ | 完整实现 |
| 用户锁定/解锁/密码重置 | `/auth/users/{id}/lock` 等 | Users.tsx | ✅ | 完整实现 |
| LDAP 用户导入 | `/ldap/*` | LDAPImportModal.tsx | ✅ | 功能可用（常量不规范） |
| 角色权限管理 | `/roles/*` | Roles.tsx | ✅ | 完整实现 |
| 认证提供商 | `/auth/providers/*` | AuthProviders.tsx | ✅ | 完整实现 |
| 终端列表/搜索/解封 | `/terminals/*` | Terminals.tsx | ✅ | 完整实现 |
| 终端导出 | `/terminals/export` | Terminals.tsx | ✅ | 完整实现 |
| 白名单 CRUD/导出 | `/whitelist/*` | Whitelist.tsx | ✅ | 完整实现 |
| 黑名单 CRUD/检查/导出 | `/blacklist/*` | Blacklist.tsx、Terminals.tsx | ✅ | 完整实现 |
| 审计日志 | `/logs/*` | AuditLogs.tsx | ✅ | 完整实现 |
| Dashboard 统计 | `/stats/`、`/stats/system-status` | Dashboard.tsx、useTerminalData.ts | ✅ | 完整实现 |
| 系统状态 | `/system/status` | GeneralSettings.tsx、Dashboard | ✅ | 已调用 |
| 系统设置（品牌/安全/速率/网络/调度/常规/邮件） | `/settings/*` | GeneralSettings.tsx、EmailSettings.tsx | ✅ | 完整实现 |
| 品牌资源上传 | `/settings/upload` | GeneralSettings.tsx | ✅ | 完整实现 |
| 种子数据/缓存失效/邮件测试 | `/settings/seed`、`/settings/invalidate-cache`、`/settings/email/test` | GeneralSettings.tsx、EmailSettings.tsx | ✅ | 完整实现 |
| 数据源 CRUD | `/data-sources/*` | DataSources.tsx | ✅ | 完整实现 |
| 数据源绑定 | `/data-sources/bindings/*` | DataSources.tsx / BindingsTab.tsx | ✅ | 完整实现 |
| 数据源禁用/删除预览 | `/data-sources/{id}/disable-preview`、`/data-sources/{id}/delete-preview`、`/data-sources/bindings/{id}/delete-preview` | DataSourcesTab.tsx、OperationSourceTab.tsx、BindingsTab.tsx | ✅ | L164、L226、L150、L110 均已调用 |
| 数据源测试/同步 | `/data-sources/{id}/test`、`/data-sources/{id}/sync` | DataSourcesTab.tsx、OperationSourceTab.tsx | ✅ | L195、L302、L180 均已调用 |
| 合规基线 CRUD | `/compliance-baselines/*` | ComplianceBaselinesTab.tsx | ✅ | 完整实现 |
| 合规基线删除预览 | `/compliance-baselines/{id}/delete-preview` | ComplianceBaselinesTab.tsx | ✅ | L154 已调用 |
| 合规基线测试/同步 | `/compliance-baselines/{id}/test`、`/compliance-baselines/{id}/sync` | ComplianceBaselinesTab.tsx | ✅ | L185、L251 已调用 |
| 合规检查/自动封堵/解封 | `/data-sources/compliance/*` | DataSources.tsx | ✅ | 完整实现 |
| 通知渠道 CRUD/测试 | `/notifications/channels/*` | Notifications.tsx | ✅ | 完整实现 |
| 通知模板 CRUD/预览 | `/notifications/templates/*` | NotificationTemplates.tsx | ✅ | 完整实现 |
| 通知规则 CRUD | `/notifications/rules/*` | NotificationRules.tsx | ✅ | 完整实现 |
| 通知日志查看/归档/删除/全部归档/清理 | `/notifications/logs/*` | Notifications.tsx | ✅ | 完整实现 |
| 通知全部重试 | `/notifications/logs/retry-all` | NotificationMonitor.tsx | ✅ | L81-L92 已实现 |
| 通知统计 | `/notifications/stats` | NotificationMonitor.tsx | ✅ | L55-L67 已调用 |
| 通知事件/通道类型列表 | `/notifications/events`、`/notifications/channel-types` | Notifications.tsx | ✅ | 完整实现 |
| 备份配置 CRUD | `/backup/config` | Backup.tsx | ✅ | 完整实现 |
| 备份执行/列表/下载/恢复/删除 | `/backup/*` | Backup.tsx | ✅ | 完整实现 |
| 备份内容预览 | `/backup/{filename}/contents` | Backup.tsx | ✅ | L224 在恢复流程中调用 |
| 白名单备份/恢复 | `/backup/whitelist/*` | Backup.tsx | ✅ | 完整实现 |
| 个人资料/密码修改 | `/auth/me/profile`、`/auth/me/password` | Profile.tsx | ✅ | 完整实现 |

---

## 三、前端 API 常量缺失/未使用汇总

### 3.1 已定义但未使用的常量
| 常量名 | 值 | 状态 |
|--------|-----|------|
| `SYSTEM_CONFIG` | `/system/config` | ⚠️ 已定义但无任何代码引用 |

### 3.2 应定义但使用内联字符串的 API
| 内联字符串 | 应定义常量名 | 使用位置 |
|-----------|------------|---------|
| `/ldap/ous` | `LDAP_OUS` | LDAPImportModal.tsx L91 |
| `/ldap/search` | `LDAP_SEARCH` | LDAPImportModal.tsx L109、L129 |
| `/ldap/import` | `LDAP_IMPORT` | LDAPImportModal.tsx L172 |

### 3.3 完全缺失的常量
| 缺失常量 | 值 | 状态 |
|----------|-----|------|
| `FIREWALL_RECONCILIATION` | `/system/firewall-reconciliation` | ❌ 完全缺失 |

---

## 四、建议实施计划（按优先级排序）

### 优先级 P0 — 核心功能缺失修复

#### 任务 1：实现合规配置子菜单
**涉及文件**：
- `frontend/src/hooks/useTerminalData.ts` — `AllConfigs` 接口增加 `compliance: ComplianceConfig` 字段；新增 `ComplianceConfig` 接口
- `frontend/src/pages/GeneralSettings.tsx` — `SECTION_FIELDS` 增加 `compliance: ['compliance_confirm_threshold']`；`flattenConfigs` 增加对 `configs.compliance` 的处理；渲染合规配置 SectionCard
- `frontend/src/i18n/locales/{zh,en,ja}.ts` — 新增合规配置相关翻译 key

#### 任务 2：实现通知单条日志重试
**涉及文件**：
- `frontend/src/pages/Notifications.tsx` — 日志标签页每行操作栏增加"重试"按钮，调用 `API_ENDPOINTS.NOTIFICATION_LOGS_RETRY`

#### 任务 3：实现防火墙对账功能
**涉及文件**：
- `frontend/src/lib/constants.ts` — 新增 `FIREWALL_RECONCILIATION: '/system/firewall-reconciliation'` 常量
- `frontend/src/pages/GeneralSettings.tsx` — 在操作区域或 Network 区块增加"防火墙对账"按钮，点击后触发并展示结果

### 优先级 P1 — 重要功能补充

#### 任务 4：实现 SystemSettings 页面增强
**涉及文件**：
- `frontend/src/pages/SystemSettings.tsx` — 调用 `API_ENDPOINTS.SYSTEM_CONFIG` 展示系统配置摘要（环境、版本、调试模式、日志级别等）

#### 任务 5：LDAP API 常量规范化
**涉及文件**：
- `frontend/src/lib/constants.ts` — 新增 `LDAP_OUS`、`LDAP_SEARCH`、`LDAP_IMPORT` 常量
- `frontend/src/components/LDAPImportModal.tsx` — 替换内联字符串为常量引用

---

## 五、v2.0 相对 v1.0 的修正说明

| v1.0 结论 | v2.0 修正 | 修正原因 |
|-----------|----------|---------|
| ❌ 通知日志重试（全部） | ✅ 已在 Monitor 页面实现 | 重新阅读 NotificationMonitor.tsx 确认 handleRetryAll 已实现（L81-L92） |
| ❌ 通知统计 API 调用 | ✅ NotificationMonitor 已调用 NOTIFICATION_STATS | L55-L67 确认 |
| ❌ 备份内容预览 | ✅ 恢复流程中已调用 BACKUP_CONTENTS | L224 确认在 handleRestore 中调用 |
| ⚠️ 合规基线删除预览 | ✅ 完整实现 | ComplianceBaselinesTab.tsx L154 确认 |
| ⚠️ 数据源禁用/删除预览 | ✅ 完整实现 | DataSourcesTab、OperationSourceTab、BindingsTab 均已调用 |
| ⚠️ 数据源手动测试/同步 | ✅ 完整实现 | 多个 Tab 均已正确绑定 |
| ❌ 合规基线删除预览利用 | ✅ 已充分利用 | 阅读确认已在删除前展示预览数据 |

**v2.0 新增发现**：
- 新增"通知单条日志重试"缺失（`NOTIFICATION_LOGS_RETRY` 常量已定义但未引用）
- 新增"LDAP API 常量未规范化"（功能可用但违反项目规范）
- 确认 `SYSTEM_CONFIG` 常量已定义但未使用

---

## 六、风险与注意事项

1. **合规配置缺失风险**：当前 `compliance_confirm_threshold` 配置项已在数据库中存在且正常工作（默认值 2），前端缺失仅影响 UI 配置能力，不影响后端业务逻辑
2. **通知单条重试缺失风险**：失败通知只能批量重试，灵活性不足
3. **防火墙对账缺失风险**：当防火墙数据与数据库不一致时，需手动通过 API 或后端脚本触发对账
4. **所有变更均为前端变更**，不涉及后端 API 修改，无数据库迁移风险

---

## 七、附录：审查方法

1. 使用 `Grep @router\.(get|post|put|delete|patch)\(` 扫描所有后端端点，获取完整 API 列表
2. 逐文件阅读 `api.py` 获取路由注册关系
3. 逐行阅读 `constants.ts` 获取所有前端 API 常量定义
4. 使用 `Grep` 交叉搜索 `NOTIFICATION_LOGS_RETRY`、`BACKUP_CONTENTS` 等常量的实际引用
5. 逐页面/组件阅读前端代码，验证每个后端 API 常量是否被正确引用
6. 阅读 `useTerminalData.ts` 的 `AllConfigs` 接口，验证配置分组覆盖完整性
7. 对比 `App.tsx` 路由注册与 `Sidebar.tsx`/`NAV_ITEMS` 导航结构
