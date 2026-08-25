# 防火墙封锁状态不一致问题分析与修复计划

> 计划版本：v1.0 | 创建日期：2026-07-16
> 适用版本：v3.6.17 → v3.6.18

***

## 一、问题描述

### 现象

1. IP `10.8.12.206` 在 Web 终端列表中显示为"已被封锁"状态
2. 但实际防火墙（深信服 AF）上没有这条封锁记录
3. 后端日志存在 Terminal 相关的 Error（Terminal#723-724）

### 影响

* **数据不一致**：数据库状态与防火墙实际状态脱节

* **误报**：用户以为终端已被封锁，但实际上没有，存在安全风险

* **对账困扰**：防火墙对账服务（firewall\_reconciliation\_service）会发现"数据库有但防火墙没有"，并执行自动解封，导致状态反复横跳

***

## 二、根因分析

### 核心问题：异步队列 + 立即提交 = 不一致

**问题代码位置**：[compliance\_service.py:466-554](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L466-L554)

#### 执行流程（当前错误逻辑）

```
合规检查发现非合规终端
    │
    ▼
enqueue_operation() 入队（同步，几乎总是成功）
    │
    ├─ errors 列表为空 → all_success = True
    │
    ▼
立即更新 Terminal.status = "blocked"  ← 错误：假设一定会成功
立即创建 Blacklist 记录          ← 错误：假设一定会成功
await self.db.commit()
    │
    ▼
后台队列 _process_queue() 异步执行实际防火墙调用
    │
    ├─ 成功 → 一切正常
    └─ 失败 → 🔥 DB 已提交但防火墙没生效，状态不一致
```

#### 问题细节

1. **`enqueue_operation`** **是 fire-and-forget 模式**

   * 方法签名：`def enqueue_operation(...)`（同步方法，非 async）

   * 只是把操作放入 `asyncio.Queue`，然后启动后台任务处理

   * 返回值为 None，无法知道操作最终是否成功

2. **`all_success`** **判断错误**

   ```python
   all_success = len(errors) == 0  # 只检查入队是否出错，不检查实际执行结果
   ```

   * errors 列表只有在 `svc` 为 None 或入队抛出异常时才会增加

   * 而实际防火墙 API 调用在后台队列中执行，失败只会打日志，不会反馈给调用方

3. **Terminal 状态与防火墙状态无确认机制**

   * Terminal.status 代表"防火墙封锁状态"

   * 但设置为 blocked 时并没有确认防火墙实际已封锁

   * 这违反了 TerminalStatus 枚举的设计初衷："represents firewall block state only"

### 与 Terminal#723-724 Error 的关联

Terminal#723-724 很可能就是指 ID 为 723 和 724 的终端记录，它们的 status 被错误地设为了 blocked，但实际防火墙操作失败了。

后台队列中失败的操作会打 error 日志（`sangfor_service.py:696`），但不会更新数据库状态。

***

## 三、修复方案

### 方案选择

| 方案                    | 说明                      | 优点          | 缺点          |
| --------------------- | ----------------------- | ----------- | ----------- |
| **方案 A：同步等待防火墙结果**    | 改为同步调用防火墙 API，成功后再更新 DB | 一致性最强，逻辑简单  | 并发封锁时慢，可能超时 |
| **方案 B：两阶段提交 + 对账修正** | 先标记为"封锁中"，对账服务修正状态      | 不改变现有架构，性能好 | 状态有短暂不一致窗口  |
| **方案 C：异步回调 + 状态确认**  | 队列处理完后回调更新状态            | 一致性好，性能中等   | 改动较大，需要事件机制 |

**推荐方案：方案 A（同步等待）**

理由：

1. 合规检查本来就是后台定时任务，对延迟不敏感
2. 代码改动最小，逻辑最清晰
3. 现有的 `SangforService.block_ip` 已经是同步方法，直接调用即可
4. 避免引入"封锁中"等中间状态的复杂度

***

## 四、具体修改内容

### 4.1 compliance\_service.py - auto\_block\_non\_compliant

**修改位置**：`auto_block_non_compliant` 方法中封锁循环部分

**修改内容**：

1. 移除 `enqueue_operation` 异步队列调用
2. 改为直接调用 `svc.block_ip()` 同步方法（或 `_execute_block`）
3. 检查实际返回结果，只有成功时才更新 Terminal.status 和创建 Blacklist
4. 失败时记录错误但不更新状态

**伪代码**：

```python
# 旧代码（异步入队，立即假设成功）
svc.enqueue_operation(FirewallOperationType.BLOCK, entry.ip_address, ...)
all_success = len(errors) == 0  # 这是错的

# 新代码（同步调用，确认成功后再更新）
try:
    result = await svc.block_ip(ip_address=entry.ip_address, ...)
    if result.success:
        # 更新 Terminal 和 Blacklist
    else:
        errors.append(f"Failed to block {entry.ip_address}: {result.message}")
except Exception as e:
    errors.append(f"Error blocking {entry.ip_address}: {str(e)}")
```

### 4.2 compliance\_service.py - auto\_unblock\_compliant

同样的问题也存在于解封逻辑中。需要检查解封部分是否也使用了异步队列。

如果使用了，同样改为同步调用。

### 4.3 firewal\_reconciliation\_service.py - 对账优化

当前对账服务发现"DB有但防火墙没有"时，如果防火墙 API 失败（返回 0 条），会跳过 DB 更新以防止数据丢失。这个保护机制是好的。

但对于单个 IP 的不一致（不是全部丢失），对账服务会执行解封操作。这在当前 bug 的场景下会导致：

* 合规检查把终端设为 blocked（但实际没封锁成功）

* 对账服务发现不一致，把终端解封（设为 unblocked）

* 下次合规检查又设为 blocked

* 循环往复...

修复 auto\_block 后，这个问题自然会减少。但建议增强对账服务的日志，记录不一致原因，方便排查。

### 4.4 数据修复

对于已经存在的不一致数据（DB 显示 blocked 但防火墙没有）：

* 可以运行一次防火墙对账（firewall reconciliation）来自动修正

* 或者手动检查并修复

***

## 五、影响范围

| 模块           | 影响            | 风险           |
| ------------ | ------------- | ------------ |
| 合规自动封锁       | 改为同步调用，封锁速度变慢 | 低 - 本来就是后台任务 |
| 合规自动解封       | 同上            | 低            |
| 防火墙对账        | 无代码改动，减少误报    | 低            |
| Terminal 状态  | 准确性提升         | 正面影响         |
| Blacklist 记录 | 准确性提升         | 正面影响         |

***

## 六、验证步骤

1. **功能验证**：

   * 创建一个非合规终端，触发合规检查

   * 确认 Terminal.status = blocked 且防火墙上确实有该 IP

   * 断开防火墙连接，触发合规检查

   * 确认 Terminal.status 不会被设为 blocked（因为防火墙调用失败）

2. **数据一致性验证**：

   * 运行防火墙对账服务

   * 确认 missing\_in\_firewall 数量为 0 或很少

   * 确认没有反复封锁/解封的循环

3. **性能验证**：

   * 大批量封锁时的耗时是否可接受

   * 如果太慢，再考虑优化（如并发控制）

***

## 七、执行计划

### 阶段一：代码修复

1. 检查并修复 `auto_block_non_compliant` - 改为同步调用
2. 检查并修复 `auto_unblock_compliant` - 同样改为同步调用
3. 确保错误处理完整，失败不更新 DB

### 阶段二：测试验证

1. 本地验证封锁/解封逻辑
2. 验证错误场景（防火墙不可达）

### 阶段三：数据修复

1. 运行一次完整的防火墙对账
2. 确认不一致数据被修正

### 阶段四：发布

1. 版本号升级到 v3.6.18
2. 更新 changelog 和 release-notes

