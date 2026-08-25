# cli.py 字段错误与合规率告警公式修复计划

## 一、问题汇总

### 问题 A：`./manage.sh user list` 报错 — cli.py 字段名与模型不匹配

**报错 1：`AttributeError: 'User' object has no attribute 'locked_until'`**

| 位置                                                                                                   | 错误代码                                                                             | 实际架构                                                                                                                                                                                        |
| ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [cli.py L198](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L198)          | `u.locked_until` + `u.failed_login_attempts`                                     | **用户锁定基于 Redis**（`login_lock:<username>`），[User 模型](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/user.py#L10-L31) 无 `locked_until`、`failed_login_attempts` 列 |
| [cli.py L207-227](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L207-L227) | `_unlock_user` 直接写 `user.failed_login_attempts = 0` + `user.locked_until = None` | 应调用 [security.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/security.py) 的 `reset_login_attempts()` 清除 Redis key                                            |

参考实现：[auth.py L630-645](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/auth.py#L630-L645) 正确做法是查 Redis TTL 并构造 lock\_info。

**报错 2：`AttributeError: 'Role' object has no attribute 'is_builtin'`**
**报错 3：（隐含）`'Role' object has no attribute 'display_name'`**

| 位置                                                                                          | 错误代码             | 实际模型字段                                                                                                               |
| ------------------------------------------------------------------------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------- |
| [cli.py L255](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L255) | `r.is_builtin`   | [Role 模型](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/role.py#L9-L25) 用 `is_default` |
| [cli.py L256](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L256) | `r.display_name` | Role 模型无 display\_name，只有 `name` + `description`                                                                     |

### 问题 B：合规率告警显示 compliance\_rate=0.0%，28 个非合规 — 公式错误

**当前代码**（[main.py L334-335](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L334-L335)）：

```python
total_for_rate = result.compliant + result.non_compliant
rate = (result.compliant / total_for_rate * 100) if total_for_rate > 0 else 100.0
```

**Bug**：分母排除了 `bypass`（白名单旁路终端）。如果某 ARP source 只有 bypass + non\_compliant，没有 compliant，则 compliant=0 → rate=0%，哪怕 bypass（合规的旁路）占了大多数。

**示例**：bypass=100, non\_compliant=28, compliant=0 → 实际 compliance\_rate 应是 (100+0)/(100+0+28) ≈ 78%，但代码算成 0/28=0%，触发 critical ERROR。

**[ComplianceCheckResult](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/data_source.py#L99-L107)** 定义了四个状态：`compliant`、`bypass`、`non_compliant`、`unknown`。其中 `bypass` 是**合规状态**（白名单旁路，不视为不合规）。

**正确公式**：

```
分母 = compliant + bypass + non_compliant + unknown   (所有纳入检查的终端)
分子 = compliant + bypass
rate = 分子 / 分母 × 100%
```

这也与前端终端列表显示一致：bypass 终端在 UI 中显示为"旁路"绿色状态，不视为非合规。

***

## 二、修改文件清单

| 序号 | 文件                                                   | 修改内容                                                    |
| -- | ---------------------------------------------------- | ------------------------------------------------------- |
| 1  | `backend/cli.py` L175-200 `_list_users`              | 从 Redis 查询锁状态而非读 DB 字段；显示 Locked 列查 TTL                 |
| 2  | `backend/cli.py` L207-227 `_unlock_user`             | 改用 `reset_login_attempts()` 清除 Redis key 而非写 DB         |
| 3  | `backend/cli.py` L238-256 `_list_roles`              | `r.is_builtin`→`r.is_default`；`r.display_name`→`r.name` |
| 4  | `backend/app/main.py` L334-335                       | 合规率计算公式：分子加 bypass，分母加 bypass 和 unknown                 |
| 5  | `backend/app/services/event_emitter.py` L295-296（可选） | 在事件 data 中附带 `total_terminals` 和 `bypass_count` 便于排查    |

***

## 三、详细修复步骤

### 步骤 1：修复 cli.py `_list_users`（问题 A-1）

**修改内容**：

* 移除 `u.locked_until` 直接字段访问

* 在循环前批量从 Redis 读取 lock\_info（参考 [auth.py L630-645](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/auth.py#L630-L645)）

* 对每个 user 从 lock\_info 字典获取 `is_locked` 状态，TTL>0 算锁定

```python
# 新逻辑：
# 1) 循环前批量查 Redis lock_key TTL
# 2) 循环中 lock_info.get(u.username, {}).get("is_locked", False)
```

### 步骤 2：修复 cli.py `_unlock_user`（问题 A-2）

**修改内容**：

* 移除 `user.failed_login_attempts = 0`、`user.locked_until = None`

* 改为调用 `app.core.security.reset_login_attempts(username)` 清除 Redis key

* 保留 `user.is_active = True`（这个是 DB 字段，有效）

```python
# 新逻辑：
from app.core.security import reset_login_attempts
reset_login_attempts(username)  # Redis 清理 login_attempts + login_lock keys
# user.is_active = True 保留
```

### 步骤 3：修复 cli.py `_list_roles`（问题 A-3）

**修改内容**：

* `r.is_builtin` → `r.is_default`

* `r.display_name or 'N/A'` → `r.name`（display\_name 不存在）

* 表头 `Display Name` 可改为 `Name` 与 role 列表页面保持一致

### 步骤 4：修复 main.py 合规率公式（问题 B）

**修改内容**：

```python
# BEFORE（错误）
total_for_rate = result.compliant + result.non_compliant
rate = (result.compliant / total_for_rate * 100) if total_for_rate > 0 else 100.0

# AFTER（正确）
checked = result.compliant + result.bypass + result.non_compliant + result.unknown
effective_compliant = result.compliant + result.bypass
rate = (effective_compliant / checked * 100) if checked > 0 else 100.0
```

**同时**：`emit_compliance_alert` 调用传入的 `non_compliant_count` 保持 `result.non_compliant` 不变（合理），但在 data 中附加 bypass/checked 便于用户理解。

### 步骤 5（可选增强）：event\_emitter.py 中增加事件详情

在 `emit_compliance_alert` 的 data dict 中新增字段：

```python
"bypass_count": bypass_count,
"total_checked": checked,
"compliant_count": compliant_count,
```

让用户在 UI 通知中能看到"总终端 X、合规 Y、旁路 Z、不合规 N"，避免 0% 造成的心理冲击。

***

## 四、关联链路检查

| 链路                                                     | 现状                                         | 影响                          |
| ------------------------------------------------------ | ------------------------------------------ | --------------------------- |
| `metrics_service.py` `tam_compliance_rate`             | 需检查是否使用同一公式                                | 若也排除了 bypass，则 metrics 同步偏差 |
| Dashboard 合规卡片                                         | 前端通过 `/terminals` API 自算，与后端 formula 可能不一致 | 修复后后端通知与前端数字应一致             |
| `data_sources.py L151, L238` `non_compliant_count` sum | 这些仅用于字符串提示，无 rate 计算                       | 不影响                         |
| `compliance_baselines.py L163`                         | 基准详情里 count，无 rate 计算                      | 不影响                         |

***

## 五、风险评估与验证

| 风险                                              | 等级 | 应对                                                                        |
| ----------------------------------------------- | -- | ------------------------------------------------------------------------- |
| cli.py 改动后 `user list` / `user unlock` 功能回归     | 中  | 手动执行 `./manage.sh user list`、`./manage.sh user unlock admin` 验证           |
| `role list` 字段显示后与 UI 有差异                       | 低  | 确认 Role.name 的显示是否可读（如 admin/user/auditor）                                |
| 合规率公式变更后"告警消失太多"（用户感知反向问题）                      | 中  | 修复后通过 `./manage.sh scheduler trigger compliance_check` 重跑，并在通知列表中验证数字合理性  |
| `reset_login_attempts` 无法 import（cli.py 运行在容器中） | 低  | cli.py 已有 `from app.core.database import async_session_maker`，import 路径一致 |

### 验证命令

```bash
# 修复前（应报错）
./manage.sh user list
./manage.sh role list

# 修复后
./manage.sh user list           # 无报错，显示 Locked: Yes/No
./manage.sh role list           # 无报错，显示 Built-in: Yes/No
./manage.sh scheduler trigger compliance_check   # 重算合规率，验证不再是 0%
```

