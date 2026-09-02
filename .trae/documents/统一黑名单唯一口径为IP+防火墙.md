# 统一黑名单活跃条目唯一口径为 IP + 防火墙

> 文档版本：v1.0  更新日期：2026-09-01

## 1. 摘要（Summary）

用户质疑"同一 IP 在同一防火墙不可能被封锁两次，重复条目从哪来"。经核查，确认：

- **防火墙层（Sangfor）按 IP 封锁且幂等**，同一 IP 在同一防火墙物理上只有一条封锁记录。
- **数据库 Blacklist 表的"活跃唯一索引"是 `(ip_address, mac_address_normalized, firewall_tag)`**，粒度是 IP+MAC，与防火墙"IP 唯一"的口径不一致。
- 当 DHCP 把同一 IP 先后分配给不同 MAC 的终端时，就会出现"同一 IP + 同一防火墙 + 不同 MAC"的多条活跃行——即用户看到的"重复条目"。这不是防火墙重复，而是 DB 建模口径错误。

本方案将 **活跃唯一口径统一为 `(ip_address, firewall_tag)`**，MAC 降级为可更新的元数据字段，从而让 DB 活跃行数与防火墙封锁 IP 数严格一一对应，彻底消除"重复条目"与"行数口径"偏差。

## 2. 现状分析（Current State Analysis）

### 2.1 防火墙封锁只认 IP（已确认）

- [sangfor_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/sangfor_service.py#L291-L374) `block_ip` 只收 `ip_list`，并有幂等检查：`_find_blacklist_entry(ip)` 已存在就 `skip`。
- [sangfor_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/sangfor_service.py#L376-L437) `unblock_ip` 同样只按 IP（`srcIP`）删除。

### 2.2 数据库唯一索引口径错误（根因之一）

[blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/blacklist.py#L41-L42)：

```python
Index('idx_blacklist_unique_active', 'ip_address', 'mac_address_normalized', 'firewall_tag',
      unique=True, postgresql_where=(unblocked_at.is_(None) & (auto_unblocked == False)))
```

因为含 `mac_address_normalized`，同一 `(ip, firewall)` 只要 MAC 不同即可并存。

### 2.3 四处 Blacklist 创建点，判重口径自相矛盾

| 位置 | 判重条件 | 是否正确 |
|------|----------|----------|
| [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L618-L629) `auto_block_non_compliant` | `(ip, mac, fw)` | 否 |
| [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1994-L2003) `_apply_compliance_result` | `(ip, mac, fw)` | 否 |
| [main.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L442-L482) retry-block 调度任务 | 仅按 MAC 预检后按 fw 逐个 insert（无 ip+fw 判重） | 否 |
| [firewall_reconciliation_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L357-L369) `_create_db_entries_for_firewall` | `(ip, fw)` | **已经正确** |

> 讽刺的是，对账服务（reconciliation）**早已按 `(ip, fw)` 判重**，其余三处却按 `(ip, mac, fw)`，这正是系统自我割裂、产生重复条的根源。

### 2.4 重复条目产生的完整链条

1. 终端 A（MAC-A）拿到 IP `10.8.24.177`，不合规 → 插入行 `(10.8.24.177, MAC-A, af)`，防火墙封锁该 IP。
2. 终端 A DHCP 换 IP（旧 IP 封锁记录并未释放），终端 B（MAC-B）拿到 `10.8.24.177`。
3. 终端 B 不合规 → `block_ip` 在防火墙侧"已存在 skip"，但代码按 `(ip, mac, fw)` 判重未命中，**又插入一行** `(10.8.24.177, MAC-B, af)`。

结果：DB 两条活跃行，防火墙只有一条。`auto_unblock_compliant` 按 MAC 分组、`_repair_stale_terminal_status` 按 MAC/IP 匹配，都会因此产生错位与反复封锁/解封。

## 3. 变更方案（Proposed Changes）

统一原则：**活跃黑名单条目以 `(ip_address, firewall_tag)` 唯一**。当同一 IP+防火墙已有活跃行而新终端（新 MAC）触发封锁时，**原地更新该行的 MAC**（MAC 是"当前占用该 IP 的终端"的元数据），而非新增行。

### 3.1 新增迁移 `036_blacklist_unique_ip_firewall`（新建文件）

路径：`backend/alembic/versions/036_blacklist_unique_ip_firewall.py`

参照 [035_blacklist_fix_sync_issues.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/alembic/versions/035_blacklist_fix_sync_issues.py) 写法，`upgrade()` 依次：

1. **去重**：对 `(ip_address, firewall_tag)` 存在多条活跃行（`unblocked_at IS NULL AND auto_unblocked = false`）的，保留 `blocked_at DESC, id DESC` 最新一条，其余标记 `auto_unblocked = true, unblocked_at = now, unblocked_by = 'migration'`，`reason` 追加 `' [migration: duplicate IP+firewall entry]'`。
2. **删旧索引**：`DROP INDEX IF EXISTS idx_blacklist_unique_active`。
3. **建新唯一索引**：

```sql
CREATE UNIQUE INDEX idx_blacklist_unique_active
ON blacklist (ip_address, firewall_tag)
WHERE unblocked_at IS NULL AND auto_unblocked = false
```

`downgrade()`：删新索引，恢复旧的 `(ip_address, mac_address_normalized, firewall_tag)` 唯一索引。

### 3.2 修改 [blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/blacklist.py#L41-L42)

将 `__table_args__` 中 `idx_blacklist_unique_active` 改为：

```python
Index('idx_blacklist_unique_active', 'ip_address', 'firewall_tag', unique=True,
      postgresql_where=(unblocked_at.is_(None) & (auto_unblocked == False)))
```

### 3.3 新增共享 helper（避免三处重复同样逻辑）

在 `compliance_service.py` 新增一个私有方法（供三处复用）：

```python
async def _attach_active_blacklist(self, ip, mac_addr, mac_norm, fw_tag, reason,
                                   source_tag, expires_at) -> str:  # 返回 'created' | 'updated'
    # 先查 (ip, fw) 活跃行；命中则原地更新 mac_address/mac_address_normalized（必要时刷新 reason/expires_at），
    # 未命中则 INSERT，并捕获 IntegrityError 回滚该条以保护上层 session。
```

### 3.4 修改三处创建点，改用 `(ip, fw)` 判重 + 原地更新 MAC

1. [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L616-L652) `auto_block_non_compliant`：
   - 将 `existing_stmt` 的 `mac_address_normalized == mac_norm` 条件删除，仅保留 `(ip, fw)`；命中后调用 `_attach_active_blacklist` 原地更新 MAC 而非 `continue`。

2. [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1992-L2026) `_apply_compliance_result`：
   - 同样将 `existing_check` 改为 `(ip, fw)`，命中改走 `_attach_active_blacklist` 更新 MAC。

3. [main.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L442-L482) retry-block 调度任务：
   - 将"仅按 MAC 预检"改为按 `(ip, fw)` 判重；对每个 `fw_tag` 调用 `service._attach_active_blacklist(...)` 完成创建/更新，避免重复 insert 触发的 `IntegrityError` 回滚整个批次。

### 3.5 对账服务（无需改动）

[firewall_reconciliation_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L357-L369) 已按 `(ip, fw)` 判重，与新口径一致，保持不变。

## 4. 假设与决策（Assumptions & Decisions）

- **假设**：DHCP 场景下同一 IP 任意时刻只被一个终端占用，因此"原地更新 MAC"语义正确（新终端接管该 IP 的封锁记录）。
- **边界**：本次只修复"重复条目 / 行数口径"，**不改动** DHCP 换 IP 时机（旧 IP 封锁未释放、新 IP 未封锁）这一更深层问题——它与本问题独立，若需处理应另立方案。
- **不改动** `compliance_status` 的判定逻辑、三层防抖、冷却期保护等，只动黑名单判重与唯一索引。
- 迁移需在 `manage.sh` 的 `upgrade`（含 migrate）流程中落地，确保自动备份可回滚。

## 5. 验证步骤（Verification）

1. `manage.sh upgrade` 执行迁移并重建重启。
2. 执行 SQL 确认无重复活跃行：
   `SELECT ip_address, firewall_tag, count(*) FROM blacklist WHERE unblocked_at IS NULL AND auto_unblocked=false GROUP BY ip_address, firewall_tag HAVING count(*) > 1;`（应返回 0 行）
3. 容器指纹核对：`docker exec tam_backend grep -n "ip_address.*firewall_tag" .../blacklist.py` 确认新索引已部署。
4. 业务链测试：构造"同一 IP 换 MAC"场景，触发 auto-block → 断言仅 1 行活跃、MAC 为新终端；再触发 auto-unblock / retry-block，确认状态一致、无振荡、无重复行。