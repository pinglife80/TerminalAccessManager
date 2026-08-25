# 修复端口硬编码、备份清理、Mixed Content 三个问题

## 问题分析

### 问题 1: 端口硬编码 (HIGH)

**现状**: 项目中多个位置硬编码了端口号，无法通过配置修改：

| 文件                              | 硬编码端口                                  | 用途           |
| ------------------------------- | -------------------------------------- | ------------ |
| `nginx/etc/conf.d/tam.conf:19`  | `listen 8080`                          | HTTP server  |
| `nginx/etc/conf.d/tam.conf:28`  | `listen 8443 ssl`                      | HTTPS server |
| `nginx/etc/conf.d/tam.dev.conf` | 同上                                     | dev 模式       |
| `backend/Dockerfile:45`         | `EXPOSE 8000`                          | 容器暴露端口       |
| `backend/Dockerfile:49`         | `curl -f http://localhost:8000/health` | 健康检查         |
| `backend/Dockerfile:52`         | `--port 8000`                          | uvicorn 启动   |
| `docker-compose.yml:90`         | `127.0.0.1:8000:8000`                  | backend 端口映射 |
| `docker-compose.yml:191`        | `wget http://localhost:8080/`          | nginx 健康检查   |
| `manage.sh`                     | 8080, 8443                             | 10 处 curl 检查 |

**修复方案**:

1. 在 `.env` 中添加端口配置变量（统一管理）
2. Nginx 配置使用 `envsubst` 在启动时替换端口
3. Dockerfile 使用 ARG/ENV 变量
4. Docker Compose 使用环境变量
5. manage.sh 从 `.env` 读取端口

### 问题 2: 历史垃圾备份文件被打包 (MEDIUM)

**根因确认**: 4 个历史备份文件存在于项目源代码目录 `backend/uploads/backups/` 中，在 Docker 构建时被 `COPY . .` 打包进镜像。

**发现的文件**:

* `backend/uploads/backups/backup_20260701_142620.zip`

* `backend/uploads/backups/backup_20260701_142313.zip`

* `backend/uploads/backups/backup_20260701_142211.zip`

* `backend/uploads/backups/backup_20260701_142011.zip`

**问题**:

* `backend/.dockerignore` 中未排除 `uploads/backups/` 目录

* 这些文件是历史测试/调试产物，不应存在于源代码中

**修复方案**:

1. 删除源代码中的历史备份文件
2. 更新 `backend/.dockerignore` 排除 `uploads/backups/`
3. 创建 `backend/.gitignore` 防止未来提交备份文件
4. 在 `_cleanup_old_backups()` 中添加 0 字节文件清理作为双重保障

### 问题 3: Mixed Content HTTPS→HTTP (CRITICAL)

**根因**: FastAPI/Starlette 的 trailing slash redirect（`/api/v1/channels/` → `/api/v1/channels`）使用 HTTP 而非 HTTPS，因为后端不知道原始请求协议。

浏览器日志显示:

```
GET http://10.8.25.121:8443/api/v1/notifications/channels 
(redirected from https://10.8.25.121:8443/api/v1/notifications/channels/)
```

**修复方案**: 在 nginx location 块中添加 `proxy_redirect http:// https://;`

## 修改方案

### 修改 1: 端口配置变量化

#### 1.1 `.env` 添加端口变量

在 `[APPLICATION]` 段落后添加：

```env
# ==============================================================================
# [PORTS] Service Port Configuration
# ==============================================================================
# Nginx HTTP port (dev mode / HTTP redirect)
TAM_NGINX_PORT=8080
# Nginx HTTPS port (prod mode)
TAM_NGINX_SSL_PORT=8443
# Backend API port (internal)
TAM_BACKEND_PORT=8000
```

#### 1.2 创建 nginx entrypoint 脚本

**新文件**: `nginx/docker-entrypoint.sh`

```bash
#!/bin/sh
set -e

# Replace environment variables in nginx config template
if [ -f /etc/nginx/conf.d/default.conf.template ]; then
    envsubst < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
    echo "nginx: environment variables substituted in config"
fi

exec "$@"
```

#### 1.3 将 nginx 配置改为模板

**新文件**: `nginx/etc/conf.d/tam.conf.template`

* 复制 `tam.conf` 内容

* 将 `listen 8080` 改为 `listen ${TAM_NGINX_PORT}`

* 将 `listen 8443 ssl` 改为 `listen ${TAM_NGINX_SSL_PORT} ssl`

**新文件**: `nginx/etc/conf.d/tam.dev.conf.template`

* 同上处理

#### 1.4 修改 docker-compose.yml

nginx 服务：

```yaml
nginx:
  environment:
    TZ: ${TZ:-Asia/Shanghai}
    TAM_NGINX_PORT: ${TAM_NGINX_PORT:-8080}
    TAM_NGINX_SSL_PORT: ${TAM_NGINX_SSL_PORT:-8443}
  volumes:
    - ./nginx/etc/conf.d/tam.conf.template:/etc/nginx/conf.d/default.conf.template:ro
    - ./nginx/docker-entrypoint.sh:/docker-entrypoint.d/40-envsubst.sh:ro
  healthcheck:
    test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider --no-check-certificate https://localhost:${TAM_NGINX_SSL_PORT:-8443}/health || exit 1"]
```

backend 服务：

```yaml
backend:
  ports:
    - "127.0.0.1:${TAM_BACKEND_PORT:-8000}:${TAM_BACKEND_PORT:-8000}"
  environment:
    BACKEND_PORT: ${TAM_BACKEND_PORT:-8000}
```

#### 1.5 修改 backend/Dockerfile

```dockerfile
# Add ARG for configurable port
ARG BACKEND_PORT=8000

# Use ARG in EXPOSE, HEALTHCHECK, and CMD
EXPOSE ${BACKEND_PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${BACKEND_PORT}/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${BACKEND_PORT}"]
```

#### 1.6 修改 manage.sh

在函数开头添加端口变量读取：

```bash
# Read port configuration from .env
NGINX_PORT=$(get_env "TAM_NGINX_PORT" || echo "8080")
NGINX_SSL_PORT=$(get_env "TAM_NGINX_SSL_PORT" || echo "8443")
BACKEND_PORT=$(get_env "TAM_BACKEND_PORT" || echo "8000")
```

替换所有硬编码端口（8080, 8443）为变量引用。

### 修改 2: 清理历史垃圾备份文件

#### 2.1 删除源代码中的历史备份文件

**删除文件**:

* `backend/uploads/backups/backup_20260701_142620.zip`

* `backend/uploads/backups/backup_20260701_142313.zip`

* `backend/uploads/backups/backup_20260701_142211.zip`

* `backend/uploads/backups/backup_20260701_142011.zip`

保留 `backend/uploads/backups/.gitkeep` 目录占位文件。

#### 2.2 更新 backend/.dockerignore

添加排除规则：

```
# Backup files - generated at runtime, not in source
uploads/backups/
backups/
*.zip
```

#### 2.3 创建 backend/.gitignore

```
# Runtime generated files
uploads/backups/
backups/
*.zip
uploads/
```

#### 2.4 增强 backup\_service.py 清理逻辑

**文件**: `backend/app/services/backup_service.py`

在 `_cleanup_sync` 中添加 0 字节文件检查：

```python
file_size = os.path.getsize(file_path)
file_age = now - os.path.getmtime(file_path)
if file_size == 0:
    os.remove(file_path)
    logger.info(f"Removed empty backup file: {filename}")
elif file_age > retention_seconds:
    os.remove(file_path)
    logger.info(f"Removed old local backup: {filename}")
```

### 修改 3: Nginx proxy\_redirect

**文件**: `nginx/etc/conf.d/tam.conf.template`

在以下 location 块中添加 `proxy_redirect http:// https://;`：

* `/api/` (原 L103-123)

* `/api/v1/auth/login` (原 L126-135)

* `/metrics` (原 L138-149)

## 实施步骤

1. 添加 `.env` 端口变量
2. 创建 nginx entrypoint 脚本 (`nginx/docker-entrypoint.sh`)
3. 创建 nginx 配置模板 (`.template` 文件)
4. 修改 `docker-compose.yml` 使用变量
5. 修改 `backend/Dockerfile` 使用 ARG
6. 修改 `manage.sh` 读取端口变量
7. 删除历史垃圾备份文件 (4 个 .zip 文件)
8. 更新 `backend/.dockerignore` 排除备份目录
9. 创建 `backend/.gitignore` 防止提交备份
10. 修改 `backup_service.py` 清理逻辑
11. 修改 nginx 配置添加 `proxy_redirect`
12. 语法验证
13. 重建服务并验证

## 风险评估

1. **端口变量化**: 中等风险。需确保所有端口引用都已更新，模板变量语法正确。
2. **备份清理**: 低风险。仅添加 0 字节文件清理。
3. **proxy\_redirect**: 低风险。仅重写 Location 头，不影响正常代理请求。

## 验证步骤

1. 语法检查:

   * `bash -n manage.sh`

   * `python3 -c "import ast; ast.parse(open('backend/app/services/backup_service.py').read())"`

   * `docker compose config` 检查配置合并

2. 重建并启动:

   ```bash
   ./manage.sh rebuild nginx
   ./manage.sh rebuild backend
   ```

3. 验证:

   * `./manage.sh status` — nginx healthy

   * 浏览器访问 HTTPS 页面 — 无 Mixed Content 错误

   * 容器内备份目录应为空：`docker compose exec backend ls /app/uploads/backups/`

   * `./manage.sh health` — 无卡住

4. 端口可配置验证:

   * 修改 `.env` 中的 `TAM_NGINX_PORT=9090`

   * 重启 nginx 容器，验证新端口生效

