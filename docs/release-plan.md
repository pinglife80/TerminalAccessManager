# v3.4.0 发布方案

> 文档版本：v3.4.0 | 更新日期：2026-06-22
> 文档性质：版本发布输出文档，记录发布准备、流程、部署步骤和回滚方案

---

## 一、发布概要

| 项目 | 内容 |
|------|------|
| **版本号** | v3.4.0 |
| **发布类型** | Minor（功能增强 + Bug 修复，向后兼容） |
| **发布日期** | 2026-06-22 |
| **前置版本** | v3.3.1 |
| **develop 提交数** | 7 个提交，主要功能变更 |
| **生产就绪评分** | 9.0/10 |

### 版本号决策

develop 上自 v3.3.1 以来新增了系统版本显示、权限 i18n、多环境配置（新功能）、两阶段删除（新功能）、审计日志优化（改进）、生产就绪改进（改进）等。根据语义化版本：

- **Minor 递增**：系统版本显示等是向后兼容的新功能 → v3.**4**.0
- 不用 v3.2.1（Patch 仅用于 bug 修复）
- 不用 v4.0.0（无破坏性变更）

---

## 二、发布前状态

### 2.1 Git 状态

| 项目 | 状态 |
|------|------|
| develop 分支 | 当前功能提交，领先 main 7 个提交 |
| main 分支 | v3.3.1 |
| 最新 tag | `v3.3.1` |

### 2.2 版本号不一致（必须修复）

| 位置 | 当前值 | 应更新为 |
|------|--------|---------|
| `manage.sh` VERSION | 3.3.1 | 3.4.0 |
| `frontend/package.json` version | 3.3.1 | 3.4.0 |
| `backend/app/core/config.py` VERSION | 3.3.1 | 3.4.0 |
| `.env.example` VERSION | 3.3.1 | 3.4.0 |
| 所有文档 | v3.3.1 | v3.4.0 |

### 2.3 生产就绪评估

- 综合评分 9.0/10，已达标
- 无 Critical/High 阻塞项
- 7 个 Medium 风险项均为非阻塞
- 测试覆盖后端 ~30%（达标）、前端 ~15%（未达标但非阻塞）

### 2.4 CI/CD 状态

- CI 流水线已建立（lint + test + build，6 个 job）
- main 分支保护规则已定义（需 PR + CI 通过）

---

## 三、发布准备（在 develop 上完成）

### Step 1: 同步版本号

| 文件 | 修改 |
|------|------|
| `manage.sh` 第 74 行 | `VERSION="2.0.0"` → `VERSION="3.3.0"` |
| `frontend/package.json` 第 4 行 | `"version": "2.0.0"` → `"version": "3.3.0"` |
| `backend/app/core/config.py` 第 12 行 | `VERSION: str = "3.2.0"` → `VERSION: str = "3.3.0"` |
| `.env.example` 第 14 行 | `VERSION=3.2.0` → `VERSION=3.3.0` |

### Step 2: 更新 changelog.md

将 `[Unreleased]` 下的所有条目移入 `[3.3.0] - 2026-06-17` 版本块，新增空 `[Unreleased]` 占位。

### Step 3: 更新 release-notes.md

新增 `[v3.3.0] - 2026-06-17` 版本记录，包含 develop 上 v3.2.0 以来所有 39 个提交的分类汇总。

### Step 4: 更新所有文档版本号

17 个文档的版本号从 `v3.2.0-r12` 更新为 `v3.3.0`，日期更新为 `2026-06-17`。

> **版本号规则**：发布版本使用三段式语义化版本号（v3.3.0），开发迭代期间使用修订号（v3.3.0-r1, r2...）追踪文档变更。

### Step 5: 提交到 develop

```bash
git add -A
git commit -m "release: prepare v3.3.0 release"
git push origin develop
```

---

## 四、发布流程

### Step 6: 创建 PR（develop → main）

在 GitHub 上创建 Pull Request: develop → main
- 标题: "Release v3.3.0"
- 描述: 从 release-notes.md 复制 v3.3.0 内容

### Step 7: CI 验证

PR 创建后自动触发 CI（6 个 job 必须全部通过）：
- backend-lint (ruff)
- backend-test (pytest)
- frontend-lint (ESLint)
- frontend-test (vitest)
- backend-build (Docker)
- frontend-build (Docker)

### Step 8: 合并 PR

CI 通过后，在 GitHub 上 Merge PR（使用 Merge commit，不用 Squash）。

### Step 9: 打 tag

```bash
git checkout main
git pull origin main
git tag -a v3.3.0 -m "release v3.3.0: RBAC, audit log optimization, production readiness"
git push origin v3.3.0
```

### Step 10: 创建 GitHub Release

在 GitHub Releases 页面：
1. 选择 tag: `v3.3.0`
2. 标题: `v3.3.0`
3. 内容: 从 release-notes.md 复制 `[v3.3.0]` 部分
4. 发布

### Step 11: 同步 develop

```bash
git checkout develop
git merge main  # 确保 develop 包含 tag
git push origin develop
```

---

## 五、生产部署

### Step 12: 部署到生产服务器

```bash
# 首次部署
git clone https://github.com/pinglife80/TerminalAccessManager.git
cd TerminalAccessManager
git checkout v3.3.0
chmod +x manage.sh
./manage.sh deploy --prod

# 后续升级（从旧版本）
./manage.sh upgrade v3.3.0
```

### Step 13: 部署后验证

| 验证项 | 方法 |
|--------|------|
| HTTPS 访问 | 浏览器访问 `https://<HOST_IP>:8443` |
| JWT 认证 | 登录 admin 账户，检查 token 刷新 |
| 功能模块 | 终端/白名单/黑名单/数据源/审计日志各页面 |
| RBAC 权限 | 不同角色访问不同功能 |
| Docker 健康 | `./manage.sh health` |
| 日志检查 | `./manage.sh logs` |

---

## 六、回滚方案

### 方案 A: 版本回退

```bash
./manage.sh upgrade v3.2.0
```

### 方案 B: 紧急修复（hotfix）

```bash
git checkout main
git checkout -b hotfix/fix-critical-issue
# ... 修复 ...
git checkout main
git merge --no-ff hotfix/fix-critical-issue
git tag -a v3.3.1 -m "hotfix: fix critical issue"
git push origin main --tags
git checkout develop
git merge hotfix/fix-critical-issue
git push origin develop
```

---

## 七、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `manage.sh` | 编辑 | VERSION 2.0.0 → 3.3.0 |
| `frontend/package.json` | 编辑 | version 2.0.0 → 3.3.0 |
| `backend/app/core/config.py` | 编辑 | VERSION 3.2.0 → 3.3.0 |
| `.env.example` | 编辑 | VERSION 3.2.0 → 3.3.0 |
| `docs/changelog.md` | 编辑 | [Unreleased] → [3.3.0]，版本号 → v3.3.0 |
| `docs/release-notes.md` | 编辑 | 新增 [v3.3.0]，版本号 → v3.3.0 |
| `docs/release-plan.md` | 新增 | 发布方案文档 |
| `docs/user-guide.md` | 新增 | 用户使用手册 |
| `docs/quick-start-guide.md` | 新增 | 快速上手指南 |
| `docs/api.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/architecture.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/backend.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/database.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/deployment.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/manage-sh-reference.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/datasource-lifecycle.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/RBAC.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/branding.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/logging-guide.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/git-workflow-guide.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/production-readiness-assessment.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/disaster-recovery.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/operations-runbook.md` | 编辑 | 版本号 → v3.3.0 |
| `frontend/docs/implementation.md` | 编辑 | 版本号 → v3.3.0 |

共 24 个文件需要修改（含新增 3 个）。

---

## 八、验证清单

- [ ] 所有版本号统一为 3.3.0
- [ ] changelog.md [Unreleased] 条目已移入 [3.3.0]
- [ ] release-notes.md [v3.3.0] 内容完整
- [ ] release-plan.md 已创建到 docs/ 目录
- [ ] user-guide.md 已创建到 docs/ 目录
- [ ] quick-start-guide.md 已创建到 docs/ 目录
- [ ] CI 6 个 job 全部通过
- [ ] PR 已合并到 main
- [ ] v3.3.0 tag 已创建并推送
- [ ] GitHub Release 已发布
- [ ] develop 已同步 main（包含 tag）
- [ ] 生产部署验证通过
