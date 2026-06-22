# TerminalAccessManager v3.4.0 版本发布 - 实施计划

## 任务概览
共 16 个任务，分为 5 个阶段：
- 阶段一：代码修复与补全（Task 1-4）
- 阶段二：版本号与文档更新（Task 5-8）
- 阶段三：提交与 CI 验证（Task 9-11）
- 阶段四：合并与发布（Task 12-14）
- 阶段五：发布后验证（Task 15-16）

---

## [ ] Task 1: 补全权限描述 i18n 翻译
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 验证并补全 en.ts、zh.ts、ja.ts 中所有 29 个权限的描述翻译（`${code}_desc` 格式）
  - 验证角色名称和描述翻译完整性
  - 确保翻译键命名无冲突（permissionsColumn 与 permissions 对象分离）
  - 确保 i18n 配置中 `nsSeparator: false` 已正确设置（避免权限代码中冒号被解析为命名空间分隔符）
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-1.1: 三种语言文件中每个权限代码都有对应的 name 和 desc 翻译键
  - `programmatic` TR-1.2: Roles.tsx 中权限列标题使用正确的翻译键（permissionsColumn）
  - `human-judgement` TR-1.3: 角色管理页面切换三种语言，权限名称和描述均正确显示
- **Notes**: 已部分完成，需验证完整性

## [ ] Task 2: 完善 docker-compose env_file 环境覆盖
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - docker-compose.yml 中 backend 和 frontend 服务的 env_file 从单层 `.env` 改为两层：`.env` + `.env.${ENVIRONMENT:-development}`
  - 确保环境变量覆盖顺序正确（后加载的覆盖先加载的）
  - 验证 nginx 服务是否需要 env_file（按需添加）
- **Acceptance Criteria Addressed**: AC-4, AC-10
- **Test Requirements**:
  - `programmatic` TR-2.1: 创建 .env 和 .env.production 测试文件，执行 `docker compose config` 验证变量覆盖
  - `programmatic` TR-2.2: 同时存在 .env 和 .env.development 时，development 优先级正确
  - `programmatic` TR-2.3: 缺少 .env.${ENVIRONMENT} 文件时不报错（有默认值）
- **Notes**: 与 manage.sh 多环境支持协同

## [ ] Task 3: 验证 manage.sh 多环境 .env 支持
- **Priority**: P1
- **Depends On**: Task 2
- **Description**: 
  - 检查 manage.sh 中 ensure_env 函数是否支持多环境 .env 文件
  - deploy 命令根据 --dev/--prod 参数创建对应环境的 .env 文件
  - 确保 .env.example 可作为通用模板
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-3.1: `./manage.sh deploy --dev` 创建 .env.development
  - `programmatic` TR-3.2: `./manage.sh deploy --prod` 创建 .env.production
  - `human-judgement` TR-3.3: 环境变量加载逻辑清晰，文档有说明
- **Notes**: 可选增强项，如时间紧张可延后到 v3.5.0

## [ ] Task 4: 验证白名单删除修复
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 验证白名单删除端点（DELETE /api/v1/whitelist/）已从路径参数改为查询参数
  - 验证支持按 identifier（IP/MAC/复合）删除
  - 验证删除后合规状态自动重算
  - 验证审计日志记录正确
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-4.1: `DELETE /api/v1/whitelist/?identifier=<value>` 返回 200
  - `programmatic` TR-4.2: 删除后终端合规状态正确更新
  - `programmatic` TR-4.3: 删除操作有对应审计日志记录
- **Notes**: 代码已提交（a7e2560），需验证和补充测试

## [ ] Task 5: 验证超管角色初始化修复
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 验证 cli.py 中 _create_admin_user() 函数创建 admin 用户后正确关联 superadmin 角色
  - 验证 _ensure_rbac_seed() 函数中 admin 用户角色修复逻辑
  - 验证全新初始化场景下 admin 用户角色正确
  - 验证已存在 admin 用户但角色不正确时的修复逻辑
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-5.1: 全新数据库 init 后，admin 用户的角色为 superadmin
  - `programmatic` TR-5.2: user_roles 表中有 admin-superadmin 关联记录
  - `programmatic` TR-5.3: 重复执行 init 不会创建重复角色关联
- **Notes**: 代码已修改，需验证

## [ ] Task 6: 统一更新版本号
- **Priority**: P0
- **Depends On**: Task 1, Task 2, Task 4, Task 5
- **Description**: 
  - 更新 `manage.sh` 中 VERSION 从 "3.3.1" 到 "3.4.0"
  - 更新 `backend/app/core/config.py` 中 VERSION 从 "3.3.1" 到 "3.4.0"
  - 更新 `frontend/package.json` 中 version 从 "3.3.1" 到 "3.4.0"
  - 更新 `.env.example` 中 VERSION 从 "3.3.1" 到 "3.4.0"
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-6.1: grep 所有版本号位置，确认均为 "3.4.0"
  - `programmatic` TR-6.2: /health API 返回的 version 字段为 "3.4.0"
  - `programmatic` TR-6.3: manage.sh version 命令输出 "3.4.0"
- **Notes**: 必须在所有代码变更完成后执行此任务

## [ ] Task 7: 更新 changelog.md
- **Priority**: P0
- **Depends On**: Task 6
- **Description**: 
  - 将 `[Unreleased]` 下的所有条目移入新的 `[3.4.0] - YYYY-MM-DD` 版本块
  - 添加新的空 `[Unreleased]` 占位
  - 确保条目分类正确（Added/Changed/Fixed）
  - 包含白名单删除修复、权限 i18n、环境配置分离、版本显示等所有变更
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `human-judgement` TR-7.1: changelog 格式符合 Keep a Changelog 规范
  - `human-judgement` TR-7.2: [3.4.0] 条目完整覆盖所有变更
  - `programmatic` TR-7.3: [Unreleased] 区块存在且为空
- **Notes**: 需仔细核对所有 commit，确保无遗漏

## [ ] Task 8: 更新 release-notes.md 和所有文档版本号
- **Priority**: P0
- **Depends On**: Task 7
- **Description**: 
  - release-notes.md 新增 `[v3.4.0]` 版本记录，包含详细变更说明、提交记录、文件变更清单
  - 更新 release-plan.md 为 v3.4.0 发布方案
  - 更新所有技术文档的版本号从 v3.3.1/v3.3.0 到 v3.4.0
  - 更新所有文档的日期为发布日期
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `human-judgement` TR-8.1: release-notes.md v3.4.0 条目内容完整（功能列表、提交记录、文件清单）
  - `programmatic` TR-8.2: 所有 docs/ 目录下文档的版本号均更新为 v3.4.0
  - `human-judgement` TR-8.3: 文档版本号和日期格式统一
- **Notes**: 文档清单参考 release-plan.md 中的文件列表

## [ ] Task 9: 提交发布准备代码到 develop
- **Priority**: P0
- **Depends On**: Task 6, Task 7, Task 8
- **Description**: 
  - 将所有版本更新和文档修改提交到 develop 分支
  - 使用规范的 commit message: `release: prepare v3.4.0 release`
  - 推送到远程仓库
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-9.1: develop 分支包含所有发布准备变更
  - `programmatic` TR-9.2: commit message 符合 Conventional Commits 规范
  - `programmatic` TR-9.3: 无未提交的变更
- **Notes**: 提交前确保所有测试通过

## [ ] Task 10: 创建 PR 并验证 CI
- **Priority**: P0
- **Depends On**: Task 9
- **Description**: 
  - 创建 Pull Request: develop → main
  - PR 标题: "Release v3.4.0"
  - PR 描述从 release-notes.md 复制 v3.4.0 内容
  - 等待 CI 流水线 6 个 Job 全部通过
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-10.1: CI 6 个 Job（backend-lint/backend-test/frontend-lint/frontend-test/backend-build/frontend-build）全部通过
  - `programmatic` TR-10.2: 无新引入的 lint 错误
  - `programmatic` TR-10.3: 所有现有测试用例通过
- **Notes**: 如 CI 失败，修复后重新提交

## [ ] Task 11: 本地构建与功能验证
- **Priority**: P0
- **Depends On**: Task 9
- **Description**: 
  - 本地执行 `./manage.sh update` 重建镜像
  - 执行 `./manage.sh health` 验证所有服务健康
  - 执行 `./manage.sh test` 运行后端测试
  - 手动验证核心功能：登录、终端管理、白名单、黑名单、角色管理、Dashboard
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-5, AC-6, AC-10
- **Test Requirements**:
  - `programmatic` TR-11.1: 5 个服务全部 healthy
  - `programmatic` TR-11.2: 后端单元测试全部通过
  - `human-judgement` TR-11.3: 核心功能页面正常访问和操作
  - `human-judgement` TR-11.4: 页脚和 Dashboard 显示正确版本号和环境
- **Notes**: 与 CI 验证可并行进行

## [ ] Task 12: 合并 PR 到 main
- **Priority**: P0
- **Depends On**: Task 10, Task 11
- **Description**: 
  - CI 通过且本地验证通过后，合并 PR 到 main 分支
  - 使用 Merge commit 方式（非 Squash）
  - 确保 main 分支历史完整
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-12.1: main 分支包含 develop 的所有变更
  - `programmatic` TR-12.2: 合并后 main 分支 CI 通过
  - `programmatic` TR-12.3: 无合并冲突
- **Notes**: 合并前确保所有验收标准已满足

## [ ] Task 13: 创建并推送 Git Tag
- **Priority**: P0
- **Depends On**: Task 12
- **Description**: 
  - 切换到 main 分支，拉取最新代码
  - 创建 annotated tag: `git tag -a v3.4.0 -m "release v3.4.0: version display, i18n completion, env separation, bug fixes"`
  - 推送 tag 到远程仓库
  - 同步 develop 分支（merge main）
- **Acceptance Criteria Addressed**: AC-7, AC-9
- **Test Requirements**:
  - `programmatic` TR-13.1: `git tag -l v3.4.0` 存在
  - `programmatic` TR-13.2: `git ls-remote --tags origin` 包含 v3.4.0
  - `programmatic` TR-13.3: tag 指向 main 分支的正确 commit
  - `programmatic` TR-13.4: develop 分支已同步 main（包含 tag）
- **Notes**: tag 名称必须为 v3.4.0（带 v 前缀）

## [ ] Task 14: 创建 GitHub Release
- **Priority**: P1
- **Depends On**: Task 13
- **Description**: 
  - 在 GitHub Releases 页面创建 v3.4.0 Release
  - 选择 tag: v3.4.0
  - 标题: "v3.4.0"
  - 内容从 release-notes.md 复制 [v3.4.0] 部分
  - 标记为正式发布（非 Pre-release）
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `human-judgement` TR-14.1: GitHub Release 页面显示正确
  - `human-judgement` TR-14.2: Release Notes 格式清晰，分类完整
  - `programmatic` TR-14.3: Release 关联正确的 tag 和 commit
- **Notes**: 如使用 GitHub CLI 可自动化

## [ ] Task 15: 发布后验证
- **Priority**: P0
- **Depends On**: Task 13
- **Description**: 
  - 验证从 v3.3.1 升级到 v3.4.0 的流程
  - 使用 `./manage.sh upgrade v3.4.0` 测试升级
  - 验证升级后所有功能正常
  - 验证数据完整性
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-15.1: upgrade 命令执行成功
  - `programmatic` TR-15.2: 升级后版本号显示为 v3.4.0
  - `programmatic` TR-15.3: 升级后数据库表结构和数据完整
  - `human-judgement` TR-15.4: 核心功能正常工作
- **Notes**: 建议在测试环境中进行

## [ ] Task 16: 回滚预案验证
- **Priority**: P1
- **Depends On**: Task 15
- **Description**: 
  - 验证从 v3.4.0 回滚到 v3.3.1 的可行性
  - 测试 `./manage.sh upgrade v3.3.1` 回滚
  - 验证回滚后系统正常
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-16.1: 回滚命令执行成功
  - `programmatic` TR-16.2: 回滚后版本号为 v3.3.1
  - `programmatic` TR-16.3: 回滚后功能正常
- **Notes**: 确保回滚预案有效，以备紧急情况
