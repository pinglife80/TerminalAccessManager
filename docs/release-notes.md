# 版本跟踪记录

> 文档版本：v3.2.0-r4 | 更新日期：2026-06-15
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
