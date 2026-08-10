# TerminalAccessManager - 运维操作手册

> 文档版本：v3.10.0  更新日期：2026-08-06

## 目录

- [1. 日常巡检清单](#1-日常巡检清单)
- [2. 常见故障排查](#2-常见故障排查)
- [3. 定时任务管理](#3-定时任务管理)
- [4. 数据源/绑定/基线变更操作规范](#4-数据源绑定基线变更操作规范)
- [5. 升级/回滚操作步骤](#5-升级回滚操作步骤)

---

## 1. 日常巡检清单

### 1.1 服务状态检查

```bash
# 快速查看服务状态
./manage.sh status

# 深度健康检查（8 项检查）
./manage.sh health
```

**关注项：**
- PostgreSQL 状态应为 `healthy`
- Redis 状态应为 `healthy`
- Backend API 状态应为 `healthy`
- Nginx Proxy 状态应为 `running`
- Web Access 应返回 `200 OK`

### 1.2 日志检查

```bash
# 查看所有服务最近日志
./manage.sh logs -n 50

# 查看后端日志（重点关注 ERROR 和 WARNING）
./manage.sh logs backend -n 100

# 查看 Nginx 访问日志（关注 4xx/5xx）
./manage.sh logs nginx -n 100

# 查看数据库日志
./manage.sh logs postgres -n 50
```

**关注项：**
- 后端日志中的 `ERROR` 和 `WARNING` 关键字
- Nginx 日志中的大量 502/503 错误
- 数据库日志中的连接拒绝或死锁信息

### 1.3 磁盘空间检查

```bash
# 查看系统磁盘空间
df -h

# 查看 Docker 磁盘使用
docker system df

# 查看备份目录大小
du -sh backups/
```

**阈值：**
- 可用空间 < 5GB：告警
- 可用空间 < 2GB：紧急处理

**清理方法：**

```bash
# 清理 Docker 无用资源
docker system prune -f

# 清理旧备份（保留最近 10 个，自动执行）
# 手动清理：
find backups/ -name "backup_*.sql" -mtime +30 -delete
find backups/ -name "redis_*.rdb" -mtime +30 -delete
```

### 1.4 数据库连接检查

```bash
# 快速检查数据库是否就绪
./manage.sh shell db -c "SELECT 1;"

# 查看数据库连接数
./manage.sh shell db -c "SELECT count(*) AS active_connections FROM pg_stat_activity;"

# 查看数据库大小
./manage.sh shell db -c "SELECT pg_size_pretty(pg_database_size('tam_db')) AS db_size;"
```

**关注项：**
- 连接数持续接近上限需排查
- 数据库体积异常增长需排查

### 1.5 Redis 内存使用检查

```bash
# 查看 Redis 服务器信息
./manage.sh redis info

# 查看键数量
./manage.sh shell redis -c "DBSIZE"

# 查看内存使用
./manage.sh redis info | grep used_memory_human
```

**关注项：**
- 内存使用持续增长可能存在键未设置过期时间
- 键数量异常增多需排查

---

## 2. 常见故障排查

### 2.1 服务启动失败

**故障现象：**
- `./manage.sh start` 后服务未正常运行
- `./manage.sh status` 显示服务不健康

**可能原因：**
1. `.env` 配置缺失或错误（必需变量未设置）
2. 端口被占用（8080/8443）
3. 磁盘空间不足
4. Docker 服务异常

**排查步骤：**

```bash
# 1. 检查 .env 配置完整性
./manage.sh config

# 2. 检查端口占用
ss -tlnp | grep -E '8080|8443'

# 3. 检查磁盘空间
df -h

# 4. 查看服务日志
./manage.sh logs -n 50

# 5. 深度健康检查
./manage.sh health
```

**解决方案：**

- 配置缺失：补充 `.env` 中必需变量后重新部署
  ```bash
  vim .env
  ./manage.sh -y deploy --prod
  ```

- 端口占用：终止占用进程或修改端口映射
  ```bash
  # 查找占用进程
  lsof -i :8080
  lsof -i :8443
  ```

- 磁盘不足：清理空间后重试
  ```bash
  docker system prune -f
  ./manage.sh start
  ```

---

### 2.2 合规检查不执行

**故障现象：**
- 合规检查状态长时间未更新
- 终端合规状态显示异常

**可能原因：**
1. 定时任务被暂停
2. 数据源连接异常
3. 后端服务异常

**排查步骤：**

```bash
# 1. 查看定时任务状态
./manage.sh scheduler status

# 2. 查看后端日志中的合规检查相关错误
./manage.sh logs backend -n 200 | grep -i "compliance"

# 3. 手动触发合规检查
./manage.sh scheduler trigger compliance_check
```

**解决方案：**

- 任务被暂停：恢复执行
  ```bash
  ./manage.sh scheduler resume compliance_check
  ```

- 数据源异常：检查数据源配置和连通性（参见 [2.6 数据源同步失败](#26-数据源同步失败)）

---

### 2.3 防火墙通信异常（Sangfor API 超时）

**故障现象：**
- 终端封堵/解封操作失败
- 日志中出现 Sangfor API 超时错误
- 防火墙黑名单查询返回空

**可能原因：**
1. Sangfor API 地址不可达
2. Sangfor API 认证失败（用户名/密码错误或过期）
3. 网络策略阻断

**排查步骤：**

```bash
# 1. 检查 Sangfor API 配置
./manage.sh config | grep -i sangfor

# 2. 测试 API 连通性（从后端容器内）
docker compose -p tam exec backend curl -sk -o /dev/null -w "%{http_code}" <SANGFOR_BASE_URL>

# 3. 查看后端日志中的防火墙相关错误
./manage.sh logs backend -n 200 | grep -i "sangfor\|firewall"

# 4. 手动触发防火墙查询
./manage.sh scheduler trigger firewall_query
```

**解决方案：**

- API 地址不可达：检查网络连通性，确认防火墙策略放行
- 认证失败：更新 Sangfor API 凭据
  ```bash
  ./manage.sh config SANGFOR_USERNAME <新用户名>
  ./manage.sh config SANGFOR_PASSWORD <新密码>
  ./manage.sh restart backend
  ```

---

### 2.4 ARP 数据采集失败

**故障现象：**
- 终端列表中 MAC/IP 信息缺失
- ARP 采集定时任务报错

**可能原因：**
1. 网络交换机连接异常
2. 交换机认证失败
3. SNMP/SSH 协议不通

**排查步骤：**

```bash
# 1. 检查交换机配置
./manage.sh config | grep -i switch

# 2. 查看后端日志中的 ARP 采集错误
./manage.sh logs backend -n 200 | grep -i "arp"

# 3. 检查定时任务状态
./manage.sh scheduler status

# 4. 手动触发 ARP 采集
./manage.sh scheduler trigger arp_collection
```

**解决方案：**

- 交换机连接异常：检查交换机 IP 可达性
  ```bash
  docker compose -p tam exec backend ping -c 3 <SWITCH_HOST>
  ```

- 认证失败：更新交换机凭据
  ```bash
  ./manage.sh config SWITCH_USERNAME <新用户名>
  ./manage.sh config SWITCH_PASSWORD <新密码>
  ./manage.sh restart backend
  ```

---

### 2.5 数据源同步失败

**故障现象：**
- 数据源状态显示异常
- 基线数据未更新
- IPGuard 同步报错

**可能原因：**
1. 数据源服务不可达
2. 认证凭据过期
3. 数据格式变更

**排查步骤：**

```bash
# 1. 查看后端日志中的同步错误
./manage.sh logs backend -n 200 | grep -i "sync\|ipguard"

# 2. 检查定时任务状态
./manage.sh scheduler status

# 3. 手动触发同步
./manage.sh scheduler trigger ipguard_sync
```

**解决方案：**

- 服务不可达：检查数据源网络连通性
- 凭据过期：更新数据源配置后重启后端
- 数据格式变更：查看日志中的具体错误，联系数据源提供方确认

---

### 2.6 终端封堵/解封失败

**故障现象：**
- 封堵操作返回失败
- 解封操作无效果
- 终端状态与实际不一致

**可能原因：**
1. Sangfor API 不可用（参见 [2.3](#23-防火墙通信异常sangfor-api-超时)）
2. 交换机通信异常
3. 终端 MAC/IP 信息缺失
4. 操作权限不足

**排查步骤：**

```bash
# 1. 查看后端日志中的封堵/解封错误
./manage.sh logs backend -n 200 | grep -i "block\|unblock"

# 2. 检查终端信息完整性
./manage.sh shell db -c "SELECT id, ip, mac, status FROM terminals WHERE id = '<终端ID>';"

# 3. 检查 Sangfor API 连通性
./manage.sh config | grep -i sangfor

# 4. 检查自动解封任务状态
./manage.sh scheduler status
```

**解决方案：**

- Sangfor API 异常：参见 [2.3](#23-防火墙通信异常sangfor-api-超时)
- 终端信息缺失：先执行 ARP 采集补全信息
  ```bash
  ./manage.sh scheduler trigger arp_collection
  ```
- 状态不一致：手动触发合规检查
  ```bash
  ./manage.sh scheduler trigger compliance_check
  ```

---

### 2.7 登录失败（账户锁定）

**故障现象：**
- 用户登录提示账户已锁定
- 多次输入错误密码后无法登录

**可能原因：**
1. 密码输入错误超过锁定阈值
2. 暴力破解触发安全机制
3. Redis 中锁定记录未正确清除

**排查步骤：**

```bash
# 1. 查看后端日志中的登录失败记录
./manage.sh logs backend -n 200 | grep -i "login\|lockout"

# 2. 查看 Redis 中的锁定键
./manage.sh redis keys "rate_limit:*"
./manage.sh redis keys "lockout:*"

# 3. 查看当前锁定配置
./manage.sh config | grep -i lockout
```

**解决方案：**

- 正常锁定：等待锁定时长过后重试，或由管理员重置
- Redis 锁定键残留：清除对应键
  ```bash
  # 查看锁定键
  ./manage.sh redis keys "rate_limit:*"
  # 删除指定键
  ./manage.sh redis del rate_limit:<username>
  ```
- 调整锁定阈值（需谨慎）：
  ```bash
  ./manage.sh config set lockout_threshold 5
  ./manage.sh config set lockout_duration 900
  ```

---

### 2.8 Redis 连接异常

**故障现象：**
- 后端日志报 Redis 连接错误
- 用户频繁掉线需重新登录
- 定时任务控制失效

**可能原因：**
1. Redis 容器停止
2. Redis 密码不匹配
3. Redis 内存满
4. 网络异常

**排查步骤：**

```bash
# 1. 检查 Redis 容器状态
./manage.sh status

# 2. 测试 Redis 连通性
./manage.sh shell redis -c "PING"

# 3. 查看 Redis 内存使用
./manage.sh redis info | grep used_memory_human

# 4. 查看 Redis 日志
./manage.sh logs redis -n 100
```

**解决方案：**

- 容器停止：重启 Redis
  ```bash
  ./manage.sh restart redis
  ```

- 密码不匹配：检查 `.env` 中 `REDIS_PASSWORD` 与 `docker-compose.yml` 中配置是否一致
  ```bash
  ./manage.sh config REDIS_PASSWORD
  ```

- 内存满：清理或扩容
  ```bash
  # 查看键空间
  ./manage.sh redis keys

  # 清理过期或无用键
  ./manage.sh redis del <key>

  # 必要时清空 Redis
  ./manage.sh -y redis flush
  ```

### 2.9 通知发送失败（SMTP 认证错误）

**故障现象：**
- 通知日志中出现 "AUTH_ERROR: SMTP authentication failed"
- 通知 worker 日志 "Skipping retry for email: SMTP auth failed. Fix email credentials in Settings -> Email Settings."
- 邮件通知全部失败，其他渠道（钉钉/企业微信）正常

**可能原因：**
1. SMTP 用户名/密码错误
2. QQ/163 等邮箱使用了账户密码而非授权码（授权码需在邮箱网页端设置中生成）
3. 邮箱账户被禁用或锁定

**排查步骤：**
1. 进入 系统设置 → 邮件设置，确认 SMTP 主机/端口/用户名/密码配置正确
2. 使用"测试连接"功能验证 SMTP 配置
3. 如使用 QQ/163 邮箱，确认填写的是授权码而非登录密码
4. 检查邮箱账户是否被锁定或禁用

**修复方式：**
- 更新正确的 SMTP 凭证并保存
- 系统会自动跳过认证错误通知的重试，无需手动清理重试队列

---

## 3. 定时任务管理

### 3.1 查看定时任务状态

```bash
./manage.sh scheduler status
```

输出示例：
```
Task                          Interval    Status
─────────────────────────────────────────────────
  ARP Data Collection          5m          RUNNING
  Compliance Baseline Sync     30m         RUNNING
  Firewall Blacklist Query     10m         PAUSED
  Compliance Check             15m         RUNNING
  Auto Unblock                 30m         RUNNING
  Scheduled Backup             cron        RUNNING
```

### 3.2 调整执行间隔

```bash
# 查看当前间隔配置
./manage.sh scheduler intervals

# 修改间隔（单位：秒，范围 30-86400）
./manage.sh config set scheduler_arp_collection_interval 600       # 10 分钟
./manage.sh config set scheduler_compliance_check_interval 1800    # 30 分钟
./manage.sh config set scheduler_firewall_query_interval 300       # 5 分钟
./manage.sh config set scheduler_auto_unblock_interval 3600        # 1 小时
./manage.sh config set scheduler_ipguard_sync_interval 1800        # 30 分钟
./manage.sh config set scheduler_backup_interval 3600             # 1 小时
```

> 修改间隔后无需重启，下次任务循环自动生效。

### 3.3 暂停/恢复定时任务

```bash
# 暂停指定任务
./manage.sh scheduler pause arp_collection
./manage.sh scheduler pause compliance_check
./manage.sh scheduler pause firewall_query
./manage.sh scheduler pause ipguard_sync
./manage.sh scheduler pause auto_unblock

# 恢复已暂停的任务
./manage.sh scheduler resume arp_collection
./manage.sh scheduler resume compliance_check
```

> 暂停机制通过 Redis 键 `scheduler:ctrl:{task}` 实现，被暂停的任务在循环中会被跳过。

### 3.4 手动触发定时任务

```bash
# 手动触发一次合规检查
./manage.sh scheduler trigger compliance_check

# 手动触发 ARP 采集
./manage.sh scheduler trigger arp_collection

# 手动触发防火墙查询
./manage.sh scheduler trigger firewall_query

# 手动触发基线同步
./manage.sh scheduler trigger ipguard_sync

# 手动触发自动解封
./manage.sh scheduler trigger auto_unblock
```

> 手动触发不受暂停状态影响，即使任务已暂停也可手动执行。

---

## 4. 数据源/绑定/基线变更操作规范

### 4.1 新增数据源流程

1. **评估需求**：确认数据源类型、接入方式、数据范围
2. **配置数据源**：通过 Web 界面或 API 添加数据源，填写连接参数
3. **测试连通性**：添加后验证数据源可达性
4. **触发同步**：手动触发一次数据同步，确认数据正常
   ```bash
   ./manage.sh scheduler trigger ipguard_sync
   ```
5. **验证数据**：检查同步后的终端数据和基线数据是否正确
6. **记录变更**：在运维日志中记录新增数据源的操作

### 4.2 修改数据源注意事项

- 修改连接参数前，先暂停相关定时任务
  ```bash
  ./manage.sh scheduler pause ipguard_sync
  ```

- 修改完成后，手动触发同步验证
  ```bash
  ./manage.sh scheduler trigger ipguard_sync
  ```

- 验证通过后恢复定时任务
  ```bash
  ./manage.sh scheduler resume ipguard_sync
  ```

- 修改认证凭据后需重启后端
  ```bash
  ./manage.sh restart backend
  ```

### 4.3 禁用数据源影响评估

禁用数据源前需评估以下影响：

- **终端数据**：该数据源关联的终端将不再更新
- **合规检查**：依赖该数据源的合规规则将无法执行
- **基线数据**：基线将不再从该数据源同步
- **封堵/解封**：若该数据源提供网络设备连接，相关操作将失败

**操作步骤：**

1. 暂停相关定时任务
2. 通过 Web 界面禁用数据源
3. 观察系统运行 30 分钟，确认无异常
4. 记录变更

### 4.4 删除数据源操作流程（两阶段删除）

**第一阶段：软删除（禁用）**

1. 评估影响范围（关联终端数、绑定关系数）
2. 禁用数据源
3. 观察运行 24 小时
4. 确认无业务依赖

**第二阶段：硬删除**

1. 确认所有关联终端已迁移或删除
2. 确认无活跃绑定关系
3. 通过 Web 界面或 API 删除数据源
4. 备份数据库
   ```bash
   ./manage.sh backup
   ```
5. 记录删除操作及原因

> **警告：** 硬删除不可逆，务必先完成软删除观察期。

### 4.5 绑定关系变更注意事项

- 变更绑定关系前，确认终端当前合规状态
- 解除绑定时，终端合规状态将变为"未评估"
- 新增绑定后，建议手动触发合规检查
  ```bash
  ./manage.sh scheduler trigger compliance_check
  ```
- 批量变更绑定关系时，建议在业务低峰期操作
- 变更后观察审计日志，确认操作记录正确

---

## 5. 升级/回滚操作步骤

### 5.1 升级前检查清单

| 检查项 | 命令 | 预期结果 |
|--------|------|----------|
| 服务健康 | `./manage.sh health` | All checks passed |
| 磁盘空间 | `df -h` | 可用空间 ≥ 5GB |
| 当前版本 | `./manage.sh version` | 记录当前版本号 |
| 数据库备份 | `./manage.sh backup` | 备份成功 |
| 配置备份 | `cp .env .env.backup` | 备份文件已创建 |
| 可用更新 | `./manage.sh upgrade --check` | 确认有可用更新 |

### 5.2 升级操作步骤

```bash
# 1. 备份数据库（必须）
./manage.sh backup

# 2. 备份配置文件
cp .env .env.backup

# 3. 检查可用更新
./manage.sh upgrade --check

# 4. 通知用户服务即将中断

# 5. 执行升级（自动：备份 → 拉取代码 → 重建 → 迁移）
./manage.sh upgrade                    # 升级到当前分支最新
./manage.sh upgrade v3.2.0             # 升级到指定 tag
./manage.sh upgrade main               # 升级到指定分支最新

# 6. 升级完成后验证
./manage.sh health
./manage.sh logs backend -n 50
```

> **升级期间服务不可用。** 升级过程自动执行数据库备份、代码拉取、镜像重建、服务重启和数据库迁移。迁移失败时会自动回滚代码并重启。

### 5.3 回滚操作步骤

**场景一：升级后发现问题，回滚到升级前版本**

```bash
# 1. 查看当前版本
git log --oneline -5

# 2. 回滚到升级前的 commit
git checkout <升级前的commit>

# 3. 重建并重启
./manage.sh update

# 4. 恢复数据库（如迁移已执行）
./manage.sh restore backups/backup_<升级前时间戳>.sql

# 5. 验证
./manage.sh health
```

**场景二：数据库迁移失败，自动回滚**

升级过程中如果数据库迁移失败，系统会自动回滚代码并重启。如需手动恢复数据库：

```bash
# 1. 查看自动备份
ls -lht backups/

# 2. 恢复到升级前的备份
./manage.sh restore backups/backup_<时间戳>.sql

# 3. 验证
./manage.sh health
```

### 5.4 升级后验证

| 验证项 | 命令 | 预期结果 |
|--------|------|----------|
| 服务健康 | `./manage.sh health` | All checks passed |
| Web 界面可访问 | `curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/` | 200 |
| 后端日志无异常 | `./manage.sh logs backend -n 50` | 无 ERROR |
| 定时任务正常 | `./manage.sh scheduler status` | 所有任务 RUNNING |
| 数据库版本 | `./manage.sh shell db -c "SELECT version_num FROM alembic_version;"` | 最新版本号 |
| 数据完整性 | `./manage.sh shell db -c "SELECT count(*) FROM terminals;"` | 终端数量正常 |

---

## 6. v3.10.0 变更记录

### 6.1 备份恢复操作变更

> v3.10.0 变更：
> - 备份恢复新增白名单恢复和日志恢复步骤
> - 系统配置 DB 恢复使用 begin_nested() 逐表事务保护
> - 远程备份过期自动清理（SFTP/FTP）

### 6.2 告警阈值配置

> v3.10.0 变更：
> - 新增「告警阈值配置」分区，可在系统设置中自定义：
>   - 合规率告警阈值（默认 80%）
>   - 合规率危险比例（默认 50%）
>   - 封锁数量告警阈值（默认 50）
>   - 离线检测倍数（默认 3）
