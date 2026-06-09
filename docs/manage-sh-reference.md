# manage.sh 命令行操作手册

TerminalAccessManager (TAM) 统一管理脚本，用于项目全生命周期管理。

## 全局选项

| 选项 | 说明 |
|------|------|
| `-y, --yes` | 跳过所有确认提示（非交互模式） |
| `-v, --verbose` | 启用详细/调试输出 |
| `-h, --help` | 显示帮助信息 |

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
./manage.sh deploy [--demo|--prod]
```

**参数说明：**
| 参数 | 说明 |
|------|------|
| `--demo` | 演示模式：自动配置 + 生成样例数据 |
| `--prod` | 生产模式：手动配置向导 |

**执行效果：**
1. 检查前置条件（Docker、磁盘空间、端口）
2. 生成 SSL 证书
3. 配置环境变量（.env）
4. 构建并启动所有服务
5. 初始化数据库和管理员账户
6. 演示模式下自动生成 Mock 数据

**示例：**
```bash
./manage.sh deploy --demo          # 快速演示部署
./manage.sh deploy --prod          # 生产部署（交互式向导）
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

### 1.8 upgrade — 拉取远程代码并升级 🔴

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

### 4.3 scheduler — 定时任务管理

#### 4.3.1 scheduler status — 任务状态

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

#### 4.3.2 scheduler pause — 暂停任务

**风险等级：** 🟡 注意

**应用场景：** 临时暂停定时任务（如维护期间）

```bash
./manage.sh scheduler pause <task>
```

**执行效果：** 在 Redis 中设置 `scheduler:ctrl:{task}` = `paused`，定时任务循环检测到此键后跳过执行。

**⚠ 注意：** 暂停期间相关数据不会更新，长时间暂停可能导致合规状态过时

#### 4.3.3 scheduler resume — 恢复任务

**风险等级：** 🟢 安全

```bash
./manage.sh scheduler resume <task>
```

**执行效果：** 删除 Redis 中的暂停控制键，任务在下一次调度周期恢复执行。

#### 4.3.4 scheduler trigger — 手动触发

**风险等级：** 🟡 注意

**应用场景：** 不等待定时调度，立即执行一次任务

```bash
./manage.sh scheduler trigger <task>
```

**⚠ 注意：** 手动触发会立即执行任务，可能消耗系统资源

#### 4.3.5 scheduler intervals — 查看间隔配置

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

### 4.4 ssl — SSL 证书管理

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

### 4.5 clean — 清理所有数据 🔴

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

### 4.6 version — 版本信息

**风险等级：** 🟢 安全

```bash
./manage.sh version
```

---

## 五、命令速查表

| 命令 | 风险 | 用途 | 是否幂等 |
|------|------|------|---------|
| `deploy` | 🟡 | 全量部署 | ✅ |
| `start` | 🟢 | 启动服务 | ✅ |
| `stop` | 🟢 | 停止服务 | ✅ |
| `restart` | 🟡 | 重启服务 | ✅ |
| `status` | 🟢 | 查看状态 | ✅ |
| `health` | 🟢 | 健康检查 | ✅ |
| `update` | 🟡 | 本地重建 | ✅ |
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
| `scheduler status` | 🟢 | 任务状态 | ✅ |
| `scheduler pause` | 🟡 | 暂停任务 | ✅ |
| `scheduler resume` | 🟢 | 恢复任务 | ✅ |
| `scheduler trigger` | 🟡 | 手动触发 | ❌ |
| `scheduler intervals` | 🟢 | 查看间隔 | ✅ |
| `ssl` | 🟢 | SSL 证书 | ✅ |
| `clean` | 🔴 | 清理所有 | ❌ |
| `version` | 🟢 | 版本信息 | ✅ |

---

## 六、常见运维场景

### 场景 1：首次部署
```bash
./manage.sh deploy --demo       # 演示环境
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
