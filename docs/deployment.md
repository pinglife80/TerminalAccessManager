# TerminalAccessManager - 部署与运维手册

## 目录

- [1. 环境要求](#1-环境要求)
- [2. 快速开始（一键部署）](#2-快速开始一键部署)
- [3. 生产环境部署](#3-生产环境部署)
- [4. 命令参考手册](#4-命令参考手册)
- [5. 典型运维场景](#5-典型运维场景)
- [6. 故障排查](#6-故障排查)
- [7. 架构说明](#7-架构说明)

---

## 1. 环境要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Docker | 20.10+ | 容器运行时 |
| Docker Compose | v2.0+ | 服务编排（`docker compose` 命令） |
| 磁盘空间 | 5GB+ | 镜像 + 数据卷 |
| 内存 | 2GB+ | 推荐 4GB |
| OpenSSL | 任意 | 生成 SSL 证书 |

**端口占用：**

| 端口 | 用途 |
|------|------|
| 8080 | HTTP（自动重定向到 HTTPS） |
| 8443 | HTTPS（Web 管理界面） |

> 其他服务端口（PostgreSQL 5432、Redis 6379、Backend 8000）不对外暴露，仅通过 Nginx 代理访问。

---

## 2. 快速开始（一键部署）

### 2.1 克隆项目

```bash
git clone https://github.com/pinglife80/TerminalAccessManager.git
cd TerminalAccessManager
```

### 2.2 一键 Demo 部署

```bash
chmod +x manage.sh
./manage.sh deploy --demo
```

这将自动完成：
1. 检查系统前提条件
2. 生成 SSL 自签名证书
3. 自动生成数据库密码、Redis 密码、JWT 密钥
4. 构建并启动所有 Docker 服务
5. 初始化数据库和 admin 用户
6. 生成演示数据（50 个终端、15 个白名单、10 个黑名单、100 条审计日志）

### 2.3 访问系统

部署完成后：

- **HTTPS**: `https://<HOST_IP>:8443`
- **HTTP**: `http://<HOST_IP>:8080`（自动重定向到 HTTPS）
- **登录账号**: admin / Admin123

> `<HOST_IP>` 为实际部署主机 IP 地址。本机部署时使用 `localhost`。

> Demo 环境仅用于评估和测试，不适合生产使用。

---

## 3. 生产环境部署

### 3.1 交互式向导部署

```bash
./manage.sh deploy --prod
```

向导将引导你配置：

1. **数据库密码** — 至少 8 位，建议使用强密码
2. **Redis 密码** — 缓存服务密码
3. **JWT 密钥** — 自动生成 64 位随机密钥
4. **Sangfor API**（可选） — API 地址、用户名、密码
5. **网络交换机**（可选） — 交换机 IP、用户名、密码

### 3.2 已有配置文件部署

如果 `.env` 已存在，使用 `-y` 标志跳过交互：

```bash
./manage.sh -y deploy --prod
```

### 3.3 手动配置

也可以先编辑 `.env`，再部署：

```bash
cp .env.example .env
vim .env                          # 编辑配置
./manage.sh -y deploy --prod     # 使用已有配置部署
```

### 3.4 配置项说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `DB_USER` | 是 | 数据库用户名（默认 tam_admin） |
| `DB_PASSWORD` | 是 | 数据库密码 |
| `REDIS_PASSWORD` | 是 | Redis 密码 |
| `SECRET_KEY` | 是 | JWT 签名密钥 |
| `SANGFOR_BASE_URL` | 否 | 深信服 API 地址 |
| `SANGFOR_USERNAME` | 否 | 深信服 API 用户名 |
| `SANGFOR_PASSWORD` | 否 | 深信服 API 密码 |
| `SWITCH_HOST` | 否 | 网络交换机 IP |
| `SWITCH_USERNAME` | 否 | 交换机用户名 |
| `SWITCH_PASSWORD` | 否 | 交换机密码 |

---

## 4. 命令参考手册

### 全局选项

| 选项 | 说明 |
|------|------|
| `-y, --yes` | 跳过所有确认提示（非交互模式） |
| `-v, --verbose` | 启用调试输出 |
| `-h, --help` | 显示帮助信息 |

### 4.1 生命周期命令

#### `deploy [--demo|--prod]`

完整部署，包含初始化向导。

```bash
./manage.sh deploy --demo        # Demo 模式（自动配置 + 示例数据）
./manage.sh deploy --prod        # 生产模式（交互式向导）
./manage.sh -y deploy --prod     # 生产模式（非交互，使用已有 .env）
```

#### `start`

启动所有服务（幂等 — 已运行则跳过）。

```bash
./manage.sh start
```

#### `stop`

停止所有服务（幂等 — 已停止则跳过）。

```bash
./manage.sh stop
```

#### `restart [service]`

重启服务。不指定服务名则重启全部。

```bash
./manage.sh restart              # 重启所有服务
./manage.sh restart backend      # 只重启后端
./manage.sh restart nginx        # 只重启 Nginx
```

#### `status`

查看服务状态和健康信息。

```bash
./manage.sh status
```

输出示例：
```
Service Health:
  ● PostgreSQL: healthy
  ● Redis: healthy
  ● Backend API: healthy
  ● Nginx Proxy: running

Web Access:
  ● https://<HOST_IP>:8443 (200 OK)

Deployment:
  Mode: demo
  Time: 2026-06-06T14:00:36+08:00
```

#### `health`

深度健康检查（8 项检查）。

```bash
./manage.sh health
```

检查项目：
1. Docker 守护进程
2. 服务容器状态（注意：frontend 容器 exited(0) 为正常状态，表示构建已完成；仅 exited(非0) 才表示构建失败）
3. 数据库连接
4. Redis 连接
5. 后端 API 可用性
6. Web UI 可达性
7. SSL 证书有效期
8. 磁盘空间

#### `update`

仅重建并重启服务（本地代码修改后使用）。不会拉取远程代码。

```bash
./manage.sh update
```

执行流程：
1. 自动备份数据库
2. 重建 Docker 镜像
3. 重启服务

> 适用于本地代码修改后重新部署的场景。如需从远程仓库拉取新版本代码，请使用 `upgrade` 命令。

#### `upgrade [version]`

从远程仓库拉取新版本代码并升级系统。

```bash
./manage.sh upgrade                    # 升级到当前分支最新版本
./manage.sh upgrade v1.2.0             # 升级到指定 tag
./manage.sh upgrade main               # 升级到指定分支最新
./manage.sh upgrade abc1234            # 升级到指定 commit
./manage.sh upgrade --check            # 仅检查可用更新，不执行升级
./manage.sh upgrade --skip-migrate     # 跳过数据库迁移（危险！）
```

**参数说明：**

| 参数 | 说明 |
|------|------|
| `[version]` | 目标版本（git tag/branch/commit），默认当前分支最新 |
| `--check` | 仅检查是否有可用更新，不执行升级 |
| `--skip-migrate` | 跳过数据库迁移步骤（**危险**，可能导致数据不一致） |

**前置检查：**

升级前会自动执行以下检查：
1. 当前目录是否为 git 仓库
2. 服务是否健康运行
3. 磁盘空间是否充足

**版本差异展示：**

升级前会显示当前 commit 与目标 commit 之间的差异：

```
升级版本差异：
  当前版本: abc1234 (2026-06-01)
  目标版本: def5678 (2026-06-08)
  提交数量: 12 个新提交
  变更文件: 34 个文件修改
```

> **⚠️ 升级警告**
>
> - 升级期间服务将**不可用**
> - 数据库迁移可能**不可逆**
> - 降级操作可能**不可行**
>
> 升级前**必须**：
> 1. 备份数据库（`./manage.sh backup`）
> 2. 备份 `.env` 配置文件
> 3. 确认服务健康（`./manage.sh health`）
>
> 升级前**建议**：
> 1. 提前通知所有用户服务将中断
> 2. 先在测试环境验证升级流程

**升级流程：**

1. 自动备份数据库
2. 拉取目标版本代码（`git fetch` + `git checkout`）
3. 重建 Docker 镜像
4. 重启服务
5. 自动执行数据库迁移
6. 迁移失败时自动回滚代码并重启（恢复到升级前状态）

> **自动数据迁移说明**：升级后后端启动时会自动迁移 `audit_logs` 表中的旧 action 值（如 `block_ip` → `block_terminal` 等统一命名）和 `system_config` 表中的旧品牌值（如 `Terminal Access Platform` → `Terminal Access Manager`），无需手动干预。

### 4.2 数据管理命令

#### `init`

初始化数据库和管理员用户（幂等 — 已初始化则跳过）。

```bash
./manage.sh init
```

#### `migrate [revision]`

执行数据库迁移（幂等操作 — 已是最新则跳过）。默认迁移到最新版本（head），可指定目标版本号。

```bash
./manage.sh migrate               # 迁移到最新版本
./manage.sh migrate head          # 同上，显式指定 head
./manage.sh migrate abc123        # 迁移到指定版本
```

执行时会显示迁移前后的数据库版本状态。执行前会显示迁移确认提示，说明迁移可能不可逆，建议先备份数据库。

#### `mock generate`

生成演示数据。

```bash
./manage.sh mock generate
```

生成内容：
- 5 个用户（含 admin）
- 50 个终端
- 15 个白名单条目
- 10 个黑名单条目
- 100 条审计日志

#### `mock clear`

清除所有演示数据（保留 admin 用户）。

```bash
./manage.sh mock clear           # 需要确认
./manage.sh -y mock clear        # 非交互模式
```

> 清除前会自动备份数据库。执行前会显示结构化警告框：
>
> ```
> ⚠️ 数据清除警告
> ─────────────────────────────
> 操作：清除所有演示数据
> 影响范围：
>   • 删除所有终端、白名单、黑名单、审计日志数据
>   • 保留 admin 用户
>   • 此操作不可逆
> ─────────────────────────────
> ```

#### `backup [file]`

备份数据库到 SQL 文件。

```bash
./manage.sh backup                                    # 自动生成文件名
./manage.sh backup /path/to/my_backup.sql             # 指定文件名
```

备份文件存储在 `backups/` 目录，自动保留最近 10 个备份。

#### `restore <file>`

从 SQL 文件恢复数据库。

```bash
./manage.sh restore backups/backup_20260606_140053.sql
```

> 恢复前会自动备份当前数据库。恢复过程会先清空目标数据库再导入。执行前会显示数据库恢复警告框：
>
> ```
> ⚠️ 数据库恢复警告
> ─────────────────────────────
> 操作：从备份文件恢复数据库
> 影响范围：
>   • 当前数据库数据将被替换为备份数据
>   • 所有活跃会话将被终止
>   • 此操作不可逆
> ─────────────────────────────
> ```

### 4.3 开发命令

#### `test`

运行后端测试套件。

```bash
./manage.sh test
```

如果服务未运行，会自动启动。

#### `shell [backend|db|redis]`

进入服务容器的交互式 Shell。

```bash
./manage.sh shell backend         # 后端 Shell (sh)
./manage.sh shell db              # PostgreSQL Shell (psql)
./manage.sh shell redis           # Redis CLI
# 简写
./manage.sh shell b               # = backend
./manage.sh shell p               # = db (postgres)
./manage.sh shell r               # = redis
```

#### `logs [service] [-n N]`

查看服务日志（实时跟踪模式）。

```bash
./manage.sh logs                  # 所有服务日志
./manage.sh logs backend          # 只看后端日志
./manage.sh logs backend -n 50    # 后端最近 50 行
./manage.sh logs nginx -n 200     # Nginx 最近 200 行
```

按 `Ctrl+C` 退出日志跟踪。

#### `validate`

运行项目验证检查。

```bash
./manage.sh validate
```

检查内容：文件结构、Python 语法、配置完整性、安全验证、API 端点、Docker 配置。

### 4.4 工具命令

#### `redis info`

显示 Redis 服务器信息，包括版本、内存使用和键空间统计。

```bash
./manage.sh redis info
```

#### `redis keys [pattern]`

列出匹配的 Redis 键，显示键的类型和 TTL。默认匹配所有键（`*`）。

```bash
./manage.sh redis keys              # 列出所有键
./manage.sh redis keys "session:*"  # 按模式匹配
```

#### `redis get <key>`

获取 Redis 键的值。支持 string、hash、list、set、zset 类型，自动识别并格式化输出。

```bash
./manage.sh redis get mykey
```

#### `redis del <key>`

删除 Redis 键。需要确认，使用 `-y` 跳过确认。

```bash
./manage.sh redis del mykey         # 需要确认
./manage.sh -y redis del mykey      # 非交互模式
```

> 执行前会显示键删除影响说明，根据键名前缀自动识别影响范围：
> - `scheduler:ctrl:{task}` — 调度器控制键，删除后任务将恢复/失去控制
> - `session:*` / `rate_limit:*` — 缓存/会话键，删除后用户需重新登录或限速重置
> - 其他键 — 通用缓存数据，删除后可能触发缓存重建

#### `redis flush [db]`

清空 Redis 数据库。默认清空 db 0，需要确认。

```bash
./manage.sh redis flush             # 清空 db 0（需要确认）
./manage.sh redis flush 1           # 清空 db 1
./manage.sh -y redis flush          # 非交互模式
```

> **危险操作**：会删除指定数据库中的所有数据，不可恢复！执行前会显示清空警告框：
>
> ```
> ⚠️ Redis 清空警告
> ─────────────────────────────
> 操作：清空 Redis 数据库
> 影响范围：
>   • 所有活跃会话将被终止，用户需重新登录
>   • 限速计数器将被重置
>   • 调度器控制键将被清除，暂停中的任务将恢复运行
>   • 缓存数据将被清除，后续请求将触发缓存重建
> ─────────────────────────────
> ```

#### `scheduler status`

显示定时任务运行状态和执行间隔。

```bash
./manage.sh scheduler status
```

#### `scheduler pause <task>`

暂停指定定时任务。通过在 Redis 中设置键 `scheduler:ctrl:{task}` 来控制，任务循环中通过 `_is_task_paused()` 检查该键，暂停机制真正生效 — 被暂停的任务在循环中会被跳过，不会执行。

```bash
./manage.sh scheduler pause arp_collection
```

#### `scheduler resume <task>`

恢复已暂停的定时任务。删除 Redis 键 `scheduler:ctrl:{task}`，任务循环中 `_is_task_paused()` 检测到键不存在后恢复执行。

```bash
./manage.sh scheduler resume arp_collection
```

#### `scheduler trigger <task>`

手动触发一次定时任务执行。

```bash
./manage.sh scheduler trigger compliance_check
```

#### `scheduler intervals`

显示所有配置的定时任务间隔。

```bash
./manage.sh scheduler intervals
```

可用任务名：`arp_collection`、`ipguard_sync`、`firewall_query`、`compliance_check`、`auto_unblock`。

#### `config [key] [value]`

查看或修改配置。

```bash
./manage.sh config                         # 查看所有配置
./manage.sh config DB_USER                 # 查看单个配置
./manage.sh config DB_PASSWORD newpass123  # 修改配置
```

> 敏感信息（密码、密钥）自动脱敏显示。修改后需 `./manage.sh restart` 生效。
>
> 修改配置时，执行前会显示新旧值对比：
>
> ```
> 配置变更确认：
> ─────────────────────────────
> 配置项：DB_PASSWORD
> 旧值：  ****1234
> 新值：  newpass123
> ─────────────────────────────
> ```
>
> 以下安全类配置修改时需二次确认：
> - `lockout_threshold` — 账户锁定阈值
> - `lockout_duration` — 账户锁定时长
> - `captcha_required` — 验证码开关
> - `max_login_attempts` — 最大登录尝试次数
> - `rate_limit` — 限速配置

#### `ssl [--force]`

管理 SSL 证书（幂等 — 有效证书存在则跳过）。

```bash
./manage.sh ssl              # 仅在证书不存在/过期时生成
./manage.sh ssl --force      # 强制重新生成
```

证书有效期 10 年，存储在 `nginx/certs/` 目录。如果 Nginx 正在运行，会自动 reload。

#### `clean`

清理所有容器、镜像、数据卷和部署状态。

```bash
./manage.sh clean            # 需要确认
./manage.sh -y clean         # 非交互模式
```

> **危险操作**：会删除所有数据，不可恢复！

#### `version`

显示版本和系统信息。

```bash
./manage.sh version
```

---

## 5. 典型运维场景

### 场景 1：首次部署到生产服务器

```bash
# 1. 克隆项目
git clone https://github.com/pinglife80/TerminalAccessManager.git && cd TerminalAccessManager

# 2. 执行生产部署向导
./manage.sh deploy --prod

# 3. 验证部署
./manage.sh health

# 4. 访问系统并修改默认密码
# https://<HOST_IP>:8443
```

### 场景 2：代码更新后重新部署

**本地代码修改后重新部署**（不拉取远程代码）：

```bash
./manage.sh update
```

自动完成：备份数据库 → 重建镜像 → 重启服务。

**从远程仓库升级到新版本**：

```bash
# 先检查可用更新
./manage.sh upgrade --check

# 备份数据库
./manage.sh backup

# 执行升级（自动拉取代码 + 重建 + 迁移）
./manage.sh upgrade v1.2.0
```

### 场景 3：数据库备份与恢复

```bash
# 备份
./manage.sh backup

# 查看可用备份
ls -lh backups/

# 恢复（会自动备份当前数据）
./manage.sh restore backups/backup_20260606_140053.sql
```

### 场景 4：查看后端日志排查问题

```bash
./manage.sh logs backend -n 100    # 查看最近 100 行
./manage.sh logs postgres          # 查看数据库日志
```

### 场景 5：修改配置后重启

```bash
# 修改 Redis 密码
./manage.sh config REDIS_PASSWORD new_redis_pass

# 重启服务使配置生效
./manage.sh restart
```

### 场景 6：完全重新部署

```bash
./manage.sh -y clean              # 清理所有
./manage.sh deploy --prod         # 重新部署
```

### 场景 7：生成演示数据用于测试

```bash
./manage.sh mock generate          # 生成数据
# ... 测试操作 ...
./manage.sh -y mock clear          # 清除数据
```

### 场景 8：SSL 证书即将过期

```bash
./manage.sh ssl --force            # 强制重新生成
```

### 场景 9：CI/CD 自动化部署

```bash
./manage.sh -y deploy --prod       # 非交互模式
./manage.sh health                 # 健康检查
```

---

## 6. 故障排查

### 服务无法启动

```bash
# 1. 查看服务状态
./manage.sh status

# 2. 查看详细日志
./manage.sh logs backend

# 3. 深度健康检查
./manage.sh health
```

### 数据库连接失败

```bash
# 检查数据库是否就绪
./manage.sh shell db -c "SELECT 1;"

# 重启数据库
./manage.sh restart postgres
```

### Web 界面无法访问

```bash
# 1. 检查端口占用
ss -tlnp | grep -E '8080|8443'

# 2. 检查 Nginx 日志
./manage.sh logs nginx

# 3. 检查 SSL 证书
./manage.sh ssl
```

### 前端页面空白

```bash
# 前端构建容器可能未完成，重启 Nginx
./manage.sh restart nginx
```

### 清理并重新部署

```bash
./manage.sh -y clean
./manage.sh deploy --demo
```

---

## 7. 架构说明

### 服务拓扑

```
                    ┌──────────────┐
                    │   Internet   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │    Nginx     │ :8080→80, :8443→443
                    │  (反向代理)   │
                    └──┬───────┬───┘
                       │       │
              ┌────────▼┐  ┌──▼────────┐
              │ Frontend │  │  Backend  │
              │ (构建产物) │  │  (FastAPI) │
              └─────────┘  └──┬─────┬──┘
                              │     │
                    ┌─────────▼┐ ┌─▼────────┐
                    │ PostgreSQL│ │  Redis   │
                    │  (数据库)  │ │ (缓存)    │
                    └──────────┘ └──────────┘
```

### 端口映射

| 对外端口 | 容器端口 | 服务 | 说明 |
|---------|---------|------|------|
| 8080 | 80 | Nginx | HTTP（重定向到 HTTPS） |
| 8443 | 443 | Nginx | HTTPS |
| - | 5432 | PostgreSQL | 仅内部网络 |
| - | 6379 | Redis | 仅内部网络 |
| - | 8000 | Backend | 仅内部网络 |

### 数据卷

| 卷名 | 用途 |
|------|------|
| `postgres_data` | PostgreSQL 数据持久化 |
| `redis_data` | Redis 数据持久化 |
| `frontend_dist` | 前端构建产物共享 |

### 部署状态

部署状态存储在 `.manage/state.env`，用于幂等性控制：

| 状态键 | 说明 |
|--------|------|
| `deployed` | 是否已部署 |
| `deploy_mode` | 部署模式（demo/prod） |
| `deploy_time` | 部署时间 |
| `db_initialized` | 数据库是否已初始化 |
