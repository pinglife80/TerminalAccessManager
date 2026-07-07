# manage.sh 命令行操作手册

> 文档版本：v3.6.6  更新日期：2026-07-08

TerminalAccessManager (TAM) 统一管理脚本，用于项目全生命周期管理。

## 全局选项

| 选项 | 说明 |
|------|------|
| `-y, --yes` | 跳过所有确认提示（非交互模式） |
| `-v, --verbose` | 启用详细/调试输出 |
| `--log` | 启用操作日志记录（本次命令生效） |
| `-h, --help` | 显示帮助信息 |

**`--log` 操作日志详情：**
- 日志写入 `.manage/logs/manage_YYYYMMDD.log`
- 也可通过 `.env` 中设置 `TAM_LOG_ENABLED=true` 全局启用
- 日志格式：`[YYYY-MM-DD HH:MM:SS] [LEVEL] [COMMAND] Message`
- 自动清理：保留最近 30 天日志

**示例：**
```bash
./manage.sh --log backup          # 本次备份操作记录日志
./manage.sh --log config set app_name MyApp  # 本次配置修改记录日志
```

---

## 风险等级说明

| 标记 | 含义 |
|------|------|
| 🟢 **安全** | 只读操作或幂等操作，无副作用 |
| 🟡 **注意** | 需要关注但不会造成数据丢失 |
| 🔴 **高危** | 可能导致数据丢失或服务中断，执行前需仔细确认 |

---

## 一、生命周期命令

### 1.1 deploy — 全量部署

**风险等级：** 🟡 注意

**应用场景：** 首次部署或重新部署整个系统

**命令格式：**
```bash
./manage.sh deploy [--dev|--prod]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `--dev` | 开发模式：自动配置 + 生成样例数据，自动设置 `ENVIRONMENT=development` |
| `--prod` | 生产模式：手动配置向导，自动设置 `ENVIRONMENT=production` |
| `--demo` | ⚠ 已弃用，重定向到 `--dev` |

> **环境变量自动设置：** `deploy --dev` 自动在 `.env` 中设置 `ENVIRONMENT=development`，`deploy --prod` 自动设置 `ENVIRONMENT=production`。该变量影响 `mock generate`、`dc()` 等命令的行为。

**执行效果：**
1. 检查前置条件（Docker、磁盘空间、端口）
2. `_check_required_env` 函数：启动前检查 `DB_PASSWORD`、`REDIS_PASSWORD`、`SECRET_KEY` 是否已设置，缺失则中止部署
3. 生成 SSL 证书
4. 配置环境变量（.env）
5. 生产向导（`--prod`）和开发模式（`--dev`）自动生成 `ENCRYPTION_KEY`（Fernet 密钥），用于敏感数据加密
6. 构建并启动所有服务
7. 初始化数据库和管理员账户
8. 开发模式下自动生成 Mock 数据

**示例：**
```bash
./manage.sh deploy --dev           # 开发模式部署（含样例数据）
./manage.sh deploy --prod          # 生产部署（交互式向导）
./manage.sh deploy --demo          # 已弃用，等同于 --dev
./manage.sh -y deploy --prod       # 非交互式生产部署
```

---

### 1.2 start — 启动服务

**风险等级：** 🟢 安全

**应用场景：** 启动已部署的系统

**命令格式：**
```bash
./manage.sh start
```

**执行效果：** 按依赖顺序启动 PostgreSQL → Redis → Backend → Frontend → Nginx。幂等操作，已运行的服务不会被重启。

---

### 1.3 stop — 停止服务

**风险等级：** 🟡 注意

**应用场景：** 临时停止系统（数据保留）

**命令格式：**
```bash
./manage.sh stop
```

**执行效果：** 按反向依赖顺序停止所有服务。数据库数据持久化保留在 Docker 卷中。

---

### 1.4 restart — 重启服务

**风险等级：** 🟡 注意

**应用场景：** 配置变更后重启，或服务异常时重启

**命令格式：**
```bash
./manage.sh restart [service]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `(无)` | 重启所有服务 |
| `backend` | 仅重启后端 |
| `postgres` | 仅重启数据库 |
| `redis` | 仅重启缓存 |
| `nginx` | 仅重启代理 |

**示例：**
```bash
./manage.sh restart              # 重启所有服务
./manage.sh restart backend      # 仅重启后端
```

---

### 1.5 status — 服务状态

**风险等级：** 🟢 安全

**应用场景：** 查看当前服务运行状态

**命令格式：**
```bash
./manage.sh status
```

**执行效果：** 显示所有服务运行状态、健康检查结果、Web 访问地址和部署信息。

---

### 1.6 health — 深度健康检查

**风险等级：** 🟢 安全

**应用场景：** 全面检查系统各组件健康状况

**命令格式：**
```bash
./manage.sh health
```

**检查项目：** Docker 守护进程、服务容器状态（frontend 容器 exited(0) 显示为 [OK] "build complete (exited)"，属正常状态；仅 exited(非0) 才显示为 [ERROR]）、数据库连接、Redis 连接、后端 API、Web UI、SSL 证书、磁盘空间。

---

### 1.7 update — 重建并重启（本地代码）

**风险等级：** 🟡 注意

**应用场景：** 本地代码修改后，重新构建并重启服务。**不会拉取远程代码。**

**命令格式：**
```bash
./manage.sh update
```

**执行效果：**
1. 自动备份数据库
2. 重新构建 Docker 镜像（使用当前本地代码）
3. 重启所有服务

**影响范围：** 服务在重建期间短暂不可用（通常 10-30 秒）

---

### 1.8 rebuild — 重建指定服务

**风险等级：** 🟡 注意

**应用场景：** 仅重建某个特定服务，比全量 `update` 更快

**命令格式：**
```bash
./manage.sh rebuild <service>
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `frontend` | 仅重建前端 |
| `backend` | 仅重建后端 |
| `nginx` | 仅重建 Nginx |

**执行效果：** 重新构建指定服务的 Docker 镜像并重启该服务。适用于仅修改了某个服务代码的场景。

**示例：**
```bash
./manage.sh rebuild frontend     # 仅重建前端
./manage.sh rebuild backend      # 仅重建后端
./manage.sh rebuild nginx        # 仅重建 Nginx
```

---

### 1.9 upgrade — 拉取远程代码并升级 🔴

**风险等级：** 🔴 **高危**

**应用场景：** 从远程仓库拉取新版本代码并升级系统

**命令格式：**
```bash
./manage.sh upgrade [version] [--skip-migrate] [--check] [--latest]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `[version]` | 指定升级目标（git tag/branch/commit），默认拉取当前分支最新代码 |
| `--check` | 仅检查是否有可用更新，不执行升级 |
| `--skip-migrate` | 跳过数据库迁移（⚠ 极其危险，可能导致应用无法运行） |
| `--latest` | 显式指定拉取最新版本 |

**执行前自动检查：**
1. ✅ Git 仓库存在性检查
2. ✅ 当前服务健康状态检查
3. ✅ 磁盘空间检查（至少 2GB）
4. ✅ 显示当前版本和目标版本差异
5. ✅ 自动备份数据库

**执行效果：**
1. 拉取远程代码（git pull 或 git checkout）
2. 重新构建并重启所有 Docker 服务
3. 自动执行数据库迁移（alembic upgrade head）
4. 验证升级结果

**⚠ 严重警告：**
- 服务在升级期间**完全不可用**
- 数据库结构变更可能**不可逆**，降级可能无法实现
- 迁移失败会导致应用**无法正常运行**

**升级前必做事项：**
```bash
./manage.sh backup              # 备份数据库
cp .env .env.backup             # 备份配置文件
./manage.sh health              # 确认系统健康
```

**升级前建议事项：**
- 通知在线用户系统即将升级
- 在测试环境先验证升级流程

**示例：**
```bash
./manage.sh upgrade --check              # 仅检查可用更新
./manage.sh upgrade                      # 升级到当前分支最新版本
./manage.sh upgrade v2.1.0               # 升级到指定版本标签
./manage.sh upgrade main                 # 升级到 main 分支
./manage.sh upgrade abc1234              # 升级到指定 commit
```

**迁移失败恢复方案：**
1. 查看迁移错误日志：`./manage.sh logs backend`
2. 恢复数据库：`./manage.sh restore <backup_file>`
3. 回滚代码：`git checkout <previous_branch>`

---

## 二、数据管理命令

### 2.1 init — 初始化数据库

**风险等级：** 🟢 安全（幂等）

**应用场景：** 首次部署后初始化数据库和管理员账户

**命令格式：**
```bash
./manage.sh init
```

**执行效果：** 创建数据库表结构和管理员账户（admin/Admin123）。幂等操作，已初始化时自动跳过。

---

### 2.2 migrate — 数据库迁移 🔴

**风险等级：** 🔴 **高危**

**应用场景：** 执行数据库结构变更（版本升级后）

**命令格式：**
```bash
./manage.sh migrate [revision]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `(无)` | 迁移到最新版本（head） |
| `revision` | 迁移到指定版本 |

**执行效果：** 显示迁移前后状态，执行 alembic 迁移脚本。

**⚠ 警告：**
- 数据库结构变更可能**不可逆**
- 执行前建议备份数据库：`./manage.sh backup`
- 迁移失败可能导致应用无法启动

**示例：**
```bash
./manage.sh migrate              # 迁移到最新版本
./manage.sh migrate head         # 同上
./manage.sh migrate 001          # 迁移到指定版本
```

---

### 2.3 mock generate — 生成演示数据

**风险等级：** 🟡 注意

**应用场景：** 生成演示/测试数据

**命令格式：**
```bash
./manage.sh mock generate
```

**执行效果：** 创建数据源、合规基准、终端、白名单、黑名单、审计日志等样例数据。幂等操作，已有数据不会被覆盖。

> RBAC 种子数据：`mock generate` 自动创建5个预设角色（superadmin/admin/operator/auditor/viewer）和29个权限码，并为演示用户分配对应角色。

> **⚠ 生产环境阻止：** `mock generate` 会检查 `.env` 文件中的 `ENVIRONMENT` 变量，当 `ENVIRONMENT=production` 时拒绝执行并提示错误。此机制防止在生产环境中误操作生成测试数据。如需强制执行，需先将 `ENVIRONMENT` 改为非 `production` 值。

---

### 2.4 mock clear — 清除演示数据 🔴

**风险等级：** 🔴 **高危**

**应用场景：** 清除所有演示数据，准备生产环境

**命令格式：**
```bash
./manage.sh mock clear
```

**⚠ 影响范围：**
- 删除所有终端数据
- 删除所有白名单/黑名单条目
- 删除所有审计日志
- 删除所有数据源和合规基准
- 删除非管理员用户
- **保留**：管理员账户、数据库表结构、系统配置

> RBAC 清理：`mock clear` 清理演示数据时保留5个内置角色和29个预设权限，仅清除用户关联和自定义角色。

**⚠ 此操作不可逆！**

---

### 2.5 backup — 备份数据库

**风险等级：** 🟢 安全

**应用场景：** 手动备份数据库，或在进行危险操作前备份

**命令格式：**
```bash
./manage.sh backup [file]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `(无)` | 自动生成带时间戳的备份文件 |
| `file` | 指定备份文件路径 |

**执行效果：** 使用 pg_dump 导出完整数据库 SQL。自动保留最近 10 个备份。

**示例：**
```bash
./manage.sh backup                              # 自动命名备份
./manage.sh backup /tmp/pre_upgrade.sql         # 指定备份路径
```

---

### 2.5.1 备份体系架构说明

系统存在两套独立的备份机制，服务于不同场景：

#### 备份位置对比

| 维度 | `tam-uploads` Docker Volume | 项目根目录 `backups/` |
|------|-----------------------------|----------------------|
| **存储位置** | Docker named volume（容器内部） | 宿主机文件系统 |
| **挂载路径** | `/app/uploads/backups/` | `<项目根>/backups/` |
| **创建者** | Python 后端服务 (`BackupService`) | Shell 脚本 (`manage.sh`) |
| **文件格式** | ZIP 压缩包 | 原始 SQL + RDB 文件 |
| **保留策略** | 可配置 `retention_days` | 固定保留最近 10 个 |

#### 备份内容对比

**`tam-uploads` Volume 备份（后端服务）**

- ✅ 数据库备份（`pg_dump` 自定义格式）
- ✅ 配置文件备份（`docker-compose.yml`, `manage.sh`）
- ⚙️ 日志备份（可选，默认关闭）
- ✅ 支持加密（默认开启）

**项目根目录 `backups/` 备份（Shell 脚本）**

- ✅ 数据库备份（`pg_dump` 纯文本格式）
- ✅ Redis 备份（`dump.rdb`）
- ❌ 配置文件
- ❌ 日志
- ❌ 加密

#### 触发方式对比

**后端服务备份**：
- API 调用 `/api/v1/system/backup`
- 定时任务调度（默认每日凌晨 2 点）
- 远程存储（SFTP/FTP）上传

**Shell 脚本备份**：
- 手动执行 `./manage.sh backup`
- 自动触发：update、rebuild、migrate、restore 等操作前
- crontab 定时任务（`./manage.sh backup-schedule`）

#### 文件命名规则

**后端服务备份**：`backup_YYYYMMDD_HHMMSS.zip`

**Shell 脚本备份**：
- 数据库：`backup_YYYYMMDD_HHMMSS.sql` 或 `auto_pre_<操作>_YYYYMMDD_HHMMSS.sql`
- Redis：`redis_YYYYMMDD_HHMMSS.rdb`

#### 适用场景建议

| 场景 | 推荐使用 | 原因 |
|------|---------|------|
| **日常定时备份** | Volume（后端服务） | 支持压缩、加密、远程存储 |
| **升级前自动备份** | `backups/`（manage.sh） | 轻量级，保证操作可回滚 |
| **手动备份** | `backups/`（manage.sh） | 命令简单，直接 SQL 文件 |
| **远程灾备** | Volume（后端服务） | 内置 SFTP/FTP 支持 |
| **快速恢复** | `backups/`（manage.sh） | 直接 `psql` 导入，无需解压 |

#### 备份体系架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        备份体系架构                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   用户操作层                                                         │
│   ├── API 调用 ──────────────────────────┐                         │
│   │   (定时任务/手动触发)                 │                         │
│   └──────────────────────────────────────┼─────────────────────────┤
│                                          ▼                         │
│   后端服务层                              │                         │
│   ┌─────────────────────────────────────────────────────┐          │
│   │              BackupService (Python)                 │          │
│   │  • ZIP 压缩包格式                                    │          │
│   │  • 包含数据库+配置+日志                              │          │
│   │  • 支持加密/远程存储                                 │          │
│   │  • → 输出到 /app/uploads/backups/                   │          │
│   │      (即 tam-uploads volume)                        │          │
│   └─────────────────────────────────────────────────────┘          │
│                                                                     │
│   ├── CLI 命令 ──────────────────────────┐                         │
│   │   (./manage.sh backup)               │                         │
│   │   (自动备份)                          │                         │
│   └──────────────────────────────────────┼─────────────────────────┤
│                                          ▼                         │
│   Shell 脚本层                            │                         │
│   ┌─────────────────────────────────────────────────────┐          │
│   │              manage.sh (Bash)                       │          │
│   │  • 原始 SQL/RDB 格式                                 │          │
│   │  • 仅数据库+Redis                                    │          │
│   │  • 无加密/远程存储                                   │          │
│   │  • → 输出到 <项目根>/backups/                        │          │
│   │      (宿主机文件系统)                                │          │
│   └─────────────────────────────────────────────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 2.6 restore — 恢复数据库 🔴

**风险等级：** 🔴 **高危**

**应用场景：** 从备份文件恢复数据库

**命令格式：**
```bash
./manage.sh restore <file>
```

**⚠ 影响范围：**
- **所有当前数据将被替换**为备份数据
- 备份之后创建的数据将**永久丢失**
- 活跃用户会话将被终止（需重新登录）
- 服务将在恢复期间重启

**执行效果：**
1. 自动备份当前数据库（安全网）
2. 断开所有数据库连接
3. 删除并重建数据库
4. 导入备份数据
5. 重启后端服务

**Redis 数据恢复：**

恢复数据库时同步检查并恢复 Redis 数据：
1. 检查备份目录中是否存在 Redis RDB 文件（`redis_*.rdb`）
2. 若存在：停止 Redis 容器 → 复制 RDB 文件到 Redis 数据目录 → 启动 Redis 容器 → 等待健康检查通过
3. 若不存在：跳过 Redis 恢复，Redis 以空数据启动

**示例：**
```bash
./manage.sh restore backups/backup_20260608.sql
```

---

## 三、开发命令

### 3.1 test — 运行测试

**风险等级：** 🟢 安全

**命令格式：**
```bash
./manage.sh test
```

---

### 3.2 shell — 访问服务终端

**风险等级：** 🟡 注意（直接操作数据库/缓存有风险）

**命令格式：**
```bash
./manage.sh shell [backend|db|redis]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `backend` / `b` | 后端容器 Shell |
| `db` / `p` | PostgreSQL 命令行 |
| `redis` / `r` | Redis CLI |

**示例：**
```bash
./manage.sh shell db        # 打开数据库终端
./manage.sh shell redis     # 打开 Redis 终端
./manage.sh shell backend   # 打开后端 Shell
```

---

### 3.3 logs — 查看日志

**风险等级：** 🟢 安全

**命令格式：**
```bash
./manage.sh logs [service] [-n N]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `(无)` | 所有服务日志 |
| `service` | 指定服务（backend/postgres/redis/nginx/frontend） |
| `-n N` | 显示最后 N 行（默认 100） |

**示例：**
```bash
./manage.sh logs               # 所有服务日志
./manage.sh logs backend       # 后端日志
./manage.sh logs backend -n 50 # 后端最后 50 行
```

---

### 3.4 validate — 项目验证

**风险等级：** 🟢 安全

**命令格式：**
```bash
./manage.sh validate
```

**执行效果：** 检查文件结构、Python 语法、关键导入、配置完整性、代码质量、安全性和 API 端点。

---

## 四、工具命令

### 4.1 config — 配置管理

#### 4.1.1 config — 查看 .env 配置

**风险等级：** 🟢 安全

```bash
./manage.sh config              # 显示 .env 配置概览
./manage.sh config DB_PASSWORD  # 查看特定 .env 值
```

#### 4.1.2 config list — 列出数据库系统配置

**风险等级：** 🟢 安全

```bash
./manage.sh config list         # 按分类显示所有数据库系统配置
```

#### 4.1.3 config get — 获取配置值

**风险等级：** 🟢 安全

```bash
./manage.sh config get <key>    # 获取指定配置值
```

#### 4.1.4 config set — 修改配置值 🟡

**风险等级：** 🟡 注意（安全类配置为 🔴 高危）

**应用场景：** 修改系统运行参数

**命令格式：**
```bash
./manage.sh config set <key> <value>
```

**执行效果：**
1. 显示当前值和新值的对比
2. 安全类配置（锁定策略、限流、验证码等）需二次确认
3. 更新数据库配置并使 Redis 缓存失效
4. 提示是否重启服务

**安全类配置键（修改时需额外确认）：**
- `lockout_threshold` — 账户锁定阈值
- `lockout_duration` — 锁定持续时间
- `captcha_required` — 验证码开关
- `max_login_attempts` — 最大登录尝试次数
- `rate_limit` — 速率限制
- `ENCRYPTION_KEY` — 数据加密密钥（Fernet 密钥，用于敏感数据加密，修改后已加密数据将无法解密）

**⚠ 警告：** 修改安全配置不当可能导致用户被锁定或安全策略削弱

**示例：**
```bash
./manage.sh config set app_name "My Platform"
./manage.sh config set lockout_threshold 3       # 安全配置，需二次确认
./manage.sh config set scheduler_arp_collection_interval 600
```

#### 4.1.5 config branding — 品牌配置

**风险等级：** 🟢 安全

```bash
./manage.sh config branding                     # 查看所有品牌配置
./manage.sh config branding app_name MyApp      # 修改品牌配置
```

#### 4.1.6 config upload — 上传品牌资源

**风险等级：** 🟡 注意

```bash
./manage.sh config upload login_bg bg.png       # 上传登录页背景
./manage.sh config upload favicon icon.ico      # 上传浏览器图标
```

---

### 4.2 redis — Redis 管理

> **安全说明：** 所有 Redis 命令改用 `env REDISCLI_AUTH="${redis_pass}" redis-cli` 形式传递密码，密码不再通过命令行参数（`-a`）传递，避免在进程列表中泄露密码。

#### 4.2.1 redis info — Redis 信息

**风险等级：** 🟢 安全

```bash
./manage.sh redis info          # 显示 Redis 服务器信息、内存、键空间
```

#### 4.2.2 redis keys — 列出键

**风险等级：** 🟢 安全

```bash
./manage.sh redis keys          # 列出所有键
./manage.sh redis keys 'scheduler:*'   # 按模式过滤
```

**输出内容：** 键名、数据类型、TTL

#### 4.2.3 redis get — 获取键值

**风险等级：** 🟢 安全

```bash
./manage.sh redis get <key>     # 获取键值（支持 string/hash/list/set/zset）
```

#### 4.2.4 redis del — 删除键 🟡

**风险等级：** 🟡 注意

**应用场景：** 删除特定 Redis 缓存键

```bash
./manage.sh redis del <key>
```

**⚠ 影响范围：**
- 删除调度器控制键（`scheduler:ctrl:*`）会使暂停的任务恢复运行
- 删除缓存键会触发下次访问时重建
- 删除会话键会使用户需要重新登录

#### 4.2.5 redis flush — 清空数据库 🔴

**风险等级：** 🔴 **高危**

**应用场景：** 清空 Redis 中所有数据

```bash
./manage.sh redis flush [db]    # 清空指定数据库（默认 db 0）
```

**⚠ 影响范围：**
- **所有键**将被删除
- 活跃用户会话终止（需重新登录）
- 登录限速计数器重置
- 调度器暂停状态清除（所有任务恢复运行）
- 合规/白名单缓存将在下次访问时自动重建

---

### 4.3 password — 密码管理

#### 4.3.1 password reset — 重置用户密码 🟡

**风险等级：** 🟡 注意

**应用场景：** 重置指定用户的密码

**命令格式：**
```bash
./manage.sh password reset <username> [--password <new_password>]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `<username>` | 要重置密码的用户名 |
| `--password <new_password>` | 指定新密码（可选） |

**执行效果：**
1. 重置指定用户的密码
2. 若未提供 `--password`，则自动生成随机密码
3. 密码必须满足复杂度要求（8+ 字符，包含大写、小写、数字）
4. 重置后自动递增该用户的 token 版本（所有现有会话失效）
5. 清除该用户的 Redis 登录锁定

**示例：**
```bash
./manage.sh password reset admin                    # 随机生成新密码
./manage.sh password reset admin --password NewP@ss123  # 指定新密码
```

---

### 4.4 user — 用户管理

#### 4.4.1 user list — 列出所有用户

**风险等级：** 🟢 安全

**应用场景：** 查看系统中所有用户信息

**命令格式：**
```bash
./manage.sh user list
```

**输出内容：** 用户名、角色、活跃状态、超级用户状态

#### 4.4.2 user unlock — 解锁用户账户

**风险等级：** 🟢 安全

**应用场景：** 解锁被锁定的用户账户（管理员被锁定无法访问 Web UI 时特别有用）

**命令格式：**
```bash
./manage.sh user unlock <username>
```

**执行效果：** 清除指定用户的 Redis 登录锁定，用户可重新登录。

**示例：**
```bash
./manage.sh user unlock admin      # 解锁管理员账户
```

---

### 4.5 role — 角色管理

#### 4.5.1 role list — 列出所有角色

**风险等级：** 🟢 安全

**应用场景：** 查看系统中所有角色信息

**命令格式：**
```bash
./manage.sh role list
```

**输出内容：** 角色名称、描述、是否默认角色、关联用户数

#### 4.5.2 role permissions — 列出所有权限码

**风险等级：** 🟢 安全

**应用场景：** 查看系统中所有权限码

**命令格式：**
```bash
./manage.sh role permissions
```

**输出内容：** 全部 29 个权限码，按模块分组显示

---

### 4.6 logs-export — 导出审计日志

**风险等级：** 🟢 安全

**应用场景：** 导出审计日志为 CSV 文件

**命令格式：**
```bash
./manage.sh logs-export [--days N] [--output file] [--username user] [--action action]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `--days N` | 导出最近 N 天的日志（默认：30） |
| `--output file` | 输出文件路径（默认：`backups/audit_logs_export_{TIMESTAMP}.csv`） |
| `--username user` | 按用户名过滤 |
| `--action action` | 按操作类型过滤 |

**安全说明：** `--username` 和 `--action` 参数已做 SQL 注入防护。

**示例：**
```bash
./manage.sh logs-export                                    # 导出最近 30 天审计日志
./manage.sh logs-export --days 7                           # 导出最近 7 天
./manage.sh logs-export --username admin --action login    # 过滤 admin 用户的登录操作
./manage.sh logs-export --output /tmp/audit.csv            # 指定输出路径
```

---

### 4.7 scheduler — 定时任务管理

#### 4.7.1 scheduler status — 任务状态

**风险等级：** 🟢 安全

```bash
./manage.sh scheduler status    # 显示所有任务状态和间隔
```

**输出内容：** 任务名称、执行间隔、运行/暂停状态

**可用任务：**
| 任务名 | 说明 |
|--------|------|
| `arp_collection` | ARP 数据采集 |
| `ipguard_sync` | 合规基准同步 |
| `firewall_query` | 防火墙黑名单查询 |
| `compliance_check` | 合规检查 |
| `auto_unblock` | 自动解封 |

#### 4.7.2 scheduler pause — 暂停任务

**风险等级：** 🟡 注意

**应用场景：** 临时暂停定时任务（如维护期间）

```bash
./manage.sh scheduler pause <task>
```

**执行效果：** 在 Redis 中设置 `scheduler:ctrl:{task}` = `paused`，定时任务循环检测到此键后跳过执行。

**⚠ 注意：** 暂停期间相关数据不会更新，长时间暂停可能导致合规状态过时

#### 4.7.3 scheduler resume — 恢复任务

**风险等级：** 🟢 安全

```bash
./manage.sh scheduler resume <task>
```

**执行效果：** 删除 Redis 中的暂停控制键，任务在下一次调度周期恢复执行。

#### 4.7.4 scheduler trigger — 手动触发

**风险等级：** 🟡 注意

**应用场景：** 不等待定时调度，立即执行一次任务

```bash
./manage.sh scheduler trigger <task>
```

**⚠ 注意：** 手动触发会立即执行任务，可能消耗系统资源

#### 4.7.5 scheduler intervals — 查看间隔配置

**风险等级：** 🟢 安全

```bash
./manage.sh scheduler intervals  # 显示所有任务的配置间隔
```

**修改间隔：**
```bash
./manage.sh config set scheduler_arp_collection_interval 600   # 修改 ARP 采集间隔为 10 分钟
```

**间隔范围：** 30 秒 ~ 86400 秒（1 天）

---

### 4.8 ssl — SSL 证书管理

**风险等级：** 🟢 安全（幂等）

**命令格式：**
```bash
./manage.sh ssl [--force]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `(无)` | 证书不存在或已过期时生成（幂等） |
| `--force` | 强制重新生成 |

---

### 4.9 clean — 清理所有数据 🔴

**风险等级：** 🔴 **高危**

**应用场景：** 完全清除系统，恢复到初始状态

**命令格式：**
```bash
./manage.sh clean
```

**⚠ 影响范围：**
- 停止所有容器
- 删除所有容器和镜像
- 删除所有 Docker 卷（**所有数据永久丢失**）
- 删除所有网络
- 重置部署状态

**⚠ 此操作不可逆！** 执行前务必备份重要数据。

---

### 4.10 version — 版本信息

**风险等级：** 🟢 安全

```bash
./manage.sh version
```

---

### 4.11 dc() — Docker Compose 辅助函数

**风险等级：** 🟢 安全

**应用场景：** 简化 docker compose 调用，自动根据环境加载对应的 compose 文件

**命令格式：**
```bash
dc [docker_compose_args]
```

**自动加载规则：**

| `ENVIRONMENT` 值 | 自动加载的 Compose 文件 |
|-------------------|------------------------|
| `development` | `docker-compose.dev.yml` |
| `production` | `docker-compose.prod.yml` |
| 未设置 / 其他 | `docker-compose.yml`（默认） |

> **说明：** `dc()` 函数读取 `.env` 文件中的 `ENVIRONMENT` 变量，自动选择对应的 compose 文件。用户无需手动通过 `-f` 参数指定 compose 文件，直接使用 `dc up -d`、`dc ps` 等命令即可。

**示例：**
```bash
dc up -d            # 根据当前环境启动服务
dc ps               # 查看服务状态
dc logs backend     # 查看后端日志
dc restart nginx    # 重启 Nginx
```

---

## 五、环境变量说明

以下环境变量可在 `.env` 文件中配置，影响 `manage.sh` 的行为：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENVIRONMENT` | — | 运行环境标识（`development` / `production`），由 `deploy --dev`/`--prod` 自动设置。影响 `mock generate`（生产环境阻止执行）和 `dc()` 函数（自动选择 compose 文件） |
| `ADMIN_PASSWORD` | — | 自定义初始管理员密码（在 `deploy`/`init` 时使用） |
| `BACKUP_RETAIN_COUNT` | 0（保留全部） | 备份文件保留数量，超过此数量自动清理最旧的备份 |
| `TAM_LOG_ENABLED` | false | 启用 manage.sh 操作日志记录（也可通过 `--log` 选项单次启用） |

---

## 六、破坏性操作备份机制

`clean`、`redis flush`、`migrate` 等破坏性命令在执行前会提供**交互式备份提示**：

- 默认选择为"创建备份"（用户可拒绝）
- 备份完成后显示备份路径和文件大小
- `BACKUP_RETAIN_COUNT` 环境变量控制备份轮转数量（默认 0 表示保留全部）

---

## 七、配置热重载与重启说明

`manage.sh config set` 执行后会提示该配置变更的生效方式：

**热重载（无需重启，立即生效）：**
- 速率限制（rate limits）
- 登录安全策略（login security）
- 调度器间隔（scheduler intervals）
- JWT 过期时间（JWT expiry）
- 品牌配置（branding）

**需重启服务（修改后需执行 `./manage.sh restart`）：**
- `LOG_LEVEL`
- `TZ`
- `DEBUG`
- `ENCRYPTION_KEY`
- 数据库连接配置
- Redis 连接配置

---

## 八、命令速查表

| 命令 | 风险 | 用途 | 是否幂等 |
|------|------|------|---------|
| `deploy` | 🟡 | 全量部署 | ✅ |
| `start` | 🟢 | 启动服务 | ✅ |
| `stop` | 🟢 | 停止服务 | ✅ |
| `restart` | 🟡 | 重启服务 | ✅ |
| `status` | 🟢 | 查看状态 | ✅ |
| `health` | 🟢 | 健康检查 | ✅ |
| `update` | 🟡 | 本地重建 | ✅ |
| `rebuild` | 🟡 | 重建指定服务 | ✅ |
| `upgrade` | 🔴 | 远程升级 | ❌ |
| `init` | 🟢 | 初始化数据库 | ✅ |
| `migrate` | 🔴 | 数据库迁移 | ❌ |
| `mock generate` | 🟡 | 生成演示数据 | ✅ |
| `mock clear` | 🔴 | 清除演示数据 | ❌ |
| `backup` | 🟢 | 备份数据库 | ✅ |
| `restore` | 🔴 | 恢复数据库 | ❌ |
| `test` | 🟢 | 运行测试 | ✅ |
| `shell` | 🟡 | 服务终端 | ✅ |
| `logs` | 🟢 | 查看日志 | ✅ |
| `validate` | 🟢 | 项目验证 | ✅ |
| `config` | 🟢 | 查看 .env | ✅ |
| `config list` | 🟢 | 列出配置 | ✅ |
| `config get` | 🟢 | 获取配置 | ✅ |
| `config set` | 🟡/🔴 | 修改配置 | ❌ |
| `config branding` | 🟢 | 品牌配置 | ✅ |
| `config upload` | 🟡 | 上传资源 | ❌ |
| `redis info` | 🟢 | Redis 信息 | ✅ |
| `redis keys` | 🟢 | 列出键 | ✅ |
| `redis get` | 🟢 | 获取键值 | ✅ |
| `redis del` | 🟡 | 删除键 | ❌ |
| `redis flush` | 🔴 | 清空数据库 | ❌ |
| `password reset` | 🟡 | 重置用户密码 | ❌ |
| `user list` | 🟢 | 列出所有用户 | ✅ |
| `user unlock` | 🟢 | 解锁用户账户 | ✅ |
| `role list` | 🟢 | 列出所有角色 | ✅ |
| `role permissions` | 🟢 | 列出权限码 | ✅ |
| `logs-export` | 🟢 | 导出审计日志 | ✅ |
| `scheduler status` | 🟢 | 任务状态 | ✅ |
| `scheduler pause` | 🟡 | 暂停任务 | ✅ |
| `scheduler resume` | 🟢 | 恢复任务 | ✅ |
| `scheduler trigger` | 🟡 | 手动触发 | ❌ |
| `scheduler intervals` | 🟢 | 查看间隔 | ✅ |
| `ssl` | 🟢 | SSL 证书 | ✅ |
| `clean` | 🔴 | 清理所有 | ❌ |
| `version` | 🟢 | 版本信息 | ✅ |
| `dc()` | 🟢 | Docker Compose 辅助 | ✅ |

---

## 九、相似命令对比

### 9.1 restart vs rebuild vs update vs upgrade — 服务更新类

这四个命令都涉及服务重启，但构建深度和影响范围差异显著：

| 维度 | `restart [svc]` | `rebuild <svc>` | `update` | `upgrade [ver]` |
|------|------------------|------------------|----------|------------------|
| **构建镜像** | 否 | 是 | 是 | 是 |
| **重建容器** | 否（仅重启进程） | 是（--force-recreate） | 是 | 是 |
| **拉取远程代码** | 否 | 否 | 否 | **是** |
| **自动备份** | 否 | 是 | 是 | 是 |
| **数据库迁移** | 否 | 否 | 否 | 是 |
| **影响范围** | 单个或全部服务 | 单个服务 | **全部服务** | **全部服务** |
| **服务中断时间** | 秒级 | 秒级（单个） | 10-30秒 | 分钟级 |
| **适用场景** | 配置变更、进程异常 | 单服务代码变更 | 全量本地代码变更 | 远程版本升级 |

**选择决策：**

```
代码是否变更？
├── 否 → restart（仅重启进程）
└── 是 → 代码变更范围？
    ├── 单个服务 → rebuild <svc>（最快）
    ├── 多个服务 → update（全量重建）
    └── 需拉远程代码 → upgrade（含 git pull + 迁移）
```

**关键区别：**
- `restart` 不重新构建镜像，代码变更**不会生效**（除非代码目录是 volume 挂载的开发模式）
- `rebuild` 和 `update` 都会重新构建镜像，代码变更**一定生效**
- `upgrade` 是唯一会拉取远程代码的命令，且自动执行数据库迁移

---

### 9.2 status vs health — 状态检查类

| 维度 | `status` | `health` |
|------|----------|----------|
| **检查深度** | 容器运行状态 | 系统各组件深度检查 |
| **检查内容** | 容器 Up/Down、端口映射 | Docker + 容器 + DB连接 + Redis连接 + API + Web UI + SSL + 磁盘 |
| **执行速度** | 快（< 2秒） | 慢（5-15秒，含连接测试） |
| **适用场景** | 快速确认服务是否在运行 | 部署后验证、故障排查 |

**选择决策：** 日常查看用 `status`，部署后或故障时用 `health`。

---

### 9.3 deploy vs init — 初始化类

| 维度 | `deploy` | `init` |
|------|----------|--------|
| **执行范围** | 全量部署（环境检查→SSL→.env→构建→启动→初始化） | 仅初始化数据库和管理员 |
| **是否构建服务** | 是 | 否 |
| **是否启动服务** | 是 | 否（需先 `start`） |
| **适用场景** | 首次部署或完全重部署 | 数据库已存在但未初始化 |

**选择决策：** 从零开始用 `deploy`，数据库空表需初始化用 `init`。

---

### 9.4 backup vs restore — 数据备份恢复类

| 维度 | `backup` | `restore` |
|------|----------|-----------|
| **操作方向** | 导出（DB → SQL文件） | 导入（SQL文件 → DB） |
| **数据影响** | 无（只读） | **覆盖当前所有数据** |
| **自动备份** | — | 是（恢复前自动备份当前数据） |
| **Redis 处理** | 可选备份 RDB | 自动检测并恢复 RDB |
| **风险等级** | 🟢 安全 | 🔴 高危 |

---

### 9.5 mock generate vs mock clear — 演示数据类

| 维度 | `mock generate` | `mock clear` |
|------|-----------------|--------------|
| **操作方向** | 创建演示数据 | 清除演示数据 |
| **幂等性** | 是（已有数据不覆盖） | 否（不可逆） |
| **保留内容** | — | 管理员账户、表结构、系统配置、内置角色和权限 |
| **RBAC 处理** | 创建5个预设角色+29个权限码 | 保留内置角色和权限，仅清除用户关联和自定义角色 |
| **风险等级** | 🟡 注意 | 🔴 高危 |

---

### 9.6 config vs config list — 配置查看类

| 维度 | `config` | `config list` |
|------|----------|----------------|
| **数据来源** | `.env` 文件 | 数据库 `system_config` 表 |
| **配置类型** | 基础设施配置（DB密码、端口、密钥等） | 业务运行配置（调度间隔、安全策略、品牌等） |
| **修改方式** | 手动编辑 `.env` + 重启 | `config set` 命令（部分热重载） |
| **适用场景** | 查看/修改部署参数 | 查看/修改运行参数 |

---

### 9.7 clean vs mock clear — 数据清除类

| 维度 | `clean` | `mock clear` |
|------|---------|--------------|
| **清除范围** | **所有**（容器+镜像+卷+网络） | 业务数据（终端、白名单、日志等） |
| **基础设施** | 全部删除 | 保留（容器继续运行） |
| **数据库** | Docker 卷删除 | 表结构保留，数据清空 |
| **恢复方式** | 需重新 `deploy` | 需重新 `mock generate` 或手动录入 |
| **风险等级** | 🔴 高危 | 🔴 高危 |

**选择决策：** 清空业务数据保留环境用 `mock clear`，彻底重置用 `clean`。

---

### 9.8 scheduler pause vs scheduler resume — 调度控制类

| 维度 | `scheduler pause` | `scheduler resume` |
|------|-------------------|---------------------|
| **操作** | 设置 Redis 暂停标记 | 删除 Redis 暂停标记 |
| **生效时机** | 下一次调度周期检查时 | 下一次调度周期检查时 |
| **数据影响** | 暂停期间数据不更新 | 恢复后数据正常更新 |
| **风险等级** | 🟡 注意 | 🟢 安全 |

---

### 9.9 logs vs logs-export — 日志查看类

| 维度 | `logs` | `logs-export` |
|------|--------|---------------|
| **日志来源** | Docker 容器运行日志 | 数据库审计日志 |
| **输出方式** | 终端实时查看 | 导出为 CSV 文件 |
| **过滤能力** | 按服务、行数 | 按天数、用户名、操作类型 |
| **适用场景** | 排查运行时错误 | 审计合规、日志归档 |

---

## 十、常见运维场景

### 场景 1：首次部署
```bash
./manage.sh deploy --dev        # 开发环境（含样例数据）
./manage.sh deploy --prod       # 生产环境
```

### 场景 2：本地代码修改后更新
```bash
./manage.sh update              # 重建并重启（不拉代码）
```

### 场景 3：升级到新版本
```bash
./manage.sh upgrade --check     # 先检查可用更新
./manage.sh backup              # 备份数据库
cp .env .env.backup             # 备份配置
./manage.sh upgrade             # 执行升级
./manage.sh health              # 验证升级结果
```

### 场景 4：数据库迁移
```bash
./manage.sh backup              # 先备份
./manage.sh migrate             # 执行迁移
```

### 场景 5：临时暂停合规检查
```bash
./manage.sh scheduler pause compliance_check   # 暂停
# ... 维护操作 ...
./manage.sh scheduler resume compliance_check  # 恢复
```

### 场景 6：修改定时任务间隔
```bash
./manage.sh scheduler intervals                 # 查看当前间隔
./manage.sh config set scheduler_arp_collection_interval 600  # 修改为 10 分钟
./manage.sh restart                             # 重启生效
```

### 场景 7：系统故障排查
```bash
./manage.sh status              # 查看服务状态
./manage.sh health              # 深度健康检查
./manage.sh logs backend -n 100 # 查看后端日志
./manage.sh shell db            # 进入数据库排查
```

### 场景 8：数据库恢复
```bash
./manage.sh backup                              # 先备份当前数据
./manage.sh restore backups/backup_20260608.sql # 从备份恢复
```
