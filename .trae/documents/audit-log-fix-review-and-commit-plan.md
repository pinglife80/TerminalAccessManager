# 审计日志修复审核与代码提交发布计划

> 计划版本：v1.1 | 更新日期：2026-07-16
> 适用版本：v3.6.17
> 提交方案：方案 B（PR 流程）
> 发布范围：develop → main → tag v3.6.17

***

## 一、代码变更审核

### 1.1 变更文件总览

当前在 `develop` 分支上，共修改 8 个文件，新增 182 行，删除 83 行：

| 文件                                              | 变更类型 | 说明                                 |
| ----------------------------------------------- | ---- | ---------------------------------- |
| `VERSION`                                       | 修改   | 版本号 3.6.16 → 3.6.17                |
| `backend/app/services/arp_collector_service.py` | 修改   | 核心修复：移除已存在终端 compliance\_status 重置 |
| `frontend/src/pages/AuditLogs.tsx`              | 修改   | 前端筛选与展示全面优化                        |
| `frontend/src/i18n/locales/zh.ts`               | 修改   | 中文翻译补全                             |
| `frontend/src/i18n/locales/en.ts`               | 修改   | 英文翻译补全                             |
| `frontend/src/i18n/locales/ja.ts`               | 修改   | 日文翻译补全                             |
| `frontend/package.json`                         | 修改   | 版本号 3.6.16 → 3.6.17                |
| `docs/release-notes.md`                         | 修改   | 添加 v3.6.17 发布记录                    |

### 1.2 系统版本号更新确认

通过 `./manage.sh version bump 3.6.17` 已自动更新以下所有版本号文件：

| 文件                           | 版本位置              | 状态    | 是否提交到 git     |
| ---------------------------- | ----------------- | ----- | ------------- |
| `VERSION`                    | 项目根目录版本文件         | ✅ 已更新 | 是             |
| `frontend/package.json`      | version 字段        | ✅ 已更新 | 是             |
| `.env`                       | APP\_VERSION 环境变量 | ✅ 已更新 | 否（.gitignore） |
| `.env.example`               | APP\_VERSION 环境变量 | ✅ 已更新 | 是             |
| `docker-compose.yml`         | VERSION build arg | ✅ 已更新 | 是             |
| `manage.sh`                  | 内置 VERSION 变量     | ✅ 已更新 | 是             |
| `frontend/vite.config.ts`    | define 中的版本号      | ✅ 已更新 | 是             |
| `backend/app/core/config.py` | 运行时从 VERSION 文件读取 | 动态读取  | 代码未变          |

**版本号一致性验证**：

```bash
./manage.sh version check
```

### 1.3 核心修复审核

#### 后端修复：arp\_collector\_service.py

**变更内容**：在 `_upsert_terminals` 方法的 `if existing:` 分支中，移除了 `existing.compliance_status = "unknown"` 和 `existing.wl_match_type = None` 两行。

**审核结论**：✅ 正确

* **根因准确**：ARP 采集每次更新终端时重置 compliance\_status 为 unknown，导致合规检查认为状态发生变化，产生大量无意义日志

* **修复恰当**：只移除了有问题的重置逻辑，保留了 `updated_at`、`source_tag`、`source` 等必要字段更新

* **影响可控**：

  * 新终端仍然会以 unknown 状态创建（正确行为）

  * 已存在终端的合规状态将保持原样（修复目标）

  * 合规检查会自动处理 unknown 状态的新终端

**验证数据**：

* 修复前：132,394 条审计日志，其中 131,398 条为 unknown→xxx 的无效变更

* 修复后：996 条审计日志，其中 456 条为真实合规状态变更

* 终端状态分布：bypass 510、compliant 312、non\_compliant 147，**无 unknown 状态**

#### 前端修复：AuditLogs.tsx

**变更内容**：

1. `actionLabelKeys`：重写全部 action 映射，与后端完全对齐，新增向后兼容的旧 action 名称映射
2. `ACTION_CATEGORIES`：新增 firewall（防火墙）和 baseline（合规基线）分类
3. `ACTION_CATEGORY_MAP`：重写分类映射，所有 24 种 action 均有正确分类
4. `CATEGORY_BADGE_STYLES`：新增各分类徽章样式

**审核结论**：✅ 正确

* Action 值全部为 snake\_case 格式，命名模式统一为 `<noun>_<verb>`

* 前端 action 值与后端数据库实际值一一对应

* 包含向后兼容映射（block\_ip→firewall\_block、add\_whitelist→whitelist\_create 等）

* 分类体系完整：auth / compliance / firewall / whitelist / blacklist / datasource / user / role / baseline / system

#### i18n 翻译

**审核结论**：✅ 正确

* 三语言（zh/en/ja）同步更新，翻译键完整

* 新增分类标签、动作标签、资源类型翻译

* 与现有翻译风格一致

### 1.4 待补充的文档更新

根据项目规范，以下文档需要同步更新后再提交：

| 文档                           | 当前版本        | 目标版本    | 需要更新内容          |
| ---------------------------- | ----------- | ------- | --------------- |
| `docs/changelog.md`          | v3.6.16     | v3.6.17 | 添加 v3.6.17 变更条目 |
| `docs/git-workflow-guide.md` | v3.6.16     | v3.6.17 | 文档版本号更新         |
| `docs/release-plan.md`       | v3.6.14     | v3.6.17 | 文档版本号更新         |
| `docs/architecture.md`       | -           | v3.6.17 | 文档版本号更新         |
| 其他所有 docs/ 下文档               | v3.6.16 或更低 | v3.6.17 | 统一版本号           |

**changelog.md 需要补充的内容**：

* 修复：审计日志爆炸增长（ARP采集重置compliance\_status）

* 修复：审计日志筛选下拉菜单与实际结果不匹配

* 优化：审计日志 action 命名格式统一（snake\_case）

* 文档：更新发布记录

***

## 二、代码提交方案（方案 B：PR 流程）

### 2.1 提交流程总览

```
develop (当前)
   │
   ├─ 步骤1：补充文档更新（changelog + 所有文档版本号）
   │
   ├─ 步骤2：创建 bugfix 分支
   │   bugfix/audit-log-fixes
   │
   ├─ 步骤3：提交代码
   │
   ├─ 步骤4：推送分支 + 创建 PR
   │   PR: bugfix/audit-log-fixes → develop
   │
   ├─ 步骤5：合并 PR 到 develop
   │
   └─ 步骤6：清理分支
       develop ← 合并结果
```

### 2.2 详细步骤

#### 步骤 1：补充文档更新

```bash
# 更新 changelog.md - 添加 v3.6.17 条目
# （手动编辑 docs/changelog.md，在最前面添加 [3.6.17] 条目）

# 统一所有 docs/ 文档版本号为 v3.6.17
# （更新各文档头部的文档版本号和日期）
```

#### 步骤 2：创建 bugfix 分支

```bash
# 确保当前在 develop 分支且工作区干净
git status
git checkout develop
git pull origin develop

# 创建 bugfix 分支
git checkout -b bugfix/audit-log-fixes
```

#### 步骤 3：提交代码

```bash
# 确认变更文件
git diff --stat

# 添加所有变更文件
git add VERSION
git add .env.example docker-compose.yml manage.sh
git add backend/app/services/arp_collector_service.py
git add frontend/package.json frontend/vite.config.ts
git add frontend/src/pages/AuditLogs.tsx
git add frontend/src/i18n/locales/zh.ts
git add frontend/src/i18n/locales/en.ts
git add frontend/src/i18n/locales/ja.ts
git add docs/release-notes.md
git add docs/changelog.md
git add docs/git-workflow-guide.md
# ... 其他更新了版本号的文档

# 提交（Conventional Commits 格式）
git commit -m "fix(audit): 修复审计日志爆炸增长、筛选不匹配和action格式不一致

- 修复ARP采集服务重置终端compliance_status导致日志爆炸问题
- 统一审计日志action命名为snake_case格式，前后端一致
- 前端筛选下拉菜单新增防火墙、合规基线分类
- i18n三语言翻译补全
- 版本号升级至 v3.6.17"
```

#### 步骤 4：推送分支

```bash
git push -u origin bugfix/audit-log-fixes
```

#### 步骤 5：创建 Pull Request

在 GitHub 上创建 PR：`bugfix/audit-log-fixes` → `develop`

**PR Title**：

```
fix(audit): 修复审计日志爆炸增长、筛选不匹配和action格式不一致
```

**PR Description**（参考模板）：

```
## 问题描述

1. 审计日志爆炸增长（13万条/天），99.7% 是无效的合规状态变更日志
2. 筛选下拉菜单选项与实际日志数据不匹配
3. Action 字段命名格式不统一

## 根因分析

ARP 采集服务在更新已存在终端时，强制将 compliance_status 重置为 "unknown"，
导致每次采集后合规检查都触发状态变更日志，形成循环。

## 修复内容

### 后端
- 移除 arp_collector_service.py 中已存在终端的 compliance_status 和 wl_match_type 重置

### 前端
- 重写 ACTION_CATEGORIES、actionLabelKeys、ACTION_CATEGORY_MAP
- 新增 firewall、baseline 分类
- 添加旧 action 名称向后兼容映射

### i18n
- 三语言翻译补全

### 数据清理
- 删除 131,398 条无效审计日志（old_compliance='unknown'）
- 日志总量从 132,394 降至 996，减少 99.2%

## 验证

- 终端状态分布：bypass 510、compliant 312、non_compliant 147，无 unknown 状态
- 所有 24 种 action 值均为 snake_case 格式，前后端一致
- 构建成功，服务健康运行
```

#### 步骤 6：合并 PR

CI 通过后，在 GitHub 上合并 PR。建议使用 **Create a merge commit**（保留完整提交历史）。

#### 步骤 7：清理分支

```bash
# 切回 develop
git checkout develop

# 拉取最新代码
git pull origin develop

# 删除本地 bugfix 分支
git branch -d bugfix/audit-log-fixes

# 删除远程 bugfix 分支
git push origin --delete bugfix/audit-log-fixes
```

***

## 三、发布到 main 并打 tag

### 3.1 发布流程总览

```
develop (已合并 PR)
   │
   ├─ 步骤1：切换到 main 并拉取最新
   │
   ├─ 步骤2：合并 develop 到 main
   │
   ├─ 步骤3：打 tag v3.6.17
   │
   ├─ 步骤4：推送 main + tags
   │
   ├─ 步骤5：同步回 develop
   │
   └─ 步骤6：GitHub 创建 Release
```

### 3.2 详细步骤

#### 步骤 1：准备 main 分支

```bash
# 切换到 main
git checkout main

# 拉取最新
git pull origin main
```

#### 步骤 2：合并 develop 到 main

```bash
# 使用 --no-ff 保留 merge commit，方便追溯
git merge --no-ff develop

# 如遇冲突，解决后：
# git add <resolved-files>
# git commit
```

#### 步骤 3：打 tag

```bash
# 创建 annotated tag（带说明的标签，推荐）
git tag -a v3.6.17 -m "release v3.6.17: 审计日志系统修复与优化

- 修复ARP采集服务重置终端compliance_status导致日志爆炸问题
- 统一审计日志action命名为snake_case格式
- 前端筛选下拉菜单新增防火墙、合规基线分类
- i18n三语言翻译补全
- 版本号 v3.6.17"
```

#### 步骤 4：推送 main 和 tag

```bash
# 推送 main 分支
git push origin main

# 推送 tag
git push origin v3.6.17

# 或一次性推送所有 tags
# git push origin --tags
```

#### 步骤 5：同步回 develop

```bash
# 切回 develop
git checkout develop

# 合并 main（确保 develop 包含 tag 信息）
git merge main

# 推送
git push origin develop
```

#### 步骤 6：在 GitHub 创建 Release

1. 进入 GitHub 仓库 → Releases → Draft a new release
2. **Choose a tag**：选择 `v3.6.17`
3. **Release title**：`v3.6.17`
4. **Write**：从 `docs/changelog.md` 复制 v3.6.17 的内容
5. （可选）勾选 **Set as the latest release**
6. 点击 **Publish release**

***

## 四、完整执行清单

### 阶段一：文档补充（提交前）

* [ ] 更新 `docs/changelog.md`，添加 v3.6.17 条目

* [ ] 统一所有 docs/ 文档版本号为 v3.6.17

* [ ] `./manage.sh version check` 确认版本号一致

### 阶段二：PR 提交流程

* [ ] 确认 develop 分支代码正确

* [ ] `git checkout -b bugfix/audit-log-fixes` 创建 bugfix 分支

* [ ] `git add` 所有变更文件

* [ ] `git commit` 按规范提交

* [ ] `git push -u origin bugfix/audit-log-fixes` 推送分支

* [ ] 在 GitHub 创建 PR：bugfix/audit-log-fixes → develop

* [ ] 等待 CI 通过

* [ ] 在 GitHub 合并 PR

* [ ] `git checkout develop && git pull` 拉取最新

* [ ] `git branch -d bugfix/audit-log-fixes` 删除本地分支

* [ ] `git push origin --delete bugfix/audit-log-fixes` 删除远程分支

### 阶段三：发布到 main 并打 tag

* [ ] `git checkout main && git pull origin main`

* [ ] `git merge --no-ff develop` 合并到 main

* [ ] `git tag -a v3.6.17 -m "release v3.6.17: ..."` 打 tag

* [ ] `git push origin main` 推送 main

* [ ] `git push origin v3.6.17` 推送 tag

* [ ] `git checkout develop && git merge main && git push` 同步回 develop

* [ ] 在 GitHub 创建 Release

### 阶段四：验证

* [ ] 确认 main 分支 CI 通过（如有）

* [ ] `./manage.sh health` 确认服务健康

* [ ] `git log --oneline -10` 确认提交历史正确

* [ ] `git tag -l` 确认 tag 存在

***

## 五、风险与注意事项

1. **数据清理操作**：已执行的历史日志清理（DELETE 131,398 条）是数据库操作，不包含在 git 提交中。这是预期行为，因为数据清理是运维操作而非代码变更。

2. **版本号文件**：`.env` 文件在 `.gitignore` 中不会被提交，但 `.env.example` 会提交，确保示例文件版本号正确。

3. **向后兼容**：前端添加了旧 action 名称的向后兼容映射（block\_ip、add\_whitelist 等），确保历史日志仍能正确显示和筛选。

4. **禁止 force push**：main 和 develop 分支禁止 `--force` 推送。

5. **提交前自检命令**：

   ```bash
   ./manage.sh version check    # 确认版本号一致
   ./manage.sh health           # 确认服务健康
   git diff --stat              # 确认变更文件符合预期
   git diff --check             # 检查空白错误
   ```

