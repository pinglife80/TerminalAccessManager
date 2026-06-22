# 部署体系评估报告

> 文档版本：v1.0  更新日期：2026-06-18

---

## 一、公共镜像版本锁定问题

### 1.1 现状分析

[docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml) 中使用了 3 个公共镜像：

| 服务 | 当前标签 | 行号 | 版本锁定情况 |
|------|---------|------|-------------|
| postgres | `postgres:15-alpine` | L3 | ✅ 已锁定主版本 15 |
| redis | `redis:7-alpine` | L54 | ✅ 已锁定主版本 7 |
| nginx | `nginx:alpine` | L167 | ❌ **未锁定版本** |

[frontend/Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/Dockerfile) L2: `FROM node:18-alpine` — ✅ 已锁定

[backend/Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile) L2: `FROM python:3.11-alpine` — ✅ 已锁定

### 1.2 风险评估

**`nginx:alpine` 是唯一未锁定版本的公共镜像**，风险如下：

- **兼容性风险**: `alpine` 标签跟随 nginx 最新稳定版。若 nginx 从 1.x 升级到 2.x（虽然目前尚未发布），可能破坏现有配置指令（如 `listen`、`proxy_pass` 语法变更）
- **安全风险**: 每次拉取可能获取不同版本的 nginx，无法确保经过充分测试
- **不可复现**: 不同时间部署的相同代码可能使用不同版本的 nginx，行为不一致

**`postgres:15-alpine` 和 `redis:7-alpine`** 虽然锁定了主版本，但小版本仍可能变化（如 15.2→15.8），不过这类更新通常是向后兼容的 bugfix/安全补丁，风险较低。

### 1.3 建议

| 镜像 | 建议标签 | 理由 |
|------|---------|------|
| nginx | `nginx:1.27-alpine` | 锁定 1.27.x 主版本，alpine 变体内的小版本更新安全 |
| postgres | `postgres:15-alpine` | 维持现状，15.x 小版本兼容 |
| redis | `redis:7-alpine` | 维持现状，7.x 小版本兼容 |

**不建议锁定到完整版本号**（如 `nginx:1.27.4-alpine`），因为：
1. 过于严格会阻碍安全补丁自动获取
2. 需要频繁手动更新版本号，维护成本高
3. Alpine 变体的补丁版本更新频率极高

---

## 二、本地构建镜像版本标签问题

### 2.1 现状分析

[docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml) 中 backend 和 frontend 使用 `build:` 而非 `image:`，构建后默认标签为 `tam-backend:latest` 和 `tam-frontend:latest`。

当前项目版本为 `3.3.1`（[.env.example](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/.env.example) L14），但镜像标签始终是 `latest`。

### 2.2 风险评估

**风险较低**，原因：

1. **单机部署场景**: 项目使用 `docker compose` 单机部署，不涉及镜像仓库推送/拉取，`latest` 标签在本地构建场景下不会造成版本混淆
2. **每次 build 都会重建**: `dc build` 会基于当前代码重新构建，`latest` 始终指向最新构建
3. **无多版本共存需求**: 不存在同时运行 v3.2 和 v3.3 的场景

**潜在问题**：

1. **回滚困难**: 升级后旧镜像被新镜像覆盖（同为 `latest`），若需回滚到上一版本，必须重新 `dc build` 旧代码
2. **审计不友好**: `docker images` 中只有 `latest` 标签，无法直观判断当前运行的镜像对应哪个版本
3. **CI/CD 集成**: 若未来引入 CI/CD 流水线，`latest` 标签不利于版本追踪

### 2.3 建议

**推荐方案**: 在 `docker-compose.yml` 中为本地构建服务添加 `image:` 标签，包含项目版本号：

```yaml
backend:
  build: ./backend
  image: tam-backend:${VERSION:-latest}
```

这样：
- `dc build` 构建的镜像会打上 `tam-backend:3.3.1` 标签
- 旧版本镜像不会被覆盖，回滚时可直接 `dc up -d` 指定旧镜像
- `VERSION` 变量来自 `.env` 文件，与项目版本保持一致

**不推荐方案**: 在 Dockerfile 中硬编码版本号（需每次手动更新，维护成本高）。

---

## 三、.env 环境变量配置审查

### 3.1 过时参数

| 变量 | 位置 | 问题 | 建议 |
|------|------|------|------|
| `PROJECT_NAME` | .env.example L12 | 值为 `Terminal Access Platform`，但项目已更名为 `Terminal Access Manager` | 更新为 `Terminal Access Manager` |
| `APP_NAME` 等 branding 变量 | .env.example L170-178 | 已全部注释掉，且后端 `_get_env_default()` 不映射这些键，**完全无效** | 删除这些注释行，避免误导用户 |
| `API_V1_STR` | .env.example L16 | 值为 `/api/v1`，硬编码在代码中，修改此变量不会生效（代码中直接使用字符串常量） | 标注为只读或移除 |
| `ALGORITHM` | .env.example L61 | 值为 `HS256`，硬编码在代码中，修改此变量不会生效 | 标注为只读或移除 |

### 3.2 遗漏参数

| 变量 | 说明 | 当前状态 |
|------|------|---------|
| `TZ` | 时区设置 | docker-compose.yml 中有 `${TZ:-Asia/Shanghai}` 默认值，但 .env.example 中未列出 | 建议添加 |
| `TAM_LOG_ENABLED` | manage.sh 日志开关 | manage.sh 读取此变量，但 .env.example 中未列出 | 建议添加 |
| `COMPOSE_PROJECT_NAME` | Docker Compose 项目名 | manage.sh L77 硬编码为 `tam`，但 .env.example 中未列出 | 建议添加 |

### 3.3 不匹配参数

| 变量 | .env.example 值 | 代码实际使用 | 问题 |
|------|-----------------|-------------|------|
| `AUTH_RATE_LIMIT_PER_MINUTE` | `5` | Nginx 配置中开发环境 `30r/m`，生产环境 `10r/m` | .env 默认值与 Nginx 配置不一致，且此变量似乎未被后端代码使用（限流由 Nginx 实现） |
| `RATE_LIMIT_PER_MINUTE` | `60` | Nginx 配置中开发环境 `120r/m`，生产环境 `60r/m` | 同上 |
| `DATABASE_URL` | 包含明文密码 | 后端代码中通过 `DB_HOST/PORT/USER/PASSWORD/NAME` 组合构建连接串 | `DATABASE_URL` 与独立 DB_* 变量功能重复，可能造成混淆 |

### 3.4 安全相关参数

| 变量 | 默认值 | 风险 |
|------|--------|------|
| `SECRET_KEY` | `change-this-to-a-random-secret-key-in-production` | manage.sh 的 `check_weak_defaults()` 会检测并阻止生产部署，**已受保护** |
| `ENCRYPTION_KEY` | `change-this-to-unique-encryption-key` | 同上 |
| `ADMIN_PASSWORD` | 开发环境硬编码 `Admin123` | 仅限开发环境，生产环境需手动设置 |

### 3.5 建议

1. **删除** .env.example 中已注释的 branding 变量（L170-178），避免误导
2. **更新** `PROJECT_NAME` 为 `Terminal Access Manager`
3. **添加** `TZ`、`TAM_LOG_ENABLED`、`COMPOSE_PROJECT_NAME` 到 .env.example
4. **标注** `API_V1_STR` 和 `ALGORITHM` 为只读/不建议修改
5. **统一** `AUTH_RATE_LIMIT_PER_MINUTE` 和 `RATE_LIMIT_PER_MINUTE` 的默认值与 Nginx 配置一致，或明确说明这些变量仅影响后端应用层限流（与 Nginx 层限流独立）

---

## 四、开发/生产环境变量文件分离

### 4.1 现状分析

当前架构：
- **单一 .env 文件**: 通过 `ENVIRONMENT=development|production` 变量区分环境
- **docker-compose 覆盖**: `docker-compose.dev.yml`（仅替换 nginx 配置）和 `docker-compose.prod.yml`（安全加固）
- **manage.sh 区分**: `_configure_dev_env()` 自动生成密码，`_configure_production_wizard()` 手动配置

### 4.2 风险评估

**当前方案的风险**：

1. **误操作风险**: 用户可能忘记修改 `ENVIRONMENT` 变量，导致生产环境使用开发配置（如 `DEBUG=false` 未设置、弱密码等）
2. **配置漂移**: 开发和生产使用同一个 .env 文件，修改开发配置时可能意外影响生产
3. **部署流程耦合**: `manage.sh deploy --dev` 和 `deploy --prod` 都写入同一个 .env，切换环境时需要重新部署

**但当前方案也有优势**：

1. **简单性**: 单一 .env 文件管理简单，不需要维护多套配置
2. **manage.sh 保护**: `check_weak_defaults()` 会阻止生产环境使用弱默认值
3. **单机部署**: 项目是单机部署，不存在多环境同时运行的需求

### 4.3 建议

**推荐方案: .env + .env.override 模式**

```
.env.example     # 模板（所有变量 + 注释）
.env             # 共享基础配置（PROJECT_NAME, VERSION, DB_HOST 等）
.env.dev         # 开发环境覆盖（ENVIRONMENT=development, DEBUG=true, 弱密码）
.env.prod        # 生产环境覆盖（ENVIRONMENT=production, DEBUG=false, 强密码）
```

docker-compose.yml 中使用：
```yaml
env_file:
  - .env
  - .env.${ENVIRONMENT:-development}
```

**优势**:
- 共享配置只需维护一份
- 环境差异配置独立管理
- 避免误操作（生产密码不会出现在开发配置中）

**不推荐方案**: 完全分离为 .env.dev 和 .env.prod（维护成本高，共享配置需同步更新）

**实施优先级**: 低。当前 manage.sh 的保护机制已足够安全，分离方案是锦上添花。

---

## 五、品牌自定义设置的升级保护

### 5.1 现状分析

品牌设置存储在两个位置：

| 存储位置 | 内容 | 持久性 | 升级影响 |
|---------|------|--------|---------|
| PostgreSQL `system_config` 表 | 文本配置（app_name, login_heading 等 11 个键） | ✅ 持久化（postgres_data volume） | **安全** — 升级不触碰数据 |
| `/app/uploads/` 目录 | 上传的资源文件（logo, 背景图, favicon） | ❌ **tmpfs** — 容器重启即丢失 | **危险** — 升级后资源丢失 |

### 5.2 关键发现

**文本配置安全**: `seed_defaults()` 是幂等操作（[config_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/config_service.py) L175-197），只插入数据库中不存在的键，不会覆盖已有值。因此升级后文本配置（如自定义的 app_name）**不会被覆盖**。

**上传资源危险**: `/app/uploads` 在 [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml) L129-131 中配置为 `tmpfs`：
```yaml
tmpfs:
  - /tmp
  - /app/uploads
```
这意味着**每次容器重启**（包括 `dc up -d`、`dc restart`、`manage.sh update`、`manage.sh upgrade`），上传的品牌资源都会丢失。数据库中仍保留 `login_bg_url` 和 `favicon_url` 的 URL 值，但对应的文件已不存在，导致 404。

**这是一个已存在的严重 bug**，不仅影响升级，还影响任何容器重启操作。

### 5.3 修复建议

**方案 A: 将 uploads 目录改为命名卷（推荐）**

docker-compose.yml:
```yaml
backend:
  volumes:
    - upload_data:/app/uploads  # 替代 tmpfs

volumes:
  upload_data:
```

docker-compose.prod.yml 中添加:
```yaml
backend:
  tmpfs:
    - /tmp  # 保留 /tmp 为 tmpfs
  volumes:
    - upload_data:/app/uploads  # uploads 使用持久卷
```

**优势**: 数据持久化，升级/重启不丢失，生产环境安全
**劣势**: 需要额外管理一个 volume，`read_only: true` 需要调整

**方案 B: 使用宿主机绑定挂载**

```yaml
backend:
  volumes:
    - ./uploads:/app/uploads
```

**优势**: 文件直接在宿主机可见，便于备份
**劣势**: 需要管理宿主机目录权限

### 5.4 升级流程补充建议

即使修复了 uploads 持久化问题，建议在 `cmd_upgrade` 中增加品牌设置保护提示：

1. 升级前自动备份 uploads 目录
2. 升级后验证品牌资源文件是否存在
3. 若资源丢失，提示用户重新上传

---

## 六、manage.sh 与 docker compose 操作一致性

### 6.1 现状分析

manage.sh 的 `dc()` 函数是对 `docker compose` 的封装：

```bash
dc() {
    local compose_files="-f ${SCRIPT_DIR}/docker-compose.yml"
    local env_mode
    env_mode=$(get_env "ENVIRONMENT" 2>/dev/null || echo "")
    if [ "${env_mode}" = "production" ] || [ "${env_mode}" = "prod" ]; then
        compose_files="${compose_files} -f ${SCRIPT_DIR}/docker-compose.prod.yml"
    elif [ "${env_mode}" = "development" ] || [ "${env_mode}" = "dev" ]; then
        compose_files="${compose_files} -f ${SCRIPT_DIR}/docker-compose.dev.yml"
    fi
    docker compose --env-file "${ENV_FILE}" ${compose_files} "$@"
}
```

### 6.2 一致性分析

| 操作 | manage.sh 行为 | 原始 docker compose | 差异 |
|------|---------------|-------------------|------|
| `start` | `dc up -d` | `docker compose up -d` | ✅ 等价（dc 自动选择 compose 文件） |
| `stop` | `dc down` | `docker compose down` | ⚠️ **不等价** — `dc down` 会停止并删除容器和网络，而 `docker compose stop` 仅停止不删除 |
| `restart` | `dc restart` | `docker compose restart` | ✅ 等价 |
| `update` | `dc build && dc up -d` | `docker compose up -d --build` | ✅ 等价（修改后拆分为两步） |
| `logs` | `dc logs` | `docker compose logs` | ✅ 等价 |
| `clean` | `dc down -v --rmi all` | `docker compose down -v --rmi all` | ✅ 等价 |

### 6.3 关键差异

**`stop` vs `down` 问题**:

[manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh) 的 `cmd_stop()` 使用 `dc down`，这会：
- 停止所有容器
- **删除所有容器**
- **删除网络**
- 但**保留 volumes**（未加 `-v`）

而用户预期的 `stop` 行为通常是 `docker compose stop`：
- 停止所有容器
- **保留容器**（状态为 Exited）
- **保留网络**

`dc down` 后再 `dc up -d` 会**重新创建容器**，而非启动已停止的容器。这意味着：
1. tmpfs 数据会丢失（如 /app/uploads）
2. 容器 ID 会变化
3. 启动时间更长（需要重新创建）

### 6.4 建议

1. **`cmd_stop()` 改用 `dc stop`** 而非 `dc down`，保持与 docker compose stop 语义一致
2. 新增 `cmd_down()` 命令用于完全销毁（当前 `stop` 的行为），供需要完全清理的场景使用
3. 或在 `cmd_stop()` 中提供 `--down` 选项，默认使用 `stop` 行为

---

## 七、manage.sh 操作日志记录

### 7.1 现状分析

manage.sh **已具备日志记录功能**，但**默认关闭**：

| 特性 | 状态 | 位置 |
|------|------|------|
| 日志写入文件 | ✅ 已实现 | [L102-113](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L102) |
| 日志级别（INFO/OK/WARN/ERROR/DEBUG/STEP） | ✅ 已实现 | [L122-127](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L122) |
| 自动清理（30天） | ✅ 已实现 | [L116-120](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L116) |
| 按日期分文件 | ✅ 已实现 | [L108](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L108) `manage_YYYYMMDD.log` |
| 命令执行记录 | ✅ 已实现 | [L3958](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L3958) `_log_to_file "CMD" "Command: $command $*"` |
| **默认启用** | ❌ **默认关闭** | 需要设置 `TAM_LOG_ENABLED=true` 或使用 `--log` 参数 |

### 7.2 问题

1. **默认关闭**: 大多数用户不会主动开启日志，导致操作无记录可查
2. **关键操作无强制日志**: backup/restore/upgrade/migrate 等关键操作应强制记录，无论日志开关是否开启
3. **日志内容不完整**: 当前仅记录 log 函数的输出，不记录：
   - 命令执行结果（成功/失败/退出码）
   - 操作耗时
   - 影响范围（如备份文件路径、恢复的数据库大小）
4. **日志与审计脱节**: manage.sh 的日志与后端审计日志（audit_logs 表）独立，无法关联

### 7.3 建议

1. **关键操作强制记录**: 无论 `TAM_LOG_ENABLED` 是否开启，backup/restore/upgrade/migrate/clean 操作都应写入日志
2. **增强日志内容**: 记录操作结果、耗时、影响范围
3. **考虑默认开启**: 生产环境建议默认开启日志（`deploy --prod` 时自动设置 `TAM_LOG_ENABLED=true`）
4. **操作结果记录**: 在 `main()` 的 EXIT trap 中记录命令退出码

---

## 八、综合评估总结

| 问题 | 严重度 | 当前风险 | 修复优先级 |
|------|--------|---------|-----------|
| 1. nginx:alpine 未锁定版本 | 中 | 潜在兼容性问题 | P2 |
| 2. 本地构建镜像无版本标签 | 低 | 单机部署影响小 | P3 |
| 3. .env 中过时/遗漏参数 | 中 | 误导用户、配置不一致 | P2 |
| 4. 开发/生产环境变量未分离 | 低 | manage.sh 有保护机制 | P3 |
| 5. uploads 目录 tmpfs 导致品牌资源丢失 | **高** | **每次容器重启丢失上传资源** | **P0** |
| 6. stop 使用 down 语义不一致 | 中 | 用户预期不符、tmpfs 数据丢失 | P1 |
| 7. 日志默认关闭 | 低 | 操作无记录可查 | P2 |

**最严重问题**: #5 — `/app/uploads` 使用 tmpfs，上传的品牌资源（logo、背景图、favicon）在**任何容器重启**后都会丢失，不仅是升级场景。这是功能性 bug，需立即修复。
