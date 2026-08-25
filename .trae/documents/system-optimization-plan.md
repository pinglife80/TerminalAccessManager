# 系统优化方案计划

## 概述

针对 todos.md 中列出的三个问题点，进行全面审查评估并制定完善的解决方案：

1. **备份管理闭环**：白名单数据备份 + 备份恢复功能完善
2. **日志归档与清理**：系统各类日志的归档和按时间/量清除逻辑
3. **SQLAlchemy 连接池耗尽**：修复 QueuePool 连接池耗尽问题

---

## 问题一：备份管理闭环

### 现状分析

| 功能 | 状态 | 说明 |
|------|------|------|
| 数据库备份 | ✅ 已实现 | 通过 pg_dump 备份整个数据库 |
| 配置文件备份 | ✅ 已实现 | docker-compose.yml, manage.sh |
| 日志备份 | ✅ 可选 | 配置项 `backup_logs` |
| 备份恢复 | ✅ 已实现 | `POST /backup/restore/{filename}` |
| 白名单单独备份 | ❌ 缺失 | 无法单独备份白名单数据 |

**关键文件：**
- [backup_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py) - 备份服务核心逻辑
- [backup.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/backup.py) - 备份 API 端点

### 问题分析

虽然数据库备份已包含白名单数据，但用户需求是**单独备份白名单数据**，便于：
- 快速恢复白名单配置
- 跨环境迁移白名单数据
- 选择性恢复白名单（不影响其他数据）

### 解决方案

#### 方案一：新增白名单专用备份端点（推荐）

**优势**：最小改动，满足业务需求，不影响现有备份流程

**实施步骤**：

1. **后端服务层**：在 `backup_service.py` 中新增白名单备份方法
   - `backup_whitelist(temp_dir)` - 导出白名单为 JSON/CSV
   - `restore_whitelist(file_path)` - 从备份文件恢复白名单

2. **后端 API 层**：在 `backup.py` 中新增端点
   - `POST /backup/whitelist` - 创建白名单专用备份
   - `GET /backup/whitelist/list` - 获取白名单备份列表
   - `POST /backup/whitelist/restore/{filename}` - 恢复白名单备份

3. **前端**：备份管理页面新增白名单备份模块

#### 方案二：增强现有备份配置（扩展）

在 `BackupConfig` 中新增 `backup_whitelist` 配置项，在全量备份时可选包含白名单独立文件。

### 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/services/backup_service.py` | 新增白名单备份/恢复方法 |
| `backend/app/api/v1/endpoints/backup.py` | 新增白名单备份 API 端点 |
| `backend/app/schemas/backup.py` | 新增白名单备份相关 Schema |

---

## 问题二：日志归档与清理

### 现状分析

| 日志类型 | 归档功能 | 清理功能 | 状态 |
|----------|----------|----------|------|
| 通知日志 (NotificationLog) | ✅ 已实现 | ✅ 已实现 | `POST /notifications/logs/archive-all`, `DELETE /notifications/logs/cleanup` |
| 审计日志 (AuditLog) | ❌ 缺失 | ❌ 缺失 | 无归档/清理机制 |
| 系统日志 (TerminalService.log_action) | ❌ 缺失 | ❌ 缺失 | 仅依赖数据库增长 |
| LDAP 同步日志 | ❌ 缺失 | ❌ 缺失 | 无清理机制 |
| 后端文件日志 | ❌ 缺失 | ❌ 缺失 | 无清理机制 |

**关键文件：**
- [logs.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/logs.py) - 审计日志端点
- [notification_logging.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_logging.py) - 通知日志服务
- [logging_config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/logging_config.py) - 日志配置

### 问题分析

当前仅通知日志有归档清理功能，其他日志类型长期累积会导致：
- 数据库表膨胀
- 查询性能下降
- 存储成本增加

### 解决方案

#### 统一日志管理方案

**1. 审计日志归档与清理**

在 `logs.py` 中新增：
- `POST /logs/archive` - 归档指定天数前的审计日志
- `DELETE /logs/cleanup` - 清理已归档的审计日志

**2. 数据库日志自动清理（定时任务）**

在 `main.py` 中新增定时任务：
- 每日凌晨自动清理 90 天前的已归档日志
- 可配置保留天数

**3. 后端文件日志清理**

在 `logging_config.py` 中配置：
- 文件大小限制（如 50MB）
- 保留文件数量（如 10 个）
- 自动压缩旧日志

**4. 日志管理 UI**

前端新增日志管理页面：
- 查看各类日志统计
- 配置归档/清理策略
- 手动触发清理

### 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/api/v1/endpoints/logs.py` | 新增审计日志归档/清理端点 |
| `backend/app/models/log.py` | 为 AuditLog 添加 `archived` 字段 |
| `backend/app/main.py` | 新增日志清理定时任务 |
| `backend/app/core/logging_config.py` | 配置文件日志轮换和清理 |

---

## 问题三：SQLAlchemy QueuePool 连接池耗尽

### 现状分析

**数据库连接池配置**（[database.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/database.py)）：

```python
_engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
```

**错误日志示例**：
```
TimeoutError: QueuePool limit of size 10 overflow 20 reached, connection timed out, timeout 30.00
```

**潜在原因分析**：

| 原因 | 可能性 | 说明 |
|------|--------|------|
| 异步会话未正确释放 | 高 | `get_db()` 依赖中 `finally: await session.close()` 可能未执行 |
| 通知工作者创建过多会话 | 高 | 通知发送时频繁创建数据库会话 |
| 长时间运行的合规检查 | 中 | 全量合规重算可能占用连接 |
| 连接泄露 | 中 | 异常情况下连接未正确归还 |

**关键文件：**
- [database.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/database.py) - 数据库连接配置
- [notification_workers.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_workers.py) - 通知工作者
- [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py) - 合规检查服务

### 解决方案

#### 方案一：优化连接池配置（快速修复）

**优势**：快速缓解问题，无需大规模代码修改

**配置调整**：
```python
_engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
    "pool_recycle": 300,          # 缩短连接回收时间（从 3600 改为 300 秒）
    "pool_timeout": 60,           # 增加连接获取超时时间
}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 20         # 增加基础连接数（从 10 改为 20）
    _engine_kwargs["max_overflow"] = 30      # 增加溢出连接数（从 20 改为 30）
```

#### 方案二：修复会话释放问题（根本解决）

**优势**：从根本上解决连接泄露问题

**修改 `get_db()` 依赖**：
```python
async def get_db() -> AsyncSession:
    """Dependency to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # 确保会话正确关闭
            await session.close()
```

**问题**：当前代码已有 `finally: await session.close()`，但在 FastAPI 依赖中，`async with` 上下文管理器会自动调用 `close()`。问题可能出在其他地方。

#### 方案三：优化通知工作者会话管理（针对性修复）

**优势**：解决最主要的连接消耗源

**修改 `notification_workers.py`**：
- 使用共享会话而非每次创建新会话
- 在工作者生命周期内复用会话
- 添加会话健康检查和自动重建机制

#### 方案四：引入连接池监控（长期优化）

**优势**：便于后续排查和优化

**实现步骤**：
- 在 Prometheus metrics 中添加连接池指标
- 监控活跃连接数、等待队列长度
- 配置连接池告警

### 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/core/database.py` | 优化连接池配置参数 |
| `backend/app/services/notification_workers.py` | 优化会话管理，减少会话创建 |
| `backend/app/main.py` | 添加连接池监控 metrics |

---

## 实施优先级

| 优先级 | 问题 | 原因 |
|--------|------|------|
| P0 | SQLAlchemy 连接池耗尽 | 直接影响系统稳定性，导致服务不可用 |
| P1 | 日志归档与清理 | 长期累积影响性能和存储 |
| P2 | 备份管理闭环 | 功能增强，非紧急但重要 |

---

## 风险评估

| 问题 | 风险 | 缓解措施 |
|------|------|----------|
| 连接池配置调整 | 可能增加数据库负载 | 逐步调整，监控性能 |
| 日志清理 | 可能误删重要日志 | 先归档后清理，保留期可配置 |
| 白名单恢复 | 可能覆盖现有数据 | 恢复前自动备份当前白名单 |

---

## 验证方案

### 连接池修复验证
1. 运行 `./manage.sh test` 确保测试通过
2. 观察后端日志，确认无 QueuePool 错误
3. 使用 `./manage.sh redis info` 和数据库查询验证连接状态

### 日志归档验证
1. 手动触发日志归档，验证归档标记正确
2. 触发日志清理，验证已归档日志被删除
3. 检查定时任务执行日志

### 白名单备份验证
1. 创建白名单备份
2. 修改白名单数据
3. 恢复备份，验证数据完整性
