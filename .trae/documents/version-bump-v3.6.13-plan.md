# v3.6.13 版本升级计划（符合项目规范）

## 问题描述

用户反馈：
1. 上次任务的文档更新覆盖面不全
2. 代码提交计划应该指定新版本号 v3.6.13
3. 所有操作必须遵循当前项目规范

## 项目规范依据

参考文档：[git-workflow-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/git-workflow-guide.md)

### 版本号规范
- 采用语义化版本：**Major.Minor.Patch**
- Tag 命名：`v3.6.13`（v 前缀 + 三段式版本号）
- 本次变更为功能变更，Minor 版本递增（3.6.11 → 3.6.13）

### Commit 规范
- 采用 Conventional Commits 格式：`<type>(<scope>): <subject>`
- 版本升级使用 `chore(release)` 类型

### 分支策略
- develop：日常开发基线，完成后直接 push
- main：生产发布分支，通过 PR 合并，每次合并打 tag

## 版本号变更

当前版本：v3.6.11 → 目标版本：v3.6.13

## 需要更新的文件清单

### 1. 版本核心文件

| 文件 | 当前版本 | 目标版本 | 更新内容 |
|------|---------|---------|---------|
| [VERSION](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/VERSION) | 3.6.11 | 3.6.13 | 版本号 |
| [frontend/package.json](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/package.json) | 3.6.11 | 3.6.13 | version 字段 |
| [.env.example](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/.env.example) | 3.6.11 | 3.6.13 | VERSION 变量 |

### 2. 文档文件

| 文件 | 当前版本 | 目标版本 | 更新内容 |
|------|---------|---------|---------|
| [docs/changelog.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/changelog.md) | v3.6.9 | v3.6.13 | 添加 v3.6.13 变更记录，更新文档版本号 |
| [docs/release-notes.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/release-notes.md) | v3.6.11 | v3.6.13 | 添加 v3.6.13 发布记录，更新文档版本号 |
| [docs/user-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/user-guide.md) | v3.6.6 | v3.6.13 | 更新文档版本号和日期 |
| [docs/api.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/api.md) | v3.6.6 | v3.6.13 | 更新文档版本号和日期 |
| [docs/business-workflow.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/business-workflow.md) | v3.6.11 | v3.6.13 | 更新文档版本号和日期 |
| [docs/quick-start-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/quick-start-guide.md) | - | v3.6.13 | 检查并更新版本号 |
| [docs/architecture.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/architecture.md) | - | v3.6.13 | 检查并更新版本号 |
| [docs/backend.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/backend.md) | - | v3.6.13 | 检查并更新版本号 |
| [docs/git-workflow-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/git-workflow-guide.md) | v3.6.6 | v3.6.13 | 更新文档版本号和日期 |

### 3. 其他文件

| 文件 | 更新内容 |
|------|---------|
| [manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh) | 更新脚本头部的版本号显示 |

## 更新步骤

### 步骤1：更新版本核心文件

```bash
# VERSION 文件
echo "3.6.13" > VERSION

# frontend/package.json - 更新 version 字段
sed -i 's/"version": "3.6.11"/"version": "3.6.13"/' frontend/package.json

# .env.example - 更新 VERSION 变量
sed -i 's/VERSION=3.6.11/VERSION=3.6.13/' .env.example
```

### 步骤2：更新 manage.sh 版本号

查找 manage.sh 中的版本号字符串并替换。

### 步骤3：更新 changelog.md

在 `[Unreleased]` 上方添加 v3.6.13 的变更记录，并更新文档版本号：

```markdown
# 更新日志

> 文档版本：v3.6.13  更新日期：2026-07-14

## [3.6.13] - 2026-07-14

### 变更

- **移除手动封锁/解封功能**：系统核心业务逻辑闭环改为合规自动判断封锁和解封锁
  - 删除手动封锁 API 端点：`POST /terminals/block/{ip_address}`
  - 删除手动解封 API 端点：`POST /terminals/unblock/{ip_address}`
  - 删除黑名单手动添加端点：`POST /blacklist/`
  - 删除黑名单手动删除端点：`DELETE /blacklist/{identifier}`
  - 删除后端服务方法：`block_ip`, `unblock_ip`, `add_to_blacklist`, `delete_from_blacklist`

- **终端管理优化**：
  - 合规终端（compliant）无任何操作按钮
  - 白名单终端（bypass）无移出白名单操作，移除动作集中在白名单管理中
  - 仅不合规（non_compliant）和未知（unknown）终端保留加白操作

- **黑名单管理优化**：
  - 移除解封按钮和删除确认模态框
  - 移除状态标签页（Active/Unblocked），只显示当前被封锁的记录
  - 封锁和解封的追溯通过完整的审计日志查询

### 文档更新

- 更新业务工作流文档，移除手动封锁/解封流程章节
- 更新 API 文档，移除已删除的 API 端点
- 更新用户操作手册版本号
```

### 步骤4：更新 release-notes.md

添加 v3.6.13 的发布记录，并更新文档版本号。

### 步骤5：更新其他文档版本号

更新所有文档头部的版本号和日期。

## 代码提交计划（遵循 Conventional Commits 规范）

### 提交步骤

```bash
# 1. 添加所有修改的文件
git add VERSION frontend/package.json .env.example manage.sh docs/*

# 2. 提交（遵循 Conventional Commits 规范）
git commit -m "chore(release): bump version to v3.6.13"

# 3. 推送到 develop 分支
git push origin develop
```

### Commit Message 说明

| 部分 | 值 | 说明 |
|------|-----|------|
| type | `chore` | 构建/工具/版本变更，不影响业务逻辑 |
| scope | `release` | 范围为版本发布 |
| subject | `bump version to v3.6.13` | 简短描述 |

## 版本发布计划（遵循 Git Flow 规范）

当准备正式发布时：

```bash
# 1. 切换到 main 分支
git checkout main
git pull origin main

# 2. 合并 develop 到 main
git merge --no-ff develop

# 3. 打 tag（遵循语义化版本规范）
git tag -a v3.6.13 -m "release v3.6.13"

# 4. 推送 main 和 tag
git push origin main --tags

# 5. 同步 develop
git checkout develop
git merge main
git push origin develop
```

## 风险处理

- **前端构建**：vite.config.ts 会自动从 VERSION 文件读取版本号，版本号变更不影响前端构建
- **后端运行**：版本号变更仅影响显示，不影响业务逻辑
- **数据库**：无需数据库迁移
- **Git Flow**：当前开发在 develop 分支，后续合并到 main 时再打 tag，符合项目规范

## 验证步骤

完成更新后，验证以下内容：

1. 版本号一致性：所有文件中的版本号均为 3.6.13
2. 前端构建：`./manage.sh -y update` 构建成功
3. 服务状态：`./manage.sh status` 所有服务正常
4. 文档链接：所有文档版本号更新正确，链接有效
