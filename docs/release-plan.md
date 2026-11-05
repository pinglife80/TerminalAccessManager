# v3.27.0 发布方案

> 文档版本：v3.27.0 | 更新日期：2026-11-05
> 文档性质：版本发布输出文档，记录发布准备、流程、部署步骤和回滚方案

---

## 一、发布概要

| 项目 | 内容 |
|------|------|
| **版本号** | v3.27.0 |
| **发布类型** | Minor（新增功能，向后兼容） |
| **发布日期** | 2026-11-05 |
| **前置版本** | v3.26.3 |
| **主要功能** | 终端排除规则（入库前过滤 + 统计口径排除） |
| **数据库迁移** | 046_terminal_exclusion、047_terminal_excluded_flag |
| **生产就绪评分** | 9.0/10 |

### 版本号决策

自 v3.26.3 以来新增了终端排除规则：新页面、7 个 API 端点、2 个数据库迁移，属于向后兼容的新功能。根据语义化版本：

- **Minor 递增**：v3.26.3 → v3.**27**.0
- 不用 v3.26.4（Patch 仅用于 bug 修复）
- 不用 v4.0.0（无破坏性变更）

---

## 二、发布前状态

### 2.1 Git 状态

| 项目 | 状态 |
|------|------|
| develop 分支 | 当前功能提交（9 个提交批次），领先 main |
| main 分支 | v3.26.3 |
| 最新 tag | `v3.26.3` |
| 发布方式 | 不创建 feature 分支，提交直接进入 develop；通过发布 PR 合并 main |

### 2.2 版本号一致性

版本号单一来源为根目录 `VERSION`，`manage.sh`、`backend/app/core/config.py`、`frontend/vite.config.ts` 均读取该文件；`frontend/package.json` 版本不参与展示，本次不修改。

| 位置 | 当前值 | 状态 |
|------|--------|------|
| 根目录 `VERSION` | 3.27.0 | 待提交 |
| `manage.sh` / backend config / vite config | 读取根 `VERSION` | ✅ 无需修改 |
| `frontend/package.json` | 3.12.1（不参与展示） | 不修改 |
| 本次有内容变更的文档 | v3.27.0 | 待提交 |

### 2.3 生产就绪评估

- 综合评分 9.0/10，已达标
- 无 Critical/High 阻塞项
- 后端全量测试 1756 passed，前端构建通过

### 2.4 CI/CD 状态

- CI 流水线 6 个 job：`backend-lint`、`backend-test`、`frontend-lint`、`frontend-test`、`backend-build`、`frontend-build`
- main 分支保护要求 PR + 4 个 status check 通过

---

## 三、发布准备（在 develop 上完成）

### Step 1: 更新版本号

| 文件 | 修改 | 状态 |
|------|------|------|
| `VERSION` | `3.26.3` → `3.27.0` | 待提交 |

### Step 2: 更新功能文档

| 文件 | 更新内容 | 目标文档版本 |
|------|----------|-------------|
| `docs/api.md` | 新增第 18 章「终端排除规则」7 个端点；同步结果新增 `entries_excluded`；权限码补充 compliance | v3.27.0 |
| `docs/database.md` | 新增 `terminal_exclusions` 表、`terminals.excluded_by_rule`、迁移 046/047 | v3.27.0 |
| `docs/user-guide.md` | 新增「终端排除规则」章节（条件类型、AND/OR、预览、保留行与统计口径） | v3.27.0 |
| `docs/architecture.md` | ARP 采集链路新增排除过滤阶段与标记回收 | v3.27.0 |
| `docs/business-workflow.md` | 采集 → 排除过滤 → 合规 → 统计流程与保留行语义 | v3.27.0 |
| `docs/backend.md` | 新增 TerminalExclusionService、排除端点、测试清单 | v3.27.0 |
| `docs/operations-runbook.md` | 新增 2.11 终端排除规则排查（日志关键字、SQL） | v3.27.0 |
| `README.md` | 核心概念补充终端排除规则 | 无版本号 |

### Step 3: 更新 changelog.md

新增 `## [3.27.0] - 2026-11-05`，按「新增 / 修复 / 数据库 / 测试」分类记录。✅

### Step 4: 更新 release-notes.md

新增 `## [v3.27.0] - 2026-11-05`，包含背景、主要变更、迁移、升级步骤、注意事项、回滚说明、验证结果与文件清单。✅

### Step 5: 更新生产就绪评估文档

`docs/production-readiness-assessment.md` 头部版本更新为 v3.27.0，文档版本跟踪表新增 v3.27.0 行。✅

### Step 6: 分批提交到 develop

共 9 个提交批次：

1. 数据库迁移（046/047）
2. 后端排除规则模型、Schema、服务
3. 排除规则 API 端点
4. 采集/合规流程接入
5. 统计口径过滤修复
6. 前端页面与三语
7. 测试用例
8. 功能文档
9. 版本号与发布文档

提交后推送：

```bash
git push origin develop
```

---

## 四、发布流程

### Step 7: 创建发布 PR（develop → main）

在 GitHub 网页手动创建 Pull Request: develop → main
- 标题: `Release v3.27.0`
- 描述: 从 release-notes.md 复制 `[v3.27.0]` 内容（变更概要、迁移 046/047、测试结果、升级与回滚说明）

### Step 8: CI 验证

PR 创建后自动触发 CI（6 个 job 必须全部通过）：
- backend-lint (ruff)
- backend-test (pytest)
- frontend-lint (ESLint)
- frontend-test (vitest)
- backend-build (Docker)
- frontend-build (Docker)

### Step 9: 合并 PR

CI 通过后，在 GitHub 上 Merge PR（使用 Merge commit，不用 Squash）。

### Step 10: 打 tag

```bash
git checkout main
git pull --ff-only origin main
git tag -a v3.27.0 -m "release v3.27.0: terminal exclusion rules, excluded_by_rule stats filter"
git push origin v3.27.0
```

> 只推送 `v3.27.0` 单个 tag，不使用 `--tags`，避免推送本地遗留 tag。

### Step 11: 创建 GitHub Release

在 GitHub Releases 页面：
1. 选择 tag: `v3.27.0`
2. 标题: `v3.27.0`
3. 内容: 从 release-notes.md 复制 `[v3.27.0]` 部分
4. 发布

### Step 12: 同步 develop

```bash
git checkout develop
git pull --ff-only origin develop
git merge main
git push origin develop
```

---

## 五、生产部署

### Step 13: 部署到生产服务器

```bash
# 首次部署
git clone https://github.com/pinglife80/TerminalAccessManager.git
cd TerminalAccessManager
git checkout v3.27.0
chmod +x manage.sh
./manage.sh deploy --prod

# 后续升级（从旧版本）
./manage.sh upgrade v3.27.0
```

`./manage.sh upgrade` 会自动执行 `alembic upgrade head`，应用迁移 046/047。

### Step 14: 部署后验证

| 验证项 | 方法 |
|--------|------|
| HTTPS 访问 | 浏览器访问 `https://<HOST_IP>:8443` |
| 版本显示 | 系统设置页显示 3.27.0 |
| 终端排除规则 | 新增规则 → 预览影响 → 保存 → 查看终端列表与仪表盘统计 |
| 采集链路 | 触发数据源同步，检查 `entries_excluded` 与 `ARP exclusion summary` 日志 |
| Docker 健康 | `./manage.sh health` |
| 日志检查 | `./manage.sh logs backend -n 100` |

---

## 六、回滚方案

### 方案 A: 版本回退

```bash
./manage.sh upgrade v3.26.3
```

如需回退标记列（会丢失 `excluded_by_rule` 标记，终端数据保留）：

```bash
docker exec tam_backend python -m alembic downgrade 046_terminal_exclusion
```

`terminal_exclusions` 表可在应用回滚后保留，不影响旧版本运行。

### 方案 B: 紧急修复（hotfix）

```bash
git checkout main
git checkout -b hotfix/fix-critical-issue
# ... 修复 ...
git checkout main
git merge --no-ff hotfix/fix-critical-issue
git tag -a v3.27.1 -m "hotfix: fix critical issue"
git push origin v3.27.1
git checkout develop
git merge hotfix/fix-critical-issue
git push origin develop
```

---

## 七、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `VERSION` | 编辑 | 3.26.3 → 3.27.0 |
| `backend/alembic/versions/046_terminal_exclusion.py` | 新增 | terminal_exclusions 表 |
| `backend/alembic/versions/047_terminal_excluded_flag.py` | 新增 | terminals.excluded_by_rule + 索引 |
| `backend/app/models/terminal_exclusion.py` | 新增 | 排除规则模型 |
| `backend/app/services/terminal_exclusion_service.py` | 新增 | 排除规则服务 |
| `backend/app/api/v1/endpoints/terminal_exclusions.py` | 新增 | 7 个 API 端点 |
| `backend/app/services/{arp_collector_service,compliance_service,terminal_service}.py` | 编辑 | 排除过滤、合规守卫、统计过滤 |
| `frontend/src/pages/TerminalExclusions.tsx` | 新增 | 终端排除规则页面 |
| `frontend/src/api/terminalExclusions.ts` | 新增 | 前端 API client |
| `backend/tests/test_terminal_exclusion_service.py` | 新增 | 单元测试 72 个 |
| `backend/tests/test_terminal_exclusion_integration.py` | 新增 | 集成测试 4 个 |
| `docs/changelog.md` | 编辑 | 新增 [3.27.0]，版本号 → v3.27.0 |
| `docs/release-notes.md` | 编辑 | 新增 [v3.27.0]，版本号 → v3.27.0 |
| `docs/release-plan.md` | 编辑 | 更新为 v3.27.0 发布方案 |
| `docs/api.md` / `database.md` / `user-guide.md` / `architecture.md` / `business-workflow.md` / `backend.md` / `operations-runbook.md` | 编辑 | 功能文档更新，版本号 → v3.27.0 |
| `docs/production-readiness-assessment.md` | 编辑 | 版本跟踪表新增 v3.27.0 |
| `README.md` | 编辑 | 核心概念补充终端排除规则 |

---

## 八、验证清单

- [ ] 根 `VERSION` = 3.27.0
- [ ] 功能文档与发布文档版本统一为 v3.27.0
- [ ] 9 个提交直接推送 develop，develop CI 6 个 job 全部通过
- [ ] 发布 PR（develop → main）CI 通过并已合并
- [ ] `v3.27.0` tag 已创建并推送
- [ ] GitHub Release `v3.27.0` 已发布
- [ ] develop 已同步 main（包含 tag）
- [ ] 生产部署后 `./manage.sh health` 通过，版本显示 3.27.0
