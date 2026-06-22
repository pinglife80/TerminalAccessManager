# TerminalAccessManager v3.2.0-r11 综合审计与修复规格

## Why

项目经过多轮迭代后，核心业务逻辑存在 3 个 CRITICAL 级缺陷（Blacklist 记录字段缺失、多防火墙解封状态不一致、过期清理错误解封），6 个 HIGH 级缺陷（手动封堵解封行为不一致、合规重算失败无重试等），以及 32 处文档与代码不一致问题。这些问题可能导致数据不一致、安全策略被绕过、以及运维人员对系统行为的错误理解。

## What Changes

### A. 核心业务逻辑修复（3 CRITICAL + 6 HIGH + 10 MEDIUM）

- **C-1**：`recalculate_all_compliance()` 自动封堵创建 Blacklist 记录时缺少 `mac_address_normalized` 字段
- **C-2**：`auto_unblock_compliant()` 多防火墙场景下部分解封失败时 Terminal 状态与实际不一致
- **C-3**：`cleanup_expired_blacklist()` 处理已解封旧记录时可能错误删除防火墙上新的封堵条目
- **H-1**：手动封堵的终端在定时自动解封和合规重算解封中行为不同
- **H-2**：手动解封后不触发合规重算，终端保持 "unknown" 状态
- **H-3**：合规重算自动解封不处理手动封堵的 Blacklist 记录
- **H-4**：`add_to_blacklist()` 不设置 Terminal 的 `firewall_tag`
- **H-5**：白名单变更后合规重算失败无重试机制
- **H-6**：`scheduled_compliance_check` 仅检查 "unknown" 终端，不重新检查已有合规状态
- **M-1~M-10**：三种解封路径行为不一致、无防火墙标签时解封失败不阻塞、数据源禁用后合规重置但不解封、过期清理不区分已解封记录、手动封堵强制设置 compliance_status、自动封堵与自动解封路由来源不同、孤儿状态、合规重算失败无重试

### B. 文档一致性修复（32 项）

- 准确性修复 8 项：过时状态值、错误速率限制值、错误函数签名、操作矩阵与代码不符
- 完整性补充 7 项：disable-preview 端点未记录、unblock mac_address 参数缺失、13 个 TBD 未更新
- 一致性修复 10 项：权限码不匹配、已移除功能仍被记录、SVG 上传矛盾、版本号不同步
- 已记录未实现 2 项：POST /blacklist/ 手动添加、unknown 状态封堵按钮
- 已实现未记录 5 项：disable-preview 端点、mac_address 解封参数、3 个定时任务触发逻辑

### C. 代码准确性修复（3 项）

- `config.py` VERSION 从 "2.0.0" 更新为 "3.2.0"
- `arp_collector_service.py` 错误消息从 "paramiko" 改为 "netmiko"
- `.env.example` VERSION 从 2.0.0 更新为 3.2.0

## Impact

- 受影响代码：`compliance_service.py`、`terminal_service.py`、`data_source_service.py`、`config.py`、`arp_collector_service.py`
- 受影响文档：16 个文档文件
- 受影响范围：合规生命周期闭环、封堵/解封一致性、API 文档准确性、RBAC 权限体系
- **无 BREAKING 变更**：所有修复均为内部逻辑一致性和文档层面，不改变外部 API 接口

## ADDED Requirements

### Requirement: Blacklist 记录完整性

系统 SHALL 在所有创建 Blacklist 记录的代码路径中确保 `mac_address_normalized` 字段被正确设置，包括 `recalculate_all_compliance()` 的自动封堵分支。

#### Scenario: 合规重算自动封堵创建 Blacklist 记录
- **WHEN** `recalculate_all_compliance()` 将终端标记为 non_compliant 并自动封堵
- **THEN** 创建的 Blacklist 记录必须包含 `mac_address_normalized` 字段，值与 `auto_block_non_compliant()` 创建的记录一致

### Requirement: 多防火墙解封原子性

系统 SHALL 在 `auto_unblock_compliant()` 中实现"全部防火墙解封成功才更新 Terminal 状态"的逻辑，与 `recalculate_all_compliance()` 的 `all_unblock_success` 模式一致。

#### Scenario: 多防火墙部分解封失败
- **WHEN** 终端在多个防火墙上被封堵，`auto_unblock_compliant()` 尝试解封时部分防火墙失败
- **THEN** Terminal 状态保持 "blocked"，仅标记成功解封的 Blacklist 记录为 `auto_unblocked=True`

### Requirement: 过期清理安全防护

系统 SHALL 在 `cleanup_expired_blacklist()` 中跳过 `auto_unblocked=True` 的记录，防止错误删除防火墙上新的封堵条目。

#### Scenario: 已解封旧记录到期清理
- **WHEN** 已通过 `auto_unblock_compliant()` 标记为 `auto_unblocked=True` 的 Blacklist 记录到期
- **THEN** 清理逻辑跳过该记录，不尝试在防火墙上解封

### Requirement: 手动解封后合规重算

系统 SHALL 在手动解封后触发合规重算，使终端合规状态从 "unknown" 立即更新为实际合规状态。

#### Scenario: 手动解封后合规状态更新
- **WHEN** 管理员手动解封一个终端
- **THEN** 系统立即触发合规重算，终端的 compliance_status 从 "unknown" 更新为 compliant/non_compliant/bypass

### Requirement: disable-preview 端点文档化

系统 SHALL 在 api.md、RBAC.md、datasource-lifecycle.md 中完整记录 `POST /data-sources/{id}/disable-preview` 端点。

#### Scenario: 开发者查阅禁用预览端点
- **WHEN** 开发者查阅 api.md 数据源章节
- **THEN** 能找到 disable-preview 端点的完整 API 文档

### Requirement: unblock 端点 mac_address 参数文档化

系统 SHALL 在 api.md 中记录 unblock 端点的 `mac_address` 可选查询参数。

#### Scenario: 开发者查阅解封端点
- **WHEN** 开发者查阅 api.md 终端解封章节
- **THEN** 能看到 `mac_address` 查询参数的说明

## MODIFIED Requirements

### Requirement: 手动封堵终端的合规重算解封行为

`recalculate_all_compliance()` 自动解封时 SHALL 同时处理手动封堵和自动封堵的 Blacklist 记录，将匹配的记录标记为 `auto_unblocked=True`。

### Requirement: 手动封堵时设置 firewall_tag

`add_to_blacklist()` 更新 Terminal 状态时 SHALL 同时设置 `firewall_tag` 字段，与 `block_ip()` 行为一致。

### Requirement: 三种解封路径行为统一

手动解封、定时自动解封、合规重算自动解封 SHALL 对 Blacklist 记录采用一致的处理方式（标记保留而非删除），对 compliance_status 采用一致的设置逻辑。

### Requirement: 速率限制默认值文档

api.md、backend.md 中的速率限制默认值 SHALL 从 60/5 更新为 120/10。

### Requirement: 终端状态枚举值

api.md 终端详情响应示例 SHALL 使用 `"unblocked"` 而非 `"unfrozen"`。

### Requirement: 操作按钮矩阵

architecture.md 操作按钮矩阵 SHALL 将 `unknown + unblocked` 状态的封堵按钮标记为不可用。

### Requirement: 权限码一致性

datasource-lifecycle.md 中 DELETE 操作的权限码 SHALL 从 `datasource:delete`/`baseline:delete` 修改为 `datasource:write`/`baseline:write`。

### Requirement: 黑名单手动添加功能移除

api.md、RBAC.md、implementation.md 中关于 `POST /blacklist/` 手动添加功能的文档 SHALL 标注为已废弃。

### Requirement: SVG 上传禁止说明

branding.md SHALL 将 SVG 从推荐格式中移除，添加 XSS 风险说明。

### Requirement: 文档版本号统一

所有文档 SHALL 统一版本号为 v3.2.0-r11。

### Requirement: release-notes.md TBD 条目更新

release-notes.md 中 13 个 TBD 条目 SHALL 根据实际代码实现状态更新。

## REMOVED Requirements

无移除需求。
