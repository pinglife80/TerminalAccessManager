# 版本跟踪记录

> 文档版本：v3.2.0-r12 | 更新日期：2026-06-17
>
> 本文档记录 TerminalAccessManager 每个版本的详细发布过程，包括变更内容、提交记录、测试验证和发布操作。
>
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)，变更描述遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范。

---

## [Unreleased] - RBAC 权限控制

### 提交记录

| 提交 | 说明 |
|------|------|
| af1960c | feat(rbac): add RBAC data models, migration and role management API |
| 48735ac | feat(rbac): implement permission control across all endpoints and frontend |
| 82ec0e0 | docs(rbac): update role and access control documentation to v2.0 |
| 707eefb | fix(search): fix search returning empty results on whitelist/blacklist/audit-logs |
| 3c5b758 | fix(perf): resolve API blocking and improve rate limit config |
| 7b4a0dc | fix(rbac): enforce superadmin protection and single-role-per-user model |
| d7a5838 | fix(frontend): improve UX and fix CSP/307 redirect issue |
| 06dbe11 | fix(i18n): complete i18n coverage for zh/en/ja locales |
| 253acb6 | test: add RBAC tests and fix security test assertions |
| 9100a8d | fix(search): increase debounce delay from 300ms to 500ms across all pages |
| 2f2add5 | fix: prevent superadmin role modification and fix Users search flickering |
| 0b36d78 | docs: update RBAC documentation to v3.0 with current implementation |

---

## [v3.2.0-r12] - 2026-06-17

### 审计日志优化与生产就绪改进

#### 审计日志优化
- Action 命名统一为 verb_resource 格式（block_terminal, auto_block_terminal, change_role 等）
- 新增 resource_name 列，存储人类可读资源名称
- 审计日志搜索支持 keyset 分页（cursor 参数）
- CSV 导出新增 Resource Name 列
- 前端 AuditLogs.tsx 新增 action 分类体系和 resource_name 优先展示

#### 生产就绪改进
- Docker 安全加固：docker-compose.prod.yml（no-new-privileges, cap_drop:ALL, read_only）
- Docker 健康检查：所有服务添加 healthcheck 配置
- Sangfor API 指数退避重试：最多 3 次重试，指数等待
- N+1 查询优化：cleanup_expired_blacklist 和 batch_check_compliance 批量预加载
- 核心服务单元测试：22 个 compliance_service 测试用例

#### 部署模式统一
- deploy --dev 替代 --demo，自动设置 ENVIRONMENT 变量
- docker-compose 三层架构：base + dev/prod override
- Nginx 环境差异化：开发 HTTP+宽松限流 vs 生产 HTTPS+标准限速
- 生产环境禁止 mock generate

#### Mock 数据业务对齐
- 28 种 verb_resource action 覆盖所有业务场景
- JSON 格式 details 替代纯文本
- resource_name 字段完整设置
- firewall_tag 与 DataSourceBinding 绑定关系一致
- 自动封堵 blocked_by="system"

### 提交记录

| 提交 | 说明 |
|------|------|
| da420a4 | fix(audit): unify action naming, add resource_name for meaningful display |
| c65466b | chore: remove sangfor_api docs and todos.md from git tracking |
| 3ed025c | feat(production-readiness): P0-P3 improvements for production deployment |
| 7722146 | refactor(deploy): unify deployment modes to dev/prod, fix mock data business alignment |

### 文件变更
- `backend/app/models/log.py` — 新增 resource_name 列
- `backend/app/schemas/terminal.py` — AuditLogBase 新增 resource_name, AuditLogQuery 新增 cursor, 新增 CursorPaginatedResponse
- `backend/alembic/versions/008_audit_resource_name.py` — 新增 resource_name 列迁移
- `backend/alembic/versions/009_audit_keyset_index.py` — keyset 分页复合索引迁移
- `backend/app/api/v1/endpoints/auth.py` — action 命名统一 + resource_name 设置
- `backend/app/api/v1/endpoints/data_sources.py` — resource_name 设置
- `backend/app/api/v1/endpoints/logs.py` — keyset 分页 + CSV 导出新增列
- `backend/app/api/v1/endpoints/roles.py` — action 命名统一 + resource_name 设置
- `backend/app/api/v1/endpoints/settings.py` — resource_name 设置
- `backend/app/api/v1/endpoints/compliance_baselines.py` — resource_name 设置
- `backend/app/services/sangfor_service.py` — 指数退避重试
- `backend/app/services/terminal_service.py` — N+1 优化 + action 命名统一
- `backend/app/services/compliance_service.py` — N+1 优化 + action 命名统一
- `backend/tests/test_compliance_service.py` — 22 个单元测试
- `backend/cli.py` — Mock 数据业务对齐
- `docker-compose.yml` — 健康检查 + 资源限制 + 日志轮转
- `docker-compose.prod.yml` — 生产安全加固
- `docker-compose.dev.yml` — 开发环境 override
- `nginx/etc/conf.d/tam.conf` — 限速调整
- `nginx/etc/conf.d/tam.dev.conf` — 开发环境 Nginx 配置
- `manage.sh` — 部署模式统一 + ENVIRONMENT 自动设置 + mock 生产限制
- `frontend/src/pages/AuditLogs.tsx` — action 分类 + resource_name 展示 + cursor 分页
- `frontend/src/hooks/useTerminalData.ts` — cursor 分页适配
- `frontend/src/i18n/locales/zh.ts` — 新增 action 翻译
- `frontend/src/i18n/locales/en.ts` — 新增 action 翻译
- `frontend/src/i18n/locales/ja.ts` — 新增 action 翻译
- `.env.example` — 新增 ENVIRONMENT 变量
- `.gitignore` — 新增 docs/sangfor_api 和 docs/todos.md
- `docs/disaster-recovery.md` — 灾难恢复计划
- `docs/operations-runbook.md` — 运维操作手册

---

## [v3.2.0-r11] - 2026-06-16

### 综合审计修复

#### 核心业务逻辑修复
- 黑名单 `mac_address_normalized` 字段补全：封堵/解封操作同步写入标准化 MAC 列，确保 MAC 维度查询一致性
- 多防火墙解封原子性：`unblock_ip` 改为按 `firewall_tag` 逐个解封并独立处理异常，单个防火墙解封失败不影响其他防火墙
- 过期清理安全性：`cleanup_expired_blacklist` 增加 `mac_address` 维度匹配，避免同 IP 多终端误解封；Sangfor 解封失败时保留 Blacklist 记录并延长重试

#### 合规生命周期修复
- 手动解封触发合规重算：`unblock_ip` 解封后自动调用 `recalculate_all_compliance`，确保合规状态及时更新
- 统一解封行为：手动解封与自动解封行为对齐，均更新 Terminal 状态、清理 Blacklist 记录、重置合规状态

#### 文档一致性修复
- 32 项文档一致性修复：所有文档版本号统一至 v3.2.0-r11，修正版本号对齐、术语一致性、文档清单补全（logging-guide.md、git-workflow-guide.md）

---

## [v3.2.0-r10] - 2026-06-16

#### 新增
- 终端封堵绑定验证：终端封堵前强制检查绑定关系，无绑定时显示防火墙选择器和无绑定错误提示
- 数据源标签页绑定状态列：数据源列表新增绑定状态列，已禁用 ARP 数据源显示"合规状态已冻结"
- 启用无绑定数据源确认对话框：启用未绑定防火墙的 ARP 数据源时弹出确认提示

#### 改进
- 绑定关系下拉框包含已禁用数据源：ARP 和防火墙数据源下拉框现在包含已禁用的数据源，以 `[已禁用]` 后缀标识
- ARP 数据源禁用触发合规重置：禁用 ARP 数据源时自动重置关联终端 `compliance_status` 为 `unknown`

#### 提交记录

| 提交 | 说明 |
|------|------|
| be0a24d | feat: 终端封堵绑定验证+绑定状态列+禁用数据源合规重置 |

#### 文件变更
- `frontend/src/pages/Terminals.tsx` — 封堵前绑定检查，显示防火墙选择器和无绑定错误
- `frontend/src/components/datasources/BindingsTab.tsx` — ARP 和防火墙下拉框包含已禁用数据源（`[已禁用]` 后缀）
- `frontend/src/components/datasources/DataSourcesTab.tsx` — 新增绑定状态列，禁用 ARP 源显示"合规状态已冻结"，启用无绑定确认对话框
- `backend/app/api/v1/endpoints/data_sources.py` — ARP 数据源禁用时触发合规状态重置
- `backend/app/services/terminal_service.py` — 合规状态批量重置方法
- `frontend/src/i18n/locales/zh.ts` — 新增绑定状态、合规冻结、无绑定封堵提示翻译键
- `frontend/src/i18n/locales/en.ts` — 新增绑定状态、合规冻结、无绑定封堵提示翻译键
- `frontend/src/i18n/locales/ja.ts` — 新增绑定状态、合规冻结、无绑定封堵提示翻译键

---

## [v3.2.0-r9] - 2026-06-16

#### 新增
- 两阶段删除机制：数据源、绑定关系、合规基准删除前提供影响预览（delete-preview API）
- 安全删除：自动解封终端、清理黑名单、清理 Redis 缓存、触发合规重算
- 前端 DeletePreviewModal 组件：展示影响范围、操作清单、受影响统计
- 数据源和合规基准 tag 修改禁止（tag 为系统全局标识符）

#### 修复
- compliance_service.py 导入错误（app.models.audit_log → app.models.log）

#### 文件变更
- `backend/app/api/v1/endpoints/data_sources.py` — 新增 delete-preview 端点，修改删除端点
- `backend/app/api/v1/endpoints/compliance_baselines.py` — 新增 delete-preview 端点，修改删除端点，tag 修改禁止
- `backend/app/schemas/data_source.py` — 新增 DeletePreviewAffected、DeletePreviewResponse Schema
- `backend/app/services/data_source_service.py` — 新增 preview/safe delete 方法，tag 修改禁止
- `backend/app/services/compliance_service.py` — 修复导入错误
- `frontend/src/components/DeletePreviewModal.tsx` — 新建删除预览弹窗组件
- `frontend/src/components/datasources/DataSourcesTab.tsx` — 集成两阶段删除
- `frontend/src/components/datasources/BindingsTab.tsx` — 集成两阶段删除
- `frontend/src/components/datasources/ComplianceBaselinesTab.tsx` — 集成两阶段删除
- `frontend/src/i18n/locales/{zh,en,ja}.ts` — 新增 deletePreview 翻译
- `frontend/src/lib/constants.ts` — 新增 API 端点常量

---

## [v3.2.0-r8] - 2026-06-16

### Fixed

- `recalculate_all_compliance` 自动封堵/解封改为多防火墙路由（`_get_bound_firewall_tags`），与 `auto_block_non_compliant` 行为一致
- `recalculate_all_compliance` 自动封堵创建的 Blacklist 记录补全 `expires_at` 和 `blocked_by` 字段，避免永不过期
- `cleanup_expired_blacklist` Sangfor 解封失败时保留 Blacklist 记录（延长 30 分钟重试），避免本地与防火墙状态不一致
- `cleanup_expired_blacklist` Terminal 查询增加 MAC 维度匹配，避免同 IP 多终端误解封
- `cleanup_expired_blacklist` 完成后触发 `recalculate_all_compliance`，确保不合规终端及时重新封堵
- `unblock_ip` 增加 `mac_address` 参数，支持按 MAC 精确解封，避免同 IP 多终端误解封
- `auto_unblock_compliant` Terminal 查询增加 MAC 维度匹配
- `auto_block_non_compliant` / `auto_unblock_compliant` / `recalculate_all_compliance` 补全审计日志
- `block_ip` / `unblock_ip` 审计日志补充 `ip_address`（客户端 IP）字段
- `block_ip` / `unblock_ip` API 端点增加 `Request` 依赖注入，记录操作来源 IP

### Changed

- ComplianceService 新增 `_get_bound_firewall_tags`（多防火墙）、`_get_block_time`、`log_action` 方法

### 文档修复

- database.md：compliance_baselines 表定义从旧 7 字段修正为实际 11 字段，ER 图同步更新
- api.md：第 9 节合规基准端点全面重写（请求/响应体、权限码、业务规则）
- datasource-lifecycle.md：frozen/unfrozen 术语替换为 blocked/unblocked；第 8.4 节 Sangfor API 从旧 blockip 更新为 whiteblacklist API
- architecture.md：Redis 故障策略从 fail-open 修正为混合策略（token 黑名单/验证码 fail-closed，其余 fail-open）
- backend.md：Redis 故障策略同步修正
- RBAC.md：审计日志 action 值 block_ip/unblock_ip 修正为 block_terminal/unblock_terminal；锁定时长从 30 分钟修正为 15 分钟（可配置）

---

## [v3.2.0-r7] - 2026-06-16

### Changed

- Sangfor 数据源移除"同步"按钮：Sangfor 为推送型防火墙，无数据同步语义，前端按 `ds.type !== 'sangfor'` 条件隐藏同步按钮
- Sangfor 同步接口行为调整：`POST /data-sources/{id}/sync` 对 sangfor 类型不再调用 `test_connection`，改为返回"Sync is not applicable"提示信息

### 提交记录

| 提交 | 说明 |
|------|------|
| 8dae3d4 | fix(datasource): remove sync button for Sangfor firewalls |

### 文件变更列表

| 文件 | 变更 |
|------|------|
| frontend/src/components/datasources/DataSourcesTab.tsx | Sangfor 类型隐藏同步按钮 |
| backend/app/api/v1/endpoints/data_sources.py | sangfor 同步接口返回不适用提示 |

---

## [v3.2.0-r6] - 2026-06-16

### Added

- Terminal 模型新增 `firewall_tag` 字段，封堵操作时同步写入防火墙标签，解封时清除
- 数据库迁移脚本 `007_firewall_tag.py`：terminals 表新增 firewall_tag 列
- 终端管理搜索栏支持 `source` 和 `firewall_tag` 过滤（后端 TerminalQuery 新增 source_tag/firewall_tag 参数）
- 封堵/解封操作支持 `comments` 参数，写入 Terminal.comments 字段
- 审计日志分类体系补全：新增 `role`（角色管理）和 `compliance`（合规基线）分类
- 审计日志 action 枚举补全 15 个缺失项（login_failed、token_refresh、change_password、bind/unbind_datasource、role_change、assign_role、create/update/delete_role、create/update/delete_baseline、upload_branding、export_audit_logs）
- 审计日志详情 key 翻译映射（23 个 key：ip→IP地址、mac→MAC地址 等）

### Changed

- 终端管理操作按钮矩阵重构：compliant+unblocked 仅查看，non_compliant+blocked 仅查看，各状态组合操作明确
- 封堵/解封/移出黑名单操作新增确认对话框，支持 comment 填写
- 黑名单管理页面移除手动添加功能，定位为审计视图（封堵操作统一从终端管理发起）
- 审计日志 details 列从图标按钮改为 message 文本预览（点击展开完整 Modal）
- 审计日志统计卡片优化：移除"独立用户数"和"独立操作数"，替换为"安全事件"统计
- 审计日志 IP 列：系统操作（username=system）显示"系统"而非"-"
- 审计日志 resource_id 格式化：数字 ID 类型显示为"类型名 #ID"（如"用户 #3"）
- 白名单 comments 自动同步到终端（bypass 终端 comments 显示 `Whitelist: {comments}`）
- Comments 超长内容支持鼠标悬浮显示完整文本（title 属性）
- Dashboard 系统状态动态检测（Sangfor AF 和 ARP 数据源状态实时查询）

### Fixed

- `token_refresh`、`change_password`、`upload_branding` 操作 IP 地址未记录（`ip_address=None`）
- blocked 终端 `firewall_tag` 为空（封堵操作未写入 Terminal.firewall_tag）
- 封堵/解封操作未更新 Terminal.comments（手动封堵/解封缺少操作记录）
- 白名单 comments 与终端 comments 不一致（bypass 终端未同步白名单备注）

### 提交记录

| 提交 | 说明 |
|------|------|
| (pending) | feat: 终端操作矩阵重构+firewall_tag字段+审计日志优化+黑名单审计视图 (v3.2.0-r6) |

### 文件变更列表

| 文件 | 变更 |
|------|------|
| backend/app/models/terminal.py | 新增 firewall_tag 字段 |
| backend/app/schemas/terminal.py | TerminalQuery 新增 source_tag/firewall_tag；TerminalResponse 新增 firewall_tag |
| backend/app/api/v1/endpoints/terminals.py | block/unblock 新增 comments 参数；搜索新增 source_tag/firewall_tag |
| backend/app/api/v1/endpoints/auth.py | refresh_token/change_password 新增 Request 参数记录 IP |
| backend/app/api/v1/endpoints/settings.py | upload_branding_asset 新增 Request 参数记录 IP |
| backend/app/services/terminal_service.py | search_macs 新增过滤；block/unblock 写入 firewall_tag+comments |
| backend/app/services/compliance_service.py | 封堵/解封写入 firewall_tag；bypass 同步白名单 comments |
| backend/alembic/versions/007_firewall_tag.py | 新增迁移脚本 |
| frontend/src/pages/Terminals.tsx | 操作矩阵重构+确认对话框+搜索过滤+comments tooltip |
| frontend/src/pages/Blacklist.tsx | 移除手动添加功能 |
| frontend/src/pages/AuditLogs.tsx | 分类补全+详情预览+统计优化+key翻译 |
| frontend/src/pages/Dashboard.tsx | 系统状态动态检测 |
| frontend/src/hooks/useTerminalData.ts | TerminalSearchParams 新增字段 |
| frontend/src/i18n/locales/zh.ts | 新增 40+ 翻译键 |
| frontend/src/i18n/locales/en.ts | 新增 40+ 翻译键 |
| frontend/src/i18n/locales/ja.ts | 新增 40+ 翻译键 |

---

## [v3.2.0-r5] - 2026-06-15

### Added

- Sangfor AF API 完全重写：从临时 `blockip` API 迁移到 `whiteblacklist` 永久封堵 API
  - 封堵：`POST /api/v1/namespaces/public/whiteblacklist`（`type=BLACK`，永久生效）
  - 解封：`DELETE /api/v1/namespaces/public/whiteblacklist/{ip}`（按 IP 精确删除）
  - 查询：`GET /api/v1/namespaces/public/whiteblacklist?type=BLACK`
  - TAM 描述前缀机制（`TAM-{tag}-{reason}`）实现幂等操作和安全删除
  - `_sanitize_description` 过滤 AF 禁止的特殊字符
  - `_find_blacklist_entry` 封堵前查询，确保幂等性
  - Token 保活：`GET /api/v1/namespaces/public/keepalive`
  - 独立 `test_connection()` 方法，分步验证认证+API
- 合规基准多数据库类型支持：MSSQL（pyodbc+FreeTDS）、MySQL（aiomysql）、PostgreSQL（asyncpg）
- IPGuard OCULAR3 数据库解析：从 `AGENT.AGT_IP_MAC_STR` 字段提取 IP+MAC 映射
- IPGuard 同步后自动触发合规重算（`recalculate_all_compliance`）
- `scheduled_compliance_check` 发现 non_compliant 终端后自动触发封堵
- 封堵/解封操作更新 Terminal `comments` 字段，记录防火墙标签和操作信息
- `datasource-lifecycle.md` 新增第 16 章「数据源安全性评估」

### Changed

- 所有 Sangfor AF API URL 添加 `/api` 前缀（根因修复：缺少前缀导致 302 重定向）
- `_get_bound_firewall_tag` 改用 `DataSourceBinding` 表查询（修复字段名/值错误）
- `recalculate_all_compliance` 自动解封/封堵通过 `terminal.source_tag` 查找 `DataSourceBinding` 获取防火墙标签
- `batch_check_compliance` 移除 1000 条限制，始终返回 details
- `cleanup_expired_blacklist` 解封后重置 `compliance_status` 为 `unknown`
- ARP 采集更新已有终端时重置 `compliance_status` 为 `unknown`，确保重新评估
- `auto_unblock_compliant` 处理 `firewall_tag=None`：通过 `DataSourceBinding` 回退查询

### Fixed

- Sangfor AF 登录 302 重定向（API URL 缺少 `/api` 前缀）
- `_get_bound_firewall_tag` 使用错误字段名 `source_type`/`sangfor_firewall`（应为 `type`/`sangfor`）
- `recalculate_all_compliance` 读取不存在的 `terminal.firewall_tag` 属性
- `recalculate_all_compliance` 封堵后不创建 Blacklist 记录（导致后续无法自动解封）
- `batch_check_compliance` 超 1000 条时 `details=None` 导致 `AttributeError`
- Sangfor AF description 包含禁止字符（冒号等）导致添加黑名单失败
- UNFROZEN/FROZEN 状态值残留（`arp_collector_service.py`、`terminal_service.py`、`cli.py`、`terminals.py`）

### 提交记录

| 提交 | 说明 |
|------|------|
| TBD | feat(sangfor): rewrite Sangfor AF API with whiteblacklist permanent blocking |
| TBD | feat(compliance): add multi-database support for IPGuard baseline sync |
| TBD | fix(compliance): fix firewall binding lookup and Blacklist record creation |
| TBD | fix(compliance): remove 1000-entry limit in batch_check_compliance |
| TBD | fix(sangfor): sanitize description to remove AF forbidden characters |
| TBD | fix(terminal): replace UNFROZEN/FROZEN with UNBLOCKED/BLOCKED in all files |
| TBD | feat(scheduler): trigger compliance recalculation after IPGuard sync |
| TBD | feat(scheduler): trigger auto-block after scheduled compliance check |
| TBD | fix(cleanup): reset compliance_status to unknown after blacklist expiry |
| TBD | fix(arp): reset compliance_status on existing terminal update |

---

## [v3.2.0-r4] - 2026-06-15

### Added
- API 数据源响应解析扩展：支持 `arp`/`devices`/`records` 包装键和 `ipv4_address` 字段兼容
- API 数据源认证增强：新增 `header` 类型，支持自定义 Header 名+值（如 `X-Auth-Token`）
- 前端数据源配置：Auth Type 新增 "Custom Header" 选项，`header_name` 字段条件显示（`showWhen` 属性）
- 白名单增删后自动触发合规状态批量重算（`recalculate_all_compliance`）
- 合规重算联动封堵/解封：状态变更时自动调用防火墙 API

### Changed
- Terminal STATUS 字段精简：6 值（`active`/`inactive`/`frozen`/`pending`/`unfrozen`/`bypass`）→ 2 值（`blocked`/`unblocked`）
- Dashboard 统计字段精简：移除 `active`/`inactive`/`pending`，新增 `unblocked`
- 白名单添加不再删除终端记录，改为合规状态重算

### Fixed
- 白名单增删后终端合规状态和封堵状态不更新的问题

### Migration
- 数据库 `terminals` 表 `status` 字段：`frozen`→`blocked`，`unfrozen`→`unblocked`，其他遗留值→`unblocked`

### 提交记录

| 提交 | 说明 |
|------|------|
| TBD | feat(datasource): extend API response parsing and add header auth type |
| TBD | fix(compliance): recalculate compliance on whitelist changes |
| TBD | refactor(terminal): simplify status enum to blocked/unblocked |

---

## [v3.2.0-r3] - 2026-06-11

**发布类型**：Bug 修复 + 文案修正 | **合并方式**：Fast-forward

### 变更概要

修复数据源服务层多个 Bug（expunge 导致更新/删除失败、明文密码回写、定时任务未解密配置），SSH 采集从 paramiko 迁移到 netmiko，前端错误处理和合规状态标签修正。

### 变更明细

#### Bug 修复

| 变更项 | 文件 | 说明 |
|--------|------|------|
| SSH 采集库迁移 | `arp_collector_service.py` | paramiko → netmiko，支持自动分页、多设备类型回退（Huawei/H3C/Cisco） |
| update/delete expunge Bug | `data_source_service.py` | `update_data_source`/`delete_data_source` 不再通过 `get_data_source_by_id` 获取对象（expunge 导致 DetachedInstanceError），改为直接查询 |
| decrypt_config 明文回写 | `data_source_service.py` | 解密前先 `db.expunge(source)` 分离对象，防止明文密码在 commit 时回写数据库 |
| update_sync_status expunge Bug | `data_source_service.py` | 改为直接查询 DB，避免 expunge 后 session 不可用 |
| 定时任务未解密配置 | `compliance_service.py` | 3 处添加 `decrypt_config`：IPGuard 同步、防火墙封堵、防火墙解封 |
| ARP 采集 entries=0 状态未更新 | `arp_collector_service.py` | entries 为空时也调用 `update_sync_status(source.id, "success")` |
| 定时采集未解密配置 | `arp_collector_service.py` | `run_scheduled_collection` 添加 `decrypt_config(source.config)` |
| 前端 getErrorMessage 对象渲染 | `utils.ts` | 处理 `detail` 为对象（`{message, error_id}`）的情况，修复 React #31 错误 |

#### 文案修正

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 合规状态标签 | `en.ts`/`zh.ts`/`ja.ts` | `non_compliant`：已封禁/Blocked → 不合规/Non-compliant；`unknown`：待定 → 待判定 |

#### 文档更新

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 相似命令对比 | `manage-sh-reference.md` | 新增第九章：9 组相似命令差异化对比 |
| 数据源生命周期 | `datasource-lifecycle.md` | 新增完整数据源生命周期文档 |

### 影响文件

```
backend/app/services/arp_collector_service.py  | 113 ++++++++++++++---
backend/app/services/compliance_service.py      |  10 ++
backend/app/services/data_source_service.py     |  26 ++++-
frontend/src/lib/utils.ts                       |   2 +-
frontend/src/i18n/locales/en.ts                 |   2 +-
frontend/src/i18n/locales/ja.ts                 |   2 +-
frontend/src/i18n/locales/zh.ts                 |   4 +-
docs/manage-sh-reference.md                     | 134 ++++++++++++++++++
docs/datasource-lifecycle.md                    | new file
```

---

## [v3.2.0-r2] - 2026-06-11

**发布类型**：Bug 修复 + 功能增强 | **合并方式**：Fast-forward

### 变更概要

manage.sh 全面审查修复与功能增强，修复 6 项 Bug，增强容错机制和备份安全，新增 7 个运维命令和 4 组环境变量。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `be61e90` | fix | manage.sh 全面审查修复与功能增强 |

### 变更明细

#### Bug 修复

| 变更项 | 文件 | 说明 |
|--------|------|------|
| `log_ok` 未定义 | `manage.sh` | 3处 `log_ok` 改为 `log_success` |
| `backup-schedule disable` 管道语法 | `manage.sh` | 修复 `|| true` 优先级导致管道断裂 |
| 硬编码容器名 | `manage.sh` | `tam_db`/`tam_redis` 统一为 `dc exec -T`，`tam_admin` 改为 `get_env DB_USER` |
| ADMIN_PASSWORD 环境变量缺失 | `manage.sh` + `cli.py` | demo/prod/init 三处写入 .env |
| `_run_setup` 不填充 RBAC 数据 | `cli.py` | 新增 `_ensure_rbac_seed(db)` 调用，init 时自动种子 5 角色 + 29 权限 |
| backup/health 硬编码用户名 | `manage.sh` | 改为 `get_env "DB_USER"` |

#### 核心增强

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 破坏性操作备份机制 | `manage.sh` | `interactive_backup` 函数，clean/redis flush/migrate 增加备份选项 |
| 日志开关 | `manage.sh` | `--log` 全局参数 + `TAM_LOG_ENABLED` 环境变量，30天自动清理 |
| 容错机制加强 | `manage.sh` | `require_services` 自动启动选项 + `check_disk_space`/`check_db_connection` 预检查 |
| 备份信息展示 | `manage.sh` | `auto_backup` 显示备份文件路径和大小 |
| SQL 注入防护 | `manage.sh` | `logs-export` 命令参数转义单引号 |

#### 新增功能

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 密码重置 | `manage.sh` + `cli.py` | `password reset <username> [--password <pw>]` |
| 用户管理 CLI | `manage.sh` + `cli.py` | `user list` / `user unlock <username>` |
| 审计日志导出 | `manage.sh` | `logs-export [--days N] [--output file] [--username user] [--action action]` |
| RBAC 角色查看 | `manage.sh` + `cli.py` | `role list` / `role permissions` |
| 服务单独重建 | `manage.sh` | `rebuild frontend/backend/nginx` |
| IPGuard 配置 | `manage.sh` | 部署向导增加 IPGuard 和 SWITCH_PORT 配置步骤 |
| 备份轮转 | `manage.sh` | `BACKUP_RETAIN_COUNT` 环境变量控制保留数量 |
| 配置热重载区分 | `manage.sh` | 区分热重载和需重启的配置键 |

#### 新增环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | — | 自定义初始管理员密码 |
| `BACKUP_RETAIN_COUNT` | `0`（保留全部） | 备份保留数量 |
| `TAM_LOG_ENABLED` | `false` | manage.sh 操作日志开关 |
| `IPGUARD_*` / `SWITCH_PORT` | — | 部署向导新增配置项 |

#### 文档更新

| 文档 | 版本 | 更新内容 |
|------|------|---------|
| `docs/release-notes.md` | v3.2.0-r1 → v3.2.0-r2 | 新增 r2 条目 |
| `docs/backend.md` | v3.2.0-r1 → v3.2.0-r2 | CLI 章节补充新子命令 + setup 行为变更 |
| `docs/RBAC.md` | v3.2.0-r1 → v3.2.0-r2 | 修正过时方案 + 补充 CLI 运维操作 |
| `docs/logging-guide.md` | v3.2.0 → v3.2.0-r2 | 补充 --log/TAM_LOG_ENABLED/logs-export |
| `docs/architecture.md` | v3.2.0-r1 → v3.2.0-r2 | 补充新环境变量 |
| `docs/production-readiness-assessment.md` | v3.2.0-r1 → v3.2.0-r2 | 运维工具覆盖表更新 |
| `docs/database.md` | v3.2.0-r1 → v3.2.0-r2 | 备份轮转策略 + RBAC seed 行为 |
| `docs/branding.md` | v3.2.0-r1 → v3.2.0-r2 | 配置热重载/重启区分 |
| `docs/api.md` | v3.2.0-r1 → v3.2.0-r2 | CLI 替代方案引用 |

### 变更统计

- **2 个文件变更**，+799 / -46 行
- **manage.sh**: +753 / -41 行（6 项 Bug 修复 + 3 项核心增强 + 7 项新增功能）
- **backend/cli.py**: +46 / -5 行（RBAC seed + 5 个新子命令）

---

## [v3.2.0-r1] - 2026-06-10

**发布类型**：功能迭代 | **合并方式**：Fast-forward | **标签**：`v3.2.0`

### 变更概要

本次版本聚焦于日志体系完善，新增 Request-ID 链路追踪、时区全局控制、审计日志补全和前端日志基础设施。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `5842dab` | feat(logging) | 新增 Request-ID 链路追踪中间件 + 集中式日志配置 |
| `daa8f24` | feat(config) | 时区全局控制 + Docker 安全加固注释化 |
| `aad35e1` | feat(audit) | 审计日志补全 + 前端日志基础设施 |
| `4a33c1a` | docs | 文档更新至 v3.2.0 |

### 变更明细

#### 新增功能

| 变更项 | 文件 | 说明 |
|--------|------|------|
| Request-ID 链路追踪 | `backend/app/middleware/request_id.py` | RequestIDMiddleware + ContextVar，12 位 hex request_id，支持上游 X-Request-ID 透传 |
| 集中式日志配置 | `backend/app/core/logging_config.py` | loguru + InterceptHandler + _log_format() 动态注入 request_id + time.tzset() 时区控制 |
| 时区全局控制 | `config.py` / `docker-compose.yml` / `logger.ts` | TZ 配置项贯穿 5 个 Docker 服务 + PostgreSQL + 后端日志 + 前端日志 |
| 前端日志工具 | `frontend/src/lib/logger.ts` | 分级输出 + 内存缓冲 100 条 + localStorage 持久化 50 条 + 本地时区格式 |
| 前端全局错误监听 | `frontend/src/App.tsx` | window.error + window.unhandledrejection |
| 日志说明文档 | `docs/logging-guide.md` | 16 章节完整日志文档 |

#### 改进优化

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 请求日志增强 | `backend/app/middleware/logging.py` | 日志消息增加 req_id= 字段 |
| 审计日志补全 | `auth.py` / `compliance_baselines.py` / `data_sources.py` / `logs.py` / `settings.py` | 新增 login_failed/change_password/token_refresh/create_baseline/update_baseline/delete_baseline/bind_datasource/unbind_datasource/upload_branding/export_audit_logs 审计事件 |
| 后端日志统一 | `security.py` / `crypto.py` | logging.getLogger 改为 loguru logger |
| Docker 安全加固注释化 | `docker-compose.yml` | security_opt/cap_drop/read_only 注释，标注 Production hardening |
| 运维命令扩展 | `manage.sh` | 新增 logs-cleanup / logs-archive / audit-cleanup |
| Nginx 日志配置 | `nginx/etc/conf.d/tam.conf` | access_log / error_log 指令 |
| ErrorBoundary 日志 | `frontend/src/components/ErrorBoundary.tsx` | console.error 改为 logger.error |

#### 文档更新

| 文档 | 版本 | 更新内容 |
|------|------|---------|
| `docs/changelog.md` | v3.1.0 → v3.2.0 | 新增 [3.2.0] 条目 |
| `docs/backend.md` | v3.1.0 → v3.2.0 | 项目结构、中间件、配置、日志章节 |
| `docs/architecture.md` | v3.1.0 → v3.2.0 | 请求流程、日志架构、时区控制架构 |
| `docs/deployment.md` | v3.1.0 → v3.2.0 | 安全加固、TZ 配置、PG 时区 |
| `docs/database.md` | v3.1.0 → v3.2.0 | PostgreSQL 时区参数 |
| `docs/production-readiness-assessment.md` | v3.1.0 → v3.2.0 | 评分 8.6→8.7，Docker 安全策略说明 |
| `frontend/docs/implementation.md` | v3.1.0 → v3.2.0 | logger.ts、全局错误、时区说明 |
| `docs/logging-guide.md` | 新增 v3.2.0 | 16 章节完整日志文档 |

### 变更统计

- **27 个文件变更**，+2402 / -129 行
- **4 个新文件**：request_id.py、logging_config.py、logger.ts、logging-guide.md

### 验证结果

| 验证项 | 结果 |
|--------|------|
| Docker 构建后端 | ✅ 通过 |
| Docker 构建前端 | ✅ 通过 |
| 5 个服务启动 | ✅ Healthy |
| 后端日志时区 `+0800` | ✅ |
| 后端日志格式含 request_id | ✅ |
| 请求日志含 `req_id=` | ✅ |
| 响应头 `X-Request-ID` | ✅ |
| 响应头 `X-Response-Time` | ✅ |
| PostgreSQL 时区 `Asia/Shanghai` | ✅ |

### 发布操作

```bash
# 1. develop 分支提交（4 个 commit）
git add <files> && git commit  # ×4

# 2. 推送 develop
git push origin develop

# 3. 合并到 main
git checkout main
git merge develop              # Fast-forward

# 4. 打标签
git tag -a v3.2.0 -m "release: v3.2.0 — Request-ID链路追踪、时区全局控制、日志体系完善"

# 5. 推送 main + tag
git push origin main --tags

# 6. 切回 develop
git checkout develop
```

### 已知问题

| 问题 | 影响 | 状态 |
|------|------|------|
| Docker 安全加固项默认注释 | 开发环境安全限制降低，生产环境需手动取消注释 | 已标注 Production hardening 注释 |
| 前端 logger.ts 渐进式接入 | 仅 App.tsx/ErrorBoundary 使用，其他组件仍用 console | 后续迭代逐步替换 |

---

## [v3.1.0] - 2026-06-09

**发布类型**：安全加固 | **合并方式**：Fast-forward | **标签**：`v3.1.0`

### 变更概要

安全加固迭代，包括 Redis fail-open 降级、全局异常处理、Docker 安全策略、测试基础设施、CI/CD 配置和容器安全。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `5d13591` | release | v3.1.0 — 安全加固、测试基础设施、CI/CD、容器安全 |

### 变更明细

#### 新增功能

- Redis fail-open 降级策略：10 个 Redis 交互函数统一 try/except
- 全局异常处理器：HTTPException / ValidationError / Unhandled
- Docker 安全加固：security_opt / cap_drop / read_only / tmpfs
- CI/CD：GitHub Actions 测试 + 超时保护
- 测试基础设施：pytest-asyncio + conftest.py + 7 个测试文件
- LICENSE：MIT License
- Git 分支策略：main + develop + 分支保护规则
- Git 敏捷开发指导手册：docs/git-workflow-guide.md

#### 文档更新

7 个文档同步更新至 v3.1.0：changelog.md、backend.md、database.md、architecture.md、deployment.md、manage-sh-reference.md、frontend/docs/implementation.md

### 变更统计

- 多文件变更，详见 git diff v3.0.0..v3.1.0

---

## [v3.0.0] - 2026-06-08

**发布类型**：Bug 修复 | **合并方式**：— | **标签**：`v3.0.0`

### 变更概要

二次生产部署 bug 修复。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `20263ae` | fix | 二次生产部署bug修复 |

---

## [v2.5.0] - 2026-06-07

**发布类型**：功能迭代 | **合并方式**：— | **标签**：`v2.5.0`

### 变更概要

早期功能迭代版本。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `263d6eb` | — | v2.5.0 |
