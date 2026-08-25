# 审计日志问题修复计划

> 文档版本：v1.0  更新日期：2026-07-16
>
> 本计划针对当前审计日志系统存在的严重问题进行根因分析、修复实施、数据清理和验证。

***

## 一、问题概览

用户反馈审计日志系统存在以下严重问题：

1. **日志数量爆炸**：项目部署仅一天，审计日志已近 13 万条
2. **筛选下拉菜单与结果不匹配**：日志类型过滤下拉菜单的选项和实际筛选结果完全不一致
3. **无差异日志泛滥**：

   * 终端 `10.8.30.1_18-56-80-19-59-FB`（白名单终端）一天内产生 2530 条日志，日志内容无差异，合规状态未实际变化

   * 终端 `10.8.15.153_C8-B2-9B-FA-6E-23`（合规终端）一天内产生 180 条日志，旧合规状态居然是 `unknown`，新状态总是 `compliant`

***

## 二、根因分析

### 问题 1：日志数量爆炸 + 无差异日志泛滥

**根本原因**：`backend/app/services/arp_collector_service.py:306-307` 在 ARP 采集时强制重置已存在终端的合规状态：

```python
# ❌ 问题代码
if existing:
    existing.updated_at = datetime.now(UTC)
    existing.source_tag = source_tag
    existing.source = "arp"
    existing.compliance_status = "unknown"   # 强制重置为 unknown
    existing.wl_match_type = None            # 清除白名单匹配类型
```

**循环机制**（每次 ARP 采集周期都发生）：

1. ARP 采集（默认每 5 分钟一次，`scheduler_arp_collection_interval=300`）将所有已存在终端的 `compliance_status` 强制重置为 `"unknown"`
2. 同一函数紧接着调用 `batch_check_compliance`，把状态从 `unknown` 重新计算为 `compliant`/`bypass`/`non_compliant`
3. `_apply_compliance_result` 中 `status_changed = terminal.compliance_status != new_compliance` 判断为 `True`（因为 `unknown → compliant/bypass`）
4. 写入一条 `compliance_status_changed` 审计日志
5. 下一个 ARP 采集周期（5 分钟后），重复以上过程

**数量验证**：

* 一天 24 小时 × 60 分钟 / 5 分钟 = 288 次 ARP 采集

* 每个终端每次产生 1 条 `compliance_status_changed` 日志

* 假设 250 个终端 × 288 次 = 72,000 条/天

* 加上 `scheduled_compliance_check`（也是每 5 分钟一次，但只查 `unknown` 状态终端，在 ARP 采集后立即运行）可能再产生一批

* 用户报告的 2530 条/终端/天 与"ARP 采集 + 合规检查"双任务共同触发的频率相符

**证据印证**：

* 用户报告终端 `10.8.15.153_C8-B2-9B-FA-6E-23` 旧合规状态是 `unknown`，新状态是 `compliant` → 正是 ARP 采集重置 + 重新计算的结果

* 用户报告终端 `10.8.30.1_18-56-80-19-59-FB`（白名单终端）2530 条无差异日志 → 每次都是 `unknown → bypass` 的循环

**次要源头**：`backend/app/services/compliance_service.py:1462` 的 `recalculate_compliance` 日志，每次有状态变化（哪怕只是 `unknown → compliant`）都会再写一条总账日志，进一步放大日志数量。

### 问题 2：日志类型筛选下拉菜单不匹配

**根本原因**：`frontend/src/pages/AuditLogs.tsx` 中 `ACTION_CATEGORIES`（L16-L67）硬编码的 action 值与后端实际写入数据库的 action 值不一致。

**前端下拉菜单定义的 action 值**：

| 类别         | 前端定义的 action 值                                                                                                                       |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| auth       | login, login\_failed, logout, token\_refresh, change\_password                                                                       |
| terminal   | block\_terminal, unblock\_terminal, auto\_block\_terminal, auto\_unblock\_terminal                                                   |
| whitelist  | add\_whitelist, remove\_whitelist                                                                                                    |
| blacklist  | block\_blacklist, unblock\_blacklist, cleanup\_expired\_blacklist                                                                    |
| datasource | create\_datasource, update\_datasource, delete\_datasource, test\_datasource, sync\_datasource, bind\_datasource, unbind\_datasource |
| user       | create\_user, update\_user, delete\_user, reset\_password, unlock\_user, change\_role, assign\_role                                  |
| role       | create\_role, update\_role, delete\_role                                                                                             |
| compliance | create\_baseline, update\_baseline, delete\_baseline                                                                                 |
| system     | update\_config, upload\_branding, export\_audit\_logs                                                                                |

**后端实际使用的 action 值**（从代码 grep 统计）：

| 后端实际 action 值               | 前端是否有对应选项                   |
| --------------------------- | --------------------------- |
| `compliance_status_changed` | ❌ **缺失（这是 13 万条日志的主要类型！）**  |
| `recalculate_compliance`    | ❌ 缺失                        |
| `firewall_block`            | ❌ 缺失                        |
| `firewall_unblock`          | ❌ 缺失                        |
| `whitelist_create`          | ❌ 前端是 `add_whitelist`       |
| `whitelist_update`          | ❌ 缺失                        |
| `whitelist_delete`          | ❌ 前端是 `remove_whitelist`    |
| `auto_block_terminal`       | ✅ 匹配                        |
| `auto_unblock_terminal`     | ✅ 匹配                        |
| `cleanup_expired_blacklist` | ✅ 匹配                        |
| `save_email_config`         | ❌ 缺失                        |
| `test_email`                | ❌ 缺失                        |
| `lock_user`                 | ❌ 缺失                        |
| `password_reset`            | ❌ 缺失（与 `reset_password` 不同） |
| `block_terminal`            | ❌ 后端已删除（v3.6.13 移除手动封锁）     |
| `unblock_terminal`          | ❌ 后端已删除（v3.6.13 移除手动封锁）     |
| `add_whitelist`             | ❌ 后端实际为 `whitelist_create`  |
| `remove_whitelist`          | ❌ 后端实际为 `whitelist_delete`  |
| `block_blacklist`           | ❌ 后端不存在                     |
| `unblock_blacklist`         | ❌ 后端不存在                     |

**结论**：

* 前端下拉菜单中绝大多数 action 值在后端不存在，导致筛选结果为空

* 后端主要产生的 `compliance_status_changed` 日志（占 13 万条的绝大多数）在前端没有任何对应选项

* v3.6.13 已经移除了手动封锁/解封功能，但前端仍保留 `block_terminal`/`unblock_terminal` 选项

***

## 三、修复方案

### 修复 1：ARP 采集不再重置已存在终端的合规状态

**文件**：`backend/app/services/arp_collector_service.py`
**行号**：L301-L308
**修改内容**：

移除对已存在终端的 `compliance_status` 和 `wl_match_type` 重置，仅更新元数据字段（`updated_at`、`source_tag`、`source`）。

**修改前**：

```python
if existing:
    from datetime import datetime
    existing.updated_at = datetime.now(UTC)
    existing.source_tag = source_tag
    existing.source = "arp"
    existing.compliance_status = "unknown"
    existing.wl_match_type = None
    updated += 1
```

**修改后**：

```python
if existing:
    from datetime import datetime
    existing.updated_at = datetime.now(UTC)
    existing.source_tag = source_tag
    existing.source = "arp"
    # 不再重置 compliance_status 和 wl_match_type：
    # 之前的实现会在每次 ARP 采集时强制把已存在终端的合规状态重置为 unknown，
    # 紧接着 batch_check_compliance 又重新计算为原状态（如 compliant/bypass），
    # 触发 _apply_compliance_result 中的 status_changed 判断，
    # 导致每个终端每次采集都产生一条 compliance_status_changed 审计日志。
    # 这造成一天产生 13 万条无差异日志，且 95% 是 unknown → 原状态 的循环。
    # 现在仅更新元数据，保留终端的合规状态。
    updated += 1
```

**影响分析**：

* ✅ 新终端创建（L309-L323）仍保持 `compliance_status="unknown"`，会触发首次合规检查和日志记录（合理）

* ✅ `batch_check_compliance` 查询 `compliance_status == "unknown"` 的终端时，已存在终端不再被匹配，只有真正的新终端会被检查

* ✅ `_apply_compliance_result` 中的 `status_changed` 判断恢复有效，只有真实状态变化才写日志

* ✅ 不影响数据源变更、绑定变更时的重置逻辑（那些是事件驱动的，频率低，合理）

### 修复 2：前端审计日志 action 选项与后端实际值对齐

**文件**：`frontend/src/pages/AuditLogs.tsx`
**行号**：L16-L165
**修改内容**：

#### 2.1 更新 `ACTION_CATEGORIES` 数组（L16-L67）

重新设计分类，包含所有后端实际使用的 action 值，并新增"合规"类别容纳 `compliance_status_changed` 等高频日志：

```typescript
const ACTION_CATEGORIES = [
  { key: 'all', labelKey: 'auditLogs.categories.all', actions: [] as string[] },
  {
    key: 'auth',
    labelKey: 'auditLogs.categories.auth',
    actions: ['login', 'login_failed', 'logout', 'token_refresh', 'change_password', 'password_reset'],
  },
  {
    key: 'compliance',
    labelKey: 'auditLogs.categories.compliance',
    actions: ['compliance_status_changed', 'recalculate_compliance', 'auto_block_terminal', 'auto_unblock_terminal'],
  },
  {
    key: 'firewall',
    labelKey: 'auditLogs.categories.firewall',
    actions: ['firewall_block', 'firewall_unblock'],
  },
  {
    key: 'whitelist',
    labelKey: 'auditLogs.categories.whitelist',
    actions: ['whitelist_create', 'whitelist_update', 'whitelist_delete'],
  },
  {
    key: 'blacklist',
    labelKey: 'auditLogs.categories.blacklist',
    actions: ['cleanup_expired_blacklist'],
  },
  {
    key: 'datasource',
    labelKey: 'auditLogs.categories.datasource',
    actions: ['create_datasource', 'update_datasource', 'delete_datasource', 'test_datasource', 'sync_datasource', 'bind_datasource', 'unbind_datasource'],
  },
  {
    key: 'user',
    labelKey: 'auditLogs.categories.user',
    actions: ['create_user', 'update_user', 'delete_user', 'reset_password', 'unlock_user', 'lock_user', 'change_role', 'assign_role'],
  },
  {
    key: 'role',
    labelKey: 'auditLogs.categories.role',
    actions: ['create_role', 'update_role', 'delete_role'],
  },
  {
    key: 'baseline',
    labelKey: 'auditLogs.categories.baseline',
    actions: ['create_baseline', 'update_baseline', 'delete_baseline'],
  },
  {
    key: 'system',
    labelKey: 'auditLogs.categories.system',
    actions: ['update_config', 'save_email_config', 'test_email', 'upload_branding', 'export_audit_logs'],
  },
] as const;
```

#### 2.2 更新 `actionLabelKeys` 映射（L69-L116）

补充缺失的 action 标签映射，移除已废弃的 action：

```typescript
const actionLabelKeys: Record<string, string> = {
  // auth
  login: 'auditLogs.actionLabels.login',
  login_failed: 'auditLogs.actionLabels.login_failed',
  logout: 'auditLogs.actionLabels.logout',
  token_refresh: 'auditLogs.actionLabels.token_refresh',
  change_password: 'auditLogs.actionLabels.change_password',
  password_reset: 'auditLogs.actionLabels.password_reset',
  // compliance
  compliance_status_changed: 'auditLogs.actionLabels.compliance_status_changed',
  recalculate_compliance: 'auditLogs.actionLabels.recalculate_compliance',
  auto_block_terminal: 'auditLogs.actionLabels.auto_block_terminal',
  auto_unblock_terminal: 'auditLogs.actionLabels.auto_unblock_terminal',
  // firewall
  firewall_block: 'auditLogs.actionLabels.firewall_block',
  firewall_unblock: 'auditLogs.actionLabels.firewall_unblock',
  // whitelist
  whitelist_create: 'auditLogs.actionLabels.whitelist_create',
  whitelist_update: 'auditLogs.actionLabels.whitelist_update',
  whitelist_delete: 'auditLogs.actionLabels.whitelist_delete',
  // blacklist
  cleanup_expired_blacklist: 'auditLogs.actionLabels.cleanup_expired_blacklist',
  // datasource
  create_datasource: 'auditLogs.actionLabels.create_datasource',
  update_datasource: 'auditLogs.actionLabels.update_datasource',
  delete_datasource: 'auditLogs.actionLabels.delete_datasource',
  test_datasource: 'auditLogs.actionLabels.test_datasource',
  sync_datasource: 'auditLogs.actionLabels.sync_datasource',
  bind_datasource: 'auditLogs.actionLabels.bind_datasource',
  unbind_datasource: 'auditLogs.actionLabels.unbind_datasource',
  // user
  create_user: 'auditLogs.actionLabels.create_user',
  update_user: 'auditLogs.actionLabels.update_user',
  delete_user: 'auditLogs.actionLabels.delete_user',
  reset_password: 'auditLogs.actionLabels.reset_password',
  unlock_user: 'auditLogs.actionLabels.unlock_user',
  lock_user: 'auditLogs.actionLabels.lock_user',
  change_role: 'auditLogs.actionLabels.change_role',
  assign_role: 'auditLogs.actionLabels.assign_role',
  // role
  create_role: 'auditLogs.actionLabels.create_role',
  update_role: 'auditLogs.actionLabels.update_role',
  delete_role: 'auditLogs.actionLabels.delete_role',
  // baseline
  create_baseline: 'auditLogs.actionLabels.create_baseline',
  update_baseline: 'auditLogs.actionLabels.update_baseline',
  delete_baseline: 'auditLogs.actionLabels.delete_baseline',
  // system
  update_config: 'auditLogs.actionLabels.update_config',
  save_email_config: 'auditLogs.actionLabels.save_email_config',
  test_email: 'auditLogs.actionLabels.test_email',
  upload_branding: 'auditLogs.actionLabels.upload_branding',
  export_audit_logs: 'auditLogs.actionLabels.export_audit_logs',
  // Legacy action names (backward compatibility for historical records)
  block_ip: 'auditLogs.actionLabels.firewall_block',
  unblock_ip: 'auditLogs.actionLabels.firewall_unblock',
  add_whitelist: 'auditLogs.actionLabels.whitelist_create',
  remove_whitelist: 'auditLogs.actionLabels.whitelist_delete',
  auto_block: 'auditLogs.actionLabels.auto_block_terminal',
  auto_unblock: 'auditLogs.actionLabels.auto_unblock_terminal',
  cleanup_expired: 'auditLogs.actionLabels.cleanup_expired_blacklist',
  role_change: 'auditLogs.actionLabels.change_role',
};
```

#### 2.3 更新 `ACTION_CATEGORY_MAP` 和 `CATEGORY_BADGE_STYLES`

新增 `compliance`、`firewall`、`baseline` 类别的样式，并补全所有 action 到 category 的映射。

#### 2.4 更新 i18n 翻译文件

**文件**：

* `frontend/src/i18n/locales/zh.ts`

* `frontend/src/i18n/locales/en.ts`

* `frontend/src/i18n/locales/ja.ts`

新增以下翻译键：

* `auditLogs.categories.firewall`（防火墙）

* `auditLogs.categories.baseline`（合规基线）

* `auditLogs.actionLabels.compliance_status_changed`（合规状态变更）

* `auditLogs.actionLabels.recalculate_compliance`（合规重新计算）

* `auditLogs.actionLabels.firewall_block`（防火墙封锁）

* `auditLogs.actionLabels.firewall_unblock`（防火墙解封）

* `auditLogs.actionLabels.whitelist_create`（添加白名单）

* `auditLogs.actionLabels.whitelist_update`（更新白名单）

* `auditLogs.actionLabels.whitelist_delete`（删除白名单）

* `auditLogs.actionLabels.password_reset`（密码重置请求）

* `auditLogs.actionLabels.lock_user`（锁定用户）

* `auditLogs.actionLabels.save_email_config`（保存邮件配置）

* `auditLogs.actionLabels.test_email`（测试邮件）

### 修复 3：清理历史无效审计日志

修复 1 和 2 部署后，需要清理数据库中已有的无效审计日志，避免：

* 13 万条无意义日志占用存储和影响查询性能

* 前端筛选时仍能看到旧的无效 action 值

**清理范围**：

* 删除所有 `action = 'compliance_status_changed'` 且 `details` 中 `old_compliance = 'unknown'` 且 `new_compliance IN ('compliant', 'bypass')` 的记录（这些是 ARP 采集重置循环产生的无意义日志）

* 保留真正有意义的合规状态变化日志（如 `compliant → non_compliant`、`non_compliant → compliant` 等）

**清理方式**：通过 `manage.sh` 执行 SQL（用户指定的运维方式）

***

## 四、假设与决策

### 假设

1. **ARP 采集间隔默认 5 分钟**：基于 `backend/app/main.py:181` 的 `_get_scheduler_interval("scheduler_arp_collection_interval", 300)` 默认值
2. **`scheduled_compliance_check`** **不会主动重置状态**：它只查询 `compliance_status == "unknown"` 的终端（L272），不会主动重置，所以修复 1 后该任务将只处理真正的新终端
3. **用户希望保留有意义的合规状态变化日志**：例如 `compliant → non_compliant` 表示终端从合规变为不合规，这种日志是有价值的，应该保留
4. **数据源变更、绑定变更时的状态重置是合理的**：这些是低频事件（用户手动操作），重置后重新计算合规状态是正确的行为

### 决策

1. **不修改** **`_apply_compliance_result`** **的日志写入逻辑**：该方法的 `status_changed` 判断本身是正确的，问题在于上游 ARP 采集错误地重置状态。修复根因后，该判断将正常工作。

2. **不修改** **`recalculate_compliance`** **日志写入逻辑**：`compliance_service.py:1462` 的总账日志在修复 1 后，因为 `non_compliant_count + unblocked_count + bypass_count + compliant_count` 大多为 0（无真实状态变化），不会写入日志（已有 `if` 判断保护）。

3. **前端新增** **`compliance`** **类别**：将 `compliance_status_changed`、`recalculate_compliance`、`auto_block_terminal`、`auto_unblock_terminal` 归入此类，便于用户筛选合规相关日志。

4. **前端新增** **`firewall`** **类别**：将 `firewall_block`、`firewall_unblock` 归入此类，与合规类别区分。

5. **保留 Legacy action 映射**：在 `actionLabelKeys` 中保留 `block_ip`、`unblock_ip`、`add_whitelist`、`remove_whitelist` 等历史 action 值的映射，确保能正确显示历史日志（不归类到任何 category，但 action 标签可显示）。

6. **不修改后端 API 端点**：`backend/app/api/v1/endpoints/logs.py` 的筛选逻辑（精确匹配 `action` 字段）本身是正确的，问题在前端选项值错误。修复前端选项后，筛选将正常工作。

***

## 五、验证步骤

### 验证 1：ARP 采集不再产生循环日志

1. 部署修复后，触发一次 ARP 采集：

   ```bash
   ./manage.sh scheduler trigger arp_collection
   ```
2. 等待 10 分钟（两个采集周期），再次触发
3. 查询审计日志，确认没有新的 `compliance_status_changed` 日志（除非终端真实状态变化）：

   ```sql
   SELECT COUNT(*) FROM audit_logs
   WHERE action = 'compliance_status_changed'
     AND timestamp > NOW() - INTERVAL '15 minutes';
   ```

   预期结果：0 条（如果没有真实状态变化）

### 验证 2：前端筛选下拉菜单与结果匹配

1. 打开审计日志页面
2. 选择"合规"类别 → 应筛选出 `compliance_status_changed`、`recalculate_compliance`、`auto_block_terminal`、`auto_unblock_terminal` 日志
3. 选择"防火墙"类别 → 应筛选出 `firewall_block`、`firewall_unblock` 日志
4. 选择"白名单"类别 → 应筛选出 `whitelist_create`、`whitelist_update`、`whitelist_delete` 日志
5. 确认所有筛选结果与所选类别一致

### 验证 3：数据清理后日志数量合理

1. 执行数据清理 SQL
2. 查询清理后日志总数：

   ```sql
   SELECT COUNT(*) FROM audit_logs;
   ```

   预期结果：从 13 万条降至数百条以内（保留真实状态变化、用户操作、系统配置变更等日志）

### 验证 4：业务流程无回归

1. 触发合规检查：

   ```bash
   ./manage.sh scheduler trigger compliance_check
   ```
2. 确认新终端（首次出现）的合规状态变化仍会记录日志
3. 确认白名单添加/删除仍会触发合规重新计算并记录真实状态变化日志
4. 确认数据源绑定变更后，相关终端的合规状态重置和重新计算正常工作

### 验证 5：服务健康

```bash
./manage.sh health
./manage.sh status
```

***

## 六、实施顺序

1. **后端修复**：修改 `arp_collector_service.py`，移除 compliance\_status 重置
2. **前端修复**：更新 `AuditLogs.tsx` 的 ACTION\_CATEGORIES、actionLabelKeys、ACTION\_CATEGORY\_MAP、CATEGORY\_BADGE\_STYLES
3. **i18n 修复**：更新 zh.ts、en.ts、ja.ts 翻译文件
4. **本地构建验证**：`./manage.sh -y update`
5. **数据清理**：执行 SQL 清理历史无效日志
6. **业务验证**：按验证步骤逐项确认
7. **文档更新**：更新 VERSION、package.json、changelog.md、release-notes.md、git-workflow-guide.md
8. **Git 提交**：按 Git Flow 提交到 develop，PR 合并到 main，打 tag

