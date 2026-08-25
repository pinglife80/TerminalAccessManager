# 备份管理优化计划

> 文档版本：v2.0 更新日期：2026-07-09

## 一、当前系统备份功能全面评估

### 1.1 已实现功能矩阵

| 备份维度 | 后端实现 | 前端实现 | 状态 |
|---------|---------|---------|------|
| 数据库全量备份 | ✅ pg_dump | ✅ | 完成 |
| 系统配置备份 | ✅ system_config/notification/auth/datasource | ✅ | 完成 |
| 品牌资源备份 | ✅ branding 文件 | ✅ | 完成 |
| 白名单备份 | ⚠️ 字段不完整 | ✅ | 需修复 |
| 日志备份 | ✅ | ✅ | 完成 |
| 配置文件备份 | ✅ docker-compose.yml, manage.sh | ✅ | 完成 |
| 备份类型选择 | ✅ full/database/config/whitelist/logs | ✅ | 完成 |
| 远程存储(SFTP/FTP) | ✅ | ✅ | 完成 |
| 备份列表管理 | ✅ 本地+远程 | ✅ | 完成 |
| 备份下载 | ✅ | ✅ | 完成 |
| 备份恢复 | ✅ | ⚠️ 白名单缺少内容预览 | 需完善 |
| 备份删除 | ✅ 本地+远程 | ✅ | 完成 |
| 备份内容预览 | ✅ | ✅ | 完成 |

### 1.2 关键问题发现

#### 问题1：白名单备份字段与实际模型不匹配（严重）

**当前代码问题：**
- [whitelist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/whitelist.py) 模型字段：`id`, `mac_address`, `mac_address_normalized`, `ip_pattern`, `pattern_type`, `comments`, `added_by`, `created_at`
- [backup_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L606-L642) 备份字段：`id`, `ip_address`, `mac_address`, `hostname`, `description`, `created_at`, `updated_at`

**影响：** 备份恢复后，`ip_pattern`、`pattern_type`、`comments`、`added_by`、`mac_address_normalized` 等关键字段丢失，导致白名单规则完全失效。

#### 问题2：白名单恢复后未触发合规重算（严重）

**当前状态：** 恢复白名单后，终端管理中的合规状态和备注不会自动更新，需要手动触发合规检查。

**影响：** 恢复操作不完整，业务链断裂。

#### 问题3：英/日翻译缺失（中等）

**当前状态：** 
- [en.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/en.ts) 缺少备份类型选择器、白名单备份模块、备份内容预览、恢复确认对话框等翻译项
- [ja.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/ja.ts) 同样缺少上述翻译项

#### 问题4：备份文件名不包含类型标识（中等）

**当前状态：** 所有备份文件名格式为 `backup_YYYYMMDD_HHMMSS.zip`，无法区分备份类型。

**影响：** `get_whitelist_backups()` 通过 `'whitelist' in filename.lower()` 筛选，永远返回空列表。

#### 问题5：白名单恢复缺少内容预览（体验问题）

**当前状态：** 普通备份恢复有完整的模态框展示备份内容，白名单恢复直接用浏览器原生 confirm。

## 二、优化方案

### 2.1 方案架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      备份管理优化架构                          │
├─────────────────────────────────────────────────────────────┤
│  前端层                                                       │
│  ├── 备份类型选择器（full/database/config/whitelist/logs）    │
│  ├── 备份列表（全量/白名单独立展示）                            │
│  ├── 备份内容预览模态框（统一样式）                             │
│  ├── 恢复确认对话框（统一样式）                                 │
│  └── i18n 中/英/日完整覆盖                                     │
├─────────────────────────────────────────────────────────────┤
│  API 层                                                       │
│  ├── POST /backup/run?backup_type={type}                     │
│  ├── POST /backup/whitelist                                  │
│  ├── GET /backup/whitelist/list                              │
│  ├── POST /backup/whitelist/restore/{filename}              │
│  ├── GET /backup/{filename}/contents                         │
│  └── DELETE /backup/{filename}                               │
├─────────────────────────────────────────────────────────────┤
│  服务层                                                       │
│  ├── backup_service.py                                       │
│  │   ├── run_backup() - 文件名包含类型标识                      │
│  │   ├── backup_whitelist() - 完整字段备份                    │
│  │   └── restore_whitelist() - 完整字段恢复+触发合规重算         │
│  └── compliance_service.py                                   │
│      └── recalculate_all_compliance() - 恢复后自动调用          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 详细实施步骤

#### 阶段一：修复白名单备份字段（高优先级）

**修改文件：** `backend/app/services/backup_service.py`

**修复内容：**
- 将 `backup_whitelist()` 中的字段映射修正为与 Whitelist 模型一致
- 将 `restore_whitelist()` 中的字段映射同步修正
- 备份文件名添加 `_whitelist` 后缀标识

```python
# 修复后（正确字段）
whitelist_data = [{
    "id": row.id,
    "mac_address": row.mac_address,
    "mac_address_normalized": row.mac_address_normalized,
    "ip_pattern": row.ip_pattern,
    "pattern_type": row.pattern_type,
    "comments": row.comments,
    "added_by": row.added_by,
    "created_at": row.created_at.isoformat() if row.created_at else None,
}]
```

#### 阶段二：白名单恢复后触发合规重算（高优先级）

**修改文件：** `backend/app/services/backup_service.py`

**修复内容：**
- 在 `restore_whitelist()` 成功后，调用 `recalculate_all_compliance()`
- 确保终端管理中的备注和合规状态同步更新

#### 阶段三：修复备份文件名命名（中优先级）

**修改文件：** `backend/app/services/backup_service.py`

**修复内容：**
- 修改 `_generate_backup_id()` 或 `run_backup()`，根据备份类型生成包含类型标识的文件名
- 格式：`backup_{type}_{YYYYMMDD_HHMMSS}.zip`

#### 阶段四：完善中文翻译（中优先级）

**修改文件：** `frontend/src/i18n/locales/zh.ts`

**修复内容：**
- 添加 `backup.backupType` 翻译（全量/数据库/配置/白名单/日志）
- 添加 `backup.whitelistBackup` 翻译（白名单备份模块）
- 添加 `backup.backupContents` 翻译（备份内容预览）
- 添加 `backup.restoreConfirm` 翻译（恢复确认对话框）

#### 阶段五：完善英文翻译（中优先级）

**修改文件：** `frontend/src/i18n/locales/en.ts`

**修复内容：**
- 添加 `backup.backupType` 翻译
- 添加 `backup.whitelistBackup` 翻译
- 添加 `backup.backupContents` 翻译
- 添加 `backup.restoreConfirm` 翻译

#### 阶段六：完善日语翻译（中优先级）

**修改文件：** `frontend/src/i18n/locales/ja.ts`

**修复内容：**
- 添加 `backup.backupType` 翻译
- 添加 `backup.whitelistBackup` 翻译
- 添加 `backup.backupContents` 翻译
- 添加 `backup.restoreConfirm` 翻译

#### 阶段七：统一恢复确认对话框（低优先级）

**修改文件：** `frontend/src/pages/Backup.tsx`

**修复内容：**
- 白名单恢复使用统一的模态框预览备份内容

## 三、风险评估

### 3.1 影响范围分析

| 变更项 | 影响模块 | 风险等级 | 说明 |
|-------|---------|---------|------|
| 白名单备份字段修复 | 备份服务、白名单管理 | 🔴 高 | 修复后恢复操作会覆盖现有数据，需确保备份文件格式兼容 |
| 合规重算触发 | 备份服务、合规服务 | 🟡 中 | 恢复后会触发全量合规检查，可能影响系统性能 |
| 文件名格式变更 | 备份服务、前端列表 | 🟡 中 | 历史备份文件筛选逻辑需要兼容 |
| i18n 更新（中/英/日） | 前端展示 | 🟢 低 | 仅影响界面文字展示 |

### 3.2 风险缓解措施

1. **数据兼容性风险**：
   - 在 `restore_whitelist()` 中添加字段兼容性处理，支持新旧格式
   - 对缺失字段使用默认值

2. **性能风险（合规重算）**：
   - 使用后台异步任务执行合规重算
   - 添加执行状态反馈

3. **文件名兼容风险**：
   - 保留旧格式的筛选逻辑（无类型标识的视为全量备份）
   - 新格式添加类型标识

## 四、功能验证方案

### 4.1 验证环境

- **环境类型**：Docker Compose
- **管理工具**：`./manage.sh`
- **验证步骤**：
  1. `./manage.sh update` - 重建服务
  2. `./manage.sh logs backend` - 检查启动日志
  3. 前端访问备份管理页面

### 4.2 验证用例

#### 用例1：白名单备份与恢复完整性

**步骤：**
1. 添加多条白名单（包含不同 pattern_type：single_ip、cidr、mac_only）
2. 创建白名单备份
3. 删除所有白名单
4. 从备份恢复
5. 验证恢复后的白名单数据完整性

**预期结果：**
- 所有字段（ip_pattern、pattern_type、comments、added_by）正确恢复
- 终端管理中匹配的终端备注正确更新
- 合规状态正确更新为 bypass

#### 用例2：备份类型筛选

**步骤：**
1. 创建全量备份
2. 创建白名单备份
3. 创建配置备份
4. 查看备份列表

**预期结果：**
- 各类型备份列表正确显示对应类型的备份文件

#### 用例3：i18n 覆盖（中/英/日）

**步骤：**
1. 切换系统语言为中文
2. 检查备份管理页面所有文字
3. 切换系统语言为英文
4. 检查备份管理页面所有文字
5. 切换系统语言为日语
6. 检查备份管理页面所有文字

**预期结果：**
- 中/英/日三种语言界面文字完整，无缺失

#### 用例4：恢复确认对话框

**步骤：**
1. 创建白名单备份
2. 点击恢复按钮
3. 查看确认对话框

**预期结果：**
- 显示备份内容预览
- 显示警告提示
- 确认后执行恢复

## 五、实施计划

| 阶段 | 任务 | 状态 | 依赖 |
|-----|------|------|------|
| 阶段一 | 修复白名单备份字段映射 | pending | 无 |
| 阶段二 | 白名单恢复后触发合规重算 | pending | 阶段一 |
| 阶段三 | 修复备份文件名命名 | pending | 阶段一 |
| 阶段四 | 完善中文翻译 | pending | 无 |
| 阶段五 | 完善英文翻译 | pending | 阶段四 |
| 阶段六 | 完善日语翻译 | pending | 阶段四 |
| 阶段七 | 统一恢复确认对话框 | pending | 阶段四 |
| 阶段八 | 重建服务并运行验证 | pending | 所有阶段 |

## 六、代码变更清单

### 后端变更

| 文件 | 变更类型 | 说明 |
|-----|---------|------|
| `backend/app/services/backup_service.py` | 修改 | 修复白名单备份字段、添加合规重算触发、修复文件名 |

### 前端变更

| 文件 | 变更类型 | 说明 |
|-----|---------|------|
| `frontend/src/pages/Backup.tsx` | 修改 | 统一恢复确认对话框 |
| `frontend/src/i18n/locales/zh.ts` | 修改 | 添加备份相关翻译 |
| `frontend/src/i18n/locales/en.ts` | 修改 | 添加备份相关翻译 |
| `frontend/src/i18n/locales/ja.ts` | 修改 | 添加备份相关翻译 |

### 文档变更

| 文件 | 变更类型 | 说明 |
|-----|---------|------|
| `docs/user-guide.md` | 修改 | 更新备份管理章节 |

## 七、注意事项

1. **Git Flow 规范**：所有变更在 develop 分支完成，通过 PR 合并到 main，打 tag 后同步回 develop
2. **Docker Compose 规范**：使用 `./manage.sh update` 重建服务，不直接使用 docker-compose 命令
3. **数据安全**：恢复操作会覆盖现有数据，必须在前端展示明确的警告信息
4. **权限控制**：备份相关 API 使用 `require_permission("backup:write")` 保护
5. **审计日志**：所有备份操作（创建、恢复、删除）需要记录审计日志