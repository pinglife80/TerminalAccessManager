# 黑名单 Bug 修复 + Patch 发布完整方案（v3.3.1）

> 文档版本：v3.3.1-hotfix | 更新日期：2026-06-17

---

## 一、当前项目状态

| 项目 | 状态 |
|------|------|
| 当前版本 | **v3.3.0**（已发布，tag 已创建） |
| main 分支 | `72dfa80`，与 develop 同步，指向 v3.3.0 tag |
| develop 分支 | `72dfa80`，与 main 同步 |
| 最新 Tag | `v3.3.0` |
| CI 配置 | push/PR 到 main 和 develop 均触发 6 个 job |

**结论**：v3.3.0 刚完成发布，main 和 develop 完全同步。本次修复是生产环境的 bugfix，应走 **Patch Release** 流程。

---

## 二、版本号决策

| 方案 | 版本号 | 适用场景 | 选择 |
|------|--------|---------|------|
| Hotfix/Patch | **v3.3.1** | 生产环境 bug 修复，向后兼容 | ✅ 采用 |
| Minor | v3.4.0 | 新功能 | 不适用 |
| Major | v4.0.0 | 破坏性变更 | 不适用 |

**语义化版本规则**：`MAJOR.MINOR.PATCH`
- v3.**3**.0 → v3.3.**1**（PATCH 递增，修复 bug）

---

## 三、Git 分支管理策略（GitFlow 标准）

### 3.1 分支拓扑

```
main (v3.3.0) ──────────────────────┬──→ main (v3.3.1) [PR merge]
                                      │
develop (v3.3.0) ────────────────────┼──→ develop (sync from main)
                                      │
                    hotfix/v3.3.1 ←──┘
                    (从 main 创建)
```

### 3.2 标准流程

```
Step 1: 从 main 创建 hotfix 分支
        git checkout main && git pull origin main
        git checkout -b hotfix/v3.3.1

Step 2: 在 hotfix 分支上修复代码
        （修改 5 个文件，见下方"修改清单"）

Step 3: 更新版本号为 v3.3.1
        manage.sh VERSION: "3.3.0" → "3.3.1"
        backend/app/core/config.py VERSION: "3.3.0" → "3.3.1"
        frontend/package.json version: "3.3.0" → "3.3.1"

Step 4: 提交并推送 hotfix 分支
        git commit -m "fix(blacklist): filter out auto-unblocked records from default list view"
        git push -u origin hotfix/v3.3.1

Step 5: 创建 PR: hotfix/v3.3.1 → main
        标题: "[Hotfix] Fix blacklist showing unblocked records"
        描述: 包含问题描述、根因、修改文件、影响评估

Step 6: CI 验证（6 个 job 全部通过）

Step 7: Merge PR 到 main（Merge commit）

Step 8: 打 tag v3.3.1 并推送
        git checkout main && git pull origin main
        git tag -a v3.3.1 -m "hotfix v3.3.1: blacklist filter fix"
        git push origin v3.3.1

Step 9: 创建 GitHub Release v3.3.1

Step 10: 同步到 develop
         git checkout develop && git pull origin develop
         git merge main
         git push origin develop
```

---

## 四、代码修改清单

### 4.1 后端修改（3 个文件）

#### 文件 1: `backend/app/services/terminal_service.py`

**`get_blacklist()` 方法（第 856 行）**：
- 添加过滤条件：默认排除 `auto_unblocked=True` 的记录
- 支持 `status` 参数筛选（active/unblocked/all）

```python
# 在 conditions 构建逻辑中添加：
if query and query.status:
    if query.status == 'active':
        conditions.append(Blacklist.auto_unblocked == False)
    elif query.status == 'unblocked':
        conditions.append(Blacklist.auto_unblocked == True)
else:
    # 默认只显示活跃封堵记录
    conditions.append(Blacklist.auto_unblocked == False)
```

**`get_blacklist_count()` 方法（第 892 行）**：同上同步修改。

#### 文件 2: `backend/app/schemas/terminal.py`

**`BlacklistQuery` 类（第 119 行）**：
```python
class BlacklistQuery(BaseModel):
    search: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = None  # active / unblocked / all
    skip: int = 0
    limit: int = 50
```

#### 文件 3: `backend/app/api/v1/endpoints/blacklist.py`

**`get_blacklist()` endpoint（第 14 行）**：
```python
async def get_blacklist(
    search: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    status: str = Query(None, description="Filter: active/unblocked/all"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    ...
):
```

### 4.2 前端修改（4 个文件）

#### 文件 4: `frontend/src/hooks/useTerminalData.ts`

- `BlacklistSearchParams` 接口添加 `status?: string`
- `useBlacklist` hook 传递 status 参数

#### 文件 5: `frontend/src/pages/Blacklist.tsx`

- 添加 Tab 切换组件（活跃封堵 / 已解封 / 全部）
- 统计卡片根据 Tab 动态调整
- 已解封记录行样式区分（降低透明度）
- 已解封记录隐藏"解封"按钮
- Tab 状态传递给 API 参数

#### 文件 6: `frontend/src/i18n/locales/zh.json` & `en.json`

添加翻译键：
- `blacklist.activeTab`: "活跃封堵" / "Active"
- `blacklist.unblockedTab`: "已解封" / "Unblocked"
- `blacklist.allTab`: "全部" / "All"
- `blacklist.unblockedRecords`: "已解封记录" / "Unblocked Records"

---

## 五、版本号更新位置

### 5.1 必须更新的位置（3 处）

这些是**代码中实际使用**的版本号，影响运行时行为和构建产物：

| # | 文件 | 行号 | 字段 | 当前值 | 目标值 | 用途 |
|---|------|------|------|--------|--------|------|
| 1 | `manage.sh` | 74 | `VERSION="3.3.0"` | 3.3.0 | **3.3.1** | 部署脚本版本标识、`manage.sh version` 输出、升级版本校验 |
| 2 | `backend/app/core/config.py` | 11 | `VERSION: str = "3.3.0"` | 3.3.0 | **3.3.1** | 后端 `/health` 和 `/api/v1/settings` 返回的版本号 |
| 3 | `frontend/package.json` | 4 | `"version": "3.3.0"` | 3.3.0 | **3.3.1** | 前端构建产物版本、`npm version` 输出 |

### 5.2 建议更新的位置（1 处）

| # | 文件 | 行号 | 字段 | 当前值 | 目标值 | 用途 |
|---|------|------|------|--------|--------|------|
| 4 | `.env.example` | 14 | `VERSION=3.3.0` | 3.3.0 | **3.3.1** | 环境变量模板参考值（不影响运行时，仅文档性质） |

### 5.3 不需要更新的位置（文档类）

以下文件包含 `v3.3.0` 但属于**已发布的文档快照**，Patch 版本不修改文档版本号（符合项目约定：文档版本跟随 Minor/Major 版本）：

| 文件 | 说明 | 不更新原因 |
|------|------|-----------|
| `docs/changelog.md` | 变更日志 | 仅需**追加** [3.3.1] 条目，不修改已有 [3.3.0] 版本号 |
| `docs/release-notes.md` | 发布说明 | 仅需**追加** [v3.3.1] 条目 |
| `docs/*.md`（15 个文档） | 各类技术文档 | Patch 不涉及文档版本更新 |
| `frontend/docs/implementation.md` | 前端实现文档 | 同上 |

### 5.4 changelog.md 追加内容

在 `[3.3.0]` 条目之前插入：

```markdown
## [3.3.1] - 2026-06-17

### Fixed
- 黑名单管理页面默认不再显示已自动解封的历史记录
- 后端 `GET /blacklist/` 查询默认过滤 `auto_unblocked=True` 的记录
- 新增 `status` 查询参数支持查看已解封记录（active/unblocked/all）
- 前端黑名单页面添加 Tab 切换（活跃封堵/已解封/全部）
```

### 5.5 release-notes.md 追加内容

在 `[v3.3.0]` 条目之前插入：

```markdown
## [v3.3.1] - 2026-06-17

### Bug 修复

- **黑名单显示已解封记录**：黑名单管理页面默认查询不再返回 `auto_unblocked=True` 的历史记录，仅展示当前仍被封堵的活跃记录。新增 `status` 查询参数和前端 Tab 切换支持查看已解封历史记录。

### 变更文件

- `backend/app/services/terminal_service.py` — get_blacklist/get_blacklist_count 添加 auto_unblocked 过滤
- `backend/app/schemas/terminal.py` — BlacklistQuery 添加 status 字段
- `backend/app/api/v1/endpoints/blacklist.py` — get_blacklist endpoint 添加 status 参数
- `frontend/src/hooks/useTerminalData.ts` — BlacklistSearchParams 添加 status 字段
- `frontend/src/pages/Blacklist.tsx` — 添加 Tab 切换、已解封记录样式区分
- `frontend/src/i18n/locales/zh.json` — 添加中文翻译键
- `frontend/src/i18n/locales/en.json` — 添加英文翻译键
- `manage.sh` — VERSION 3.3.0 → 3.3.1
- `backend/app/core/config.py` — VERSION 3.3.0 → 3.3.1
- `frontend/package.json` — version 3.3.0 → 3.3.1
- `.env.example` — VERSION 3.3.0 → 3.3.1
- `docs/changelog.md` — 追加 [3.3.1] 条目
- `docs/release-notes.md` — 追加 [v3.3.1] 条目
```

---

## 六、CI/CD 影响

| 触发条件 | 自动运行 |
|----------|---------|
| push `hotfix/v3.3.1` | ❌ 不触发（CI 只监听 main/develop） |
| 创建 PR `hotfix/v3.3.1 → main` | ✅ 触发 6 个 CI job |
| Merge PR 到 main | ✅ 触发 6 个 CI job |
| 同步 develop 后 push | ✅ 触发 6 个 CI job |

---

## 七、验证检查清单

- [ ] 后端 `get_blacklist` 默认不返回 `auto_unblocked=True` 的记录
- [ ] 后端 `?status=unblocked` 返回已解封记录
- [ ] 后端 `?status=all` 或不传 status 时行为符合预期
- [ ] 前端默认显示"活跃封堵" Tab，无已解封记录
- [ ] 前端切换到"已解封" Tab 能看到历史记录
- [ ] 已解封记录不显示"解封"按钮
- [ ] 统计卡片数值与 Tab 一致
- [ ] 搜索和日期筛选在各 Tab 下正常工作
- [ ] CSV 导出包含正确数据
- [ ] 6 个 CI job 全部通过

---

## 八、回滚方案

如果 v3.3.1 发布后发现问题：

```bash
# 回滚 main 到 v3.3.0
git checkout main
git revert <merge-commit-hash>
git push origin main

# 重新打 tag
git tag -d v3.3.1
git push origin :refs/tags/v3.3.1
git tag -a v3.3.2 -m "hotfix v3.3.2: rollback of v3.3.1"
```

---

## 九、时间线预估

| 步骤 | 操作者 | 说明 |
|------|--------|------|
| Step 1-3 | Assistant | 创建分支、修改代码、更新版本号 |
| Step 4-5 | Assistant | 提交、推送、创建 PR |
| Step 6 | GitHub Actions | CI 自动运行 |
| Step 7 | User | 在 GitHub 合并 PR |
| Step 8-10 | Assistant | 打 tag、同步 develop |
