# 修复端口绑定和卷权限问题

## 根因分析

### 问题 1: 端口 80/443 绑定失败

**根因: Docker 运行在 Rootless 模式**

```
$ docker info | grep rootless
  Context:    rootless
  rootless
```

Rootless Docker 中，守护进程以非 root 用户运行，容器进程在宿主机上也是非 root。Linux 规定端口 < 1024 为特权端口，只有 root 进程或具有 `CAP_NET_BIND_SERVICE` 的进程才能绑定。

```
$ cat /proc/sys/net/ipv4/ip_unprivileged_port_start
1024
```

实测确认：即使 `--privileged` + `--cap-add NET_BIND_SERVICE`，rootless Docker 仍无法绑定端口 80。

**结论**: 这不是变量解耦的设计缺陷。envsubst 模板工作正常（日志显示 "config generated (HTTP: 80, HTTPS: 443, Backend: 8001)"），问题在于 rootless Docker 环境下端口 < 1024 的系统级限制。

### 问题 2: 后端卷权限不足

```
Permission denied for backup directory /app/uploads/backups
```

**根因**: Docker 卷 `tam_backend-data` 创建于容器以 root 运行时期，卷目录归 root:root 所有。恢复 `USER app` 后，`app` 用户无写权限。

```
$ docker run --rm -v tam_backend-data:/data alpine ls -la /data/
drwxr-xr-x    2 root     root          4096 Aug  7 09:50 .
```

## 修复方案

### 方案选择

| 方案 | 操作 | 优缺点 |
|------|------|--------|
| A. 使用端口 >= 1024 | `.env` 改为 8080/8443/8000 | ✅ 无需 sudo，立即生效 ❌ 不是标准端口 |
| B. 修改 sysctl | `sudo sysctl net.ipv4.ip_unprivileged_port_start=80` | ✅ 可用 80/443 ❌ 需 sudo，影响全系统 |

**推荐方案 A**：用户无 sudo 权限，且 8080/8443 在内网环境完全可接受。

## 修复步骤

### 1. .env — 恢复可用端口

将端口改回 >= 1024 的值（用户可自选，如 8080/8443/8000 或 8880/8843/8001 等）：

```env
TAM_NGINX_PORT=8080
TAM_NGINX_SSL_PORT=8443
TAM_BACKEND_PORT=8000
```

### 2. 删除旧卷并重建

```bash
docker compose -p tam --env-file .env -f docker-compose.yml down
docker volume rm tam_backend-data
docker compose -p tam --env-file .env -f docker-compose.yml up -d --build
```

删除旧卷后，Docker 会以镜像中的 `app:app` 权限重新创建卷。

### 3. 验证

- Nginx 日志显示 "config generated (HTTP: 8080, HTTPS: 8443, Backend: 8000)"
- 后端无 "Permission denied" 警告
- `curl -k https://localhost:8443/health` 正常响应

## 关于变量解耦的说明

变量解耦机制本身工作正常：
- ✅ envsubst 正确生成 nginx 配置（任意端口值都能替换）
- ✅ 后端 `BACKEND_PORT` 环境变量正确传递
- ✅ `TAM_BACKEND_PORT` 正确注入 nginx upstream

**限制**：rootless Docker 环境下，端口 < 1024 受 Linux 内核限制无法绑定，这是系统级约束，非代码问题。如需使用 80/443，需要管理员执行：
```bash
sudo sysctl -w net.ipv4.ip_unprivileged_port_start=80
echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee -a /etc/sysctl.conf
```