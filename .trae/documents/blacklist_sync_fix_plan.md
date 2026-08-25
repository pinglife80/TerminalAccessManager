# 黑名单与防火墙封锁状态不同步问题修复计划

## 问题现象

* Dashboard和终端页面显示封锁终端数：85条（与防火墙实际一致）

* 黑名单管理页面显示活跃封锁条目：99条

* 差异14条，存在以下问题：

  1. 防火墙封锁失败但黑名单已创建记录（数据库状态与实际不一致）
  2. 存在重复的黑名单记录
  3. 存在孤儿记录（无对应终端、无防火墙标记）
  4. 多防火墙场景下唯一约束不正确

***

## 根因分析

通过代码审查发现以下问题：

### Bug 1：Blacklist唯一约束缺少`firewall_tag`

**文件**：`backend/app/models/blacklist.py` 第34行
**问题**：当前唯一部分索引为：

```python
Index('idx_blacklist_unique_active', 'ip_address', 'mac_address_normalized', unique=True,
      postgresql_where=(unblocked_at.is_(None) & (auto_unblocked == False)))
```

但一个终端绑定多个防火墙时，应该是**每个防火墙一条Blacklist记录**，缺少`firewall_tag`导致多防火墙场景下只能插入一条，违反业务需求。

### Bug 2：auto\_block\_non\_compliant中`errors`列表累积不重置

**文件**：`backend/app/services/compliance_service.py` 第477-519行
**问题**：`errors = []`在entry循环外初始化，每个entry处理后错误累积。判断条件：

```python
all_success = fw_success_count == len(firewall_tags) and len(errors) == 0
```

只要任意一个entry在任意防火墙上封锁失败，后续所有entry即使全部成功，`len(errors) > 0`也会导致`all_success=False`，Blacklist记录不会创建，造成数据库漏记。

### Bug 3：recalculate中现有记录检查缺少firewall\_tag过滤

**文件**：`backend/app/services/compliance_service.py` 第1619-1629行
**问题**：检查是否已有活跃黑名单记录时，只按`(ip, mac_norm)`查询，不区分`firewall_tag`。多防火墙场景下：

* 已有一个防火墙的记录时，会错误认为所有防火墙都已有记录，跳过创建

* 使用`scalar_one_or_none()`如果存在多条匹配会抛异常

### Bug 4：FirewallReconciliationService创建Blacklist时不填firewall\_tag和mac\_address

**文件**：`backend/app/services/firewall_reconciliation_service.py` 第165-204行
**问题**：

1. `_get_firewall_blocked_ips()`把所有防火墙的封锁IP合并到一个set，丢失了IP属于哪个防火墙的信息
2. `_create_db_entries()`创建记录时：

   * 不填`firewall_tag`字段

   * 不填`mac_address`和`mac_address_normalized`（只按IP查找terminal，MAC唯一化后可能找不到或找错）

   * 这些"幽灵记录"无法通过MAC关联到Terminal，导致黑名单计数偏高但终端统计正常

### Bug 5：Reconciliation按IP查找Terminal已过时

**文件**：`backend/app/services/firewall_reconciliation_service.py` 第167行
**问题**：v3.12已改为MAC作为终端唯一标识，一个IP可能对应历史记录，但这里仍按`ip_address`查询Terminal，MAC唯一化后IP可重复使用，可能：

* 找不到terminal → 创建新Terminal记录（错误）

* 找到旧terminal记录 → 更新错了terminal状态

### Bug 6：Reconciliation \_unblock\_from\_firewall 同样按IP操作，且不区分firewall\_tag

**文件**：`backend/app/services/firewall_reconciliation_service.py` 第215-290行
**问题**：发现DB有但防火墙没有的IP时，尝试在所有防火墙解封（多余操作），然后把该IP的所有Blacklist记录（不管属于哪个防火墙）都标记为unblocked。如果某些防火墙确实还封着该IP，会错误标记为已解封。

***

## 修复方案

### 修改文件清单

| 文件                                                          | 修改内容                                                            |
| ----------------------------------------------------------- | --------------------------------------------------------------- |
| `backend/app/models/blacklist.py`                           | 修复唯一约束，增加`firewall_tag`；增加mac\_address\_normalized NOT NULL约束迁移 |
| `backend/app/services/compliance_service.py`                | 修复errors累积bug；修复recalculate中重复检查；每个防火墙独立判断成功/失败创建记录             |
| `backend/app/services/firewall_reconciliation_service.py`   | 重写对账逻辑：按防火墙分别获取封锁列表，正确创建带firewall\_tag和MAC的记录                   |
| `backend/alembic/versions/035_blacklist_fix_sync_issues.py` | 数据迁移：清理/修复现有脏数据                                                 |

***

## 详细修改步骤

### Step 1: 修复Blacklist模型唯一约束

**文件**：[blacklist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/blacklist.py)

将唯一索引从：

```python
Index('idx_blacklist_unique_active', 'ip_address', 'mac_address_normalized', unique=True,
      postgresql_where=(unblocked_at.is_(None) & (auto_unblocked == False))),
```

改为：

```python
Index('idx_blacklist_unique_active', 'ip_address', 'mac_address_normalized', 'firewall_tag', unique=True,
      postgresql_where=(unblocked_at.is_(None) & (auto_unblocked == False))),
```

### Step 2: 修复auto\_block\_non\_compliant中errors累积bug

**文件**：[compliance\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py)

将每个entry循环内重置errors，并且改为**每个防火墙独立判断**：

* 每个防火墙封锁成功 → 创建该防火墙对应的Blacklist记录

* 某个防火墙封锁失败 → 只跳过该防火墙的记录，不影响其他防火墙和其他终端

* 全部防火墙都成功才更新Terminal.status = blocked

### Step 3: 修复recalculate中现有记录检查

**文件**：[compliance\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py)

在第1619-1629行，检查现有记录时按`(ip_address, mac_address_normalized, firewall_tag)`查询，每个防火墙独立检查是否已存在对应记录，不存在才创建。

### Step 4: 重写FirewallReconciliationService对账逻辑

**核心改动**：

1. `_get_firewall_blocked_ips()`改为按防火墙分别返回 `{fw_tag: set(ips)}`，不再合并去重
2. `_get_db_active_blacklist()`也按防火墙分组返回
3. 对账时**每个防火墙独立计算差异**：

   * missing\_in\_db: 该防火墙上有但该防火墙没有对应DB记录的IP → 查找对应terminal的MAC后创建带firewall\_tag的记录

   * missing\_in\_firewall: 该防火墙有DB记录但防火墙上已解封 → 在该防火墙上重新封锁（而不是解封！如果DB说应该封但防火墙没有，应该补封而不是标记DB为解封）
4. `_create_db_entries()`必须填写正确的：

   * `firewall_tag`: 所属防火墙

   * `mac_address`/`mac_address_normalized`: 通过IP查ARP表/当前Terminal关联获取MAC，避免创建无MAC记录
5. 移除"firewall返回0条就跳过"的保护逻辑改为警告并跳过该防火墙（不影响其他防火墙）
6. 修复"DB有但防火墙没有"的处理逻辑：应该是**补封锁**而不是**标记DB解封**，因为DB是权威源

### Step 5: 数据迁移脚本 035

**任务**：

1. 清理现有脏数据：

   * 标记没有`firewall_tag`的active记录为unblocked（这些是reconciliation创建的幽灵记录）

   * 标记`mac_address_normalized`为NULL的active记录为unblocked（无法关联终端）
2. 对于同一个(ip, mac, firewall\_tag)有多条active记录的情况，保留最新创建的一条，其余标记unblocked
3. 删除过期的unblocked历史记录（可选，保留unblocked\_at > 90天前的历史）

***

## 数据一致性校验逻辑

修复后每个Blacklist记录必须满足：

1. 活跃记录必须有`firewall_tag`（不能为空）
2. 活跃记录必须有`mac_address_normalized`（不能为空）
3. 同一`(ip_address, mac_address_normalized, firewall_tag)`在活跃状态下只能有一条记录
4. Blacklist活跃记录数 = Σ 每个防火墙上实际封锁IP数（通过对账保证）
5. Terminal表中`status='blocked'`的记录数 = 有至少一个活跃Blacklist记录的不同MAC数（一个MAC多个防火墙只算一个终端）

***

## 风险与处理

| 风险                      | 处理方式                                         |
| ----------------------- | -------------------------------------------- |
| 迁移误删有效记录                | 只标记`auto_unblocked=True`，不硬删除；迁移前建议先做一次数据库备份 |
| 对账补封导致误封                | 对账只补封DB中已有活跃记录但防火墙丢失的IP，不新增封锁；新增封锁只由合规检查触发   |
| 多防火墙解封部分失败              | 现有逻辑已经支持部分成功部分标记，保持不变，只修复成功才更新terminal状态     |
| Reconciliation获取防火墙列表失败 | 单个防火墙失败跳过不影响其他防火墙，记录error日志                  |

***

## 测试验证

1. 单元验证：模拟auto\_block部分防火墙成功部分失败，确认只创建成功防火墙的Blacklist记录
2. 集成验证：

   * 手动封锁一个终端 → 防火墙封锁成功 → Blacklist记录正确 → 计数一致

   * 防火墙API返回错误 → 不创建Blacklist记录 → 终端状态不更新 → 下一轮重试

   * 模拟重启服务触发reconciliation → 对账后数量一致，无重复记录
3. 数据验证：执行迁移后确认：

   * Blacklist活跃记录数 = Dashboard/终端页面封锁数 × 每个终端绑定的防火墙数（单防火墙环境两者相等）

   * 无firewall\_tag=NULL或mac\_address\_normalized=NULL的活跃记录

   * 无同一(ip, mac, fw\_tag)多条活跃记录

