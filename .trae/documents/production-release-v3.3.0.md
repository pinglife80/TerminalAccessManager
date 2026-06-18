# v3.3.0 发布方案

> 文档版本：v3.3.0 | 更新日期：2026-06-17
> 文档性质：版本发布输出文档，记录发布准备、流程、部署步骤和回滚方案

---

## 一、发布概要

| 项目 | 内容 |
|------|------|
| **版本号** | v3.3.0 |
| **发布类型** | Minor（新功能，向后兼容） |
| **发布日期** | 2026-06-17 |
| **前置版本** | v3.2.0 |
| **develop 提交数** | 39 个提交，93 文件，+16288/-2027 行 |
| **生产就绪评分** | 9.0/10 |

### 版本号决策

develop 上自 v3.2.0 以来新增了 RBAC 权限控制（新功能）、两阶段删除（新功能）、审计日志优化（改进）、生产就绪改进（改进）等。根据语义化版本：

- **Minor 递增**：RBAC 是向后兼容的新功能 → v3.**3**.0
- 不用 v3.2.1（Patch 仅用于 bug 修复）
- 不用 v4.0.0（无破坏性变更）

---

## 二、发布前状态

### 2.1 Git 状态

| 项目 | 状态 |
|------|------|
| develop 分支 | `9f00100`，领先 main 39 个提交 |
| main 分支 | `4a33c1a`，停留在 v3.2.0 之前 |
| 最新 tag | `v3.2.0`（`39b2bb9`） |

### 2.2 版本号不一致（必须修复）

| 位置 | 当前值 | 应更新为 |
|------|--------|---------|
| `manage.sh` VERSION | **2.0.0** | 3.3.0 |
| `frontend/package.json` version | **2.0.0** | 3.3.0 |
| `backend/app/core/config.py` VERSION | 3.2.0 | 3.3.0 |
| `.env.example` VERSION | 3.2.0 | 3.3.0 |
| 所有文档 | v3.2.0-r12 | v3.3.0 |

### 2.3 生产就绪评估

- 综合评分 9.0/10，已达标
- 无 Critical/High 阻塞项
- 7 个 Medium 风险项均为非阻塞
- 测试覆盖后端 ~30%（达标）、前端 ~15%（未达标但非阻塞）

### 2.4 CI/CD 状态

- CI 流水线已建立（lint + test + build，6 个 job）
- main 分支保护规则已定义（需 PR + CI 通过）

---

## 三、发布准备（在 develop 上完成）

### Step 1: 同步版本号

| 文件 | 修改 |
|------|------|
| `manage.sh` 第 74 行 | `VERSION="2.0.0"` → `VERSION="3.3.0"` |
| `frontend/package.json` 第 4 行 | `"version": "2.0.0"` → `"version": "3.3.0"` |
| `backend/app/core/config.py` 第 12 行 | `VERSION: str = "3.2.0"` → `VERSION: str = "3.3.0"` |
| `.env.example` 第 14 行 | `VERSION=3.2.0` → `VERSION=3.3.0` |

### Step 2: 更新 changelog.md

将 `[Unreleased]` 下的所有条目移入 `[3.3.0] - 2026-06-17` 版本块，新增空 `[Unreleased]` 占位。

### Step 3: 更新 release-notes.md

新增 `[v3.3.0] - 2026-06-17` 版本记录，包含 develop 上 v3.2.0 以来所有 39 个提交的分类汇总。

### Step 4: 更新所有文档版本号

17 个文档的版本号从 `v3.2.0-r12` 更新为 `v3.3.0`，日期更新为 `2026-06-17`。

> **版本号规则**：发布版本使用三段式语义化版本号（v3.3.0），开发迭代期间使用修订号（v3.3.0-r1, r2...）追踪文档变更。

### Step 5: 提交到 develop

```bash
git add -A
git commit -m "release: prepare v3.3.0 release"
git push origin develop
```

---

## 四、发布流程

### Step 6: 创建 PR（develop → main）

在 GitHub 上创建 Pull Request: develop → main
- 标题: "Release v3.3.0"
- 描述: 从 release-notes.md 复制 v3.3.0 内容

### Step 7: CI 验证

PR 创建后自动触发 CI（6 个 job 必须全部通过）：
- backend-lint (ruff)
- backend-test (pytest)
- frontend-lint (ESLint)
- frontend-test (vitest)
- backend-build (Docker)
- frontend-build (Docker)

### Step 8: 合并 PR

CI 通过后，在 GitHub 上 Merge PR（使用 Merge commit，不用 Squash）。

### Step 9: 打 tag

```bash
git checkout main
git pull origin main
git tag -a v3.3.0 -m "release v3.3.0: RBAC, audit log optimization, production readiness"
git push origin v3.3.0
```

### Step 10: 创建 GitHub Release

在 GitHub Releases 页面：
1. 选择 tag: `v3.3.0`
2. 标题: `v3.3.0`
3. 内容: 从 release-notes.md 复制 `[v3.3.0]` 部分
4. 发布

### Step 11: 同步 develop

```bash
git checkout develop
git merge main  # 确保 develop 包含 tag
git push origin develop
```

---

## 五、生产部署

### Step 12: 部署到生产服务器

```bash
# 首次部署
git clone https://github.com/pinglife80/TerminalAccessManager.git
cd TerminalAccessManager
git checkout v3.3.0
chmod +x manage.sh
./manage.sh deploy --prod

# 后续升级（从旧版本）
./manage.sh upgrade v3.3.0
```

### Step 13: 部署后验证

| 验证项 | 方法 |
|--------|------|
| HTTPS 访问 | 浏览器访问 `https://<HOST_IP>:8443` |
| JWT 认证 | 登录 admin 账户，检查 token 刷新 |
| 功能模块 | 终端/白名单/黑名单/数据源/审计日志各页面 |
| RBAC 权限 | 不同角色访问不同功能 |
| Docker 健康 | `./manage.sh health` |
| 日志检查 | `./manage.sh logs` |

---

## 六、回滚方案

### 方案 A: 版本回退

```bash
./manage.sh upgrade v3.2.0
```

### 方案 B: 紧急修复（hotfix）

```bash
git checkout main
git checkout -b hotfix/fix-critical-issue
# ... 修复 ...
git checkout main
git merge --no-ff hotfix/fix-critical-issue
git tag -a v3.3.1 -m "hotfix: fix critical issue"
git push origin main --tags
git checkout develop
git merge hotfix/fix-critical-issue
git push origin develop
```

---

## 七、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `manage.sh` | 编辑 | VERSION 2.0.0 → 3.3.0 |
| `frontend/package.json` | 编辑 | version 2.0.0 → 3.3.0 |
| `backend/app/core/config.py` | 编辑 | VERSION 3.2.0 → 3.3.0 |
| `.env.example` | 编辑 | VERSION 3.2.0 → 3.3.0 |
| `docs/changelog.md` | 编辑 | [Unreleased] → [3.3.0]，版本号 → v3.3.0 |
| `docs/release-notes.md` | 编辑 | 新增 [v3.3.0]，版本号 → v3.3.0 |
| `docs/release-plan.md` | 新增 | 发布方案文档 |
| `docs/user-guide.md` | 新增 | 用户使用手册 |
| `docs/quick-start-guide.md` | 新增 | 快速上手指南 |
| `docs/api.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/architecture.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/backend.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/database.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/deployment.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/manage-sh-reference.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/datasource-lifecycle.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/RBAC.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/branding.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/logging-guide.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/git-workflow-guide.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/production-readiness-assessment.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/disaster-recovery.md` | 编辑 | 版本号 → v3.3.0 |
| `docs/operations-runbook.md` | 编辑 | 版本号 → v3.3.0 |
| `frontend/docs/implementation.md` | 编辑 | 版本号 → v3.3.0 |

共 24 个文件需要修改（含新增 3 个）。

---

## 九、用户手册（新增交付件）

### 9.1 必要性分析

当前项目文档以**技术文档**为主（架构、API、数据库、部署），缺少面向终端用户的**操作指引**。生产发布后，运维人员和业务用户需要快速上手，而非阅读技术文档。

### 9.2 交付物

| 文档 | 文件名 | 定位 | 内容 |
|------|--------|------|------|
| **用户使用手册** | `docs/user-guide.md` | 面向终端用户的完整操作手册 | 所有功能模块的详细操作流程、配置说明、注意事项 |
| **快速上手指南** | `docs/quick-start-guide.md` | 面向新用户的精简入门 | 核心操作流程（登录→终端管理→合规检查→封堵/解封），详细内容引用 user-guide.md |

### 9.3 用户使用手册（user-guide.md）大纲

```
1. 系统概述
   - 系统简介与核心概念
   - 合规状态说明（compliant / non_compliant / bypass / unknown）
   - 角色与权限概览

2. 登录与认证
   - 首次登录与密码修改
   - 验证码与账户锁定机制
   - 多语言与主题切换

3. 仪表板
   - 合规状态统计概览
   - 快捷操作入口

4. 终端管理
   - 终端列表与搜索
   - 合规状态解读
   - 封堵操作（选择防火墙、封堵时长）
   - 解封操作
   - 白名单标记说明

5. 白名单管理
   - 添加白名单（MAC / IP / CIDR / IP 段）
   - 查看与删除
   - 白名单对合规状态的影响

6. 黑名单管理
   - 黑名单列表与筛选
   - 查看详情
   - 解封操作
   - 手动封堵与自动封堵的区别

7. 数据源管理
   - ARP 数据源（SSH / API 类型）
   - Sangfor 防火墙数据源
   - 数据源绑定关系
   - 启用/禁用与同步操作
   - 删除预览与安全删除

8. 合规基准
   - IPGuard 数据库集成
   - 同步操作
   - 删除预览

9. 审计日志
   - 日志搜索与过滤
   - 操作分类说明
   - 详情查看
   - CSV 导出

10. 用户管理
    - 创建/编辑/停用用户
    - 角色分配
    - 超管隔离说明

11. 系统设置
    - 品牌自定义（应用名、Logo、Favicon、登录页、页脚）
    - 安全配置

12. 常见问题（FAQ）
```

### 9.4 快速上手指南（quick-start-guide.md）大纲

```
1. 30 秒了解系统
   - 一句话：终端准入管控平台
   - 核心流程：数据采集 → 合规判定 → 封堵/解封

2. 登录
   - 访问地址与默认密码

3. 查看终端合规状态
   - 仪表板概览
   - 终端列表筛选

4. 封堵不合规终端
   - 选择终端 → 点击封堵 → 选择防火墙 → 确认

5. 解封终端
   - 黑名单中找到记录 → 点击解封

6. 添加白名单
   - 白名单页面 → 添加 → 输入 MAC/IP

7. 查看操作记录
   - 审计日志页面 → 按类型/日期筛选

8. 更多操作
   - 引用 user-guide.md 对应章节
```

---

## 八、验证清单

- [ ] 所有版本号统一为 3.3.0
- [ ] changelog.md [Unreleased] 条目已移入 [3.3.0]
- [ ] release-notes.md [v3.3.0] 内容完整
- [ ] release-plan.md 已创建到 docs/ 目录
- [ ] user-guide.md 已创建到 docs/ 目录
- [ ] quick-start-guide.md 已创建到 docs/ 目录
- [ ] CI 6 个 job 全部通过
- [ ] PR 已合并到 main
- [ ] v3.3.0 tag 已创建并推送
- [ ] GitHub Release 已发布
- [ ] develop 已同步 main（包含 tag）
- [ ] 生产部署验证通过
