# 综合审计验证清单

## 核心业务逻辑验证

### CRITICAL 修复验证
- [ ] C-1: `recalculate_all_compliance()` 创建的 Blacklist 记录包含 `mac_address_normalized` 字段
- [ ] C-2: `auto_unblock_compliant()` 多防火墙解封部分失败时 Terminal 保持 "blocked" 状态
- [ ] C-3: `cleanup_expired_blacklist()` 跳过 `auto_unblocked=True` 的记录
- [ ] C-3: `cleanup_expired_blacklist()` 解封前检查同一 IP 是否有活跃 Blacklist 记录

### HIGH 修复验证
- [ ] H-1/H-3: `recalculate_all_compliance()` 自动解封时处理手动封堵的 Blacklist 记录
- [ ] H-2: 手动解封后触发合规重算，compliance_status 不再保持 "unknown"
- [ ] H-4: `add_to_blacklist()` 设置 Terminal 的 `firewall_tag`
- [ ] H-5: 白名单变更后合规重算失败有重试或恢复机制

### MEDIUM 修复验证
- [ ] M-1: 三种解封路径对 Blacklist 记录处理方式一致（标记保留而非删除）
- [ ] M-2: 无防火墙标签时解封失败不标记为已解封
- [ ] M-5: 过期清理仅当 Terminal 当前为 "blocked" 时才重置状态
- [ ] M-6: 手动封堵不强制设置 compliance_status 为 "non_compliant"

## 代码准确性验证
- [ ] config.py VERSION 值为 "3.2.0"
- [ ] arp_collector_service.py 错误消息引用 "netmiko"
- [ ] .env.example VERSION 值为 3.2.0

## 文档准确性验证
- [ ] api.md 终端详情响应示例使用 "unblocked" 而非 "unfrozen"
- [ ] api.md 速率限制默认值为 120/10
- [ ] backend.md `unblock_ip()` 签名包含 `mac_address` 参数
- [ ] architecture.md 操作按钮矩阵 unknown+unblocked 状态封堵按钮标记为不可用

## 文档完整性验证
- [ ] api.md 包含 `POST /data-sources/{id}/disable-preview` 端点文档
- [ ] api.md unblock 端点包含 `mac_address` 查询参数
- [ ] RBAC.md 包含 delete-preview 和 disable-preview 端点权限映射
- [ ] datasource-lifecycle.md API 表包含 delete-preview、safe-delete、disable-preview
- [ ] production-readiness-assessment.md 文档清单包含 logging-guide.md 和 git-workflow-guide.md
- [ ] changelog.md 包含版本头
- [ ] release-notes.md TBD 条目已根据实现状态更新

## 文档一致性验证
- [ ] datasource-lifecycle.md DELETE 权限码为 datasource:write（非 datasource:delete）
- [ ] datasource-lifecycle.md DELETE 权限码为 baseline:write（非 baseline:delete）
- [ ] RBAC.md 无 `POST /blacklist/` 添加端点或已标注废弃
- [ ] RBAC.md `blacklist:write` 描述不含"添加"
- [ ] api.md `POST /blacklist/` 已标注废弃
- [ ] implementation.md 无"添加黑名单条目"描述
- [ ] implementation.md 无 `POST /api/v1/blacklist/` 集成点
- [ ] branding.md 不推荐 SVG 格式，含 XSS 风险说明
- [ ] 所有文档版本号为 v3.2.0-r11
- [ ] RBAC.md Blacklist 页面功能描述不含"封禁终端"

## 构建验证
- [ ] 前端构建成功
- [ ] 后端启动成功
- [ ] 合规重算业务链测试通过
- [ ] 封堵/解封业务链测试通过
- [ ] 黑名单清理业务链测试通过
