# 三个问题修复计划

## 问题1：数据导出功能不支持全量导出

### 根因分析
`TerminalQuery` 类（`backend/app/schemas/terminal.py`）的 `limit` 字段限制最大为200，导出端点使用该类并传入 `limit=50000` 导致验证失败。

### 修复方案
导出端点不使用 `TerminalQuery`，直接构建查询条件，不限制返回数量。

### 修改文件
- `backend/app/api/v1/endpoints/terminals.py` — 修改 `/export` 端点，移除 `TerminalQuery` 依赖
- `backend/app/api/v1/endpoints/whitelist.py` — 修改 `/export` 端点
- `backend/app/api/v1/endpoints/blacklist.py` — 修改 `/export` 端点

---

## 问题2：创建通知渠道时报500内部错误

### 根因分析
`backend/app/api/v1/endpoints/notifications.py` 第85行：
```python
{"name": channel.name, "type": channel.channel_type, "enabled": channel.enabled},
```
`NotificationChannel` 数据库模型的字段名是 `type`，不是 `channel_type`，导致 `AttributeError`。

### 修复方案
将 `channel.channel_type` 改为 `channel.type`。

### 修改文件
- `backend/app/api/v1/endpoints/notifications.py` — 第85行

---

## 问题3：bypass终端缺少备注信息

### 根因分析
`backend/app/services/compliance_service.py` 第1094行：
```python
await emit_terminal_compliant(
    ip_address=ip_addr,
    mac_address=mac_addr,
    source_tag=terminal.source_tag  # 此参数不存在
)
```
`emit_terminal_compliant()` 函数只接受 `ip_address` 和 `mac_address` 两个参数，传入 `source_tag` 导致 `TypeError`，中断合规性重算流程。

### 修复方案
移除 `source_tag` 参数。

### 修改文件
- `backend/app/services/compliance_service.py` — 第1094-1099行

---

## 实施步骤

1. 修复问题2（最紧急，影响功能使用）
2. 修复问题3（影响数据同步）
3. 修复问题1（数据导出）
4. 构建验证

---

## 风险评估

- **问题2**: 低风险，仅修改一个字段名
- **问题3**: 低风险，仅移除多余参数
- **问题1**: 中风险，需要确保导出性能，建议限制最大导出数量为10000条

---

## 验证方法

1. 创建通知渠道 → 确认返回201状态码，无500错误
2. 添加/删除白名单 → 确认终端管理中bypass终端的备注信息正确更新
3. 测试全量导出和筛选导出 → 确认返回完整CSV数据
