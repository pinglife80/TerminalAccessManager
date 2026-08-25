# v3.11.0 发布计划

## 一、发布概要

| 项目 | 内容 |
|------|------|
| **当前版本** | v3.10.4 |
| **目标版本** | v3.11.0 |
| **发布类型** | Minor（新功能 + Bug 修复，向后兼容） |
| **分支** | feature → develop → main（通过 PR） |
| **Remote** | git@github.com:pinglife80/TerminalAccessManager.git |

### 版本号决策依据

本次变更包含 **合规 Scope 条件管理**（新功能）+ **多处 Bug 修复**：
- ✅ 新增 Compliance Scope 条件管理功能 → **Minor 升级** (v3.10.4 → v3.11.0)
- 合规 recalculate 集成修复（Bug fix）
- 侧边栏 UI 修复（Bug fix）
- 白名单备份导入功能增强（功能增强）

---

## 二、变更清单

### 2.1 新增文件（未追踪）

| 文件 | 说明 |
|------|------|
| `backend/alembic/versions/031_compliance_scope.py` | 数据库迁移：创建 `compliance_scope` 表 |
| `backend/app/models/compliance_scope.py` | 数据模型：`ComplianceScope` ORM 模型 |
| `backend/app/schemas/compliance_scope.py` | Pydantic Schema：请求/响应验证 |
| `backend/app/services/compliance_scope_service.py` | Service 层：CRUD + 缓存失效 + 格式校验 |
| `backend/app/api/v1/endpoints/compliance_scope.py` | API 端点：RESTful CRUD + toggle |
| `frontend/src/api/complianceScope.ts` | 前端 API：React Query hooks |
| `frontend/src/pages/ComplianceScope.tsx` | 前端页面：Scope 管理 UI |

### 2.2 修改文件（已修改）

| 文件 | 变更说明 |
|------|----------|
| `backend/alembic/env.py` | 注册 `ComplianceScope` 模型到 Alembic 上下文 |
| `backend/app/api/v1/api.py` | 注册 `compliance_scope` 路由 |
| `backend/app/models/__init__.py` | 注册 `ComplianceScope` 到模型列表 |
| `backend/app/services/compliance_service.py` | **核心修改**：1) 白名单后增加 scope 检查节点；2) recalculate_all_compliance 集成 scope；3) bypass 快速降级；4) auto_unblock 集成 scope |
| `backend/app/services/terminal_service.py` | 白名单备份导入、合规统计方法 |
| `backend/app/api/v1/endpoints/blacklist.py` | 黑名单导出字段修复 |
| `backend/app/api/v1/endpoints/whitelist.py` | 白名单导入增强 + 备份文件支持 |
| `backend/app/schemas/terminal.py` | Terminal Schema 新增字段 |
| `frontend/src/App.tsx` | 路由注册 ComplianceScope 页面 |
| `frontend/src/components/Sidebar.tsx` | 侧边栏折叠按钮裁剪修复 + 导航项 |
| `frontend/src/index.css` | 侧边栏自定义滚动条样式 |
| `frontend/src/lib/constants.ts` | 新增 COMPLIANCE_SCOPE 导航项和 API 端点 |
| `frontend/src/i18n/locales/zh.ts` | 中文翻译：complianceScope |
| `frontend/src/i18n/locales/en.ts` | 英文翻译：complianceScope |
| `frontend/src/i18n/locales/ja.ts` | 日文翻译：complianceScope |
| `frontend/src/pages/Whitelist.tsx` | 白名单页面增强（导入功能、冲突处理） |
| `frontend/src/pages/Blacklist.tsx` | 黑名单页面小调整 |

### 2.3 统计数据

- **新增文件**: 7 个
- **修改文件**: 17 个
- **总变更量**: +1350 / -35 行
- **新增迁移**: 1 个 (031_compliance_scope)

---

## 三、版本号同步计划

### 3.1 需修改的版本号位置

| 文件 | 当前值 | 目标值 | 方式 |
|------|--------|--------|------|
| `VERSION` | 3.10.4 | 3.11.0 | 直接编辑 |
| `frontend/package.json` | 3.10.4 | 3.11.0 | 直接编辑 |
| `frontend/package-lock.json` | 3.10.4 | 3.11.0 | 直接编辑 |
| 所有文档版本头 | v3.10.4 | v3.11.0 | 批量编辑 |

### 3.2 版本同步步骤

```
Step 1: 编辑 VERSION → 3.11.0
Step 2: 编辑 frontend/package.json → "version": "3.11.0"
Step 3: 编辑 frontend/package-lock.json → "version": "3.11.0"
Step 4: 同步后端 Dockerfile（从 VERSION 文件自动读取，无需手动改）
Step 5: 同步所有文档的版本头
```

---

## 四、文档更新计划

### 4.1 需更新的文档

| 文档 | 更新内容 |
|------|----------|
| **changelog.md** | 新增 `[3.11.0]` 版本块，记录所有变更 |
| **release-notes.md** | 新增 `[v3.11.0]` 版本记录，含修改文件清单 |
| **production-readiness-assessment.md** | 更新文档版本头 + 版本跟踪表 |
| **architecture.md** | 新增合规 Scope 条件节点架构说明 |
| **deployment.md** | 文档版本号更新 |
| **user-guide.md** | 新增 Compliance Scope 管理功能使用说明 |
| **api.md** | 新增 compliance-scope API 端点文档 |
| **database.md** | 新增 compliance_scope 表结构说明 |

### 4.2 文档更新顺序

```
1. changelog.md（版本变更日志）
2. release-notes.md（发布说明）
3. architecture.md（架构文档更新）
4. production-readiness-assessment.md（生产就绪评估）
5. deployment.md / user-guide.md / api.md / database.md（同步版本号）
```

---

## 五、Git 提交计划

### 5.1 分支策略（严格遵循 git-workflow-guide.md）

根据项目 Git 工作流规范，采用**简化版 Git Flow**：

```
main  ───────────────────────●──────────────────────
                              ↑ PR + merge + tag
                              │
develop  ────●──●──●──●──●──●──●──●──●──●──●──●────
             ↑                                ↑
feature/compliance-scope-management  ────●──●──●──●
                                        ↑ PR → develop
```

**分支职责**（参照 git-workflow-guide.md §1.2）：

| 分支 | 用途 | 来源 | 合并到 | 保护规则 |
|------|------|------|--------|---------|
| main | 生产发布基线 | — | — | 禁止 force push + 删除 + 强制 PR + CI |
| develop | 开发集成分支 | 初始从 main | — | 禁止 force push + 删除 |
| feature/compliance-scope-management | 本次功能开发 | develop | develop | 无保护 |

### 5.2 提交策略

按功能主题拆分为 **3 个 commit**（符合 Conventional Commits 规范）：

#### Commit 1: 合规 Scope 条件管理功能

```
feat(compliance-scope): add scope-based compliance calculation

- Add ComplianceScope model, schema, service, and API endpoints
- Add frontend management page with CRUD and toggle
- Integrate scope conditions into compliance calculation flow:
  whitelist check → scope condition check → IPGuard baseline match
- Support ip_cidr, ip_range, mac_prefix scope types
- Add scope-based IP-only vs IP+MAC matching strategy selection
- Fix recalculate_all_compliance to include scope conditions
- Add cache invalidation on scope changes
- Add i18n translations (zh/en/ja)
- Add Alembic migration 031_compliance_scope

Files:
- backend/alembic/versions/031_compliance_scope.py (new)
- backend/app/models/compliance_scope.py (new)
- backend/app/schemas/compliance_scope.py (new)
- backend/app/services/compliance_scope_service.py (new)
- backend/app/api/v1/endpoints/compliance_scope.py (new)
- backend/app/services/compliance_service.py
- backend/alembic/env.py
- backend/app/models/__init__.py
- backend/app/api/v1/api.py
- backend/app/schemas/terminal.py
- frontend/src/api/complianceScope.ts (new)
- frontend/src/pages/ComplianceScope.tsx (new)
- frontend/src/App.tsx
- frontend/src/lib/constants.ts
- frontend/src/i18n/locales/zh.ts
- frontend/src/i18n/locales/en.ts
- frontend/src/i18n/locales/ja.ts
```

#### Commit 2: 白名单导入与黑名单修复

```
fix(whitelist,blacklist): fix export/import and enhance import flow

- Fix blacklist export field references (id, mac_address, etc.)
- Add ZIP/JSON backup file import support to whitelist page
- Add conflict resolution (skip/overwrite) for whitelist import
- Add savepoint transaction for row-level import error isolation
- Add whitelist compliance cache invalidation on import
- Fix import error messages specific to row numbers
- Enhance import UI with format guidance and progress feedback

Files:
- backend/app/api/v1/endpoints/blacklist.py
- backend/app/api/v1/endpoints/whitelist.py
- backend/app/services/terminal_service.py
- frontend/src/pages/Whitelist.tsx
- frontend/src/pages/Blacklist.tsx
```

#### Commit 3: UI 与体验修复

```
fix(ui,sidebar): fix sidebar scrollbar, toggle button, and layout issues

- Fix sidebar toggle button clipping (overflow-hidden → min-h-0 approach)
- Add custom thin scrollbar for sidebar navigation (6px width, dark theme)
- Fix scrollbar overflow beyond sidebar boundary
- Ensure toggle button fully visible and not clipped by scrollbar area

Files:
- frontend/src/components/Sidebar.tsx
- frontend/src/index.css
```

### 5.3 Commit 顺序

```
Commit 1: feat(compliance-scope) ← 核心新功能
Commit 2: fix(whitelist,blacklist) ← Bug 修复 + 功能增强
Commit 3: fix(ui,sidebar) ← UI 修复
```

---

## 六、PR 与分支同步计划（严格遵循 git-workflow-guide.md）

### 6.1 开发分支创建与提交

```bash
# Step 1: 确保 develop 分支最新
git checkout develop
git pull origin develop

# Step 2: 创建 feature 分支（从 develop 拉出）
git checkout -b feature/compliance-scope-management

# Step 3: 按 5.2 节顺序提交 3 个 commit
git add <files for commit 1>
git commit -m "feat(compliance-scope): add scope-based compliance calculation"

git add <files for commit 2>
git commit -m "fix(whitelist,blacklist): fix export/import and enhance import flow"

git add <files for commit 3>
git commit -m "fix(ui,sidebar): fix sidebar scrollbar, toggle button, and layout issues"

# Step 4: 推送 feature 分支到远程
git push -u origin feature/compliance-scope-management
```

### 6.2 第一个 PR：feature → develop

```
# 在 GitHub 创建 PR（参照 git-workflow-guide.md §5.2 PR 工作流）：
# Base: develop ← Compare: feature/compliance-scope-management
# Title: feat(compliance-scope): add scope-based compliance calculation
# Body: 使用 6.3 PR 内容模板

# PR 流程（严格遵循规范）：
# 1. 创建 PR → CI 自动运行（backend-lint + backend-test + frontend-lint + frontend-test）
# 2. CI 通过后 → 自审代码变更（PR 页面查看 diff）
# 3. Merge PR 到 develop
# 4. 删除远程 feature 分支（清理临时分支）
#    git push origin --delete feature/compliance-scope-management
```

**必须走 PR 的理由**（参照 git-workflow-guide.md §5.2）：
- 超过 5 个文件修改（7 个新文件 + 17 个修改文件）
- 涉及数据库迁移（031_compliance_scope）
- 涉及核心模块变更（compliance_service.py 合规计算逻辑）

### 6.3 PR 内容模板

```markdown
## Summary

### New Features
- Compliance Scope Management: support scope-based compliance calculation
- Whitelist backup file import (ZIP/JSON format)
- Enhanced whitelist import with conflict resolution

### Bug Fixes
- Compliance recalculate_all_compliance missing scope condition integration
- Sidebar toggle button clipping by overflow-hidden
- Sidebar scrollbar overflow beyond boundary
- Blacklist export field reference errors

### Improvements
- Custom thin scrollbar for dark theme sidebar
- Bypass status fast-track degradation (1 confirmation cycle)

## Test Plan
- [x] Python syntax validation (py_compile)
- [x] TypeScript compilation (tsc --noEmit)
- [x] Docker build and health check
- [x] Compliance calculation business verification
- [x] Whitelist import/export verification
- [x] Sidebar UI verification

## Files Changed
- 7 new files
- 17 modified files
- +1350 / -35 lines
- 1 new migration (031_compliance_scope)
```

### 6.4 第二个 PR：develop → main（发布分支）

```
# 根据 git-workflow-guide.md §1.4 核心规则：
# main 分支只接受 merge，不直接 commit；每次合并打 tag
# 根据 §5.1 分支保护规则：main 强制 PR + CI 通过

# 在 GitHub 创建第二个 PR：
# Base: main ← Compare: develop
# Title: release v3.11.0: compliance scope management, whitelist import, UI fixes
# Body: 使用 6.5 Release PR 内容模板

# PR 流程（严格遵循规范）：
# 1. 创建 PR → CI 自动运行
# 2. CI 通过后 → Merge PR 到 main
```

### 6.5 Release PR 内容模板

```markdown
## Release v3.11.0

### Version
v3.10.4 → v3.11.0 (Minor)

### Summary
本次发布包含合规 Scope 条件管理新功能、白名单导入增强、黑名单导出修复、UI 体验优化。

### Changes
- **New Feature**: Compliance Scope Management (IP CIDR / IP Range / MAC Prefix)
- **Enhancement**: Whitelist backup file import (ZIP/JSON) with conflict resolution
- **Bug Fix**: Blacklist export field references
- **Bug Fix**: Compliance recalculate missing scope condition integration
- **Bug Fix**: Sidebar toggle button clipping and scrollbar overflow

### Files Changed
- 7 new files
- 17 modified files
- +1350 / -35 lines
- 1 new migration

### Test Results
- [x] Python syntax validation
- [x] TypeScript compilation
- [x] Docker build and health check
- [x] Compliance calculation business verification
- [x] Whitelist import/export verification
- [x] Sidebar UI verification

### Related PR
- PR #XXX: feat(compliance-scope): add scope-based compliance calculation
```

### 6.6 Tag 创建与推送（在 main 上）

```bash
# PR 合并到 main 后，在 main 上创建 tag（参照 git-workflow-guide.md §3.5 发布新版本）
git checkout main
git pull origin main
git tag -a v3.11.0 -m "release v3.11.0: compliance scope management, whitelist import, UI fixes"
git push origin main --tags
```

### 6.7 分支同步（main → develop）

```bash
# 同步 main 变更回 develop，确保 develop 包含 tag（参照 git-workflow-guide.md §3.5）
git checkout develop
git merge main
git push origin develop
```

### 6.8 在 GitHub 创建 Release

```
# 参照 git-workflow-guide.md §5.3 Release 管理
# GitHub Releases → Draft a new release
# - Choose tag: v3.11.0
# - Release title: v3.11.0
# - Release notes: 从 changelog.md 复制 [3.11.0] 部分
# - Publish
```

---

## 七、风险评估与回滚

### 7.1 风险评估

| 风险项 | 等级 | 缓解措施 |
|--------|------|----------|
| 数据库迁移失败 | 低 | 新增表，不修改现有表结构 |
| 合规计算逻辑回归 | 低 | 保留现有 check/batch_check 逻辑，仅修复 recalculate |
| Sidebar UI 兼容性 | 极低 | CSS 变更，不影响功能 |
| 白名单导入向后兼容 | 低 | 支持现有 CSV 格式，新增 ZIP/JSON |

### 7.2 回滚方案

如果发布后出现严重问题：

```bash
# 方式 1: 通过 manage.sh 回滚
./manage.sh rollback v3.10.4

# 方式 2: 通过 git 回滚（参照 git-workflow-guide.md §3.7 回滚操作）
# 用 revert 而非 reset，保留历史
git checkout main
git revert <commit-hash>
git tag -a v3.11.1 -m "hotfix: rollback broken feature"
git push origin main --tags

# 同步回 develop
git checkout develop
git merge main
git push origin develop
```

---

## 八、验证清单

### 8.1 代码质量

- [x] Python 语法检查 (`py_compile`)
- [x] TypeScript 编译 (`tsc --noEmit`)
- [x] 所有修改文件无 lint 错误

### 8.2 服务功能

- [x] Backend 容器正常启动
- [x] 数据库迁移成功执行
- [x] 健康检查全部通过
- [x] API 端点正常响应

### 8.3 业务验证

- [x] Compliance Scope CRUD 正常
- [x] Scope 条件合规计算正确
- [x] 白名单导入/导出正常
- [x] 黑名单导出正常
- [x] 侧边栏滚动条 UI 正常

### 8.4 版本一致性

- [ ] VERSION = 3.11.0
- [ ] package.json version = 3.11.0
- [ ] package-lock.json version = 3.11.0
- [ ] 所有文档版本头 = v3.11.0

---

## 九、执行步骤总结

按以下顺序执行发布流程（严格遵循 git-workflow-guide.md）：

```
Phase 1: 版本号同步（在 feature 分支上完成）
  1.1 更新 VERSION → 3.11.0
  1.2 更新 frontend/package.json → 3.11.0
  1.3 更新 frontend/package-lock.json → 3.11.0

Phase 2: 文档更新（在 feature 分支上完成）
  2.1 更新 changelog.md [3.11.0]
  2.2 更新 release-notes.md [v3.11.0]
  2.3 更新 architecture.md（scope 架构说明）
  2.4 更新 production-readiness-assessment.md
  2.5 同步其他文档版本号

Phase 3: Git 提交（在 feature 分支上完成，3 个 commit）
  3.1 feat(compliance-scope): ...  ← 核心新功能 + 文档 + 版本号
  3.2 fix(whitelist,blacklist): ...
  3.3 fix(ui,sidebar): ...

Phase 4: 第一个 PR（feature → develop）
  4.1 git checkout -b feature/compliance-scope-management（从 develop 拉出）
  4.2 推送分支到远程
  4.3 创建 GitHub PR（base: develop，参照 §6.2）
  4.4 CI 验证通过后合并 PR
  4.5 删除远程 feature 分支

Phase 5: 第二个 PR（develop → main，发布分支）
  5.1 确保 develop 已包含所有变更
  5.2 创建 GitHub PR（base: main，参照 §6.4）
  5.3 CI 验证通过后合并 PR

Phase 6: Tag 创建（在 main 上）
  6.1 git checkout main && git pull origin main
  6.2 git tag -a v3.11.0 -m "release v3.11.0: ..."
  6.3 git push origin main --tags

Phase 7: 分支同步（main → develop）
  7.1 git checkout develop
  7.2 git merge main（确保 develop 包含 tag）
  7.3 git push origin develop

Phase 8: GitHub Release 创建
  8.1 GitHub Releases → Draft a new release
  8.2 选择 tag: v3.11.0
  8.3 填写 Release title 和 notes
  8.4 Publish
```

---

> 本文档待用户审核确认后执行。所有步骤严格遵循 [git-workflow-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/git-workflow-guide.md) 规范。
