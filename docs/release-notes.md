# 版本跟踪记录

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
