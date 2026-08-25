# v3.6.13 版本打 Tag 及同步 Main 分支执行方案

## 项目规范依据

参考文档：[git-workflow-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/git-workflow-guide.md)

### Git Flow 发布规范

```bash
# 标准发布流程（文档第160-175行）
git checkout main
git pull origin main
git merge --no-ff develop
git tag -a v3.6.13 -m "release v3.6.13"
git push origin main --tags

# 同步 develop
git checkout develop
git merge main
git push origin develop
```

### 分支策略

| 分支 | 用途 | 保护规则 |
|------|------|---------|
| main | 生产发布，始终可部署 | 禁止 force push，禁止删除，PR 合并前 CI 通过 |
| develop | 开发集成分支 | 禁止 force push，禁止删除 |

## 当前状态

- **PR 状态**：已 merge 完成
- **当前分支**：develop
- **最新提交**：`2a0d6d1 chore(release): bump version to v3.6.13`
- **目标版本**：v3.6.13

## 执行步骤

### 步骤1：切换到 main 分支并拉取最新代码

```bash
git checkout main
git pull origin main
```

### 步骤2：合并 develop 到 main（使用 --no-ff）

```bash
git merge --no-ff develop
```

> **原因**：`--no-ff` 保留分支历史，便于后续回滚和版本追溯

### 步骤3：打 Tag（遵循语义化版本规范）

```bash
git tag -a v3.6.13 -m "release v3.6.13"
```

> **Tag 命名规范**：`v` 前缀 + 三段式版本号（v3.6.13）

### 步骤4：推送 main 分支和 Tag

```bash
git push origin main --tags
```

### 步骤5：同步 develop 分支

```bash
git checkout develop
git merge main
git push origin develop
```

> **原因**：确保 develop 包含最新的 tag 信息，保持分支同步

## 验证步骤

完成后验证以下内容：

1. **分支状态**：main 和 develop 分支指向同一提交
2. **Tag 验证**：`git tag -l` 显示 v3.6.13
3. **远程验证**：`git ls-remote --tags origin` 显示 v3.6.13
4. **GitHub Release**：在 GitHub 上创建 Release（可选）

## 风险处理

| 风险 | 处理方式 |
|------|---------|
| 合并冲突 | 解决冲突后重新合并，确保代码一致性 |
| 推送失败 | 检查分支保护规则，确保有推送权限 |
| Tag 重复 | 使用 `git tag -d v3.6.13` 删除本地 tag，`git push origin :v3.6.13` 删除远程 tag，重新打 tag |

## 后续操作（可选）

在 GitHub 上创建 Release：

1. 进入仓库 → Releases → Draft a new release
2. 选择 tag：v3.6.13
3. 填写 Release title：v3.6.13
4. 填写 Release notes（从 changelog.md 复制对应版本内容）
