# 黑名单统计三处口径统一修复计划

## 一、问题摘要

用户反馈：dashboard、terminal、blacklist 三个位置的黑名单统计无法与防火墙实际封锁统计保持一致，且"修了很多次仍修不好"。

**实测当前数值（2026-08-21 11:xx 取证）**：

| 位置 | 数值 | 统计口径 | 维度 |
|------|------|---------|------|
| Dashboard「已封锁」 | **92** | `terminals.status='blocked'` 计数 | 终端维度（按MAC去重） |
| Terminals 页红色卡片 | **94** | `compliance_status='non_compliant'` 计数 | 合规维度（tooltip却写"已被封禁"） |
| Blacklist 页 total | **94** | 活跃黑名单条目数 | 条目维度（按IP×防火墙） |
| 防火墙实际封锁 | **94~96**（波动） | Sangfor API 实时查询 | IP维度 |

**差异构成**：
- Dashboard 92 vs Blacklist 94 的差值 = 2 条 **NULL-MAC 对账补建记录**（10.8.19.48、10.8.17.83，终端已离线/IP已变更，防火墙确实封锁中但对账无法关联到终端记录）——这2条是正确数据，不是脏数据
- 防火墙 94~96 的波动 = 封锁/解封操作发生在两次对账（5分钟间隔）之间的正常时间差

## 二、为什么"修了很多次还修不好"——历史修复复盘

历次修复全部聚焦于**数据同步正确性**（让 DB 记录与防火墙状态一致），从未处理过**统计口径定义**问题：

1. v3.11.0：对账补建 Blacklist 条目 + 白名单保护（修"DB缺记录"）
2. 8/20 16:21：分析三处数量不一致 → 归因于环境状态+历史残留1条差异（修"数据残留"）
3. 8/20 17:42：修复 `Terminal.last_seen` AttributeError 导致对账补建漏1条（修"代码bug"）
4. 8/20 18:06：修复白名单震荡5处bug（修"状态翻转"）
5. 8/21：datetime 遮蔽 + 部署流程问题（修"重算崩溃"）

**真正的结构性根因**：三个位置使用三个不同聚合维度（终端维度 / 合规维度 / 条目维度），即使底层数据完全正确，数字也天然不相等。这是定义问题，不是数据bug，所以此前每轮修复都无法消除差异。

## 三、修复方案（用户已确认：统一DB口径 + 防火墙对照）

统一口径 = **DB 活跃封锁 IP 数**（黑名单表 distinct 活跃 IP，经对账与防火墙同步）。终端页保留非合规计数与现有 tooltip 不变（用户确认：非合规含已封锁+未封锁，tooltip 无问题，可按封锁状态筛选）。防火墙实际数量作为对照展示在黑名单页（读对账缓存，不增加防火墙API轮询压力）。

### 修改1：get_stats 的 blocked 改为统一口径
文件：`backend/app/services/terminal_service.py` `get_stats()`（L217-257）
- `blocked` 字段计算从 `terminals.status='blocked'` 计数改为 **黑名单活跃条目 distinct IP 计数**：
```python
blocked = count(distinct(Blacklist.ip_address)) WHERE
  auto_unblocked=false AND unblocked_at IS NULL
  AND (expires_at >= now OR expires_at IS NULL)
```
- 这样 Dashboard 与黑名单页、防火墙实际数（经对账）天然对齐，NULL-MAC 补建条目也被正确计入
- `unblocked` 及其他字段不动

### 修改2：对账结果缓存到 Redis
文件：`backend/app/main.py` `firewall_reconciliation` 任务（L156-177）+ `backend/app/api/v1/endpoints/system.py` 手动对账端点（L108-123）
- reconcile() 成功后将结果写入 Redis：`reconcile:latest` = JSON `{firewall_ip_count, db_entry_count, firewall_errors, synced_at}`，TTL 1小时
- 两处（定时任务+手动触发）都写入，保证数据新鲜

### 修改3：blacklist stats 接口返回防火墙对照数
文件：`backend/app/services/terminal_service.py` `get_blacklist_stats()`（L1432-1465）
- 读取 Redis `reconcile:latest`，在返回体追加：
  - `firewall_ip_count`（防火墙实际封锁数，缓存值；无缓存时为 null）
  - `firewall_synced_at`（上次对账时间）
- 不实时调用防火墙API，零额外负载

### 修改4：黑名单页展示统一统计条 + 防火墙对照
文件：`frontend/src/pages/Blacklist.tsx`
- 页头下方增加统计信息行：`活跃封锁：{total}（数据库）｜防火墙实际：{firewall_ip_count}`，防火墙数来自已有但未使用的 `useBlacklistStats` hook（`frontend/src/hooks/useTerminalData.ts` L202-211）
- `frontend/src/lib/constants.ts` 增加 `BLACKLIST_STATS: '/blacklist/stats'` 端点常量
- 扩展 `BlacklistStats` 接口（useTerminalData.ts L194-200）增加 `firewall_ip_count`、`firewall_synced_at` 字段
- 防火墙数缺失时显示"-"，不报错

### 修改5：无（终端页不改动）
用户确认：终端页非合规计数含已封锁+未封锁，tooltip 无问题，可按封锁状态筛选。Terminals.tsx 及 i18n 均不修改。

## 四、假设与决策
- 当前单防火墙环境，条目数=distinct IP数；多防火墙时 distinct IP 口径仍正确代表"被封锁的终端网络身份数"
- 防火墙对照数接受最长5分钟延迟（对账周期），换取零额外API压力
- 2条 NULL-MAC 补建记录保留（是防火墙真实封锁的正确映射），不做数据清理

## 五、验证步骤
1. `python3 -m py_compile` 检查后端修改文件；`npm run build`（或 tsc）检查前端
2. `manage.sh update` 部署，部署后立即做容器代码指纹验证（吸取上轮教训）：
   - `docker exec tam_backend grep -c "count(func.distinct" /app/app/services/terminal_service.py` ≥1
   - `grep -c "reconcile:latest" /app/app/main.py` ≥1
3. 数据库口径验证：`SELECT count(DISTINCT ip_address) FROM blacklist WHERE auto_unblocked=false AND unblocked_at IS NULL AND (expires_at>=now() OR expires_at IS NULL)` == API `/stats/` 返回的 blocked
4. 页面验证：Dashboard blocked == Blacklist 页活跃数 == 防火墙对照数（允许±对账周期内波动）
5. Terminals 页红色卡片保持非合规计数不变（不修改）
