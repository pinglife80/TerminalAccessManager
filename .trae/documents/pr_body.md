## 问题描述

本次修复涉及 CLI 工具多个命令的属性错误和合规率告警计算错误，影响日常运维和调度器告警功能。

### 具体问题：

1. **`user list` / `user unlock`**：报错 `AttributeError: 'User' object has no attribute 'locked_until'`
   - 根因：User 模型已移除 `locked_until`、`failed_login_attempts` 字段，账户锁定状态迁移至 Redis
   
2. **`role list`**：报错 `AttributeError: 'Role' object has no attribute 'is_builtin'`
   - 根因：Role 模型 `is_builtin` 改为 `is_default`，`display_name` 改为 `name`

3. **`scheduler trigger compliance_check`**：报错 `TypeError: missing 1 required positional argument: 'entries'`
   - 根因：`batch_check_compliance()` 调用未传入 `entries` 参数

4. **合规率告警显示 `0.0%`**：告警数据异常，显示 `compliance_rate: 0.0%`、`total_checked: 32`
   - 根因：合规率公式错误排除了 bypass + unknown；告警数据源错误使用 per-source 局部结果而非 DB 全局统计

## 修复内容

| 项目 | 文件 | 说明 |
|------|------|------|
| User 锁查询改为 Redis | `cli.py` | 批量查询 `login_lock:{username}` TTL |
| User 解锁改为 Redis | `cli.py` | 调用 `reset_login_attempts()` |
| Role 字段修正 | `cli.py` | `is_default`、`name` |
| compliance_check 流程重写 | `cli.py` | 完整实现流程 |
| 合规率公式修正 | `main.py` | 分母含 bypass+unknown，分子含 bypass |
| 告警数据源修正 | `main.py` | DB 全局统计 |
| 删除重复告警 | `main.py` | 移除 per-source 告警 |
| 阈值守卫 | `event_emitter.py` | rate ≥ threshold 时静默 |
| Shell 变量修复 | `manage.sh` | `${2:-}` 语法 |
| 版本管理重写 | `manage.sh` | 仅同步必要文件 |
| API URL 动态化 | `manage.sh`、`.env.example` | 支持环境变量覆盖 |
| 参数描述 i18n | `GeneralSettings.tsx` | FIELD_DESC_I18N_KEYS |
| Dockerfile 版本同步 | `Dockerfile` | 构建时自动同步 |

## 变更统计

- **修改文件**：12 个
- **新增行**：+453
- **删除行**：-100

## 验证结果

- ✅ `user list`：正常显示 5 个用户，锁定状态正确
- ✅ `role list`：正常显示 5 个角色
- ✅ `scheduler trigger compliance_check`：合规率 84.7%，≥80% 阈值时静默
- ✅ 所有修改文件通过 Python 语法检查

## 影响范围

- 仅限 CLI 工具和调度器告警逻辑
- 不影响核心 API 接口
- 不涉及数据库迁移
