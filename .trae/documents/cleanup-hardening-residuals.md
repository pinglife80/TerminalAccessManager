# 清理安全加固残留配置 + 修复权限问题

## 当前状态分析

安全加固已全面取消，但 docker-compose.yml 中仍残留大量注释掉的安全加固配置，且部分为 `read_only: true` 服务的 tmpfs 绕行方案，不再需要。同时发现一个实际权限问题。

### 问题清单

| # | 问题 | 文件 | 严重性 |
|---|------|------|--------|
| 1 | 4 个服务各有 `# Production hardening (uncomment for production):` 注释块，含注释掉的 security_opt/cap_drop/read_only | docker-compose.yml L37-41, L72-76, L162-167, L198-202 | 低（死代码，误导） |
| 2 | backend `tmpfs: /tmp` — 是 read_only 的绕行方案，已不需要 | docker-compose.yml L168-169 | 低（冗余） |
| 3 | postgres `tmpfs: /var/run/postgresql` — 是 read_only 的绕行方案 | docker-compose.yml L42-43 | 低（冗余） |
| 4 | nginx `tmpfs: /var/cache/nginx, /var/run` — 是 read_only 的绕行方案 | docker-compose.yml L242-244 | 低（可保留作性能优化） |
| 5 | **backend Dockerfile 未创建 `/var/log/tam` 目录** — 首次挂载 named volume 时 Docker 以 root:root 创建，app 用户无法写入，文件日志静默失效 | backend/Dockerfile L38-42 | **中高（功能缺陷）** |
| 6 | Dockerfile HEALTHCHECK 被 compose healthcheck 覆盖，是死代码 | backend/Dockerfile L50-51 | 低（冗余） |

### 问题 5 详情

[logging_config.py:135](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/logging_config.py#L135) 写入 `/var/log/tam/app.log`，但 [Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile#L38-L42) 未创建此目录。

Docker named volume 首次挂载时，如果容器内路径不存在，Docker 以 root:root 创建。`USER app` 无写入权限，[logging_config.py:144-147](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/logging_config.py#L144-L147) 的 try/except 静默跳过文件日志，导致 `backend-logs` 卷存在但始终为空。

## 修改计划

### 1. docker-compose.yml — 删除 4 个注释块

删除以下 4 处 `# Production hardening` 注释块：
- [L37-41](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L37-L41)（postgres）
- [L72-76](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L72-L76)（redis）
- [L162-167](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L162-L167)（backend）
- [L198-202](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L198-L202)（frontend）

### 2. docker-compose.yml — 删除 backend tmpfs

删除 [L168-169](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L168-L169) 的 `tmpfs: /tmp`（read_only 绕行方案，已不需要）。

### 3. docker-compose.yml — 删除 postgres tmpfs

删除 [L42-43](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L42-L43) 的 `tmpfs: /var/run/postgresql`（read_only 绕行方案）。

### 4. docker-compose.yml — 保留 nginx tmpfs

**保留** [L242-244](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L242-L244) 的 nginx tmpfs。虽然最初是 read_only 绕行方案，但 tmpfs 对 nginx cache/run 有实际性能收益，且无副作用。

### 5. backend/Dockerfile — 创建 /var/log/tam 并设置权限

在 [L41 `RUN chown -R app:app /app`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile#L41) 之后、`USER app` 之前，添加：

```dockerfile
RUN mkdir -p /var/log/tam && chown app:app /var/log/tam
```

这样 Docker named volume 首次挂载时，会从镜像中复制 `app:app` 权限，文件日志正常写入。

### 6. backend/Dockerfile — 删除被覆盖的 HEALTHCHECK

删除 [L50-51](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile#L50-L51) 的 HEALTHCHECK 指令（被 docker-compose.yml 的 healthcheck 覆盖，是死代码）。

## Assumptions & Decisions

1. nginx tmpfs 保留 — 纯性能优化，无权限风险
2. postgres tmpfs 删除 — 无性能收益（Unix socket 在普通文件系统上足够快），增加复杂度
3. backend tmpfs 删除 — /tmp 在普通文件系统上正常可写，无需 tmpfs
4. Dockerfile EXPOSE 8000 保留 — 仅作文档元数据，不影响实际端口映射

## 验证

1. `docker compose -f docker-compose.yml config --quiet` — 无报错
2. `docker compose up -d backend && docker exec tam_backend ls -la /var/log/tam/` — 目录存在且 owner 为 app
3. `docker exec tam_backend touch /var/log/tam/test && docker exec tam_backend rm /var/log/tam/test` — app 用户可写入
4. 重启 backend 后检查 `backend-logs` 卷中有 `app.log` 文件
5. `./manage.sh health` — 全绿