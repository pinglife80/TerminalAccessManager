# 移除容器安全加固配置

## 问题概述

用户反馈：内网环境下，容器安全加固（`cap_drop ALL`、`read_only`、`no-new-privileges` 等）是鸡肋，导致了大量权限问题：
1. Nginx `setgid(101) failed` —— 需要额外添加 `CHOWN`、`SETUID`、`SETGID` 能力
2. Nginx `bind() to 0.0.0.0:80 failed` —— 需要 `NET_BIND_SERVICE` 能力
3. 后端卷权限不足 —— 需要额外的 `docker-entrypoint.sh` 脚本 + `su-exec`

**结论**: 内网环境下移除所有容器安全加固，简化部署。

## 修改计划

### 1. docker-compose.yml - 移除 nginx 和 backend 的安全配置

**文件**: [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml)

移除以下配置：
- nginx 服务 (L206-L215): 删除 `security_opt`、`cap_drop`、`cap_add`、`read_only`
- nginx 服务 (L216-L218): 删除 `tmpfs` (与 read_only 绑定)
- backend 服务 (L127-L132): 删除被注释的安全加固代码块（保持现状，本就未启用）

### 2. docker-compose.prod.yml - 移除 backend 的安全配置

**文件**: [docker-compose.prod.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.prod.yml)

移除 backend 服务的 `security_opt`、`cap_drop`、`read_only`、`tmpfs`，清空文件或删除整个文件。

### 3. backend/Dockerfile - 简化，移除 su-exec 和 entrypoint

**文件**: [backend/Dockerfile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/Dockerfile)

- 从 `apk add` 中移除 `su-exec`
- 移除 `COPY docker-entrypoint.sh` 和 `chmod` 行
- 恢复 `USER app` + `CMD exec uvicorn ...` 形式

### 4. 删除 backend/docker-entrypoint.sh

删除 [backend/docker-entrypoint.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/docker-entrypoint.sh) 文件。

## 风险评估

- **低风险**: 内网环境，系统不直接暴露给公网
- **低风险**: Docker 容器隔离仍然提供进程隔离和文件系统隔离
- **收益**: 消除所有权限问题，简化部署和维护