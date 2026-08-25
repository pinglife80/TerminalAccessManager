# 修复 prod 模式下 nginx 启动失败问题

## 问题分析

### 报错现象
```
tam_nginx | nginx: [emerg] chown("/var/cache/nginx/client_temp", 101) failed (1: Operation not permitted)
```
nginx 容器不断崩溃重启。

### 根因
`docker-compose.prod.yml` 中 nginx 服务配置了 `cap_drop: [ALL]`，仅添加了 `cap_add: [NET_BIND_SERVICE]`。

nginx 官方镜像的 `/docker-entrypoint.sh` 启动时会执行：
```bash
chown -R nginx:nginx /var/cache/nginx
```
将缓存目录所有权改为 nginx 用户(uid 101)。此操作需要 `CAP_CHOWN`，但 `cap_drop: [ALL]` 已将其剥夺，导致 `Operation not permitted`。

### 为什么 backend 没问题
backend Dockerfile 中 `USER app` 在构建时就完成了用户切换，运行时不需要 `chown`。而 nginx 镜像以 root 启动，entrypoint 脚本运行时动态 `chown` 缓存目录。

## 修改方案

### 文件: `docker-compose.prod.yml`

在 nginx 服务的 `cap_add` 列表中添加 `CHOWN`：

**Before** (第20-21行):
```yaml
    cap_add:
      - NET_BIND_SERVICE
```

**After**:
```yaml
    cap_add:
      - NET_BIND_SERVICE
      - CHOWN
```

### 设计决策
选择添加 `CHOWN` 而非移除整个 `cap_drop`：
- 保留 `cap_drop: [ALL]` 的基线防护，仅放行 nginx entrypoint 必需的 `CHOWN`
- `NET_BIND_SERVICE` 用于绑定 <1024 端口（虽然当前用 8080/8443，保留以备未来需要）
- `CHOWN` 仅允许更改文件所有权，不引入提权风险
- `read_only: true` + `tmpfs` 仍然有效，root 文件系统依然只读

## 验证步骤

1. 重建 nginx 容器：
   ```bash
   docker rm -f tam_nginx
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d nginx
   ```

2. 检查状态：
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps nginx
   ```
   预期状态为 `Up`。

3. 查看日志：
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml logs nginx --tail 10
   ```
   预期不再出现 `Operation not permitted`。

4. 验证 HTTP 可访问：
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/
   ```
   预期返回 200 或 301。
