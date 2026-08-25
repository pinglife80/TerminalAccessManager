# 防火墙黑名单数据一致性修复 - 审核与提交计划

> 创建日期：2026-07-16
> 当前版本：v3.6.14 → 目标版本：v3.6.15 (Patch)

***

## 一、代码变更审核

### 1.1 变更概览

本次共修改 3 个文件，+31 行 / -8 行：

| 文件                                                        | 变更类型      | 说明                                            |
| --------------------------------------------------------- | --------- | --------------------------------------------- |
| `backend/app/services/terminal_service.py`                | fix + fix | 添加 `decrypt_config` 导入；3 个方法添加过期时间过滤          |
| `backend/app/services/firewall_reconciliation_service.py` | fix       | 对账查询添加过期时间过滤；创建记录 `is_auto_blocked` 改为 `True` |
| `backend/cli.py`                                          | fix       | 修复防火墙查询结果解析逻辑                                 |

### 1.2 变更详情

#### 文件1: `backend/app/services/terminal_service.py`

**变更A - 添加缺失的导入**（第22行）

* 添加 `from app.core.crypto import decrypt_config`

* 原因：`_get_sangfor_service_by_tag` 方法调用 `decrypt_config` 但未导入，导致 `NameError`

**变更B -** **`get_blacklist`** **方法**（第757-769行）

* 添加 `expires_at` 过滤条件：`or_(expires_at >= now, expires_at.is_(None))`

* 原因：原查询未过滤过期记录，导致黑名单管理页面显示数量偏多

**变更C -** **`get_blacklist_count`** **方法**（第818-830行）

* 同上，添加 `expires_at` 过滤条件

* 原因：统计数量与 `get_blacklist` 保持一致

**变更D -** **`get_blacklist_stats`** **方法**（第872-879行）

* 同上，添加 `expires_at` 过滤条件

* 原因：Dashboard 统计与黑名单管理保持一致

#### 文件2: `backend/app/services/firewall_reconciliation_service.py`

**变更A -** **`_get_db_active_blacklist`** **方法**（第144-159行）

* 添加 `expires_at` 过滤条件

* 原因：对账时只比较未过期记录，避免将过期记录误判为"防火墙有但数据库无"

**变更B -** **`_create_db_entries`** **方法**（第199行）

* `is_auto_blocked=False` → `is_auto_blocked=True`

* 原因：对账服务自动创建的记录应标记为自动封锁，而非手动封锁

#### 文件3: `backend/cli.py`

**变更 - firewall\_query 结果解析**（第1674行）

* `len(result.get("data", []))` → `len(result.get("data", {}).get("items", []))`

* 原因：防火墙 API 返回格式为 `{"data": {"items": [...]}}`，原代码将 `data` 当作列表处理，导致显示数量错误

### 1.3 审核结论

* 所有变更均为 bug 修复，无新功能添加

* 变更逻辑正确，过滤条件与 `check_blacklist` 方法保持一致

* 无破坏性变更，向后兼容

* 符合 Patch 版本升级标准

***

## 二、文档更新

### 2.1 需要更新的文档

| 文档                           | 更新内容                          |
| ---------------------------- | ----------------------------- |
| `VERSION`                    | `3.6.14` → `3.6.15`           |
| `docs/changelog.md`          | 添加 `[3.6.15]` 条目，记录黑名单数据一致性修复 |
| `docs/release-notes.md`      | 添加 `[v3.6.15]` 发布记录           |
| `docs/git-workflow-guide.md` | 文档版本号 `v3.6.14` → `v3.6.15`   |
| `docs/changelog.md`（头部）      | 文档版本号 `v3.6.14` → `v3.6.15`   |
| `docs/release-notes.md`（头部）  | 文档版本号 `v3.6.14` → `v3.6.15`   |

### 2.2 changelog.md 新增内容

在 `## [3.6.14]` 条目之前添加 `## [3.6.15] - 2026-07-16` 条目：

```markdown
## [3.6.15] - 2026-07-16

### 修复

- **黑名单数据一致性修复**：修复黑名单管理页面与防火墙、Dashboard、终端管理统计数量不一致问题
  - `get_blacklist`、`get_blacklist_count`、`get_blacklist_stats` 方法添加过期时间过滤
  - 原因：黑名单管理页面未过滤已过期记录，导致显示数量偏多
  - 关联文件：`backend/app/services/terminal_service.py`

- **防火墙对账记录类型修复**：修复对账服务创建的记录被错误标记为手动封锁
  - `_create_db_entries` 方法中 `is_auto_blocked` 从 `False` 改为 `True`
  - `_get_db_active_blacklist` 方法添加过期时间过滤
  - 关联文件：`backend/app/services/firewall_reconciliation_service.py`

- **防火墙查询导入修复**：修复 `terminal_service.py` 中 `decrypt_config` 未导入导致的 NameError
  - 关联文件：`backend/app/services/terminal_service.py`

- **防火墙查询结果解析修复**：修复 `cli.py` 中防火墙查询结果解析逻辑
  - 原代码 `result.get("data", [])` 修正为 `result.get("data", {}).get("items", [])`
  - 关联文件：`backend/cli.py`

### 文档更新

- 更新 changelog.md 添加 v3.6.15 变更记录
- 更新 release-notes.md 添加 v3.6.15 发布记录
- 统一所有文档版本号至 v3.6.15
```

### 2.3 release-notes.md 新增内容

在 `## [v3.6.14]` 之前添加 `## [v3.6.15]` 发布记录。

***

## 三、代码提交推送计划

### 3.1 分支策略

根据 [git-workflow-guide.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/git-workflow-guide.md) 的规范：

* 本次为 **bugfix**（3个文件，≤5个文件）

* 适用"单人开发简化模式"，可直接在 develop 分支提交

* 无需创建临时分支和 PR

### 3.2 版本号

* 当前：v3.6.14

* 目标：**v3.6.15** (Patch - Bug 修复)

### 3.3 提交步骤

**步骤1：更新 VERSION 文件**

```bash
# VERSION 文件内容改为 3.6.15
```

**步骤2：更新文档**

* 更新 `docs/changelog.md`：添加 v3.6.15 条目 + 头部版本号

* 更新 `docs/release-notes.md`：添加 v3.6.15 发布记录 + 头部版本号

* 更新 `docs/git-workflow-guide.md`：头部版本号

**步骤3：暂存并提交**

```bash
git add backend/app/services/terminal_service.py
git add backend/app/services/firewall_reconciliation_service.py
git add backend/cli.py
git add VERSION
git add docs/changelog.md
git add docs/release-notes.md
git add docs/git-workflow-guide.md

git commit -m "fix(blacklist): 修复黑名单数据一致性问题

- 黑名单管理页面添加过期时间过滤，与终端管理/Dashboard保持一致
- 防火墙对账服务 is_auto_blocked 修正为 True
- 修复 terminal_service.py 中 decrypt_config 未导入问题
- 修复 cli.py 防火墙查询结果解析逻辑

Bump version to v3.6.15"
```

**步骤4：推送到远程**

```bash
git push origin develop
```

**步骤5：发布版本（打 tag）**

```bash
# 从 develop 创建 release tag
git checkout main
git pull origin main
git merge --no-ff develop
git tag -a v3.6.15 -m "release v3.6.15: fix blacklist data consistency"

git push origin main --tags

# 同步 develop
git checkout develop
git merge main
git push origin develop
```

### 3.4 提交信息规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范：

* Type: `fix`（Bug 修复）

* Scope: `blacklist`（黑名单模块）

* Subject: `修复黑名单数据一致性问题`

* Body: 详细说明4个修复点

***

## 四、验证清单

* [ ] VERSION 文件更新为 3.6.15

* [ ] changelog.md 添加 v3.6.15 条目

* [ ] release-notes.md 添加 v3.6.15 发布记录

* [ ] 文档版本号统一更新为 v3.6.15

* [ ] 代码提交到 develop 分支

* [ ] 推送到远程 origin/develop

* [ ] 合并到 main 并打 tag v3.6.15

* [ ] 推送 main 和 tags 到远程

