# 修复 Nginx 端口绑定和后端目录权限问题

## 问题概述

用户将 `.env` 中的端口改为 `80`/`443`/`8001`，引发两个错误：

### 问题 1: Nginx 绑定 80 端口失败
```
bind() to 0.0.0.0:80 failed (13: Permission denied)
```

**根因**: Nginx 容器以 root 运行（nginx:alpine 默认），但 `docker-compose.yml` 基础配置中 nginx 服务的 `cap_drop`/`cap_add` 被注释，未启用。虽有 `docker-compose.prod.yml` 配置了完整的能力列表，但用户可能未使用 prod 配置启动，或者基础配置的注释导致配置不完整。

**修复方案**: 取消 `docker-compose.yml` 中 nginx 服务的安全配置注释，**包含完整的 4 项能力**（NET_BIND_SERVICE + CHOWN + SETUID + SETGID），确保无论 dev 还是 prod 模式都能绑定特权端口并正常启动 worker 进程。

### 问题 2: 后端备份目录权限不足
```
Permission denied for backup directory /app/uploads/backups, using /tmp/backups instead
```

**根因**: Docker 卷 `backend-data` 挂载到 `/app/uploads`，新卷根目录归 root 所有，而后端以 `app` 用户（UID 1000）运行，无写权限。Dockerfile 中的 `chown` 只在构建时生效，卷挂载后会被覆盖。

**修复方案**: 添加 `entrypoint.sh` 启动脚本，以 root 身份修正卷权限后再切换到 app 用户运行 uvicorn。

## 修复计划

### 1. docker-compose.yml - 启用 nginx 安全配置

**文件**: [docker-compose.yml#L206-L213](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L206-L213)

将 nginx 服务中被注释的安全配置**取消注释**，保留完整 4 项能力：
```yaml
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
      - CHOWN
      - SETUID
      - SETGID
```

同时从 `docker-compose.prod.yml` 中移除 nginx 的重复安全配置（避免列表覆盖风险）。

### 2. backend/docker-entrypoint.sh - 创建启动脚本

**新建文件**: backend/docker-entrypoint.sh

脚本逻辑：
1. 以 root 身份修复 `/app/uploads` 目录权限（`chown -R app:app`）
2. 创建必要的子目录（backups、branding）
3. 切换到 app 用户执行 uvicorn

```bash
#!/bin/sh
set -e

# Fix volume permissions (runs as root before dropping privileges)
if [ -d /app/uploads ]; then
    chown -R app:app /app/uploads 2>/dev/null || true
    mkdir -p /app/uploads/backups /app/uploads/branding 2>/dev/null || true
    chown -R app:app /app/uploads/backups /app/uploads/branding 2>/dev/null || true
fi

# Switch to app user and run uvicorn
exec su - app -c "exec uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8000}"
```

### 3. backend/Dockerfile - 添加 entrypoint 和 su 工具

**文件**: [backend/Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile)

- 在 builder 阶段安装 `su-exec`（轻量替代 su），或直接用 `su`
- 复制 `docker-entrypoint.sh` 到镜像
- 修改 CMD 为 ENTRYPOINT

修改内容：
```dockerfile
# Install su-exec for privilege dropping
RUN apk add --no-cache su-exec

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Remove USER app (entrypoint handles privilege dropping)
# CMD replaced by ENTRYPOINT
ENTRYPOINT ["docker-entrypoint.sh"]
```

### 4. docker-compose.yml - 更新 backend 服务

移除 `backend` 服务的 `USER app` 依赖（由 entrypoint 处理权限降级）。

### 5. 重置卷并重建验证

删除旧的 `tam_backend-data` 卷，重建后端镜像，验证权限修复。

## 假设与决策

- 用户故意使用 80/443 标准端口，需要支持
- Docker Compose 列表合并策略：`cap_add` 在 override 文件中会**替换**而非追加基础配置，因此将完整能力列表放在基础配置中，从 prod 覆盖中移除
- `su-exec` 是 Alpine 镜像中最轻量的权限降级方案

## 风险评估

- **低风险**: 启用 nginx 的 security_opt 和 cap_drop/cap_add 是标准安全加固
- **低风险**: entrypoint 脚本在容器启动时修正卷权限，不影响数据
- **注意**: cap_drop ALL + cap_add 4 项已在之前的会话中验证可行（解决了 setgid(101) failed 错误）