> 文档版本：v1.0  更新日期：2026-09-04

# MAC+IP 复合唯一键改造 —— 回归测试用例清单

## 一、测试目标与范围

本次改造将终端唯一身份从「MAC 单列唯一」改为「(IP, MAC) 复合唯一」，使同 MAC 多 IP 终端（典型：桥接虚拟机）能够在系统中独立落库、独立展示、独立合规判定与独立封堵。

**核心验收目标**：同 MAC 多 IP 终端在 **终端页、看板、黑名单页** 的状态必须完全隔离，不得再出现交叉污染。

**参照方案**：[三问题根因诊断与优化解决方案报告](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/.trae/documents/三问题优化解决方案与实施报告.md)

**改造范围涉及的代码/配置**：
- 迁移 [040_terminal_mac_ip_unique.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/alembic/versions/040_terminal_mac_ip_unique.py)
- 模型 [terminal.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/terminal.py)
- ARP 采集 [arp_collector_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py)
- 合规/解封/封锁 [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py)
- 统计/黑名单关联 [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py)
- 防火墙对账 [firewall_reconciliation_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py)
- 数据源解绑 [data_source_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/data_source_service.py)
- 终端页 [Terminals.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx)

---

## 二、前置准备

### 2.1 环境要求
- 后端已通过 `manage.sh upgrade` 完成迁移 `040`，且数据库唯一约束已生效（见 M-1）。
- 至少一台启用且联通的 Sangfor 防火墙（用于对账/封堵用例），一个启用的 ARP 数据源（arp_ssh 或 arp_api）。
- 具备 `blacklist:read` / `blacklist:write` 权限的测试账号，以及可直连数据库的只读账号。

### 2.2 测试数据（核心遥测对）

| 终端 | IP | MAC | 数据源 |
|---|---|---|---|
| T1 | 10.8.14.32 | AA:BB:CC:DD:EE:FF | arp_ssh / arp_api（启用） |
| T2 | 10.8.14.100 | AA:BB:CC:DD:EE:FF | arp_ssh / arp_api（启用） |

> 二者共享同一 MAC，是本次隔离验证的「最小复现场景」。若环境无法造桥接虚拟机，可在测试环境的交换机 ARP 表写入两条映射，或通过 mock 数据源构造。

### 2.3 校验 SQL（执行 DB 断言用）
```sql
-- 校验唯一约束已切换
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'terminals'::regclass AND contype = 'u';

-- 校验同 MAC 多 IP 均保留
SELECT ip_address, mac_address_normalized, status, compliance_status
FROM terminals
WHERE mac_address_normalized = 'AABBCCDDEEFF'
ORDER BY ip_address;
```

---

## 三、用例清单

### 分组 A：迁移与数据完整性（门槛用例，P0）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 / 通过标准 |
|---|---|---|---|---|
| M-1 | 唯一约束切换 | 升级前存在旧约束 `uq_terminal_mac` | 执行迁移 `040`；查询 `pg_constraint` | 新约束 `uq_terminal_mac_ip (ip_address, mac_address_normalized)` 存在，旧 `uq_terminal_mac` 已被移除 |
| M-2 | 空 MAC 脏数据清理 | 升级前存在 `mac_address_normalized IS NULL` 的终端 | 执行迁移后查询 `terminals` | NULL-MAC 终端被删除，`mac_address_normalized` 列置为 NOT NULL |
| M-3 | 历史数据保留 | 升级前已有 T1/T2 两行（同 MAC 不同 IP） | 迁移后查询 | T1/T2 两行均保留，未被折叠或丢失 |

---

### 分组 B：终端页（Terminals.tsx）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 / 通过标准 |
|---|---|---|---|---|
| T-1 | MAC 命中但 IP 不命中不再误判（回归旧缺陷） | 仅封堵 T1（IP=10.8.14.32）；T2 未封堵 | 打开终端页，观察 T1/T2 的封堵命中 | T1 显示封堵命中；T2 **不显示**封堵命中（旧逻辑下 T2 会因同 MAC 被 `black_match_type='mac'` 误判，本次必须消除） |
| T-2 | 双 IP 分别封堵后互不串扰 | 无 | 依次封堵 T1、T2 两个 IP | 两行终端各自独立显示封堵；`black_match_type` 为 `both`（IP+MAC 命中）或 `ip`，不再出现纯 `mac` |
| T-3 | NULL-MAC 条目的 IP 回退匹配 | 对账补建一条仅 IP=10.8.14.32 的无 MAC 黑名单 | 打开终端页 | T1 按 IP 命中显示封堵；T2 不受影响 |
| T-4 | 解封单 IP 后状态回落 | T1 处于 blocked | 对 T1 执行解封并刷新 | 仅 T1 变回 unblocked；若 T2 也封堵则仍保持 blocked |

---

### 分组 C：看板（Dashboard stats）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 / 通过标准 |
|---|---|---|---|---|
| D-1 | `total` 按 (IP, MAC) 计数 | T1/T2 均在库 | 打开看板 | `total = 2`（同一行 Terminal = 一个 (IP, MAC)，不再按 MAC 折叠为 1） |
| D-2 | `non_compliant` 单边违规不连带 | 仅 T1 触发 non_compliant | 打开看板 | `non_compliant = 1`；`non_compliant + compliant + bypass + unknown` 与 `total` 可加和，无宿主机连坐 |
| D-3 | `blocked` 按 distinct IP 统计 | 封堵 T1、T2 两个 IP | 打开看板 | `blocked = 2`（distinct IP 口径），且与黑名单页 active 总数一致 |
| D-4 | 同 IP 多防火墙不重复计数 | 同一 IP 在两个防火墙各有 active 条目 | 打开看板 | `blocked` distinct IP = 1，不按防火墙数重复 |

---

### 分组 D：黑名单页（Blacklist.tsx / stats）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 / 通过标准 |
|---|---|---|---|---|
| B-1 | `success_blocked` 口径一致 | 封堵 T1、T2 | 打开黑名单页 | active 记录 2 条，与看板 `blocked` 一致；T1/T2 各一条，MAC 相同但 IP 不同 |
| B-2 | `pending_retry_unblock ⊆ success_blocked` | 构造「已封锁但终端已合规/待解封」的 T1 | 打开黑名单页统计卡片 | T1 可同时出现在两个卡片；tooltip 明确口径，避免误解为数据矛盾 |
| B-3 | 解封后两卡联动 | T1 处于 active | 解封 T1 并刷新 | T1 从 `success_blocked` 移除，进入 `success_unblocked`；T2 仍为 active |
| B-4 | 唯一索引不冲突 | 无 | 对同一 IP 在不同防火墙分别封堵 | 均按 `(ip_address, firewall_tag)` 唯一创建成功；同 IP 同防火墙重复插入被约束阻止 |

---

### 分组 E：跨层状态一致性（最高风险，P0）

| 编号 | 用例 | 前置条件 | 操作步骤 | 预期结果 / 通过标准 |
|---|---|---|---|---|
| C-1 | 合规解封按 (MAC, IP) 分组 | T1 non_compliant 后转为合规 | 触发 `auto_unblock_compliant` 或待调度执行 | 仅 T1 解封；同 MAC 的 T2 状态不变（旧 MAC-only 逻辑会把 T2 一并解封/重置） |
| C-2 | retry-block 不串台 | T1 存在 `non_compliant + unblocked` 中间态 | 触发 retry-block | 仅重封 T1；`source_tag` 过滤口径与看板/终端页一致 |
| C-3 | 防火墙对账补建精确更新 | 防火墙实际封锁 IP=10.8.14.32，DB 缺黑名单 | 触发对账 `reconcile` | 对账补建后仅 T1 `status=blocked`，不误更新 T2；`firewall_tag` 推进正确 |
| C-4 | 对账自愈孤儿状态 | T1 `status=blocked` 但黑名单已无 active 支撑 | 触发对账自愈 | 自愈仅重置 T1 为 unblocked；**不改 `compliance_status`**（守三层防抖，避免震荡） |
| C-5 | 数据源解绑清理 | 存在绑定且 T1/T2 已封堵 | 执行 `safe_delete_binding` | 解封/删记录按 (MAC, IP) 定位，不误伤同 MAC 其它 IP 终端 |

---

## 四、执行顺序与优先级

1. **先跑迁移门槛（M 类）**：M-1/M-2/M-3 全部通过后，才进入功能回归。
2. **再跑最高风险跨层用例（C 类）**：C-1、C-3 优先（历史震荡/串台均源于 MAC-only 关联）。
3. **随后跑隔离展示（T/D/B 类）**：T-1、D-2、B-2 为隔离效果的直接体现。
4. 其余用例（T-4、B-4、D-4 等）作为补充回归协同执行。

**优先级标记**：P0 = 阻断上线（M-1/M-2/M-3、C-1/C-3）；P1 = 严重缺陷（T-1、C-2、C-4、D-2、B-2）；P2 = 一般（其余）。

---

## 五、通过标准与退出条件

- 所有 P0 用例 100% 通过，且无「同 MAC 不同 IP 状态串台」现象。
- P1/P2 用例通过率 ≥ 95%；未通过项需登记缺陷并说明影响范围。
- 退出条件：P0 + P1 全部关闭后方可安排正式发布（tag），避免带病上线。

---

## 六、缺陷记录模板

| 字段 | 说明 |
|---|---|
| 用例编号 | 如 C-1 |
| 复现步骤 | 操作路径与输入 |
| 实际结果 | 观察到的错误行为 |
| 预期结果 | 依据本清单 |
| 影响面 | 涉及页面/模块/数据 |
| 严重级别 | P0/P1/P2 |
| 相关截图/日志 | 附 SQL 结果、API 响应、控制台输出 |

---

> 附注：本文档覆盖 MAC+IP 复合唯一键改造的隔离验证。若后续调整用例或补充数据准备脚本，请同步更新本清单版本号与日期，保持与项目发布版本一致。