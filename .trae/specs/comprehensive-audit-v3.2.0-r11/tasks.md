# Tasks

## 第一阶段：核心业务逻辑修复

- [x] Task 1: 修复 C-1 — `recalculate_all_compliance()` Blacklist 缺少 `mac_address_normalized`
  - [x] 1.1: 在 `compliance_service.py` 自动封堵分支的 Blacklist 构造中添加 `mac_address_normalized` 字段
  - [x] 1.2: 验证字段值与 `auto_block_non_compliant()` 一致

- [x] Task 2: 修复 C-2 — `auto_unblock_compliant()` 多防火墙解封原子性
  - [x] 2.1: 重构 `auto_unblock_compliant()`，先收集同一 IP+MAC 的所有 Blacklist 记录
  - [x] 2.2: 统一判断所有防火墙解封结果后再更新 Terminal 状态
  - [x] 2.3: 仅标记成功解封的 Blacklist 记录为 `auto_unblocked=True`

- [x] Task 3: 修复 C-3 — `cleanup_expired_blacklist()` 跳过已解封记录
  - [x] 3.1: 在查询条件中添加 `Blacklist.auto_unblocked == False` 过滤
  - [x] 3.2: 在解封前检查是否存在同一 IP 的其他活跃 Blacklist 记录

- [x] Task 4: 修复 H-1 + H-3 — 统一解封行为
  - [x] 4.1: `recalculate_all_compliance()` 自动解封时同时处理手动封堵的 Blacklist 记录
  - [x] 4.2: `auto_unblock_compliant()` 增加对手动封堵终端的处理

- [x] Task 5: 修复 H-2 — 手动解封后触发合规重算
  - [x] 5.1: 在 `unblock_ip()` 中调用 `recalculate_all_compliance()`
  - [x] 5.2: 事务管理正确（flush/commit）

- [x] Task 6: 修复 H-4 — `add_to_blacklist()` 设置 `firewall_tag`
  - [x] 6.1: 添加 `record.firewall_tag = firewall_tag`

- [x] Task 7: 修复 M-1 — 统一三种解封路径的 Blacklist 处理
  - [x] 7.1: 手动解封改为标记 `auto_unblocked=True` 而非删除
  - [x] 7.2: 统一三种路径的 `compliance_status` 设置逻辑

- [x] Task 8: 修复 M-2 — 无防火墙标签时解封失败应阻塞
  - [x] 8.1: 已在 C-2 重构中处理

- [x] Task 9: 修复 M-5 — 过期清理不无条件重置合规状态
  - [x] 9.1: 已在 C-3 修复中处理（仅当 Terminal 当前为 "blocked" 时才重置）

- [x] Task 10: 修复 M-6 — 手动封堵不强制设置 compliance_status
  - [x] 10.1: `block_ip()` 和 `add_to_blacklist()` 中不再强制设置 `compliance_status = "non_compliant"`
  - [x] 10.2: 保留合规状态不变，仅更新 `status = "blocked"` 和 `firewall_tag`

## 第二阶段：代码准确性修复

- [x] Task 11: 修复代码中的过时值
  - [x] 11.1: `config.py` VERSION 从 "2.0.0" 更新为 "3.2.0"
  - [x] 11.2: `arp_collector_service.py` 错误消息从 "paramiko" 改为 "netmiko"
  - [x] 11.3: `.env.example` VERSION 从 2.0.0 更新为 3.2.0

## 第三阶段：文档一致性修复

- [x] Task 12: 修复 api.md（5 处）
  - [x] 12.1: `"status": "unfrozen"` 改为 `"unblocked"`
  - [x] 12.2: 速率限制默认值从 60/5 更新为 120/10
  - [x] 12.3: unblock 端点补充 `mac_address` 查询参数文档
  - [x] 12.4: `POST /blacklist/` 标注为已废弃
  - [x] 12.5: 补充 `POST /data-sources/{id}/disable-preview` 端点文档

- [x] Task 13: 修复 RBAC.md（4 处）
  - [x] 13.1: `blacklist:write` 描述从"添加/解封"改为"解封"
  - [x] 13.2: `POST /blacklist/` 端点标注为已废弃
  - [x] 13.3: 补充 delete-preview 和 disable-preview 端点权限映射
  - [x] 13.4: Blacklist 页面功能描述移除"封禁终端"

- [x] Task 14: 修复 datasource-lifecycle.md（3 处）
  - [x] 14.1: API 表补充 7 个新端点
  - [x] 14.2: 权限码从 `datasource:delete` 改为 `datasource:write`
  - [x] 14.3: 权限码从 `baseline:delete` 改为 `baseline:write`

- [x] Task 15: 修复 architecture.md（1 处）
  - [x] 15.1: 操作按钮矩阵 unknown+unblocked 状态封堵按钮标记为不可用

- [x] Task 16: 修复 backend.md（2 处）
  - [x] 16.1: `unblock_ip()` 签名补充 `mac_address` 参数
  - [x] 16.2: 速率限制默认值从 60/5 更新为 120/10

- [x] Task 17: 修复 branding.md（2 处）
  - [x] 17.1: SVG 从推荐格式移除，添加 XSS 风险说明
  - [x] 17.2: 版本号更新为 v3.2.0-r11

- [x] Task 18: 修复 frontend/docs/implementation.md（2 处）
  - [x] 18.1: 移除"添加黑名单条目"描述
  - [x] 18.2: `POST /api/v1/blacklist/` 标注为已废弃

- [x] Task 19: 修复 production-readiness-assessment.md（3 处）
  - [x] 19.1: 文档清单补充 logging-guide.md 和 git-workflow-guide.md
  - [x] 19.2: 版本号统一声明与实际表格对齐
  - [x] 19.3: `.env VERSION` 值从 2.0.0 更新为 3.2.0

- [x] Task 20: 修复版本号不同步
  - [x] 20.1: deployment.md 版本号更新为 v3.2.0-r11
  - [x] 20.2: manage-sh-reference.md 版本号更新为 v3.2.0-r11
  - [x] 20.3: logging-guide.md 版本号更新为 v3.2.0-r11
  - [x] 20.4: git-workflow-guide.md 版本号更新为 v3.2.0-r11
  - [x] 20.5: changelog.md 添加版本头
  - [x] 20.6: release-notes.md 添加 v3.2.0-r11 变更记录

## 第四阶段：构建验证与提交

- [x] Task 21: 构建验证
  - [x] 21.1: 前端构建成功
  - [x] 21.2: 后端启动成功
  - [x] 21.3: 业务链测试通过

- [x] Task 22: 提交代码和文档
  - [x] 22.1: 代码修复提交 (128f378)
  - [x] 22.2: 文档修复提交 (e67bab5)
