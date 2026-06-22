# 文档同步更新计划 — v3.2.0-r12

## 一、变更范围评估

自上次文档全面更新（v3.2.0-r11, commit e67bab5）以来，共有 4 个代码提交：

| 提交      | 说明                                                  | 主要变更                                                            |
| ------- | --------------------------------------------------- | --------------------------------------------------------------- |
| da420a4 | fix(audit): unify action naming, add resource\_name | 审计日志 action 统一为 verb\_resource 格式，新增 resource\_name 列，keyset 分页 |
| c65466b | chore: remove sangfor\_api docs and todos.md        | 从 git 移除 sangfor\_api 文件夹和 todos.md                             |
| 3ed025c | feat(production-readiness): P0-P3 improvements      | 容器安全加固、健康检查、单元测试、指数退避、N+1 优化、灾难恢复+运维 Runbook                    |
| 7722146 | refactor(deploy): unify deployment modes dev/prod   | 部署模式合并 demo→dev，Nginx 环境差异化，Mock 数据业务对齐                         |

### 关键变更清单

1. **审计日志 action 命名统一**：`block_ip→block_terminal`, `unblock_ip→unblock_terminal`, `auto_block→auto_block_terminal`, `auto_unblock→auto_unblock_terminal`, `cleanup_expired→cleanup_expired_blacklist`, `role_change→change_role`
2. **新增** **`resource_name`** **列**：audit\_logs 表新增 String(200) nullable 列，存储人类可读资源名称
3. **新增数据库迁移**：008\_audit\_resource\_name.py, 009\_audit\_keyset\_index.py
4. **审计日志 keyset 分页**：`/api/v1/logs/search` 新增 cursor 参数，返回 CursorPaginatedResponse
5. **审计日志导出新增列**：CSV 导出新增 Resource Name 列
6. **Docker 安全加固**：docker-compose.prod.yml（no-new-privileges, cap\_drop:ALL, read\_only）
7. **Docker 健康检查**：所有服务添加 healthcheck 配置
8. **Sangfor API 指数退避**：`_request_with_backoff` 方法，最多 3 次重试
9. **N+1 查询优化**：cleanup\_expired\_blacklist 和 batch\_check\_compliance 批量预加载
10. **核心服务单元测试**：22 个 compliance\_service 测试用例
11. **部署模式统一**：demo→dev，自动设置 ENVIRONMENT，生产环境禁止 mock generate
12. **Nginx 环境差异化**：tam.dev.conf（HTTP+宽松限流）vs tam.conf（HTTPS+标准限流）
13. **Mock 数据业务对齐**：28 种 verb\_resource action、JSON details、resource\_name、firewall\_tag 一致
14. **新增文档**：disaster-recovery.md、operations-runbook.md
15. **从 git 移除**：docs/sangfor\_api/、docs/todos.md

***

## 二、文档影响评估

### 需要内容更新的文档（8 个）

| # | 文档                                     |   优先级  | 需要更新的内容                                                                                                    |
| - | -------------------------------------- | :----: | ---------------------------------------------------------------------------------------------------------- |
| 1 | **changelog.md**                       |  HIGH  | \[Unreleased] 新增 4 个提交的变更条目                                                                                |
| 2 | **release-notes.md**                   |  HIGH  | 新增 \[v3.2.0-r12] 版本记录，含提交列表和文件变更                                                                           |
| 3 | **api.md**                             |  HIGH  | 审计日志搜索端点新增 cursor 参数和 CursorPaginatedResponse；导出端点新增 Resource Name 列；AuditLogResponse 新增 resource\_name 字段 |
| 4 | **database.md**                        |  HIGH  | audit\_logs 表新增 resource\_name 列；新增 008/009 迁移文件说明；keyset 分页复合索引                                           |
| 5 | **deployment.md**                      |  HIGH  | 部署模式从 demo/prod 改为 dev/prod；docker-compose 三层架构（base+dev+prod）；Nginx 环境差异化；ENVIRONMENT 变量自动设置              |
| 6 | **manage-sh-reference.md**             | MEDIUM | deploy 命令参数变更（--demo→--dev）；mock generate 生产环境限制；dc() 函数环境 override 逻辑                                     |
| 7 | **backend.md**                         | MEDIUM | log\_action 新增 resource\_name 参数；SangforService 指数退避机制；N+1 优化说明；compliance\_service 单元测试                   |
| 8 | **production-readiness-assessment.md** | MEDIUM | 更新 P0-P3 改进完成状态；测试覆盖数据更新（63→85 用例）；docker-compose.prod.yml 从"缺失"改为"已完成"；容器安全加固状态更新                         |

### 仅需版本号更新的文档（7 个）

| #  | 文档                              | 当前版本       | 目标版本       |
| -- | ------------------------------- | ---------- | ---------- |
| 9  | architecture.md                 | v3.2.0-r11 | v3.2.0-r12 |
| 10 | datasource-lifecycle.md         | v3.2.0-r11 | v3.2.0-r12 |
| 11 | RBAC.md                         | v3.2.0-r11 | v3.2.0-r12 |
| 12 | branding.md                     | v3.2.0-r11 | v3.2.0-r12 |
| 13 | logging-guide.md                | v3.2.0-r11 | v3.2.0-r12 |
| 14 | git-workflow-guide.md           | v3.2.0-r11 | v3.2.0-r12 |
| 15 | frontend/docs/implementation.md | v3.2.0-r11 | v3.2.0-r12 |

### 不需要更新的文档（2 个）

| #  | 文档                    | 原因                               |
| -- | --------------------- | -------------------------------- |
| 16 | disaster-recovery.md  | 已在 3ed025c 中创建为 v3.2.0-r11，本次无变更 |
| 17 | operations-runbook.md | 已在 3ed025c 中创建为 v3.2.0-r11，本次无变更 |

***

## 三、具体更新内容

### 3.1 changelog.md

在 `[Unreleased]` 的 `### 新增` 部分追加：

```
- 审计日志 resource_name 字段：存储人类可读资源名称（用户名、数据源名称、IP 地址等），替代无意义的 #id 显示
- 审计日志 keyset 分页：`/api/v1/logs/search` 新增 cursor 参数，支持深分页高性能查询
- Docker 安全加固：docker-compose.prod.yml 实现容器安全最佳实践（no-new-privileges、cap_drop:ALL、read_only）
- Docker 健康检查：所有服务添加 healthcheck 配置，支持容器编排健康探测
- Sangfor API 指数退避重试：`_request_with_backoff` 方法，最多 3 次重试，等待时间指数增长（1s→2s→4s，上限 10s）
- 核心服务单元测试：compliance_service 22 个测试用例（状态转换、自动封堵/解封、过期清理、白名单匹配、合规重算）
- 灾难恢复计划：docs/disaster-recovery.md（故障分级 P0-P3、各组件恢复步骤、RPO/RTO 目标）
- 运维操作手册：docs/operations-runbook.md（日常巡检、故障排查、定时任务管理、升级回滚）
- 部署模式统一：`deploy --dev` 替代 `deploy --demo`，自动设置 ENVIRONMENT 变量
- 开发环境 Nginx 配置：tam.dev.conf（HTTP 直连 + 放宽限流 120r/m+30r/m）
- docker-compose.dev.yml：开发环境 override 文件，自动加载 tam.dev.conf
- Mock 数据业务对齐：28 种 verb_resource action、JSON details、resource_name、firewall_tag 绑定关系一致
```

在 `### 改进` 部分追加：

```
- 审计日志 action 命名统一为 verb_resource 格式：block_ip→block_terminal, unblock_ip→unblock_terminal, auto_block→auto_block_terminal, auto_unblock→auto_unblock_terminal, cleanup_expired→cleanup_expired_blacklist, role_change→change_role
- N+1 查询优化：cleanup_expired_blacklist 批量预加载 Terminal + 批量检查活跃 Blacklist + 缓存 SangforService；batch_check_compliance 一次性加载白名单和 IPGuard 数据
- Nginx 生产限速调整：api_limit 30r/m→60r/m，auth_limit 5r/m→10r/m，避免前端正常操作触发限速
- 生产环境禁止 mock generate：`cmd_mock()` 检测 ENVIRONMENT=production 时拒绝执行
- Mock 数据 blocked_by 修正：自动封堵 blocked_by="system"，手动封堵使用操作者用户名
- 从 git 移除 sangfor_api 文件夹和 todos.md：仅保留本地，不再追踪到仓库
```

### 3.2 release-notes.md

新增版本记录：

```markdown
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
```

### 3.3 api.md

更新内容：

1. 审计日志搜索端点 `GET /api/v1/logs/search`：新增 `cursor` 查询参数说明，返回类型改为 `CursorPaginatedResponse`
2. 审计日志导出端点 `GET /api/v1/logs/export`：CSV 新增 `Resource Name` 列
3. AuditLogResponse schema：新增 `resource_name: Optional[str]` 字段
4. 新增 CursorPaginatedResponse schema 说明

### 3.4 database.md

更新内容：

1. audit\_logs 表结构：新增 `resource_name` 列（String(200), nullable=True）
2. 索引部分：新增 `idx_audit_logs_keyset` 复合索引说明
3. 迁移文件列表：新增 008\_audit\_resource\_name.py 和 009\_audit\_keyset\_index.py

### 3.5 deployment.md

更新内容：

1. 部署模式从 demo/prod 改为 dev/prod
2. 新增 docker-compose 三层架构说明（base + dev overlay + prod overlay）
3. 新增 ENVIRONMENT 变量自动设置说明
4. Nginx 环境差异化表格（HTTP vs HTTPS，限速差异）
5. docker-compose.dev.yml 和 docker-compose.prod.yml 说明

### 3.6 manage-sh-reference.md

更新内容：

1. deploy 命令参数：`--demo` 标记为废弃，`--dev` 为推荐参数
2. mock generate 命令：新增生产环境限制说明
3. dc() 函数：新增环境 override 逻辑说明

### 3.7 backend.md

更新内容：

1. log\_action 方法：新增 resource\_name 参数说明
2. SangforService：新增 `_request_with_backoff` 指数退避方法说明
3. N+1 优化：cleanup\_expired\_blacklist 和 batch\_check\_compliance 批量预加载说明
4. 测试覆盖：compliance\_service 22 个测试用例

### 3.8 production-readiness-assessment.md

更新内容：

1. 10.3 缺失交付件：`docker-compose.prod.yml` 从"缺失"改为"已完成"
2. 10.4 测试覆盖：后端用例数从 63 更新为 85（+22 compliance\_service）
3. 12.1 风险矩阵：#14 容器未 cap\_drop:ALL 从"待修复"改为"已修复"
4. 13.2 交付后优化：#4 容器 cap\_drop:ALL 标记为"已完成"
5. 新增 P0-P3 改进完成记录

***

## 四、版本号统一

所有 17 个文档统一更新为 **v3.2.0-r12**，更新日期 **2026-06-17**。

***

## 五、执行计划

### Step 1: 更新 changelog.md

* 追加 \[Unreleased] 变更条目

### Step 2: 更新 release-notes.md

* 新增 \[v3.2.0-r12] 版本记录

### Step 3: 更新 api.md

* 审计日志端点变更 + schema 变更

### Step 4: 更新 database.md

* audit\_logs 表结构 + 迁移文件

### Step 5: 更新 deployment.md

* 部署模式 + docker-compose 三层架构 + Nginx 差异化

### Step 6: 更新 manage-sh-reference.md

* deploy 命令参数 + mock 限制 + dc() 逻辑

### Step 7: 更新 backend.md

* log\_action + 指数退避 + N+1 优化 + 测试

### Step 8: 更新 production-readiness-assessment.md

* 交付件状态 + 测试覆盖 + 风险矩阵 + P0-P3 改进

### Step 9: 批量更新版本号

* 7 个仅版本号更新的文档统一改为 v3.2.0-r12

### Step 10: Git 提交 + 推送

* 单独文档提交推送到 develop 分支

***

## 六、验证步骤

1. 检查所有文档版本号是否统一为 v3.2.0-r12
2. 检查 changelog.md \[Unreleased] 条目是否覆盖所有 4 个提交的变更
3. 检查 release-notes.md \[v3.2.0-r12] 提交记录和文件变更是否完整
4. 检查 api.md 新增端点参数和 schema 是否与代码一致
5. 检查 database.md 表结构和迁移文件是否与代码一致
6. 检查 deployment.md 部署模式描述是否与 manage.sh 一致
7. 检查 production-readiness-assessment.md 状态更新是否与实际一致

