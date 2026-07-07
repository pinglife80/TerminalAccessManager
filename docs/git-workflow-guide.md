# Git 敏捷开发指导手册

> 适用场景：单人/小团队、单产品、基于 GitHub 的敏捷开发
> 文档版本：v3.6.4  更新日期：2026-07-08

---

## 1. 分支策略

### 1.1 分支模型

采用 **简化版 Git Flow**，适配单人/小团队开发节奏：

```
main          ────●────────────●────────────●───
                   ↑            ↑            ↑
                v3.0.0       v3.1.0       v3.2.0
                   ↑            ↑
develop       ────●────●──●──●──●──●──●──●──●───
                        ↑     ↑        ↑
feature/xxx   ────●──●──┘     │        │
bugfix/xxx    ────────────────●────────┘
hotfix/xxx    ────────────────────●──●──┘  (从 main 拉出，合并回 main + develop)
```

### 1.2 分支职责

| 分支 | 用途 | 来源 | 合并到 | 生命周期 | 保护 |
|------|------|------|--------|---------|------|
| **main** | 生产发布，始终可部署 | — | — | 永久 | 是 |
| **develop** | 开发集成分支，最新成果 | 初始从 main | — | 永久 | 是 |
| **feature/xxx** | 新功能开发 | develop | develop | 临时 | 否 |
| **bugfix/xxx** | 非紧急 bug 修复 | develop | develop | 临时 | 否 |
| **hotfix/xxx** | 生产紧急修复 | main | main + develop | 临时 | 否 |

### 1.3 分支命名规范

```
feature/简短描述    # 新功能
feature/add-export-csv
feature/multi-firewall-support

bugfix/简短描述     # 非紧急修复
bugfix/fix-login-captcha
bugfix/fix-pagination-offset

hotfix/简短描述     # 生产紧急修复
hotfix/fix-redis-connection-leak
hotfix/fix-auth-bypass
```

### 1.4 核心规则

1. **main 分支**：只接受 merge，不直接 commit；每次合并打 tag（vX.Y.Z）
2. **develop 分支**：日常开发基线，feature/bugfix 完成后合并回来
3. **hotfix 分支**：从 main 拉出，修复后同时合并回 main（打 tag）和 develop
4. **临时分支**：合并后立即删除，保持分支列表整洁
5. **禁止 force push**：main 和 develop 分支禁止 `--force` 推送

---

## 2. 版本号规范

采用 [语义化版本](https://semver.org/lang/zh-CN/)：**Major.Minor.Patch**

| 版本类型 | 格式 | 何时递增 | 示例 |
|---------|------|---------|------|
| Patch | v3.1.**1** | Bug 修复，无新功能，向后兼容 | hotfix 修复 |
| Minor | v3.**2**.0 | 新功能，向后兼容 | feature 合并 |
| Major | v**4**.0.0 | 破坏性变更，不向后兼容 | 架构重构 |

**Tag 命名**：`v3.1.0`（v 前缀 + 三段式版本号）

---

## 3. 常用命令场景

### 3.1 初始化项目分支

```bash
# 场景：从现有 main 创建 develop 分支
git checkout main
git pull origin main
git checkout -b develop
git push -u origin develop
```

### 3.2 开发新功能

```bash
# 场景：开发"CSV导出"功能
git checkout develop
git pull origin develop
git checkout -b feature/add-export-csv

# ... 开发过程中，频繁提交 ...
git add backend/app/api/v1/endpoints/terminals.py
git commit -m "feat(terminals): add CSV export endpoint"

git add frontend/src/pages/Terminals.tsx
git commit -m "feat(terminals): add CSV export button to frontend"

# 开发完成，合并回 develop
git checkout develop
git pull origin develop
git merge --no-ff feature/add-export-csv
git push origin develop

# 删除临时分支
git branch -d feature/add-export-csv
git push origin --delete feature/add-export-csv  # 如已推送远程
```

### 3.3 修复非紧急 Bug

```bash
# 场景：修复分页偏移 bug
git checkout develop
git pull origin develop
git checkout -b bugfix/fix-pagination-offset

# ... 修复 ...
git add backend/app/services/terminal_service.py
git commit -m "fix(terminals): correct pagination offset calculation"

# 合并回 develop
git checkout develop
git merge --no-ff bugfix/fix-pagination-offset
git push origin develop
git branch -d bugfix/fix-pagination-offset
```

### 3.4 生产紧急修复（Hotfix）

```bash
# 场景：生产环境 Redis 连接泄漏，需要紧急修复
git checkout main
git pull origin main
git checkout -b hotfix/fix-redis-connection-leak

# ... 修复 ...
git add backend/app/core/security.py
git commit -m "hotfix(security): fix Redis connection leak in fail-open handlers"

# 1. 合并回 main 并打 tag
git checkout main
git merge --no-ff hotfix/fix-redis-connection-leak
git tag -a v3.1.1 -m "hotfix: fix Redis connection leak"
git push origin main --tags

# 2. 同步合并回 develop
git checkout develop
git merge hotfix/fix-redis-connection-leak
git push origin develop

# 3. 删除临时分支
git branch -d hotfix/fix-redis-connection-leak
```

### 3.5 发布新版本

```bash
# 场景：develop 积累了足够功能，准备发布 v3.2.0
git checkout main
git pull origin main
git merge --no-ff develop
git tag -a v3.2.0 -m "release v3.2.0: add CSV export, multi-firewall support"

git push origin main --tags

# 同步 develop
git checkout develop
git merge main  # 确保 develop 包含 tag
git push origin develop
```

### 3.6 查看版本历史

```bash
# 查看所有 tag
git tag -l

# 查看某个 tag 的详细信息
git show v3.1.0

# 查看 tag 之间的变更
git log v3.0.0..v3.1.0 --oneline

# 查看当前版本
git describe --tags --abbrev=0
```

### 3.7 回滚操作

```bash
# 场景1：某个 commit 引入 bug，需要撤销（保留历史）
git revert <commit-hash>
git push origin develop

# 场景2：develop 上最近一次 merge 有问题，需要撤销
git checkout develop
git revert -m 1 <merge-commit-hash>
git push origin develop

# 场景3：生产版本回退（不删除 tag，重新发布旧版本）
git checkout main
git revert <commit-hash>  # 用 revert 而非 reset
git tag -a v3.1.2 -m "hotfix: rollback broken feature"
git push origin main --tags
```

---

## 4. Commit 规范

### 4.1 Commit Message 格式

采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范：

```
<type>(<scope>): <subject>

<body>
```

### 4.2 Type 类型

| Type | 说明 | SemVer 影响 |
|------|------|------------|
| `feat` | 新功能 | Minor |
| `fix` | Bug 修复 | Patch |
| `hotfix` | 生产紧急修复 | Patch |
| `docs` | 文档变更 | — |
| `style` | 代码格式（不影响逻辑） | — |
| `refactor` | 重构（非新功能非修复） | — |
| `test` | 测试相关 | — |
| `chore` | 构建/工具/依赖变更 | — |
| `perf` | 性能优化 | Patch/Minor |

### 4.3 Scope 范围

| Scope | 说明 |
|-------|------|
| `auth` | 认证模块 |
| `terminals` | 终端管理 |
| `whitelist` | 白名单 |
| `blacklist` | 黑名单 |
| `security` | 安全模块 |
| `database` | 数据库/迁移 |
| `deploy` | 部署/配置 |
| `frontend` | 前端 |
| `ci` | CI/CD |

### 4.4 示例

```bash
git commit -m "feat(terminals): add CSV export endpoint"
git commit -m "fix(auth): correct token refresh when Redis unavailable"
git commit -m "hotfix(security): fix Redis connection leak in fail-open handlers"
git commit -m "docs(api): update auth endpoint documentation for v3.1"
git commit -m "test(security): add Redis fail-open degradation tests"
git commit -m "chore(deps): update bcrypt to 4.2.0"
git commit -m "refactor(search): replace func.replace with mac_address_normalized column"
```

---

## 5. GitHub 最佳实践

### 5.1 分支保护规则

**main 分支（严格保护）**：生产发布基线，任何代码进入都须经过 CI 验证。

**develop 分支（轻度保护）**：日常开发分支，小改动直接 push 减少摩擦，仅保留安全网。

| 保护规则 | main | develop | 理由 |
|---------|:----:|:-------:|------|
| 禁止 force push | ✅ | ✅ | 防止误操作覆盖历史，两个分支都应保护 |
| 禁止删除 | ✅ | ✅ | 核心分支不可删除 |
| PR 合并前 CI 通过 | ✅ | ❌ | main 是生产基线必须过 CI；develop 日常开发直接推，减少摩擦 |
| PR 合并前要求审批 | ❌ | ❌ | 单人开发无意义 |
| 要求分支最新 | ✅ | ❌ | main 合并前确保与目标分支同步 |

**main 强制 PR 的价值**（即使单人开发）：
- 触发 CI 自动检查（lint + test + build）
- PR 页面查看 diff 更清晰，相当于代码自审
- 防止误操作（force push / 直接 push 未验证代码）

**develop 不强制 PR 的理由**：
- 日常开发小改动频繁，每次走 PR 效率太低
- 小改动直接 push，大改动自觉走 PR 即可
- 只保留 force push 和删除保护作为安全网

**GitHub 设置方法**：

> **原则**：只勾选下面列出的项，其余全部不勾（包括默认勾选的也取消）。

**设置路径**：Settings → Code and automation → Branches → Add rule

**main 分支规则**：
1. Branch name pattern: `main`
2. ☑ **Require a pull request before merging**
3. ☑ **Require status checks to pass before merging**
   - ☑ Require branches to be up to date before merging
   - 搜索并勾选: `backend-lint`、`backend-test`、`frontend-lint`、`frontend-test`
4. 其余所有选项均不勾选
5. 点击 **Create**

> 注意：status checks 列表需要 CI 至少运行过一次后才会出现。如果搜不到，
> 先推送一次触发 CI 运行，再回来编辑规则勾选。

**develop 分支规则**：
1. Branch name pattern: `develop`
2. 其余所有选项均不勾选（默认已禁止 force push 和删除，无需额外操作）
3. 点击 **Create**

### 5.2 PR 工作流

```
1. 从 develop 创建 feature/bugfix 分支
2. 开发 + 提交
3. 推送到 GitHub
4. 创建 Pull Request (feature → develop)
5. CI 自动运行（lint + test + build）
6. 自审代码变更
7. CI 通过后 Merge PR
8. 删除远程分支
```

**单人开发简化模式**：对于小改动（1-3 个 commit），可以直接在 develop 上提交，跳过 PR 流程。但以下场景必须走 PR：

- 涉及核心模块变更（security/database/deploy）
- 超过 5 个文件修改
- 涉及数据库迁移

### 5.3 Release 管理

利用 GitHub Releases 管理版本发布：

```bash
# 1. 在 main 上打 tag
git tag -a v3.2.0 -m "release v3.2.0"
git push origin v3.2.0

# 2. 在 GitHub 上创建 Release
#    Releases → Draft a new release
#    - 选择 tag: v3.2.0
#    - 填写 Release title: v3.2.0
#    - 填写 Release notes（从 changelog.md 复制对应版本内容）
#    - 如有构建产物可附加
```

### 5.4 .gitignore 建议

确保以下文件不被提交：

```gitignore
# 环境配置
.env
.env.local
.env.production

# 敏感文件
*.pem
*.key
*.p12
nginx/certs/

# 运行时状态
.manage/

# 依赖
node_modules/
__pycache__/
*.pyc

# 构建产物
dist/
build/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

---

## 6. CI/CD 最佳实践

### 6.1 流水线设计原则

| 原则 | 说明 |
|------|------|
| **快速反馈** | lint/test 优先，build 在后；lint < 1min，test < 5min |
| **依赖并行** | 无依赖的 Job 并行执行，缩短总耗时 |
| **失败快速** | 任一前置 Job 失败，后续依赖 Job 自动跳过 |
| **缓存优化** | pip cache / npm cache 减少依赖安装时间 |
| **最小权限** | CI 环境不使用生产密钥，使用专用测试密钥 |

### 6.2 当前 CI 流水线结构

```
push/PR to main or develop
│
├── backend-lint ──────┐
├── backend-test ──────┤
├── frontend-lint ─────┤  (4个并行)
├── frontend-test ─────┘
│
├── backend-build ─────┐  (依赖 lint+test 通过)
├── frontend-build ────┘
```

### 6.3 触发策略

```yaml
on:
  push:
    branches: [main, develop]    # main/develop 推送触发完整 CI
  pull_request:
    branches: [main, develop]    # PR 触发完整 CI
```

**优化建议**：对于路径变更，可以添加 `paths` 过滤避免无关变更触发 CI：

```yaml
on:
  push:
    branches: [main, develop]
    paths:
      - 'backend/**'
      - 'frontend/**'
      - '.github/workflows/**'
      - 'docker-compose.yml'
```

### 6.4 发布自动化（进阶）

当项目成熟后，可添加 CD 流水线：

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'    # 推送 v 开头的 tag 时触发

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build & Push Docker Images
        run: |
          docker build -t tam-backend:${{ github.ref_name }} ./backend
          docker build -t tam-frontend:${{ github.ref_name }} ./frontend

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          generate_release_notes: true
```

---

## 7. 日常工作流速查

### 典型一天

```
早上：
  git checkout develop && git pull origin develop

开发新功能：
  git checkout -b feature/xxx
  # ... 编码 + 提交 ...
  git push -u origin feature/xxx
  # 创建 PR → CI 运行 → 自审 → 合并

修复发现的 bug：
  git checkout develop
  git checkout -b bugfix/fix-xxx
  # ... 修复 + 提交 ...
  git push -u origin bugfix/fix-xxx
  # 创建 PR → CI 运行 → 合并

下班前：
  git checkout develop && git pull origin develop
  # 确认 develop 状态正常
```

### 发布日

```
1. git checkout develop && git pull origin develop
2. 运行完整测试：./manage.sh test
3. 更新 changelog.md 版本条目
4. git commit -m "chore(release): prepare v3.2.0"
5. git checkout main && git pull origin main
6. git merge --no-ff develop
7. git tag -a v3.2.0 -m "release v3.2.0"
8. git push origin main --tags
9. 在 GitHub 创建 Release
10. git checkout develop && git merge main && git push origin develop
```

---

## 8. 常见问题

### Q: 单人开发有必要走 PR 流程吗？

**建议**：小改动直接在 develop 上提交，大改动走 PR。PR 的价值在于：
- 触发 CI 自动检查
- 代码自审（PR 页面查看 diff 更清晰）
- 保留变更上下文（PR description 记录 why）

### Q: hotfix 修复后忘记合并回 develop 怎么办？

```bash
git checkout develop
git merge main  # main 已包含 hotfix，合并过来即可
git push origin develop
```

### Q: feature 开发到一半需要紧急修 bug 怎么办？

```bash
# 暂存当前工作
git stash

# 切换去修 bug
git checkout develop
git checkout -b bugfix/fix-xxx
# ... 修复 + 合并 ...

# 回来继续开发
git checkout feature/xxx
git stash pop
```

### Q: 误提交到 main 怎么办？

```bash
# 如果还没 push
git reset --soft HEAD~1    # 撤销 commit，保留修改在暂存区
git checkout develop       # 切到 develop 重新提交

# 如果已经 push
git revert <commit-hash>   # 用 revert 撤销，保留历史
git push origin main
```

### Q: 如何查看两个版本之间的差异？

```bash
# 查看版本间变更文件
git diff v3.0.0..v3.1.0 --stat

# 查看版本间变更内容
git diff v3.0.0..v3.1.0

# 查看版本间 commit 日志
git log v3.0.0..v3.1.0 --oneline
```
