# TerminalAccessManager 系统架构设计文档

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
| 认证 | JWT (python-jose) + bcrypt |
| HTTP 客户端 | httpx (async) |
| SSH 客户端 | paramiko |
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
│  │    Store 动态品牌  │  │   │  │  - CORS 中间件                  │  │
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
              ┌─────────▼─────────┐    ┌───────▼────────┐
              │ 自动封禁          │    │ 自动解封        │
              │ non_compliant     │    │ 已合规/白名单   │
              │ → 防火墙封禁 API  │    │ → 防火墙解封 API│
              │ → Blacklist 记录  │    │ → 更新状态      │
              │ → status=frozen   │    │ → status=       │
              └───────────────────┘    │   unfrozen      │
                                       └────────────────┘
```

**详细步骤：**

1. **ARP 数据采集** -- 定时任务通过 SSH 或 API 从交换机获取 ARP 表，解析后写入 `Terminal` 表（`compliance_status=unknown`）
2. **合规判定** -- 合规检查引擎依次执行：
   - 白名单匹配（IP 精确匹配 / CIDR 匹配 / IP 范围匹配 + MAC 精确匹配）→ `bypass`，记录 `wl_match_type`（`mac` / `ip` / `both`）
   - 合规基准匹配（IP + MAC 同时匹配）→ `compliant`
   - 均不匹配 → `non_compliant`
3. **自动封禁** -- `non_compliant` 终端按 `DataSourceBinding` 路由到对应防火墙，调用深信服 API 封禁，创建 `Blacklist` 记录（`is_auto_blocked=True`），终端状态置为 `frozen`
4. **自动解封** -- 已封禁终端若恢复合规或匹配白名单，调用防火墙解封 API，更新 `Blacklist.auto_unblocked=True`，终端状态置为 `unfrozen`

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
┌────────┐    POST /auth/login     ┌──────────────┐
│        │ ──────────────────────→ │  验证码检查   │
│        │                         │ (失败次数≥3)  │
│        │                         └──────┬───────┘
│        │                                │
│  客户端 │                         ┌──────▼───────┐
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
- **角色控制** -- `User.is_superuser` 字段区分超管与普通用户，超管专用端点通过 `get_current_active_superuser` 依赖守卫
- **认证状态恢复** -- 应用启动时前端调用 `initializeAuth()` 恢复认证状态：检查 sessionStorage 中是否存在 token → 调用 `/auth/me` 验证 token 有效性 → token 失效则尝试 refresh → 全部失败则清除会话。恢复期间 `isInitializing` 状态为 `true`，页面显示加载状态，避免未认证闪烁。`initializeAuth` 设置 10 秒超时（timeout: 10000），防止后端不可达时前端请求卡死
- **401 拦截器并发控制** -- 多个请求同时收到 401 时，仅触发一次 token 刷新：通过 `isRefreshing` 标志锁定，后续 401 请求加入 `failedQueue` 队列等待；刷新成功后重试队列中所有请求，刷新失败则统一清除会话并 toast 提示。刷新时 refresh_token 通过 Body 传递（非 Query 参数），使用 `_retry` 标志防止循环重试，React Query 配置 401 状态码不自动重试

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
| 交换机 → ARP 采集服务 | 入站 | SSH (paramiko) / HTTP API (httpx) | 定时采集 ARP 表，支持 Cisco/Huawei/H3C 格式解析 |
| 合规基准 → 合规检查引擎 | 入站 | 数据库直连 (asyncpg) | 定时同步 IP+MAC 基准数据到 Redis 缓存 |
| 白名单 → 合规检查引擎 | 入站 | 内存加载 (Redis 缓存) | 白名单数据加载到内存进行 IP/MAC 匹配 |
| 合规检查引擎 → 深信服防火墙 | 出站 | REST API (httpx) | 封禁/解封 IP 地址 |
| 深信服防火墙 → 合规检查引擎 | 入站 | REST API 响应 | 封禁/解封结果确认 |

---

## 5. 定时任务架构

系统通过 `asyncio.create_task` + `while True` + `asyncio.sleep` 实现 5 个后台定时任务，在 FastAPI lifespan 中启动：

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Lifespan (Startup)                      │
│                                                                     │
│  asyncio.create_task(cleanup_expired_blacklist())     ──→ Task 1   │
│  asyncio.create_task(scheduled_arp_collection())      ──→ Task 2   │
│  asyncio.create_task(scheduled_ipguard_sync())        ──→ Task 3   │
│  asyncio.create_task(scheduled_compliance_check())    ──→ Task 4   │
│  asyncio.create_task(scheduled_auto_unblock())        ──→ Task 5   │
│                                                                     │
│  Shutdown: task.cancel() for all tasks                              │
└─────────────────────────────────────────────────────────────────────┘
```

| 任务 | 配置键 | 默认间隔 | 功能 |
|------|--------|----------|------|
| 过期黑名单清理 | `scheduler_firewall_query_interval` | 300s（DEFAULT_CONFIGS 种子值；代码 fallback 为 3600s） | 清理已过期的 Blacklist 记录 |
| ARP 数据采集 | `scheduler_arp_collection_interval` | 300s | 遍历所有启用的 ARP 数据源，采集并处理 |
| 合规基准数据同步 | `scheduler_ipguard_sync_interval` | 600s | 遍历所有启用的合规基准数据源，同步基准数据到 Redis |
| 合规检查 | `scheduler_compliance_check_interval` | 300s | 遍历所有 ARP 源中 `compliance_status=unknown` 的记录，执行批量合规判定 |
| 自动解封 | `scheduler_auto_unblock_interval` | 600s | 检查已自动封禁的终端，若恢复合规则调用防火墙解封 |

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
| CORS | CORSMiddleware，白名单域名，限制方法和头部 |
| 速率限制 | RateLimitMiddleware，Redis Sorted Set 滑动窗口 |
| 输入验证 | Pydantic Schema 严格校验所有请求体 |
| SQL 注入防护 | SQLAlchemy ORM 参数化查询 |
| 安全响应头 | Nginx 层 X-Frame-Options / X-Content-Type-Options / X-XSS-Protection |
| 生产环境 | 禁用 /docs /redoc /openapi.json |

### 7.6 权限控制

- `User.is_superuser` 字段区分超管与普通用户
- `get_current_active_superuser` 依赖守卫超管专用端点（用户管理、系统配置等）
- `get_current_user` 依赖守卫常规认证端点

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
| 重启策略 | backend 和 nginx 设置 `unless-stopped`，frontend 设置 `"no"`（一次性构建） |

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
| MAC 地址格式无关搜索 | 白名单/黑名单搜索使用 `func.replace` 去除 MAC 地址分隔符（`-`、`:`、`.`）后 `ILIKE` 匹配，用户输入任意格式均可命中 |
| 服务端分页 | 后端根据 `page` + `page_size` 参数执行 `OFFSET/LIMIT` 查询，返回分页元数据 |
| 前端防抖 | 搜索输入使用 debounce（300ms），减少无效请求 |
| 前端 keepPreviousData | React Query 使用 `keepPreviousData: true`（或 `placeholderData: keepPreviousData`），搜索切换时保留上一页数据直到新数据返回，防止页面闪烁 |
| 数据库索引 | 对高频搜索字段（IP、MAC 等）建立索引，加速 ILIKE 前缀匹配查询 |

**MAC 地址格式无关搜索原理：**

```sql
-- 白名单/黑名单搜索时，去除 MAC 地址中的分隔符后进行 ILIKE 匹配
WHERE func.replace(func.replace(func.replace(Whitelist.mac_address, '-', ''), ':', ''), '.', '')
      ILIKE func.replace(func.replace(func.replace('%{search}%', '-', ''), ':', ''), '.', '')
```

用户无论输入 `AA-BB-CC-DD-EE-FF`、`AA:BB:CC:DD:EE:FF`、`AABBCCDDEEFF` 中的哪种格式，均可匹配到目标记录。

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
      │  └─ 白名单/黑名单: MAC 格式无关搜索 (func.replace + ILIKE)
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
| **scheduler** | scheduler_arp_collection_interval, scheduler_ipguard_sync_interval, scheduler_firewall_query_interval, scheduler_compliance_check_interval, scheduler_auto_unblock_interval | 是 |
| **general** | environment, debug, log_level | environment/debug 只读 |
| **branding** | app_name, app_short_name, app_subtitle, login_heading, login_subheading, login_footer_text, login_bg_url, favicon_url, footer_copyright, footer_icp_number, footer_icp_url | 是 |

### 10.3 只读配置

`environment` 和 `debug` 标记为 `is_readonly=True`，不可通过 API 修改，防止运行时变更导致系统行为异常。

### 10.4 配置热加载

- 定时任务每次循环从 `ConfigService` 读取间隔配置，修改后下次循环即生效
- JWT 令牌过期时间从 `ConfigService` 读取，修改后新签发的令牌使用新过期时间
- 速率限制阈值从 `ConfigService` 读取，修改后即时生效
- 登录安全阈值（验证码/锁定）从 `ConfigService` 读取，修改后即时生效

---

## 11. 可扩展性设计

### 11.1 数据源插件化

系统通过 `DataSource.type` 字段支持三种数据源类型，新增类型只需：

1. 在 `DataSourceService.VALID_TYPES` 中注册新类型
2. 实现对应的采集/连接逻辑
3. 在 `test_connection` 中添加新类型的测试方法

当前支持类型：

| 类型 | 说明 | 采集方式 |
|------|------|----------|
| `arp_ssh` | 交换机 SSH 采集 | paramiko SSH 连接，执行命令解析 ARP 表 |
| `arp_api` | 交换机 API 采集 | httpx HTTP 请求，解析 JSON 响应 |
| `sangfor` | 深信服防火墙 | httpx HTTP 请求，REST API 封禁/解封 |

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

### 14.2 8 类分类体系

前端审计日志按 8 个分类进行过滤展示：

| 分类 | 包含的 action | badge 颜色 |
|------|---------------|------------|
| 终端管理 | block_terminal, unblock_terminal | 红色/绿色 |
| 黑名单 | block_blacklist, unblock_blacklist | 红色/绿色 |
| 白名单 | add_whitelist, remove_whitelist | 蓝色/灰色 |
| 认证 | login, logout | 紫色/灰色 |
| 数据源 | create_datasource, update_datasource, delete_datasource, test_datasource, sync_datasource | 青色 |
| 用户管理 | create_user, update_user, delete_user, reset_password, unlock_user | 橙色 |
| 系统配置 | update_config | 黄色 |
| 定时任务 | cleanup_expired | 灰色 |

### 14.3 details JSON 格式存储

审计日志的 `details` 字段统一使用 `json.dumps` 序列化为 JSON 格式存储，每个 dict 包含 `message` 字段：

```json
{"message": "Blocked terminal 192.168.1.100", "ip_address": "192.168.1.100", "mac_address": "AA-BB-CC-DD-EE-FF"}
```

前端审计日志页面解析 `details` 字段时，对 JSON 格式内容进行解析并格式化展示。

### 14.4 log_action 公共函数

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
