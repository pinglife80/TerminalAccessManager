# 修复 Docker Compose 项目名称不一致问题

## 问题概述

项目中同时存在 `tam_*` 和 `terminalaccessmanager_*` 两套 Docker 资源（镜像、卷、网络），导致资源冗余和潜在冲突。

## 根因分析

### 当前状态

| 配置项 | 当前值 | 说明 |
|--------|--------|------|
| manage.sh `COMPOSE_PROJECT_NAME` | `tam` (line 83) | manage.sh 通过 `-p tam` 参数指定项目名 |
| docker-compose.yml `name:` 字段 | **缺失** | 未设置顶层 `name` 字段 |
| .env `COMPOSE_PROJECT_NAME` | **缺失** | 未设置环境变量 |
| 项目目录名 | `TerminalAccessManager` | Docker Compose 默认使用目录名（小写化）作为项目名 |

### Docker Compose 项目名优先级

1. `-p` 命令行参数（最高）— manage.sh 使用此方式 ✅
2. `COMPOSE_PROJECT_NAME` 环境变量
3. `name:` 顶层字段（compose 文件中）
4. 目录名（最低）— 直接运行 `docker compose` 时使用此方式 ❌

### 问题发生路径

- **通过 manage.sh 操作** → `docker compose -p tam` → 生成 `tam_*` 资源 ✅
- **直接运行 `docker compose`** → 无 `-p` 参数 → 使用目录名 → 生成 `terminalaccessmanager_*` 资源 ❌

### 当前冗余资源（实测确认）

```
镜像:
  tam-backend / tam-frontend              ← manage.sh 创建
  terminalaccessmanager-backend / frontend ← 直接 docker compose 创建

卷 (各5个):
  tam_postgres_data, tam_redis_data, tam_frontend_dist, tam_tam-logs, tam_tam-uploads
  terminalaccessmanager_postgres_data, ..._redis_data, ..._frontend_dist, ..._tam-logs, ..._tam-uploads

网络 (各1个):
  tam_tam_network
  terminalaccessmanager_tam_network
```

## 修复方案

### Step 1: 在 docker-compose.yml 添加顶层 `name` 字段

**文件**: [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml)

在第 1 行 `services:` 之前添加：

```yaml
name: tam

services:
  postgres:
    ...
```

**原理**: Compose Spec 标准的 `name:` 字段会作为默认项目名，即使直接运行 `docker compose`（不带 `-p` 参数），也会使用 `tam` 而非目录名 `terminalaccessmanager`。manage.sh 的 `-p tam` 参数优先级更高，不会受影响。

### Step 2: 更新 manage.sh 注释

**文件**: [manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh) L82

将注释从：
```bash
# Docker Compose project name (derived from directory name)
readonly COMPOSE_PROJECT_NAME="tam"
```

改为：
```bash
# Docker Compose project name (also set in docker-compose.yml top-level 'name:' field)
readonly COMPOSE_PROJECT_NAME="tam"
```

### Step 3: 清理冗余资源

删除所有 `terminalaccessmanager_*` 前缀的孤儿资源：

```bash
# 删除冗余镜像
docker rmi terminalaccessmanager-backend terminalaccessmanager-frontend

# 删除冗余卷
docker volume rm terminalaccessmanager_postgres_data \
  terminalaccessmanager_redis_data \
  terminalaccessmanager_frontend_dist \
  terminalaccessmanager_tam-logs \
  terminalaccessmanager_tam-uploads

# 删除冗余网络
docker network rm terminalaccessmanager_tam_network
```

**注意**: 删除前需确认这些资源没有被使用（当前 `tam_*` 资源是活跃的，`terminalaccessmanager_*` 是孤立的）。

### Step 4: 验证修复

```bash
# 1. 验证 docker-compose.yml 语法
docker compose config --quiet

# 2. 验证直接运行 docker compose 也使用 tam 项目名
docker compose config | grep "name:"

# 3. 确认无 terminalaccessmanager_* 资源残留
docker images --format '{{.Repository}}' | grep terminalaccessmanager
docker volume ls --format '{{.Name}}' | grep terminalaccessmanager
docker network ls --format '{{.Name}}' | grep terminalaccessmanager

# 4. 服务健康检查
./manage.sh health
```

## 假设与决策

- **不使用 `.env` 中的 `COMPOSE_PROJECT_NAME`**: `name:` 字段已在 compose 文件中声明，更直观且符合 Compose Spec 标准。`.env` 方式需要用户不删除该变量，不如文件内声明可靠。
- **保留 manage.sh 的 `-p tam`**: 双重保险，`-p` 优先级最高，确保 manage.sh 行为不变。
- **不修改 docker-compose.prod.yml 和 docker-compose.dev.yml**: 它们是 override 文件，继承主文件的 `name:` 字段。

## 影响评估

- **风险**: 极低。`name: tam` 与 manage.sh 已有的 `-p tam` 完全一致，不改变任何现有行为。
- **收益**: 消除直接运行 `docker compose` 时产生冗余资源的根因，统一所有 Docker 资源命名。
