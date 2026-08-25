# 容器安全加固取消后的权限风险评估与修复计划

> 文档版本：v1.0  更新日期：2026-08-10

---

## 一、核心结论

**按照当前方案直接修改，系统在构建启动时会存在 3 个高风险权限问题，1 个中风险配置残留问题。** 必须在部署前完成以下修复，否则会导致：后端文件日志静默失效、品牌资源上传失败、数据库备份写入失败、Nginx 缓存目录无法写入等功能性故障。

| # | 风险点 | 影响范围 | 严重程度 |
|---|--------|----------|----------|
| 1 | backend/Dockerfile 缺少 `/var/log/tam` 目录预创建与权限设置 | 后端文件日志静默失效（仅stdout输出，无持久化文件） | 高 |
| 2 | backend `/app/uploads` 挂载点首次挂载为 root:root，app 用户无写权限 | 品牌图片上传失败、备份 ZIP 写入失败、branding/backups 子目录无法创建 | 高 |
| 3 | Nginx 自定义 entrypoint 未处理 tmpfs 目录权限，覆盖官方镜像初始化逻辑 | `/var/cache/nginx` 和 `/var/run` 为 root:root，worker 进程（UID 101）写入失败导致启动异常 | 高 |
| 4 | docker-compose.yml 仍残留安全加固注释块 + 冗余 tmpfs 配置（postgres /var/run/postgresql、backend /tmp） | 配置不清晰，维护时易产生误解 | 中 |

---

## 二、风险点详细分析

### 风险 1：`/var/log/tam` 日志目录权限（高风险）

#### 根因
Docker named volume 首次挂载规则：
- 若镜像内**不存在**挂载点目录 → Docker 以 `root:root` 创建该目录
- 容器运行用户为 `app`（非 root，UID 由 `adduser -D app` 分配，通常为 1000）
- 结果：app 用户对 `/var/log/tam` 无写入权限

#### 当前代码状态
[backend/Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile) 中**缺少**以下关键行：
```dockerfile
RUN mkdir -p /var/log/tam && chown app:app /var/log/tam
```

#### 故障表现
- [logging_config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/logging_config.py#L132-L147) 中 `logger.add("/var/log/tam/app.log", ...)` 抛出 PermissionError
- 被 try-except 静默捕获，仅输出一行 warning，文件日志完全不工作
- 容器重启后日志无持久化，无法回溯历史问题

---

### 风险 2：`/app/uploads` 上传目录权限（高风险）

#### 根因
与风险 1 相同的 volume 首次挂载机制：
- 镜像构建时虽然执行了 `RUN chown -R app:app /app`，但如果代码仓库中**没有** `backend/uploads/` 目录（且未在 Dockerfile 中显式创建），则镜像内 `/app/uploads` 不存在
- named volume `backend-data` 首次挂载时，Docker 以 `root:root` 创建 `/app/uploads` 挂载点
- 应用启动时 `_ensure_upload_dir()` 中的 `os.makedirs(UPLOAD_DIR, exist_ok=True)` **不会修改已有目录的所有者**

#### 涉及代码路径
1. **品牌资源上传**：[settings.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/settings.py#L267-L270)
   ```python
   filepath = os.path.join(UPLOAD_DIR, filename)
   with open(filepath, "wb") as f:  # PermissionError!
       f.write(content)
   ```

2. **备份目录创建**：[backup_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L95-L98)
   ```python
   self.backup_dir = os.path.join(settings.UPLOAD_DIR, "backups")
   os.makedirs(self.backup_dir, exist_ok=True)  # PermissionError!
   ```

3. **branding 子目录创建**：[backup_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L631-L633)
   ```python
   branding_dir = os.path.join(upload_dir, "branding")
   os.makedirs(branding_dir, exist_ok=True)  # PermissionError!
   ```

#### 故障表现
- 系统设置 → 品牌定制：上传图片返回 500 错误
- 备份管理：手动/自动备份均失败，报 `[Errno 13] Permission denied`
- 备份恢复：恢复 ZIP 中 branding 资源时无法写入目标目录

---

### 风险 3：Nginx tmpfs 目录权限（高风险）

#### 根因
[docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L242-L244) 中 Nginx 配置了两个 tmpfs：
```yaml
tmpfs:
  - /var/cache/nginx
  - /var/run
```

问题链：
1. 官方 `nginx:alpine` 镜像默认 entrypoint 会在启动前调整 `/var/cache/nginx`、`/var/run` 等目录的所有者为 `nginx:nginx`（UID 101），确保 worker 进程可写
2. 但我们通过 `entrypoint: ["/docker-entrypoint.sh"]` **覆盖了官方 entrypoint**
3. 自定义的 [nginx/docker-entrypoint.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/docker-entrypoint.sh) **仅做了 envsubst 和 nginx -t**，没有执行权限调整
4. tmpfs 挂载后默认所有者为 `root:root`，权限 755
5. Nginx worker 进程以 `nginx` 用户（UID 101）运行，对上述目录无写权限

#### 故障表现
- Nginx 启动时报错：
  ```
  [alert] 1#1: mkdir() "/var/cache/nginx/client_temp" failed (13: Permission denied)
  [emerg] 1#1: chown("/var/cache/nginx", 101) failed (1: Operation not permitted)
  ```
- 若容器有 `cap_drop: ALL` 历史残留则更严重，但即使无 cap_drop，worker 进程切换用户后仍然无法写入 root 所有的目录
- HTTPS 请求处理失败，proxy 临时文件无法创建

---

### 风险 4：安全加固残留与冗余 tmpfs（中风险）

#### 当前残留内容
[docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml) 中：

1. **4 处安全加固注释块未删除**（L37-L41 postgres、L72-L76 redis、L162-L167 backend、L198-L202 frontend）
2. **postgres tmpfs**（L42-L43）：`/var/run/postgresql` — 此为 postgres socket 目录，原配合 `read_only: true` 使用。取消安全加固后非必须，但 postgres 官方镜像依赖该目录存在，需谨慎评估
3. **backend tmpfs**（L168-L169）：`/tmp` — 原配合 `read_only: true` 使用。取消安全加固后，/tmp 可写入容器层，tmpfs 非必须但无害
4. **nginx tmpfs**（L242-L244）：见风险 3 分析

---

## 三、修复方案

### 修复 1：backend/Dockerfile — 预创建挂载点目录并设置权限

#### 修改文件
[backend/Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile)

#### 修改位置
在 `RUN chown -R app:app /app` 之后、`USER app` 之前插入：

```dockerfile
# Pre-create volume mount points with correct ownership.
# Docker named volumes copy content+perms from image ONLY on first mount,
# so we must ensure these dirs exist and are owned by app:app BEFORE USER directive.
RUN mkdir -p /var/log/tam && \
    mkdir -p /app/uploads/backups && \
    mkdir -p /app/uploads/branding && \
    chown -R app:app /var/log/tam /app/uploads
```

#### 原理
- 在构建阶段（root 用户）创建挂载点及其必要子目录
- 设置所有者为 `app:app`
- 当 named volume 首次挂载时，Docker 会将镜像内该目录的内容和权限**复制**到 volume 中，从而保证运行时 app 用户可写

---

### 修复 2：nginx/docker-entrypoint.sh — 补充 tmpfs 权限调整

#### 修改文件
[nginx/docker-entrypoint.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/docker-entrypoint.sh)

#### 修改位置
在 `set -e` 之后、envsubst 之前插入：

```sh
# Fix ownership of directories that may be mounted as tmpfs.
# The official nginx entrypoint normally does this, but we override it.
# Worker process runs as 'nginx' user (UID 101), needs write access to:
#   - /var/cache/nginx (client_temp, proxy_temp, fastcgi_temp, etc.)
#   - /var/run (pid file, sockets)
if [ -d /var/cache/nginx ]; then
    chown -R nginx:nginx /var/cache/nginx
fi
if [ -d /var/run ]; then
    chown -R nginx:nginx /var/run
fi
# Create nginx temp subdirs (client_temp etc.) if missing
nginx -T >/dev/null 2>&1 || true
```

#### 原理
- Nginx master 进程以 root 启动（能执行 chown）
- 在 worker fork 之前调整目录所有者，确保切换到 nginx 用户后可写
- 同时兼容非 tmpfs 场景（正常挂载时也不会有副作用）

---

### 修复 3：docker-compose.yml — 清理残留 + 调整 tmpfs

#### 修改文件
[docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml)

#### 修改项 A：删除 4 处安全加固注释块
删除以下行：
- L37-L41：`# Production hardening (uncomment for production):` + 后续 4 行注释（postgres）
- L72-L76：同上（redis）
- L162-L167：同上（backend，含 `# read_only: true`）
- L198-L202：同上（frontend）

#### 修改项 B：删除 postgres 和 backend 的冗余 tmpfs
- 删除 L42-L43：`tmpfs: - /var/run/postgresql`（postgres 官方镜像会自行创建 socket 目录，非 read_only 模式下无需 tmpfs）
- 删除 L168-L169：`tmpfs: - /tmp`（取消 read_only 后，容器层 /tmp 默认可写）
- **保留** nginx 的 tmpfs（L242-L244）：/var/cache/nginx 频繁 IO，tmpfs 可延长磁盘寿命且提升性能，配合修复 2 权限正确

#### 修改后验证
```
postres: 无 tmpfs，无 hardening 注释
redis:    无 hardening 注释
backend:  无 tmpfs，无 hardening 注释
frontend: 无 hardening 注释
nginx:    保留 tmpfs (/var/cache/nginx, /var/run)，无 hardening 注释
```

---

## 四、完整验证步骤（修复后执行）

### 4.1 构建阶段验证
```bash
# 清理旧的容器和 volume（重要！否则旧 volume 权限残留影响判断）
./manage.sh down
docker volume rm tam_backend-logs tam_backend-data tam_postgres_data tam_redis_data tam_frontend_dist 2>/dev/null || true
docker volume prune -f

# 重建镜像（确保 Dockerfile 变更生效）
docker compose build --no-cache backend frontend

# 验证 backend 镜像内目录权限
docker run --rm --entrypoint sh tam-backend -c "ls -ld /var/log/tam /app/uploads /app/uploads/backups /app/uploads/branding"
# 预期输出所有者均为 app:app
```

### 4.2 启动阶段验证
```bash
./manage.sh up

# 1. 验证后端文件日志
docker exec tam_backend sh -c "ls -l /var/log/tam/ && stat -c '%U:%G' /var/log/tam"
# 预期：app.log 存在，所有者 app:app

# 2. 验证上传目录可写
docker exec tam_backend sh -c "touch /app/uploads/test_write && rm /app/uploads/test_write && echo OK"
docker exec tam_backend sh -c "touch /app/uploads/backups/test_write && rm /app/uploads/backups/test_write && echo OK"
docker exec tam_backend sh -c "touch /app/uploads/branding/test_write && rm /app/uploads/branding/test_write && echo OK"
# 预期：均输出 OK

# 3. 验证 Nginx 权限
docker logs tam_nginx 2>&1 | grep -i "permission denied\|failed" || echo "No permission errors"
docker exec tam_nginx sh -c "stat -c '%U:%G' /var/cache/nginx /var/run"
# 预期：nginx:nginx，无 Permission denied 错误

# 4. 健康检查全绿
./manage.sh health
```

### 4.3 功能链验证
```bash
# 品牌上传测试（通过 API）
./manage.sh user login <admin> <password>  # 获取 token
# 调用 POST /api/v1/settings/upload?purpose=favicon 上传一张小图
# 预期：返回 200 且 /app/uploads 下生成 UUID 文件名

# 备份测试
./manage.sh backup create
# 预期：备份成功，/app/uploads/backups/ 下生成 ZIP 文件且大小 > 0
```

---

## 五、回滚预案

若修复后出现异常，按以下步骤快速回滚：

| 修复项 | 回滚操作 |
|--------|----------|
| backend/Dockerfile 目录创建 | 删除新增的 RUN mkdir/chown 行，重建镜像 |
| nginx/docker-entrypoint.sh 权限调整 | 删除新增的 chown 块，重建 nginx 容器 |
| docker-compose.yml 注释/tmpfs 删除 | 从 git 恢复原文件，重新 `./manage.sh up` |

**注意**：任何修改后都必须执行 `docker compose build` 重建对应镜像，不能仅 restart 容器（Dockerfile 变更不会生效）。
