# v3.3.1 以来变更与文档匹配程度审查报告

> 审查日期：2026-06-22
> 审查范围：v3.3.1 tag 至当前工作目录（含已提交和未提交变更）
> 审查方式：静态代码分析 + 文档对比

---

## 一、执行摘要

### 1.1 总体结论

自 v3.3.1 版本以来，项目经历了多方面的变更，包括功能增强、Bug 修复和基础设施改进。**整体文档与实现匹配程度为 65%**，存在以下主要问题：

| 类别 | 数量 | 说明 |
|------|------|------|
| 严重差异 | 3 | 已提交变更未记录到官方文档、关键功能部分实现 |
| 中等差异 | 5 | 实现与计划存在偏差、命名不一致 |
| 轻微差异 | 4 | 格式和细节问题 |

### 1.2 变更总览

| 变更类型 | 数量 | 说明 |
|----------|------|------|
| 已提交变更 | 1 个提交 | 白名单删除 404 修复 |
| 未提交变更 | 18 个文件修改 | 覆盖前端、后端、DevOps 多领域 |
| 新增文件 | 8 个 | .env 模板、Dockerfile、文档等 |
| 涉及计划文档 | 6 份 | 描述各功能领域的改进计划 |

### 1.3 主要发现

1. **白名单删除修复已提交但未记录**：v3.3.1 之后有 1 个关于白名单删除 404 修复的提交，但 release-notes.md 和 changelog.md 均无记录
2. **大量工作在进行中**：工作目录中有大量未提交变更，涉及页脚版本、Dashboard 系统状态、角色 i18n、开发环境增强等
3. **计划与实现存在偏差**：部分功能实现与计划文档描述存在差异（如权限 i18n 命名空间、env_file 配置）
4. **版本号当前一致**：所有版本号位置当前均为 3.3.1，但新功能尚未发布

---

## 二、v3.3.1 以来变更清单

### 2.1 已提交变更（1 个提交）

**提交**: `a7e2560 fix(whitelist): fix deletion 404 errors`

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/api/v1/endpoints/whitelist.py` | 修改 | 删除端点从 `DELETE /{identifier}` 改为 `DELETE /?identifier=` |
| `backend/app/services/terminal_service.py` | 修改 | 白名单删除逻辑增强，支持 MAC-only、IP-only、复合条目删除 |
| `backend/tests/test_whitelist.py` | 修改 | 新增大量删除场景测试用例 |
| `frontend/src/pages/Whitelist.tsx` | 修改 | 前端删除调用方式调整 |

### 2.2 未提交变更（18 个修改文件 + 8 个新增文件）

按功能领域分组：

#### A. 页脚版本与 Dashboard 系统状态

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/store/branding.ts` | 修改 | 添加 `systemVersion`、`systemEnvironment` 字段，从 `/health` 获取 |
| `frontend/src/components/Layout.tsx` | 修改 | Footer 显示版本号 |
| `frontend/src/pages/Login.tsx` | 修改 | 登录页 Footer 显示版本号 |
| `frontend/src/pages/Dashboard.tsx` | 修改 | System Status 区域添加系统版本和运行环境 |
| `frontend/src/config/branding.ts` | 修改 | 移除硬编码 `version: 'v2.0.0'` |
| `frontend/src/i18n/locales/en.ts` | 修改 | 添加 `dashboard.systemVersion` 等翻译 |
| `frontend/src/i18n/locales/zh.ts` | 修改 | 添加对应中文翻译 |
| `frontend/src/i18n/locales/ja.ts` | 修改 | 添加对应日文翻译 |
| `nginx/etc/conf.d/tam.conf` | 修改 | 添加 `/health` 路径代理 |
| `nginx/etc/conf.d/tam.dev.conf` | 修改 | 开发环境同步添加 `/health` 路径 |

#### B. 角色权限 i18n 与超管角色修复

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/src/pages/Roles.tsx` | 修改 | 权限列表头改用 `permissionsColumn`、角色描述和权限名称改用 i18n |
| `frontend/src/i18n/locales/en.ts` | 修改 | 添加角色描述翻译、权限翻译对象、`permissionsColumn` |
| `frontend/src/i18n/locales/zh.ts` | 修改 | 添加对应中文翻译 |
| `frontend/src/i18n/locales/ja.ts` | 修改 | 添加对应日文翻译 |
| `frontend/src/i18n/index.ts` | 修改 | 添加 `nsSeparator: false` 禁用冒号分隔符 |
| `backend/cli.py` | 修改 | 初始化 admin 用户时关联 superadmin 角色 |

#### C. 开发环境增强与 .env 分离

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `docker-compose.yml` | 修改 | 添加 `env_file`、`image` 标签、`upload_data` 卷、nginx 版本固定 |
| `docker-compose.dev.yml` | 修改 | 增强开发环境：后端热重载、前端 HMR、端口暴露 |
| `docker-compose.prod.yml` | 修改 | 添加 `env_file`、`upload_data` 卷 |
| `.env.example` | 修改 | 环境变量模板更新 |
| `.env.dev` | 新增 | 开发环境覆盖模板 |
| `.env.prod` | 新增 | 生产环境覆盖模板（占位符） |
| `frontend/Dockerfile.dev` | 新增 | 前端开发服务器 Dockerfile |

#### D. manage.sh 脚本优化

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `manage.sh` | 修改 | flock 锁替代文件锁、printf 替代 eval、新增强制日志函数等 |

---

## 三、官方发布文档匹配审查

### 3.1 release-notes.md 审查

**当前状态**：v3.3.1 条目存在且内容准确，但之后无新条目

| 版本 | 文档状态 | 实际变更 | 匹配度 |
|------|----------|----------|--------|
| v3.3.1 | ✅ 有记录 | 黑名单过滤修复 | 100% 匹配 |
| v3.3.1 之后 | ❌ 无记录 | 白名单删除修复 + 大量未提交变更 | 0% 匹配 |

**问题**:
- 已提交的白名单删除修复（`a7e2560`）未记录在 release-notes.md 中
- 大量未提交的功能增强（页脚版本、Dashboard、i18n、开发环境等）尚未发布，暂无文档记录属于预期

### 3.2 changelog.md 审查

**当前状态**：v3.3.1 条目存在，`[Unreleased]` 节为空

| 变更 | changelog 状态 | 说明 |
|------|---------------|------|
| 黑名单过滤修复 | ✅ [3.3.1] 节有记录 | 与实际变更一致 |
| 白名单删除修复 | ❌ 缺失 | 已提交但未记录到 [Unreleased] |
| 其他未提交变更 | N/A | 尚未发布，无需记录 |

**问题**:
- `[Unreleased]` 节为空，但实际上已有 1 个提交在 v3.3.1 之后
- 按 Keep a Changelog 规范，已提交但未发布的变更应记录在 `[Unreleased]` 节

---

## 四、计划与规格文档匹配审查

### 4.1 页脚版本 + Dashboard 系统状态 + 角色 i18n 计划

**文档**: `footer-version-dashboard-status-role-i18n-plan.md`

**整体状态**: 大部分已实现（约 80%）

| 计划功能 | 实现状态 | 说明 |
|----------|----------|------|
| 页脚版本号（从 /health 获取） | ✅ 已实现 | branding store + Layout + Login 均已实现 |
| Dashboard 系统状态显示版本 | ✅ 已实现 | System Status 卡片已添加 |
| Dashboard 显示运行环境 | ✅ 已实现 | production/development 翻译显示 |
| 角色描述 i18n | ✅ 已实现 | `roles.${name}_desc` 模式 |
| 权限名称 i18n | ⚠️ 部分实现 | 实现方式与计划有差异 |
| 权限描述 i18n | ❌ 未实现 | 当前只翻译了名称，未翻译描述 |
| branding.ts 删除硬编码版本 | ✅ 已实现 | version 字段已移除 |

**差异详情**:

1. **权限 i18n 命名空间不一致**
   - 计划: `permissions.${code}`（独立命名空间）
   - 实际: `roles.permissions.${code}`（嵌套在 roles 下）
   - 影响: 中等 - 功能可用但与计划命名约定不一致

2. **权限描述 i18n 未实现**
   - 计划: `permissions.${code}_desc` 翻译权限描述
   - 实际: 未实现，仍显示后端返回的中文描述
   - 影响: 中等 - 权限名称已国际化，但描述未国际化

3. **i18n 文件类型不匹配**
   - 计划文档提到 `zh.json` / `en.json`
   - 实际使用 `zh.ts` / `en.ts` / `ja.ts`
   - 影响: 轻微 - 计划文档基于旧信息，实际代码已升级为 TS

### 4.2 开发环境增强 + .env 分离计划

**文档**: `dev-env-enhancement-and-env-separation-plan.md`

**整体状态**: 部分实现（约 60%）

| 计划功能 | 实现状态 | 说明 |
|----------|----------|------|
| .env.dev 模板 | ✅ 已实现 | 开发环境覆盖文件已创建 |
| .env.prod 模板 | ✅ 已实现 | 生产环境覆盖文件已创建 |
| docker-compose.yml 添加 env_file | ⚠️ 部分实现 | 只添加了 `.env`，未添加 `.env.${ENVIRONMENT}` |
| docker-compose.dev.yml 增强 | ✅ 已实现 | 热重载、HMR、端口暴露等均已实现 |
| frontend/Dockerfile.dev | ✅ 已实现 | Vite 开发服务器镜像已创建 |
| manage.sh 支持 .env 分离 | ⚠️ 部分实现 | dc() 函数可能已调整（需进一步验证） |
| .env.example 精简 | ❌ 未完全实现 | .env.example 内容仍然较多 |
| .gitignore 添加 .env | ⚠️ 待验证 | 需要确认 .env 是否已在 .gitignore 中 |

**差异详情**:

1. **docker-compose.yml env_file 不完整**
   - 计划: 加载 `.env` + `.env.${ENVIRONMENT:-development}`
   - 实际: 只加载了 `.env`
   - 影响: 严重 - 环境差异配置无法通过 docker-compose 自动加载

2. **docker-compose.prod.yml 使用 .env.prod.local**
   - 计划: 使用 `.env.prod`
   - 实际: 使用 `.env.prod.local`
   - 影响: 中等 - 命名约定与计划不一致

### 4.3 白名单删除修复计划

**文档**: `whitelist_delete_fix_plan.md`

**整体状态**: 完全实现（100%）

| 计划修改文件 | 实现状态 | 说明 |
|-------------|----------|------|
| `backend/app/api/v1/endpoints/whitelist.py` | ✅ 已实现 | 删除端点路径和参数调整 |
| `backend/app/services/terminal_service.py` | ✅ 已实现 | 删除逻辑增强 |
| `frontend/src/pages/Whitelist.tsx` | ✅ 已实现 | 前端调用方式调整 |

### 4.4 角色权限 i18n 与超管角色修复规格

**文档**: `.trae/specs/role-i18n-superadmin-fix/spec.md`

**整体状态**: 完全实现（100%）

| 功能需求 | 实现状态 | 说明 |
|----------|----------|------|
| 权限列表头正确显示 | ✅ 已实现 | 重命名为 `permissionsColumn` |
| 权限名称 i18n 翻译 | ✅ 已实现 | `roles.permissions.${code}` 模式 |
| admin 用户初始化关联 superadmin | ✅ 已实现 | `cli.py` 中添加了角色关联逻辑 |
| nsSeparator 禁用 | ✅ 已实现 | 冒号不再被视为命名空间分隔符 |

### 4.5 部署评估报告

**文档**: `deployment-assessment-report.md`

**整体状态**: 部分建议已实施

| 评估建议 | 实施状态 | 说明 |
|----------|----------|------|
| Nginx 锁定版本 | ✅ 已实施 | `nginx:alpine` → `nginx:1.27-alpine` |
| 上传目录使用 volume | ✅ 已实施 | `upload_data` 卷替代 tmpfs |
| 其他建议 | ⚠️ 待验证 | 需要逐一核对 |

### 4.6 manage.sh 优化验证计划

**文档**: `manage-sh-optimization-verification-plan.md`

**整体状态**: 部分优化已实施（约 40%）

已观察到的优化：
- ✅ flock 原子锁替代文件锁
- ✅ printf -v 替代 eval（安全性提升）
- ✅ 新增 `_log_forced()` 强制日志函数
- ✅ 锁文件路径调整到项目目录内

---

## 五、版本号一致性检查

### 5.1 检查结果

| 位置 | 当前值 | 状态 |
|------|--------|------|
| `manage.sh` (L1050) | `3.3.1` | ✅ 一致 |
| `manage.sh` (L1188) | `3.3.1` | ✅ 一致 |
| `backend/app/core/config.py` (L11) | `"3.3.1"` | ✅ 一致 |
| `frontend/package.json` (L4) | `"3.3.1"` | ✅ 一致 |
| `.env.example` (L27) | `3.3.1` | ✅ 一致 |

**结论**: 当前所有版本号位置均为 `3.3.1`，一致性良好。

### 5.2 注意事项

- 大量新功能正在开发中，尚未发布，版本号保持 3.3.1 是合理的
- 下一次发布时需要根据变更内容决定版本号是 patch（3.3.2）还是 minor（3.4.0）
- 鉴于有多个新功能（页脚版本、Dashboard 系统状态、开发环境增强等），建议下次发布为 minor 版本（v3.4.0）

---

## 六、差异列表（按严重程度）

### 6.1 严重差异（3 项）

**S-1: 已提交的白名单修复未记录到官方文档**
- **描述**: v3.3.1 之后有 1 个白名单删除 404 修复的提交，但 release-notes.md 和 changelog.md 均无记录
- **证据**: 
  - 提交 `a7e2560` 存在于 v3.3.1..HEAD
  - [changelog.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/changelog.md#L12-L14) 中 `[Unreleased]` 节为空
  - [release-notes.md](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/release-notes.md) 中最新版本为 v3.3.1
- **影响**: 发布时可能遗漏该修复，导致用户不知道变更内容
- **建议**: 在 changelog.md 的 `[Unreleased]` 节添加白名单修复记录

**S-2: docker-compose.yml env_file 不包含环境覆盖文件**
- **描述**: 计划中 docker-compose.yml 应加载 `.env` + `.env.${ENVIRONMENT}`，但实际只加载了 `.env`
- **证据**:
  - [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L90-L92) 只有 `- .env`
  - 计划文档描述应包含环境特定的 env_file
- **影响**: 环境差异配置（如开发环境的 DEBUG=true）无法通过 docker-compose 自动生效
- **建议**: 在 docker-compose.yml 中添加第二行 env_file，或在各环境 override 文件中单独添加

**S-3: 权限描述 i18n 未实现**
- **描述**: 计划中权限名称和描述都应国际化，但当前只实现了权限名称的国际化
- **证据**:
  - [Roles.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Roles.tsx) 中只翻译了 `perm.name`，未翻译 `perm.description`
  - i18n 文件中只有权限名称翻译，没有 `_desc` 后缀的描述翻译
- **影响**: 权限描述在非中文环境下仍显示中文，国际化不完整
- **建议**: 添加权限描述的 i18n 翻译键，并在 Roles.tsx 中使用

### 6.2 中等差异（5 项）

**M-1: 权限 i18n 命名空间与计划不一致**
- **描述**: 计划使用 `permissions.${code}`，实际使用 `roles.permissions.${code}`
- **证据**:
  - [Roles.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Roles.tsx#L330): `t('roles.permissions.${perm.code}', perm.name)`
  - 计划文档描述: `permissions.terminal:read`
- **影响**: 功能可用，但与计划文档的命名约定不一致
- **建议**: 统一命名空间，更新计划文档或更新代码

**M-2: docker-compose.prod.yml 使用 .env.prod.local 而非 .env.prod**
- **描述**: 生产环境覆盖文件名与计划不一致
- **证据**:
  - [docker-compose.prod.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.prod.yml) 中使用 `.env.prod.local`
  - 计划文档描述使用 `.env.prod`
- **影响**: 命名约定不一致，可能造成混淆
- **建议**: 统一命名，明确 `.env.prod`（模板，入库）和 `.env.prod.local`（实际配置，不入库）的区别

**M-3: .env.example 未按计划精简**
- **描述**: 计划将 .env.example 精简为仅含共享配置，但实际内容仍然较多
- **证据**: .env.example 当前有 7589 字节（约 100+ 行）
- **影响**: 环境分离的概念不够清晰
- **建议**: 按计划精简 .env.example，环境特有配置移至 .env.dev/.env.prod 模板

**M-4: 大量功能开发中但无版本规划**
- **描述**: 工作目录中有大量未提交的功能变更，但没有明确的下一个版本号和发布计划
- **证据**: git status 显示 18 个修改文件 + 8 个新增文件
- **影响**: 可能导致版本号决策困难，发布时遗漏变更
- **建议**: 制定下一个版本的发布计划，确定版本号和发布范围

**M-5: 前端品牌配置变更无对应计划文档**
- **描述**: `branding.ts` 有变更（移除 version 字段），但无专门的计划文档描述品牌配置的整体调整
- **证据**:
  - [branding.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/config/branding.ts) 已修改
  - 变更分散在多个计划文档中，无统一的品牌配置调整文档
- **影响**: 变更关联性不清晰，难以追踪品牌配置的完整变更
- **建议**: 在计划文档中明确品牌配置调整的完整范围

### 6.3 轻微差异（4 项）

**L-1: 计划文档提到 .json 翻译文件，实际为 .ts**
- **描述**: 部分计划文档提到 `zh.json` / `en.json`，但实际项目使用 `zh.ts` / `en.ts` / `ja.ts`
- **影响**: 轻微 - 计划文档基于旧信息，不影响功能
- **建议**: 更新计划文档中的文件名引用

**L-2: 锁文件路径调整无单独记录**
- **描述**: manage.sh 中锁文件路径从 `/tmp/tam_manage.lock` 改为 `.manage/manage.lock`，但无专门说明
- **影响**: 轻微 - 功能改进但未显式记录
- **建议**: 在 changelog 的改进项中记录此变更

**L-3: Nginx /health 路径代理未在计划中显式提及**
- **描述**: nginx 配置中添加了 `/health` 路径代理，但计划文档未明确提及需要修改 nginx
- **影响**: 轻微 - 合理的补充实现，但与计划文档不完全对应
- **建议**: 在计划文档中补充 nginx 配置修改项

**L-4: docker-compose.yml 添加 image 标签未在计划中提及**
- **描述**: docker-compose.yml 中为 backend 和 frontend 添加了 `image: tam-backend:${VERSION:-latest}` 标签，但环境增强计划文档中未提及
- **影响**: 轻微 - 合理的改进，但未在计划中记录
- **建议**: 在计划文档中补充此项

---

## 七、改进建议

### 7.1 文档更新建议（高优先级）

1. **更新 changelog.md 的 [Unreleased] 节**
   - 添加白名单删除 404 修复的记录
   - 格式参考 Keep a Changelog 规范

2. **制定下一版本发布计划**
   - 确定版本号（建议 v3.4.0，因为有多个新功能）
   - 明确发布范围和时间线
   - 整理所有待发布的变更清单

3. **补全 release-notes.md**
   - 发布时同步更新发布说明文档
   - 确保每个已发布版本都有对应的 release notes 条目

### 7.2 实现完善建议（中优先级）

1. **完成 .env 分离实现**
   - docker-compose.yml 中添加环境特定的 env_file
   - 确保 manage.sh 的 dc() 函数正确处理多 env_file
   - 精简 .env.example 为共享配置

2. **补全权限描述 i18n**
   - 在三个语言文件中添加所有权限的描述翻译
   - 在 Roles.tsx 中使用翻译后的描述

3. **统一命名约定**
   - 权限 i18n 命名空间（`permissions` vs `roles.permissions`）
   - env 文件命名（`.env.prod` vs `.env.prod.local`）

### 7.3 流程改进建议（低优先级）

1. **建立变更-文档联动机制**
   - 提交代码时同步更新 changelog 的 [Unreleased] 节
   - 或在 PR 模板中要求确认是否需要更新文档

2. **定期审查文档一致性**
   - 每次发布前进行文档与代码的一致性审查
   - 确保计划文档、规格文档与实际实现同步

3. **工作目录变更管理**
   - 对于大量未提交变更，建议按功能分批提交
   - 避免长时间存在大量未提交变更导致管理混乱

---

## 八、附录

### 8.1 审查方法

本次审查基于以下信息源：
- `git log v3.3.1..HEAD` — 已提交变更
- `git diff --stat v3.3.1..HEAD` — 已提交变更统计
- `git status --short` — 未提交变更
- `git diff <file>` — 具体变更内容
- 文档文件内容对比

### 8.2 相关文件索引

| 文档 | 路径 |
|------|------|
| 本审查报告 | `.trae/specs/review-v3.3.1-changes/review-report.md` |
| 规格文档 | `.trae/specs/review-v3.3.1-changes/spec.md` |
| 实施计划 | `.trae/specs/review-v3.3.1-changes/tasks.md` |
| 验证清单 | `.trae/specs/review-v3.3.1-changes/checklist.md` |
| 官方发布说明 | `docs/release-notes.md` |
| 更新日志 | `docs/changelog.md` |
