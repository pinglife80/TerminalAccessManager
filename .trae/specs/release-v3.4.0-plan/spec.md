# v3.4.0 版本发布方案 - 产品需求文档

## Overview
- **Summary**: 制定 Terminal Access Manager v3.4.0 版本的完整发布方案，包括功能范围、发布流程、文档更新、验证标准和回滚计划。
- **Purpose**: 确保 v3.4.0 版本有序、高质量发布，整合 v3.3.1 以来的所有功能改进和 Bug 修复。
- **Target Users**: 项目维护者、版本发布管理者、运维人员。

## Goals
- 整合 v3.3.1 以来的所有功能改进到 v3.4.0 版本
- 确保所有功能经过完整测试和验证
- 确保所有文档与代码实现同步更新
- 提供清晰的发布流程和回滚方案
- 最小化发布风险

## Non-Goals (Out of Scope)
- 不添加 v3.4.0 范围之外的新功能
- 不进行架构重构
- 不更新第三方依赖版本
- 不处理历史遗留的低优先级 Bug
- 不进行数据库 schema 迁移

## Background & Context

### 当前版本状态
- **当前已发布版本**: v3.3.1（黑名单过滤热修复）
- **v3.3.1 后已提交**: 1 个提交（白名单删除 404 修复）
- **未提交变更**: 18 个修改文件 + 8 个新增文件，涵盖多个功能领域

### 版本号决策

| 方案 | 版本号 | 理由 | 选择 |
|------|--------|------|------|
| Patch | v3.3.2 | 仅 Bug 修复 | ❌ 有多个新功能 |
| **Minor** | **v3.4.0** | **新功能 + 改进 + Bug 修复，向后兼容** | ✅ 采用 |
| Major | v4.0.0 | 破坏性变更 | ❌ 无破坏性变更 |

**语义化版本依据**:
- **MINOR** 版本递增：新增功能 + 向后兼容的改进
- 新功能：页脚版本显示、Dashboard 系统状态、开发环境增强等
- 改进：.env 分离、manage.sh 优化、i18n 完善等
- 修复：白名单删除、超管角色初始化等

### 发布方式
采用 **GitFlow** 标准发布流程：
1. 从 develop 创建 release/v3.4.0 分支
2. 在 release 分支上完成版本号更新和文档收尾
3. 合并到 main 并打 tag
4. 同步回 develop

## 功能范围 (Release Scope)

### 新增功能 (New Features)

#### NF-1: 页脚系统版本显示
- 登录页和主布局 Footer 显示系统版本号
- 版本号从后端 `/health` API 动态获取
- 支持前端 branding store 状态管理
- **涉及文件**: 
  - [branding.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/store/branding.ts)
  - [Layout.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/Layout.tsx)
  - [Login.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Login.tsx)
  - [tam.conf](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf)

#### NF-2: Dashboard 系统状态增强
- System Status 卡片新增"系统版本"显示
- System Status 卡片新增"运行环境"显示（生产/开发）
- 环境显示支持 i18n 多语言
- **涉及文件**:
  - [Dashboard.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Dashboard.tsx)
  - 多语言翻译文件（en.ts, zh.ts, ja.ts）

#### NF-3: 开发环境增强
- 后端代码热重载（uvicorn --reload）
- 前端 HMR 热更新（Vite dev server）
- Postgres 端口暴露（5432）
- Redis 端口暴露（6379）
- 后端远程调试端口（5678, debugpy）
- 开发环境移除资源限制
- **涉及文件**:
  - [docker-compose.dev.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.dev.yml)
  - [Dockerfile.dev](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/Dockerfile.dev)

#### NF-4: .env 环境分离
- 共享配置存于 `.env`
- 开发环境覆盖存于 `.env.dev`
- 生产环境覆盖存于 `.env.prod`
- .env.example 精简为共享配置模板
- **涉及文件**:
  - [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml)
  - [docker-compose.prod.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.prod.yml)
  - `.env.dev`、`.env.prod`、`.env.example`

### 功能改进 (Improvements)

#### IMP-1: 角色权限 i18n 完善
- 修复权限列表头显示错误（"key 'roles.permissions (en)' returned an object instead of string"）
- 5 个内置角色描述支持国际化
- 权限名称支持国际化翻译
- 权限代码冒号不再被误解析为命名空间分隔符
- **涉及文件**:
  - [Roles.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Roles.tsx)
  - [index.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/index.ts)
  - 多语言翻译文件

#### IMP-2: manage.sh 脚本优化
- flock 原子锁替代文件锁，避免并发竞态
- printf -v 替代 eval，提升安全性
- 锁文件路径移至项目目录内（`.manage/manage.lock`）
- 新增强制日志函数 `_log_forced()`
- dc() 函数支持多 env_file
- **涉及文件**:
  - [manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh)

#### IMP-3: Docker Compose 优化
- 后端和前端服务添加固定 image 标签（含版本号）
- Nginx 镜像版本锁定（`nginx:1.27-alpine`）
- 上传目录改用 volume（`upload_data`）替代 tmpfs
- 添加 env_file 配置支持
- **涉及文件**:
  - [docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml)
  - [docker-compose.prod.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.prod.yml)

#### IMP-4: 品牌配置优化
- 移除前端硬编码版本号（`v2.0.0`）
- 版本号改为从后端 API 动态获取
- **涉及文件**:
  - [branding.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/config/branding.ts)

### Bug 修复 (Bug Fixes)

#### FIX-1: 白名单删除 404 错误
- 修复删除白名单条目时返回 404 的问题
- 删除端点从路径参数改为查询参数
- 增强删除逻辑，支持 MAC-only、IP-only、复合条目
- 新增单元测试覆盖多种删除场景
- **涉及文件**:
  - [whitelist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/whitelist.py)
  - [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py)
  - [Whitelist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Whitelist.tsx)
  - [test_whitelist.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/tests/test_whitelist.py)

#### FIX-2: 超管角色初始化错误
- 修复初始化 admin 用户时未分配 superadmin 角色的问题
- 确保 admin 用户在 `user_roles` 表中正确关联 superadmin 角色
- 修复前端显示为 "User" 而非 "Super Admin" 的问题
- **涉及文件**:
  - [cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py)

#### FIX-3: Nginx /health 路径代理
- 添加 `/health` 路径的反向代理配置
- 确保前端可直接访问后端健康检查接口
- 开发环境和生产环境同步配置
- **涉及文件**:
  - [tam.conf](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.conf)
  - [tam.dev.conf](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.dev.conf)

## 非功能性需求

- **NFR-1**: 向后兼容性 — v3.4.0 必须完全向后兼容，无破坏性变更
- **NFR-2**: 发布可靠性 — 所有功能必须通过完整测试验证后才能发布
- **NFR-3**: 文档一致性 — 所有功能变更必须同步更新相关文档
- **NFR-4**: 可回滚性 — 发布失败时可快速回滚到 v3.3.1
- **NFR-5**: 发布可重复性 — 发布过程可通过脚本自动化重复执行

## 约束条件

- **技术**: 基于现有技术栈，不引入新的依赖和框架
- **时间**: 建议在所有功能开发完成并通过测试后发布
- **流程**: 遵循 GitFlow 发布流程和现有 CI/CD 配置
- **数据**: 不涉及数据库 schema 变更和数据迁移

## 假设

- 所有未提交的变更都计划包含在 v3.4.0 中
- CI/CD 流水线正常工作，6 个 job 全部通过
- v3.3.1 版本的 tag 和代码状态正确
- 生产环境当前运行 v3.3.1 版本

## 验收标准

### AC-1: 版本号一致性
- **Given**: 发布准备完成
- **When**: 检查所有版本号定义位置
- **Then**: manage.sh、config.py、package.json、.env.example 中的版本号均为 v3.4.0
- **Verification**: `programmatic`

### AC-2: 功能完整性
- **Given**: v3.4.0 代码已合并到 main
- **When**: 对照功能范围清单逐一验证
- **Then**: 所有计划功能都已实现并集成
- **Verification**: `human-judgment`
- **Notes**: 每个功能点都有对应的代码文件作为证据

### AC-3: 文档同步更新
- **Given**: v3.4.0 发布完成
- **When**: 检查所有相关文档
- **Then**: release-notes.md、changelog.md 等文档包含 v3.4.0 的完整变更记录
- **Verification**: `human-judgment`
- **Notes**: 文档描述需与实际功能一致

### AC-4: CI/CD 全量通过
- **Given**: PR 已创建，CI 自动运行
- **When**: CI 执行完成
- **Then**: 所有 6 个 CI job 全部通过
- **Verification**: `programmatic`

### AC-5: 可成功部署
- **Given**: v3.4.0 已打 tag 并发布
- **When**: 在生产环境执行升级
- **Then**: `./manage.sh upgrade v3.4.0` 成功执行，服务正常运行
- **Verification**: `programmatic`

### AC-6: 可回滚
- **Given**: 已升级到 v3.4.0
- **When**: 发现严重问题需要回滚
- **Then**: 可在 5 分钟内回滚到 v3.3.1，且数据不丢失
- **Verification**: `human-judgment`

## 发布前待决项 (Pre-Release TODOs)

- [ ] 完成权限描述 i18n 翻译（当前仅名称有翻译）
- [ ] 完善 docker-compose.yml 的 env_file 环境覆盖配置
- [ ] 验证 .env 分离在 manage.sh 中的完整支持
- [ ] 精简 .env.example 为共享配置模板
- [ ] 所有功能代码提交到 develop 分支
- [ ] 补充或更新相关单元测试
- [ ] 前端构建测试通过（`npm run build`）
- [ ] 后端测试通过（`pytest`）
- [ ] lint 检查通过

## Open Questions

- [ ] v3.4.0 是否需要包含权限描述 i18n？还是推迟到下一个版本？
- [ ] .env 分离功能是否需要在本次版本中完全实现？
- [ ] manage.sh 的全部优化是否都要在 v3.4.0 中完成？
- [ ] 是否需要在发布前进行用户验收测试（UAT）？
- [ ] 发布后是否需要安排运维值守？
