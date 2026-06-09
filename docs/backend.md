# TerminalAccessManager 后端实现文档

> 文档版本：v3.0.0 | 更新日期：2026-06-09

## 1. 概述

### 1.1 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 异步高性能，自动 OpenAPI 文档 |
| ORM | SQLAlchemy 2.0 (async) | 异步数据库访问 |
| 数据库 | PostgreSQL | 主数据存储 |
| 缓存 | Redis | 令牌黑名单、限流计数、配置缓存、合规数据缓存 |
| 认证 | JWT (python-jose) | access_token + refresh_token 双令牌机制 |
| 密码哈希 | bcrypt | 自适应哈希，防暴力破解 |

### 1.2 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                          # 应用入口
│   ├── cli.py                           # (不在 app/ 下，见下方)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                    # 配置管理 (Settings)
│   │   ├── database.py                  # 数据库引擎与会话
│   │   ├── security.py                  # 安全模块 (JWT/密码/登录防护)
│   │   ├── crypto.py                    # 字段级加密 (Fernet + ENC: 前缀 + 独立 ENCRYPTION_KEY)
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── rate_limit.py                # 限流中间件
│   │   └── logging.py                   # 请求日志中间件
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                      # 用户模型
│   │   ├── terminal.py                  # 终端模型
│   │   ├── whitelist.py                 # 白名单模型
│   │   ├── blacklist.py                 # 黑名单模型
│   │   ├── log.py                       # 审计日志模型
│   │   ├── system_config.py             # 系统配置模型
│   │   ├── data_source.py              # 数据源模型 + DataSourceBinding
│   │   └── compliance_baseline.py       # 合规基准模型
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py                      # 认证相关 Schema
│   │   ├── terminal.py                  # 终端查询 Schema
│   │   ├── compliance_baseline.py       # 合规基准 Schema
│   │   ├── system_config.py             # 系统配置 Schema
│   │   └── data_source.py              # 数据源 + 合规检查 Schema
│   ├── services/
│   │   ├── __init__.py
│   │   ├── terminal_service.py          # 终端管理服务
│   │   ├── compliance_service.py        # 合规检查服务
│   │   ├── arp_collector_service.py     # ARP 数据采集服务
│   │   ├── config_service.py            # 系统配置服务
│   │   ├── sangfor_service.py           # 深信服防火墙 API 服务
│   │   └── data_source_service.py       # 数据源管理服务
│   └── api/
│       └── v1/
│           ├── __init__.py
│           ├── api.py                   # 路由聚合
│           └── endpoints/
│               ├── __init__.py
│               ├── auth.py              # 认证端点
│               ├── terminals.py         # 终端端点
│               ├── whitelist.py         # 白名单端点
│               ├── blacklist.py         # 黑名单端点
│               ├── logs.py              # 审计日志端点
│               ├── stats.py             # 统计端点
│               ├── settings.py          # 系统配置端点
│               ├── data_sources.py      # 数据源端点
│               └── compliance_baselines.py  # 合规基准端点
├── alembic/                             # 数据库迁移
├── tests/                               # 测试
├── cli.py                               # 统一 CLI 工具
└── requirements.txt
```

---

## 2. 核心模块

### 2.1 应用入口 (main.py)

#### FastAPI 应用配置

```python
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A secure platform for managing network terminals and access control",
    openapi_url=...,   # 生产环境关闭
    docs_url=...,      # 生产环境关闭
    redoc_url=...,     # 生产环境关闭
    lifespan=lifespan,
)
```

- 生产环境 (`ENVIRONMENT=production`) 自动禁用 OpenAPI 文档、Swagger UI 和 ReDoc。
- API 前缀：`/api/v1`。

#### Lifespan 生命周期管理

| 阶段 | 操作 |
|------|------|
| Startup | 初始化数据库 (`init_db`) → 种子默认配置 (`seed_defaults`) → 自动迁移审计日志旧 action 值 → 自动迁移 system_config 旧品牌值 → 启动 5 个后台定时任务 |
| Shutdown | 取消所有后台任务 → 关闭 Redis 连接 (`close_redis_client`) |

#### 启动时自动迁移

应用启动时在 lifespan 中自动执行以下数据迁移，确保旧数据兼容新代码：

**审计日志 action 值迁移：**

| 旧值 | 新值 |
|------|------|
| `block_ip` | `block_terminal` |
| `unblock_ip` | `unblock_terminal` |
| `block` | `block_blacklist` |
| `unblock` | `unblock_blacklist` |

**system_config 品牌值迁移：**

将 `system_config` 表中 `app_name`、`login_heading` 等品牌配置项的旧值 `"Terminal Access Platform"` 替换为 `"Terminal Access Manager"`。

#### 后台定时任务

5 个 `asyncio.create_task` 启动的协程：

| 任务函数 | 说明 |
|----------|------|
| `cleanup_expired_blacklist` | 清理过期黑名单 |
| `scheduled_arp_collection` | 定时采集 ARP 数据 |
| `scheduled_ipguard_sync` | 定时同步 IPGuard 基线数据 |
| `scheduled_compliance_check` | 定时合规检查 |
| `scheduled_auto_unblock` | 定时自动解封 |

#### _get_scheduler_interval 辅助函数

```python
async def _get_scheduler_interval(key: str, default: int) -> int:
```

- 从 `ConfigService` 读取调度间隔配置。
- 钳制范围：**30 ~ 86400 秒**（即最短 30 秒，最长 24 小时）。
- 读取失败时返回 `default` 值。

#### _is_task_paused 辅助函数

```python
async def _is_task_paused(task_name: str) -> bool:
```

- 检查 Redis 键 `scheduler:ctrl:{task_name}` 是否存在且值为 `"paused"`。
- 存在则返回 `True`，表示该任务已暂停。
- 异常时返回 `False`（不阻塞任务执行）。

#### 中间件注册顺序

按 Starlette 中间件洋葱模型，注册顺序（先注册的在外层）：

1. **RateLimitMiddleware** — 限流（最外层，最先拦截）
2. **RequestLoggingMiddleware** — 请求日志
3. **CORSMiddleware** — 跨域

#### CORS 安全校验

当 `allow_origins=["*"]` 时自动降级 `allow_credentials=False`，防止 CORS 规范违规（规范不允许通配符来源与凭证模式同时启用）。

#### 健康检查端点

`GET /health` 返回：

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "environment": "development",
  "db": "ok",
  "redis": "ok"
}
```

- 检测 PostgreSQL 连接（`SELECT 1`）和 Redis 连接（`PING`）。
- 任一依赖异常则 `status` 为 `unhealthy`，HTTP 状态码 503。

#### Prometheus 监控（可选）

- 使用 `prometheus-fastapi-instrumentator`。
- 自动暴露 `/metrics` 端点。
- 未安装时静默跳过。

---

### 2.2 配置管理 (core/config.py)

#### Settings 类

继承 `pydantic_settings.BaseSettings`，从环境变量和 `.env` 文件加载。

| 分类 | 配置项 | 类型 | 默认值 | 说明 |
|------|--------|------|--------|------|
| 应用 | `PROJECT_NAME` | str | `"Terminal Access Manager"` | 项目名称 |
| | `VERSION` | str | `"2.0.0"` | 版本号 |
| | `API_V1_STR` | str | `"/api/v1"` | API 前缀 |
| | `DEBUG` | bool | `False` | 调试模式 |
| | `ENVIRONMENT` | str | `"development"` | 运行环境 |
| 数据库 | `DATABASE_URL` | str | (必填) | 异步数据库连接串 |
| | `DB_HOST` | str | `"localhost"` | 数据库主机 |
| | `DB_PORT` | int | `5432` | 数据库端口 |
| | `DB_USER` | str | `"tam_admin"` | 数据库用户 |
| | `DB_PASSWORD` | str | `""` | 数据库密码 |
| | `DB_NAME` | str | `"tam_db"` | 数据库名 |
| JWT | `SECRET_KEY` | str | (必填) | JWT 签名密钥 |
| | `ALGORITHM` | str | `"HS256"` | JWT 算法 |
| | `ACCESS_TOKEN_EXPIRE_MINUTES` | int | `30` | Access Token 有效期（分钟） |
| | `REFRESH_TOKEN_EXPIRE_DAYS` | int | `7` | Refresh Token 有效期（天） |
| | `ENCRYPTION_KEY` | Optional[str] | `None` | 独立加密密钥，生产环境必须设置且不能与 SECRET_KEY 相同 |
| 深信服 | `SANGFOR_BASE_URL` | Optional[str] | `None` | 深信服 API 地址 |
| | `SANGFOR_USERNAME` | Optional[str] | `None` | 深信服用户名 |
| | `SANGFOR_PASSWORD` | Optional[str] | `None` | 深信服密码 |
| | `SANGFOR_CA_BUNDLE` | Optional[str] | `None` | CA 证书路径 |
| 交换机 | `SWITCH_HOST` | Optional[str] | `None` | 交换机地址 |
| | `SWITCH_USERNAME` | Optional[str] | `None` | 交换机用户名 |
| | `SWITCH_PASSWORD` | Optional[str] | `None` | 交换机密码 |
| | `SWITCH_PORT` | int | `23` | 交换机端口 |
| IPGuard | `IPGUARD_HOST` | Optional[str] | `None` | IPGuard 数据库地址 |
| | `IPGUARD_USER` | Optional[str] | `None` | IPGuard 用户名 |
| | `IPGUARD_PASSWORD` | Optional[str] | `None` | IPGuard 密码 |
| | `IPGUARD_DATABASE` | str | `"OCULAR3"` | IPGuard 数据库名 |
| Redis | `REDIS_URL` | str | `"redis://localhost:6379/0"` | Redis 连接串 |
| | `REDIS_PASSWORD` | Optional[str] | `None` | Redis 密码 |
| CORS | `BACKEND_CORS_ORIGINS` | List[str] | `["http://localhost", ...]` | 允许的跨域来源 |
| 限流 | `RATE_LIMIT_PER_MINUTE` | int | `60` | 通用 API 限流（次/分钟） |
| | `AUTH_RATE_LIMIT_PER_MINUTE` | int | `5` | 认证端点限流（次/分钟） |
| 账户锁定 | `MAX_LOGIN_ATTEMPTS` | int | `5` | 最大登录尝试次数 |
| | `LOCKOUT_DURATION_MINUTES` | int | `15` | 锁定时长（分钟） |
| | `CAPTCHA_THRESHOLD` | int | `3` | 触发验证码的失败次数 |
| 注册 | `ALLOW_REGISTRATION` | bool | `False` | 是否允许公开注册 |
| 日志 | `LOG_LEVEL` | str | `"INFO"` | 日志级别 |

#### 生产环境安全验证

启动时检测 `ENVIRONMENT=production`：

- `SECRET_KEY` 不得为已知不安全默认值（如 `"change-this-to-a-random-secret-key-in-production"` 等），否则进程退出。
- `DEBUG=True` 在生产环境打印警告。

---

### 2.3 数据库 (core/database.py)

#### 异步引擎配置

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,      # 连接池健康检查
    pool_size=10,             # 持久连接数
    max_overflow=20,          # 最大溢出连接数
    pool_recycle=3600,        # 连接回收时间（秒）
)
```

#### 会话工厂

```python
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,   # 提交后对象仍可访问属性
    autocommit=False,
    autoflush=False,
)
async_session_factory = async_session_maker  # 别名，供后台任务使用
```

#### get_db 依赖注入

- 通过 `async with` 管理会话生命周期。
- 正常退出自动 `commit`，异常自动 `rollback`。
- 用作 FastAPI `Depends` 依赖注入。

#### init_db 初始化

- 调用 `Base.metadata.create_all` 创建所有表。
- 额外执行 `ALTER TABLE blacklist ALTER COLUMN ip_address DROP NOT NULL`，使 `ip_address` 可为空（支持仅按 MAC 封锁）。
- 生产环境建议使用 Alembic 迁移。

---

### 2.4 安全模块 (core/security.py)

#### 密码哈希

- 直接使用 `bcrypt` 库（`bcrypt.hashpw` / `bcrypt.checkpw`）。
- `verify_password(plain, hashed)` — 验证明文密码。
- `hash_password(password)` — 哈希密码。

#### JWT 令牌

| 函数 | 说明 |
|------|------|
| `create_access_token_async(data, expires_delta=None, user_id=None)` | 创建 Access Token，payload 包含 `sub`/`exp`/`jti`/`type:"access"`/`ver`(Token 版本号)，有效期从 ConfigService 热加载（`access_token_expire_minutes`） |
| `create_refresh_token_async(data, user_id=None)` | 创建 Refresh Token，payload 包含 `sub`/`exp`/`jti`/`type:"refresh"`/`ver`(Token 版本号)，有效期从 ConfigService 热加载（`refresh_token_expire_days`） |

- 每个令牌携带唯一 `jti`（UUID4），用于黑名单标识。
- 令牌载荷：`sub`（用户名）、`exp`（过期时间）、`jti`（唯一标识）、`type`（令牌类型：`access` 或 `refresh`）、`ver`（创建时的 Token 版本号）。

#### Redis 令牌黑名单

| 函数 | 说明 |
|------|------|
| `add_token_to_blacklist(jti, exp)` | 将令牌加入黑名单，TTL 为令牌剩余有效期 |
| `is_token_blacklisted(jti)` | 检查令牌是否在黑名单中 |

- 键格式：`token_blacklist:{jti}`。

#### 登录安全

| 函数 | 说明 |
|------|------|
| `check_login_attempts(username)` | 检查账户是否被锁定（Redis key `login_lock:{username}`） |
| `check_captcha_required(username)` | 检查是否需要验证码（失败次数 >= `captcha_threshold`） |
| `record_failed_login(username)` | 记录失败登录，达到 `max_login_attempts` 则锁定账户 |
| `reset_login_attempts(username)` | 登录成功后重置失败计数和锁定状态 |

- 阈值从 ConfigService 热加载：`max_login_attempts`、`lockout_duration_minutes`、`captcha_threshold`。
- Redis 键：
  - `login_attempts:{username}` — 失败次数计数器，首次设置 TTL 为 `lockout_duration_minutes * 60`。
  - `login_lock:{username}` — 锁定标记，TTL 为 `lockout_duration_minutes * 60`。

#### 验证码

| 函数 | 说明 |
|------|------|
| `generate_captcha()` | 生成算术验证码，答案存入 Redis（5 分钟 TTL），返回 `(captcha_id, question)` |
| `verify_captcha(captcha_id, answer)` | 校验验证码答案，验证后删除 |

#### Token 版本号

| 函数 | 说明 |
|------|------|
| `get_token_version(user_id)` | 获取用户当前 Token 版本号（Redis key: `token_version:{user_id}`） |
| `increment_token_version(user_id)` | 递增用户 Token 版本号（密码变更时调用） |

#### 鉴权依赖

| 依赖函数 | 说明 |
|----------|------|
| `get_current_user(token, db)` | 从 JWT 解析用户，检查黑名单和活跃状态，返回 `User` 对象 |
| `get_current_active_superuser(current_user)` | 在 `get_current_user` 基础上验证 `is_superuser` |

---

## 3. 中间件

### 3.1 限流中间件 (middleware/rate_limit.py)

#### 算法

Redis Sorted Set 滑动窗口算法：

1. `ZREMRANGEBYSCORE` — 移除窗口外（60 秒前）的记录。
2. `ZADD` — 添加当前请求（score 为时间戳）。
3. `ZCARD` — 统计窗口内请求数。
4. `EXPIRE` — 设置键过期时间（60 秒）。

以上操作通过 Redis Pipeline 原子执行。

#### 限流策略

| 路径模式 | 限流值 | 配置项 |
|----------|--------|--------|
| `/auth/login`, `/auth/register`, `/auth/refresh` | `auth_rate_limit_per_minute` | 认证端点独立限流 |
| 其他 `/api/*` 路径 | `rate_limit_per_minute` | 通用 API 限流 |

- 限流值从 ConfigService 热加载，读取失败回退到 `.env` 默认值。
- 超限时返回 HTTP 429，附带 `Retry-After` 响应头。

#### 跳过规则

- `/health`、`/metrics`、`/` 不限流。
- 非 `/api` 路径不限流。
- Redis 不可用时放行请求（降级策略）。

#### 客户端识别

- 优先读取 `X-Forwarded-For` 头（取第一个 IP）。
- 回退到 `request.client.host`。

---

### 3.2 请求日志中间件 (middleware/logging.py)

- 记录：请求方法、路径、状态码、耗时（毫秒）。
- 响应头：`X-Response-Time: {duration_ms}ms`。
- 排除路径：`/health`、`/metrics`。

---

## 4. 服务层

### 4.1 TerminalService (services/terminal_service.py)

#### IPAddressParser

IP 地址解析工具类，支持以下输入格式：

| 格式 | 示例 | 说明 |
|------|------|------|
| 单 IP | `192.168.1.1` | 直接返回 |
| CIDR | `192.168.1.0/24` | 展开为所有主机 IP |
| IP 范围 | `192.168.1.1-100` | 同 /24 内范围 |
| 带子网 IP 范围 | `192.168.1.1-100/24` | 范围与子网交集 |

- `detect_pattern_type(ip_input)` — 检测输入类型（`single_ip` / `cidr` / `ip_range`）。
- `validate_ip(ip)` — 验证单个 IP 地址合法性。

#### 搜索与分页

4个搜索方法均返回 `PaginatedResponse`（含 `items`、`total`、`skip`、`limit`），支持服务端分页。

| 方法 | 说明 |
|------|------|
| `search_terminals(ip, mac, compliance_status, status, start_date, end_date, skip, limit)` | 搜索终端，IP/MAC 使用 ILIKE 模糊搜索 + OR 逻辑（任一匹配即可），支持 `compliance_status` 过滤 |
| `get_whitelist(query, start_date, end_date, skip, limit)` | 查询白名单，支持搜索（MAC/IP/备注）和日期范围。MAC 搜索使用格式无关匹配（`func.replace` 去除分隔符后 ILIKE） |
| `get_blacklist(query, start_date, end_date, skip, limit)` | 查询黑名单，支持搜索和日期范围。MAC 搜索使用格式无关匹配（`func.replace` 去除分隔符后 ILIKE） |
| `search_audit_logs(username, action, search, start_date, end_date, skip, limit)` | 搜索审计日志，支持用户名、操作类型、关键词、日期范围 |

**PaginatedResponse 结构：**

```python
class PaginatedResponse(Generic[T]):
    items: List[T]    # 当前页数据
    total: int        # 总记录数
    skip: int         # 跳过记录数
    limit: int        # 每页记录数
```

**Terminals 搜索逻辑：**

- `ip` 参数：`Terminal.ip_address ILIKE '%{ip}%'`
- `mac` 参数：`Terminal.mac_address ILIKE '%{mac}%'`
- IP 和 MAC 同时提供时使用 OR 逻辑（任一匹配即返回）
- `compliance_status` 参数：精确匹配过滤（compliant/bypass/non_compliant/unknown）

**LIKE 通配符注入防护：**

- `_escape_like(value)` — 转义 LIKE 通配符 `%` 和 `_`，防止通配符注入，21 处 ilike 查询统一使用

**Whitelist/Blacklist MAC 格式无关搜索逻辑：**

白名单和黑名单的搜索使用 `func.replace` 去除 MAC 地址分隔符后进行 ILIKE 匹配，用户无论输入哪种 MAC 格式均可命中：

```python
# 去除 MAC 地址中的分隔符（-、:、.）后进行 ILIKE 匹配
mac_clean = func.replace(
    func.replace(func.replace(model.mac_address, '-', ''), ':', ''), '.', ''
)
search_clean = search.replace('-', '').replace(':', '').replace('.', '')
mac_clean.ilike(f'%{search_clean}%')
```

#### Count 方法

4个 count 方法用于获取符合条件的总记录数，供分页计算使用：

| 方法 | 说明 |
|------|------|
| `count_terminals(ip, mac, compliance_status, status, start_date, end_date)` | 统计终端搜索结果总数 |
| `count_whitelist(query, start_date, end_date)` | 统计白名单搜索结果总数 |
| `count_blacklist(query, start_date, end_date)` | 统计黑名单搜索结果总数 |
| `count_audit_logs(username, action, search, start_date, end_date)` | 统计审计日志搜索结果总数 |

#### get_stats

仪表盘统计，按 `compliance_status` 和 `status` 分组计数：

- 仅统计 `source='arp'` 的终端。
- 返回：`total`、`whitelisted`、`blocked`、`active`、`inactive`、`pending`、`compliant`、`bypass`、`non_compliant`、`unknown`。

#### get_system_status

系统状态检查，包括深信服 AF 连通性检测。

#### block_ip / unblock_ip

封锁/解封操作：

- `block_ip(ip_address, mac_address, username, block_time, firewall_tag)`：
  - 通过 `firewall_tag` 查找对应的 `DataSource`（type=sangfor）获取防火墙服务实例。
  - 调用深信服 API 封锁 IP。
  - 更新 `Terminal.status` 为 `frozen`，`compliance_status` 为 `non_compliant`。
  - 创建 `Blacklist` 记录（`source_tag="manual"`，`is_auto_blocked=False`）。
  - 记录审计日志。

- `unblock_ip(ip_address, username, firewall_tag)`：
  - 调用深信服 API 解封 IP。
  - 恢复 `Terminal.status` 为 `unfrozen`，`compliance_status` 为 `unknown`。
  - 删除对应 `Blacklist` 记录。
  - 记录审计日志。

- 防火墙未配置时跳过 API 调用，视为成功。

#### 白名单 CRUD

| 方法 | 说明 |
|------|------|
| `get_whitelist(query, start_date, end_date, skip, limit)` | 查询白名单，返回 `PaginatedResponse`，支持搜索（MAC/IP/备注）和日期范围 |
| `add_to_whitelist(mac_address, ip_address, comments, username)` | 添加白名单，存储原始 pattern（不展开 CIDR），自动失效白名单缓存 |
| `delete_from_whitelist(identifier, username)` | 删除白名单，自动识别 MAC 或 IP，失效缓存 |

- `add_to_whitelist` 存储原始 `ip_pattern` 和 `pattern_type`（`single_ip` / `cidr` / `ip_range` / `mac_only`），不展开 CIDR。
- 白名单添加后，若该 MAC 存在于 `terminals` 表则删除。
- 白名单变更后调用 `ComplianceService.invalidate_whitelist_cache()` 失效 Redis 缓存。

#### 黑名单 CRUD

| 方法 | 说明 |
|------|------|
| `get_blacklist(query, start_date, end_date, skip, limit)` | 查询黑名单，返回 `PaginatedResponse`，支持搜索和日期范围 |
| `add_to_blacklist(ip_address, mac_address, reason, username, block_time, firewall_tag)` | 添加黑名单并调用防火墙 API |
| `delete_from_blacklist(identifier, username)` | 删除黑名单并调用防火墙 API 解封 |
| `cleanup_expired_blacklist()` | 清理过期黑名单，恢复 MAC 状态，调用防火墙解封 |

#### 审计日志

| 方法 | 说明 |
|------|------|
| `search_audit_logs(username, action, search, start_date, end_date, skip, limit)` | 搜索审计日志，返回 `PaginatedResponse`，支持用户名、操作类型、关键词、日期范围 |
| `log_action(db, username, action, resource_type, resource_id, details, ip_address)` | 公共审计日志写入函数，`details` 接收 dict 并使用 `json.dumps(details, ensure_ascii=False)` 序列化，`ip_address` 参数记录操作来源 IP |

**action 命名变更对照表：**

| 旧 action 值 | 新 action 值 | 说明 |
|---|---|---|
| `block_ip` | `block_terminal` | 封禁终端（从终端管理页面操作） |
| `unblock_ip` | `unblock_terminal` | 解封终端（从终端管理页面操作） |
| `block` | `block_blacklist` | 加入黑名单 |
| `unblock` | `unblock_blacklist` | 移出黑名单 |

**完整 action 值列表：**

| action 值 | 说明 | 触发位置 |
|---|---|---|
| `block_terminal` | 封禁终端 | terminals.py |
| `unblock_terminal` | 解封终端 | terminals.py |
| `block_blacklist` | 加入黑名单 | blacklist.py |
| `unblock_blacklist` | 移出黑名单 | blacklist.py |
| `add_whitelist` | 添加白名单 | whitelist.py |
| `remove_whitelist` | 移除白名单 | whitelist.py |
| `cleanup_expired` | 清理过期黑名单 | 定时任务 |
| `login` | 用户登录 | auth.py |
| `logout` | 用户登出 | auth.py |
| `create_datasource` | 创建数据源 | data_sources.py |
| `update_datasource` | 更新数据源 | data_sources.py |
| `delete_datasource` | 删除数据源 | data_sources.py |
| `test_datasource` | 测试数据源连接 | data_sources.py |
| `sync_datasource` | 同步数据源 | data_sources.py |
| `create_user` | 创建用户 | users.py |
| `update_user` | 更新用户 | users.py |
| `delete_user` | 删除用户 | users.py |
| `reset_password` | 重置密码 | users.py |
| `unlock_user` | 解锁用户 | users.py |
| `update_config` | 更新系统配置 | settings.py |

#### MAC 地址标准化

格式：**XX-XX-XX-XX-XX-XX**（大写，短横线分隔）。

```python
@staticmethod
def _normalize_mac(mac: str) -> str:
    mac_clean = mac.replace('-', '').replace(':', '').replace('.', '').upper()
    formatted = '-'.join(mac_clean[i:i+2] for i in range(0, len(mac_clean), 2))
    return formatted
```

---

### 4.2 ComplianceService (services/compliance_service.py)

#### 合规检查逻辑

**单条检查 `check_compliance(ip_address, mac_address)`**：

```
1. 白名单匹配 → compliance_status = "bypass"
2. 合规基准匹配 → compliance_status = "compliant"
3. 都不匹配 → compliance_status = "non_compliant"
```

**批量检查 `batch_check_compliance(entries)`**：

- 一次性加载全部白名单和合规基准数据到内存，避免逐条查询。
- 返回 `ComplianceCheckResult`：`total_checked`、`compliant`、`bypass`、`non_compliant`、`details`。
- `details` 仅在条目数 <= 1000 时返回。

#### 白名单匹配规则

`_match_whitelist_in_memory(whitelist_data, ip_address, mac_address)` 返回匹配类型：

| 匹配类型 | 返回值 | 条件 |
|----------|--------|------|
| MAC 精确匹配 | `"mac"` | 白名单条目 MAC 与目标 MAC 一致 |
| IP 精确匹配 | `"ip"` | 白名单条目 IP 与目标 IP 一致（single_ip） |
| CIDR 子网匹配 | `"ip"` | 目标 IP 属于白名单 CIDR 网络 |
| IP 范围匹配 | `"ip"` | 目标 IP 在白名单 IP 范围内 |
| MAC + IP 同时匹配 | `"both"` | MAC 和 IP 都匹配 |
| 无匹配 | `None` | — |

- `mac_only` 类型条目仅按 MAC 匹配。
- 同时指定 MAC 和 IP 的白名单条目要求两者都匹配才返回 `"both"`。

#### 合规基准数据同步

`sync_compliance_baseline_data(source_tag)`：

- 从 `ComplianceBaseline` 表查找合规基准数据。
- 使用 `asyncpg` 直连外部数据库，查询终端信息。
- 结果缓存到 Redis，键 `compliance_baseline:{source_tag}`，TTL 10 分钟。
- 更新 `DataSource.last_sync_status`。

#### 自动封锁

`auto_block_non_compliant(arp_source_tag, block_time, dry_run)`：

1. 查找该 ARP 来源下 `compliance_status=non_compliant` 且未封锁的终端。
2. 排除已在黑名单中的 IP。
3. 通过 `DataSourceBinding` 查找关联的防火墙标签。
4. 对每个关联防火墙调用封锁 API。
5. 创建 `Blacklist` 记录（`is_auto_blocked=True`），每个防火墙一条。
6. 支持 `dry_run` 模式（仅模拟，不实际封锁）。

#### 自动解封

`auto_unblock_compliant()`：

1. 查找 `is_auto_blocked=True` 且 `auto_unblocked=False` 的黑名单条目。
2. 检查该 IP+MAC 是否已合规（白名单或合规基准匹配）。
3. 合规则调用防火墙解封 API，标记 `auto_unblocked=True`。
4. 白名单匹配的终端 `compliance_status` 设为 `bypass`，合规基准匹配的设为 `compliant`。

#### 缓存策略

| 缓存 | Redis 键 | TTL |
|------|----------|-----|
| 白名单 | `whitelist:all` | 5 分钟 |
| 合规基准数据 | `compliance_baseline:{source_tag}` | 10 分钟 |

- 白名单变更时主动失效缓存（`invalidate_whitelist_cache`）。
- 合规基准数据由定时同步任务刷新。

---

### 4.3 ArpCollectorService (services/arp_collector_service.py)

#### SSH 采集

`collect_from_ssh(source)`：

- 使用 `paramiko` 连接交换机。
- 执行配置的命令（默认 `show arp`）。
- 超时 30 秒。
- 解析输出后调用 `process_arp_entries` 处理。

#### API 采集

`collect_from_api(source)`：

- 使用 `httpx.AsyncClient` 发送 HTTP 请求。
- 支持 GET/POST 方法。
- 支持 Bearer Token 认证。
- 超时 30 秒。
- 解析 JSON 响应后调用 `process_arp_entries` 处理。

#### ARP 条目处理

`process_arp_entries(entries, source_tag)`：

1. **Upsert**：按 IP+MAC 查找，存在则更新时间戳和来源，不存在则新建（`compliance_status="unknown"`）。
2. **批量合规检查**：对 `compliance_status="unknown"` 的条目执行 `batch_check_compliance`。
3. **更新合规状态**：根据检查结果更新 `compliance_status` 和 `wl_match_type`。
4. **触发自动封锁**：若存在 `non_compliant` 条目，异步触发 `auto_block_non_compliant`（fire-and-forget）。

#### ARP 输出解析

`_parse_arp_output(output, source_type)` 支持三种格式：

| 格式 | 正则模式 | MAC 格式转换 |
|------|----------|-------------|
| Cisco | `Internet  192.168.1.1   2   aa11.bb22.cc33  ARPA  Vlan10` | `aa11.bb22.cc33` → `AA-11-BB-22-CC-33` |
| 华为/H3C | `192.168.1.1  aa11-bb22-cc33  I  Vlanif10` | `aa11-bb22-cc33` → `AA-11-BB-22-CC-33` |
| 通用 | `192.168.1.1  aa:11:bb:22:cc:33` | `aa:11:bb:22:cc:33` → `AA-11-BB-22-CC-33` |

#### API 响应解析

`_parse_api_response(data)` 支持多种结构：

- 直接列表：`[{ip, mac}, ...]`
- 包装结构：`{data/entries/results: [{...}, ...]}`
- 字段名兼容：`ip_address` / `ip` / `ipAddress`，`mac_address` / `mac` / `macAddress`

#### 定时采集

`run_scheduled_collection()`：

- 查找所有启用的 ARP 数据源（`arp_ssh` + `arp_api`）。
- 依次执行采集（SSH 或 API）。

---

### 4.4 ConfigService (services/config_service.py)

#### DEFAULT_CONFIGS

6 个分类的默认配置，首次启动时种子到数据库：

**security（安全）**

| 键 | 默认值 | 类型 | 说明 |
|----|--------|------|------|
| `max_login_attempts` | `5` | int | 最大登录失败次数 |
| `lockout_duration_minutes` | `15` | int | 账户锁定时长（分钟） |
| `captcha_threshold` | `3` | int | 触发验证码的失败次数 |
| `allow_registration` | `false` | bool | 允许公开注册 |
| `access_token_expire_minutes` | `30` | int | Access Token 有效期（分钟） |
| `refresh_token_expire_days` | `7` | int | Refresh Token 有效期（天） |

**rate_limit（限流）**

| 键 | 默认值 | 类型 | 说明 |
|----|--------|------|------|
| `rate_limit_per_minute` | `60` | int | 通用 API 限流（次/分钟） |
| `auth_rate_limit_per_minute` | `5` | int | 认证端点限流（次/分钟） |

**network（网络）**

| 键 | 默认值 | 类型 | 说明 |
|----|--------|------|------|
| `sangfor_enabled` | `false` | bool | 启用深信服防火墙集成 |
| `sangfor_base_url` | `""` | string | 深信服 API 地址 |
| `switch_enabled` | `false` | bool | 启用交换机集成 |
| `switch_host` | `""` | string | 交换机地址 |
| `ipguard_enabled` | `false` | bool | 启用 IPGuard 集成 |
| `ipguard_host` | `""` | string | IPGuard 数据库地址 |

**scheduler（调度）**

| 键 | 默认值 | 类型 | 说明 |
|----|--------|------|------|
| `scheduler_arp_collection_interval` | `300` | int | ARP 采集间隔（秒） |
| `scheduler_ipguard_sync_interval` | `600` | int | IPGuard 同步间隔（秒） |
| `scheduler_firewall_query_interval` | `300` | int | 黑名单清理间隔（秒）（种子值 300，main.py fallback 为 3600） |
| `scheduler_compliance_check_interval` | `300` | int | 合规检查间隔（秒） |
| `scheduler_auto_unblock_interval` | `600` | int | 自动解封间隔（秒） |

**general（通用）**

| 键 | 默认值 | 类型 | 只读 | 说明 |
|----|--------|------|------|------|
| `environment` | `"development"` | string | 是 | 运行环境 |
| `debug` | `"false"` | bool | 是 | 调试模式 |
| `log_level` | `"INFO"` | string | 否 | 日志级别 |

**branding（品牌定制）**

| 键 | 默认值 | 类型 | 说明 |
|----|--------|------|------|
| `app_name` | `"Terminal Access Manager"` | string | 应用显示名称 |
| `app_short_name` | `"Terminal Access"` | string | 侧边栏短名称 |
| `app_subtitle` | `"Manager"` | string | 侧边栏副标题 |
| `login_heading` | `"Terminal Access Manager"` | string | 登录页标题 |
| `login_subheading` | `"Sign in to your account"` | string | 登录页副标题 |
| `login_footer_text` | `"Secure authentication · Session-based access control"` | string | 登录页页脚 |
| `login_bg_url` | `""` | string | 登录页背景图 URL |
| `favicon_url` | `""` | string | 自定义 Favicon URL |
| `footer_copyright` | `"© {year} TerminalAccessManager (TAM)"` | string | 页脚版权（`{year}` 动态替换） |
| `footer_icp_number` | `""` | string | ICP 备案号 |
| `footer_icp_url` | `"https://beian.miit.gov.cn/"` | string | ICP 备案链接 |

#### 核心方法

| 方法 | 说明 |
|------|------|
| `seed_defaults()` | 种子默认配置（幂等），已有键跳过，.env 有值则优先使用 |
| `get(key)` | 获取配置值：Redis 缓存 → 数据库 → .env 回退 |
| `get_typed(key, default)` | 获取类型化配置值（根据 `value_type` 自动解析） |
| `get_value(key)` | 直接从数据库查询值（快捷方法） |
| `set(key, value, updated_by)` | 设置配置：验证 → 持久化 → 失效缓存 |
| `batch_update(updates, updated_by)` | 批量更新（全部验证通过才执行，否则全部回滚） |
| `get_all_grouped()` | 按分类分组获取全部配置（带类型化值） |

#### 缓存策略

- Redis 缓存键：`sys_config:{key}`，TTL 5 分钟。
- 写穿透：更新配置时立即删除缓存（`_invalidate_cache`）。
- 读取链路：Redis → 数据库 → .env 默认值。

#### 模块级便捷函数

`get_config_value(key, default)` — 无需 DB 会话，直接从 Redis 缓存或 .env 读取配置值。供中间件和安全模块等无 DB 会话场景使用。

---

## 5. 定时任务

| # | 函数名 | 配置项 | 默认间隔 | Fallback | 业务逻辑 |
|---|--------|--------|----------|----------|----------|
| 1 | `cleanup_expired_blacklist` | `scheduler_firewall_query_interval` | 300s | 3600（代码 fallback，DEFAULT_CONFIGS 种子值为 300） | 查找 `expires_at < now` 的黑名单条目，恢复 MAC 状态为 `unfrozen`，调用防火墙解封 API，删除黑名单记录，记录审计日志 |
| 2 | `scheduled_arp_collection` | `scheduler_arp_collection_interval` | 300s | 300s | 查找所有启用的 ARP 数据源（`arp_ssh` + `arp_api`），依次执行 SSH/API 采集 |
| 3 | `scheduled_ipguard_sync` | `scheduler_ipguard_sync_interval` | 600s | 600s | 查找所有启用的合规基准数据源，逐个调用 `sync_compliance_baseline_data` 同步基线数据到 Redis |
| 4 | `scheduled_compliance_check` | `scheduler_compliance_check_interval` | 300s | 300s | 查找所有启用的 ARP 数据源，对每个来源下 `compliance_status="unknown"` 的条目执行批量合规检查，更新合规状态 |
| 5 | `scheduled_auto_unblock` | `scheduler_auto_unblock_interval` | 600s | 600s | 调用 `auto_unblock_compliant`，对已合规的自动封锁终端执行解封 |

所有任务共同特征：

- 每轮循环开始时从 ConfigService 读取间隔，钳制 30~86400 秒。
- 使用 `asyncio.sleep(interval)` 控制间隔。
- 每轮循环在 `await asyncio.sleep(interval)` 之后调用 `_is_task_paused(task_name)` 检查 Redis 暂停键，若已暂停则 `continue` 跳过当轮执行。
- `_auto_block_task` 改用 `async_session_factory()` 创建独立数据库会话，含 commit/rollback。
- 异常时记录日志并继续下一轮循环。
- 应用关闭时通过 `task.cancel()` 取消。

---

## 6. CLI (cli.py)

统一命令行管理工具，位于 `backend/cli.py`。

### 子命令

| 命令 | 说明 |
|------|------|
| `python cli.py setup` | 初始化数据库 + 创建 admin 用户（admin/Admin123） |
| `python cli.py mock generate` | 生成 Demo 数据 |
| `python cli.py mock clear` | 清除所有 Demo 数据（需输入 `DELETE` 确认，保留 admin 用户和系统配置） |
| `python cli.py validate` | 运行后端验证检查 |
| `python cli.py test [args]` | 运行 pytest 测试套件 |

### Demo 数据生成详情

`mock generate` 创建以下数据：

| 数据类型 | 数量 | 说明 |
|----------|------|------|
| 数据源 | 6 | 2 个 ARP SSH、1 个 ARP API、2 个深信服防火墙、1 个合规基准 |
| 数据源绑定 | 3 | ARP 来源与防火墙的关联 |
| 用户 | 5 | admin / john.doe / jane.smith / network.admin / security.officer |
| 终端 | 50 | 随机生成，含多种合规状态 |
| 白名单 | ~15 | 含 single_ip、CIDR、IP 范围三种模式 |
| 黑名单 | ~10 | 含手动和自动封锁 |
| 审计日志 | 100 | 随机操作记录 |

### 验证检查详情

`validate` 检查 8 个维度：

1. 文件结构 — 必要文件是否存在
2. Python 语法 — 编译检查
3. 关键导入 — 依赖安装状态
4. 配置 — `.env.example` 和关键环境变量
5. 代码质量 — 类型提示、文档字符串、异步模式
6. 安全 — 硬编码密码检测、bcrypt 直接调用和 JWT 实现
7. API 端点 — 关键端点关键词检测
8. Docker — Dockerfile、健康检查、非 root 用户

### firewall_query 任务修复

`firewall_query` 任务已改用 `TerminalService._get_sangfor_service_by_tag()` 获取防火墙服务实例，再调用 `SangforService.get_blocked_ips()` 查询黑名单。原调用不存在的 `query_firewall_blacklist` 方法已修复。

---

## 7. API 端点审计记录

各端点模块在执行关键操作时通过 `log_action` 公共函数记录审计日志，包含操作来源 IP 地址。

### 7.1 认证端点 (auth.py)

| 端点 | 审计 action | 说明 |
|------|-------------|------|
| `POST /auth/login` | `login` | 用户登录成功时记录，details 包含登录用户名 |
| `POST /auth/logout` | `logout` | 用户登出时记录，details 包含登出用户名 |

**认证端点参数变更：**

| 端点 | 变更 | 说明 |
|------|------|------|
| `POST /auth/refresh` | `refresh_token` 参数从 Query 改为 Body | 原先 refresh_token 通过 URL Query 参数传递，存在安全风险（日志泄露、浏览器历史记录），现改为通过请求 Body 传递 |

### 7.2 数据源端点 (data_sources.py)

| 端点 | 审计 action | 说明 |
|------|-------------|------|
| `POST /data-sources/` | `create_datasource` | 创建数据源 |
| `PUT /data-sources/{id}` | `update_datasource` | 更新数据源 |
| `DELETE /data-sources/{id}` | `delete_datasource` | 删除数据源 |
| `POST /data-sources/{id}/test` | `test_datasource` | 测试数据源连接 |
| `POST /data-sources/{id}/sync` | `sync_datasource` | 同步数据源 |

### 7.3 用户管理端点 (users.py)

| 端点 | 审计 action | 说明 |
|------|-------------|------|
| `POST /users/` | `create_user` | 创建用户 |
| `PUT /users/{id}` | `update_user` | 更新用户 |
| `DELETE /users/{id}` | `delete_user` | 删除用户 |
| `POST /users/{id}/reset-password` | `reset_password` | 重置用户密码 |
| `POST /users/{id}/unlock` | `unlock_user` | 解锁用户账户 |

### 7.4 系统配置端点 (settings.py)

| 端点 | 审计 action | 说明 |
|------|-------------|------|
| `PUT /settings/` | `update_config` | 更新系统配置 |
