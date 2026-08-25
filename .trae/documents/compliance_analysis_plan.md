# 合规计算逻辑全面分析文档

> 文档版本：v1.0  更新日期：2026-08-19

***

## 一、合规计算整体架构

### 1.1 核心服务模块

| 文件                                                        | 功能                              |
| --------------------------------------------------------- | ------------------------------- |
| `backend/app/services/compliance_service.py`              | **核心合规服务**：合规检查、自动封堵、自动解封、全量重算  |
| `backend/app/main.py`                                     | **调度器入口**：所有周期性后台任务的注册和调度       |
| `backend/app/services/arp_collector_service.py`           | **ARP 数据采集**：定期采集网络 ARP 表，发现新终端 |
| `backend/app/services/firewall_reconciliation_service.py` | **防火墙对账**：同步防火墙与数据库黑名单状态        |

### 1.2 数据流向总览

```
┌─────────────────────┐
│  ARP 数据采集       │ ← 每 300 秒
│  (scheduler_arp_)  │
│   collection)      │
└────────┬────────────┘
         │ 发现新终端
         ▼
┌─────────────────────┐
│  合规检查           │ ← 每 300 秒
│  (scheduler_compl_)│
│   iance_check)     │
└────────┬────────────┘
         │ 计算合规状态
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────┐
│ IPGuard │ │  白名单     │
│ 基线    │ │  (Whitelist)│
└───┬────┘ └──────┬───────┘
    │             │
    ▼             ▼
┌─────────────────────┐
│  合规状态判定        │
│  bypass/compliant/  │
│  non_compliant      │
└────────┬────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────┐
│ 自动封堵│ │  自动解封   │ ← 每 600 秒
└────────┘ └────────────┘
```

***

## 二、合规状态判定逻辑

### 2.1 三级判定规则

**核心函数**: `ComplianceService.check_compliance()` (第 100-139 行)

```
判定优先级：
1. 白名单匹配 → bypass（强制绕过，最高优先级）
2. IPGuard 基线匹配 → compliant（合规）
3. 均不匹配 → non_compliant（不合规）
```

### 2.2 白名单匹配规则

**函数**: `_match_whitelist_in_memory()` (第 804-844 行)

| pattern\_type | 匹配条件          | 说明                  |
| ------------- | ------------- | ------------------- |
| `mac_only`    | MAC 地址精确匹配    | 仅检查 MAC             |
| `single_ip`   | IP 地址精确匹配     | 单 IP 匹配             |
| `cidr`        | IP 在 CIDR 网段内 | 如 `192.168.0.0/24`  |
| `ip_range`    | IP 在范围内       | 如 `192.168.1.1-100` |
| `both`        | IP + MAC 同时匹配 | 双条件绑定               |

**匹配逻辑**：

* 同时指定 `ip_pattern` 和 `mac_address` → 两者必须同时匹配

* 仅指定 `ip_pattern` → 只需 IP 匹配

* 仅指定 `mac_address` → 只需 MAC 匹配

### 2.3 IPGuard 基线匹配

**函数**: `_match_ipguard_in_memory()` (第 909-920 行)

* 精确匹配 `ip_address` + `mac_address`（MAC 格式归一化为 `XX-XX-XX-XX-XX-XX`）

* 所有启用的 IPGuard 数据源的缓存数据合并匹配

### 2.4 缓存机制

| 缓存         | Key                           | TTL        | 更新时机                  |
| ---------- | ----------------------------- | ---------- | --------------------- |
| 白名单        | `whitelist:all`               | 300 秒（可配置） | 白名单增删改时失效 + 定期从 DB 重载 |
| IPGuard    | `ipguard:{source_tag}`        | 900 秒（可配置） | IPGuard 同步时更新         |
| IPGuard 备份 | `ipguard:backup:{source_tag}` | 永久         | 同步失败时用作 fallback      |

***

## 三、合规计算周期与触发条件

### 3.1 周期性调度任务

| 任务函数                         | 调度参数                                  | 默认周期       | 功能                        |
| ---------------------------- | ------------------------------------- | ---------- | ------------------------- |
| `scheduled_arp_collection`   | `scheduler_arp_collection_interval`   | **300 秒**  | ARP 数据采集，发现新终端            |
| `scheduled_compliance_check` | `scheduler_compliance_check_interval` | **300 秒**  | 合规检查 + 自动封堵 + 重试封堵 + 合规告警 |
| `scheduled_ipguard_sync`     | `scheduler_ipguard_sync_interval`     | **600 秒**  | IPGuard 基线数据同步 + 触发全量重算   |
| `scheduled_auto_unblock`     | `scheduler_auto_unblock_interval`     | **600 秒**  | 自动解封检查                    |
| `firewall_reconciliation`    | 硬编码 300 秒                             | **300 秒**  | 防火墙与数据库黑名单状态同步            |
| `cleanup_expired_blacklist`  | 硬编码 3600 秒                            | **3600 秒** | 过期黑名单清理                   |

### 3.2 非周期性触发（即时）

| 触发源          | 调用函数                                                            | 场景            |
| ------------ | --------------------------------------------------------------- | ------------- |
| IPGuard 同步完成 | `recalculate_all_compliance()`                                  | 同步新的基线数据后立即重算 |
| 白名单增/删/改     | `recalculate_all_compliance()`                                  | 白名单变更后即时重算    |
| 白名单导入完成      | `invalidate_whitelist_cache()` + `recalculate_all_compliance()` | 批量导入后         |
| 白名单备份恢复      | `invalidate_whitelist_cache()` + `recalculate_all_compliance()` | 从备份恢复后        |
| 合规 API 手动调用  | `recalculate_all_compliance()`                                  | 用户在 UI 手动触发   |

### 3.3 调度器内部控制机制

每个调度任务都有：

* **分布式锁**（Redis 实现）：防止多实例并发执行同一任务

* **任务暂停控制**（Redis key `scheduler:ctrl:{task_name}`）：支持动态暂停/恢复

* **超时保护**：锁自动过期防止死锁

***

## 四、自动封堵（Auto-Block）机制

### 4.1 触发条件

**函数**: `auto_block_non_compliant()` (第 362-613 行)

**筛选条件（AND 关系）**：

1. `Terminal.source_tag == arp_source_tag` — 属于该 ARP 数据源
2. `Terminal.compliance_status == "non_compliant"` — 合规状态为不合规
3. `Terminal.status != "blocked"` — 当前未被封堵
4. 不在活跃黑名单中（`Blacklist.auto_unblocked == False` 的记录中不存在对应 IP+MAC）

### 4.2 执行流程

```
1. 查询不合规终端 → 过滤掉已在黑名单中的
2. 获取防火墙绑定（DataSourceBinding）
3. 预加载所有防火墙服务实例
4. 逐个终端处理：
   a. dry_run 模式：仅记录不执行
   b. 非 dry_run：
      - 对每个关联防火墙调用 SangforService.block_ip()
      - 所有防火墙都成功 → 创建黑名单记录 + 更新终端状态
      - 任一防火墙失败 → 跳过（不记录）
5. 创建 Blacklist 记录：
   - is_auto_blocked=True
   - auto_unblocked=False
   - 过期时间默认 30d（可配置 block_time）
   - 每个防火墙创建独立记录
6. 更新 Terminal 状态：
   - status = "blocked"
   - firewall_tag = 关联防火墙 tag
   - 追加备注信息
7. 发送事件：
   - emit_terminal_blocked()
   - emit_auto_block_triggered()
8. 封堵数超过阈值 → emit_block_threshold_exceeded()
9. 记录审计日志
```

### 4.3 重试封堵机制

在 `scheduled_compliance_check` 任务中（第 334-402 行），还存在一个 **重试封堵** 流程：

* 针对 `compliance_status == "non_compliant" AND status == "unblocked"` 的终端

* 这些终端可能因防火墙 API 临时故障导致封堵未成功

* 使用独立的 block\_time 解析逻辑，直接调用 `_block_on_firewall()` 重试

***

## 五、自动解封（Auto-Unblock）机制

### 5.1 触发条件

**函数**: `auto_unblock_compliant()` (第 618-794 行)

**筛选条件**：

* `Blacklist.auto_unblocked == False` — 未被自动解封过的黑名单记录

### 5.2 执行流程

```
1. 查询所有 auto_unblocked=False 的黑名单记录
2. 按 (ip_address, mac_address) 分组
3. 每组处理：
   a. 重新检查合规性（白名单 + IPGuard）
   b. 如果现在合规 → 尝试在所有关联防火墙上解封
   c. 解封逻辑：
      - 有 firewall_tag → 直接调用 _unblock_on_firewall()
      - 无 firewall_tag → 通过 DataSourceBinding 查找绑定的防火墙
      - 完全无防火墙 → 直接在 DB 中标记
4. 全防火墙解封成功：
   - 标记所有 Blacklist 记录 auto_unblocked=True, unblocked_at=now
   - 更新 Terminal：
     - status = "unblocked"
     - firewall_tag = None（清空）
     - compliance_status = "bypass" 或 "compliant"
   - 追加解封备注
5. 部分成功：仅标记成功解封的防火墙记录，终端保持 blocked
6. 发送事件：
   - emit_auto_unblock_triggered()
   - emit_terminal_unblocked()
7. 记录审计日志
```

***

## 六、全量合规重算（Recalculate）机制

### 6.1 触发条件

**函数**: `recalculate_all_compliance()` (第 1442-1616 行)

| 触发场景         | 说明           |
| ------------ | ------------ |
| IPGuard 同步完成 | 新基线数据可用      |
| 白名单增删改       | 规则变更后即时生效    |
| 白名单导入/恢复     | 批量数据变更后      |
| 手动触发         | 用户点击"重算合规状态" |

### 6.2 执行流程

```
1. 获取分布式锁（compliance:recalc:lock）
2. 加载白名单 + IPGuard 缓存
3. IPGuard 数据完全不可用 → 中止（防止误判）
4. 分页处理所有 Terminal 记录（BATCH_SIZE=100）：
   a. 内存匹配白名单
   b. 内存匹配 IPGuard
   c. 合规状态判定：
      - 匹配白名单 → bypass
      - 匹配 IPGuard → compliant
      - 均不匹配 →
        * 之前 non_compliant/unknown → 直接 non_compliant
        * 之前 compliant/bypass → 需满足确认阈值（confirm_threshold）
          - 递增 non_compliant_confirm_count
          - 达到阈值 → non_compliant + 重置计数
          - 未达阈值 → 保持原状态（防止 IPGuard 波动误判）
   d. 调用 _apply_compliance_result() 应用变更
   e. 如状态变更且非 blocked → 自动解封
5. 每个批次 flush + commit
6. 记录审计日志（含耗时统计）
7. 释放锁
```

### 6.3 确认阈值机制

为防止 IPGuard 数据波动导致的状态抖动，系统引入了 **确认阈值（Confirm Threshold）**：

* 仅对从 `compliant`/`bypass` 转为 `non_compliant` 的情况生效

* 需连续 N 次检测到不合规才真正切换状态

* 配置项：`alert_non_compliant_confirm_threshold`（默认值由 `_get_confirm_threshold()` 读取）

* 每次未达阈值时递增 `non_compliant_confirm_count`

* 达到阈值后重置计数并切换状态

***

## 七、合规告警机制

### 7.1 周期性告警

在 `scheduled_compliance_check` 任务末尾（第 404-431 行）执行：

```
计算流程：
1. 从数据库获取终端统计（TerminalService.get_stats()）
2. 计算有效合规率：(compliant + bypass) / (compliant + bypass + non_compliant + unknown) × 100%
3. 检查阈值：
   - alert_compliance_rate_threshold（默认 80%）
   - 低于阈值 → emit_compliance_alert()
```

### 7.2 封堵数量告警

在 `auto_block_non_compliant()` 中（第 587-593 行）执行：

```
检查：本次封堵数 > alert_block_count_threshold（默认 50）
→ emit_block_threshold_exceeded()
```

### 7.3 通知事件清单

| 事件类型                                  | 触发场景         |
| ------------------------------------- | ------------ |
| `terminal.blocked`                    | 单个终端被封堵      |
| `terminal.unblocked`                  | 单个终端被解封      |
| `auto_block.triggered`                | 自动封堵执行       |
| `auto_unblock.triggered`              | 自动解封执行       |
| `compliance.alert`                    | 合规率低于阈值      |
| `policy.violation`                    | 终端不合规（非封堵触发） |
| `firewall.block` / `firewall.unblock` | 防火墙操作        |
| `datasource.sync_failed`              | IPGuard 同步失败 |
| `block.threshold_exceeded`            | 单次封堵数超阈值     |

***

## 八、关键配置项

| 配置键                                     | 默认值    | 类型        | 说明             |
| --------------------------------------- | ------ | --------- | -------------- |
| `scheduler_arp_collection_interval`     | 300    | int (秒)   | ARP 采集周期       |
| `scheduler_compliance_check_interval`   | 300    | int (秒)   | 合规检查周期         |
| `scheduler_ipguard_sync_interval`       | 600    | int (秒)   | IPGuard 同步周期   |
| `scheduler_auto_unblock_interval`       | 600    | int (秒)   | 自动解封周期         |
| `cache_whitelist_ttl`                   | 300    | int (秒)   | 白名单缓存 TTL      |
| `cache_ipguard_ttl`                     | 900    | int (秒)   | IPGuard 缓存 TTL |
| `alert_compliance_rate_threshold`       | 80     | float (%) | 合规率告警阈值        |
| `alert_block_count_threshold`           | 50     | int       | 单次封堵数量告警阈值     |
| `alert_non_compliant_confirm_threshold` | (配置默认) | int       | 不合规确认阈值        |
| `block_time`                            | 30d    | str       | 自动封堵默认过期时间     |

***

## 九、典型执行时序

### 9.1 正常周期（300 秒）

```
T+0s   scheduled_compliance_check 启动
T+0.1s  acquire_task_lock("compliance_check")
T+0.2s  查询所有 ARP 数据源
T+0.3s  遍历每个数据源：
          ├─ 查询 unknown 状态终端
          ├─ batch_check_compliance()
          ├─ 应用合规结果 _apply_compliance_result()
          ├─ db.commit()
          ├─ auto_block_non_compliant()  ← 自动封堵
          └─ retry block for 未成功封堵的终端
T+0.5s  计算全局合规率
T+0.6s  emit_compliance_alert()（如需告警）
T+0.7s  release_task_lock("compliance_check")
```

### 9.2 IPGuard 同步后的即时重算

```
T+0s    scheduled_ipguard_sync 启动
T+0.5s  sync_ipguard_data() → Redis 更新缓存
T+1.0s  recalculate_all_compliance()
          ├─ acquire_compliance_lock()
          ├─ 加载白名单 + IPGuard 数据
          ├─ IPGuard 为空 → 中止
          ├─ 分页遍历所有 Terminal
          ├─ 逐个计算合规状态（含确认阈值）
          ├─ 调用 _apply_compliance_result()
          ├─ 自动解封已合规的 blocked 终端
          └─ 记录日志，释放锁
T+2.0s  完成
```

### 9.3 自动解封周期（600 秒）

```
T+0s    scheduled_auto_unblock 启动
T+0.1s  acquire_task_lock("auto_unblock")
T+0.2s  auto_unblock_compliant()
          ├─ 查询所有 auto_unblocked=False 黑名单记录
          ├─ 按 (IP, MAC) 分组
          ├─ 每组：
          │   ├─ 检查合规性（白名单 + IPGuard）
          │   ├─ 不合规 → 跳过
          │   ├─ 合规 → 所有防火墙解封
          │   └─ 全成功 → 标记 auto_unblocked=True + 解封 Terminal
          └─ 发送事件 + 记录日志
T+0.5s  release_task_lock("auto_unblock")
```

***

## 十、风险点与注意事项

1. **IPGuard 数据不可用**：`recalculate_all_compliance()` 在 IPGuard 完全不可用时会中止，不会误判为 non\_compliant
2. **确认阈值保护**：避免因 IPGuard 临时波动导致的状态抖动
3. **分布式锁**：多实例部署时防止并发重算
4. **部分解封处理**：防火墙集群中部分解封成功部分失败时，终端保持 blocked 状态
5. **白名单缓存失效**：白名单变更后自动失效缓存，确保下次检查使用最新数据
6. **重试封堵**：处理防火墙 API 临时故障导致的封堵失败
7. **过期清理**：`cleanup_expired_blacklist` 每 3600 秒清理过期黑名单记录

