# 合规基线管理 - ARP数据源下拉与操作按钮分析

> 创建日期：2026-07-16
> 分析范围：数据源管理 → 合规基线管理 Tab 中的操作区域

***

## 一、界面元素

合规基线管理 Tab 顶部有一个操作区域（[ComplianceBaselinesTab.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/ComplianceBaselinesTab.tsx) 第371-409行），包含：

1. **ARP Data Source 下拉菜单**：列出所有 `arp_ssh` 和 `arp_api` 类型的数据源
2. **Run Compliance Check 按钮**：触发合规检查
3. **Auto Block 按钮**：自动封锁不合规终端
4. **Auto Unblock 按钮**：自动解封已合规终端

***

## 二、ARP Data Source 下拉菜单分析

### 2.1 为什么有这个下拉菜单？

前端代码（第298-301行）：

```javascript
const arpSources = useMemo(
  () => (dataSources || []).filter((ds) => ds.type === 'arp_ssh' || ds.type === 'arp_api'),
  [dataSources],
);
```

**原因**：合规检查是基于 ARP 数据源采集的终端信息进行的。ARP 数据源负责发现网络中的终端（IP + MAC），然后系统根据白名单和 IP-Guard 数据判断这些终端是否合规。下拉菜单允许用户选择只检查某个 ARP 数据源发现的终端，或选择"All"检查所有。

### 2.2 业务意义

| 选择       | 含义                       |
| -------- | ------------------------ |
| All      | 检查所有 ARP 数据源发现的未知合规状态的终端 |
| 指定 ARP 源 | 仅检查该数据源发现的未知合规状态的终端      |

***

## 三、三个操作按钮分析

### 3.1 Run Compliance Check

**前端代码**（第307-325行）：

* API: `POST /data-sources/compliance/check`

* 参数: `arp_source_tag`（可选）、`force: false`

* 作用: 检查 `compliance_status == "unknown"` 的终端是否合规

**后端实现**（[data\_sources.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/data_sources.py) 第515-561行）：

* 查询 `Terminal` 表中 `compliance_status == "unknown"` 的记录

* 调用 `batch_check_compliance` 方法，与白名单和 IP-Guard 数据比对

* 更新终端的 `compliance_status` 字段（bypass / compliant / non\_compliant）

**是否生效**：✅ 生效。手动触发和定时任务（默认300秒间隔）都使用同一方法。

### 3.2 Auto Block

**前端代码**（第327-349行）：

* API: `POST /data-sources/compliance/auto-block`

* 参数: `arp_source_tag`（必选）、`block_time: '30d'`、`dry_run: false`

* 作用: 封锁指定 ARP 源下所有 `compliance_status == "non_compliant"` 且未封锁的终端

**后端实现**（[compliance\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py) 第354-460行）：

1. 查询指定 ARP 源下 `non_compliant` 且 `status != 'blocked'` 的终端
2. 通过 `DataSourceBinding` 查找关联的防火墙
3. 调用防火墙 API 封锁 IP
4. 创建 `Blacklist` 记录（`is_auto_blocked=True`）

**是否生效**：✅ 生效。手动触发和定时任务中都调用 `auto_block_non_compliant`。定时任务在合规检查发现 `non_compliant > 0` 时自动触发（[main.py 第322-328行](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L322-L328)）。

**业务场景**：当新终端接入网络且不在白名单/IP-Guard 中时，合规检查标记为 `non_compliant`，Auto Block 会自动封锁该终端。

### 3.3 Auto Unblock

**前端代码**（第351-367行）：

* API: `POST /data-sources/compliance/auto-unblock`

* 无参数

* 作用: 解封已变为合规状态的被封锁终端

**后端实现**（[compliance\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py) 第592-680行）：

1. 查询所有 `auto_unblocked == False` 的黑名单记录
2. 按 `(ip, mac)` 分组，检查该终端是否已合规（白名单或 IP-Guard 匹配）
3. 如果合规，在**所有防火墙**上解封
4. 仅当所有防火墙都成功解封时，才更新终端状态

**是否生效**：✅ 生效。手动触发和定时任务（默认600秒间隔）都使用同一方法。

**业务场景**：当被封锁的终端后来被加入白名单或 IP-Guard 中时，Auto Unblock 会自动解封该终端。

***

## 四、定时任务与手动触发对比

| 操作               | 手动触发       | 定时任务         | 定时间隔      |
| ---------------- | ---------- | ------------ | --------- |
| Compliance Check | ✅ 可选 ARP 源 | ✅ 遍历所有 ARP 源 | 300秒（可配置） |
| Auto Block       | ✅ 必选 ARP 源 | ✅ 合规检查后自动触发  | 跟随合规检查    |
| Auto Unblock     | ✅ 无参数      | ✅ 独立定时任务     | 600秒（可配置） |

**关键发现**：手动触发和定时任务使用相同的后端方法，功能完全一致。手动触发适用于即时操作场景，定时任务保证系统持续运行。

***

## 五、问题与建议

### 5.1 当前无问题

三个按钮功能都正常生效，与定时任务逻辑一致。下拉菜单的设计合理，允许用户针对特定 ARP 源进行操作。

### 5.2 潜在改进建议（仅供参考，非必须修改）

1. **Auto Block 未选 ARP 源时的提示**：前端已做了校验（第328行），未选择时会提示用户
2. **Auto Unblock 无 ARP 源筛选**：Auto Unblock 会检查所有黑名单记录，不限 ARP 源，这是合理的因为解封逻辑需要全局视角
3. **操作结果展示**：当前通过 toast 提示，如果需要查看详细日志可查看审计日志页面

***

## 六、结论

| 问题                         | 答案                               |
| -------------------------- | -------------------------------- |
| 为什么有 ARP Data Source 下拉？   | 合规检查基于 ARP 数据源发现的终端，下拉菜单用于选择检查范围 |
| Run Compliance Check 是否生效？ | ✅ 生效，与定时任务使用同一方法                 |
| Auto Block 是否生效？           | ✅ 生效，手动和定时任务都调用同一方法              |
| Auto Unblock 是否生效？         | ✅ 生效，手动和定时任务都调用同一方法              |
| 三个按钮的业务意义                  | 手动触发合规检查、封锁不合规终端、解封已合规终端         |

