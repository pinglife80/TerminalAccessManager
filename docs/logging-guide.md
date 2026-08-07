# TerminalAccessManager 日志说明文档

> 文档版本：v3.9.0  更新日期：2026-08-05
> **适用范围**：后端应用日志、前端运行时日志、审计日志、Docker 容器日志、Nginx 日志、PostgreSQL 日志、运维脚本日志

---

## 目录

1. [日志体系架构](#1-日志体系架构)
2. [后端应用日志](#2-后端应用日志)
   - 2.1 [日志库与配置](#21-日志库与配置)
   - 2.2 [日志格式说明](#22-日志格式说明)
   - 2.3 [日志级别规范](#23-日志级别规范)
   - 2.4 [日志输出目标](#24-日志输出目标)
   - 2.5 [日志轮转与保留](#25-日志轮转与保留)
   - 2.6 [各业务模块日志详解](#26-各业务模块日志详解)
   - 2.7 [Request-ID 链路追踪](#27-request-id-链路追踪)
3. [前端运行时日志](#3-前端运行时日志)
   - 3.1 [日志工具](#31-日志工具)
   - 3.2 [日志格式说明](#32-日志格式说明)
   - 3.3 [日志级别与输出策略](#33-日志级别与输出策略)
   - 3.4 [本地存储与导出](#34-本地存储与导出)
   - 3.5 [全局错误监听](#35-全局错误监听)
4. [审计日志](#4-审计日志)
   - 4.1 [审计日志架构](#41-审计日志架构)
   - 4.2 [审计操作类型清单](#42-审计操作类型清单)
   - 4.3 [审计日志字段说明](#43-审计日志字段说明)
   - 4.4 [审计日志查询与导出](#44-审计日志查询与导出)
   - 4.5 [审计日志归档与清理](#45-审计日志归档与清理)
5. [Docker 容器日志](#5-docker-容器日志)
   - 5.1 [日志驱动与限制](#51-日志驱动与限制)
   - 5.2 [各服务日志配置](#52-各服务日志配置)
   - 5.3 [容器日志查看](#53-容器日志查看)
6. [Nginx 日志](#6-nginx-日志)
7. [PostgreSQL 日志](#7-postgresql-日志)
8. [运维脚本日志](#8-运维脚本日志)
   - 8.1 [脚本日志函数](#81-脚本日志函数)
   - 8.2 [日志运维命令](#82-日志运维命令)
9. [日志管理运维手册](#9-日志管理运维手册)
   - 9.1 [日常日志查看](#91-日常日志查看)
   - 9.2 [日志归档操作](#92-日志归档操作)
   - 9.3 [日志清理操作](#93-日志清理操作)
   - 9.4 [故障排查指南](#94-故障排查指南)
10. [日志安全与合规](#10-日志安全与合规)
11. [文档版本历史](#11-文档版本历史)
12. [日志监控与告警](#12-日志监控与告警)
13. [紧急处理流程](#13-紧急处理流程)
14. [性能影响说明](#14-性能影响说明)
15. [日志分析常用命令](#15-日志分析常用命令)
16. [日志配置变更指南](#16-日志配置变更指南)

---

## 1. 日志体系架构

TAM 系统采用多层日志架构，覆盖从基础设施到业务逻辑的完整日志链路：

```
┌─────────────────────────────────────────────────────────────────┐
│                        日志采集与查看                             │
│  docker logs / manage.sh logs / 浏览器 DevTools / 审计日志页面    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                     日志输出目标                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  stdout   │  │ 文件输出  │  │ 数据库   │  │  localStorage    │ │
│  │(Docker   │  │/var/log/ │  │audit_logs│  │ (前端warn/error) │ │
│  │  logs)   │  │ tam/     │  │  表      │  │                  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└───────────────────────────┼─────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                     日志生产层                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │  后端     │  │  前端    │  │  Nginx   │  │  PostgreSQL      │ │
│  │  loguru  │  │ logger.ts│  │ access/  │  │  slow_query/     │ │
│  │          │  │          │  │ error_log│  │  connections     │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 日志类型总览

| 日志类型 | 存储位置 | 保留策略 | 用途 |
|---------|---------|---------|------|
| 后端应用日志 | stdout + /var/log/tam/app.log | 30天轮转 / 10MB分割 | 应用运行状态、错误排查 |
| 前端运行时日志 | 浏览器 console + localStorage | 会话级 / 50条 | 前端错误捕获、用户端排查 |
| 审计日志 | PostgreSQL audit_logs 表 | 手动归档清理 | 安全审计、操作追溯 |
| Docker 容器日志 | /var/lib/docker/containers/ | json-file 限制 | 容器级日志查看 |
| Nginx 访问日志 | stdout | Docker 日志限制 | HTTP 请求记录 |
| PostgreSQL 日志 | stdout | Docker 日志限制 | 慢查询、连接记录 |

---

## 2. 后端应用日志

### 2.1 日志库与配置

**核心日志库**：loguru（统一管理所有后端日志输出）

**配置文件**：`backend/app/core/logging_config.py`

**初始化入口**：`backend/app/main.py` → `setup_logging()`

**标准库拦截**：通过 `InterceptHandler` 将 `logging.getLogger(__name__)` 调用统一转发到 loguru，确保所有模块日志格式一致。

**环境变量**：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志输出级别 |
| `DEBUG` | `false` | 调试模式（启用 diagnose 详细异常信息） |
| `TZ` | `Asia/Shanghai` | 系统时区，影响日志时间戳和数据库时间 |

**时区控制机制**：

| 层级 | 配置方式 | 影响范围 |
|------|---------|---------|
| Docker 容器 | `docker-compose.yml` 中 `TZ: ${TZ:-Asia/Shanghai}` | 所有容器系统时间 |
| 后端应用 | `config.py` → `TZ` 配置项 → `setup_logging()` 调用 `time.tzset()` | loguru 日志 `ZZ` 时区偏移 |
| PostgreSQL | `docker-compose.yml` 中 `log_timezone` / `timezone` 参数 | 数据库日志和查询时间 |
| 前端浏览器 | `logger.ts` 使用 `new Date()` 本地时区 | 前端日志时间戳 |

修改时区只需在 `.env` 中设置 `TZ=Asia/Shanghai`（或其他 IANA 时区），然后重启所有服务即可全局生效。

**第三方库日志降噪**：以下库的日志级别自动设为 WARNING，避免噪音：

- `uvicorn.access` / `uvicorn.error`
- `sqlalchemy.engine`
- `asyncio`
- `httpx` / `httpcore`

### 2.2 日志格式说明

**标准输出格式**：

```
2026-06-09 14:30:00.123 +08:00 | INFO     | a1b2c3d4e5f6 | app.core.security:verify_token:45 - Token validated successfully
```

**格式拆解**：

| 字段 | 格式 | 示例 | 说明 |
|------|------|------|------|
| 时间戳 | `YYYY-MM-DD HH:mm:ss.SSS ZZ` | `2026-06-09 14:30:00.123 +08:00` | 带毫秒和时区 |
| 级别 | 左对齐8字符 | `INFO    ` | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| Request-ID | 12位hex 或 `-` | `a1b2c3d4e5f6` | 请求链路追踪ID，非请求上下文显示 `-` |
| 位置 | `模块:函数:行号` | `app.core.security:verify_token:45` | 精确到代码行 |
| 消息 | 自由文本 | `Token validated successfully` | 日志内容 |

**请求日志格式**（由 RequestLoggingMiddleware 产生）：

```
2026-06-09 14:30:00.123 +08:00 | INFO     | a1b2c3d4e5f6 | app.middleware.logging:dispatch:34 - GET /api/v1/terminals - 200 - 45.23ms | ip=192.168.1.100 | req_id=a1b2c3d4e5f6
```

| 字段 | 说明 |
|------|------|
| `GET` | HTTP 方法 |
| `/api/v1/terminals` | 请求路径 |
| `200` | HTTP 状态码 |
| `45.23ms` | 响应时间 |
| `ip=192.168.1.100` | 客户端 IP（优先取 X-Forwarded-For） |
| `req_id=a1b2c3d4e5f6` | Request-ID，与格式字段中的 request_id 一致 |

**未捕获异常日志格式**（由 error_handler.py 产生）：

```
2026-06-09 14:30:00.123 +08:00 | ERROR    | a1b2c3d4e5f6 | app.middleware.error_handler:unhandled_exception_handler:43 - Unhandled exception [f7e8d9c0]: RuntimeError: Connection pool exhausted | POST /api/v1/terminals
```

| 字段 | 说明 |
|------|------|
| `a1b2c3d4e5f6` | request_id（格式字段），标识该请求的所有日志行 |
| `[f7e8d9c0]` | error_id（消息内容），标识该请求中的具体异常 |
| `RuntimeError` | 异常类型 |
| `Connection pool exhausted` | 异常消息 |
| `POST /api/v1/terminals` | 请求方法和路径 |

### 2.3 日志级别规范

| 级别 | 使用场景 | 生产环境输出 | 数量 |
|------|---------|:----------:|:----:|
| **DEBUG** | 调试信息：函数参数、中间状态、Redis 操作详情 | 否（LOG_LEVEL=INFO） | 1 |
| **INFO** | 正常业务流程：操作成功、定时任务执行、服务启动 | 是 | 39 |
| **WARNING** | 降级/容错：Redis 不可用 fail-open、API 调用失败、配置不安全 | 是 | 25 |
| **ERROR** | 操作失败：异常捕获、API 错误、定时任务失败 | 是 | 35 |
| **CRITICAL** | 系统级故障：数据库连接失败、密钥缺失（预留） | 是 | 0 |

**级别选择原则**：

- `DEBUG`：仅开发调试时需要的信息，生产环境不输出
- `INFO`：确认事情按预期工作（"做了什么"）
- `WARNING`：事情未按预期但系统可继续运行（"降级了什么"）
- `ERROR`：操作失败需要关注但不影响系统运行（"什么失败了"）
- `CRITICAL`：系统无法继续运行（"什么崩溃了"）

**日志消息规范**：

| 规范 | 正确示例 | 错误示例 |
|------|---------|---------|
| ERROR 必须含异常类型 | `ConnectionError: {e}` | `{str(e)}` |
| 定时任务日志含来源标记 | `[source=scheduler]` | 无标记 |
| 降级日志含策略说明 | `Redis unavailable, allowing token (fail-open)` | `Redis error` |
| 操作日志含操作对象 | `Cleaned up {count} expired blacklist entries` | `Cleanup done` |

### 2.4 日志输出目标

| 输出目标 | 路径 | 启用条件 | 说明 |
|---------|------|---------|------|
| **stdout** | 标准输出 | 始终启用 | Docker 容器日志采集源 |
| **文件** | `/var/log/tam/app.log` | 目录可写时启用 | 需 Docker volume 挂载 |

**Docker volume 配置**（docker-compose.yml）：

```yaml
backend:
  volumes:
    - backend-logs:/var/log/tam

volumes:
  backend-logs:
```

### 2.5 日志轮转与保留

| 参数 | 值 | 说明 |
|------|-----|------|
| rotation | 10 MB | 单文件达到 10MB 时轮转 |
| retention | 30 days | 保留最近 30 天的日志文件 |
| compression | gz | 轮转后的旧日志自动压缩 |
| backtrace | true | 异常时显示完整调用栈 |
| diagnose | true（开发）/ false（生产） | 异常时显示变量值 |

### 2.6 各业务模块日志详解

#### 2.6.1 认证与安全模块（core/security.py）

**日志概览**：12 条日志，覆盖 Token 管理、验证码、登录防护

| 日志级别 | 消息模板 | 触发场景 | 处理建议 |
|---------|---------|---------|---------|
| DEBUG | `Token blacklisted: jti={jti}, ttl={ttl}s` | Token 加入黑名单成功 | 正常，调试时查看 |
| WARNING | `Redis unavailable, skipping token blacklist: {e}` | Redis 不可用，Token 无法加入黑名单 | 检查 Redis 服务状态 |
| WARNING | `Redis unavailable, allowing token (fail-open): {e}` | Redis 不可用，Token 黑名单检查跳过 | 检查 Redis，期间已注销 Token 仍可使用 |
| WARNING | `Redis unavailable, returning token version 0 (fail-open): {e}` | Redis 不可用，Token 版本号返回 0 | 检查 Redis，期间密码修改后旧 Token 不失效 |
| INFO | `Token version incremented for user_id={id}: now at {ver}` | 用户密码修改/重置后 Token 版本号递增 | 正常 |
| WARNING | `Redis unavailable, allowing login (fail-open): {e}` | Redis 不可用，登录尝试次数检查跳过 | 检查 Redis，期间无登录锁定保护 |
| WARNING | `Redis unavailable, skipping captcha check (fail-open): {e}` | Redis 不可用，验证码要求检查跳过 | 检查 Redis，期间不要求验证码 |
| WARNING | `Redis unavailable, skipping failed login record: {e}` | Redis 不可用，登录失败记录跳过 | 检查 Redis，期间不累计失败次数 |
| WARNING | `Redis unavailable, skipping login attempts reset: {e}` | Redis 不可用，登录尝试次数重置跳过 | 检查 Redis |
| ERROR | `Redis unavailable, cannot generate captcha: {e}` | Redis 不可用，验证码生成失败 | **唯一非 fail-open**，验证码必须依赖 Redis |
| WARNING | `Redis unavailable, captcha verification failed (fail-open): {e}` | Redis 不可用，验证码验证跳过 | 检查 Redis，期间验证码不生效 |

**Redis 降级策略总览**：

| 函数 | 降级策略 | 安全影响 |
|------|---------|---------|
| `is_token_blacklisted` | 返回 False（允许） | 已注销 Token 短暂可用 |
| `get_token_version` | 返回 0 | 密码修改后旧 Token 不失效 |
| `increment_token_version` | 返回 0 | 同上 |
| `check_login_attempts` | 返回 False（未锁定） | 无登录锁定保护 |
| `check_captcha_required` | 返回 False（不需要） | 无验证码保护 |
| `record_failed_login` | 静默忽略 | 不累计失败次数 |
| `reset_login_attempts` | 静默忽略 | 无影响 |
| `verify_captcha` | 返回 False（验证失败） | 验证码不生效 |
| `generate_captcha` | **抛出异常** | **唯一 fail-closed**，验证码必须依赖 Redis |

#### 2.6.2 加密模块（core/crypto.py）

| 日志级别 | 消息模板 | 触发场景 | 处理建议 |
|---------|---------|---------|---------|
| WARNING | `ENCRYPTION_KEY is not set. Falling back to SECRET_KEY...` | ENCRYPTION_KEY 未配置 | 在 .env 中设置独立的 ENCRYPTION_KEY |

#### 2.6.3 请求日志中间件（middleware/logging.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `{METHOD} {PATH} - {STATUS} - {DURATION}ms | ip={IP} | req_id={REQ_ID}` | 每个非 /health 请求 |

**排除路径**：`/health`、`/metrics`（避免健康检查日志噪音）

#### 2.6.4 全局异常处理（middleware/error_handler.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| ERROR | `Unhandled exception [{error_id}]: {ExceptionType}: {message} \| {METHOD} {PATH}` | 未捕获异常 |

**error_id 关联**：前端 500 响应体中的 `error_id` 与日志中的 `[error_id]` 一致，用于快速定位。

> **Request-ID 与 error_id 的关系**：当未捕获异常发生时，日志中同时包含 request_id（格式字段）和 error_id（消息内容）。request_id 标识整个请求，error_id 标识该请求中的具体异常。排查问题时，先用 request_id 收集该请求的所有日志行，再用 error_id 定位异常详情和对应的前端错误提示。

#### 2.6.5 限流中间件（middleware/rate_limit.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| WARNING | `Rate limit exceeded for {client_id} on {path}` | 请求超过速率限制 |

#### 2.6.6 定时任务（main.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `Cleaned up {count} expired blacklist entries [source=scheduler]` | 过期黑名单清理完成 |
| ERROR | `Error in blacklist cleanup task: {Type}: {e} [source=scheduler]` | 清理任务异常 |
| ERROR | `Error in scheduled ARP collection task: {Type}: {e} [source=scheduler]` | ARP 采集任务异常 |
| INFO | `Synced IPGuard data for baseline: {tag} [source=scheduler]` | IPGuard 同步成功 |
| ERROR | `Error syncing IPGuard data for {tag}: {Type}: {e} [source=scheduler]` | IPGuard 同步失败 |
| ERROR | `Error in scheduled IPGuard sync task: {Type}: {e} [source=scheduler]` | IPGuard 同步任务异常 |
| INFO | `Compliance check for {tag}: {compliant} compliant, {bypass} bypass, {non_compliant} non-compliant` | 合规检查完成 |
| ERROR | `Error in compliance check for {tag}: {Type}: {e} [source=scheduler]` | 合规检查异常 |
| ERROR | `Error in scheduled compliance check task: {Type}: {e} [source=scheduler]` | 合规检查任务异常 |
| INFO | `Auto-unblocked {count} compliant terminals` | 自动解封完成 |
| ERROR | `Error in scheduled auto-unblock task: {Type}: {e} [source=scheduler]` | 自动解封任务异常 |
| INFO | `Scheduled backup completed: {filename}, size={size} [source=scheduler]` | 定时备份完成 |
| ERROR | `Error in scheduled backup task: {Type}: {e} [source=scheduler]` | 定时备份任务异常 |
| INFO | `Starting Terminal Network Access Manager...` | 应用启动 |
| INFO | `Database initialized` | 数据库初始化完成 |
| INFO | `Seeded {count} default system configs` | 系统配置初始化 |
| INFO | `All background scheduler tasks started` | 后台任务启动完成 |
| INFO | `Shutting down Terminal Network Access Manager...` | 应用关闭 |
| WARNING | `CORS: allow_origins='*' with allow_credentials=True is insecure...` | CORS 配置不安全 |

#### 2.6.7 终端管理服务（services/terminal_service.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `Successfully blocked IP: {ip}` | 终端封禁成功 |
| INFO | `Successfully unblocked IP: {ip}` | 终端解封成功 |
| WARNING | `Sangfor block failed for {ip}: {message}` | 防火墙封禁 API 返回失败 |
| WARNING | `Sangfor API error when blocking {ip}: {e}` | 防火墙封禁 API 调用异常 |
| WARNING | `Sangfor unblock failed for {ip}: {message}` | 防火墙解封 API 返回失败 |
| WARNING | `Sangfor API error when unblocking {ip}: {e}` | 防火墙解封 API 调用异常 |
| ERROR | `Error blocking IP {ip}: {e}` | 终端封禁操作失败 |
| ERROR | `Error unblocking IP {ip}: {e}` | 终端解封操作失败 |
| ERROR | `Error adding to whitelist: {e}` | 白名单添加失败 |
| ERROR | `Error deleting from whitelist: {e}` | 白名单删除失败 |
| ERROR | `Error adding to blacklist: {e}` | 黑名单添加失败 |
| ERROR | `Error deleting from blacklist: {e}` | 黑名单删除失败 |
| ERROR | `Error cleaning up expired blacklist: {e}` | 过期黑名单清理失败 |
| ERROR | `Error getting stats: {e}` | 统计查询失败 |
| ERROR | `Error getting/searching/counting MACs: {e}` | MAC 地址查询失败 |

#### 2.6.8 ARP 采集服务（services/arp_collector_service.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `Starting scheduled collection for '{tag}'` | 开始定时采集 |
| INFO | `Scheduled collection for '{tag}': success={s}, processed={p}, added={a}, updated={u}` | 采集完成 |
| INFO | `Auto-block result for '{tag}': blocked={b}, skipped={s}` | 自动封禁结果 |
| INFO | `Compliance check for source '{tag}': ...` | 合规检查结果 |
| ERROR | `SSH collection failed for '{tag}': {e}` | SSH 采集失败 |
| ERROR | `API collection failed for '{tag}': {e}` | API 采集失败 |
| ERROR | `Scheduled collection failed for '{tag}': {e}` | 定时采集失败 |
| ERROR | `Auto-block task failed for '{tag}': {e}` | 自动封禁失败 |
| ERROR | `Compliance check failed for source '{tag}': {e}` | 合规检查失败 |

#### 2.6.9 合规服务（services/compliance_service.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `Synced {count} IPGuard entries from '{tag}'` | IPGuard 数据同步成功 |
| WARNING | `No firewall bindings found for ARP source '{tag}'` | 数据源未绑定防火墙 |
| WARNING | `Firewall '{tag}' not found or disabled` | 防火墙配置不存在或已禁用 |
| ERROR | `IPGuard sync failed for '{tag}': {e}` | IPGuard 同步失败 |
| ERROR | `Failed to block/unblock {ip} on firewall '{tag}': {e}` | 防火墙操作失败 |

#### 2.6.10 数据源服务（services/data_source_service.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `Created data source: {name} (tag={tag}, type={type})` | 数据源创建 |
| INFO | `Updated data source: {name} (id={id})` | 数据源更新 |
| INFO | `Deleted data source: {name} (id={id})` | 数据源删除 |
| INFO | `Created binding: {arp} -> {firewall}` | 数据源绑定 |
| INFO | `Deleted binding: {arp} -> {firewall}` | 数据源解绑 |
| ERROR | `Connection test failed for {name}: {e}` | 连接测试失败 |

#### 2.6.11 配置服务（services/config_service.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `Seeded config: {key} = {value}` | 系统配置初始化 |
| INFO | `Seeded {count} default configs` | 批量初始化 |
| INFO | `Config updated: {key} = {value} (by {user})` | 配置更新 |

#### 2.6.12 深信服防火墙服务（services/sangfor_service.py）

| 日志级别 | 消息模板 | 触发场景 |
|---------|---------|---------|
| INFO | `Successfully authenticated with Sangfor API` | 防火墙认证成功 |
| INFO | `Blocked IPs: {list}` | 批量封禁成功 |
| INFO | `Unblocked IPs: {list}` | 批量解封成功 |
| ERROR | `Failed to authenticate with Sangfor API: {e}` | 防火墙认证失败 |
| ERROR | `Failed to block/unblock IPs {list}: {e}` | 批量操作失败 |
| ERROR | `Failed to get blocked IPs: {e}` | 查询封禁列表失败 |
| ERROR | `Failed to get system stats: {e}` | 查询系统状态失败 |

### 2.7 Request-ID 链路追踪

**实现架构**：

```
客户端请求 → RequestIDMiddleware → ContextVar(request_id) → _log_format 函数自动注入 → 日志输出
                    ↓                                        ↓
           读取/生成 request_id                        {extra[request_id]}
                    ↓
           响应头 X-Request-ID 返回客户端
```

**request_id 生成规则**：

- 优先使用客户端 `X-Request-ID` 请求头（支持上游服务传入）
- 若客户端未提供，则自动生成 12 位十六进制字符串（`uuid4` 前 12 位）
- 同一请求的所有日志行共享同一 request_id

**日志格式中的 request_id 字段**：

request_id 位于日志格式的 **级别** 和 **模块名** 之间：

```
2026-06-09 14:30:00.123 +08:00 | INFO | a1b2c3d4e5f6 | app.core.security:verify_token:45 - Token validated successfully
```

| 字段位置 | 字段 | 示例 | 说明 |
|---------|------|------|------|
| 第1段 | 时间戳 | `2026-06-09 14:30:00.123 +08:00` | 带毫秒和时区 |
| 第2段 | 级别 | `INFO` | 日志级别 |
| **第3段** | **request_id** | **`a1b2c3d4e5f6`** | **请求唯一标识** |
| 第4段 | 位置 | `app.core.security:verify_token:45` | 模块:函数:行号 |
| 第5段 | 消息 | `Token validated successfully` | 日志内容 |

**非请求上下文**：定时任务、启动日志等非 HTTP 请求上下文中，request_id 显示为 `-`：

```
2026-06-09 14:30:00.123 +08:00 | INFO | - | app.main:startup - Starting Terminal Network Access Manager...
```

**请求日志中的 req_id 字段**：RequestLoggingMiddleware 产生的请求日志中 `req_id` 字段与日志格式中的 `{extra[request_id]}` 一致，确保请求日志与业务日志可通过同一 request_id 关联。

**响应头**：每个 HTTP 响应均包含 `X-Request-ID` 头，返回给客户端，便于前端与后端日志关联。

**使用示例**：通过 request_id 追踪一个请求的所有日志行：

```bash
# 在后端日志中搜索特定 request_id 的所有日志
docker logs tam_backend 2>&1 | grep "a1b2c3d4e5f6"

# 输出示例：
# 2026-06-09 14:30:00.100 | INFO  | a1b2c3d4e5f6 | app.middleware.logging:dispatch:34 - POST /api/v1/auth/login - 200 - 45.23ms | ip=192.168.1.100
# 2026-06-09 14:30:00.105 | DEBUG | a1b2c3d4e5f6 | app.core.security:verify_token:45 - Token validated successfully
# 2026-06-09 14:30:00.110 | INFO  | a1b2c3d4e5f6 | app.services.terminal_service:get_stats:120 - Stats retrieved
```

---

## 3. 前端运行时日志

### 3.1 日志工具

**文件**：`frontend/src/lib/logger.ts`

**使用方式**：

```typescript
import { logger } from '../lib/logger';

logger.debug('ModuleName', 'Debug message', { key: 'value' });
logger.info('ModuleName', 'Info message');
logger.warn('ModuleName', 'Warning message', { context: 'data' });
logger.error('ModuleName', 'Error message', error);
```

> **注意**：前端 logger.ts 采用渐进式接入策略。当前仅在 App.tsx（全局错误监听）和 ErrorBoundary 中使用，其他模块仍使用 console.log/warn/error。后续迭代将逐步替换为统一 logger 调用。

### 3.2 日志格式说明

**控制台输出格式**：

```
[2026-06-09T06:30:00.123Z] [ERROR] [Global] Uncaught error: TypeError: Cannot read properties of undefined {"filename":"App.tsx","lineno":42,"colno":5}
```

| 字段 | 格式 | 说明 |
|------|------|------|
| 时间戳 | ISO 8601（UTC） | `2026-06-09T06:30:00.123Z` |
| 级别 | 大写英文 | DEBUG/INFO/WARN/ERROR |
| 模块名 | 自定义标识 | 如 `Global`、`ErrorBoundary`、`AuthStore` |

### 3.3 日志级别与输出策略

| 级别 | 开发环境 | 生产环境 | localStorage 持久化 |
|------|:-------:|:-------:|:------------------:|
| DEBUG | ✅ 输出 | ❌ 不输出 | ❌ |
| INFO | ✅ 输出 | ❌ 不输出 | ❌ |
| WARN | ✅ 输出 | ✅ 输出 | ✅ |
| ERROR | ✅ 输出 | ✅ 输出 | ✅ |

### 3.4 本地存储与导出

| 特性 | 说明 |
|------|------|
| 内存缓冲区 | 最近 100 条日志（所有级别） |
| localStorage | 最近 50 条 warn/error 日志 |
| Storage Key | `tam_log_buffer` |
| 存储大小 | 约 50KB |

**API 方法**：

| 方法 | 说明 |
|------|------|
| `logger.getBuffer()` | 获取内存缓冲区日志（只读） |
| `logger.getStored()` | 获取 localStorage 持久化日志 |
| `logger.exportLogs()` | 导出所有日志为 JSON 字符串（去重） |
| `logger.clearLogs()` | 清除内存和 localStorage 日志 |

### 3.5 全局错误监听

**注册位置**：`frontend/src/App.tsx` useEffect

| 事件 | 日志模块 | 消息模板 | 附加数据 |
|------|---------|---------|---------|
| `window.error` | `Global` | `Uncaught error: {message}` | filename, lineno, colno |
| `window.unhandledrejection` | `Global` | `Unhandled promise rejection: {reason}` | — |
| ErrorBoundary | `ErrorBoundary` | `Uncaught error: {message}` | stack, componentStack |

---

## 4. 审计日志

### 4.1 审计日志架构

审计日志独立于应用日志，存储在 PostgreSQL `audit_logs` 表中，通过前端审计日志页面查看和管理。

**数据流**：

```
API 端点 → TerminalService.log_action() → audit_logs 表 → 前端审计日志页面
                                                    ↓
                                              CSV 导出（超管）
```

### 4.2 审计操作类型清单

#### 认证相关（6项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `login` | auth | POST /auth/login | 登录成功 |
| `login_failed` | auth | POST /auth/login | 登录失败（用户不存在或密码错误） |
| `logout` | auth | POST /auth/logout | 用户注销 |
| `token_refresh` | auth | POST /auth/refresh | Token 刷新 |
| `change_password` | auth | PUT /auth/me/password | 用户自行修改密码 |
| `password_reset` | auth | POST /auth/password-reset/verify | 用户通过验证码重置密码 |

#### 用户管理（7项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `create_user` | user | POST /auth/users | 创建用户 |
| `update_user` | user | PUT /auth/users/{id} | 更新用户信息 |
| `delete_user` | user | DELETE /auth/users/{id} | 删除用户 |
| `reset_password` | user | POST /auth/users/{id}/reset-password | 管理员重置用户密码 |
| `unlock_user` | user | POST /auth/users/{id}/unlock | 解锁用户 |
| `lock_user` | user | POST /auth/users/{id}/lock | 锁定用户 |
| `change_role` | user | PUT /auth/users/{id}/role | 修改用户角色 |

#### 终端管理（5项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `block_terminal` | terminal | POST /terminals/{id}/block | 手动封禁终端 |
| `unblock_terminal` | terminal | POST /terminals/{id}/unblock | 手动解封终端 |
| `auto_block_terminal` | terminal | 定时任务 | 自动封锁不合规终端 |
| `auto_unblock_terminal` | terminal | 定时任务 | 自动解封合规终端 |
| `recalculate_compliance` | terminal | POST /data-sources/compliance/recalculate | 重新计算合规状态 |

#### 白名单管理（2项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `add_whitelist` | whitelist | POST /whitelist | 添加白名单 |
| `remove_whitelist` | whitelist | DELETE /whitelist/{id} | 移除白名单 |

#### 黑名单管理（3项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `block_blacklist` | blacklist | POST /blacklist | 添加黑名单 |
| `unblock_blacklist` | blacklist | DELETE /blacklist/{id}/unblock | 解除黑名单 |
| `cleanup_expired_blacklist` | blacklist | POST /blacklist/cleanup | 清理过期黑名单 |

#### 数据源管理（7项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `create_datasource` | datasource | POST /data-sources/ | 创建数据源 |
| `update_datasource` | datasource | PUT /data-sources/{id} | 更新数据源 |
| `delete_datasource` | datasource | DELETE /data-sources/{id} | 删除数据源 |
| `test_datasource` | datasource | POST /data-sources/{id}/test | 测试数据源连接 |
| `sync_datasource` | datasource | POST /data-sources/{id}/sync | 同步数据源数据 |
| `bind_datasource` | datasource | POST /data-sources/bindings/ | 绑定数据源到防火墙 |
| `unbind_datasource` | datasource | DELETE /data-sources/bindings/{id} | 解绑数据源 |

#### 合规基线管理（6项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `create_baseline` | compliance | POST /compliance-baselines/ | 创建合规基线 |
| `update_baseline` | compliance | PUT /compliance-baselines/{id} | 更新合规基线 |
| `delete_baseline` | compliance | DELETE /compliance-baselines/{id} | 删除合规基线 |
| `sync_baseline` | compliance | POST /compliance-baselines/{id}/sync | 同步合规基线数据 |
| `test_baseline` | compliance | POST /compliance-baselines/{id}/test | 测试合规基线连接 |
| `recalculate_compliance` | compliance | POST /data-sources/compliance/recalculate | 重新计算合规状态 |

#### 通知管理（9项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `create_notification_channel` | notification | POST /notifications/channels | 创建通知渠道 |
| `update_notification_channel` | notification | PUT /notifications/channels/{id} | 更新通知渠道 |
| `delete_notification_channel` | notification | DELETE /notifications/channels/{id} | 删除通知渠道 |
| `create_notification_template` | notification | POST /notifications/templates | 创建通知模板 |
| `update_notification_template` | notification | PUT /notifications/templates/{id} | 更新通知模板 |
| `delete_notification_template` | notification | DELETE /notifications/templates/{id} | 删除通知模板 |
| `create_notification_rule` | notification | POST /notifications/rules | 创建通知规则 |
| `update_notification_rule` | notification | PUT /notifications/rules/{id} | 更新通知规则 |
| `delete_notification_rule` | notification | DELETE /notifications/rules/{id} | 删除通知规则 |

#### 备份管理（6项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `create_backup` | backup | POST /backup/run | 执行手动备份 |
| `delete_backup` | backup | DELETE /backup/{filename} | 删除备份文件 |
| `restore_backup` | backup | POST /backup/restore/{filename} | 恢复备份 |
| `download_backup` | backup | GET /backup/download/{filename} | 下载备份文件 |
| `update_backup_config` | backup | PUT /backup/config | 更新备份配置 |
| `scheduled_backup` | backup | 内部定时任务 | 定时触发自动备份 |

#### 认证提供商（4项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `create_auth_provider` | auth_provider | POST /auth/providers | 创建认证提供商 |
| `update_auth_provider` | auth_provider | PUT /auth/providers/{id} | 更新认证提供商 |
| `delete_auth_provider` | auth_provider | DELETE /auth/providers/{id} | 删除认证提供商 |
| `test_auth_provider` | auth_provider | POST /auth/providers/{id}/test | 测试认证提供商连接 |

#### 系统管理（6项）

| 操作类型 | 资源类型 | 触发端点 | 说明 |
|---------|---------|---------|------|
| `update_config` | system | PUT /settings/{key} | 更新系统配置 |
| `upload_branding` | system | POST /settings/upload | 上传品牌资源 |
| `export_audit_logs` | system | GET /logs/export | 导出审计日志 |
| `test_email` | system | POST /settings/email/test | 测试邮件配置 |
| `save_email_config` | system | PUT /settings/update | 保存邮件配置 |

**共计 56 项审计操作类型**。

### 4.3 审计日志字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer | 主键 |
| `username` | String | 操作人用户名 |
| `action` | String | 操作类型（见上表） |
| `resource_type` | String | 资源类型（auth/user/terminal/whitelist/blacklist/datasource/compliance/system/notification/backup/auth_provider） |
| `resource_id` | String | 资源 ID（可为空） |
| `resource_name` | String | 资源名称（如用户名、配置键名，可为空） |
| `details` | JSON | 操作详情（含 message 和其他上下文） |
| `ip_address` | String | 客户端 IP 地址 |
| `created_at` | DateTime | 操作时间（UTC） |

### 4.3.1 details 字段结构

`details` 字段为 JSON 格式，包含操作的详细信息：

| 字段 | 类型 | 说明 |
|------|------|------|
| `message` | String | 操作描述信息 |
| `key` | String | 配置键名（update_config 操作） |
| `old_value` | Any | 旧值（update_config 操作） |
| `new_value` | Any | 新值（update_config 操作） |
| `changes` | Object | 变更详情（save_email_config 操作） |
| `terminals` | Array | 受影响终端列表（auto_block/auto_unblock 操作，最多50条） |
| `total_terminals` | Integer | 终端总数（auto_block/auto_unblock 操作） |
| `source_tag` | String | 数据源标签（合规相关操作） |
| `firewall_tags` | Array | 防火墙标签列表（封锁相关操作） |
| `blocked` | Integer | 成功封锁数量（auto_block 操作） |
| `unblocked` | Integer | 成功解封数量（auto_unblock 操作） |
| `skipped` | Integer | 跳过数量（auto_block/auto_unblock 操作） |

### 4.4 审计日志查询与导出

- **查询**：前端审计日志页面，支持按用户名、操作类型、时间范围筛选
- **导出**：仅超级管理员可导出 CSV，GET /api/v1/logs/export

### 4.5 审计日志归档与清理

使用 `manage.sh audit-cleanup` 命令（详见 [8.2 节](#82-日志运维命令)）。

**定时归档 cron 示例**：

```bash
# 每月1日凌晨3点自动归档并清理180天前的审计日志
0 3 1 * * /opt/tam/manage.sh audit-cleanup --days 180 --archive --force >> /var/log/tam/audit-cleanup.log 2>&1
```

---

## 5. Docker 容器日志

### 5.1 日志驱动与限制

所有服务使用 `json-file` 日志驱动，配置大小和文件数限制：

| 服务 | max-size | max-file | 最大占用 | 说明 |
|------|:--------:|:--------:|:--------:|------|
| postgres | 10m | 3 | 30MB | 数据库日志量小 |
| redis | 10m | 3 | 30MB | Redis 日志量小 |
| backend | 20m | 5 | 100MB | 应用日志量大，保留更多 |
| frontend | 10m | 3 | 30MB | 仅构建日志 |
| nginx | 10m | 3 | 30MB | 访问日志 |

**总计最大占用**：约 220MB

### 5.2 各服务日志配置

```yaml
# docker-compose.yml 中每个服务的 logging 配置
logging:
  driver: json-file
  options:
    max-size: "10m"    # 单个日志文件最大大小
    max-file: "3"      # 保留的日志文件数量
```

### 5.3 容器日志查看

```bash
# 查看所有服务日志
./manage.sh logs

# 查看指定服务日志
./manage.sh logs backend

# 指定显示条数
./manage.sh logs -n 200 backend
```

---

## 6. Nginx 日志

**配置文件**：`nginx/etc/conf.d/tam.conf`

| 日志类型 | 输出目标 | 级别 | 说明 |
|---------|---------|------|------|
| access_log | `/dev/stdout` | — | 所有 HTTP 请求记录 |
| error_log | `/dev/stderr` | warn | Nginx 错误日志 |

**查看方式**：通过 `docker logs tam_nginx` 或 `./manage.sh logs nginx`

**典型 access_log 条目**：

```
192.168.1.100 - - [09/Jun/2026:14:30:00 +0800] "GET /api/v1/terminals HTTP/1.1" 200 1234 "-" "Mozilla/5.0"
```

---

## 7. PostgreSQL 日志

**配置方式**：docker-compose.yml 中 postgres command 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `log_min_duration_statement` | 1000 | 记录执行超过 1 秒的慢查询 |
| `log_connections` | on | 记录所有数据库连接 |
| `log_disconnections` | on | 记录所有数据库断开连接 |
| `log_line_prefix` | `%t [%p] %u@%d ` | 时间戳 [PID] 用户@数据库 |

**典型日志条目**：

```
2026-06-09 14:30:00.123 CST [42] tam_admin@tam_db LOG:  duration: 1523.456 ms  statement: SELECT ...
2026-06-09 14:30:01.000 CST [43] tam_admin@tam_db LOG:  connection received: host=172.18.0.4 port=5432
2026-06-09 14:30:01.001 CST [43] tam_admin@tam_db LOG:  connection authorized: user=tam_admin database=tam_db
```

**查看方式**：`./manage.sh logs postgres`

---

## 8. 运维脚本日志

### 8.1 脚本日志函数

`manage.sh` 定义了 4 个日志输出函数：

| 函数 | 前缀 | 颜色 | 输出目标 | 用途 |
|------|------|------|---------|------|
| `log_step` | `━━━` | 青色粗体 | stdout | 步骤标题 |
| `log_ok` | `[OK]` | 绿色 | stdout | 操作成功 |
| `log_warn` | `[WARN]` | 黄色 | stdout | 警告信息 |
| `log_error` | `[ERROR]` | 红色 | stderr | 错误信息 |

#### manage.sh 操作日志

manage.sh 支持操作日志记录功能，记录所有命令执行过程和结果：

**启用方式**：

```bash
# 方式一：命令行参数（单次生效）
./manage.sh --log backup

# 方式二：环境变量（持久生效）
# 在 .env 中设置
TAM_LOG_ENABLED=true
```

**日志存储**：

| 项目 | 说明 |
|------|------|
| 目录 | `.manage/logs/` |
| 文件名 | `manage_YYYYMMDD.log` |
| 格式 | `[YYYY-MM-DD HH:MM:SS] [LEVEL] [COMMAND] Message` |
| 轮转 | 保留最近 30 天日志 |

**日志内容**：

- 所有命令执行记录（命令名、参数、时间）
- 操作结果（成功/失败/警告）
- 备份记录（文件路径、大小）
- 破坏性操作确认记录
- 错误详情

### 8.2 日志运维命令

#### logs — 查看服务日志

```bash
./manage.sh logs                    # 查看所有服务日志（最近100条）
./manage.sh logs backend            # 查看 backend 日志
./manage.sh logs -n 200 backend     # 查看 backend 最近200条日志
```

#### logs-cleanup — 清理 Docker 容器日志

```bash
./manage.sh logs-cleanup            # 清理所有容器日志
./manage.sh logs-cleanup --dry-run  # 仅查看日志大小，不实际清理
```

**输出示例**：

```
  postgres: 5.23MB
  redis: 1.02MB
  backend: 12.45MB
  frontend: 0.50MB
  nginx: 8.30MB
  Total: 27.50MB

Truncating Docker container logs...
  postgres: truncated
  redis: truncated
  backend: truncated
  frontend: truncated
  nginx: truncated
[OK] Docker logs cleaned up
```

#### logs-archive — 归档日志

```bash
./manage.sh logs-archive
```

将所有服务的 Docker 日志和应用日志文件归档到 `backups/logs_{TIMESTAMP}.tar.gz`。

#### audit-cleanup — 清理过期审计日志

```bash
./manage.sh audit-cleanup                    # 默认保留180天，需确认
./manage.sh audit-cleanup --days 90          # 保留90天
./manage.sh audit-cleanup --days 90 --archive # 先导出CSV再删除
./manage.sh audit-cleanup --force             # 跳过确认
```

**输出示例**：

```
━━━ Cleaning up expired audit logs ━━━

Found 1250 audit log(s) older than 180 days
Exporting to backups/audit_logs_20260609_143000.csv...
  Exported 1250 record(s)

This will permanently delete 1250 audit log(s) older than 180 days.
Continue? [y/N] y

[OK] Cleaned up 1250 audit log(s) older than 180 days
```

#### logs-export — 导出审计日志

```bash
./manage.sh logs-export                              # 导出最近30天审计日志
./manage.sh logs-export --days 90                    # 导出最近90天
./manage.sh logs-export --output /tmp/audit.csv      # 指定输出文件
./manage.sh logs-export --username admin             # 按用户名过滤
./manage.sh logs-export --action login               # 按操作类型过滤
```

**输出示例**：

```
━━━ Exporting audit logs ━━━

Exporting audit logs (last 30 days)...
  Output: backups/audit_logs_export_20260611_143000.csv
  Records: 1,250
  Size: 256KB

[OK] Audit logs exported successfully
```

**参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--days N` | 30 | 导出最近 N 天的审计日志 |
| `--output file` | `backups/audit_logs_export_{TIMESTAMP}.csv` | 输出文件路径 |
| `--username user` | 全部 | 按用户名过滤 |
| `--action action` | 全部 | 按操作类型过滤 |

> **安全说明**：`--username` 和 `--action` 参数已做 SQL 注入防护（单引号转义）。

---

## 9. 日志管理运维手册

### 9.1 日常日志查看

```bash
# 实时跟踪后端日志
./manage.sh logs backend

# 查看最近错误
docker logs tam_backend 2>&1 | grep "ERROR" | tail -20

# 查看 Redis 降级警告
docker logs tam_backend 2>&1 | grep "Redis unavailable" | tail -10

# 查看请求日志
docker logs tam_backend 2>&1 | grep "GET\|POST\|PUT\|DELETE" | tail -20

# 查看 Nginx 访问日志
./manage.sh logs nginx

# 查看数据库慢查询
docker logs tam_db 2>&1 | grep "duration" | tail -10
```

### 9.2 日志归档操作

```bash
# 归档所有服务日志
./manage.sh logs-archive

# 查看归档文件
ls -lh backups/logs_*.tar.gz
```

### 9.3 日志清理操作

```bash
# 查看 Docker 日志占用
./manage.sh logs-cleanup --dry-run

# 清理 Docker 日志
./manage.sh logs-cleanup

# 清理过期审计日志（先归档）
./manage.sh audit-cleanup --days 180 --archive

# 清理过期审计日志（直接删除，跳过确认）
./manage.sh audit-cleanup --days 365 --force
```

### 9.4 故障排查指南

#### Redis 不可用

**特征日志**：大量 `Redis unavailable, ... (fail-open)` WARNING

**排查步骤**：

1. `./manage.sh logs redis` — 查看 Redis 日志
2. `docker exec tam_redis redis-cli -a <password> ping` — 测试连接
3. `docker restart tam_redis` — 重启 Redis
4. 检查内存限制：`docker stats tam_redis`

#### 登录失败

**特征日志**：`login_failed` 审计日志 + `Rate limit exceeded` WARNING

**排查步骤**：

1. 查看审计日志页面的 `login_failed` 记录
2. 检查是否触发限流：`docker logs tam_backend 2>&1 | grep "Rate limit"`
3. 检查验证码：`docker logs tam_backend 2>&1 | grep "captcha"`

#### 防火墙操作失败

**特征日志**：`Sangfor API error` / `Sangfor block/unblock failed`

**排查步骤**：

1. 检查防火墙连接配置
2. 测试数据源连接：前端 → 数据源管理 → 测试连接
3. 检查防火墙认证：`docker logs tam_backend 2>&1 | grep "Sangfor API"`

#### 未捕获异常

**特征日志**：`Unhandled exception [error_id]` ERROR

**排查步骤**：

1. 记录前端响应中的 `error_id`
2. 在后端日志中搜索：`docker logs tam_backend 2>&1 | grep "error_id"`
3. 查看完整异常栈

#### 数据库连接问题

**特征日志**：PostgreSQL 日志中 `connection received` 频繁出现

**排查步骤**：

1. `./manage.sh logs postgres` — 查看数据库日志
2. `docker exec tam_db psql -U tam_admin -d tam_db -c "SELECT count(*) FROM pg_stat_activity;"` — 查看连接数
3. 检查连接泄漏：大量 `connection received` 但无 `disconnection`

---

## 10. 日志安全与合规

### 敏感信息保护

| 规则 | 实现 |
|------|------|
| 不记录密码 | 密码字段在日志中以 `***` 替代 |
| 不记录 Token 完整值 | 仅记录 jti（Token ID） |
| 不记录加密密钥 | ENCRYPTION_KEY 仅在启动校验时检查存在性 |
| 请求日志不含请求体 | 仅记录方法、路径、状态码、耗时、IP |
| 审计日志 details 不含密码 | change_password 仅记录消息，不含密码值 |

### 日志访问控制

| 日志类型 | 访问权限 |
|---------|---------|
| Docker 容器日志 | 服务器管理员（shell 访问） |
| 应用日志文件 | 服务器管理员（文件系统访问） |
| 审计日志页面 | 已登录用户（查看）/ 超级管理员（导出） |
| 前端浏览器日志 | 终端用户（浏览器 DevTools） |

### 日志保留合规

| 日志类型 | 默认保留 | 可配置 | 归档方式 |
|---------|---------|--------|---------|
| 应用日志文件 | 30 天 | loguru retention 参数 | 自动 gz 压缩 |
| Docker 容器日志 | 3-5 个文件 | max-file 参数 | json-file 驱动自动轮转 |
| 审计日志 | 无限 | audit-cleanup --days | CSV 导出后删除 |
| PostgreSQL 慢查询 | Docker 日志限制 | 同容器日志 | 同容器日志 |

### 审计日志完整性

- 审计日志通过数据库事务写入，确保一致性
- 审计日志无 UPDATE/DELETE API，仅支持查询和导出
- 清理操作通过 manage.sh 命令执行，需管理员 shell 权限
- 清理前可选归档为 CSV 文件，保留历史记录

---

## 11. 文档版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v3.1.0 | 2026-06-09 | 初始版本：完整日志体系文档 |
| v3.2.0 | 2026-06-10 | 新增 Request-ID 链路追踪、文档版本历史、日志监控与告警、紧急处理流程、性能影响说明、日志分析常用命令、日志配置变更指南；修正审计归档 cron 示例、前端日志标注"渐进式接入"、Request-ID 与 error_id 关联说明 |
| v3.2.0-r2 | 2026-06-11 | 新增 manage.sh 操作日志功能（`--log`/`TAM_LOG_ENABLED`）、`logs-export` 审计日志导出命令 |

---

## 12. 日志监控与告警

### 推荐监控指标

| 指标 | 说明 | 采集方式 |
|------|------|---------|
| ERROR 日志速率 | 每分钟 ERROR 级别日志数量 | 日志解析 / Prometheus counter |
| Redis 降级事件频率 | `Redis unavailable` WARNING 出现频率 | 日志解析 / grep 计数 |
| 请求延迟 P99 | 请求响应时间第 99 百分位 | RequestLoggingMiddleware 日志解析 |
| 4xx/5xx 状态码比例 | HTTP 错误状态码占比 | Nginx access_log 解析 / 应用日志解析 |

### 推荐告警规则

| 告警规则 | 条件 | 级别 | 处理建议 |
|---------|------|------|---------|
| ERROR 日志高频 | 连续5分钟 > 10次/分钟 | WARNING | 检查后端日志，定位异常模块 |
| Redis 不可用 | `Redis unavailable` 事件 > 0 | CRITICAL | 立即检查 Redis 服务状态 |
| 5xx 率过高 | 5xx 状态码比例 > 5% | CRITICAL | 检查后端服务健康状态 |

### 推荐工具

| 工具组合 | 适用场景 | 说明 |
|---------|---------|------|
| Prometheus + Grafana | 指标监控与可视化 | Prometheus 采集指标，Grafana 展示仪表盘 |
| ELK Stack (Elasticsearch + Logstash + Kibana) | 日志聚合与全文搜索 | 适合大规模日志分析 |
| Loki + Grafana | 轻量级日志聚合 | 仅索引标签，资源占用低 |

### 当前系统已有的监控基础

| 组件 | 说明 |
|------|------|
| `/health` 端点 | 后端健康检查端点，返回服务状态 |
| Prometheus instrumentator | 非生产环境已集成，提供请求指标采集 |

---

## 13. 紧急处理流程

### 日志系统故障处理

#### 日志文件不可写

**症状**：应用日志仅输出到 stdout，无文件日志

**处理步骤**：

```bash
# 1. 检查日志目录是否存在
docker exec tam_backend ls -la /var/log/tam/

# 2. 检查目录权限
docker exec tam_backend stat /var/log/tam/

# 3. 检查 Docker volume 挂载
docker inspect tam_backend | grep -A 5 "Mounts"

# 4. 修复权限（如需要）
docker exec tam_backend chmod 755 /var/log/tam/

# 5. 重启后端服务
docker restart tam_backend
```

#### 磁盘满

**症状**：日志写入失败、服务异常

**处理步骤**：

```bash
# 1. 检查磁盘使用率
df -h

# 2. 查看日志目录占用
du -sh /var/log/tam/
du -sh /var/lib/docker/containers/

# 3. 紧急清理 Docker 容器日志
./manage.sh logs-cleanup

# 4. 清理旧的应用日志文件
find /var/log/tam/ -name "*.gz" -mtime +7 -delete

# 5. 归档并清理审计日志
./manage.sh audit-cleanup --days 90 --archive --force
```

#### 日志丢失

**症状**：预期日志行缺失

**处理步骤**：

```bash
# 1. 确认日志级别配置
docker exec tam_backend env | grep LOG_LEVEL

# 2. 检查日志轮转是否过于激进
docker exec tam_backend ls -la /var/log/tam/

# 3. 检查 Docker 日志限制
docker inspect tam_backend | grep -A 5 "LogConfig"

# 4. 临时调低日志级别以确认
# 修改 .env 中 LOG_LEVEL=DEBUG，然后重启
docker restart tam_backend
```

### 审计日志紧急处理

#### 数据库写入失败

**症状**：审计日志页面无新记录，但应用日志正常

**处理步骤**：

```bash
# 1. 检查数据库连接
docker exec tam_db psql -U tam_admin -d tam_db -c "SELECT 1;"

# 2. 检查 audit_logs 表状态
docker exec tam_db psql -U tam_admin -d tam_db -c "SELECT count(*) FROM audit_logs;"

# 3. 检查数据库磁盘空间
docker exec tam_db df -h /var/lib/postgresql/data

# 4. 检查后端日志中的数据库错误
docker logs tam_backend 2>&1 | grep -i "database\|psql\|connection" | tail -20
```

#### 磁盘空间不足

**处理步骤**：

```bash
# 1. 检查数据库占用
docker exec tam_db psql -U tam_admin -d tam_db -c "SELECT pg_size_pretty(pg_database_size('tam_db'));"

# 2. 检查 audit_logs 表占用
docker exec tam_db psql -U tam_admin -d tam_db -c "SELECT pg_size_pretty(pg_total_relation_size('audit_logs'));"

# 3. 归档并清理旧审计日志
./manage.sh audit-cleanup --days 90 --archive --force

# 4. 如需紧急释放空间，直接清理更早的记录
./manage.sh audit-cleanup --days 30 --archive --force
```

### 日志泄露应急

**症状**：敏感信息（密码、Token、密钥）出现在日志中

**处理步骤**：

```bash
# 1. 立即定位泄露的日志文件
docker logs tam_backend 2>&1 | grep -i "password\|secret\|token.*=" | head -20

# 2. 评估泄露范围
# - 检查 stdout 日志（Docker 容器日志）
# - 检查文件日志 /var/log/tam/app.log*
# - 检查归档文件

# 3. 清理 Docker 容器日志
./manage.sh logs-cleanup

# 4. 清理应用日志文件
docker exec tam_backend rm -f /var/log/tam/app.log*

# 5. 重启服务（生成新的日志文件）
docker restart tam_backend

# 6. 修复代码中的日志泄露点
# - 在对应模块中添加敏感信息脱敏处理
# - 确保 password/secret/token 字段以 *** 替代

# 7. 通知安全团队
# - 报告泄露的信息类型和范围
# - 评估是否需要轮换受影响的密钥/Token
```

---

## 14. 性能影响说明

### 日志系统性能开销评估

| 组件 | 开销类型 | 说明 |
|------|---------|------|
| loguru 异步写文件 | I/O 开销 | loguru 使用独立线程写文件，不阻塞主线程 |
| 格式函数调用开销 | CPU 开销 | `_log_format` 函数每次日志调用执行，含 ContextVar 读取和字符串格式化 |
| ContextVar 读取开销 | CPU 开销 | 每次 `_log_format` 调用读取 `request_id`，开销极低（< 0.1μs） |

### 各级别日志的预估性能影响

| 日志级别 | 单次日志调用耗时 | 生产环境是否输出 | 说明 |
|---------|:--------------:|:--------------:|------|
| DEBUG | < 1μs | 否（LOG_LEVEL=INFO） | 仅格式化判断，不输出 |
| INFO | < 5μs | 是 | 格式化 + 异步写入 |
| WARNING | < 5μs | 是 | 格式化 + 异步写入 |
| ERROR（含异常栈） | 50-200μs | 是 | 含异常栈格式化，开销较大 |

### 文件轮转性能影响

| 场景 | 影响 | 说明 |
|------|------|------|
| 正常写入 | 无感知 | loguru 异步线程写入 |
| 轮转时（10MB 触发） | 短暂暂停 < 100ms | 文件重命名 + 压缩旧文件 |
| 压缩旧日志 | 后台进行 | 不影响当前日志写入 |

### 建议的生产环境日志级别

| 环境 | 建议级别 | 说明 |
|------|---------|------|
| 生产环境 | INFO | 平衡信息量和性能，DEBUG 级别日志量过大 |
| 预发布环境 | INFO / DEBUG | 排查问题时可临时切换为 DEBUG |
| 开发环境 | DEBUG | 完整调试信息 |

---

## 15. 日志分析常用命令

### 按 request_id 追踪完整请求链路

```bash
docker logs tam_backend 2>&1 | grep "a1b2c3d4e5f6"
```

### 统计各状态码分布

```bash
docker logs tam_backend 2>&1 | grep -oP '\d{3}' | sort | uniq -c | sort -rn
```

### 查找慢请求（>1s）

```bash
docker logs tam_backend 2>&1 | grep -oP '\d+\.\d+ms' | awk -F'ms' '{if($1>1000) print}'
```

### 统计 ERROR 日志按模块分组

```bash
docker logs tam_backend 2>&1 | grep "ERROR" | grep -oP '(?<=\| ).*?(?=:\w+:)' | sort | uniq -c | sort -rn
```

### 查找 Redis 降级事件

```bash
docker logs tam_backend 2>&1 | grep "Redis unavailable" | wc -l
```

### 按时间范围过滤

```bash
docker logs tam_backend --since "2026-06-09T14:00:00" --until "2026-06-09T15:00:00"
```

### 审计日志 SQL 查询

```sql
SELECT action, count(*) FROM audit_logs WHERE timestamp > NOW() - INTERVAL '7 days' GROUP BY action ORDER BY count DESC;
```

---

## 16. 日志配置变更指南

### 修改日志级别

**文件**：`.env`

**修改示例**：

```bash
# 将日志级别从 INFO 改为 DEBUG
LOG_LEVEL=DEBUG
```

**生效方式**：重启 backend 容器

```bash
docker restart tam_backend
```

### 修改日志保留天数

**文件**：`backend/app/core/logging_config.py`

**修改示例**：

```python
# 将保留天数从 30 天改为 60 天
retention="60 days",
```

**生效方式**：重启 backend 容器

```bash
docker restart tam_backend
```

### 修改日志文件大小限制

**文件**：`backend/app/core/logging_config.py`

**修改示例**：

```python
# 将单文件大小限制从 10MB 改为 20MB
rotation="20 MB",
```

**生效方式**：重启 backend 容器

```bash
docker restart tam_backend
```

### 修改 Docker 日志限制

**文件**：`docker-compose.yml`

**修改示例**：

```yaml
# 将 backend 服务的日志限制从 20m/5文件 改为 50m/10文件
backend:
  logging:
    driver: json-file
    options:
      max-size: "50m"
      max-file: "10"
```

**生效方式**：重新创建容器

```bash
docker compose up -d backend
```

### 修改 PostgreSQL 日志级别

**文件**：`docker-compose.yml`

**修改示例**：

```yaml
# 在 postgres 服务的 command 中修改日志参数
postgres:
  command: >
    postgres
    -c log_min_duration_statement=500
    -c log_connections=on
    -c log_disconnections=on
    -c log_line_prefix='%t [%p] %u@%d '
```

**生效方式**：重新创建容器

```bash
docker compose up -d postgres
```

### 修改 Nginx 日志级别

**文件**：`nginx/etc/conf.d/tam.conf`

**修改示例**：

```nginx
# 将 error_log 级别从 warn 改为 error
error_log /dev/stderr error;
```

**生效方式**：重新加载 Nginx 配置

```bash
docker exec tam_nginx nginx -s reload
```

### 修改系统时区

**文件**：`.env`

**修改示例**：

```bash
# 将时区从 Asia/Shanghai 改为 America/New_York
TZ=America/New_York
```

**影响范围**：所有容器系统时间、后端日志时间戳、PostgreSQL 日志和查询时间

**生效方式**：重启所有服务

```bash
docker compose down && docker compose up -d
```
