# 修复 .env 变量未动态引用到 docker-compose.yml 的问题

## 根因确认

对比 [config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/config.py#L17-L106) 的 Settings 字段 vs [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L86-L142) 的 `backend.environment`，确实存在大量 `.env` 定义的变量 **未传递到容器**，且有几处 **硬编码端口**：

### Critical Bug — 自定义后端端口后健康检查必挂

```yaml
# docker-compose.yml:117 — 硬编码 8000！
test: ["CMD", "python", "-c", "...urlopen('http://localhost:8000/health')"]
```

用户改 `.env TAM_BACKEND_PORT=8001` 后：

* 容器内 uvicorn 实际监听 8001

* healthcheck 却去探测 8000

* 结果：服务正常运行但被标记 unhealthy → 上游依赖受影响 → 表现为"各种问题"

这正是"默认端口 OK，自定义端口崩"的直接原因。

### 缺失的环境变量清单

`.env` / `.env.example` 中定义但 docker-compose.yml **未动态传入** 的变量（用户改了白改）：

| 分类             | 变量                                                                                               |
| -------------- | ------------------------------------------------------------------------------------------------ |
| **安全/认证**      | `DEBUG`, `PROJECT_NAME`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` |
| **风控/锁定**      | `MAX_LOGIN_ATTEMPTS`, `LOCKOUT_DURATION_MINUTES`, `CAPTCHA_THRESHOLD`                            |
| **注册/限流**      | `ALLOW_REGISTRATION`, `RATE_LIMIT_PER_MINUTE`, `AUTH_RATE_LIMIT_PER_MINUTE`                      |
| **日志/路径**      | `LOG_LEVEL`, `UPLOAD_DIR`                                                                        |
| **数据库组件**      | `DB_HOST`, `DB_PORT`, `DB_NAME` (postgres 容器 `POSTGRES_DB` 也硬编码 `tam_db`，未用 `${DB_NAME}`)        |
| **Redis**      | `REDIS_PASSWORD` 未独立传（仅内联在构造的 `REDIS_URL` 里）                                                     |
| **深信服集成**      | `SANGFOR_CA_BUNDLE`                                                                              |
| **交换机集成**      | `SWITCH_PORT`                                                                                    |
| **IPGuard 集成** | `IPGUARD_HOST`, `IPGUARD_USER`, `IPGUARD_PASSWORD`, `IPGUARD_DATABASE`                           |

### DATABASE\_URL / REDIS\_URL 构造方式

当前 docker-compose.yml **不使用** `.env` 中的 `DATABASE_URL`，而是用 `${DB_USER}` / `${DB_PASSWORD}` / `${REDIS_PASSWORD}` 重新拼接。优点：支持 `${DB_USER:-tam_admin}` 默认值语法，且对 postgres / redis 容器自身传参也用这些片段。**保留这种方式**，但：

* 也要把 `DATABASE_URL` 和 `REDIS_URL` 原样传进后端作为兜底

* 把 DB\_\* 和 REDIS\_PASSWORD 等字段也传进去（Settings 类本身也支持这些字段的独立解析）

## 修改清单

### 1. postgres 容器 — POSTGRES\_DB 改为变量引用

**文件**: [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L5-L9)

```yaml
POSTGRES_DB: ${DB_NAME:-tam_db}
```

### 2. backend.environment — 补齐所有缺失的动态变量

**文件**: [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L91-L107)

将当前 16 行 environment 扩充为完整映射：

```yaml
    environment:
      # Core
      PROJECT_NAME: ${PROJECT_NAME:-Terminal Access Platform}
      ENVIRONMENT: ${ENVIRONMENT:-development}
      DEBUG: ${DEBUG:-false}
      VERSION: "${VERSION}"
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      TZ: ${TZ:-Asia/Shanghai}
      # Database (DATABASE_URL takes priority; DB_* for fallback/backup_service)
      DATABASE_URL: ${DATABASE_URL}
      DB_HOST: ${DB_HOST:-postgres}
      DB_PORT: ${DB_PORT:-5432}
      DB_USER: ${DB_USER:-tam_admin}
      DB_PASSWORD: ${DB_PASSWORD}
      DB_NAME: ${DB_NAME:-tam_db}
      # Redis
      REDIS_URL: ${REDIS_URL}
      REDIS_PASSWORD: ${REDIS_PASSWORD}
      # Security
      SECRET_KEY: "${SECRET_KEY:?ERROR: SECRET_KEY must be set in .env}"
      ENCRYPTION_KEY: "${ENCRYPTION_KEY:-}"
      ALGORITHM: ${ALGORITHM:-HS256}
      ACCESS_TOKEN_EXPIRE_MINUTES: ${ACCESS_TOKEN_EXPIRE_MINUTES:-30}
      REFRESH_TOKEN_EXPIRE_DAYS: ${REFRESH_TOKEN_EXPIRE_DAYS:-7}
      # Lockout / CAPTCHA
      MAX_LOGIN_ATTEMPTS: ${MAX_LOGIN_ATTEMPTS:-5}
      LOCKOUT_DURATION_MINUTES: ${LOCKOUT_DURATION_MINUTES:-15}
      CAPTCHA_THRESHOLD: ${CAPTCHA_THRESHOLD:-3}
      # Registration / Rate limit
      ALLOW_REGISTRATION: ${ALLOW_REGISTRATION:-false}
      RATE_LIMIT_PER_MINUTE: ${RATE_LIMIT_PER_MINUTE:-60}
      AUTH_RATE_LIMIT_PER_MINUTE: ${AUTH_RATE_LIMIT_PER_MINUTE:-5}
      # Integrations: Sangfor
      SANGFOR_BASE_URL: ${SANGFOR_BASE_URL}
      SANGFOR_USERNAME: ${SANGFOR_USERNAME}
      SANGFOR_PASSWORD: ${SANGFOR_PASSWORD}
      SANGFOR_CA_BUNDLE: ${SANGFOR_CA_BUNDLE}
      # Integrations: Switch
      SWITCH_HOST: ${SWITCH_HOST}
      SWITCH_USERNAME: ${SWITCH_USERNAME}
      SWITCH_PASSWORD: ${SWITCH_PASSWORD}
      SWITCH_PORT: ${SWITCH_PORT:-23}
      # Integrations: IPGuard
      IPGUARD_HOST: ${IPGUARD_HOST}
      IPGUARD_USER: ${IPGUARD_USER}
      IPGUARD_PASSWORD: ${IPGUARD_PASSWORD}
      IPGUARD_DATABASE: ${IPGUARD_DATABASE:-OCULAR3}
      # CORS / Admin / Paths / Port
      BACKEND_CORS_ORIGINS: '${BACKEND_CORS_ORIGINS:-[]}'
      ADMIN_PASSWORD: "${ADMIN_PASSWORD:-}"
      UPLOAD_DIR: ${UPLOAD_DIR:-/app/uploads}
      BACKEND_PORT: ${TAM_BACKEND_PORT:-8000}
```

（覆盖 Settings 中所有与 `.env` 对应的字段，全部使用 `${VAR:-default}` 形式保持兼容性，未设值的集成项为空字符串）

### 3. backend.healthcheck — 使用 ${BACKEND\_PORT} 不再硬编码

**文件**: [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L116-L121)

改为 CMD-SHELL 形式以展开环境变量：

```yaml
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen(f'http://localhost:${BACKEND_PORT:-8000}/health')\""]
```

## 验证

1. `docker compose -p tam --env-file .env -f docker-compose.yml config` — 输出展开后的完整 yml，确认每个缺失变量都已正确展开且值与 `.env` 一致
2. 修改 `.env` 中 `TAM_BACKEND_PORT=8001` 重启 → `docker inspect tam_backend --format '{{.State.Health.Status}}'` 返回 healthy
3. 修改 `.env` 中 `LOG_LEVEL=DEBUG` 重启 → 后端日志显示 DEBUG 级别，证明变量生效
4. 修改 `.env` 中 `LOCKOUT_DURATION_MINUTES=99` 重启 → 通过后端 debug 端点或 settings API 确认值为 99
5. 最终 `./manage.sh health` 全绿

