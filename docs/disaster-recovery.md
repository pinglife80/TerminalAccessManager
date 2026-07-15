# TerminalAccessManager - 灾难恢复计划

> 文档版本：v3.6.14  更新日期：2026-07-15

## 目录

- [1. 故障分级](#1-故障分级)
- [2. 响应时间要求](#2-响应时间要求)
- [3. 各组件故障恢复步骤](#3-各组件故障恢复步骤)
- [4. 数据恢复流程](#4-数据恢复流程)
- [5. RPO/RTO 目标](#5-rporto-目标)
- [6. 恢复演练](#6-恢复演练)

---

## 1. 故障分级

| 级别 | 定义 | 典型场景 |
|------|------|----------|
| **P0** | 系统完全不可用 | 所有服务宕机、数据库损坏、服务器硬件故障、磁盘满导致全部服务停止 |
| **P1** | 核心功能受损 | 合规检查持续失败、终端封堵/解封不可用、后端 API 无法响应、数据库连接池耗尽 |
| **P2** | 部分功能降级 | 单个数据源不可用、审计日志写入异常、Redis 缓存失效导致性能下降、Sangfor API 超时 |
| **P3** | 轻微影响 | UI 显示异常、非关键告警、SSL 证书即将过期、磁盘空间低于推荐值 |

---

## 2. 响应时间要求

| 级别 | 响应时间 | 恢复时间 | 通知范围 |
|------|---------|---------|----------|
| **P0** | 15 分钟内 | 2 小时内 | 全体运维、开发负责人、管理层 |
| **P1** | 30 分钟内 | 4 小时内 | 运维值班、开发负责人 |
| **P2** | 2 小时内 | 1 个工作日内 | 运维值班 |
| **P3** | 1 个工作日内 | 下个版本修复 | 运维值班 |

---

## 3. 各组件故障恢复步骤

### 3.1 PostgreSQL 故障

**故障现象：**
- 后端日志报 `connection refused` 或 `could not connect to server`
- `./manage.sh health` 数据库连接检查失败
- Web 界面返回 500 错误

**诊断命令：**

```bash
# 检查容器状态
./manage.sh status

# 检查数据库是否就绪
./manage.sh shell db -c "SELECT 1;"

# 查看数据库日志
./manage.sh logs postgres -n 200

# 检查磁盘空间（磁盘满是常见原因）
df -h

# 查看数据库连接数
./manage.sh shell db -c "SELECT count(*) FROM pg_stat_activity;"
```

**恢复步骤：**

1. 若容器已停止，尝试重启：
   ```bash
   ./manage.sh restart postgres
   ```

2. 若重启失败，检查磁盘空间并清理：
   ```bash
   # 清理 Docker 无用资源
   docker system prune -f
   # 清理旧备份
   find backups/ -name "backup_*.sql" -mtime +30 -delete
   ```

3. 若数据库损坏，从备份恢复（参见 [4. 数据恢复流程](#4-数据恢复流程)）

4. 若连接数耗尽，终止空闲连接：
   ```bash
   ./manage.sh shell db -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '30 minutes';"
   ```

**验证方法：**

```bash
# 数据库连接检查
./manage.sh shell db -c "SELECT 1;"

# 完整健康检查
./manage.sh health

# 验证 Web 界面可访问
curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/
```

---

### 3.2 Redis 故障

**故障现象：**
- 用户登录失败或频繁掉线（会话丢失）
- 限速功能异常
- 定时任务控制失效
- 后端日志报 Redis 连接错误

**诊断命令：**

```bash
# 检查 Redis 连通性
./manage.sh shell redis -c "PING"

# 查看 Redis 信息
./manage.sh redis info

# 查看键空间统计
./manage.sh shell redis -c "INFO keyspace"

# 查看 Redis 日志
./manage.sh logs redis -n 200
```

**恢复步骤：**

1. 若容器已停止，尝试重启：
   ```bash
   ./manage.sh restart redis
   ```

2. 若 Redis 内存满（`maxmemory` 报错），检查并清理：
   ```bash
   # 查看内存使用
   ./manage.sh redis info | grep used_memory_human

   # 清理过期键
   ./manage.sh shell redis -c "SCAN 0 COUNT 1000"

   # 必要时清空 Redis（注意：会终止所有会话）
   ./manage.sh -y redis flush
   ```

3. 若 Redis 数据损坏，从 RDB 备份恢复（参见 [4.3 Redis 数据恢复](#43-redis-数据恢复)）

**验证方法：**

```bash
# Redis 连通性
./manage.sh shell redis -c "PING"

# 完整健康检查
./manage.sh health
```

---

### 3.3 Backend 故障

**故障现象：**
- Web 界面返回 502 Bad Gateway
- API 请求超时或无响应
- 定时任务不执行
- `./manage.sh status` 显示 backend 不健康

**诊断命令：**

```bash
# 查看后端日志
./manage.sh logs backend -n 200

# 检查后端进程
docker compose -p tam ps backend

# 查看后端健康端点
curl -sk https://localhost:8443/api/health
```

**恢复步骤：**

1. 重启后端服务：
   ```bash
   ./manage.sh restart backend
   ```

2. 若重启失败，重建容器：
   ```bash
   ./manage.sh update
   ```

3. 若数据库迁移问题导致启动失败，检查迁移状态：
   ```bash
   ./manage.sh migrate head
   ```

4. 若配置错误导致启动失败，检查并修正 `.env`：
   ```bash
   ./manage.sh config
   ```

**验证方法：**

```bash
# 后端 API 可达性
curl -sk https://localhost:8443/api/health

# 完整健康检查
./manage.sh health
```

---

### 3.4 Nginx 故障

**故障现象：**
- Web 界面完全无法访问（连接拒绝）
- HTTP 不自动重定向到 HTTPS
- 静态资源加载失败
- SSL 证书错误

**诊断命令：**

```bash
# 检查端口占用
ss -tlnp | grep -E '8080|8443'

# 查看 Nginx 日志
./manage.sh logs nginx -n 200

# 检查 SSL 证书
openssl x509 -enddate -noout -in nginx/certs/cert.pem

# 检查 Nginx 配置
docker compose -p tam exec nginx nginx -t
```

**恢复步骤：**

1. 重启 Nginx：
   ```bash
   ./manage.sh restart nginx
   ```

2. 若 SSL 证书过期或损坏，重新生成：
   ```bash
   ./manage.sh ssl --force
   ```

3. 若端口被占用，排查占用进程：
   ```bash
   ss -tlnp | grep -E '8080|8443'
   # 终止占用进程或修改端口映射
   ```

4. 若前端构建产物丢失，重建：
   ```bash
   ./manage.sh update
   ```

**验证方法：**

```bash
# HTTPS 可访问
curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/

# HTTP 重定向到 HTTPS
curl -sk -o /dev/null -w "%{http_code}" http://localhost:8080/

# 完整健康检查
./manage.sh health
```

---

## 4. 数据恢复流程

### 4.1 全量恢复（从备份恢复）

适用于数据库损坏、误操作删除数据等场景。

**前置条件：** 确认备份文件存在且完整。

```bash
# 1. 查看可用备份
ls -lh backups/

# 2. 确认服务运行
./manage.sh status

# 3. 执行恢复（会自动备份当前数据）
./manage.sh restore backups/backup_20260616_020000.sql

# 4. 验证恢复结果
./manage.sh health
./manage.sh shell db -c "SELECT count(*) FROM terminals;"
```

> **注意：** `restore` 命令会先自动备份当前数据库，然后清空目标数据库再导入。恢复期间服务不可用。

---

### 4.2 时间点恢复（PostgreSQL PITR）

适用于需要恢复到特定时间点的场景（需要提前启用 WAL 归档）。

**前提条件：** 已配置 PostgreSQL WAL 归档。默认部署未启用，需手动配置。

**启用 WAL 归档（预防措施）：**

1. 在 `docker-compose.yml` 的 postgres 服务 `command` 中添加：
   ```yaml
   command: >
     postgres
     -c wal_level=replica
     -c archive_mode=on
     -c archive_command='cp %p /var/lib/postgresql/data/pg_archive/%f'
   ```

2. 创建归档目录并重启：
   ```bash
   docker compose -p tam exec postgres mkdir -p /var/lib/postgresql/data/pg_archive
   ./manage.sh restart postgres
   ```

**PITR 恢复步骤：**

1. 停止后端服务：
   ```bash
   ./manage.sh stop
   ```

2. 备份当前数据目录：
   ```bash
   docker compose -p tam run --rm postgres cp -a /var/lib/postgresql/data /tmp/pg_data_backup
   ```

3. 恢复基础备份并配置 `recovery_target_time`：
   ```bash
   # 在 postgresql.auto.conf 中添加
   restore_command = 'cp /var/lib/postgresql/data/pg_archive/%f %p'
   recovery_target_time = '2026-06-16 10:00:00+08'
   recovery_target_action = 'promote'
   ```

4. 启动 PostgreSQL 等待恢复完成：
   ```bash
   docker compose -p tam up -d postgres
   ```

5. 验证并启动所有服务：
   ```bash
   ./manage.sh health
   ./manage.sh start
   ```

---

### 4.3 Redis 数据恢复

适用于 Redis 数据丢失或损坏的场景。

**从 RDB 备份恢复：**

```bash
# 1. 查看可用的 Redis 备份
ls -lh backups/redis_*.rdb

# 2. 停止 Redis
docker compose -p tam stop redis

# 3. 复制 RDB 文件到 Redis 数据目录
docker compose -p tam run --rm redis cp /backup/redis_20260616_020000.rdb /data/dump.rdb

# 4. 启动 Redis
docker compose -p tam start redis

# 5. 验证
./manage.sh shell redis -c "PING"
./manage.sh redis info
```

> **注意：** `./manage.sh restore` 命令在恢复 PostgreSQL 时会自动检测并恢复同目录下的 Redis RDB 文件。

**无 RDB 备份时的处理：**

Redis 数据为缓存性质（会话、限速计数、调度器控制键），丢失后不影响业务数据完整性：

```bash
# 重启 Redis 即可（空库启动）
./manage.sh restart redis

# 用户需重新登录
# 定时任务将恢复默认运行状态
# 限速计数器将重置
```

---

## 5. RPO/RTO 目标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| **RPO**（恢复点目标） | 1 小时 | 定时备份间隔决定，建议配置 `backup-schedule enable hourly` |
| **RTO**（恢复时间目标） | 2 小时 | 从故障发生到服务恢复的时间 |

**达成 RPO 的措施：**

```bash
# 启用每小时自动备份
./manage.sh backup-schedule enable hourly

# 验证自动备份已启用
./manage.sh backup-schedule status
```

**达成 RTO 的措施：**

- 保持备份文件可用且完整（自动保留最近 10 个备份）
- 熟悉恢复操作流程（定期演练）
- 监控服务健康状态，及时发现故障

---

## 6. 恢复演练

### 6.1 演练频率

建议每季度进行一次灾难恢复演练，确保恢复流程有效、团队熟悉操作。

### 6.2 演练步骤

**演练前准备：**

1. 确认演练时间窗口，通知相关人员
2. 准备演练环境（建议使用独立测试环境，避免影响生产）
3. 确认最新备份可用：
   ```bash
   ls -lh backups/
   ```

**演练内容：**

**场景一：全量数据恢复**

```bash
# 1. 确认当前数据状态
./manage.sh shell db -c "SELECT count(*) FROM terminals;"

# 2. 执行恢复
./manage.sh restore backups/backup_20260616_020000.sql

# 3. 验证恢复后数据
./manage.sh shell db -c "SELECT count(*) FROM terminals;"

# 4. 健康检查
./manage.sh health
```

**场景二：单组件故障恢复**

```bash
# 1. 模拟 PostgreSQL 故障
docker compose -p tam stop postgres

# 2. 验证故障现象
./manage.sh health

# 3. 执行恢复
./manage.sh restart postgres

# 4. 验证恢复
./manage.sh health
```

**场景三：Redis 数据丢失**

```bash
# 1. 记录当前 Redis 键数量
./manage.sh redis keys | wc -l

# 2. 清空 Redis（模拟数据丢失）
./manage.sh -y redis flush

# 3. 验证系统功能（用户需重新登录，定时任务恢复运行）

# 4. 从 RDB 备份恢复（如有）
ls -lh backups/redis_*.rdb
```

**场景四：完整系统恢复**

```bash
# 1. 停止所有服务
./manage.sh stop

# 2. 清理环境
./manage.sh -y clean

# 3. 重新部署
./manage.sh -y deploy --prod

# 4. 恢复数据
./manage.sh restore backups/backup_20260616_020000.sql

# 5. 验证
./manage.sh health
```

**演练后：**

1. 记录演练耗时，与 RTO 目标对比
2. 记录遇到的问题和改进点
3. 更新本文档中的恢复步骤
4. 确认备份策略有效性
