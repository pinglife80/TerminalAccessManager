# v3.3.0 发布准备 — 剩余步骤

> 文档版本：v3.3.0 | 更新日期：2026-06-17

## 当前状态

已完成：
- ✅ Step 1: 同步版本号（manage.sh, package.json, config.py, .env.example）
- ✅ Step 2: 更新 changelog.md
- ✅ Step 3: 更新 release-notes.md
- ✅ Step 4: 更新 15 个文档版本号 → v3.3.0
- ✅ Step 6: 创建 docs/user-guide.md
- ✅ Step 7: 创建 docs/quick-start-guide.md

未完成：
- ⬜ Step 5: 创建 docs/release-plan.md
- ⬜ Step 8: 更新 README.md 文档导航
- ⬜ Step 9: Git 提交 + 推送

## 实施步骤

### Step 5: 创建 docs/release-plan.md

**操作**：将 `.trae/documents/production-release-v3.3.0.md` 的内容复制到 `docs/release-plan.md`，并调整文档头部格式使其与其他 docs/ 文档一致（添加版本号和日期行）。

**源文件**：`.trae/documents/production-release-v3.3.0.md`（已读取，357 行）
**目标文件**：`docs/release-plan.md`（新建）

内容调整：
- 保留完整发布方案内容
- 确保文档头部包含 `> 文档版本：v3.3.0 | 更新日期：2026-06-17`（已有，无需修改）

### Step 8: 更新 README.md 文档导航

**文件**：`README.md`（已读取，71 行）

在文档导航表中新增 3 行：

| 我想… | 看这个 |
|--------|--------|
| 快速上手操作 | [quick-start-guide.md](docs/quick-start-guide.md) |
| 查用户操作手册 | [user-guide.md](docs/user-guide.md) |
| 查发布方案 | [release-plan.md](docs/release-plan.md) |

插入位置：在"查版本变更"行之前，保持逻辑分组（用户文档 → 技术文档 → 版本文档）。

### Step 9: Git 提交 + 推送

```bash
git add manage.sh frontend/package.json backend/app/core/config.py .env.example \
  docs/changelog.md docs/release-notes.md docs/release-plan.md \
  docs/user-guide.md docs/quick-start-guide.md \
  docs/api.md docs/architecture.md docs/backend.md docs/database.md \
  docs/deployment.md docs/manage-sh-reference.md docs/datasource-lifecycle.md \
  docs/RBAC.md docs/branding.md docs/logging-guide.md docs/git-workflow-guide.md \
  docs/production-readiness-assessment.md docs/disaster-recovery.md \
  docs/operations-runbook.md frontend/docs/implementation.md README.md
git commit -m "release: prepare v3.3.0 release"
git push origin develop
```

**注意**：不添加 `.trae/` 目录下的文件（这些是 IDE 工作文件，不属于项目代码）。

## 验证

- [ ] docs/release-plan.md 存在且内容完整
- [ ] README.md 文档导航包含 3 个新条目
- [ ] git status 无未跟踪的项目文件
- [ ] git push 成功
