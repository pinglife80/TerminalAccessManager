# 白名单终端合规状态频繁震荡修复计划

> 文档版本：v1.1  更新日期：2026-08-20

## 一、问题现象

白名单范围内的终端（如10.8.10.28）本应始终保持`bypass`状态，不参与合规计算，不会被封锁/解封。但实际出现`bypass → non_compliant → blocked → bypass → unblocked`的频繁震荡循环。

## 二、根因分析

经过全面代码审查，共发现**4个严重bug**共同导致此问题：

***

### Bug 1（核心根因）：防火墙对账服务越权修改compliance\_status

* **位置**：[firewall\_reconciliation\_service.py#L234-L237](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L234-L237)

* **问题代码**：

  ```python
  if terminal.status != TerminalStatus.BLOCKED.value:
      terminal.status = TerminalStatus.BLOCKED.value
      if terminal.compliance_status in ("unknown", "compliant", "bypass"):
          terminal.compliance_status = "non_compliant"  # ❌ 严重越权！
  ```

* **问题描述**：

  * 防火墙对账的职责**仅仅是同步防火墙实际封锁状态**到`status`字段

  * `compliance_status`（合规判定状态）只能由合规计算逻辑（`recalculate_all_compliance`）通过三层防震荡机制（对称确认计数、冷却期、IP宽限期）更新

  * 此代码发现IP在防火墙已封锁时，**直接强制将bypass/compliant/unknown改为non\_compliant**，完全绕过了所有防震荡保护

* **后果**：直接触发状态震荡链条的起点。

***

### Bug 2：补封逻辑查询活跃Blacklist仍带多余IP条件

* **位置**：[compliance\_service.py#L1549-L1554](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1549-L1554)

* **问题代码**：

  ```python
  bl_active_stmt = select(Blacklist.firewall_tag).where(
      (Blacklist.mac_address_normalized == mac_norm) &
      (Blacklist.ip_address == ip_addr) &  # ❌ 多余条件！
      (Blacklist.auto_unblocked == False) &
      (Blacklist.unblocked_at.is_(None))
  )
  ```

* **问题描述**：

  * 之前只修复了`auto_unblock_compliant`路径的此问题，但`_apply_compliance_result`中补封逻辑的查询仍然带IP条件

  * MAC是终端唯一稳定标识，IP可能因DHCP变化；带IP条件会导致查询不到已有的Blacklist记录，重复补封或错误判断

***

### Bug 3：解封逻辑查询Blacklist也带多余IP条件

* **位置**：[compliance\_service.py#L1521-L1526](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1521-L1526)

* **问题代码**：

  ```python
  bl_stmt = select(Blacklist).where(
      (Blacklist.ip_address == ip_addr) &  # ❌ 多余条件！
      (Blacklist.mac_address_normalized == mac_norm) &
      (Blacklist.unblocked_at.is_(None)) &
      (Blacklist.auto_unblocked == False)
  )
  ```

* **问题描述**：

  * 与Bug 2同理：按MAC分组解封时，DHCP换IP后查询不到应解封的Blacklist记录

  * 导致数据库中残留已解封但未标记的Blacklist条目，造成状态不一致

  * 防火墙对账会认为这些IP"应该被封锁"（因为DB中有活跃记录），触发重新封锁，形成震荡

***

### Bug 4：\_apply\_compliance\_result中的解封逻辑完全绕过冷却期保护

* **位置**：[compliance\_service.py#L1490-L1542](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1490-L1542)

* **问题代码**：

  ```python
  if terminal.status == "blocked" and new_compliance in ("bypass", "compliant"):
      fw_tags = await self._get_bound_firewall_tags(terminal.source_tag)
      if fw_tags:
          for fw_tag in fw_tags:
              success = await self._unblock_on_firewall(ip_addr, fw_tag)  # ❌ 无冷却期检查！
          # ... 直接标记Blacklist为auto_unblocked
  ```

* **问题描述**：

  * `auto_unblock_compliant`方法中有10分钟冷却期保护（刚被封锁的终端10分钟内不解封）

  * 但`_apply_compliance_result`（被`recalculate_all_compliance`调用）中的解封路径**完全没有冷却期检查**

  * 一旦状态通过对称确认变为bypass/compliant，立即解封，没有任何保护

  * 配合Bug 1（对账错误设置non\_compliant），形成：错误封锁→确认计数到阈值→立即解封→对账发现防火墙没封锁但DB有记录？不...配合Bug 3（残留Blacklist标记错误），形成完美震荡循环

***

### Bug 5（补充）：防火墙对账补建Blacklist时不检查白名单

* **位置**：[firewall\_reconciliation\_service.py#L207-L278](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L207-L278)

* **问题描述**：

  * 对账补建Blacklist记录时，没有检查该终端是否匹配白名单

  * 如果因历史bug导致白名单终端被错误封锁在防火墙，对账应该识别并纠正（解封），而非补建记录继续封锁

  * 防火墙实际状态是封锁状态的根本依据，但如果DB明确标记该终端是白名单bypass状态，说明这是异常封锁，应该纠正

## 三、修复方案

### 修复1：防火墙对账严禁修改compliance\_status

* 文件：`backend/app/services/firewall_reconciliation_service.py`

* 修改：移除第236-237行强制设置`compliance_status = "non_compliant"`的代码

* 原则：`status`字段（防火墙实际状态）和`compliance_status`字段（合规判定结果）职责严格分离

  * 防火墙对账**只更新`status`字段**，反映防火墙真实状态

  * `compliance_status`只能由合规计算逻辑更新

### 修复2：移除补封逻辑中多余的IP查询条件

* 文件：`backend/app/services/compliance_service.py`

* 修改：移除第1551行的`(Blacklist.ip_address == ip_addr) &`条件

* 原则：Blacklist活跃状态查询以MAC为唯一标识

### 修复3：移除解封逻辑中多余的IP查询条件

* 文件：`backend/app/services/compliance_service.py`

* 修改：移除第1522行的`(Blacklist.ip_address == ip_addr) &`条件

* 原则：同Bug 2，按MAC查询所有应解封的Blacklist记录

### 修复4：为\_apply\_compliance\_result的解封路径增加冷却期检查

* 文件：`backend/app/services/compliance_service.py`

* 修改：在第1490行解封逻辑前，增加与`auto_unblock_compliant`一致的冷却期检查

  * 查询该MAC最近10分钟内是否有auto\_block记录

  * 如果在冷却期内，跳过本次解封，保持blocked状态

  * 冷却期过后再执行解封，给系统稳定时间

### 修复5：防火墙对账补建Blacklist前检查白名单

* 文件：`backend/app/services/firewall_reconciliation_service.py`

* 修改：在`_create_db_entries_for_firewall`中，查询到Terminal后：

  * 加载白名单缓存，检查该IP/MAC是否匹配白名单

  * 如果匹配白名单且`compliance_status == "bypass"`：

    * 不创建Blacklist记录

    * 记录warning日志，说明发现白名单终端在防火墙被错误封锁

    * 不修改`status`字段（保持实际状态），由下一轮合规重算的冷却期逻辑安全处理解封

## 四、涉及修改文件

| 文件                                                        | 修改内容                                                                                                    |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `backend/app/services/firewall_reconciliation_service.py` | 1. 移除越权修改compliance\_status的代码2. 补建Blacklist前增加白名单检查，白名单bypass终端跳过补建                                    |
| `backend/app/services/compliance_service.py`              | 1. 移除补封逻辑Blacklist查询中多余的IP条件2. 移除解封逻辑Blacklist查询中多余的IP条件3. 为\_apply\_compliance\_result的解封路径增加10分钟冷却期保护 |

## 五、震荡链条完整说明

```
[正常白名单终端：bypass + unblocked + 防火墙无封锁 + 无Blacklist]
                           ↓
[某个原因导致防火墙封锁了该IP]（历史bug/手动测试/其他异常）
                           ↓
[防火墙对账运行] → Bug1触发：
  - 设置status=blocked
  - ❌越权设置compliance_status=non_compliant（绕过防震荡）
  - 创建Blacklist记录
                           ↓
[recalculate_all_compliance运行（第1次）]：
  - 白名单匹配→current_check_status=bypass
  - old_compliance=non_compliant（被Bug1错误设置）
  - compliant_confirm_count=1 < threshold(2) → 状态不变
                           ↓
[recalculate_all_compliance运行（第2次）]：
  - compliant_confirm_count=2 ≥ threshold → new_compliance=bypass
  - ❌Bug4触发：_apply_compliance_result无冷却期检查→立即解封
  - ❌Bug3触发：如果IP有变化，查不到Blacklist记录，无法正确标记auto_unblocked
                           ↓
[下一轮防火墙对账运行]：
  - 防火墙已解封→fw_ips无此IP
  - 如果Bug3导致Blacklist残留（未标记auto_unblocked）→db_ips_for_fw有此IP
  - 触发missing_in_fw→重新封锁该IP！
                           ↓
                          ↻ 无限循环震荡
```

## 六、验证方案

1. Python语法检查通过
2. 重建backend服务
3. 手动触发防火墙对账，确认白名单终端的compliance\_status不会被修改
4. 手动触发合规全量重算，确认解封逻辑冷却期生效
5. 观察审计日志至少30分钟，确认10.8.10.28等白名单终端不再出现状态频繁切换
6. 验证DHCP换IP场景下，Blacklist状态查询正确
7. 验证三个位置（Terminal状态、Blacklist表、防火墙实际封锁）计数一致

## 七、风险评估

* 风险等级：**低**

* 修改范围：

  * 移除错误代码（越权修改、多余查询条件）

  * 增加安全检查（冷却期、白名单检查）

  * 不改变正常合规判定流程，仅修复bug

* 回滚方案：直接revert本次修改即可

