# v3.28.0 发布方案

> 文档版本：v3.28.0 | 更新日期：2026-11-05
> 文档性质：版本发布输出文档，记录发布准备、流程、部署步骤和回滚方案

---

## 一、发布概要

| 项目 | 内容 |
|------|------|
| **版本号** | v3.28.0 |
| **版本类型** | Minor |
| **基线版本** | v3.27.0 |
| **发布日期** | 2026-11-05 |
| **开发分支** | `develop` |
| **发布分支** | `main` |
| **数据库迁移** | 无 |

### 发布主题

**排除规则可选解封已封锁终端**，同时修复 CI 三个必然失败的 Job 并完成后端 ruff 告警清零。

---

## 二、变更内容

### 2.1 新功能

| 模块 | 内容 |
|------|------|
| 后端 | 创建 / 停用→启用排除规则支持 `unblock_blocked`（默认 false）；仅当终端绑定的全部防火墙解封成功才删除终端记录，黑名单置 `auto_unblocked=true`、`unblock_reason=excluded_by_rule`；失败/部分成功/无绑定保留并打标 |
| 接口 | `POST /terminal-exclusions`、`POST /terminal-exclusions/{id}/toggle` 接收 `unblock_blocked`；响应新增 `impact.blocked` 与 `unblock` 明细；勾选时额外校验 `blacklist:write` |
| 前端 | 影响预览新增「已封锁」指标；解封勾选与二次确认；启停确认弹窗；toast 展示成功/失败/跳过 |
| 可观测性 | 解封流程 ALL_SUCCESS / PARTIAL / SKIPPED / finished 分支日志；审计归属当前操作人 |

### 2.2 工程化

- 修复 CI 三个必然失败 Job：backend-lint（固定 `ruff==0.15.17`）、frontend-lint（空 catch + warning 阈值 30）、frontend-build（仓库根构建上下文 + `VERSION` 注入）。
- CI 新增 `permissions`、`concurrency` 与各 Job `timeout-minutes`；前端 lint 统一走 `npm run lint`。
- 后端 ruff 317 条告警全部修复，移除 22 条临时基线豁免，恢复零容忍门禁。
- 行为验证：646 条定向回归 + 1764 条全量测试通过，解封冒烟输出与清理前一致。

---

## 三、提交记录

| # | 提交信息 | 内容 |
|---|---------|------|
| 1 | `feat(exclusions): 支持创建/启用排除规则时可选解封已封锁终端` | 后端 schema / service / compliance / API 与测试 |
| 2 | `feat(frontend): 排除规则页面支持可选解封已封锁终端` | 页面、API client、三语文案 |
| 3 | `docs(terminals): 补充排除规则可选解封说明` | api / backend / user-guide / operations-runbook |
| 4 | `chore(ci): 修复工作流失败并统一 lint 门禁` | ci.yml、deployment.md、前端 lint 修复 |
| 5 | `refactor(backend): 清零 ruff 告警并移除临时基线豁免` | 77 个后端文件的等价格式/静态修复 |
| 6 | `chore(release): bump version to v3.28.0 and refresh docs` | VERSION 与发布文档 |

---

## 四、发布流程

### 4.1 准备

```bash
cd /opt/TerminalAccessManager
git checkout develop
git pull origin develop
```

本地验证（提交前已完成）：

```bash
cd backend && ruff check app/ tests/
cd backend && VERSION=dev DATABASE_URL=sqlite+aiosqlite:///:memory: .venv/bin/python -m pytest tests/ -q --no-cov
cd frontend && npm run lint && npx tsc --noEmit && npx vitest run && npm run build
```

### 4.2 推送与 CI

```bash
git push origin develop
```

等待 develop 的 6 个 CI Job 全部通过：backend-lint、backend-test、frontend-lint、frontend-test、backend-build、frontend-build。

### 4.3 创建 PR

- 方向：`develop` → `main`
- 标题：`release: v3.28.0 排除规则可选解封 + CI 修复与 lint 清零`
- 说明：使用下方模板

```markdown
## Summary
- 排除规则创建/启用新增可选解封：全部防火墙成功才删除终端并标记黑名单，失败/部分成功/无绑定保留并打标
- 修复 CI 三个必然失败 Job（ruff 未固定版本、ESLint 阈值、前端镜像构建上下文），新增并发取消与超时
- 后端 ruff 317 条告警清零，移除全部临时基线豁免，恢复零容忍门禁

## 行为影响
- 解封为可选操作，默认关闭时与 v3.27.0 行为完全一致
- lint 清理无行为变化：1764 条后端测试、75 条前端测试全部通过

## Test plan
- [ ] 后端 `pytest tests/` 1764 passed
- [ ] 前端 `npm run lint` / `tsc` / `vitest run` / `vite build`
- [ ] `docker build ./backend`、`docker build -f frontend/Dockerfile .`
- [ ] `./manage.sh update && ./manage.sh health`
- [ ] PR CI 6 个 Job 全部通过
```

### 4.4 合并与打标签

PR CI 通过后合并（merge commit），然后：

```bash
git checkout main
git pull origin main
git tag -a v3.28.0 -m "release v3.28.0: optional unblock for excluded blocked terminals, CI fixes, zero-warning lint"
git push origin v3.28.0
```

创建 GitHub Release：标题 `v3.28.0`，正文复用 `docs/release-notes.md` 的 `[v3.28.0]` 段落。

### 4.5 同步 develop

```bash
git checkout develop
git merge main
git push origin develop
```

---

## 五、部署步骤

### 5.1 生产环境

```bash
cd /opt/TerminalAccessManager
git checkout main
git pull origin main
./manage.sh upgrade
./manage.sh health
```

### 5.2 本地开发环境

```bash
./manage.sh update
./manage.sh health
```

本次无数据库迁移，无需执行 `alembic upgrade`。

---

## 六、回滚方案

```bash
./manage.sh upgrade v3.27.0
```

- 无数据库迁移，回滚不涉及 schema 变更。
- 若仅解封行为异常，取消勾选 `unblock_blocked` 即可恢复 v3.27.0 的默认行为。

---

## 七、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `VERSION` | 编辑 | 3.27.0 → 3.28.0 |
| `backend/app/schemas/terminal_exclusion.py` | 编辑 | `unblock_blocked`、`blocked`、`ExclusionUnblockResult`、`TerminalExclusionToggle` |
| `backend/app/services/terminal_exclusion_service.py` | 编辑 | 解封编排、分支日志、失败/跳过统计 |
| `backend/app/services/compliance_service.py` | 编辑 | `_unblock_on_firewall(actor=...)` |
| `backend/app/api/v1/endpoints/terminal_exclusions.py` | 编辑 | 参数接收、`blacklist:write` 校验、响应与审计扩展 |
| `backend/tests/test_terminal_exclusion_{service,integration}.py` | 编辑 | 解封分支与失败策略测试 |
| `backend/tests/test_endpoints_terminal_exclusions.py` | 新增 | 端点级权限与参数测试 |
| `frontend/src/pages/TerminalExclusions.tsx` | 编辑 | 已封锁指标、解封勾选与确认、结果提示 |
| `frontend/src/api/terminalExclusions.ts` | 编辑 | 类型与 toggle 参数 |
| `frontend/src/i18n/locales/{zh,en,ja}.ts` | 编辑 | 新增文案 |
| `.github/workflows/ci.yml` | 编辑 | 修复 3 个 Job，新增权限/并发/超时 |
| `frontend/package.json` | 编辑 | lint warning 阈值 30 |
| `frontend/src/{components/LDAPImportModal.tsx,components/datasources/OperationSourceTab.tsx,hooks/useTokenExpiration.ts}` | 编辑 | 空 catch 修复 |
| 后端 77 个 `app/`、`tests/` 文件 | 编辑 | ruff 告警等价修复 |
| `docs/{api,backend,user-guide,operations-runbook,deployment}.md` | 编辑 | 功能/CI 说明与版本号 |
| `docs/changelog.md` / `release-notes.md` / `release-plan.md` / `production-readiness-assessment.md` | 编辑 | 发布文档 |

---

## 八、验证清单

- [ ] 根 `VERSION` = 3.28.0
- [ ] 功能文档与发布文档版本统一为 v3.28.0
- [ ] `ruff check app/ tests/` 零告警
- [ ] 后端全量 1764 passed，前端 75 passed
- [ ] 6 个提交已推送 develop，CI 全部通过
- [ ] 发布 PR（develop → main）CI 通过并已合并
- [ ] `v3.28.0` tag 已创建并推送
- [ ] GitHub Release `v3.28.0` 已发布
- [ ] develop 已同步 main（包含 tag）
- [ ] 部署后 `./manage.sh health` 通过，版本显示 3.28.0
