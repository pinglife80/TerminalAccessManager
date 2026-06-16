# 更新日志

本文件记录 TerminalAccessManager 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 新增

- 两阶段删除机制：数据源、绑定关系、合规基准删除前提供影响预览 API（`POST /{id}/delete-preview`）
- 安全删除：自动解封终端、清理黑名单记录、清理 Redis 缓存、触发合规重算
- 前端 DeletePreviewModal 组件：展示影响范围、操作清单、受影响资源统计
- 数据源 tag 和合规基准 tag 修改禁止（tag 为系统全局标识符，修改会导致关联数据断裂）
- RBAC 角色权限控制：4张核心表（roles/permissions/user_roles/role_permissions），5个预设角色（superadmin/admin/operator/auditor/viewer），29个权限码覆盖10个功能模块
- `require_permission` 权限检查工厂函数：FastAPI 依赖注入 + Redis 缓存（TTL 300s）+ superuser 短路
- 角色 CRUD API：7个端点（列表/详情/创建/编辑/删除/权限列表/角色用户列表）
- 用户角色分配 API：`PUT /roles/users/{id}/roles`（单角色分配）
- 前端 `usePermission` Hook：4个权限判断方法（hasPermission/hasAnyPermission/hasAllPermissions/hasRole）
- 前端 `ProtectedRoute` 路由守卫：支持 `requiredPermission` / `requiredAnyPermissions`
- 前端侧边栏导航过滤：根据 `requiredPermission` 过滤导航项
- 角色管理页面：角色列表、创建/编辑弹窗、权限按模块分组、删除确认
- 超管隔离机制：非超管不可见/不可管理超管用户，超管只能自己管理自己
- 初始管理员4层保护：不可删除/降级/停用/角色变更
- RBAC 后端测试：11个测试用例（权限缓存、权限检查、缓存失效）
- RBAC 前端测试：20个 usePermission Hook 测试用例
- RBAC 文档：`docs/RBAC.md`（从"角色管理与用户访问控制说明文档"重命名）

### 改进

- 数据源删除操作从直接删除改为安全删除（先自动善后再删除）
- 绑定关系删除操作从直接删除改为安全删除（先解封终端再删除绑定）
- 合规基准删除操作增加 Redis 缓存清理和合规重算步骤
- Sangfor 数据源移除"同步"按钮：Sangfor 为推送型防火墙，无数据同步语义，前端按类型条件隐藏同步按钮，后端同步接口对 sangfor 类型返回"不适用"提示
- 合规重算（`recalculate_all_compliance`）自动封堵/解封改为多防火墙路由，与 `auto_block_non_compliant` 行为一致
- 合规重算创建的 Blacklist 记录补全 `expires_at` 和 `blocked_by` 字段
- 过期黑名单清理 Sangfor 解封失败时保留 Blacklist 记录并延长重试，避免本地与防火墙状态不一致
- 过期清理完成后触发合规重算，确保不合规终端及时重新封堵
- `unblock_ip` 增加 `mac_address` 参数，支持按 MAC 精确解封
- `auto_unblock_compliant` / `cleanup_expired_blacklist` Terminal 查询增加 MAC 维度匹配
- 自动封堵/解封/合规重算操作补全审计日志
- `block_ip` / `unblock_ip` 审计日志补充客户端 IP 地址
- 单角色模型：`role_ids: list[int]` → `role_id: int`，前端 checkbox 多选 → select 单选下拉
- 搜索防抖统一为 500ms（Terminals/Whitelist/Blacklist/AuditLogs），`keepPreviousData` 防搜索闪屏
- Redis 客户端添加超时配置（`socket_timeout`/`socket_connect_timeout`），防止无限阻塞
- API 速率限制从 60→120 次/分钟，认证限制从 5→10 次/分钟
- i18n 三语言补全：`superadminRoleFixed`/`selectRole` 等 RBAC 相关 key
- 9个后端端点文件从 `get_current_user` 替换为 `require_permission`，实现真正的 RBAC 权限校验

### 修复

- 修复 compliance_service.py 导入错误（`app.models.audit_log` → `app.models.log`）导致后端启动失败
- 搜索返回空结果（Whitelist/Blacklist/AuditLogs）：`_escape_like` 对已包裹 `%` 的字符串转义导致 LIKE 模式错误
- AuditLog 搜索缺少 action 字段：搜索只覆盖 ip_address/username/details
- MAC 搜索从前缀匹配改为包含匹配：`ilike(f"{value}%")` → `ilike(f"%{value}%")`
- API 全局阻塞（30s+）：paramiko SSH 同步操作阻塞 asyncio 事件循环，改用 `asyncio.to_thread()`
- 307 重定向 + CSP 错误：前端 API 路径带尾部斜杠，后端路由不带
- 超管角色可被分配给其他用户：创建/编辑用户时过滤 superadmin 角色
- 超管编辑自己时仍显示角色修改选项：超管或自己编辑时隐藏角色下拉框，显示只读文本
- Users 搜索框闪屏/失焦：添加 `keepPreviousData` + `useDebounce(500ms)`

---

## [3.2.0] - 2026-06-10

### 新增

- Request-ID 链路追踪：新增 `RequestIDMiddleware` + `ContextVar`，每个 HTTP 请求自动分配 12 位 hex request_id（优先读取客户端 `X-Request-ID` 请求头），响应头返回 `X-Request-ID`，日志格式自动注入 request_id 字段
- 时区全局控制：`config.py` 新增 `TZ` 配置项（默认 `Asia/Shanghai`），`docker-compose.yml` 5 个服务统一添加 `TZ` 环境变量，PostgreSQL 添加 `log_timezone`/`timezone` 参数，后端启动时调用 `time.tzset()` 使 loguru `ZZ` 显示正确时区偏移
- 前端日志本地时区：`logger.ts` 的 `formatTimestamp()` 从 UTC ISO 格式（`Z` 后缀）改为本地时区+偏移量格式（如 `+08:00`），日志时间与用户本地时间一致

### 改进

- 日志格式函数化：`logging_config.py` 从静态 `LOG_FORMAT` 字符串改为 `_log_format()` 动态函数，运行时自动从 ContextVar 注入 request_id，非请求上下文显示 `-`
- 请求日志增强：`RequestLoggingMiddleware` 日志消息增加 `req_id=` 字段，与格式字段中的 request_id 一致
- Docker 安全加固注释化：`security_opt`/`cap_drop`/`read_only` 等生产加固项改为注释（标注 `Production hardening`），开发环境直接运行，生产环境取消注释即可启用
- 日志文档补全：`logging-guide.md` 新增 7 个章节（文档版本历史、日志监控与告警、紧急处理流程、性能影响说明、日志分析常用命令、日志配置变更指南、Request-ID 链路追踪）+ 3 项修正（审计归档 cron 示例、前端日志渐进式接入标注、Request-ID 与 error_id 关联说明）

---

## [3.1.0] - 2026-06-09

### 新增

- Redis fail-open 降级策略：`security.py` 中 10 个 Redis 交互函数统一添加 try/except 异常处理，Redis 不可用时按策略降级（黑名单放行、版本号返回 0、登录防护放行等），避免 Redis 故障导致服务不可用
- MAC 地址标准化列：`terminals`/`whitelist`/`blacklist` 三张表新增 `mac_address_normalized` 列（VARCHAR(12)，去除分隔符的大写 MAC），Alembic 005 迁移脚本含数据回填和索引创建，6 处 MAC 搜索从 `func.replace()` 变换改为标准化列查询，4 处 MAC 写入点自动填充标准化列
- 全局异常处理中间件：新增 `error_handler.py`，注册 3 个异常处理器（HTTPException 透传、RequestValidationError 保留 422 格式、未捕获异常返回 500 + error_id + 日志），统一错误响应格式
- CI/CD 流水线：新增 `.github/workflows/ci.yml`（6 个 Job：lint-backend/test-backend/lint-frontend/test-frontend/build-backend/build-frontend），`backend/pyproject.toml`（ruff 配置），`frontend/.eslintrc.json`
- 后端测试基础设施：重写 `conftest.py`（mock_redis fixture + 内存模拟 Redis），新增 `test_security.py`（4 个测试类 19 用例）、`test_terminals.py`（2 个测试类 10 用例）、`test_whitelist.py`（2 个测试类 3 用例）、`test_blacklist.py`（2 个测试类 2 用例），修复 `test_app.py`/`test_auth.py`/`test_core.py` 与代码变更同步
- 前端测试基础设施：新增 `vitest.config.ts`、`src/test/setup.ts`、3 个测试文件（`utils.test.ts` 42 用例、`theme.test.ts` 8 用例、`auth.test.ts` 8 用例），共 58 个测试用例
- LICENSE 文件：项目根目录新增 MIT License 文件
- manage.sh `cmd_restore` Redis RDB 恢复：恢复数据库时同步恢复 Redis RDB 文件

### 改进

- docker-compose.yml：`postgres` 和 `redis` 服务添加 `restart: unless-stopped`，容器异常退出后自动重启
- docker-compose.yml：5 个服务统一添加 `cap_drop: [ALL]`，`nginx` 添加 `cap_add: [NET_BIND_SERVICE]`（绑定低位端口），容器安全加固
- 评估文档综合评分从 8.6 提升至 8.8（安全 8.5→9.0，鲁棒性 8.5→9.0）

---

## [3.0.0] - 2026-06-09

### 安全修复（Critical）

- 服务端验证码机制：新增 `GET /auth/captcha` 端点生成算术验证码，答案存入 Redis（5 分钟 TTL），登录时校验 captcha_id + 答案，前端移除本地验证码生成和校验逻辑
- 加密密钥分离：新增 `ENCRYPTION_KEY` 配置字段，生产环境启动时强制校验（未设置或与 SECRET_KEY 相同则拒绝启动），开发环境回退到 SECRET_KEY 并输出警告日志
- 移除不安全默认密码：docker-compose.yml 移除 `DB_PASSWORD:-password`、`REDIS_PASSWORD:-redis_password`、`SECRET_KEY:-your-secret-key-change-in-production` 等弱默认值，改用 `:?` 必填语法；manage.sh 新增 `_check_required_env` 函数检查必需环境变量

### 安全修复（High）

- 移除 `/auth/login-status` 公开端点：防止未认证用户枚举有效用户名
- 移除登录响应头信息泄露：删除 `X-Captcha-Required`、`X-Account-Locked`、`X-Lock-Remaining` 响应头，改为在错误响应 JSON detail 中返回 `captcha_required`/`locked`/`lock_remaining` 字段
- LIKE 通配符注入防护：新增 `_escape_like()` 工具函数，21 处 ilike 查询统一转义 `%` 和 `_` 通配符
- Token 版本号机制：JWT payload 新增 `ver` 字段，密码变更/重置时递增用户 Token 版本号，旧 Token 自动失效
- terminals 表联合唯一约束：新增 `(ip_address, mac_address)` 联合唯一约束 `uq_terminal_ip_mac`，Alembic 004 迁移脚本含去重逻辑
- `_auto_block_task` 会话生命周期修复：改用 `async_session_factory()` 创建独立数据库会话，含 commit/rollback

### 安全修复（Medium）

- JWT Token 类型区分：access token 添加 `"type": "access"` 字段，refresh token 添加 `"type": "refresh"` 字段，refresh 端点验证 Token 类型
- 上传文件安全加固：新增 `ALLOWED_EXTENSIONS` 扩展名白名单（.jpg/.jpeg/.png/.gif/.ico），移除 SVG 支持（XSS 风险），双重校验 content_type + 扩展名，文件名 UUID 重命名
- /uploads/ 访问控制：Nginx 添加 Referer 检查，恶意来源返回 403
- 审计日志导出权限：导出端点从 `get_current_user` 改为 `get_current_active_superuser`，仅超管可导出
- Redis 密码安全：manage.sh 22 处 `redis-cli -a` 改为 `REDISCLI_AUTH` 环境变量，密码不再暴露在进程列表
- CORS 安全校验：`allow_origins=["*"]` 时自动降级 `allow_credentials=False`

### 改进

- Alembic env.py 修复 asyncpg 驱动兼容性，迁移不再依赖 psycopg2
- 修复伪测试：`TestSecretKeyValidation` 和 `TestLoginSecurity` 重写为有效测试
- 新增 `_escape_like` 和 `token_version` 单元测试
- 修复 `test_login_wrong_password` 断言适配结构化 detail 响应

---

## [2.5.0] - 2026-06-09

### 新增

- i18n 国际化：i18next + react-i18next + i18next-browser-languagedetector，支持中文(zh)/英文(en)/日语(ja)三种语言，自动检测浏览器语言，手动切换（HeaderControls Globe 下拉菜单），语言持久化到 localStorage，14 个页面/组件全部 i18n 替换，翻译文件 en.ts/zh.ts/ja.ts
- HeaderControls 组件：新增 `frontend/src/components/HeaderControls.tsx`，页面顶部右上角（登录页和登录后均可见），主题切换浅色/深色/跟随系统三选项并列，语言选择 Globe 图标下拉菜单
- Layout 顶栏：内容区顶部新增一行顶栏，右侧显示 HeaderControls
- 审计日志前端分类过滤：8 类操作分类过滤（认证/终端/白名单/黑名单/数据源/用户/配置/系统），彩色 badge 标识，resource 展示优化，details JSON 解析展示
- MAC 地址格式无关搜索：后端 whitelist/blacklist 搜索使用 `func.replace` 去除 MAC 分隔符后 ILIKE 匹配，前端 `keepPreviousData` 防搜索闪烁

### 改进

- 审计日志 action 统一命名：`block_ip` → `block_terminal` 等规范化，启动时自动迁移旧值
- 审计日志 details 改为 JSON 格式，补充 login/logout/数据源/用户管理/配置变更审计记录
- 审计日志新增 `log_action` 公共函数 + `ip_address` 字段
- Sidebar 简化：移除主题和语言切换按钮（移至 HeaderControls），只保留 Profile 和 Logout
- 品牌名称替换：Terminal Access Platform → Terminal Access Manager，代码 19 处 + package.json + 后端启动时自动迁移数据库
- 前端请求超时和可靠性增强：`initializeAuth` timeout 10s、refresh token 传递统一为 body、排队请求 `_retry` 防循环、React Query 401 不重试、`api.ts` refresh timeout 10s、sonner 动态 import `.catch()`

### 修复

- 登录深色主题适配：背景从 `branding.login.background.gradientClass` 改为 `bg-background` 语义化颜色，锁定警告区/错误提示区/验证码区/输入框全部添加 `dark:` 变体
- 页面闪烁修复：Suspense 移到 Layout Outlet 外层、QueryClient `staleTime` 30s、Sidebar hover 预加载页面组件
- 搜索闪烁修复：前端使用 `keepPreviousData` 防止搜索时页面闪烁

---

## [2.4.0] - 2026-06-09

### 新增

- 搜索优化：4个搜索API返回 `PaginatedResponse`（含 items/total/skip/limit），支持真正的服务端分页
- Terminals 搜索改为 ILIKE 模糊搜索 + OR 逻辑（IP 或 MAC 任一匹配即可）
- Terminals 搜索新增 `compliance_status` 过滤参数
- 前端4个页面搜索输入框添加 300ms debounce，减少无效 API 请求
- 前端4个页面实现服务端分页，支持浏览全部数据
- 数据库索引优化：whitelist.created_at、blacklist.blocked_at/expires_at、audit_logs.ip_address
- 数据库迁移脚本 003_search_indexes.py
- 认证状态恢复机制：`initializeAuth()` 在应用启动时从 sessionStorage 恢复认证状态
- 401 拦截器并发控制：多个 401 请求只触发一次 token 刷新，排队的请求用新 token 重发
- 会话过期提示：token 刷新失败时 toast 提示"Session expired"

### 改进

- 移除 passlib 依赖，直接使用 bcrypt 库，彻底解决 bcrypt 版本兼容性警告
- Sidebar Logo 区域固定高度（h-10），折叠/展开时不再位置跳动
- health check 中 frontend 容器 exited(0) 视为正常（构建完成），不再误报 ERROR

### 修复

- 修复会话超时后不会自动退出登录的问题
- 修复页面刷新后认证状态丢失的问题
- 修复 Terminals 搜索使用精确匹配导致部分输入无法搜到结果的问题
- 修复前端分页与后端分页矛盾导致只能看到前50条数据的问题
- 修复 logs/export 无 limit 限制可能导致 OOM 的问题（新增 limit 参数，默认10000，最大50000）

---

## [2.3.0] - 2026-06-08

### 新增

- `upgrade` 命令：从远程仓库拉取新版本代码并升级，支持指定版本（tag/branch/commit）、`--check` 仅检查模式、前置安全检查、版本差异展示、红色警告框、强制自动备份、自动数据库迁移、迁移失败恢复方案
- 危险命令结构化警告：`restore`、`mock clear`、`migrate`、`redis flush`、`redis del`、`config set`（安全类配置）执行前显示影响范围和确认提示
- `config set` 新旧值对比显示，安全类配置（锁定策略、限流、验证码等）二次确认
- 定时任务暂停机制真正生效：`_is_task_paused()` 函数在任务循环中检查 Redis 键 `scheduler:ctrl:{task}`
- 新增 `docs/manage-sh-reference.md` 命令行操作手册

### 改进

- `update` 命令移除 git pull，改为仅重建+重启本地代码（不再有 `--no-git` 参数）
- `scheduler pause/resume` 现在真正控制定时任务执行（之前仅设置 Redis 键但任务未检查）

### 修复

- `firewall_query` 定时任务改用 `TerminalService._get_sangfor_service_by_tag()` + `SangforService.get_blocked_ips()`（原调用不存在的 `query_firewall_blacklist` 方法）

---

## [2.2.0] - 2026-06

### 重构

- **MacAddress → Terminal 重命名**：数据库表 `mac_addresses` → `terminals`，后端模型 `MacAddress` → `Terminal`，Schema `MacAddressBase/Create/Update/Response/Query` → `TerminalBase/Create/Update/Response/Query`，服务 `MacService` → `TerminalService`，API 路由 `/mac` → `/terminals`，前端组件 `MacAddresses` → `Terminals`，前端路由 `/mac-addresses` → `/terminals`，前端 Hook `useMacAddresses` → `useTerminals`，前端类型 `MacAddress` → `Terminal`，文件名 `mac_address.py` → `terminal.py`、`mac_service.py` → `terminal_service.py`、`mac_addresses.py` → `terminals.py`、`MacAddresses.tsx` → `Terminals.tsx`、`useMacData.ts` → `useTerminalData.ts`
- **API 路由 `/mac` → `/terminals`**：`GET /api/v1/mac/` → `GET /api/v1/terminals/`，`GET /api/v1/mac/search` → `GET /api/v1/terminals/search`，`POST /api/v1/mac/block/{ip}` → `POST /api/v1/terminals/block/{ip}`，`POST /api/v1/mac/unblock/{ip}` → `POST /api/v1/terminals/unblock/{ip}`，`GET /api/v1/mac/{id}` → `GET /api/v1/terminals/{id}`
- **IP Guard → ComplianceBaseline 分离**：新增 `compliance_baselines` 数据库表，新增 `ComplianceBaseline` 模型、Schema、Endpoint，DataSource 的 `type` 不再包含 `ipguard`（只保留 `arp_ssh`/`arp_api`/`sangfor`），新增 API 路由 `/compliance-baselines/`（CRUD + test + sync），前端 DataSources 页面新增 "Compliance Baselines" Tab，数据库迁移脚本 `002_terminal_baseline.py`

---

## [2.1.0] - 2026-06

### 新功能

- **数据源管理系统**：新增 DataSource 和 DataSourceBinding 数据模型，统一管理 ARP 数据源（SSH/API）、IP Guard 合规基准、深信服防火墙，支持数据源 CRUD、测试连接、手动同步
- **合规检查引擎**：新增 ComplianceService，4 种合规状态判定（compliant/bypass/non_compliant/unknown），白名单匹配类型标记（wl_match_type: mac/ip/both），IPGuard 基准匹配，自动封禁/解封按防火墙 Tag 路由
- **多防火墙支持**：数据源绑定（DataSourceBinding）关联 ARP 数据源与防火墙，封禁/解封操作按 Tag 路由到对应防火墙，多防火墙场景创建独立 Blacklist 记录
- **定时任务可配置**：5 个定时任务频率参数（ARP 采集、IPGuard 同步、防火墙查询、合规检查、自动解封），支持 30 秒 - 1 天间隔，通过 `manage.sh config set` 修改
- **Scheduler 配置分类**：系统配置新增 `scheduler` 分类，SchedulerConfigResponse 包含 5 个间隔配置项
- **前端自动刷新**：Terminal 和 Blacklist 页面支持手动刷新按钮和自动刷新选择器（30 秒 / 1 分钟 / 5 分钟 / 10 分钟）
- **DataSources 页面**：新增数据源管理页面（管理员专属），包含 Data Sources / Bindings / Compliance 三个 Tab，支持编辑数据源、手动同步、合规检查操作
- **Users 页面**：新增用户管理页面（管理员专属），用户 CRUD 操作
- **Profile 页面**：新增个人资料页面
- **品牌动态加载**：新增 useBrandingStore Zustand store，登录后从后端 `/settings/` API 动态加载品牌配置，替代纯静态 branding.ts
- **manage.sh config 增强**：新增 `config list`、`config get`、`config set`、`config branding`、`config upload` 子命令，支持数据库系统配置和品牌资源管理
- **Whitelist 详情查看**：白名单页面新增详情弹窗，comments 字段改为必填
- **Terminal 合规状态**：终端页面从 6 种状态改为 4 种合规状态（Normal/Bypass/Blocked/Pending），集成黑名单数据展示，Bypass 显示匹配类型（MAC/IP/Both），Blocked 显示防火墙 Tag
- **Terminal 快捷操作**：Bypass 条目支持"从白名单移除"，Blocked 条目支持"从黑名单移除"
- **Dashboard 合规统计**：统计卡片更新为 5 个（Total/Normal/Bypass/Blocked/Pending），compliance_status 分组统计
- **导航权限控制**：NAV_ITEMS 新增 adminOnly 字段，Data Sources 和 Users 页面仅管理员可见

### 改进

- **终端总数统计**：Total 统计仅计算 ARP 数据源条目（source='arp'），不再包含白名单独立条目
- **黑名单手动封禁**：手动封禁 source_tag 标记为 "manual"，compliance_status 设置为 "non_compliant"
- **黑名单手动解封**：按 firewall_tag 过滤删除 Blacklist 记录，compliance_status 设置为 "unknown"
- **白名单 CIDR 匹配**：存储原始 pattern，使用 ipaddress 模块判断包含关系，不展开 CIDR
- **合规检查缓存**：IPGuard 数据 Redis 缓存 10 分钟 TTL，白名单数据 Redis 缓存 5 分钟 TTL
- **ARP 采集后合规更新**：ARP 采集完成后自动运行合规检查，更新 compliance_status 和 wl_match_type
- **Demo 默认密码**：Demo 模式默认密码从 admin123 改为 Admin123（满足密码复杂度要求）
- **前端类型对齐**：MacAddress、WhitelistEntry、BlacklistEntry、DataSourceItem 等类型定义与后端 schema 完全对齐
- **前端 UI 统一**：所有页面按钮使用默认 md 尺寸，Dashboard Overview 放在页面标题下方

### Bug 修复

- 修复 Stats API `GET /mac/stats` 被 `GET /mac/{mac_id}` 路由匹配的问题
- 修复 Scheduler 配置未出现在 settings API 的问题（AllConfigsResponse 缺少 scheduler 字段）
- 修复 ConfigService 缺少 get_value 方法导致 _get_scheduler_interval 调用失败
- 修复 MacAddress 模型缺少 wl_match_type 字段导致前端类型不匹配
- 修复 arp_collector_service.py 合规检查后未更新 wl_match_type
- 修复 main.py scheduled_compliance_check 未更新 wl_match_type
- 修复前端 MacAddresses.tsx 中 removingWlId/removingBlId/whitelistId 与 mac.id 类型比较错误（string | null vs number）
- 修复前端 MacAddresses.tsx 中 CheckCircle 未使用导入导致构建失败

---

## [2.0.0] - 2026-06

### 新功能

- **统一管理脚本**：整合 `manage.sh`、`deploy.sh`、`quickstart.sh` 为单一 `manage.sh`，支持 17 个子命令（deploy/start/stop/restart/status/health/logs/update/init/test/mock/backup/restore/shell/ssl/config/validate/clean/version），幂等设计，非交互模式（`-y`），调试输出（`-v`）
- **生产部署向导**：`deploy --prod` 交互式配置数据库密码、Redis 密码、JWT 密钥、深信服 API、网络交换机集成
- **深度健康检查**：`health` 命令执行 8 项检查（Docker/容器/数据库/Redis/后端/Web/SSL/磁盘）
- **配置管理**：`config` 命令查看/修改环境变量，敏感信息自动脱敏
- **SSL 证书管理**：`ssl` 命令幂等生成自签名证书，`--force` 强制重新生成，Nginx 自动 reload
- **数据库备份恢复**：`backup`/`restore` 命令，自动清理旧备份（保留 10 个），恢复前自动备份
- **自动备份**：`update`/`restore`/`mock clear` 操作前自动备份数据库
- **部署状态管理**：`.manage/state.env` 跟踪部署状态，实现幂等性控制
- **品牌自定义**：集中式品牌配置（`branding.ts`），支持自定义应用名称、Logo、Favicon、登录页样式、页脚信息、ICP 备案等，无需修改组件代码
- **可折叠侧边栏**：侧边栏支持展开/折叠切换，折叠时显示图标与悬停提示
- **高级分页**：分页组件支持顶部/底部双展示、每页条数选择（10/20/50/100）、快速跳转指定页码
- **日期范围过滤**：`DateRangeFilter` 组件，支持快捷选项和自定义日期范围
- **可折叠搜索面板**：搜索与过滤条件区域支持折叠/展开
- **登录安全增强**：3 次失败后显示验证码，5 次失败后锁定账户 15 分钟
- **状态提示**：6 种状态（Active/Inactive/Blocked/Pending/Unblocked/Bypass）悬停 Tooltip 解释
- **统一卡片风格**：所有页面卡片采用 `rounded-2xl` 圆角、渐变色条、Section Header 统一风格
- **页脚信息**：主布局和登录页页脚显示版权信息、版本号、ICP 备案号及自定义链接
- **Nginx 安全代理**：仅 Nginx 对外暴露端口（8080→80, 8443→443），HTTP 自动重定向 HTTPS，其他服务端口不对外暴露

### 改进

- **登录错误提示**：登录失败提示改为持久显示，支持手动关闭
- **图标一致性**：Dashboard 与导航栏图标统一（Whitelisted=List, Blocked=ShieldOff）
- **Blacklist ip_address 可空**：黑名单 IP 地址字段改为可选，支持仅基于 MAC 地址的封禁
- **空值保护**：增强各组件对空值/未定义值的容错处理
- **依赖顺序启停**：按基础设施→应用→代理顺序启动，反向停止
- **前端构建产物保护**：`dist_backup` 机制防止 Docker Volume 覆盖构建产物

### Bug 修复

- 修复 DateRangeFilter onChange 不触发的问题
- 修复 Blocked 页面 `Cannot read properties of null (reading 'toLowerCase')` 错误
- 修复黑名单无法单独添加 MAC 地址（ip_address NOT NULL 约束）
- 修复 Docker 构建 TypeScript 编译错误（`NodeJS.Timeout`、`as const` 类型推断、Fragment 包裹）
- 修复 PostgreSQL 健康检查 `tam_admin does not exist`（需指定 `-d tam_db`）
- 修复 Redis 健康检查（需 `-a password` 参数）
- 修复前端容器构建产物被 Volume 覆盖的问题
- 修复 Nginx HTTPS 端口映射（内部 443，对外 8443）

---

## [1.0.0] - 2025-12

### 初始实现

- **FastAPI 后端**：基于 FastAPI + SQLAlchemy 2.0 的异步 API 服务
- **React 前端**：基于 React 18 + TypeScript + Vite 的现代化前端
- **Docker 部署**：完整的 Docker Compose 编排，包含 PostgreSQL、Redis、Nginx
- **用户认证**：JWT 令牌认证，支持登录/登出/令牌刷新
- **MAC 地址管理**：搜索、过滤、分页、状态管理
- **白名单管理**：增删查、搜索、过滤、分页
- **黑名单管理**：增删查、搜索、过滤、分页
- **审计日志**：操作记录查看、搜索、日期过滤、分页
- **仪表板**：数据概览与统计图表
- **HTTPS 支持**：Nginx 配置 SSL/TLS
- **速率限制**：认证端点请求频率限制
- **CORS 保护**：跨域请求安全配置
