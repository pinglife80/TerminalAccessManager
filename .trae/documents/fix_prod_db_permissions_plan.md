# 修复 prod 模式下 postgres 和 redis 启动失败问题

## 问题分析

### 报错现象
```
tam_redis  | setpriv: setresuid failed: Operation not permitted
tam_db     | chmod: /var/lib/postgresql/data: Operation not permitted
tam_db     | chown: /var/run/postgresql: Operation not permitted
tam_db exited with code 1 (restarting)
tam_redis exited with code 127 (restarting)
```

### 根因
`docker-compose.prod.yml` 对 postgres 和 redis 服务应用了错误的安全加固配置：
- `security_opt: no-new-privileges: true`
- `cap_drop: [ALL]`

**为什么会失败：**

1. **PostgreSQL** 官方镜像（`postgres:16-alpine`）
   - 启动时执行 `/docker-entrypoint.sh`，需要 `chown postgres:postgres /var/lib/postgresql/data` 和 `chmod 700`
   - `cap_drop: [ALL]` 剥夺了 `CAP_CHOWN`、`CAP_FOWNER` 等 capabilities
   - `no-new-privileges: true` 阻止 setuid/setgid 生效
   - 结果：`Operation not permitted`，数据库数据目录权限无法修正

2. **Redis** 官方镜像（`redis:7-alpine`）
   - 启动时执行 `/usr/local/bin/docker-entrypoint.sh`，通过 `redis-server --user redis` 降权运行
   - 需要 `setresuid`/`setresgid` 系统调用
   - `no-new-privileges: true` 直接阻断 `setpriv` 操作
   - `cap_drop: [ALL]` 剥夺 `CAP_SETUID`、`CAP_SETGID`
   - 结果：`setpriv: setresuid failed: Operation not permitted`，容器以 127 退出码崩溃

### 为什么业务服务（backend/nginx）没问题
- backend 和 nginx 是应用层服务，不需要在容器启动时执行文件所有权变更或用户切换
- 安全加固（`no-new-privileges` + `cap_drop: ALL` + `read_only`）对它们是有效的防御措施

## 修改方案

### 文件修改
**文件**: `docker-compose.prod.yml`

**修改内容**: 移除 postgres 和 redis 的安全加固配置块

**Before**:
```yaml
services:
  postgres:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL

  redis:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL

  backend:
    ...
```

**After**:
```yaml
services:
  backend:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    read_only: true
    tmpfs:
      - /tmp
```

## 验证步骤

### 1. 重建容器
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 2. 检查容器状态
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```
预期 postgres 和 redis 状态为 `Up`。

### 3. 查看日志确认
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs postgres --tail 20
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs redis --tail 20
```
预期不再出现 `Operation not permitted` 错误。

## 风险评估

### 降低的安全防护
- postgres 和 redis 将不再受 `no-new-privileges` 和 `cap_drop: ALL` 保护
- 如果 postgres 或 redis 镜像本身存在 0day 漏洞，攻击者理论上可以提权

### 风险可控性
1. **官方镜像信任**：postgres 和 redis 使用官方镜像，维护良好，历史上极少出现严重的容器逃逸漏洞
2. **网络隔离**：在 docker compose 网络内，postgres/redis 仅对 backend 开放端口，外部无法直接访问
3. **数据卷隔离**：postgres 使用 `tam_db_data` 命名卷，与宿主机文件系统隔离
4. **基础服务例外**：这是业界最佳实践——数据库容器通常不施加 `cap_drop: ALL`，因为它们需要初始化时修改文件所有权
5. **最小化暴露**：backend 和 nginx 仍然保留完整安全加固

### 后续可选优化
- 如果需要，可以在 postgres/redis 上仅添加特定的 capabilities（如 `cap_add: [CHOWN, FOWNER, SETUID, SETGID]`），但这增加了复杂性且收益有限
- 对于生产环境，建议在宿主机层面使用 Docker User Namespace remapping（`userns-remap`）来提供更强隔离，而不是依赖容器内 capabilities

## 实施

Step 1: 删除 postgres 和 redis 的 security_opt 和 cap_drop 配置
Step 2: 重建并重启容器
Step 3: 验证容器启动状态
Step 4: 验证数据库连接和基本功能
