# 修复 Nginx 端口配置和后端 uvicorn 模块问题

## 问题根因分析

### 问题 1: 后端 `ModuleNotFoundError: No module named 'uvicorn'`

**根因**: 上一步移除安全加固时，删除了 Dockerfile 中的 `USER app`。但 pip 包通过 `--user` 安装到 `/home/app/.local/`，运行身份为 root 时 Python 不搜索该路径。

**修复**: 恢复 `USER app`。卷权限问题之前是由 `read_only: true` + `cap_drop: ALL` 导致的，这些已移除，`USER app` 本身不影响卷写入。

### 问题 2: Nginx `bind() to 0.0.0.0:80 failed`

**根因链**:

1. [tam.conf](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf) 被直接编辑为 `listen 80;` / `listen 443 ssl;`（之前改端口的遗留）
2. [docker-entrypoint.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/docker-entrypoint.sh) 用 `sed` 替换 `listen 8080;` → 实际端口，但配置文件中没有 `8080`，sed 无效
3. Nginx 实际尝试绑定 80 端口 → Permission denied

**已有正确方案**: [tam.conf.template](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf.template) 已使用 `${TAM_NGINX_PORT}` 占位符，但从未被使用。

### 问题 3: 后端端口未变量化

所有 nginx 配置中 `upstream backend_api { server 127.0.0.1:8000; }` 硬编码 8000，但 `.env` 中 `TAM_BACKEND_PORT` 可改为其他值。

### 回答用户问题

> nginx 是 host 网络模式，.env 指定的端口能改变实际服务启动端口吗？

**能**。docker-compose.yml 将 `TAM_NGINX_PORT` 作为环境变量传入容器，entrypoint 读取后替换配置中的端口号。host 网络模式下 nginx 直接监听该端口。**但当前实现是坏的**，因为 sed 替换依赖固定的原始值，配置被直接编辑后就失效了。

## Dev vs Prod 差异分析（删除两个 override 文件后）

删除 `docker-compose.dev.yml` 和 `docker-compose.prod.yml` 后，**Docker 容器配置完全一致**，差异仅存在于 `.env` 中（由 manage.sh 的不同向导生成）：

| 维度                         | Dev 模式               | Prod 模式               | 控制方式                  |
| -------------------------- | -------------------- | --------------------- | --------------------- |
| `ENVIRONMENT`              | `development`        | `production`          | .env 变量               |
| API 文档 (`/docs`, `/redoc`) | 可用                   | 禁用                    | 后端代码根据 ENVIRONMENT 判断 |
| 日志格式                       | 文本                   | JSON                  | 后端代码根据 ENVIRONMENT 判断 |
| 启动校验                       | 宽松                   | 严格（校验 SECRET\_KEY 强度） | 后端代码根据 ENVIRONMENT 判断 |
| 密码                         | 自动生成弱密码 (`Admin123`) | 交互式输入强密码              | manage.sh 向导逻辑        |
| 集成配置                       | 清空                   | 保留/配置                 | manage.sh 向导逻辑        |

**结论**: 两个 override 文件均可安全删除。dev/prod 差异由 `.env` 中的 `ENVIRONMENT` 变量和 manage.sh 配置向导控制，与 Docker 容器配置无关。

## 冗余文件清单

| 文件                                   | 状态                     | 处理                                |
| ------------------------------------ | ---------------------- | --------------------------------- |
| `nginx/etc/conf.d/tam.conf`          | 被直接编辑，端口错误             | **删除** — 用 template + envsubst 替代 |
| `nginx/etc/conf.d/tam.conf.template` | 正确的模板，有 `${}` 占位符      | **保留** — 作为唯一配置源                  |
| `nginx/etc/conf.d/tam.dev.conf`      | 硬编码 8080，仅被 dev.yml 引用 | **删除** — template 统一适配            |
| `docker-compose.dev.yml`             | 仅覆盖 nginx 配置为 dev.conf | **删除** — 不再需要                     |
| `docker-compose.prod.yml`            | 已清空，占位文件               | **删除** — 不再需要                     |

## 修复计划

### 1. backend/Dockerfile — 恢复 USER app

**文件**: [backend/Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile)

将 `# Note: Running as root...` 注释替换为 `USER app`：

```dockerfile
RUN chown -R app:app /app
USER app
```

### 2. tam.conf.template — 添加后端端口变量

**文件**: [nginx/etc/conf.d/tam.conf.template](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf.template#L15-L18)

```nginx
upstream backend_api {
    server 127.0.0.1:${TAM_BACKEND_PORT};
    keepalive 32;
}
```

### 3. docker-entrypoint.sh — 用 envsubst 替代 sed

**文件**: [nginx/docker-entrypoint.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/docker-entrypoint.sh)

```sh
#!/bin/sh
set -e

# Substitute environment variables in nginx config template
if [ -f /etc/nginx/conf.d/default.conf.template ]; then
    envsubst '${TAM_NGINX_PORT} ${TAM_NGINX_SSL_PORT} ${TAM_BACKEND_PORT}' \
        < /etc/nginx/conf.d/default.conf.template \
        > /etc/nginx/conf.d/default.conf
    echo "nginx: config generated (HTTP: ${TAM_NGINX_PORT:-8080}, HTTPS: ${TAM_NGINX_SSL_PORT:-8443}, Backend: ${TAM_BACKEND_PORT:-8000})"
fi

nginx -t
echo "nginx: starting..."
exec nginx -g 'daemon off;'
```

关键改进：

* `envsubst` 只替换指定的 3 个变量，不会破坏 nginx 原生 `$host`、`$remote_addr` 等变量

* 无需 sed 匹配固定字符串，彻底解决端口替换问题

### 4. docker-compose.yml — 更新 nginx 配置

**文件**: [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L182-L190)

```yaml
  nginx:
    environment:
      TZ: ${TZ:-Asia/Shanghai}
      TAM_NGINX_PORT: ${TAM_NGINX_PORT:-8080}
      TAM_NGINX_SSL_PORT: ${TAM_NGINX_SSL_PORT:-8443}
      TAM_BACKEND_PORT: ${TAM_BACKEND_PORT:-8000}
    volumes:
      - ./nginx/etc/conf.d/tam.conf.template:/etc/nginx/conf.d/default.conf.template:ro
      - ./nginx/docker-entrypoint.sh:/docker-entrypoint.sh:ro
      - ./nginx/certs:/etc/nginx/ssl:ro
      - frontend_dist:/usr/share/nginx/html:ro
```

关键变更：

* 挂载 `tam.conf.template` 为 `.template` 文件（而非直接作为 `default.conf`）

* 添加 `TAM_BACKEND_PORT` 环境变量

* entrypoint 用 envsubst 生成最终 `default.conf`

### 5. 删除冗余文件

* `nginx/etc/conf.d/tam.conf` — 已被 template + envsubst 替代

* `nginx/etc/conf.d/tam.dev.conf` — template 通过环境变量适配

* `docker-compose.dev.yml` — 不再需要

* `docker-compose.prod.yml` — 不再需要

### 6. 更新 manage.sh — 移除 override 文件引用

**文件**: [manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L270-L283)

dc 函数中移除 dev.yml 和 prod.yml 的加载逻辑，简化为：

```bash
dc() {
    (export VERSION="${VERSION}" && docker compose -p "${COMPOSE_PROJECT_NAME}" --env-file "${ENV_FILE}" -f ${SCRIPT_DIR}/docker-compose.yml "$@")
}
```

### 7. 重建并验证

* `docker compose down` — 清除旧容器

* 重建后端镜像（恢复 USER app）

* 启动所有服务

* 验证端口配置正确生效

## 验证步骤

1. `docker compose down` — 清除旧容器
2. `./manage.sh rebuild backend` — 重建后端
3. `docker compose up -d` — 启动所有服务
4. 检查 nginx 日志：应显示 "config generated (HTTP: 8080, HTTPS: 8443, Backend: 8000)"
5. 检查后端日志：uvicorn 正常启动
6. `curl -k https://localhost:8443/health` — 验证服务可用

