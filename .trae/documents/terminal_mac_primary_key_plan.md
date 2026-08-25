# 终端记录以 MAC 为唯一标识（修正 IP+MAC 联合主键）实施方案

## 1. 现状问题分析

### 1.1 IPGuard 基线侧（已正确处理多网卡）

**IPGuard MSSQL 数据源** ([compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L270-L287))：
```sql
SELECT AGT_IP_MAC_STR FROM AGENT WHERE AGT_IP_MAC_STR IS NOT NULL AND AGT_IP_MAC_STR <> ''
```

`AGT_IP_MAC_STR` 字段格式为：
```
88-66-5A-4E-E2-71(10.8.19.168)F0-D7-AF-D0-24-66(10.8.25.167)
```
即 `MAC1(IP1)MAC2(IP2)...` 格式，一个物理终端（多网卡）的所有网卡在同一行字符串中。

当前解析正则：
```python
mac_ip_pattern = re.compile(
    r'([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-]'
    r'[0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})\(([^)]*)\)'
)
```
使用 `findall()` 正确提取出所有 (MAC, IP) 对，展开为独立 entries 存入 Redis 缓存：
```json
[
  {"ip_address": "10.8.19.168", "mac_address": "88-66-5A-4E-E2-71"},
  {"ip_address": "10.8.25.167", "mac_address": "F0-D7-AF-D0-24-66"}
]
```

**IPGuard 侧多网卡处理已正确，无需修改。**

### 1.2 terminals 表（ARP 侧）问题

**当前模型** ([terminal.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/terminal.py#L42))：
```python
UniqueConstraint('ip_address', 'mac_address', name='uq_terminal_ip_mac')
```

使用 `(ip_address, mac_address)` 联合唯一约束，ARP 入库逻辑 ([arp_collector_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L297-L300)) 按此联合键 upsert：
```python
stmt = select(Terminal).where(
    (Terminal.ip_address == ip_addr) &
    (Terminal.mac_address == mac_normalized)
)
```

**问题场景**：当终端发生以下情况时，同一 MAC 会产生多条记录：
- DHCP 续租导致 IP 变更（MAC 不变，IP 变 → 产生新记录）
- ARP 缓存短暂同时存在新旧 IP
- 终端在有线/无线之间切换（但同一网卡切换本质是 IP 变化）

这导致：
1. **同一物理网卡（同一 MAC）** 在 terminals 表中存在多条记录（不同 IP）
2. 旧 IP 记录的 IP 不在 IPGuard 中（IP 已变），合规匹配失败 → 误判 non_compliant
3. 旧 IP 记录可能触发自动封禁（错误地封禁了已不存在的 IP）
4. 离线检测按 (IP, MAC) 判断，同一 MAC 的旧 IP 记录被误判为"离线"

**正确行为应该是**：
- **一张网卡（一个 MAC）= terminals 表中一条记录**
- IP 地址是网卡的**可变属性**，随 ARP 采集更新，不是唯一键的一部分
- 双网卡设备（MAC1→IP1, MAC2→IP2）= 两条记录（因为两张网卡独立通信，防火墙策略按 IP/MAC 生效，确实需要独立判断）
- 但同一 MAC 因 IP 变化**不应产生新记录**，只更新现有记录的 IP

### 1.3 合规匹配逻辑影响

当前合规匹配（`_match_ipguard_in_memory`）是：
```python
for entry in entries:
    if entry.get("ip_address") == ip_address and entry_mac == normalized_mac:
        return True
```

这是精确的 (IP, MAC) 匹配。只要 terminals 表中每个 MAC 只有一条记录（存最新 IP），这个逻辑就是正确的：
- 双网卡终端：MAC1+IP1 去匹配 IPGuard 中的 MAC1+IP1；MAC2+IP2 去匹配 IPGuard 中的 MAC2+IP2 → 两张网卡独立判断，正确
- 单网卡 IP 变更：MAC+IP_new 去匹配 IPGuard 中的 MAC+IP_new（因为 IPGuard 已同步最新数据）→ 正确匹配
- 如果不改 terminals 模型，旧 IP 记录 MAC+IP_old 匹配 IPGuard 中 MAC+IP_new 失败 → 误判

---

## 2. 技术方案

### 2.1 数据模型变更

**Terminal 模型**：
- 将唯一约束从 `UniqueConstraint('ip_address', 'mac_address')` 改为 `UniqueConstraint('mac_address_normalized')`
- `ip_address` 保留为字段，存储"最新发现的 IP"
- 不需要新增字段

**Blacklist 模型**：不需要修改——黑名单仍然按 (IP, MAC) 记录封禁条目，防火墙封禁操作本身就是基于具体的 IP+MAC，一个 MAC 在不同时期关联过的不同 IP 可能各自需要保留封禁记录（如 IP 地址被其他设备复用）。

### 2.2 ARP 入库逻辑变更

修改 `process_arp_entries()` ([arp_collector_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L266-L452))：

1. **查询条件改为仅按 MAC**：
   ```python
   # Before: (Terminal.ip_address == ip_addr) & (Terminal.mac_address == mac_normalized)
   # After:  Terminal.mac_address_normalized == mac_norm
   ```

2. **已存在记录时更新 IP**：
   ```python
   if existing:
       existing.ip_address = ip_addr          # 更新为最新 IP
       existing.updated_at = datetime.now(UTC)
       existing.source_tag = source_tag
       existing.source = "arp"
       # 如果之前是 unknown 状态（新建后还没检查），保持 unknown 等待本轮合规检查
       # 如果已有合规状态，保持原状，本轮会更新
   ```

3. **同批次去重改为按 MAC**：`seen_ips: set[str]` → `seen_macs: set[str]`

4. **离线检测改为按 MAC 判断**：
   ```python
   # Before: if terminal.ip_address not in seen_ips
   # After:  if terminal.mac_address_normalized not in seen_macs
   ```

### 2.3 合规结果应用逻辑

当前 ARP 采集后，合规结果回写时（第 356-391 行），`result_lookup` 的 key 是 `ip_address`。改为按 MAC 构建 lookup：

```python
# Before: result_lookup[item.get("ip_address")] = {...}
# After:  result_lookup[item.get("mac_address_normalized", item.get("mac_address"))] = {...}
```

然后在更新 Terminal 记录时，按 MAC 查找对应记录（因为 MAC 是唯一的），而不是依赖 unchecked_entries 中的引用。

### 2.4 合规服务逻辑

`batch_check_compliance()`、`auto_block_non_compliant()`、`auto_unblock_compliant()`、`recalculate_all_compliance()` 的核心匹配逻辑**无需修改**：
- 白名单匹配已支持 MAC 匹配（`_match_whitelist_in_memory`）→ 正确
- IPGuard 匹配是 (IP, MAC) 精确匹配 → 只要 terminals 表中是最新 IP，就能正确匹配
- Scope 条件匹配按每条记录独立判断 → 正确，因为每张网卡是独立记录

**唯一需要注意**：`auto_block_non_compliant()` 中构建 `blacklisted_pairs` 去重时，由于 MAC 已唯一，不会出现同一 MAC 重复处理的问题，无需额外修改。

---

## 3. 涉及文件修改

### 3.1 Backend

| 文件 | 修改内容 |
|------|----------|
| [terminal.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/terminal.py) | 唯一约束改为 `mac_address_normalized`，移除 `(ip, mac)` 联合约束；更新 Index |
| [arp_collector_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py) | 入库查询改为按 MAC；已存在时更新 IP；去重改为 seen_macs；离线检测改用 MAC 判断；合规结果 lookup 改用 MAC 作为 key |
| `backend/alembic/versions/033_*.py` | 迁移脚本：去重（保留每个 MAC 最新/被封禁的记录）、删除旧约束、添加新唯一约束 |

### 3.2 Frontend

前端无需修改——API 返回的终端列表仍然按记录展示，每张网卡（每个 MAC）一条记录，IP 显示最新值。

---

## 4. 实施步骤

### Phase 1: 数据库迁移
1. 创建迁移脚本 `033_terminal_mac_unique.py`：
   - **数据清理**：对每个 `mac_address_normalized`，选择保留策略：
     a. 如果有记录 status='blocked'，优先保留 blocked 记录（取 updated_at 最新的 blocked 记录）
     b. 如果没有 blocked 记录，保留 updated_at 最新（或 id 最大）的记录
     c. 删除其余重复记录
   - 删除旧约束 `uq_terminal_ip_mac`
   - 创建新唯一约束 `uq_terminal_mac` on `mac_address_normalized`
2. 更新 Terminal 模型定义

### Phase 2: ARP 入库逻辑重构
1. 修改 `process_arp_entries()`：
   - 查询条件改为按 `mac_address_normalized`
   - 已存在记录时更新 `ip_address` 为最新值
   - `seen_ips` → `seen_macs`
   - 离线检测判断条件改为 MAC 不在 seen_macs 中
   - 合规结果 result_lookup 的 key 从 ip_address 改为 mac_address_normalized

### Phase 3: 验证
1. Python 语法检查
2. 迁移脚本幂等性验证
3. Docker 重启 + 自动迁移测试

---

## 5. 风险与注意事项

### 5.1 数据迁移风险
- 现有数据中同一 MAC 可能有多条记录，迁移只保留一条，旧记录被删除
- **保留策略**：优先保留 blocked 状态记录（保护封禁状态），否则保留最新记录
- 旧记录如果关联了黑名单条目，黑名单中的 (IP, MAC) 记录不会被删除——黑名单独立于 terminals 表，历史封禁记录保留在 blacklist 表中不受影响

### 5.2 旧 IP 封禁残留问题
- 如果某 MAC 的旧 IP 已被封禁（blacklist 中有记录），但 terminals 表保留了最新 IP 记录（unblocked），可能出现状态不一致
- **处理方式**：
  - 迁移时选择保留策略优先保留 blocked 记录能缓解此问题
  - 如果黑名单中该 MAC 有旧 IP 的封禁记录，但新 IP 未封禁，防火墙规则按 IP 生效，新 IP 不会被封，终端可以通过新 IP 通信——这是正确行为（DHCP 换 IP 后如果新 IP 合规应该放行）
  - 自动解封逻辑会在终端合规后自动解封其当前 IP，历史旧 IP 的封禁记录可由清理任务处理

### 5.3 业务影响
- 迁移后终端列表中同一 MAC 不再出现多条记录，IP 始终显示最新发现的
- 双网卡终端仍然显示为两条记录（两个 MAC），正确反映物理现实
- 合规状态和封禁状态以每个 MAC 的最新记录为准
- 防火墙封禁仍然按具体 IP+MAC 执行，封禁操作不受影响

### 5.4 并发安全
- ARP 入库改为按 MAC upsert 后，仍然是"先查后写"模式，并发采集同一 MAC 有极小概率冲突
- 可优化为数据库级 `INSERT ... ON CONFLICT (mac_address_normalized) DO UPDATE`，但这是后续优化项

---

## 6. 验证要点

1. **迁移验证**：同一 MAC 的重复记录被正确合并，blocked 记录优先保留
2. **ARP 入库验证**：同一 MAC 的 IP 变化时更新现有记录的 IP 而非新建
3. **双网卡场景**：有线 MAC1 和无线 MAC2 各有一条独立记录，互不干扰，各自正确匹配 IPGuard
4. **合规计算验证**：IP 变更后不会因旧 IP 记录误判 non_compliant
5. **离线检测验证**：MAC 不在本次采集列表中才判定离线（而非旧 IP 消失）
6. **事件发送验证**：emit_terminal_online/offline 事件基于 MAC 去重，不重复发送
