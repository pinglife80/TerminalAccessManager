# TerminalAccessManager 系统架构设计文档

> 文档版本：v3.10.0  更新日期：2026-08-06

## 1. 系统概述

TerminalAccessManager 是基于 MAC 地址和 IP 地址的网络终端准入管理平台，面向企业网络环境，实现对网络终端的合规监控、自动准入控制与多数据源集成。

**核心目标：**

- **网络终端合规监控** -- 实时采集网络中终端的 IP/MAC 信息，与白名单和合规基准库进行比对，判定合规状态
- **自动准入控制** -- 对不合规终端自动执行防火墙封禁，对恢复合规的终端自动解封，实现准入策略闭环
- **多数据源集成** -- 支持多种 ARP 数据采集方式（SSH/API）和多种防火墙设备，通过数据源绑定机制灵活路由

**技术栈总览：**

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python 3.11+) |
| 数据库 | PostgreSQL 15 |
| 缓存 | Redis 7 |
| 前端框架 | React + TypeScript (Vite) |
| 反向代理 | Nginx (Alpine) |
| 容器编排 | Docker Compose |
| ORM | SQLAlchemy 2.0 (async) |
| 认证 | JWT (python-jose) + bcrypt + RBAC |
| HTTP 客户端 | httpx (async) |
| SSH 客户端 | netmiko |
| 监控 | Prometheus (可选) |

---

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                           用户层                                    │
│                        ┌──────────┐                                │
│                        │  浏览器   │                                │
│                        └────┬─────┘                                │
└─────────────────────────────┼───────────────────────────────────────┘
                              │ HTTPS
┌─────────────────────────────▼───────────────────────────────────────┐
│                           代理层                                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Nginx (Alpine)                           │  │
│  │  - SSL/TLS 终止                                               │  │
│  │  - HTTP → HTTPS 301 重定向                                    │  │
│  │  - 反向代理 /api/ → backend:8000                              │  │
│  │  - 静态资源服务 / → React SPA 构建产物                        │  │
│  │  - 上传资源代理 /uploads/ → backend:8000                      │  │
│  │  - 安全响应头 (HSTS, X-Frame-Options, CSP)                   │  │
│  │  - Gzip 压缩                                                  │  │
│  └───────────┬──────────────────────────────┬────────────────────┘  │
└──────────────┼──────────────────────────────┼───────────────────────┘
               │ 静态文件                      │ /api/
┌──────────────▼──────────┐   ┌───────────────▼──────────────────────┐
│        前端层            │   │             后端层                    │
│  ┌───────────────────┐  │   │  ┌─────────────────────────────────┐  │
│  │   React SPA       │  │   │  │      FastAPI 应用               │  │
│  │  - TypeScript     │  │   │  │  - REST API (/api/v1/)          │  │
│  │  - Vite 构建      │  │   │  │  - 5 个定时任务 (asyncio)       │  │
│  │  - Zustand 状态   │  │   │  │  - JWT 认证中间件               │  │
│  │  - React Router   │  │   │  │  - 速率限制中间件               │  │
│  │  - useBranding    │  │   │  │  - 请求日志中间件               │  │
│  │    Store 动态品牌  │  │   │  │  - 请求ID中间件                 │  │
│  │  - i18next i18n   │  │   │  │  - CORS 中间件                  │  │
│  │  - i18next i18n   │  │   │  │  - Prometheus 指标 (可选)       │  │
│  │    zh/en/ja       │  │   │  │  - WebSocket 就绪               │  │
│  │  - HeaderControls │  │   │  └─────────────────────────────────┘  │
│  │    主题+语言切换   │  │   │                                      │
│  └───────────────────┘  │   │                                      │
│  构建产物由 Nginx 直接  │   │                                      │
│  服务，不独立运行       │   │                                      │
└─────────────────────────┘   └───────────────┬──────────────────────┘
                                              │
┌─────────────────────────────────────────────▼───────────────────────┐
│                           数据层                                    │
│  ┌─────────────────────┐          ┌─────────────────────────────┐  │
│  │   PostgreSQL 15     │          │        Redis 7              │  │
│  │  - users            │          │  - 配置缓存 (5 min TTL)     │  │
│  │  - terminals          │          │  - 合规基准缓存 (10 min)  │  │
│  │  - whitelist        │          │  - 白名单缓存 (5 min)       │  │
│  │  - blacklist        │          │  - JWT 令牌黑名单           │  │
│  │  - data_sources     │          │  - 速率限制 (Sorted Set)    │  │
│  │  - data_source_     │          │  - 登录安全 (计数器/锁定)   │  │
│  │    bindings         │          │                             │  │
│  │  - compliance_      │          │                             │  │
│  │    baselines        │          │                             │  │
│  │  - system_config    │          │                             │  │
│  │  - audit_logs       │          │                             │  │
│  └─────────────────────┘          └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                              │
┌─────────────────────────────────────────────▼───────────────────────┐
│                        外部集成层                                    │
│  ┌─────────────┐   ┌──────────────────┐   ┌─────────────────────────┐  │
│  │   交换机     │   │  ComplianceBase  │   │    深信服防火墙         │  │
│  │  (SSH/API)  │   │   line 数据库    │   │    (REST API)           │  │
│  │  ARP 表采集  │   │   合规基准库     │   │    IP 封禁/解封         │  │
│  └─────────────┘   └──────────────────┘   └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 请求处理流程

请求从客户端到达 FastAPI 路由，依次经过以下中间件链：

```
Nginx → RateLimitMiddleware → RequestLoggingMiddleware → RequestIDMiddleware → FastAPI Route
```

**中间件职责：**

| 中间件 | 职责 |
|--------|------|
| RateLimitMiddleware | Redis Sorted Set 滑动窗口限流，超限返回 429 + `Retry-After` |
| RequestLoggingMiddleware | 记录请求方法、路径、状态码、响应时间 |
| RequestIDMiddleware | 为每个请求分配 12 位 hex `request_id`，通过 `ContextVar` 在请求生命周期内共享 |

**RequestIDMiddleware 机制：**

- 为每个入站请求生成 12 位十六进制 `request_id`（`os.urandom(6).hex()`）
- 通过 Python `ContextVar` 存储，在整个请求生命周期内可被任意层访问
- 响应头注入 `X-Request-ID` 和 `X-Response-Time`，便于客户端追踪与调试
- 日志系统通过 `_log_format()` 动态格式函数从 `ContextVar` 读取 `request_id`，实现日志自动关联

---

## 3. 核心业务流程

### 3.1 合规检查流程

```
ARP 数据采集          合规判定              准入执行
┌──────────┐     ┌──────────────┐     ┌──────────────────┐
│ 交换机    │     │              │     │                  │
│ SSH/API  │────→│ Terminal     │────→│ 白名单匹配?      │
│ ARP 表   │     │ compliance_  │     │ ├─ 是 → bypass   │
└──────────┘     │ status:      │     │ │   (wl_match_   │
                 │ unknown      │     │ │    type)        │
                 └──────┬───────┘     │ ├─ 合规基准匹配? │
                        │             │ │   └─ 是 →       │
                 ┌──────▼───────┐     │ │     compliant  │
                 │ 合规检查引擎  │     │ └─ 都不匹配 →    │
                 │              │     │     non_compliant │
                 └──────┬───────┘     └────────┬─────────┘
                        │                      │
              ┌───────────────────┐    ┌────────────────┐
              │ 自动封禁          │    │ 自动解封        │
              │ non_compliant     │    │ 已合规/白名单   │
              │ → 防火墙封禁 API  │    │ → 防火墙解封 API│
              │ → Blacklist 记录  │    │ → 更新状态      │
              │ → status=blocked  │    │ → status=       │
              └───────────────────┘    │   unblocked     │
                                       └────────────────┘
```

**详细步骤：**

1. **ARP 数据采集** -- 定时任务通过 SSH 或 API 从交换机获取 ARP 表，解析后写入 `Terminal` 表（`compliance_status=unknown`）；已有终端更新时重置 `compliance_status=unknown` 确保重新评估
2. **合规判定** -- 合规检查引擎依次执行：
   - 白名单匹配（IP 精确匹配 / CIDR 匹配 / IP 范围匹配 + MAC 精确匹配）→ `bypass`，记录 `wl_match_type`（`mac` / `ip` / `both`）
   - 合规基准匹配（IP + MAC 同时匹配）→ `compliant`
   - 均不匹配 → `non_compliant`
3. **自动封禁** -- `non_compliant` 终端按 `DataSourceBinding` 路由到对应防火墙，调用深信服 AF 黑白名单 API 永久封禁（`type=BLACK`，description 带 `TAM-` 前缀），创建 `Blacklist` 记录（`is_auto_blocked=True`），终端状态置为 `blocked`，`comments` 记录封堵信息
4. **自动解封** -- 已封禁终端若恢复合规或匹配白名单，调用深信服 AF 黑白名单 API 按 IP 精确删除，更新 `Blacklist.auto_unblocked=True`，终端状态置为 `unblocked`，`comments` 记录解封信息
5. **合规重算** -- 白名单增删、IPGuard 同步后触发 `recalculate_all_compliance`，批量重算所有终端合规状态，合规变更联动封堵/解封

**Terminal 状态模型：**

Terminal 模型包含两个正交维度——**Status**（封堵状态）和 **Compliance**（合规状态），二者独立变化：

| 维度 | 字段 | 取值 | 说明 |
|------|------|------|------|
| Status | `status` | `blocked` | 已被防火墙封堵 |
| | | `unblocked` | 未被封堵（默认） |
| Compliance | `compliance_status` | `unknown` | 待检查 |
| | | `compliant` | 合规（匹配合规基准） |
| | | `non_compliant` | 不合规 |
| | | `bypass` | 白名单放行 |

Status 描述的是终端在网络层的实际封堵情况，Compliance 描述的是终端的合规判定结果。二者正交：一个 `non_compliant` 终端可能因防火墙不可用而仍为 `unblocked`；一个 `blocked` 终端可能因合规基准更新后变为 `compliant` 而触发解封。

**终端管理页面操作按钮矩阵：**

终端管理页面根据终端的合规状态与封堵状态组合，动态显示不同的操作按钮：

| 合规状态 | 封堵状态 | 附加条件 | 可用操作 |
|----------|----------|----------|----------|
| compliant | unblocked | — | 仅查看详情，无操作按钮 |
| compliant | blocked | — | 查看 + 解封（含确认+comment） |
| bypass | unblocked | — | 查看 + 移出白名单（含确认） |
| non_compliant | blocked | — | 仅查看详情，无操作按钮 |
| non_compliant | unblocked | 在黑名单 | 查看 + 移出黑名单（含确认+comment） |
| non_compliant | unblocked | — | 查看 + 封锁（含确认+comment） |
| unknown | unblocked | — | 查看 + 加白名单（含comment） |
| unknown | blocked | — | 查看 + 解封（含确认+comment） |

**黑名单管理页面定位：**

黑名单管理页面定位为审计视图，仅提供黑名单记录的查看与搜索功能，移除了手动添加黑名单功能。封堵操作统一从终端管理页面发起，确保操作入口唯一、审计链路完整。

### 3.2 数据源路由机制

系统通过 `DataSource` + `DataSourceBinding` 实现多数据源灵活路由：

```
┌──────────────────────────────────────────────────────────────┐
│ DataSource (数据源定义)                                       │
│                                                              │
│  type: arp_ssh / arp_api / sangfor                │
│  tag:  唯一标识符 (如 "switch-floor1", "fw-sangfor-01")      │
│  config: JSON 连接配置 (host, port, username, password...)   │
│  enabled: 是否启用                                           │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ DataSourceBinding (绑定关系)                                  │
│                                                              │
│  arp_source_tag ──────→ firewall_tag                         │
│  "switch-floor1"  ───→ "fw-sangfor-01"                      │
│  "switch-floor1"  ───→ "fw-sangfor-02"  (多防火墙)          │
│  "switch-floor2"  ───→ "fw-sangfor-01"                      │
│                                                              │
│  封禁/解封操作通过 binding 查找对应防火墙 tag → 路由到正确设备 │
│  多防火墙场景：每个防火墙创建独立 Blacklist 记录              │
└──────────────────────────────────────────────────────────────┘
```

**路由流程：**

1. ARP 采集时，终端记录携带 `source_tag`（ARP 源标识）
2. 封禁时，通过 `DataSourceBinding.get_firewall_tags_for_arp(source_tag)` 查询关联的防火墙 tag 列表
3. 对每个防火墙 tag，查找对应 `DataSource(type=sangfor)` 获取连接配置
4. 实例化 `SangforService` 调用封禁/解封 API
5. 每个防火墙创建独立的 `Blacklist` 记录，携带 `firewall_tag` 字段

### 3.3 认证与授权流程

```
┌────────┐    GET /auth/captcha     ┌──────────────┐
│        │ ──────────────────────→  │  获取验证码   │
│        │ ←──────────────────────  │  captcha_id   │
│        │    captcha_id + question │  + question   │
│        │                          └──────────────┘
│        │
│        │    POST /auth/login      ┌──────────────┐
│        │ ──────────────────────→ │  验证码检查   │
│        │                         │ (失败次数≥3)  │
│        │                         └──────┬───────┘
│  客户端 │                                │
│        │                         ┌──────▼───────┐
│        │                         │ 账户锁定检查  │
│        │                         │ (失败次数≥5)  │
│        │                         └──────┬───────┘
│        │                                │
│        │                         ┌──────▼───────┐
│        │                         │ 密码验证      │
│        │                         │ (bcrypt)      │
│        │                         └──────┬───────┘
│        │                                │
│        │    access_token        ┌──────▼───────┐
│        │ ←────────────────────  │ 生成 JWT      │
│        │    refresh_token       │ access_token  │
│        │                        │ refresh_token │
└────────┘                        └──────────────┘
```

**认证机制：**

- **JWT 令牌认证** -- 双令牌机制：`access_token`（默认 30 分钟）+ `refresh_token`（默认 7 天），令牌携带 `jti`（UUID）用于黑名单追踪
- **Redis 令牌黑名单** -- 登出或刷新令牌时，旧 token 的 `jti` 加入 Redis 黑名单，TTL 等于 token 剩余有效期
- **登录安全** -- 三级渐进保护：
  - 失败次数 < `captcha_threshold`（默认 3）：正常登录
  - 失败次数 >= `captcha_threshold`：要求验证码
  - 失败次数 >= `max_login_attempts`（默认 5）：账户锁定 `lockout_duration_minutes`（默认 15 分钟）
- **验证码流程** -- 前端先调用 `GET /auth/captcha` 获取题目和 `captcha_id`，登录时提交 `captcha_id` 和答案
- **登录失败状态** -- 登录失败时从错误响应体（JSON detail）获取 `captcha_required`/`locked`/`lock_remaining` 状态
- **角色控制** -- `User.is_superuser` 字段区分超管与普通用户，超管专用端点通过 `get_current_active_superuser` 依赖守卫
- **认证状态恢复** -- 应用启动时前端调用 `initializeAuth()` 恢复认证状态：检查 sessionStorage 中是否存在 token → 调用 `/auth/me` 验证 token 有效性 → token 失效则尝试 refresh → 全部失败则清除会话。恢复期间 `isInitializing` 状态为 `true`，页面显示加载状态，避免未认证闪烁。`initializeAuth` 设置 10 秒超时（timeout: 10000），防止后端不可达时前端请求卡死
- **401 拦截器并发控制** -- 多个请求同时收到 401 时，仅触发一次 token 刷新：通过 `isRefreshing` 标志锁定，后续 401 请求加入 `failedQueue` 队列等待；刷新成功后重试队列中所有请求，刷新失败则统一清除会话并 toast 提示。刷新时 refresh_token 通过 Body 传递（非 Query 参数），使用 `_retry` 标志防止循环重试，React Query 配置 401 状态码不自动重试

### Token 版本号机制

密码变更后旧 Token 自动失效：

- Redis 存储每个用户的 Token 版本号（key: `token_version:{user_id}`）
- JWT payload 包含 `ver` 字段（创建时的版本号）
- Token 验证时检查 `ver` 是否与 Redis 当前版本一致
- 密码变更/重置时调用 `increment_token_version()` 递增版本号
- 旧 Token（ver 不匹配）自动被拒绝
- 无 `ver` 字段的旧 Token 视为版本 0（向后兼容）

### JWT Token 类型区分

- Access Token payload 包含 `"type": "access"`
- Refresh Token payload 包含 `"type": "refresh"`
- `/auth/refresh` 端点验证 Token 类型，拒绝 access token 用于刷新
- 旧 Token（无 type 字段）向后兼容

---

## 4. 数据流架构

```
外部数据源                    系统内部                       外部执行
┌──────────┐              ┌──────────────┐             ┌──────────┐
│ 交换机    │──SSH/API──→ │ ARP 采集服务  │             │          │
│ (ARP表)  │              │              │             │          │
└──────────┘              └──────┬───────┘             │          │
                                 │                     │          │
┌──────────┐              ┌──────▼───────┐             │ 深信服    │
│ 合规基准  │──DB───────→ │ 合规检查引擎  │──API──────→ │ 防火墙   │
│ (基准库) │              │              │←──API─────── │ (封禁/   │
└──────────┘              └──────┬───────┘             │  解封)   │
                                 │                     │          │
┌──────────┐              ┌──────▼───────┐             └──────────┘
│ 白名单    │──内存─────→ │ 状态更新      │
│ (MAC/IP/ │              │ compliance_   │
│  CIDR)   │              │ status +      │
└──────────┘              │ wl_match_type │
                          └──────────────┘
```

**数据流说明：**

| 数据流 | 方向 | 协议/方式 | 说明 |
|--------|------|-----------|------|
| 交换机 → ARP 采集服务 | 入站 | SSH (netmiko) / HTTP API (httpx) | 定时采集 ARP 表，支持 Cisco/Huawei/H3C 格式解析 |
| 合规基准 → 合规检查引擎 | 入站 | 数据库直连 (asyncpg) | 定时同步 IP+MAC 基准数据到 Redis 缓存 |
| 白名单 → 合规检查引擎 | 入站 | 内存加载 (Redis 缓存) | 白名单数据加载到内存进行 IP/MAC 匹配；白名单增删后触发合规状态批量重算（`recalculate_all_compliance`），合规状态变更联动封堵/解封操作 |
| 合规检查引擎 → 深信服防火墙 | 出站 | REST API (httpx) | 封禁/解封 IP 地址 |
| 深信服防火墙 → 合规检查引擎 | 入站 | REST API 响应 | 封禁/解封结果确认 |

---

## 5. 定时任务架构

系统通过 `asyncio.create_task` + `while True` + `asyncio.sleep` 实现 6 个后台定时任务，在 FastAPI lifespan 中启动：

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Lifespan (Startup)                      │
│                                                                     │
│  asyncio.create_task(cleanup_expired_blacklist())     ──→ Task 1   │
│  asyncio.create_task(scheduled_arp_collection())      ──→ Task 2   │
│  asyncio.create_task(scheduled_ipguard_sync())        ──→ Task 3   │
│  asyncio.create_task(scheduled_compliance_check())    ──→ Task 4   │
│  asyncio.create_task(scheduled_auto_unblock())        ──→ Task 5   │
│  asyncio.create_task(scheduled_backup())              ──→ Task 6   │
│                                                                     │
│  Shutdown: task.cancel() for all tasks                              │
└─────────────────────────────────────────────────────────────────────┘
```

| 任务 | 配置键 | 默认间隔 | 功能 |
|------|--------|----------|------|
| 过期黑名单清理 | `scheduler_firewall_query_interval` | 300s（DEFAULT_CONFIGS 种子值；代码 fallback 为 3600s） | 清理已过期的 Blacklist 记录 |
| ARP 数据采集 | `scheduler_arp_collection_interval` | 300s | 遍历所有启用的 ARP 数据源，采集并处理 |
| 合规基准数据同步 | `scheduler_ipguard_sync_interval` | 600s | 遍历所有启用的合规基准数据源，同步基准数据到 Redis；同步完成后自动触发合规重算 |
| 合规检查 | `scheduler_compliance_check_interval` | 300s | 遍历所有 ARP 源中 `compliance_status=unknown` 的记录，执行批量合规判定；发现 `non_compliant` 终端后自动触发封堵 |
| 自动解封 | `scheduler_auto_unblock_interval` | 600s | 检查已自动封禁的终端，若恢复合规则调用防火墙解封 |
| 定时备份 | `scheduler_backup_interval` | 3600s | 按 cron 表达式解析 schedule 配置，执行数据库+配置+日志备份；基于 Redis key 去重防止重复执行 |

**调度方式特点：**

- 每次循环开始时从 `ConfigService` 读取间隔配置，支持运行时热调整
- 间隔值被钳位在 30-86400 秒范围内（`max(30, min(86400, interval))`）
- 每次迭代创建独立的数据库会话，避免长事务
- 异常被捕获并记录日志，不会中断任务循环
- 应用关闭时通过 `task.cancel()` 优雅终止
- 每个任务循环中通过 `_is_task_paused()` 函数检查 Redis 暂停键 `scheduler:ctrl:{task}`
- 当键值为 `"paused"` 时，跳过当轮执行并继续等待下一轮
- `manage.sh scheduler pause` 写入该键，`resume` 删除该键
- 暂停机制现在真正生效（之前仅设置键但任务未检查）

---

## 6. 缓存架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Redis 缓存层                              │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ 配置缓存         │  │ 合规基准缓存     │  │ 白名单缓存     │  │
│  │ sys_config:{key} │  │ compliance_      │  │ whitelist:all  │  │
│  │ TTL: 300s        │  │ baseline:{tag}   │  │ TTL: 300s      │  │
│  │ 写穿透           │  │ TTL: 600s        │  │ 写时失效       │  │
│  └─────────────────┘  │ 定时同步刷新     │  └────────────────┘  │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ 令牌黑名单       │  │ 速率限制         │  │ 登录安全       │  │
│  │ token_blacklist: │  │ rate_limit:      │  │ login_attempts:│  │
│  │   {jti}          │  │   {ip}:{path}    │  │   {username}  │  │
│  │ TTL: token 剩余  │  │ Sorted Set       │  │ login_lock:   │  │
│  │   有效期         │  │ 60s 滑动窗口     │  │   {username}  │  │
│  └─────────────────┘  └─────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

| 缓存类型 | Key 模式 | TTL | 更新策略 | 说明 |
|----------|----------|-----|----------|------|
| 配置缓存 | `sys_config:{key}` | 300s (5 min) | 写穿透（更新时立即失效） | 三层读取：Redis → DB → .env |
| 合规基准缓存 | `compliance_baseline:{source_tag}` | 600s (10 min) | 定时同步刷新 | 存储 IP+MAC 映射 JSON |
| 白名单缓存 | `whitelist:all` | 300s (5 min) | 写时失效（白名单变更时 `invalidate_whitelist_cache`） | 存储全量白名单数据 |
| 令牌黑名单 | `token_blacklist:{jti}` | token 剩余有效期 | 登出/刷新时写入 | 值为 `"1"`，自动过期 |
| 速率限制 | `rate_limit:{ip}:{path}` | 60s | Sorted Set 滑动窗口 | score=时间戳，member=请求ID |
| 登录计数 | `login_attempts:{username}` | 锁定时长 | 递增计数 | 首次设置时指定过期时间 |
| 登录锁定 | `login_lock:{username}` | 锁定时长 | 超过阈值时写入 | 值为失败次数 |
| 暂停控制 | `scheduler:ctrl:{task_name}` | 无（手动管理） | `manage.sh scheduler pause` 写入、`resume` 删除 | 标记定时任务暂停状态，值为 `"paused"`，`_is_task_paused()` 在任务循环中检查 |
| Redis 故障降级 | 所有 Redis 交互 | — | try/except 异常捕获 | Redis 不可用时按混合策略降级（黑名单/验证码校验 fail-closed 拒绝，版本号/登录防护 fail-open 放行等），详见 7.7 节 |

**速率限制算法（Sorted Set 滑动窗口）：**

1. `ZREMRANGEBYSCORE` -- 移除 60 秒窗口之前的记录
2. `ZADD` -- 添加当前请求（score=当前时间戳）
3. `ZCARD` -- 统计窗口内请求数
4. `EXPIRE` -- 设置 key 过期时间（60s）
5. 若请求数超过限制，计算 `Retry-After` 并返回 429

---

## 7. 安全架构

### 7.1 传输安全

- Nginx 执行 SSL/TLS 终止，强制 HTTPS（HTTP 80 → HTTPS 443 301 重定向）
- TLS 1.2 / 1.3，优先 ECDHE 密码套件
- HSTS 响应头（`max-age=63072000`）

### 7.2 认证安全

- **JWT 双令牌** -- access_token + refresh_token，令牌携带 `jti`（UUID）唯一标识
- **Redis 令牌黑名单** -- 登出/刷新时旧 token 加入黑名单，TTL = token 剩余有效期，自动过期清理
- **刷新机制** -- refresh_token 换取新 access_token，旧 access_token 加入黑名单

### 7.3 密码安全

- **bcrypt 哈希** -- 直接使用 bcrypt 库，work factor 12
- **复杂度校验** -- 注册/修改密码时 Pydantic 校验长度和字符组成

### 7.4 登录保护

- **验证码** -- 失败次数 >= `captcha_threshold`（默认 3）时要求验证码
- **账户锁定** -- 失败次数 >= `max_login_attempts`（默认 5）时锁定 `lockout_duration_minutes`（默认 15 分钟）
- **限流** -- 认证接口独立限流（默认 5 次/分钟/IP）

### 7.5 API 安全

| 措施 | 实现方式 |
|------|----------|
| CORS | CORSMiddleware，白名单域名，限制方法和头部。当 `allow_origins=["*"]` 时自动降级 `allow_credentials=False`，防止 CORS 规范违规 |
| 速率限制 | RateLimitMiddleware，Redis Sorted Set 滑动窗口 |
| 输入验证 | Pydantic Schema 严格校验所有请求体 |
| SQL 注入防护 | SQLAlchemy ORM 参数化查询 |
| 安全响应头 | Nginx 层 X-Frame-Options / X-Content-Type-Options / X-XSS-Protection |
| 生产环境 | 禁用 /docs /redoc /openapi.json |

### 7.6 权限控制

- `User.is_superuser` 字段区分超管与普通用户
- `get_current_active_superuser` 依赖守卫超管专用端点（用户管理、系统配置等）
- `get_current_user` 依赖守卫常规认证端点

### RBAC 权限控制架构

系统采用基于角色的访问控制（RBAC）模型，通过角色（Role）将权限（Permission）与用户（User）关联：

- **数据模型**: 4张核心表（roles, permissions, user_roles, role_permissions），5个预设角色，29个权限码
- **权限检查**: `require_permission(code)` FastAPI 依赖注入工厂函数，superuser 直接通过，普通用户通过 Redis 缓存（TTL 300s）+ 数据库回查
- **前端控制**: `usePermission` Hook + `ProtectedRoute` 路由守卫 + 侧边栏导航过滤 + 按钮级权限控制
- **超管隔离**: 非超管用户不可见/不可管理超管用户，superadmin 角色不可分配/修改
- **详细文档**: 参见 [RBAC.md](RBAC.md)

### 7.7 Redis 故障降级

系统采用混合策略处理 Redis 不可用场景，10 个 Redis 交互函数统一添加 try/except 异常处理，根据安全级别选择 fail-closed 或 fail-open：

| 场景 | 降级行为 | 策略 | 安全影响 |
|------|---------|------|---------|
| 令牌黑名单不可用 | 拒绝请求（`is_token_blacklisted` 返回 `True`） | fail-closed | 已注销的 token 不可用，但合法 token 也可能被误拒；确保已注销 token 不会被复用 |
| 验证码校验不可用 | 校验失败（`verify_captcha` 返回 `False`） | fail-closed | 验证码校验不可用时拒绝验证，防止绕过验证码保护 |
| Token 版本号不可用 | 视为初始版本（`get_token_version` 返回 `0`） | fail-open | 密码变更后旧 token 短暂可用 |
| Token 版本递增不可用 | 静默降级（`increment_token_version` 返回 `0`） | fail-open | 密码变更后旧 token 短暂可用 |
| 登录防护不可用 | 放行登录（`check_login_attempts`/`check_captcha_required` 返回 `False`） | fail-open | 暴力破解防护短暂失效 |
| 验证码生成不可用 | 抛出异常（`generate_captcha` 必须 Redis） | — | 需要验证码的登录暂时不可用 |
| 限流不可用 | 放行请求（`RateLimitMiddleware` 降级） | fail-open | API 限流短暂失效 |

设计原则：**安全性优先于可用性**（fail-closed）与 **可用性优先于安全性**（fail-open）混合 — 涉及令牌黑名单和验证码校验等关键安全检查采用 fail-closed 策略，确保安全边界不被突破；登录防护、版本号等非关键路径采用 fail-open 策略，避免 Redis 故障导致服务完全不可用。所有降级行为均记录 `logger.warning` 日志，便于运维发现和排查。

---

## 8. 部署架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Docker Compose 编排                              │
│                                                                     │
│  ┌──────────┐                                                       │
│  │  Nginx   │ :8080 (HTTP) → 301 → :8443 (HTTPS)                   │
│  │  Alpine  │ :8443 (HTTPS) ← 唯一对外暴露端口                      │
│  └────┬─────┘                                                       │
│       │ /api/          │ 静态文件          │ /uploads/               │
│       ▼                ▼                   ▼                         │
│  ┌──────────┐   ┌──────────┐       ┌──────────┐                    │
│  │ Backend  │   │ Frontend │       │ Backend  │                    │
│  │ FastAPI  │   │ (构建阶段)│       │ /uploads │                    │
│  │ :8000    │   │ dist →   │       │          │                    │
│  │ (内部)   │   │ Volume   │       │          │                    │
│  └────┬─────┘   └──────────┘       └──────────┘                    │
│       │                                                             │
│  ┌────▼─────────────────────────────────────────────┐              │
│  │              tam_network (bridge)        │              │
│  │  ┌────────────┐         ┌────────────┐           │              │
│  │  │ PostgreSQL │         │   Redis    │           │              │
│  │  │ :5432      │         │ :6379      │           │              │
│  │  │ (内部)     │         │ (内部)     │           │              │
│  │  └─────┬──────┘         └─────┬──────┘           │              │
│  │        │                      │                  │              │
│  │  ┌─────▼──────┐         ┌─────▼──────┐           │              │
│  │  │ postgres_  │         │ redis_data │           │              │
│  │  │ data       │         │ Volume     │           │              │
│  │  │ Volume     │         │            │           │              │
│  │  └────────────┘         └────────────┘           │              │
│  └───────────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

**部署要点：**

| 项目 | 说明 |
|------|------|
| 容器编排 | Docker Compose，5 个服务：nginx + backend + postgres + redis + frontend |
| 网络隔离 | `tam_network` bridge 网络，仅 Nginx 对外暴露端口（8080/8443） |
| 数据持久化 | `postgres_data` + `redis_data` 两个 Docker Volume |
| 前端构建 | `frontend` 容器执行构建，产物写入 `frontend_dist` Volume，Nginx 挂载该 Volume 提供服务 |
| 健康检查 | PostgreSQL 和 Redis 均配置 healthcheck，backend 通过 `depends_on` 确保依赖就绪 |
| 环境变量 | 通过 `.env` 文件注入，包含数据库密码、Redis 密码、JWT 密钥等敏感配置 |
| 重启策略 | 所有服务设置 `restart: unless-stopped`（frontend 除外，为一次性构建），容器异常退出后自动重启 |

**容器安全加固：**

| 措施 | 说明 |
|------|------|
| `cap_drop: [ALL]` | 5 个服务统一移除所有 Linux capabilities |
| `cap_add: [NET_BIND_SERVICE]` | nginx 需要绑定 80/443 低位端口 |
| `security_opt: no-new-privileges:true` | 所有服务禁止权限提升 |

---

## 9. 搜索/查询架构

系统采用服务端分页 + 模糊搜索架构，所有列表查询接口统一返回 `PaginatedResponse` 结构：

```
PaginatedResponse[T]
├── items: List[T]       # 当前页数据
├── total: int           # 总记录数
├── page: int            # 当前页码（从 1 开始）
├── page_size: int       # 每页条数
└── total_pages: int     # 总页数
```

**搜索机制：**

| 特性 | 实现方式 |
|------|----------|
| 模糊搜索 | PostgreSQL `ILIKE` 模式匹配，搜索关键词自动添加 `%keyword%` 通配符 |
| LIKE 通配符注入防护 | `_escape_like()` 函数转义 `%` → `\%`、`_` → `\_`，所有 ilike 查询统一使用 `_escape_like()` 包装搜索词 |
| MAC 地址格式无关搜索 | 白名单/黑名单搜索使用 `func.replace` 去除 MAC 地址分隔符（`-`、`:`、`.`）后 `ILIKE` 匹配，用户输入任意格式均可命中 |
| 服务端分页 | 后端根据 `page` + `page_size` 参数执行 `OFFSET/LIMIT` 查询，返回分页元数据 |
| 前端防抖 | 搜索输入使用 debounce（300ms），减少无效请求 |
| 前端 keepPreviousData | React Query 使用 `keepPreviousData: true`（或 `placeholderData: keepPreviousData`），搜索切换时保留上一页数据直到新数据返回，防止页面闪烁 |
| 数据库索引 | 对高频搜索字段（IP、MAC 等）建立索引，加速 ILIKE 前缀匹配查询 |

**MAC 地址标准化搜索原理：**

```sql
-- 使用 mac_address_normalized 列（已建索引）进行搜索
-- 写入时自动填充：mac_address_normalized = UPPER(REPLACE(REPLACE(REPLACE(mac_address, '-', ''), ':', ''), '.', ''))
WHERE mac_address_normalized ILIKE 'AABBCCDDEEFF%'
```

用户无论输入 `AA-BB-CC-DD-EE-FF`、`AA:BB:CC:DD:EE:FF`、`AABBCCDDEEFF` 中的哪种格式，后端统一去除分隔符后使用标准化列前缀匹配，命中索引，避免全表扫描。

**搜索流程：**

```
用户输入搜索词
      │
      ▼ debounce (300ms)
      │
      ▼ 前端发起请求 (page, page_size, search)
      │  keepPreviousData: 保留旧数据直到新数据返回
      │
      ▼ 后端查询
      │  ├─ 终端: ILIKE 模糊搜索
      │  └─ 白名单/黑名单: MAC 标准化列搜索 (mac_address_normalized + ILIKE)
      │
      ▼ 返回 PaginatedResponse
      │
      ▼ 前端解构 { items, total, page, page_size, total_pages }
```

**适用页面：** 终端管理、白名单管理、黑名单管理、审计日志

---

## 10. 配置管理架构

系统采用三层配置读取 + 分类管理的架构，支持运行时热修改：

### 10.1 三层配置读取

```
读取请求 ──→ Redis 缓存 ──→ 数据库 ──→ .env 回退
             (命中则返回)   (命中则     (最终回退)
                            缓存并返回)
```

**写入流程：**

```
写入请求 → Pydantic 校验 → 数据库持久化 → Redis 缓存失效
```

### 10.2 配置分类

| 分类 | 配置项 | 可修改 |
|------|--------|--------|
| **security** | max_login_attempts, lockout_duration_minutes, captcha_threshold, allow_registration, access_token_expire_minutes, refresh_token_expire_days | 是 |
| **rate_limit** | rate_limit_per_minute, auth_rate_limit_per_minute | 是 |
| **network** | sangfor_enabled, sangfor_base_url, switch_enabled, switch_host, ipguard_enabled, ipguard_host | 是 |
| **scheduler** | scheduler_arp_collection_interval, scheduler_ipguard_sync_interval, scheduler_firewall_query_interval, scheduler_compliance_check_interval, scheduler_auto_unblock_interval, scheduler_backup_interval | 是 |
| **general** | environment, debug, log_level | environment/debug 只读 |
| **branding** | app_name, app_short_name, app_subtitle, login_heading, login_subheading, login_footer_text, login_bg_url, favicon_url, footer_copyright, footer_icp_number, footer_icp_url | 是 |
| **backup** | backup_retain_count | 是 |

### 10.3 只读配置

`environment` 和 `debug` 标记为 `is_readonly=True`，不可通过 API 修改，防止运行时变更导致系统行为异常。

### 10.4 配置热加载

- 定时任务每次循环从 `ConfigService` 读取间隔配置，修改后下次循环即生效
- JWT 令牌过期时间从 `ConfigService` 读取，修改后新签发的令牌使用新过期时间
- 速率限制阈值从 `ConfigService` 读取，修改后即时生效
- 登录安全阈值（验证码/锁定）从 `ConfigService` 读取，修改后即时生效

### 10.5 新增环境变量（v3.2.0-r2）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | — | 自定义初始管理员密码，deploy/init 时写入 .env |
| `BACKUP_RETAIN_COUNT` | `0`（保留全部） | 备份文件保留数量，超出时自动清理最旧的备份 |
| `TAM_LOG_ENABLED` | `false` | manage.sh 操作日志开关，启用后所有命令执行记录写入 `.manage/logs/` |

---

## 11. 可扩展性设计

### 11.1 数据源插件化

系统通过 `DataSource.type` 字段支持三种数据源类型，新增类型只需：

1. 在 `DataSourceService.VALID_TYPES` 中注册新类型
2. 实现对应的采集/连接逻辑
3. 在 `test_connection` 中添加新类型的测试方法

当前支持类型：

| 类型 | 说明 | 采集方式 | 认证方式 |
|------|------|----------|----------|
| `arp_ssh` | 交换机 SSH 采集 | netmiko SSH 连接，自动分页和设备类型检测，解析 ARP 表 | password（SSH 用户名+密码） |
| `arp_api` | 交换机 API 采集 | httpx HTTP 请求，解析 JSON 响应 | basic / bearer / header（自定义 Header 名+值） |
| `sangfor` | 深信服防火墙 | httpx HTTP 请求，黑白名单 API 永久封堵/解封 | basic / bearer / header（自定义 Header 名+值） |

合规基准数据通过独立的 `ComplianceBaseline` 模型管理，支持 CRUD、测试连接和手动同步操作。

### 11.2 防火墙扩展

通过 `DataSourceBinding` 绑定新防火墙：

1. 创建 `DataSource(type=sangfor, tag="fw-new")` 定义新防火墙连接
2. 创建 `DataSourceBinding(arp_source_tag="switch-x", firewall_tag="fw-new")` 绑定关系
3. 封禁/解封操作自动路由到新防火墙

多防火墙场景下，每个防火墙创建独立的 `Blacklist` 记录，携带 `firewall_tag` 字段用于追踪。

### 11.3 配置热加载

`ConfigService` 支持运行时修改所有非只读配置，修改后通过 Redis 缓存失效机制即时生效，无需重启服务。

### 11.4 前端品牌动态化

前端通过 `useBrandingStore`（Zustand）从后端 `/api/v1/settings/` 加载品牌配置：

- 应用名称、副标题、登录页文案
- 登录背景图、Favicon
- 页脚版权信息、ICP 备案号

品牌配置存储在 `system_config` 表的 `branding` 分类中，修改后前端刷新即可生效。

---

## 12. i18n 国际化架构

系统采用 i18next 生态实现前端国际化，支持中文（zh）、英文（en）、日语（ja）三种语言。

### 12.1 技术栈

| 组件 | 说明 |
|------|------|
| i18next | 核心国际化框架，管理翻译资源和语言切换 |
| react-i18next | React 绑定层，提供 `useTranslation` Hook 和 `Trans` 组件 |
| i18next-browser-languagedetector | 自动检测浏览器语言，支持多种检测策略 |

### 12.2 语言检测与持久化

```
应用启动
    │
    ▼ i18next-browser-languagedetector
    │  检测顺序：localStorage → navigator → fallback
    │
    ▼ 检测到语言 (zh/en/ja)
    │
    ▼ 加载对应翻译资源
    │
    ▼ 渲染界面
```

- **自动检测**：通过 `i18next-browser-languagedetector` 自动检测浏览器语言设置
- **持久化**：用户手动切换语言后，选择结果写入 `localStorage`（key: `i18nextLng`），下次访问自动应用
- **回退语言**：若检测到的语言不在支持列表中，回退到英文（en）

### 12.3 翻译覆盖范围

14 个页面/组件全部完成 i18n 替换，包括：登录页、仪表盘、终端管理、白名单管理、黑名单管理、审计日志、数据源管理、合规基准、用户管理、系统设置、Sidebar、HeaderControls、通用组件等。

---

## 13. 前端布局架构

### 13.1 Layout 顶栏结构

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layout 顶栏                                                        │
│  ┌──────────────────────────────┐  ┌────────────────────────────┐  │
│  │  Sidebar Toggle + 应用名称    │  │      HeaderControls        │  │
│  │  (左侧)                      │  │      (右侧)                │  │
│  └──────────────────────────────┘  │  ┌──────────────────────┐  │  │
│                                     │  │ 主题切换             │  │  │
│                                     │  │ ☀ 浅色 | 🌙 深色    │  │  │
│                                     │  │ 💻 跟随系统          │  │  │
│                                     │  ├──────────────────────┤  │  │
│                                     │  │ 语言选择 🌐          │  │  │
│                                     │  │ ├─ 中文              │  │  │
│                                     │  │ ├─ English           │  │  │
│                                     │  │ └─ 日本語            │  │  │
│                                     │  └──────────────────────┘  │  │
│                                     └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 13.2 HeaderControls 组件

位于页面顶部右上角，包含两个功能区域：

| 功能 | 实现方式 | 说明 |
|------|----------|------|
| 主题切换 | 三选项并列按钮 | 浅色（light）/ 深色（dark）/ 跟随系统（system），使用 Tailwind CSS `dark:` 变体实现深色主题 |
| 语言选择 | Globe 图标下拉菜单 | 显示当前语言，点击展开下拉菜单选择中文/英文/日语 |

---

## 14. 审计日志架构

### 14.1 action 统一命名规范

审计日志的 `action` 字段采用 `{动词}_{对象}` 命名规范，确保语义清晰一致：

| 旧 action 值 | 新 action 值 | 说明 |
|---|---|---|
| `block_ip` | `block_terminal` | 封禁终端（从终端管理页面操作） |
| `unblock_ip` | `unblock_terminal` | 解封终端（从终端管理页面操作） |
| `block` | `block_blacklist` | 加入黑名单 |
| `unblock` | `unblock_blacklist` | 移出黑名单 |

新增 action 值：

| action 值 | 说明 |
|---|---|
| `login` | 用户登录 |
| `logout` | 用户登出 |
| `create_datasource` | 创建数据源 |
| `update_datasource` | 更新数据源 |
| `delete_datasource` | 删除数据源 |
| `test_datasource` | 测试数据源连接 |
| `sync_datasource` | 同步数据源 |
| `create_user` | 创建用户 |
| `update_user` | 更新用户 |
| `delete_user` | 删除用户 |
| `reset_password` | 重置密码 |
| `unlock_user` | 解锁用户 |
| `update_config` | 更新系统配置 |

### 14.2 10 类分类体系

前端审计日志按 10 个分类进行过滤展示：

| 分类 | 包含的 action | badge 颜色 |
|------|---------------|------------|
| 终端管理 | block_terminal, unblock_terminal | 红色/绿色 |
| 黑名单 | block_blacklist, unblock_blacklist | 红色/绿色 |
| 白名单 | add_whitelist, remove_whitelist | 蓝色/灰色 |
| 认证 | login, logout | 紫色/灰色 |
| 数据源 | create_datasource, update_datasource, delete_datasource, test_datasource, sync_datasource | 青色 |
| 用户管理 | create_user, update_user, delete_user, reset_password, unlock_user | 橙色 |
| 角色 | create_role, update_role, delete_role, assign_role, remove_role | 靛色 |
| 合规 | compliance_check, compliance_recalculate | 棕色 |
| 系统配置 | update_config | 黄色 |
| 定时任务 | cleanup_expired | 灰色 |

### 14.3 details JSON 格式存储

审计日志的 `details` 字段统一使用 `json.dumps` 序列化为 JSON 格式存储，每个 dict 包含 `message` 字段：

```json
{"message": "Blocked terminal 192.168.1.100", "ip_address": "192.168.1.100", "mac_address": "AA-BB-CC-DD-EE-FF"}
```

前端审计日志页面解析 `details` 字段时，对 JSON 格式内容进行解析并格式化展示。详情 key 支持翻译显示，通过 i18n 映射将 key（如 `ip_address`、`mac_address`）翻译为当前语言的标签。

### 14.4 统计卡片

审计日志页面顶部统计卡片优化为两个核心指标：

| 卡片 | 说明 |
|------|------|
| 日志总数 | 当前筛选条件下的审计日志总量 |
| 安全事件 | 封堵/解封/黑名单等安全相关操作的数量统计 |

### 14.5 log_action 公共函数

`TerminalService._log_action` 改为公共函数 `log_action`，新增 `ip_address` 参数：

```python
async def log_action(
    db: AsyncSession,
    username: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict,
    ip_address: str = None,  # 新增：请求来源 IP
) -> None:
```

- `details` 参数接收 dict，内部使用 `json.dumps(details, ensure_ascii=False)` 序列化
- `ip_address` 参数记录操作来源 IP，供安全审计追溯

---

## 15. 页面闪烁修复架构决策

### 15.1 Suspense 位置调整

将 `React.Suspense` 从 Layout 的 `<Outlet>` 内层移到外层，避免路由切换时整个 Layout（含 Sidebar）重新挂载导致的闪烁：

```
修复前：
<Layout>
  <Sidebar />
  <Suspense fallback={<Loading />}>
    <Outlet />     ← Suspense 在 Outlet 内层
  </Suspense>
</Layout>

修复后：
<Suspense fallback={<Loading />}>
  <Layout>
    <Sidebar />
    <Outlet />     ← Suspense 在 Layout 外层
  </Layout>
</Suspense>
```

### 15.2 QueryClient staleTime

React Query 的 `QueryClient` 默认 `staleTime` 从 0 调整为 30 秒（30000ms），减少不必要的后台重新请求：

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,  // 30 秒内数据视为新鲜，不触发后台重新请求
      retry: (failureCount, error) => {
        // 401 状态码不重试，避免与认证拦截器冲突
        if (error?.response?.status === 401) return false;
        return failureCount < 3;
      },
    },
  },
});
```

### 15.3 Sidebar hover 预加载

Sidebar 菜单项在鼠标 hover 时预加载对应页面的数据（通过 React Query 的 `queryClient.prefetchQuery`），用户点击时数据已缓存，实现页面即时渲染：

```
用户 hover Sidebar 菜单项
      │
      ▼ onMouseEnter 触发 prefetchQuery
      │
      ▼ 后台预加载该页面数据
      │
      ▼ 用户点击菜单项
      │
      ▼ 数据已缓存，页面即时渲染（无闪烁）
```

---

## 16. 异常处理架构

### 16.1 全局异常处理器

系统通过 FastAPI 的 `add_exception_handler` 注册 3 个全局异常处理器，统一错误响应格式：

```
请求 → FastAPI 路由
          │
          ├─ 正常处理 → 返回业务响应
          │
          ├─ HTTPException → http_exception_handler → 透传 detail
          │
          ├─ RequestValidationError → validation_exception_handler → 422 校验错误
          │
          └─ 其他未捕获异常 → unhandled_exception_handler → 500 + error_id
```

| 处理器 | 异常类型 | 状态码 | 响应格式 |
|--------|---------|--------|---------|
| `http_exception_handler` | `StarletteHTTPException` | 原始状态码 | `{"detail": ...}`（透传，保持业务端点现有格式） |
| `validation_exception_handler` | `RequestValidationError` | 422 | FastAPI 默认校验错误格式 |
| `unhandled_exception_handler` | `Exception` | 500 | `{"detail": {"message": "Internal server error", "error_id": "..."}}` |

**error_id 机制：** 未捕获异常生成 8 位 UUID 前缀作为 error_id，同时写入 `logger.error` 日志和响应体，运维可通过 error_id 在日志中快速定位具体异常。

### 16.2 Redis 故障降级

所有 Redis 交互函数采用 try/except + 混合降级策略（fail-closed / fail-open），异常时记录 `logger.warning` 并按策略降级（详见 7.7 Redis 故障降级）。

---

## 17. 日志架构

### 17.1 日志库与配置

- **日志库**：loguru，集中式配置于 `logging_config.py`
- **初始化入口**：`setup_logging()` 函数，在 FastAPI lifespan 启动时调用

### 17.2 日志格式

```
YYYY-MM-DD HH:mm:ss.SSS ZZ | LEVEL | request_id | 模块:函数:行号 - 消息
```

示例：

```
2026-06-10 14:30:00.123 +08:00 | INFO | a1b2c3d4e5f6 | auth:login:42 - User login successful
2026-06-10 14:30:01.456 +08:00 | WARNING | - | scheduler:arp_collect:88 - Redis unavailable, fail-open
```

### 17.3 request_id 自动注入

- 通过 `_log_format()` 动态格式函数从 `ContextVar` 读取当前请求的 `request_id`
- 请求上下文中：`request_id` 为 RequestIDMiddleware 分配的 12 位 hex 值
- 非请求上下文（定时任务、启动日志）：`request_id` 显示为 `-`

### 17.4 时区控制

- `config.py` 中 `TZ` 配置项设定目标时区
- `setup_logging()` 调用 `time.tzset()` 使进程时区生效
- loguru 格式中 `ZZ` 占位符显示正确的时区偏移（如 `+08:00`）

---

## 18. 时区控制架构

系统各层时区控制机制如下：

```
.env TZ=Asia/Shanghai
      │
      ▼ docker-compose.yml TZ 环境变量
      │
      ├─→ 所有容器系统时间
      │
      ├─→ 后端：config.py TZ → setup_logging() time.tzset() → loguru ZZ
      │
      ├─→ PostgreSQL：log_timezone / timezone 参数
      │
      └─→ 前端：logger.ts new Date() 本地时区
```

**各层时区策略：**

| 层次 | 时区来源 | 说明 |
|------|----------|------|
| 容器系统 | `.env TZ` → `docker-compose.yml` 环境变量 | 所有容器共享同一 TZ 设置，系统时间一致 |
| 后端 Python | `config.py TZ` → `setup_logging()` `time.tzset()` | 进程启动时设置时区，loguru `ZZ` 显示正确偏移 |
| PostgreSQL | `log_timezone` / `timezone` 参数 | 数据库日志和查询时间使用配置的时区 |
| 前端 | `logger.ts` `new Date()` 本地时区 | 浏览器端日志使用客户端本地时区 |

---

## 19. 事件通知服务架构

### 19.1 架构设计

系统采用直发式通知架构，业务模块直接通过 NotificationService 发射事件到 Redis Queue，Worker 异步消费并分发到各通知渠道：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      事件通知服务                                    │
│                                                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐    │
│  │ 业务模块     │    │Notification  │    │   通知渠道          │    │
│  │ (Compliance │───→│ Service.emit │───→│                     │    │
│  │  Terminal等) │    │              │    │  Email (SMTP)       │    │
│  └─────────────┘    └──────┬───────┘    │  DingTalk (Webhook) │    │
│                             │            │  WeCom (Webhook)    │    │
│                             ▼            │  Generic Webhook    │    │
│                   ┌──────────────────┐   └─────────────────────┘    │
│                   │  Redis Queue     │                              │
│                   │ notify:queue:main│                              │
│                   └────────┬─────────┘                              │
│                            │                                        │
│                            ▼                                        │
│                   ┌──────────────────┐                              │
│                   │  Worker Pipeline │                              │
│                   │  (事件处理+分发)  │                              │
│                   └──────────────────┘                              │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                 通知日志 (notification_logs)                │    │
│  │  - channel_id, event_type, status, error_message          │    │
│  │  - retries, created_at, updated_at                        │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

> **v3.9.0 架构变更**：移除 NotificationAggregator 优先级聚合路径，改为业务模块 → NotificationService.emit → Redis Queue → Worker 的直发式管道。实时事件（REALTIME_EVENT_TYPES）跳过队列直接同步发送。

### 19.2 支持的事件类型

| 事件类型 | 说明 |
|----------|------|
| `terminal_blocked` | 终端被封堵 |
| `terminal_unblocked` | 终端被解封 |
| `compliance_changed` | 合规状态变更 |
| `login_success` | 用户登录成功 |
| `login_failed` | 用户登录失败 |
| `backup_completed` | 备份完成 |
| `config_changed` | 配置变更 |
| `terminal.offline` | 终端离线 |
| `alert.auto_block_triggered` | 自动封锁触发告警 |

> **实时事件机制**：`REALTIME_EVENT_TYPES` 集合定义了需要立即发送的事件类型（如 `alert.auto_block_triggered`），通过 `is_realtime_event()` 函数判断。实时事件跳过 Redis Queue 直接同步发送，确保告警时效性。

### 19.3 通知渠道接口

所有通知渠道实现统一接口：

```python
class NotificationChannel(ABC):
    @abstractmethod
    async def send(self, event: dict) -> bool:
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        pass
```

### 19.4 关键特性

- **异步发布**：事件发布不阻塞业务流程
- **渠道隔离**：单个渠道失败不影响其他渠道
- **重试机制**：失败通知自动重试
- **日志追踪**：完整记录每条通知的发送状态和错误信息
- **实时事件直发（REALTIME_EVENT_TYPES）**：关键告警事件跳过队列直接同步发送，确保时效性
- **事件覆盖率监控（event_coverage）**：统计已定义事件类型与实际发射次数的比率，用于识别未使用的事件
- **模块级单例替代 ContextVar**：NotificationService 使用模块级单例实例，简化调用链路

---

## 20. 认证提供者架构

### 20.1 插件化设计

系统采用接口抽象 + 具体实现的插件化架构，支持多种认证方式：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      认证提供者系统                                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    AuthProvider (接口)                        │    │
│  │  ├─ authenticate(username, password) → User | None          │    │
│  │  ├─ get_user_by_username(username) → User | None           │    │
│  │  └─ validate_config(config) → bool                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ▲                                      │
│                              │ 实现                                 │
│  ┌───────────────────────────┼─────────────────────────────────┐    │
│  │                           │                                 │    │
│  │  ┌───────────────┐  ┌─────┴─────┐  ┌───────────────────┐    │    │
│  │  │ LocalProvider │  │LDAPProvider│  │ OAuthProvider     │    │    │
│  │  │ (本地认证)    │  │(LDAP/AD)   │  │ (预留扩展)        │    │    │
│  │  └───────────────┘  └───────────┘  └───────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │               auth_providers (数据库表)                      │    │
│  │  - name, type, config (JSON), enabled                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 20.2 LDAP认证安全

LDAP认证提供者实现了以下安全防护：

| 措施 | 说明 |
|------|------|
| **用户名验证** | 正则校验用户名格式，仅允许 `a-zA-Z0-9_.@-` |
| **DN注入防护** | 转义LDAP特殊字符（`\*()\"=<>,+.\\/:`） |
| **连接泄漏防护** | finally块确保连接正确关闭 |

---

## 21. 备份服务架构

### 21.1 备份流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                      备份服务                                       │
│                                                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐    │
│  │ 数据库备份   │    │  配置文件     │    │   创建归档          │    │
│  │ (pg_dump)   │───→│  备份         │───→│   (.zip)           │    │
│  └─────────────┘    │ (docker-     │    ├─────────────────────┤    │
│                     │  compose.yml, │    │   校验和计算        │    │
│                     │  manage.sh)   │    │   (SHA256)         │    │
│                     └──────────────┘    └─────────────────────┘    │
│                                                │                   │
│                                                ▼                   │
│                              ┌─────────────────────┐               │
│                              │    存储              │               │
│                              │  ├─ 本地存储         │               │
│                              │  └─ SFTP远程存储     │               │
│                              └─────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### 21.2 安全特性

| 特性 | 说明 |
|------|------|
| **敏感信息排除** | 不备份 `.env` 文件，避免密码泄露 |
| **路径遍历防护** | download/restore/delete端点添加路径检查 |
| **SFTP主机密钥验证** | 添加主机密钥验证策略 |
| **FTP支持移除** | 强制使用SFTP安全传输 |

### 21.3 备份轮转

- 配置保留天数（`retention_days`）
- 自动清理超过保留期的旧备份
- 清理操作使用 `asyncio.to_thread` 避免阻塞事件循环

### 21.4 v3.10.0 变更记录

> v3.10.0 变更：
> - 系统配置分类新增 `ALERT`（告警阈值配置）
> - 新增 `AlertConfigResponse` 模型和 4 条 alert 默认配置
> - 备份恢复架构增强：白名单恢复、日志恢复、begin_nested 事务保护
> - 远程备份清理架构：SFTP/FTP 过期备份自动删除
