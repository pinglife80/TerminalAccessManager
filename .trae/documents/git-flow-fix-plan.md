# Git Flow 发布流程修复计划

## 问题分析

**现状**：v3.6.9 版本发布时直接在 `main` 分支提交，跳过了以下规范流程：

| 规范步骤 | 实际执行 | 问题 |
|----------|----------|------|
| develop 分支开发 | ❌ 直接在 main 开发 | 分支策略违规 |
| 创建 PR（develop → main） | ❌ 未创建 PR | 无 CI 验证、无代码审查 |
| CI 通过后合并 | ❌ 直接 push | 质量保障缺失 |
| 打 tag | ✅ 已完成 | - |
| 同步回 develop | ❌ 未执行 | develop 落后 |

**当前分支状态**：
- `main`: 包含 v3.6.9 提交（`956aa3e`）+ tag `v3.6.9`
- `develop`: 落后 2 个提交（缺少 v3.6.8 和 v3.6.9）

---

## 修复方案

### 方案 A：同步 develop 到 main（推荐）

由于代码已推送且 tag 已创建，最安全的做法是将 develop 同步到 main，确保分支一致性。

**执行步骤**：

```bash
# 1. 切换到 develop
git checkout develop

# 2. 拉取最新远程
git pull origin develop

# 3. 合并 main 到 develop（快进合并）
git merge main --ff-only

# 4. 推送到远程
git push origin develop

# 5. 验证分支同步状态
git log --oneline -5 --all --graph
```

### 方案 B：回滚 main 并重新走 PR 流程

如果需要严格遵循规范（包括 CI 验证），可以回滚并重做。

**风险**：需要强制推送，可能影响已部署的生产环境。

---

## 未来发布规范流程

为确保后续版本严格遵循 Git Flow 规范，制定标准发布流程：

### 标准发布流程（Patch 版本）

```bash
# Step 1: 切换到 develop，确保最新
git checkout develop
git pull origin develop

# Step 2: 创建 bugfix 分支
git checkout -b bugfix/compliance-logic-optimization

# Step 3: 开发和提交（遵循 Conventional Commits）
git commit -m "fix(compliance): ..."
git commit -m "docs(compliance): ..."

# Step 4: 推送到远程
git push -u origin bugfix/compliance-logic-optimization

# Step 5: 创建 PR（bugfix → develop）
# GitHub: New Pull Request

# Step 6: CI 通过后合并到 develop
# GitHub: Merge Pull Request

# Step 7: 删除临时分支
git branch -d bugfix/compliance-logic-optimization
git push origin --delete bugfix/compliance-logic-optimization

# Step 8: 更新版本号和文档
git checkout develop
git pull origin develop
./manage.sh version bump 3.6.9
git commit -m "chore(release): prepare v3.6.9"
git push origin develop

# Step 9: 创建 Release PR（develop → main）
# GitHub: New Pull Request from develop to main

# Step 10: CI 通过后合并到 main
# GitHub: Merge Pull Request

# Step 11: 打 tag
git checkout main
git pull origin main
git tag -a v3.6.9 -m "release v3.6.9: compliance logic optimization"
git push origin v3.6.9

# Step 12: 创建 GitHub Release
# GitHub: Releases → Draft a new release

# Step 13: 同步回 develop
git checkout develop
git merge main
git push origin develop
```

### 流程检查清单

| 检查项 | 说明 |
|--------|------|
| ✅ 代码在 develop 分支开发 | 不直接在 main 提交 |
| ✅ 创建 PR 到 develop | 小改动可直接 push，大改动必须 PR |
| ✅ CI 通过 | lint + test 必须全部通过 |
| ✅ 更新 changelog.md | 记录版本变更 |
| ✅ 更新 release-notes.md | 记录发布过程 |
| ✅ 更新技术文档 | 反映代码变更 |
| ✅ 创建 PR（develop → main） | 发布前必须走 PR |
| ✅ 在 main 上打 tag | 仅在 main 分支打版本 tag |
| ✅ 创建 GitHub Release | 填写 release notes |
| ✅ 同步回 develop | 确保 develop 包含 tag |

---

## 风险处理

### 风险 1：develop 合并冲突

**应对**：手动解决冲突，确保代码一致性。

### 风险 2：CI 失败

**应对**：修复失败的测试或 lint 错误，重新推送。

### 风险 3：tag 推送失败

**应对**：检查网络和权限，重新推送。

---

## 执行计划

| 步骤 | 任务 | 负责人 | 状态 |
|------|------|--------|------|
| 1 | 同步 develop 到 main | 自动化 | pending |
| 2 | 验证分支同步状态 | 自动化 | pending |
| 3 | 更新 git-workflow-guide.md | 自动化 | pending |
| 4 | 制定标准发布检查清单 | 自动化 | pending |