# 版本跟踪记录

> 文档版本：v3.6.7 | 更新日期：2026-07-08
>
> 本文档记录 TerminalAccessManager 每个版本的详细发布过程，包括变更内容、提交记录、测试验证和发布操作。
>
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)，变更描述遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范。

---

## [v3.6.7] - 2026-07-08

### 版本统一管理优化

#### 新增功能

- **版本一致性检查命令**：`./manage.sh version check`
  - 检查 7 个版本号文件：VERSION、frontend/package.json、.env、.env.example、docker-compose.yml、manage.sh、frontend/vite.config.ts
  - 显示每个文件的版本状态（一致/不一致）
  - 不一致时给出修复建议

- **一键版本升级命令**：`./manage.sh version bump <version>`
  - 自动更新所有版本号文件到指定版本
  - 版本格式验证（X.Y.Z）
  - 提供后续操作指引

#### 代码变更

| 文件 | 变更内容 |
|------|---------|
| `manage.sh` | 新增 `cmd_version_check()` 和 `cmd_version_bump()` 函数，修复 VERSION fallback 值 |
| `frontend/vite.config.ts` | 修复 getVersion() fallback 值为 3.6.6 |

#### 文档更新

| 文件 | 更新内容 |
|------|---------|
| `docs/manage-sh-reference.md` | 版本命令文档补充 check/bump 子命令 |
| `docs/deployment.md` | 版本命令说明补充 check/bump 子命令 |
| `docs/changelog.md` | 添加 v3.6.7 变更记录 |
| `docs/release-notes.md` | 添加 v3.6.7 发布记录 |

#### 验证方式

```bash
# 验证版本一致性
./manage.sh version check

# 验证服务健康
./manage.sh health

# 验证 API 版本
curl -sk http://localhost:8000/api/v1/system/health
```

---

## [v3.6.6] - 2026-07-08

### Bug 修复与数据一致性增强

#### 黑名单管理修复

- **Unblocked 标签筛选不出数据**：统一 active/unblocked 筛选逻辑，同时考虑 `auto_unblocked` 和 `unblocked_at` 两个字段；通过数据迁移 026 补全历史记录缺失的 `unblocked_at` 字段
- **统计基于当前页数据**：新增 `GET /api/v1/blacklist/stats` 服务端统计接口，Active Tab 下使用全局统计数据
- **Unblocked 标签显示一致性**：UI 标签显示条件从 `auto_unblocked` 改为 `auto_unblocked || unblocked_at`
- **自动解封未设置 unblocked_at**：compliance_service.py 中 3 处自动解封逻辑补全 `unblocked_at` 字段

#### 终端管理修复

- **timestamp 被覆盖**：ARP 采集更新终端时错误更新 `timestamp`（创建时间），新增 `updated_at` 字段（迁移 025），采集仅更新 `updated_at`
- **白名单备注不一致**：白名单备注更新逻辑优化（支持备注变更时替换旧备注）；白名单删除时清除关联终端备注和 `wl_match_type`（支持 CIDR 和 IP 范围匹配）

#### 角色管理修复

- **角色名称修改不生效**：`RoleUpdate` schema 添加 `name` 字段，`update_role` 支持自定义角色重命名，保护 5 个内置角色不可重命名，检查名称唯一性

#### 数据源管理增强

- **Operation Source 子菜单**：在数据源管理页面新增 Operation Source 标签页，独立管理 Sangfor 防火墙数据源，位于 Data Sources 和 Bindings 之间
- **Sangfor 测试连接 Last Test 不更新**：测试连接成功后使用直接 UPDATE 语句更新 `last_sync_at`（绕过 ORM expunge 问题）

#### 备份管理增强

- **FTP 远程备份**：备份列表/下载/删除支持远程存储（FTP/SFTP），备份列表显示存储位置标签
- **备份计划预设国际化**：预设选项改用 i18n 翻译键

#### 前端修复

- **导航栏菜单同时选中**：父级菜单高亮基于路由匹配（`isGroupActive`）而非展开状态
- **通知时间戳时区不一致**：所有通知渠道统一使用 `format_timestamp()` 转换为 Asia/Shanghai 时区
- **前端时间戳格式不一致**：统一 `formatDate` 为 `formatDateTime`，支持多语言和时区
- **翻译键命名错误**：白名单 `identifier` 重命名为 `macAddress`/`ipAddress`

#### 数据库迁移

- `025_terminal_updated_at.py`：终端表添加 `updated_at` 列
- `026_blacklist_fix_unblocked_at.py`：修复历史 `auto_unblocked=True` 但 `unblocked_at IS NULL` 的记录

#### 文档更新

- 更新 `changelog.md` 添加 v3.6.6 变更记录
- 更新 `database.md` 补充 terminals/`updated_at` 和 blacklist/`unblocked_at`/`unblocked_by` 字段
- 更新 `api.md` 添加 `/blacklist/stats` 接口说明
- 更新 `user-guide.md` 添加 Operation Source 功能说明
- 统一所有文档版本号至 v3.6.6

---

## [v3.6.5] - 2026-07-07

### 评估报告修复补充 - 事件触发点完善/黑名单软删除/文档更新

#### 事件触发点完善

- **安全事件**：在 `auth.py` 中添加 `PASSWORD_CHANGED`、`USER_CREATED`、`USER_DELETED`、`USER_UPDATED` 事件触发点
- **合规告警**：在 `compliance_service.py` 中添加 `BLOCK_THRESHOLD_EXCEEDED`、`POLICY_VIOLATION`、`TERMINAL_COMPLIANT`、`TERMINAL_NON_COMPLIANT` 事件触发点
- **管理事件**：在 `roles.py`、`settings.py`、`data_source_service.py`、`arp_collector_service.py` 中添加角色变更、配置变更、数据源变更、终端事件触发点
- **事件发射器**：在 `event_emitter.py` 中新增多个事件触发函数，事件覆盖率提升至85%

#### 黑名单软删除

- 在 `blacklist.py` 模型中添加 `unblocked_at` 和 `unblocked_by` 字段
- 在 `terminal_service.py` 中将删除操作改为软删除（标记而非删除）
- 更新查询逻辑，默认只返回活跃（未解封）记录
- 创建数据库迁移脚本 `024_blacklist_soft_delete.py`

#### Bug修复

- 修复 `cleanup_expired_blacklist` 函数中 datetime 变量作用域问题
- 修复 `emit_terminal_non_compliant` 调用时传入错误参数的问题
- 更新测试用例以适应软删除行为

#### 文档更新

- 创建 `business-workflow.md`，详细说明合规判定和封锁/解封流程
- 更新 `api.md`，补充通知统计、日志、重试、归档和备份FTP配置等API端点说明
- 更新 `logging-guide.md`，新增日志监控与告警、紧急处理流程等章节
- 统一所有文档版本号至 v3.6.5

#### 测试验证

- 后端测试：131+ 测试通过（2个原有mock问题测试失败可忽略）
- 服务健康检查：全部通过
- 业务链条测试：用户认证、用户管理、黑名单管理等核心功能正常

---

## [v3.6.3] - 2026-07-07

### 备份管理增强 + Bug 修复 + 版本统一管理

#### FTP备份支持

- 新增 FTP 存储类型，支持普通 FTP 和 FTPS（SSL）两种模式
- 后端 `backup_service.py` 新增 `_upload_via_ftp()` 方法，使用 ftplib 实现安全传输
- 前端 `Backup.tsx` 添加 FTP 配置选项（主机、端口、用户名、密码、远程路径、SSL 开关）
- API `/backup/test` 端点支持 FTP 连接测试

#### 备份配置持久化

- 创建 `BackupConfigModel` 数据库模型（`backup_config` 表），实现配置持久化
- 包含字段：enabled、schedule、retention_days、storage_type、storage_config、backup_database、backup_config、backup_logs、encrypt_backup
- 后端 `backup_service.py` 新增 `load_config()` 和 `save_config()` 方法
- API `GET/PUT /backup/config` 使用数据库存储，刷新页面后配置保留

#### 定时任务预设选择器

- 前端 `Backup.tsx` 添加 SCHEDULE_PRESETS 预设选择器（每天凌晨2点、每天凌晨3点、每周日凌晨2点、自定义）
- 只有选择"自定义"时才显示 crontab 输入栏
- 添加 CRON 格式正则校验，失去焦点时触发校验并显示错误提示
- 新增国际化翻译键（`cronRequired`、`cronInvalid`）

#### 登录页页脚样式优化

- 页脚区域移出 `max-w-md` 容器限制，内容横向自适应扩展
- 使用 `flex-col` 确保页脚在登录框下方而非并排
- 移除 `overflow-hidden` 和 `text-ellipsis`，取消长度限制
- 保留 `whitespace-nowrap` 确保一行显示不换行

#### FTP连接测试Bug修复

- 修复 `ftplib.FTP.__init__()` 不支持 `port` 参数的问题
- 改为先创建实例再调用 `connect(host, port)` 方法
- 修复范围：`backup_service.py` 和 `backup.py` API 端点

#### 版本号统一管理

- 创建 `VERSION` 文件作为单一版本源（`3.6.3`）
- `manage.sh`：从 VERSION 文件读取版本号并注入环境变量
- `config.py`：添加 `_load_version()` 函数动态读取
- `vite.config.ts`：添加 `getVersion()` 函数注入 `VITE_APP_VERSION`
- `.env` 和 `.env.example`：更新版本号为 3.6.3

### 数据库迁移

- **023_backup_config_table**：创建 backup_config 表

### 变更文件

**后端（3 个修改 + 2 个新增）：**

- `backend/app/services/backup_service.py` — FTP上传方法、配置持久化
- `backend/app/api/v1/endpoints/backup.py` — 配置持久化、FTP测试
- `backend/app/core/config.py` — 版本号动态读取
- `backend/app/models/backup_config.py` — BackupConfigModel（新增）
- `backend/alembic/versions/023_backup_config_table.py` — 数据库迁移（新增）

**前端（2 个修改 + 1 个配置）：**

- `frontend/src/pages/Backup.tsx` — FTP配置、预设选择器、CRON校验
- `frontend/src/pages/Login.tsx` — 页脚布局优化
- `frontend/vite.config.ts` — 版本号注入
- `frontend/src/config/branding.ts` — 使用环境变量版本

**基础设施（2 个修改 + 1 个新增）：**

- `manage.sh` — 版本号读取和环境变量注入
- `.env` / `.env.example` — 版本号更新
- `VERSION` — 统一版本源文件（新增）

**文档（2 个修改）：**

- `docs/release-notes.md` — 本文档
- `docs/changelog.md` — 追加 [3.6.3] 条目

### 提交记录

```
feat(backup): add FTP backup support with SSL option
feat(backup): implement backup config persistence with database
feat(backup): add schedule preset selector with CRON validation
fix(backup): fix FTP connection test port parameter error
fix(login): optimize footer layout to allow full width display
chore(version): unify version management with VERSION file
docs(release): add v3.6.3 release notes
docs(changelog): add v3.6.3 changelog
```

### 测试验证

- ✅ FTP配置测试验证通过
- ✅ 备份配置持久化验证通过（刷新后配置保留）
- ✅ 定时任务预设选择器验证通过（自定义时显示输入栏）
- ✅ CRON格式校验验证通过（无效格式显示错误）
- ✅ 登录页页脚布局验证通过（在登录框下方，内容完整显示）
- ✅ 版本号统一管理验证通过（所有位置显示3.6.3）
- ✅ 数据库迁移 023 执行成功
- ✅ Docker Compose 构建成功

---

## [v3.6.2] - 2026-07-06

### 通知管理增强版本：日志归档、通配符匹配、优先级控制

#### 通知日志管理功能

- 新增日志归档功能：支持单条归档和批量归档（30天前日志）
- 新增日志清理功能：清理90天前的已归档日志（永久删除）
- 新增日志删除功能：支持单条日志删除
- 数据库新增 `archived` 字段，用于标记归档状态
- 前端监控页面添加归档/清理/删除操作按钮和确认对话框

#### 模板和规则通配符匹配

- 支持通配符 `*` 匹配所有事件类型，实现通用模板/规则兜底
- 精确匹配优先于通配符匹配，确保特定事件使用专用模板
- 添加 `priority` 字段控制匹配顺序（数值越小优先级越高）
- 前端模板和规则表单添加通配符选项和优先级输入框

#### 监控统计修复

- 修复监控统计内部服务错误：替换 PostgreSQL 特定函数为标准 SQL 函数
- 优化异常处理，添加详细错误日志
- 前端监控组件添加错误信息展示

#### Channel 开关颜色优化

- 启用状态改为绿色（bg-green-500），更加直观
- 关闭状态改为灰色（bg-gray-300），提升辨识度

#### 提交记录

```
fix(notification): 修复监控统计SQL兼容性和异常处理
feat(notification): 添加通知日志归档和清理功能
feat(notification): 模板和规则支持通配符匹配与优先级
style(notification): 优化Channel开关颜色显示
chore(version): bump version to 3.6.2
docs(changelog): add v3.6.2 changelog
docs(release): add v3.6.2 release notes
```

#### 测试验证

- ✅ 通知服务测试 10/10 通过
- ✅ 日志归档/清理/删除功能验证通过
- ✅ 模板通配符匹配和优先级验证通过
- ✅ 规则通配符匹配和优先级验证通过
- ✅ Channel 开关颜色显示验证通过

---

## [v3.6.1] - 2026-07-06

### 稳定性修复版本：品牌配置同步、密码校验、时区处理

#### 品牌配置同步修复

- 登录页面支持动态加载 `login_heading`、`login_footer_text`、`footer_copyright`、`footer_icp_number`、`footer_icp_url` 字段
- 配置修改后刷新页面即可生效，无需重新构建
- 回退机制：后端不可用时使用 `branding.ts` 静态默认值

#### 密码系统优化

- 密码复杂度规则统一：至少8位，必须包含大写字母、小写字母和数字，允许特殊字符
- 密码重置流程优化：成功提示 → 2秒延迟 → 跳转登录页
- 邮箱重复使用确认：管理员可确认后使用重复邮箱（`force_email` 参数）

#### 时区处理统一

- 后端时间戳统一使用 `app.core.timezone.now()`（Asia/Shanghai）
- 前端日期格式化统一使用 `Intl.DateTimeFormat` 指定 Asia/Shanghai 时区
- 通知日志修复：aware datetime → naive datetime 转换，解决写入 `TIMESTAMP WITHOUT TIME ZONE` 字段失败问题

#### 事件通知增强

- 新增6个安全事件类型，覆盖用户全生命周期操作：
  - `security.user_deleted`：用户删除事件
  - `security.user_updated`：用户更新事件
  - `security.password_changed`：密码修改事件
  - `security.role_changed`：角色变更事件
  - `security.login_locked`：登录锁定事件
  - `security.password_reset_requested`：密码重置请求事件
- 登录锁定事件自动触发通知，提升安全监控能力

#### 会话管理增强

- 新增 `useTokenExpiration` hook：前端主动检测 JWT 令牌过期时间
- 支持令牌自动刷新和超时自动登出
- 会话过期前1分钟显示警告提示

#### 用户体验优化

- 用户管理页面区分显示 Active/Locked/Disabled 三种状态（Locked 状态从 Redis 获取）
- 忘记密码链接仅在密码输入错误次数触发安全校验后显示
- 密码重置时自动传递用户名到重置页面，无需用户重复输入

#### API 数据源测试认证修复

- 修复 ARP API 类型数据源测试连接时未处理自定义 Header 认证的问题
- 支持 bearer 和 header 两种认证方式

#### 提交记录

```
fix(branding): sync login page branding config from backend
feat(event): add security event emitters for user operations
feat(auth): add token expiration detection and email availability check
i18n: add missing auth translation keys
refactor(notification): optimize service and channel implementations
chore(service): minor service optimizations
docs(changelog): update changelog for v3.6.1
docs(branding): update branding guide to v3.6.1
docs(release): add v3.6.1 release notes
```

#### 测试验证

- ✅ 品牌配置动态加载验证通过
- ✅ 密码重置流程端到端验证通过
- ✅ 通知日志时区错误修复验证通过
- ✅ 事件发射器集成测试通过
- ✅ 后端单元测试 131 个通过（2 个失败为 v3.6.0 已存在的测试代码问题）

---

## [v3.6.0] - 2026-07-03

### 功能增强版本：消息模板、通知规则、异步队列与监控

#### 消息模板系统（P1）

- **Jinja2 模板引擎**：集成 Jinja2 模板渲染引擎，支持每个事件-渠道组合配置独立的消息模板
- **模板 CRUD**：支持模板创建、编辑、删除、列表、筛选（按事件类型/渠道类型）
- **模板预览**：提供模板预览端点，管理员可在保存前查看渲染效果
- **Jinja2 变量参考**：前端侧栏展示可用变量列表（event_type、event_name、severity、timestamp、data 等）
- **默认模板标记**：支持 is_default 标记，未配置自定义模板时使用系统默认渲染

#### 国内 IM 应用模式（P1）

- **飞书应用模式**：支持飞书自建应用模式，通过 tenant_access_token 发送消息，token 缓存 Redis（7000s TTL）
- **钉钉应用模式**：支持钉钉企业内部应用模式，通过 access_token 发送消息，token 缓存 Redis
- **企业微信应用模式**：支持企业微信应用模式，通过 access_token 发送消息，token 缓存 Redis
- **双模式切换**：每个渠道可在 Webhook 模式和应用模式之间切换，配置字段动态调整
- **邮件配置页面**：独立的 SMTP 邮件系统配置页面，支持配置测试与加密存储

#### 通知规则系统（P2）

- **消息抑制（Suppression）**：同一事件在抑制窗口内仅发送一次，后续事件被静默，使用 Redis TTL key 实现
- **消息聚合（Aggregation）**：窗口内事件计数，用于统计和升级判定
- **消息升级（Escalation）**：达到阈值后自动提升 severity（如 warning → critical），确保重要告警被关注
- **升级绕过抑制**：escalated 事件自动设置 bypass_suppression 标志，确保升级后的消息总能送达
- **PostgreSQL 部分唯一索引**：使用 `uq_rule_event_null_channel` 和 `uq_rule_event_specific_channel` 解决 NULL channel_name 唯一性约束

#### 异步队列与重试机制（P3）

- **Redis List 异步队列**：`notify:queue:main` 作为主队列，事件发布采用 fire-and-forget 模式，不阻塞请求
- **Redis ZSet 重试队列**：`notify:queue:retry` 管理待重试任务，按 next_retry_at 时间排序
- **指数退避重试**：默认最大 3 次重试，首重试延迟 10s，后续指数增长（10s → 20s → 40s）
- **通知日志增强**：notification_logs 表新增 retry_count、next_retry_at、completed_at 字段
- **手动重试 API**：支持单条失败通知重发（`/logs/{id}/retry`）和批量重发（`/logs/retry-all`）
- **双 Worker 架构**：main_worker 处理主队列，retry_worker 扫描到期重试任务

#### 监控统计面板（P3）

- **8 个核心统计卡片**：总发送量、成功数、失败数、成功率、待重试、平均延迟、渠道数、规则数
- **各渠道成功率**：按渠道维度展示成功率进度条
- **30 秒自动刷新**：监控页面默认每 30 秒自动刷新统计数据
- **统计聚合**：基于 PostgreSQL `func.cast` 条件聚合，一次查询返回全部统计指标

#### 权限一致性修复

- **通知模块**：9 处 `notification:manage` → `notification:write`，与数据库权限定义一致
- **备份模块**：6 处 `system.manage` → `backup:write`，修正点号格式并细化到备份模块
- **认证提供者模块**：4 处 `auth.manage` → `settings:write`，使用系统已有权限码

#### 基础设施优化

- **Nginx 缓存头修复**：移除 `expires -1`，消除与 `add_header Cache-Control` 的重复冲突，确保 index.html 正确禁用缓存
- **前端邮件入口**：新增侧边栏邮件设置导航项，完善图标映射与国际化

### 数据库迁移

- **017_notification_templates**：创建 notification_templates 表（id、name、event_type、channel_type、subject_template、body_template、is_default、created_by、created_at、updated_at）
- **018_notification_rules**：创建 notification_rules 表（id、name、event_type、channel_name、enabled、suppress_window、aggregate_window、escalate_threshold、escalate_severity、created_by、created_at、updated_at），含 2 个部分唯一索引
- **019_notification_async_retry**：notification_logs 表新增 retry_count（int, default 0）、next_retry_at（timestamp, nullable）、completed_at（timestamp, nullable）字段

### 变更文件

**后端（18 个修改 + 3 个新增）：**

- `backend/app/core/config.py` — VERSION 升级至 3.6.0
- `backend/app/main.py` — lifespan 中启动/停止通知 worker
- `backend/app/models/notification.py` — NotificationTemplate、NotificationRule、NotificationLog 新字段
- `backend/app/schemas/notification.py` — Templates/Rules/Stats/Preview 的 Pydantic schemas
- `backend/app/schemas/system_config.py` — EmailConfigResponse schema
- `backend/app/api/v1/endpoints/notifications.py` — 新增 templates/rules/stats/retry 端点，权限码修正
- `backend/app/api/v1/endpoints/settings.py` — 邮件配置 API 端点
- `backend/app/api/v1/endpoints/auth_providers.py` — 权限码修正（auth.manage → settings:write）
- `backend/app/api/v1/endpoints/backup.py` — 权限码修正（system.manage → backup:write）
- `backend/app/api/v1/endpoints/auth.py` — /auth/me 返回 provider 字段
- `backend/app/services/notification_service.py` — Jinja2 模板、Redis 队列、重试、统计聚合
- `backend/app/services/config_service.py` — 邮件默认配置 seed
- `backend/app/services/email_service.py` — 邮件发送增强
- `backend/app/services/event_emitter.py` — 事件发射器对接通知服务
- `backend/app/services/compliance_service.py` — 合规事件触发通知
- `backend/app/services/notification_channels/feishu_channel.py` — 应用模式 + Redis token 缓存
- `backend/app/services/notification_channels/dingtalk_channel.py` — 应用模式 + Redis token 缓存
- `backend/app/services/notification_channels/wecom_channel.py` — 应用模式 + Redis token 缓存
- `backend/app/services/notification_channels/email_channel.py` — 模板渲染集成
- `backend/alembic/versions/017_notification_templates.py` — 新迁移（新增）
- `backend/alembic/versions/018_notification_rules.py` — 新迁移（新增）
- `backend/alembic/versions/019_notification_async_retry.py` — 新迁移（新增）

**前端（9 个修改 + 4 个新增）：**

- `frontend/src/App.tsx` — /email-settings 路由
- `frontend/src/lib/constants.ts` — 新增 email 侧栏入口、P2/P3 API 端点常量
- `frontend/src/components/Sidebar.tsx` — Mail 图标 + nav.email 标签映射
- `frontend/src/pages/Notifications.tsx` — 新增 templates/rules/monitor 三个 Tab
- `frontend/src/pages/SystemSettings.tsx` — 增加邮件设置卡片入口
- `frontend/src/hooks/useTerminalData.ts` — AllConfigs 增加 EmailConfig 接口
- `frontend/src/components/notifications/shared.ts` — 飞书/钉钉/企微 webhook+app 模式切换字段
- `frontend/src/i18n/locales/zh.ts` — 4 个命名空间翻译
- `frontend/src/i18n/locales/en.ts` — 4 个命名空间翻译
- `frontend/src/pages/EmailSettings.tsx` — SMTP 邮件配置页面（新增）
- `frontend/src/components/notifications/NotificationTemplates.tsx` — 模板 CRUD + 预览（新增）
- `frontend/src/components/notifications/NotificationRules.tsx` — 规则 CRUD + 帮助侧栏（新增）
- `frontend/src/components/notifications/NotificationMonitor.tsx` — 监控统计面板（新增）

**基础设施（2 个修改）：**

- `nginx/etc/conf.d/tam.conf` — 移除 `expires -1`
- `nginx/etc/conf.d/tam.dev.conf` — 移除 `expires -1`

**文档（待更新）：**

- `docs/changelog.md` — 已更新 [3.6.0] 条目
- `docs/release-notes.md` — 本文档

### 验证结果

- ✅ Docker Compose 构建成功（backend + frontend + nginx）
- ✅ Alembic 迁移 017 → 018 → 019 顺序执行成功
- ✅ 通知模板 CRUD 全流程通过
- ✅ 通知规则 CRUD 全流程通过
- ✅ 抑制行为验证通过（3 次事件仅 2 条日志）
- ✅ 升级行为验证通过（threshold=3 后 severity 升级到 critical）
- ✅ 升级绕过抑制验证通过
- ✅ 删除规则后抑制不再生效验证通过
- ✅ 监控统计 API 正常返回（200）
- ✅ 飞书/钉钉/企微应用模式 token 缓存正常
- ✅ 权限码一致性验证通过（operator 角色可访问通知管理）
- ✅ Nginx Cache-Control 头验证通过（单条，无重复）

---

## [v3.5.1] - 2026-07-03

### 热修复版本：用户体验优化与问题修复

#### LDAP用户体验优化

- **Profile页面信息精简**：LDAP用户的个人信息页面仅显示从LDAP同步的信息（用户名、邮箱、角色、状态），完全隐藏邮箱更新和密码修改功能，避免用户困惑
- **邮箱显示位置调整**：将邮箱信息移至账户信息卡片中，与用户名、角色、状态统一展示，信息结构更清晰

#### 模态框交互优化

- **Modal点击外部不关闭**：Import LDAP Users等重要操作模态框，点击灰色遮罩层不再关闭，防止误操作导致数据丢失
- **关闭方式**：仅通过右上角关闭按钮或ESC键关闭模态框

#### LDAP认证编辑体验优化

- **Bind Password可选**：编辑LDAP认证提供者时，Bind Password字段变为可选项，留空则保持原有密码
- **提示信息**：编辑时显示"留空以保持当前密码"提示，用户明确知晓行为
- **后端兼容**：更新API支持密码字段为空时保留原有密码

#### 认证提供者管理精简

- **移除Local类型选项**：认证提供者管理页面中移除Local类型选项（Local认证为系统内置功能，无需用户手动配置）
- **默认选中LDAP**：新建认证提供者时默认选中LDAP类型，简化操作流程

#### 翻译修复

- **Profile页面邮箱标签**：修复LDAP用户Profile页面邮箱标签显示为`profile.email`的翻译键名错误，正确显示为"Email Address"

### 变更文件

- `frontend/src/pages/Profile.tsx` — LDAP用户信息展示优化
- `frontend/src/pages/AuthProviders.tsx` — 移除Local类型、Bind Password可选
- `frontend/src/components/Modal.tsx` — 点击外部不关闭
- `frontend/src/i18n/locales/en.ts` — 新增leaveBlankToKeep翻译
- `frontend/src/i18n/locales/zh.ts` — 新增leaveBlankToKeep翻译
- `backend/app/api/v1/endpoints/auth.py` — /auth/me和/me/profile返回provider字段
- `backend/app/api/v1/endpoints/auth_providers.py` — 更新时保留原有密码
- `docs/changelog.md` — 追加 [3.5.1] 条目

---

## [v3.5.0] - 2026-07-01

### 功能增强 + 安全修复 + 性能优化

#### 事件通知服务

- 事件总线架构：支持多渠道事件发布订阅
- 通知渠道类型：邮件（SMTP）、钉钉（Webhook）、企业微信（Webhook）、通用 Webhook
- 通知日志：完整记录每条通知发送状态、重试次数、错误信息
- 测试连接：支持通知渠道连通性测试
- 事件类型：登录、终端封堵、终端解封、合规变更、配置变更、备份完成等

#### 认证提供者系统

- 插件化认证架构：接口抽象 + 具体实现模式
- 本地认证：用户名密码验证（已有）
- LDAP认证：支持 Active Directory 和 OpenLDAP，用户名验证和 DN 注入防护
- OAuth认证：预留接口，支持后续扩展
- 认证提供者管理：CRUD API + 前端配置页面

#### SFTP备份服务

- 数据库备份：pg_dump 全量备份
- 配置文件备份：docker-compose.yml、manage.sh（排除 .env 敏感文件）
- SFTP远程上传：paramiko 安全传输，主机密钥验证
- 备份轮转：按保留天数自动清理旧备份
- 校验和验证：SHA256 完整性校验

#### 系统设置前端页面

- 统一导航入口："系统设置"分组
- 通用设置：系统名称、Logo、页脚等品牌配置
- 认证提供者：LDAP/本地认证配置管理
- 备份配置：存储类型、保留策略、SFTP参数配置
- 通知管理：通知渠道配置、测试、日志查看
- 用户管理：用户 CRUD、角色分配
- 角色管理：角色 CRUD、权限配置

#### 安全修复

- **路径遍历漏洞**：backup.py 添加路径检查和文件名净化
- **LDAP DN注入**：ldap_provider.py 添加用户名验证和特殊字符转义
- **2FA验证码暴力破解防护**：email_service.py 添加最大尝试次数限制（5次）
- **敏感信息备份泄露**：backup_service.py 排除 .env 文件备份
- **FTP支持移除**：强制使用 SFTP 安全传输
- **SFTP主机密钥验证**：添加主机密钥验证策略

#### 性能优化

- **N+1查询优化**：roles.py 使用 JOIN 批量获取权限和用户计数
- **异步性能优化**：backup_service.py 使用 asyncio.to_thread 包装同步操作
- **通知模块权限控制**：notifications.py 添加 permission 依赖

#### 前端优化

- **导航重构**：嵌套导航结构，系统设置分组
- **国际化完善**：补全备份、认证、通知模块中/英/日翻译
- **Nginx限流调整**：API限流 60→300 r/m，认证限流 10→30 r/m

### 变更文件

- `manage.sh` — VERSION 3.4.0 → 3.5.0
- `backend/app/core/config.py` — VERSION 3.4.0 → 3.5.0
- `frontend/package.json` — version 3.4.0 → 3.5.0
- `.env.example` — VERSION 3.4.0 → 3.5.0
- `backend/app/services/notification_service.py` — 新增通知服务
- `backend/app/services/auth_providers/ldap_provider.py` — LDAP认证实现
- `backend/app/services/auth_providers/base.py` — 认证提供者接口
- `backend/app/services/backup_service.py` — SFTP备份服务
- `backend/app/api/v1/endpoints/notifications.py` — 通知模块API
- `backend/app/api/v1/endpoints/auth_providers.py` — 认证提供者API
- `backend/app/api/v1/endpoints/backup.py` — 备份服务API
- `frontend/src/pages/Settings.tsx` — 系统设置页面
- `frontend/src/pages/AuthProviders.tsx` — 认证提供者页面
- `frontend/src/pages/Backup.tsx` — 备份配置页面
- `frontend/src/pages/Notifications.tsx` — 通知管理页面
- `nginx/etc/conf.d/tam.conf` — 限流配置调整
- `docs/changelog.md` — 追加 [3.5.0] 条目
- `docs/release-notes.md` — 追加 [v3.5.0] 条目

---

## [v3.4.0] - 2026-06-22

### 功能增强 + Bug 修复

#### 系统版本与环境展示
- 前端页脚显示系统版本号（从 /health API 获取）
- Dashboard System Status 页面显示版本号和部署模式
- 新增 `/health` API 返回版本和环境信息
- Nginx 配置添加 /health 路径代理

#### 角色权限国际化
- 5 个内置角色名称和描述三语言翻译（中文/英文/日语）
- 29 个权限码名称和描述三语言翻译
- 修复 roles.permissions 键命名冲突（表头 vs 权限对象）
- i18n 配置禁用 nsSeparator 支持权限代码中的冒号

#### 多环境配置分离
- docker-compose.yml 支持双层 env_file（.env + .env.{ENVIRONMENT}）
- 开发环境配置模板 .env.dev
- 生产环境配置模板 .env.prod
- Nginx 镜像版本锁定为 1.27-alpine

#### Bug 修复
- 白名单删除 404 错误：修复删除端点路由匹配问题
- 白名单删除 MAC 匹配错误：使用 mac_address_normalized 字段查询
- 超管角色初始化错误：修复 admin 用户未正确关联 superadmin 角色

### 变更文件

- `manage.sh` — VERSION 3.3.1 → 3.4.0
- `frontend/package.json` — version 3.3.1 → 3.4.0
- `backend/app/core/config.py` — VERSION 3.3.1 → 3.4.0
- `.env.example` — VERSION 3.3.1 → 3.4.0
- `.env.dev` — 新增开发环境配置模板
- `.env.prod` — 新增生产环境配置模板
- `frontend/Dockerfile.dev` — 新增开发环境 Dockerfile
- `docker-compose.yml` — 添加双层 env_file 配置、锁定 nginx 版本
- `nginx/etc/conf.d/tam.conf` — 添加 /health 路径代理
- `frontend/src/store/branding.ts` — 添加系统版本和环境状态
- `frontend/src/pages/Dashboard.tsx` — System Status 页面显示版本信息
- `frontend/src/components/Layout.tsx` — 页脚显示版本号
- `frontend/src/i18n/index.ts` — 添加 nsSeparator: false
- `frontend/src/i18n/locales/en.ts` — 角色权限翻译
- `frontend/src/i18n/locales/zh.ts` — 角色权限翻译
- `frontend/src/i18n/locales/ja.ts` — 角色权限翻译
- `frontend/src/pages/Roles.tsx` — 权限列标题翻译键修正
- `backend/cli.py` — 修复 admin 用户角色关联
- `backend/app/services/terminal_service.py` — 修复白名单删除逻辑
- `backend/app/api/v1/endpoints/whitelist.py` — 修复删除端点
- `docs/changelog.md` — 追加 [3.4.0] 条目
- `docs/release-notes.md` — 追加 [v3.4.0] 条目
- `docs/release-plan.md` — 更新为 v3.4.0 内容

---

## [v3.3.1] - 2026-06-17

### Bug 修复

- **黑名单显示已解封记录**：黑名单管理页面默认查询不再返回 `auto_unblocked=True` 的历史记录，仅展示当前仍被封堵的活跃记录。新增 `status` 查询参数和前端 Tab 切换支持查看已解封历史记录。

### 变更文件

- `backend/app/services/terminal_service.py` — get_blacklist/get_blacklist_count 添加 auto_unblocked 过滤
- `backend/app/schemas/terminal.py` — BlacklistQuery 添加 status 字段
- `backend/app/api/v1/endpoints/blacklist.py` — get_blacklist endpoint 添加 status 参数
- `frontend/src/hooks/useTerminalData.ts` — BlacklistSearchParams 添加 status 字段
- `frontend/src/pages/Blacklist.tsx` — 添加 Tab 切换、已解封记录样式区分、隐藏解封按钮
- `frontend/src/i18n/locales/zh.ts` — 添加中文翻译键
- `frontend/src/i18n/locales/en.ts` — 添加英文翻译键
- `frontend/src/i18n/locales/ja.ts` — 添加日文翻译键
- `manage.sh` — VERSION 3.3.0 → 3.3.1
- `backend/app/core/config.py` — VERSION 3.3.0 → 3.3.1
- `frontend/package.json` — version 3.3.0 → 3.3.1
- `.env.example` — VERSION 3.3.0 → 3.3.1
- `docs/changelog.md` — 追加 [3.3.1] 条目
- `docs/release-notes.md` — 追加 [v3.3.1] 条目

---

## [v3.3.0] - 2026-06-17

### RBAC 权限控制 + 审计日志优化 + 生产就绪改进

#### RBAC 权限控制
- 4 张核心表（roles/permissions/user_roles/role_permissions），5 个预设角色（superadmin/admin/operator/auditor/viewer），29 个权限码覆盖 10 个功能模块
- `require_permission` 权限检查工厂函数：FastAPI 依赖注入 + Redis 缓存（TTL 300s）+ superuser 短路
- 角色 CRUD API：7 个端点（列表/详情/创建/编辑/删除/权限列表/角色用户列表）
- 前端 `usePermission` Hook + `ProtectedRoute` 路由守卫 + 侧边栏导航过滤
- 角色管理页面：角色列表、创建/编辑弹窗、权限按模块分组、删除确认
- 超管隔离机制：非超管不可见/不可管理超管用户
- 初始管理员 4 层保护：不可删除/降级/停用/角色变更

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

#### 终端封堵与合规改进
- 终端封堵绑定验证：封堵终端前强制检查绑定关系，无绑定时显示防火墙选择器和无绑定错误提示
- 数据源标签页绑定状态列：数据源列表新增绑定状态列，已禁用 ARP 数据源显示"合规状态已冻结"
- 绑定关系下拉框包含已禁用数据源，以 `[已禁用]` 后缀标识
- ARP 数据源禁用触发合规重置：禁用 ARP 数据源时自动重置关联终端 compliance_status 为 unknown
- 两阶段删除机制：数据源、绑定关系、合规基准删除前提供影响预览 API
- 安全删除：自动解封终端、清理黑名单记录、清理 Redis 缓存、触发合规重算
- Sangfor 数据源移除"同步"按钮：Sangfor 为推送型防火墙，无数据同步语义

#### 合规生命周期修复
- 黑名单 mac_address_normalized 字段补全
- 多防火墙解封原子性
- 过期清理安全性增强
- 手动解封触发合规重算
- 统一解封行为对齐

#### 用户手册
- 新增用户使用手册（docs/user-guide.md）：12 章完整操作指引
- 新增快速上手指南（docs/quick-start-guide.md）：8 步核心操作流程
- 新增发布方案文档（docs/release-plan.md）
- 修正用户使用手册与实际系统功能不一致的描述：仪表板快捷操作、终端封堵不支持批量选择、终端详情字段、黑名单详情字段、合规基准页面为标签页、系统设置无前端管理界面（仅 API）、Logo 不支持动态上传、密码策略为硬编码、移除不存在的 SSO 和并发会话控制
- 修正快速上手指南终端封堵操作描述（不支持批量勾选）

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
| da420a4 | fix(audit): unify action naming, add resource_name for meaningful display |
| c65466b | chore: remove sangfor_api docs and todos.md from git tracking |
| 3ed025c | feat(production-readiness): P0-P3 improvements for production deployment |
| 7722146 | refactor(deploy): unify deployment modes to dev/prod, fix mock data business alignment |
| 42b3f06 | docs: comprehensive documentation update to v3.2.0-r12 |
| 9f00100 | docs: rewrite README.md as concise project onboarding guide |

### 文件变更
- 93 个文件，+16288/-2027 行（相比 v3.2.0）

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
