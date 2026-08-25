# 合规基线按钮修复 - 审核与提交计划

> 创建日期：2026-07-16
> 当前版本：v3.6.15 → 目标版本：v3.6.16 (Patch)

***

## 一、代码变更审核

### 1.1 变更概览

本次共修改 7 个文件，+56 行 / -5 行：

| 文件                                                               | 变更类型     | 说明                                                   |
| ---------------------------------------------------------------- | -------- | ---------------------------------------------------- |
| `backend/app/schemas/data_source.py`                             | feat     | AutoBlockResult 和 AutoUnblockResult 添加 message 字段    |
| `backend/app/services/compliance_service.py`                     | fix      | auto\_unblock\_compliant 返回 message 提示               |
| `frontend/src/components/datasources/ComplianceBaselinesTab.tsx` | fix+feat | Force Re-check 复选框；Modal 替换 window\.confirm；优化 toast |
| `frontend/src/i18n/locales/zh.ts`                                | feat     | 添加4条中文翻译                                             |
| `frontend/src/i18n/locales/en.ts`                                | feat     | 添加4条英文翻译                                             |
| `frontend/src/i18n/locales/ja.ts`                                | feat     | 添加4条日文翻译                                             |
| `frontend/package.json`                                          | chore    | version 3.6.14 → 3.6.15（自动更新）                        |

### 1.2 变更详情

#### 文件1: `backend/app/schemas/data_source.py`

**变更 - 添加 message 字段**（第124行、第134行）：

* `AutoBlockResult` 添加 `message: str | None = None`

* `AutoUnblockResult` 添加 `message: str | None = None`

* 原因：后端已有 message 返回值但 schema 中缺失字段，导致前端无法获取

#### 文件2: `backend/app/services/compliance_service.py`

**变更 - auto\_unblock\_compliant 返回 message**（第767行）：

* 添加 `message="All blocked terminals are still non-compliant" if unblocked == 0 and skipped > 0 else None`

* 原因：0条解封时返回原因说明

#### 文件3: `frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

**变更A - 添加 state**（第306-307行）：

* `forceCheck` 和 `showAutoBlockModal` 状态

**变更B - handleComplianceCheck 使用 forceCheck**（第314行）：

* `force: false` → `force: forceCheck`

* 原因：允许用户强制重新检查已处理的终端

**变更C - handleAutoBlock 拆分为两步**（第329-358行）：

* `handleAutoBlockClick`：打开 Modal

* `handleAutoBlockConfirm`：确认后执行

* 添加 `r.total_non_compliant === 0` 时的 toast.info 提示

**变更D - handleAutoUnblock 优化提示**（第368-370行）：

* 添加 `r.unblocked === 0 && r.skipped > 0` 时的 toast.info 提示

**变更E - 添加 Force Re-check 复选框**（第399-407行）

**变更F - Auto Block 按钮 onClick 改为 handleAutoBlockClick**（第418行）

**变更G - 添加 Auto Block 确认 Modal**（第431-445行）

#### 文件4-6: i18n 翻译

每个文件添加4条翻译：

* `forceRecheck`

* `autoBlockWarning`

* `autoBlockNoAction`

* `autoUnblockNoAction`

#### 文件7: `frontend/package.json`

* version: `3.6.14` → `3.6.15`（npm 构建自动更新）

### 1.3 审核结论

* 所有变更均为 bug 修复和 UX 改进，无新功能添加

* 变更逻辑正确，后端 message 字段已验证返回

* 前端 Modal 替换符合项目现有 UI 规范

* 无破坏性变更，向后兼容

* 符合 Patch 版本升级标准

***

## 二、文档更新

### 2.1 需要更新的文档

| 文档                           | 更新内容                        |
| ---------------------------- | --------------------------- |
| `VERSION`                    | `3.6.15` → `3.6.16`         |
| `frontend/package.json`      | version `3.6.15` → `3.6.16` |
| `docs/changelog.md`          | 添加 `[3.6.16]` 条目 + 头部版本号    |
| `docs/release-notes.md`      | 添加 `[v3.6.16]` 发布记录 + 头部版本号 |
| `docs/git-workflow-guide.md` | 头部版本号 `v3.6.15` → `v3.6.16` |

### 2.2 changelog.md 新增内容

在 `## [3.6.15]` 之前添加 `## [3.6.16] - 2026-07-16` 条目：

```markdown
## [3.6.16] - 2026-07-16

### 修复

- **合规检查 Force Re-check 选项**：Run Compliance Check 按钮添加强制重新检查复选框
  - 原因：前端硬编码 `force: false`，只检查 unknown 终端，但 ARP 采集时已自动处理
  - 变更：添加 `forceCheck` state，传递到 API 请求
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

- **Auto Block 确认对话框优化**：用自定义 Modal 替换浏览器原生 window.confirm
  - 原因：`window.confirm` 与项目 UI 设计不一致
  - 变更：添加 `showAutoBlockModal` state，拆分为 `handleAutoBlockClick` 和 `handleAutoBlockConfirm`
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

- **Auto Block / Auto Unblock 提示优化**：0条操作时添加 toast.info 说明原因
  - 变更：Auto Block 返回0条时提示"所有不合规终端已封锁"
  - 变更：Auto Unblock 返回0解封时提示"被封锁终端均未变为合规状态"
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

### 新增

- **后端 message 字段**：AutoBlockResult 和 AutoUnblockResult 添加 message 字段
  - 原因：后端已返回 message 但 schema 缺失字段
  - 变更：`auto_unblock_compliant` 方法返回 `message` 提示
  - 关联文件：`backend/app/schemas/data_source.py`、`backend/app/services/compliance_service.py`

- **i18n 翻译**：三语言添加4条合规相关翻译
  - `forceRecheck`、`autoBlockWarning`、`autoBlockNoAction`、`autoUnblockNoAction`
  - 关联文件：`frontend/src/i18n/locales/{zh,en,ja}.ts`
```

### 2.3 release-notes.md 新增内容

在 `## [v3.6.15]` 之前添加 `## [v3.6.16]` 发布记录。

***

## 三、代码提交推送计划

### 3.1 分支策略

根据 [git-workflow-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/git-workflow-guide.md) 的规范：

* 本次为 **bugfix + feat**（7个文件，>5个文件）

* 适用"标准开发模式"，但单人开发可直接在 develop 提交

* 无需创建临时分支和 PR

### 3.2 版本号

* 当前：v3.6.15

* 目标：**v3.6.16** (Patch - Bug 修复 + UX 改进)

### 3.3 提交步骤

**步骤1：更新版本号**

* `VERSION` 文件改为 `3.6.16`

* `frontend/package.json` version 改为 `3.6.16`

**步骤2：更新文档**

* `docs/changelog.md`：添加 v3.6.16 条目 + 头部版本号

* `docs/release-notes.md`：添加 v3.6.16 发布记录 + 头部版本号

* `docs/git-workflow-guide.md`：头部版本号

**步骤3：暂存并提交**

```bash
git add backend/app/schemas/data_source.py
git add backend/app/services/compliance_service.py
git add frontend/src/components/datasources/ComplianceBaselinesTab.tsx
git add frontend/src/i18n/locales/zh.ts
git add frontend/src/i18n/locales/en.ts
git add frontend/src/i18n/locales/ja.ts
git add frontend/package.json
git add VERSION
git add docs/changelog.md
git add docs/release-notes.md
git add docs/git-workflow-guide.md

git commit -m "fix(compliance): 优化合规基线管理按钮交互体验

- Run Compliance Check 添加 Force Re-check 复选框
- Auto Block 用自定义 Modal 替换浏览器原生 window.confirm
- Auto Block/Unblock 返回0条操作时添加 toast.info 原因提示
- 后端 AutoBlockResult/AutoUnblockResult 添加 message 字段
- 三语言添加4条合规相关翻译

Bump version to v3.6.16"
```

**步骤4：推送到远程**

```bash
git push origin develop
```

**步骤5：发布版本（打 tag）**

```bash
git checkout main
git pull origin main
git merge --no-ff develop
git tag -a v3.6.16 -m "release v3.6.16: improve compliance baseline UX"

git push origin main --tags

git checkout develop
git merge main
git push origin develop
```

### 3.4 提交信息规范

* Type: `fix`（Bug 修复 + UX 改进）

* Scope: `compliance`（合规模块）

* Subject: `优化合规基线管理按钮交互体验`

* Body: 详细说明5个改进点

***

## 四、验证清单

* [ ] VERSION 文件更新为 3.6.16

* [ ] frontend/package.json version 更新为 3.6.16

* [ ] changelog.md 添加 v3.6.16 条目

* [ ] release-notes.md 添加 v3.6.16 发布记录

* [ ] 文档版本号统一更新为 v3.6.16

* [ ] 代码提交到 develop 分支

* [ ] 推送到远程 origin/develop

* [ ] 合并到 main 并打 tag v3.6.16

* [ ] 推送 main 和 tags 到远程

