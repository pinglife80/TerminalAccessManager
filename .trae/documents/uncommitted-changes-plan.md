# 未提交代码处理计划

> 文档版本：v1.0 | 创建日期：2026-07-14
>
> **适用版本**：v3.6.11
> **分支策略**：简化版 Git Flow

---

## 1. 问题分析

当前本地 develop 分支存在大量未提交的代码变更，分为两类：

### 1.1 未暂存的修改文件（18个）

| 文件 | 变更规模 | 所属功能模块 |
|------|---------|-------------|
| `backend/app/api/v1/endpoints/backup.py` | 中 | 备份管理 |
| `backend/app/api/v1/endpoints/system.py` | 小 | 系统管理 |
| `backend/app/api/v1/endpoints/terminals.py` | 小 | 终端管理 |
| `backend/app/main.py` | 小 | 主应用 |
| `backend/app/models/backup_config.py` | 中 | 备份管理 |
| `backend/app/models/blacklist.py` | 小 (+1行) | 黑名单 |
| `backend/app/models/notification.py` | 小 (+10/-10) | 通知系统 |
| `backend/app/schemas/backup.py` | 中 | 备份管理 |
| `backend/app/services/backup_service.py` | 大 (+401/-30) | 备份管理 |
| `backend/app/services/notification_channels/email_channel.py` | 小 | 通知系统 |
| `backend/app/services/terminal_service.py` | 小 | 终端管理 |
| `frontend/src/hooks/useTokenExpiration.ts` | 小 | 前端安全 |
| `frontend/src/i18n/locales/en.ts` | 小 | 国际化 |
| `frontend/src/i18n/locales/ja.ts` | 小 | 国际化 |
| `frontend/src/i18n/locales/zh.ts` | 小 | 国际化 |
| `frontend/src/lib/constants.ts` | 小 | 前端常量 |
| `frontend/src/pages/Backup.tsx` | 中 | 备份管理 |
| `frontend/src/pages/Terminals.tsx` | 小 | 终端管理 |

### 1.2 未跟踪的新文件（20个）

| 文件 | 类型 | 所属功能模块 |
|------|------|-------------|
| `.trae/documents/backend_architecture_analysis.md` | 文档 | 架构分析 |
| `.trae/documents/backend_log_analysis_plan.md` | 文档 | 日志分析 |
| `.trae/documents/backup-management-plan.md` | 文档 | 备份管理 |
| `.trae/documents/backup_optimization_plan.md` | 文档 | 备份优化 |
| `.trae/documents/blacklist_duplicate_fix_plan.md` | 文档 | 黑名单修复 |
| `.trae/documents/compliance-consistency-plan.md` | 文档 | 合规一致性 |
| `.trae/documents/compliance_logic_fix_plan.md` | 文档 | 合规逻辑修复 |
| `.trae/documents/firewall_sync_issue_plan.md` | 文档 | 防火墙同步 |
| `.trae/documents/git-flow-fix-plan.md` | 文档 | Git Flow修复 |
| `.trae/documents/git-flow-revert-plan.md` | 文档 | Git Flow回滚 |
| `.trae/documents/issue_root_cause_analysis_plan.md` | 文档 | 根因分析 |
| `.trae/documents/system-optimization-analysis-plan.md` | 文档 | 系统优化分析 |
| `.trae/documents/system-optimization-plan.md` | 文档 | 系统优化 |
| `.trae/documents/v3.6.10-release-plan.md` | 文档 | 发布计划 |
| `.trae/documents/v3.6.9-release-plan.md` | 文档 | 发布计划 |
| `backend/alembic/versions/027_backup_wl_tz_dt.py` | 数据库迁移 | 备份管理 |
| `backend/app/services/firewall_reconciliation_service.py` | 服务 | 防火墙对账 |
| `backend/scripts/` | 脚本目录 | 工具脚本 |
| `test_compliance_verify.py` | 测试 | 合规验证 |
| `test_verify.py` | 测试 | 通用验证 |

### 1.3 原因分析

这些文件未提交的原因：

1. **备份管理功能开发**：之前会话中开发的备份管理功能，涉及大量前后端代码变更
2. **防火墙对账服务**：新增的防火墙对账服务模块
3. **配置优化**：系统配置和国际化相关的小修改
4. **文档文件**：`.trae/documents/` 目录下的计划文档，通常不纳入版本控制
5. **测试文件**：临时测试脚本

---

## 2. 处理策略

### 2.1 分类处理原则

| 类别 | 处理方式 | 说明 |
|------|---------|------|
| **核心功能代码**（备份管理、防火墙对账） | 按功能模块分批提交 | 确保每个 commit 是完整的功能单元 |
| **小修改**（黑名单、通知模型等） | 合并到相关功能 commit | 避免碎片化提交 |
| **文档文件**（`.trae/documents/`） | 检查是否需要纳入版本控制 | 通常不需要，建议添加到 .gitignore |
| **测试文件**（test_*.py） | 检查是否为临时文件 | 临时文件建议删除或添加到 .gitignore |

### 2.2 Commit 计划

#### Commit 1: 备份管理功能开发

```bash
git add backend/app/api/v1/endpoints/backup.py
git add backend/app/models/backup_config.py
git add backend/app/schemas/backup.py
git add backend/app/services/backup_service.py
git add frontend/src/pages/Backup.tsx
git add backend/alembic/versions/027_backup_wl_tz_dt.py
git commit -m "feat(backup): implement backup management feature

- Add backup configuration model and schema
- Implement backup service with full CRUD operations
- Add backup API endpoints
- Add backup management UI page
- Add database migration for backup config"
```

#### Commit 2: 防火墙对账服务

```bash
git add backend/app/services/firewall_reconciliation_service.py
git commit -m "feat(firewall): add firewall reconciliation service

- Implement firewall state reconciliation logic
- Add methods to sync local blacklist with firewall state
- Support periodic reconciliation tasks"
```

#### Commit 3: 终端管理优化

```bash
git add backend/app/api/v1/endpoints/terminals.py
git add backend/app/services/terminal_service.py
git add frontend/src/pages/Terminals.tsx
git commit -m "feat(terminal): optimize terminal management

- Enhance terminal API endpoints
- Improve terminal service logic
- Update terminal management UI"
```

#### Commit 4: 系统配置和国际化更新

```bash
git add backend/app/api/v1/endpoints/system.py
git add backend/app/main.py
git add frontend/src/hooks/useTokenExpiration.ts
git add frontend/src/i18n/locales/en.ts
git add frontend/src/i18n/locales/ja.ts
git add frontend/src/i18n/locales/zh.ts
git add frontend/src/lib/constants.ts
git commit -m "chore: update system config and internationalization

- Update system API endpoints
- Enhance token expiration handling
- Update i18n translations for en/ja/zh
- Update frontend constants"
```

#### Commit 5: 通知和黑名单优化

```bash
git add backend/app/models/blacklist.py
git add backend/app/models/notification.py
git add backend/app/services/notification_channels/email_channel.py
git commit -m "fix(notification): optimize notification and blacklist models

- Fix blacklist model minor issue
- Optimize notification model structure
- Update email notification channel"
```

#### Commit 6: 工具脚本（如需要）

```bash
git add backend/scripts/
git commit -m "chore(scripts): add utility scripts

- Add backend utility scripts for maintenance tasks"
```

### 2.3 文档文件处理

`.trae/documents/` 目录下的文件是内部计划文档，通常不需要纳入版本控制。建议：

1. 检查 `.gitignore` 是否已排除 `.trae/` 目录
2. 如果未排除，添加到 `.gitignore`

### 2.4 测试文件处理

`test_compliance_verify.py` 和 `test_verify.py` 是临时测试脚本，建议：

1. 检查是否为临时文件
2. 如果是临时文件，删除或添加到 `.gitignore`
3. 如果是正式测试文件，移至 `tests/` 目录并提交

---

## 3. 执行步骤

### Step 1: 检查 .gitignore 配置

```bash
cat .gitignore | grep -E "\.trae|test_verify"
```

### Step 2: 按功能模块分批提交

按上述 Commit 计划依次执行 git add 和 git commit。

### Step 3: 推送 develop 分支

```bash
git push origin develop
```

### Step 4: 更新 changelog 和 release notes

在完成所有提交后，更新文档以反映这些变更。

---

## 4. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Commit 冲突 | 中 | 中 | 推送前先 pull develop |
| 功能不完整 | 低 | 高 | 确保每个 commit 功能完整 |
| 文档遗漏 | 低 | 中 | 提交后更新 changelog |

---

## 5. 验证方案

```bash
# 验证所有文件已提交
git status

# 验证提交记录
git log --oneline

# 验证服务健康
./manage.sh health
```

