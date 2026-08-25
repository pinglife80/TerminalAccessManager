# 合规判断逻辑一致性优化方案

## 一、问题评估

### 1.1 现状分析

当前系统存在两条合规判断路径，行为不一致：

| 路径 | 方法 | 触发时机 |
|------|------|----------|
| 路径A | `batch_check_compliance()` | ARP采集、定时检查（仅处理 `unknown` 终端） |
| 路径B | `recalculate_all_compliance()` | 白名单变更、IPGuard同步（全量重算） |

### 1.2 功能差距矩阵

| 功能 | 路径A（batch_check） | 路径B（recalculate_all） | 影响 |
|------|---------------------|------------------------|------|
| 更新 compliance_status | ✅ | ✅ | - |
| 更新 wl_match_type | ✅ | ✅ | - |
| 更新 comments（白名单备注） | ❌ | ✅ | ARP采集的白名单终端无备注 |
| 触发事件通知 | ❌ | ✅ | ARP采集不触发告警/日志 |
| 自动解封（blocked → compliant/bypass） | ❌ | ✅ | 白名单新增后无法自动解封 |
| 自动封堵（non_compliant） | ✅（异步） | ✅（同步） | ARP封堵失败无重试机制 |

### 1.3 代码位置

- **路径A调用点**：
  - [arp_collector_service.py:353](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L353) — ARP采集后
  - [main.py:209](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L209) — 定时合规检查

- **路径B逻辑**：
  - [compliance_service.py:1031-1226](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1031-L1226) — `recalculate_all_compliance` 循环体

---

## 二、解决方案

### 2.1 核心思路

将 `recalculate_all_compliance` 中单个终端的更新逻辑抽取为共享方法 `_apply_compliance_result`，确保所有路径行为一致：

```
┌──────────────────────────────────────────────────────────────┐
│                   _apply_compliance_result()                 │
│  ─────────────────────────────────────────────────────────  │
│  参数: terminal, new_compliance, new_wl_match_type,         │
│        wl_comments, ip_addr, mac_addr                       │
│                                                             │
│  功能:                                                       │
│    1. 更新 compliance_status                                 │
│    2. 更新 wl_match_type                                    │
│    3. 更新 comments（白名单备注处理）                         │
│    4. 状态变更时触发事件通知                                  │
│    5. 自动封堵/解封逻辑                                      │
└──────────────────────────────────────────────────────────────┘
           ▲                          ▲
           │                          │
┌──────────┴──────────┐    ┌──────────┴──────────┐
│ recalculate_all_    │    │ batch_check_        │
│   compliance()      │    │   compliance()      │
│ (全量重算)          │    │ (增量检查)          │
└─────────────────────┘    └─────────────────────┘
```

### 2.2 实施步骤

#### 步骤1：提取共享方法 `_apply_compliance_result`

**文件**：`backend/app/services/compliance_service.py`

**新增方法签名**：
```python
async def _apply_compliance_result(
    self,
    terminal: Terminal,
    new_compliance: str,
    new_wl_match_type: str | None,
    wl_comments: str | None,
    ip_addr: str,
    mac_addr: str,
) -> dict:
    """
    Apply compliance result to a single terminal.
    
    Returns: {"status_changed": bool, "new_compliance": str}
    """
```

**提取内容**：从 `recalculate_all_compliance` 第1052-1226行提取以下逻辑：
- comments 更新（白名单备注处理）
- compliance_status 和 wl_match_type 更新
- 状态变更事件触发
- 自动解封逻辑
- 自动封堵逻辑

#### 步骤2：修改 `recalculate_all_compliance` 使用共享方法

**文件**：`backend/app/services/compliance_service.py`

**修改内容**：将原循环体（第1052-1226行）替换为调用 `_apply_compliance_result`，保留计数逻辑。

#### 步骤3：修改 ARP 采集服务使用共享方法

**文件**：`backend/app/services/arp_collector_service.py`

**修改内容**：将第368-377行的手动状态更新替换为调用 `compliance_service._apply_compliance_result`。

#### 步骤4：修改定时任务使用共享方法

**文件**：`backend/app/main.py`

**修改内容**：将第221-230行的手动状态更新替换为调用 `compliance_service._apply_compliance_result`。

---

## 三、风险评估

| 风险项 | 风险等级 | 应对措施 |
|--------|----------|----------|
| 共享方法接口设计不当 | 中 | 确保方法签名完整，包含所有必要参数 |
| 事务边界问题 | 低 | 保持现有事务模式，调用方负责 commit |
| 性能影响 | 低 | 仅对 `unknown` 终端调用，不增加额外数据库查询 |
| 事件重复触发 | 低 | 在方法内部判断 `status_changed` 后才触发事件 |

---

## 四、验证方案

### 4.1 功能验证

| 验证场景 | 操作步骤 | 预期结果 |
|----------|----------|----------|
| ARP采集白名单终端 | 添加白名单网段 → 触发ARP采集 | 终端 `compliance_status=bypass`，`comments` 包含 "Whitelist: xxx" |
| ARP采集不合规终端 | 确保IP不在白名单/IPGuard → 触发ARP采集 | 终端 `compliance_status=non_compliant`，触发自动封堵 |
| ARP采集后自动解封 | 终端被封堵 → 添加到白名单 → 触发ARP采集 | 终端自动解封，`status=unblocked` |
| 定时检查事件触发 | 手动设置终端为unknown → 等待定时任务 | 终端状态更新后触发对应事件 |

### 4.2 数据一致性验证

| 验证项 | SQL查询 | 预期结果 |
|--------|---------|----------|
| bypass终端备注完整性 | `SELECT COUNT(*) FROM terminals WHERE compliance_status='bypass' AND comments IS NULL` | 0 |
| bypass终端wl_match_type完整性 | `SELECT COUNT(*) FROM terminals WHERE compliance_status='bypass' AND wl_match_type IS NULL` | 0 |

### 4.3 构建验证

```bash
./manage.sh -y update
./manage.sh health
```

---

## 五、实施清单

- [ ] 步骤1：在 `compliance_service.py` 新增 `_apply_compliance_result` 方法
- [ ] 步骤2：修改 `recalculate_all_compliance` 使用共享方法
- [ ] 步骤3：修改 `arp_collector_service.py` 使用共享方法
- [ ] 步骤4：修改 `main.py` 定时任务使用共享方法
- [ ] 步骤5：构建验证（`./manage.sh update`）
- [ ] 步骤6：健康检查（`./manage.sh health`）
- [ ] 步骤7：功能验证（ARP采集、定时任务、白名单变更）
- [ ] 步骤8：数据一致性验证（SQL查询）

---

## 六、文档同步

| 文档 | 同步内容 |
|------|----------|
| `docs/backend.md` | 更新合规检查流程说明，明确共享方法的职责 |
| `docs/datasource-lifecycle.md` | 更新ARP采集后的合规处理流程 |
