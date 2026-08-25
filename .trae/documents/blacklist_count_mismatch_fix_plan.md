# 黑名单计数差1条问题修复计划（更新版）

## 事实核对（更正之前错误推测）

| 项目               | 事实                           |
| ---------------- | ---------------------------- |
| Terminal.status  | blocked ✅（正确，防火墙确实封锁了）       |
| 防火墙实际状态          | blocked ✅（用户确认确实在封锁列表中）      |
| Blacklist活跃记录    | ❌ 0条（漏记录，这是计数不一致的原因）         |
| Dashboard/终端页面统计 | 按Terminal.status统计 = 85 ✅ 正确 |
| 黑名单页面统计          | 按Blacklist活跃记录统计 = 84 ❌ 少1条  |

**正确结论**：防火墙实际封锁了85条，Terminal记录正确，Blacklist漏了1条记录，导致黑名单页面统计少1。

***

## 根因分析

### 根本原因：Firewall Reconciliation Service 存在字段引用错误，无法补建缺失记录

对账(reconciliation)的设计原则是：**防火墙实际封锁状态是最终事实依据**，对于防火墙已封锁但Blacklist中没有记录的IP，应该自动补建Blacklist记录。

但在代码中：
[firewall\_reconciliation\_service.py:219-223](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L219-L223)

```python
term_stmt = select(Terminal).where(
    Terminal.ip_address == ip_address
).order_by(Terminal.last_seen.desc())  # <-- BUG HERE
```

**`Terminal`模型根本没有`last_seen`字段**，正确的字段名是`timestamp`。这个错误导致SQL查询抛出异常，虽然外层有try-except捕获错误只影响单个IP，但会导致：

1. 对账时检测到这个IP在防火墙封锁中但Blacklist缺失
2. 尝试查询Terminal获取MAC地址时，因为`last_seen`字段不存在抛出异常
3. 异常被外层catch，只打日志不创建Blacklist记录
4. 每次对账都无法补建这条记录，一直缺失

这就是为什么重启后、对账后这条记录始终补不上：每次执行到这里都报错跳过。

### 次要问题：recalculate\_all\_compliance中查询活跃Blacklist多加了IP条件

注释写着"Query by MAC only (IP may change due to DHCP)"，但代码实际上仍然加上了`Blacklist.ip_address == ip_addr`条件，DHCP换IP时会漏查活跃记录。这个问题不影响当前案例（IP没变），但也是一个bug需要修复。

***

## 需要修复的文件

1. **`backend/app/services/firewall_reconciliation_service.py`** - 修复`last_seen`→`timestamp`字段名错误
2. **`backend/app/services/compliance_service.py`** - 修复补封逻辑中活跃Blacklist查询，移除不必要的IP条件

***

## 修复步骤

### 1. 修复firewall\_reconciliation\_service.py字段名错误

将第221行：

```python
).order_by(Terminal.last_seen.desc())
```

改为：

```python
).order_by(Terminal.timestamp.desc())
```

（Terminal模型中`timestamp`字段就是最后ARP看到的时间，对应原来要表达的"最近活跃优先"逻辑）

### 2. 修复compliance\_service.py补封逻辑中的查询条件

第1549-1554行，按注释说明只按MAC查询，移除IP条件：

```python
# Before:
bl_active_stmt = select(Blacklist.firewall_tag).where(
    (Blacklist.mac_address_normalized == mac_norm) &
    (Blacklist.ip_address == ip_addr) &  # <-- 删除这一行
    (Blacklist.auto_unblocked == False) &
    (Blacklist.unblocked_at.is_(None))
)

# After:
bl_active_stmt = select(Blacklist.firewall_tag).where(
    (Blacklist.mac_address_normalized == mac_norm) &
    (Blacklist.auto_unblocked == False) &
    (Blacklist.unblocked_at.is_(None))
)
```

这保证DHCP换IP后也能正确找到这个MAC对应的所有活跃Blacklist记录。

### 3. 验证修复

重启服务后，手动触发一次防火墙对账，预期结果：

* 对账检测到10.8.16.254在防火墙封锁但Blacklist缺失

* 成功查询到Terminal记录，获取到MAC地址

* 创建Blacklist记录，`firewall_tag='af'`，`mac_address_normalized='F83E958B7742'`

* 三个位置计数一致：Terminal=85，Blacklist=85，Dashboard=85，防火墙实际=85

***

## 风险评估

| 风险            | 影响   | 处理                                              |
| ------------- | ---- | ----------------------------------------------- |
| 修改字段名错误影响其他逻辑 | 极低   | 只改一个排序字段名，逻辑不变，只是修复了错误引用                        |
| 移除IP条件导致重复创建  | 极低   | 后续创建Blacklist前还有按(ip, mac, fw\_tag)的幂等检查，不会重复创建 |
| 历史其他缺失记录也被补建  | 正面影响 | 所有对账遗漏都会被补，保证数据一致                               |

***

> 文档版本：v1.1 更新日期：2026-08-20

