# v3.28.1 发布方案

> 文档版本：v3.28.1 | 更新日期：2026-11-06
> 文档性质：版本发布输出文档，记录发布准备、流程、部署步骤和回滚方案

---

## 一、发布概要

| 项目 | 内容 |
|------|------|
| **版本号** | v3.28.1 |
| **版本类型** | Patch |
| **基线版本** | v3.28.0 |
| **发布日期** | 2026-11-06 |
| **开发分支** | `develop` |
| **发布分支** | `main` |
| **数据库迁移** | 无 |

### 发布主题

**修复合规误判**：合规震荡、离线状态冻结、陈旧 `device_id` 误判合规，同时补充 `[compliance-trace]` 判定链路追踪日志与存量修复脚本。

---

## 二、变更内容

### 2.1 缺陷修复

| 模块 | 内容 |
|------|------|
| ARP 采集 | 新增记录写入 `updated_at=now()`；离线检测改为 `updated_at or timestamp` 兜底，修复已有记录被误判离线导致的合规震荡（10.8.18.183） |
| 设备归组判定 | 新增 `_effective_device_id()`：注册表可用时以当前 MAC→设备映射为准，映射为空时回退旧逻辑；批量首检与全量重算写回自愈值，修复陈旧关联授予的误合规（10.8.15.41） |
| 离线守卫 | `auto_block_non_compliant`、定时任务 retry-block、`_expand_non_compliant_to_device` 统一排除 `block_state=offline` 且未封锁的终端 |
| 存量修复 | 新增 `backend/scripts/repair_stale_device_ids.py`：默认 dry-run，`--apply` 清理失效关联并将离线未封锁记录重置为 `unknown` |

### 2.2 可观测性

- 统一前缀 `[compliance-trace]`：`[device-grouping]` 关联校验与设备级覆盖、`[offline-skip]` 跳过原因与冻结状态、`[auto-block]` 候选数/设备扩展/逐条封锁。
- 离线终端为 `compliant` 且 `device_id` 已失效时输出 WARNING，并提示运行修复脚本。

### 2.3 测试

- 后端全量 1781 passed（较 v3.28.0 新增 17 条）。
- 新增“离线 + 陈旧 device_id + 冻结 compliant”端到端回归用例，锁定事故场景。
- `ruff check app/ tests/` 零告警。

---

## 三、提交记录

| # | 提交信息 | 内容 |
|---|---------|------|
| 1 | `fix(arp): harden offline detection and refresh device_id from registry` | ARP `updated_at`、离线检测兜底、`device_id` 刷新与对应测试 |
| 2 | `fix(compliance): reject stale device_id and keep offline terminals out of blocking` | 设备归组映射校验、离线守卫、存量修复脚本、追踪日志与测试 |
| 3 | `chore(release): bump version to v3.28.1 and refresh docs` | VERSION 与发布文档 |

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
- 标题：`release: v3.28.1 修复合规误判与陈旧 device_id 关联`

```markdown
## Summary
- 修复 ARP 新记录缺少 updated_at 导致的合规震荡，离线检测增加 timestamp 兜底
- auto-block / retry-block / 设备归组扩展排除 offline 终端，避免错误状态被覆盖
- 设备归组以当前 MAC→设备映射校验 device_id，陈旧关联不再误判合规；重算与采集自动自愈
- 新增 repair_stale_device_ids 存量修复脚本（默认 dry-run）与 [compliance-trace] 追踪日志

## 行为影响
- 仅影响存在陈旧 device_id 或离线冻结状态的终端；离线记录合规状态变为 unknown（预期）
- 无 API/schema/数据库迁移变更；正常在线终端判定与封锁行为不变

## Test plan
- [ ] 后端 `pytest tests/` 1781 passed
- [ ] 后端 `ruff check app/ tests/` 零告警
- [ ] 前端 `npm run lint` / `tsc` / `vitest run` / `vite build`（CI）
- [ ] `./manage.sh update && ./manage.sh health`
- [ ] 升级后 repair_stale_device_ids dry-run 为 0 条
- [ ] PR CI 6 个 Job 全部通过
```

### 4.4 合并与打标签

PR CI 通过后合并（merge commit），然后：

```bash
git checkout main
git pull origin main
git tag -a v3.28.1 -m "release v3.28.1: fix compliance misjudgment, stale device_id and offline state handling"
git push origin v3.28.1
```

创建 GitHub Release：标题 `v3.28.1`，正文复用 `docs/release-notes.md` 的 `[v3.28.1]` 段落。

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

升级后建议执行存量修复 dry-run：

```bash
docker exec -w /app tam_backend python scripts/repair_stale_device_ids.py
```

---

## 六、回滚方案

```bash
./manage.sh upgrade v3.28.0
```

- 无数据库迁移，回滚不涉及 schema 变更。
- 已被存量修复脚本清空的 `device_id` 不会随代码回滚恢复；v3.28.0 对 `NULL` 关联按单网卡口径判定，不会重新产生误合规。
- 若设备归组判定过严，可临时关闭 `device_grouping_enabled`。

---

## 七、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `VERSION` | 编辑 | 3.28.0 → 3.28.1 |
| `backend/app/services/arp_collector_service.py` | 编辑 | `updated_at` 写入、离线检测兜底、`device_id` 刷新 |
| `backend/app/services/compliance_service.py` | 编辑 | `_effective_device_id`、离线守卫、重算自愈、存量修复、追踪日志 |
| `backend/app/main.py` | 编辑 | retry-block 排除离线终端 |
| `backend/tests/test_arp_collector_service.py` | 编辑 | `updated_at`、离线检测、`device_id` 刷新测试 |
| `backend/tests/test_compliance_service.py` | 编辑 | 离线守卫、存量修复、离线陈旧关联回归测试 |
| `backend/tests/test_device_grouping.py` | 编辑 | 陈旧/冲突 `device_id` 判定与扩展防护测试 |
| `backend/scripts/repair_stale_device_ids.py` | 新增 | 存量修复 CLI（dry-run 默认） |
| `docs/{changelog,release-notes,release-plan}.md` | 编辑 | 发布文档 |
| `docs/{backend,operations-runbook,production-readiness-assessment}.md` | 编辑 | 功能说明、排查手册、版本跟踪 |

---

## 八、验证清单

- [ ] 根 `VERSION` = 3.28.1
- [ ] 功能文档与发布文档版本统一为 v3.28.1
- [ ] `ruff check app/ tests/` 零告警
- [ ] 后端全量 1781 passed
- [ ] 3 个提交已推送 develop，CI 全部通过
- [ ] 发布 PR（develop → main）CI 通过并已合并
- [ ] `v3.28.1` tag 已创建并推送
- [ ] GitHub Release `v3.28.1` 已发布
- [ ] develop 已同步 main（包含 tag）
- [ ] 部署后 `./manage.sh health` 通过，版本显示 3.28.1
- [ ] `repair_stale_device_ids.py` dry-run 输出 0 条陈旧关联
