# 优化 scheduler 动态任务清单/真实状态 + cleanup 心跳 + upgrade 兼容性评估

## 1. 概述（Summary）

本次要实现三件事：

1. **动态任务清单 + 真实状态**：让 `manage.sh scheduler` 各子命令动态获取后端权威的完整任务清单（8 个）与真实状态（暂停 / 执行中 / 存活），替换当前 [manage.sh 中硬编码且不全、状态失真的 `_SCHEDULER_TASKS`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L3540)。
2. **cleanup 心跳**：给 `cleanup_expired_blacklist` 加心跳（Redis 键 + 每周期日志），解决它"静默死亡后无任何可观察信号"的问题。
3. **upgrade 兼容性评估**：评估上述两处改动对 `./manage.sh upgrade` 在线升级的影响。

已与用户确认的方案取向：
- 后端新增 `/system/scheduler/tasks` 端点，作为任务清单与状态的**唯一权威源**，manage.sh 完全动态拉取。
- 心跳采用 **Redis 键 + 日志** 双形式，且 8 个任务统一写 Redis 心跳键（支撑第 1 件事的"真实存活"判断）。

## 2. 现状分析（Current State Analysis）

- [manage.sh L3540 `_SCHEDULER_TASKS`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L3540) 硬编码 5 个任务，缺 `log_cleanup` / `firewall_reconciliation` / `backup` 这 3 个。
- 状态判断 [L3625-3636](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L3625-L3636) 只读暂停键 `scheduler:ctrl:{task}`，"RUNNING" 只代表"未暂停"，不反映任务是否真的还活着。
- 显示名 [L3548-3557 `_sched_display_name`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L3548-L3557) 把 `firewall_query` 标成 "Firewall Blacklist Query"，但该 task_name 实际对应 `cleanup_expired_blacklist`（清理到期黑名单），语义错位。
- 后端 8 个后台任务在 [main.py L785-792](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L785-L792) 由 `asyncio.create_task` 启动，无统一注册表、无 API 暴露、无心跳机制（已确认代码中无 `scheduler:heartbeat:*`）。
- [cli.py `_scheduler_trigger`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L1672-L1898) 仅支持 5 个任务，且 `firewall_query` 分支触发的是"查询防火墙 `get_blocked_ips`"，与真实 cleanup 任务不符。
- manage.sh 调后端 API 已有现成链路：[`_api_base_url`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L2643) + [`_config_get_admin_token`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L2665)（admin 登录拿 Bearer token）。
- 【历史根因】已通过排查确认：`cleanup_expired_blacklist` 曾被 `create_task` 启动过（归档日志中有两条 `All background scheduler tasks started`），但运行期静默死亡，38 天内既无 `Cleaned up` 也无 `Error` 日志，导致 81 条到期条目未清理。

## 3. 改动方案（Proposed Changes）

### 3.1 新增 `backend/app/core/scheduler_registry.py`（任务定义唯一权威源）

新建模块，只含一份数据常量（无外部依赖），供 main.py（心跳/任务）与 system.py（端点）共同引用：

```python
# 每个任务：name = task_name（Redis ctrl/lock/heartbeat 键及 cli trigger 共用）
#           interval_key = 可配间隔的 system_config key（None 表示固定间隔）
SCHEDULER_TASKS = [
    {"name": "firewall_query",          "display_name": "Blacklist Expiry Cleanup", "interval_key": "scheduler_firewall_query_interval",      "default_interval": 3600},
    {"name": "arp_collection",          "display_name": "ARP Data Collection",       "interval_key": "scheduler_arp_collection_interval",      "default_interval": 300},
    {"name": "ipguard_sync",            "display_name": "Compliance Baseline Sync",  "interval_key": "scheduler_ipguard_sync_interval",        "default_interval": 600},
    {"name": "compliance_check",        "display_name": "Compliance Check",          "interval_key": "scheduler_compliance_check_interval",    "default_interval": 300},
    {"name": "auto_unblock",            "display_name": "Auto Unblock",              "interval_key": "scheduler_auto_unblock_interval",        "default_interval": 600},
    {"name": "log_cleanup",             "display_name": "Log Cleanup",               "interval_key": None,                                     "default_interval": 86400},
    {"name": "firewall_reconciliation", "display_name": "Firewall Reconciliation",   "interval_key": None,                                     "default_interval": 300},
    {"name": "backup",                  "display_name": "Scheduled Backup",          "interval_key": None,                                     "default_interval": 60},
]
```

说明：`firewall_query` 的 `display_name` 修正为 "Blacklist Expiry Cleanup"，但 **`name` 保持 `firewall_query` 不变**（避免迁移 Redis `scheduler:ctrl/lock` 键与现有 `scheduler_firewall_query_interval` 配置 key）。

### 3.2 `backend/app/main.py`：心跳 helper + 8 个任务加心跳 + cleanup 加日志

**新增心跳 helper**（写 Redis 键，静默，不打印日志）：

```python
async def _record_task_heartbeat(task_name: str, ttl_seconds: int) -> None:
    try:
        from app.core.security import get_redis_client
        from datetime import datetime, UTC
        redis_client = await get_redis_client()
        await redis_client.setex(f"scheduler:heartbeat:{task_name}", ttl_seconds, datetime.now(UTC).isoformat())
    except Exception:
        pass  # Redis 不可用时静默降级，不阻塞任务主流程
```

**8 个任务循环内各插入一次心跳**，位置统一在 `await asyncio.sleep(...)` 之后、`_is_task_paused(...)` 判断之前（表示"本轮循环已苏醒"），TTL 规则 `max(300, interval * 3)`：

- 可配间隔的 5 个任务（`cleanup_expired_blacklist` / `scheduled_arp_collection` / `scheduled_ipguard_sync` / `scheduled_compliance_check` / `scheduled_auto_unblock`）：`await _record_task_heartbeat("<name>", max(300, interval * 3))`。
- 固定间隔任务：`log_cleanup` → `ttl=172800`；`firewall_reconciliation` → `ttl=900`；`backup`（`poll_interval=60`）→ `ttl=300`。

> 存活判定语义：任务每周期刷新心跳键；键在 `3×interval` 内过期若任务停止刷新 → 被判定 dead。心跳放在暂停检查之前，保证"被暂停（paused）"与"进程活着（alive）"正交、互不干扰。

**cleanup 额外打日志心跳（第 2 件事）**：在 `cleanup_expired_blacklist` 心跳调用后、清理逻辑执行前，打印一条 info 日志（`count=0` 时也打印），例如：

```python
logger.info(f"Scheduler heartbeat: {task_name} alive (interval={interval}s) [source=scheduler]")
```

`count > 0` 时仍沿用原有 `Cleaned up N expired blacklist entries` 日志，不再重复打印心跳日志。

### 3.3 `backend/app/api/v1/endpoints/system.py`：新增状态端点

新增 `GET /system/scheduler/tasks`（认证沿用 `Depends(get_current_user)`，与 `/system/status` 一致）：

- 遍历 `SCHEDULER_TASKS`，对每个任务读 Redis：
  - `scheduler:ctrl:{name}` → `paused`
  - `scheduler:lock:{name}` → `executing`
  - `scheduler:heartbeat:{name}` → `alive`（键存在即 alive）+ `last_heartbeat_at`
- `interval_seconds`：`interval_key` 非 None 时用 `ConfigService.get_value(interval_key)` 读取并 fallback 到 `default_interval`；否则直接 `default_interval`。
- 返回：

```json
{
  "tasks": [
    {
      "name": "firewall_query",
      "display_name": "Blacklist Expiry Cleanup",
      "interval_seconds": 3600,
      "interval_key": "scheduler_firewall_query_interval",
      "paused": false,
      "executing": false,
      "alive": true,
      "last_heartbeat_at": "2026-10-12T..."
    }
  ]
}
```

Redis 读取复用 `app.core.security.get_redis_client`；interval 读取复用 `ConfigService`（需 `db: AsyncSession = Depends(get_db)`）。

### 3.4 `backend/cli.py`：trigger 扩展并修正语义

在 [`_scheduler_trigger`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L1672) 中：

- 修正 `firewall_query` 分支：由"查询 `get_blocked_ips`"改为 `await TerminalService(db).cleanup_expired_blacklist()`（真正触发清理到期黑名单）。
- 新增 `log_cleanup` 分支：读 `audit_log_retention_days`（默认 90），删除过期 `AuditLog` 与已归档 `NotificationLog`（逻辑与 [main.py `cleanup_expired_logs`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L127-L172) 对齐，实现时内联即可）。
- 新增 `firewall_reconciliation` 分支：`FirewallReconciliationService(db).reconcile()` + `_cache_reconcile_result`（照抄 [system.py 触发端点](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/system.py#L108-L127)）。
- 新增 `backup` 分支：`BackupService(db=db).run_backup("full")`。
- 更新末尾提示为 8 个 task：`Valid tasks: firewall_query, arp_collection, ipguard_sync, compliance_check, auto_unblock, log_cleanup, firewall_reconciliation, backup`。

### 3.5 `manage.sh`：scheduler 子命令动态化

- 删除 `_SCHEDULER_TASKS` 与 `_sched_display_name`，改用一个新 helper `_scheduler_fetch_tasks()`：用 `_config_get_admin_token` 登录后 `GET {api_base}/system/scheduler/tasks`，返回 JSON（供 status/intervals/pause/resume/trigger 共用）。
- **status**：用 `_scheduler_fetch_tasks()` 结果渲染，`Status` 列按优先级显示：
  1. `paused` → `PAUSED`（黄）
  2. `!alive` → `DEAD`（红）
  3. `executing` → `RUNNING`（或标注 executing）
  4. 否则 → `RUNNING`（绿）
- **intervals**：输出端点返回的 `display_name` + `interval_seconds`（覆盖 8 个，含 3 个固定间隔任务）。
- **pause / resume**：合法 `task` 从端点清单（`name` 列表）校验；实际操作仍写/删 Redis `scheduler:ctrl:{task}`（沿用现有 [L3659 / L3672](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L3659) 逻辑）。
- **trigger**：合法 `task` 集与提示更新为 8 个，触发仍走 `dc exec backend python cli.py scheduler trigger <task>`。
- 若端点不可达（如旧版后端未升级），给出一次明确报错提示"后端版本不支持 /system/scheduler/tasks，请升级"，而不是静默显示空。

## 4. 假设与决策（Assumptions & Decisions）

- `task_name`（`firewall_query` 等）**保持不变**，只修正显示名，避免迁移 Redis 键与配置 key。
- 心跳键 TTL 采用 `max(300, interval*3)`，存活判定 = 键是否仍在 TTL 内（简单可靠，无需额外超时配置）。
- 心跳写入失败静默降级（Redis 虽应可用，但不清空主流程）。
- 端点认证用 `get_current_user`（manage.sh 已具备 admin token 登录能力），不新增权限点。
- 不新增数据库表 / 迁移 / 环境变量。

## 5. 验证（Verification）

1. 构建并重启后端：`./manage.sh update`（本地重建，不 git pull）。
2. `redis-cli --scan --pattern 'scheduler:heartbeat:*'` 应能看到 8 个心跳键（需等待各任务首个周期）。
3. `./manage.sh scheduler status` 显示 8 个任务，且有真实 `Status`（RUNNING/PAUSED/DEAD）。
4. `./manage.sh scheduler intervals` 显示 8 项含固定间隔的 3 项。
5. 观察日志：`grep "Scheduler heartbeat" /var/log/tam/app.log` 每周期出现 cleanup 心跳日志。
6. `./manage.sh scheduler pause firewall_query` / `resume` 生效；`status` 相应显示 PAUSED/RUNNING。
7. `./manage.sh scheduler trigger firewall_query` 能真正执行清理（可临时造一条 `expires_at < now` 的黑名单验证被清）。
8. 验证其它 3 个新 trigger（`log_cleanup` / `firewall_reconciliation` / `backup`）可正常执行不报错。

## 6. upgrade 在线升级兼容性评估（第 3 件事）

结论：**两处改动均支持 `./manage.sh upgrade` 在线升级，无需额外操作。**

依据：

- [cmd_upgrade](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L1899) 的部署流程是 `git fetch` + `git pull` 拉取远程代码 → `dc up -d --build` 重建镜像 → 重启。本次改动的两个载体都被覆盖：
  - `manage.sh`（脚本）：随 git pull 更新；
  - `backend/**`（main.py / system.py / cli.py / scheduler_registry.py）：随镜像重建生效。
- 改动**不涉及数据库 schema 变更**（心跳用 Redis key，端点只读 Redis/config），因此 alembic 迁移步骤会 no-op，即使带 `--check`/`--skip-migrate` 也安全。
- 不新增环境变量，`.env` 无需变更，也不触发 `_config_prompt_restart` 类提示。
- 唯一前提：代码需先 commit 并 push 到远程（`upgrade` 拉的是远程，不是本地工作区）。此为常规发布约束，非本次改动的额外风险。
- 潜在注意点：若未来某次只发布了前端/manage.sh 而非后端，`scheduler status` 会因旧版后端缺少 `/system/scheduler/tasks` 而报错——因此 3.5 中已要求对此做明确的"后端未升级"提示降级，避免静默失败。