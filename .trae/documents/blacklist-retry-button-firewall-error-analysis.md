# 黑名单「Retry Unblock 按钮」与「Firewall Errors 消息」分析

> 文档版本：r2  更新日期：2026-08-24

## 1. 摘要

1. **问题一（Retry Unblock 按钮）：** 黑名单行内的「Retry Unblock（重试解封）」按钮**当前对所有活跃条目都展示，范围过宽，不完全符合业务逻辑**。它的正确语义是「重试一次失败的解封」，只应针对「终端已合规/绕过、但自动解封失败」的条目（即 `pending_retry_unblock`）。当前对所有已封锁条目都展示、且后端不做合规校验直接解封，会解封「本应继续封锁」的终端，造成 re-block 振荡。见第 2 节。
2. **问题二（Firewall Errors 消息）：** 那条消息**不是错误码**，而是 TAM 对账服务自生成的「0-IP 保护 + 单点探测」诊断文案，触发后保守跳过对账。见第 3 节。

## 2. 问题一：Retry Unblock 按钮是否合理 —— 未完全合理

### 2.1 现状事实（代码已核实）

- 黑名单列表每行操作按钮为（[Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L466-L483)）：
  - `Eye` → 查看详情
  - `Unlock`（`retryUnblock`）→ **Retry Unblock**，展示条件是 **`!(item.auto_unblocked || item.unblocked_at)`** —— 即**所有「未解封」的活跃条目**都展示该按钮，与终端合规状态无关。
- 后端接口 `POST /blacklist/{entry_id}/retry`（[blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/blacklist.py#L27-L38)）→ 调 [retry_unblock](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1676-L1762)。
- `retry_unblock` 的校验链**只有**：条目存在、未解封、有 IP、有 firewall_tag、防火墙存在且启用 —— **它完全不检查该终端当前的 `compliance_status`**，直接调 `svc.unblock_ip` 并置 `auto_unblocked=True / reason='手动重试解封'`。

### 2.2 为什么「范围过宽」不符合业务逻辑

本系统里「解封」有严格的条件：只有当终端的合规判定变成 `compliant` / `bypass` 时才应当解除封锁。对应统计分类 `pending_retry_unblock`（[terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1618-L1631) 与 [get_blacklist 的 category 过滤](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1431-L1465)）的口径就是「**仍活跃条目 + 终端已是 compliant/bypass**」。

而「Retry Unblock（重试解封）」的字面语义 = 「上一次解封失败，再试一次」。上一次解封会失败的，只有 `pending_retry_unblock` 这一批——它们本该被解封却没成功。**对「终端仍 non_compliant（应继续封锁）」的条目，不存在「重试解封」这回事**。

因此当前实现有两处偏离：

| 偏离点 | 现状 | 应然 |
|---|---|---|
| 展示范围 | 所有未解封活跃条目都展示按钮 | 仅 `pending_retry_unblock`（终端已 compliant/bypass）展示 |
| 后端校验 | 不校验终端合规，直接解封 | 解封前校验终端已 compliant/bypass，否则拒绝 |

### 2.3 当前数据下的具体影响（实测）

- `success_blocked`（活跃黑名单条目）= 11；`pending_retry_unblock` = **0**；11 台对应终端**均为 non_compliant + blocked**。
- 也就是说：**现在页面展示了 11 个「Retry Unblock」按钮，但符合「应解封」条件的条目其实是 0 条**。
- 若管理员点其中任意一个，会触发：防火墙解封 → 合规重算判定仍 non_compliant → 调度器 retry-block 重新封锁 → **振荡**（正是本项目反复修复的「action-state 一致性」问题）。

### 2.4 建议改动

**必做（安全兜底，后端）：** 在 [retry_unblock](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1676-L1693) 里，用既有 [\_blacklist_terminal_join()](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L36-L52)（MAC 归一化匹配、NULL-MAC 回退 IP）查出该条目对应的 Terminal，仅当 `compliance_status in ('compliant','bypass')` 时允许解封；否则返回 `{"success": False, "error": "终端仍不合规（non_compliant），不可解封"}`，不执行 unblock。

**推荐（体验修正，前端）：** 让列表接口返回每条录对应的 `terminal_compliance_status`（在 `get_blacklist` 中对 `success_blocked`/默认视图 join Terminal 并透出该字段），前端据此只在 `compliant/bypass` 时渲染「Retry Unblock」按钮，避免展示一个「点了必然失败」的按钮。

> 说明：改动后「手动强制解封」仍可通过终端页的「解封」入口（带二次确认）完成，与「重试解封」语义分离，互不影响。

## 3. 问题二：Firewall Errors 那条消息 —— 不是错误码

### 3.1 结论

- 这不是「错误码」（error code，通常指 API 返回的 `code != 0` 标识）。
- 它是 TAM 对账服务**源码里硬编码的中文诊断文案**，作为 `firewall_errors` 数组某一项的 `error` 字段（[firewall_reconciliation_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L123)）。

### 3.2 触发逻辑（0-IP 保护 + 单点探测）

对账服务逐台防火墙执行（[reconcile](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L97-L131)）：

1. 调 `svc.get_blocked_ips()` 拉该防火墙的封锁 IP 列表。
2. 若返回 **0 个 IP**，但 DB 里该防火墙仍有活跃黑名单（`db_count_for_fw > 0`）→ 出现「防火墙说没封、DB 说封了」的矛盾。
3. 为避免「把 0 误当外部清空，进而误删/误解封」，执行**单点探测**：拿一个已知被封锁 IP 调 `_find_blacklist_entry(probe_ip)`。
4. 两个分支、两条不同文案：
   - **探测命中**（line 116）：`...单点探测命中，疑似列表接口异常...` → 列表接口坏了，但条目还在。
   - **探测未命中**（line 123，用户所见）：`...单点探测未命中，无法区分外部清空与接口故障...` → 列表空 + 单点也查不到，无法判断「外部清空」还是「接口故障」。

两种都 `continue` **跳过该防火墙对账**，并把 `{tag, error}` 写入 `firewall_errors`。

### 3.3 我的理解

- 该文案是**正常保护性设计**（「拿不准就不动手，防数据丢失」），不是故障、也不是可检索的错误码。
- 真正值得关注的是**它为何「总是出现」**。当前实测 `reconcile:latest`（Redis）：

  ```
  {"firewall_ip_count": 11, "db_entry_count": 11, "firewall_errors": [], "synced_at": "2026-08-24T09:07:27Z"}
  ```

  即**最新一次对账已成功读到 11 IP、`firewall_errors` 为空**，说明「返回 0 个封锁 IP」是**历史/间歇性**现象，不是当前持续状态。间歇返回 0 的排查方向：
  1. 深信服 AF `whiteblacklist` 列表接口偶发空返回（token 过期、接口抖动）；
  2. `get_blocked_ips` 用 `_length: 200` 分页（[sangfor_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/sangfor_service.py#L471-L486)），未来封锁数超过 200 会成稳定漏读源（当前仅 11 台，暂无影响）；
  3. 防火墙侧确被外部短暂清空后恢复。

## 4. 假设与决策

- 问题一是**行为不一致 + 振荡风险**，需按第 2.4 节修复（后端必做、前端推荐）。
- 问题二是**诊断性结论**，无代码缺陷；如需消除盲区，按第 5 节可选增强。

## 5. 建议的后续动作（可选，需业务确认）

1. 若需消除问题二盲区：在 `get_blocked_ips` 命中 `code==0 但 items 为空` 时上抛更细的 `code/message/raw`（现已有 raw 日志，[sangfor_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/sangfor_service.py#L500-L506)），用于区分「接口异常」与「真空」。
2. 若封锁规模未来超过 200，需给 `get_blocked_ips` 加分页采集，避免 `_length: 200` 造成 0-IP 假象。

## 6. 验证步骤（若执行问题一修复）

1. 重启后对一台「仍 non_compliant」的活跃条目调 `POST /blacklist/{id}/retry`，应返回 400「终端仍不合规，不可解封」，且 `auto_unblocked` 保持 False。
2. 对一台「已 compliant/bypass」的活跃条目调同一接口，应成功解封并写回 `last_operation_*`。
3. 前端在当前 11 条（全为 non_compliant）场景下，默认视图不应再出现「Retry Unblock」按钮；切到 `pending_retry_unblock` 卡片时才出现。