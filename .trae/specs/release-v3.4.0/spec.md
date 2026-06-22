# TerminalAccessManager v3.4.0 版本发布 - Product Requirement Document

## Overview
- **Summary**: 发布 v3.4.0 版本，包含系统版本与环境信息展示、角色权限国际化完善、部署环境配置分离、白名单删除修复等功能增强和问题修复。
- **Purpose**: 提升系统可观测性（版本/环境显示）、完善国际化覆盖、优化多环境部署配置、修复已知问题，为下阶段功能迭代奠定稳定基础。
- **Target Users**: 系统管理员、运维人员、终端用户

## Goals
- 系统版本号和部署环境在前端页脚和 Dashboard 系统状态中可见
- 角色权限名称和描述实现完整的三语言国际化（中/英/日）
- 支持多环境配置分离（.env + .env.${ENVIRONMENT}）
- 修复白名单删除 404 错误
- 修复超管用户初始化角色分配问题
- 所有版本号统一更新为 v3.4.0
- 文档同步更新，发布记录完整

## Non-Goals (Out of Scope)
- 新增业务功能模块（如新增数据源类型、新增权限模型等）
- 大规模架构重构
- UI/UX 大改版
- 数据库 Schema 破坏性变更
- 新增除中/英/日之外的语言支持

## Background & Context
### 当前版本状态
- **当前稳定版本**: v3.3.1（main 分支，tag: v3.3.1）
- **开发分支**: develop（领先 main 1 个提交：a7e2560 - 白名单删除修复）
- **生产就绪评分**: 9.0/10

### 已完成但未发布的变更
1. 白名单删除 404 修复（commit a7e2560）- 已提交到 develop，未记录到 changelog
2. Nginx 镜像版本锁定为 1.27-alpine
3. 页脚版本显示与 Dashboard 系统状态增强（部分实现）
4. 角色权限 i18n 部分实现
5. 超管角色初始化修复

### 技术栈
- 后端: Python 3.11 + FastAPI + SQLAlchemy 2.0 + PostgreSQL + Redis
- 前端: React 18 + TypeScript + Vite + Zustand + i18next
- 部署: Docker Compose + Nginx
- 运维: manage.sh 统一管理脚本

## Functional Requirements

### FR-1: 系统版本与环境信息展示
- 前端页脚显示系统版本号（v3.4.0）
- Dashboard 系统状态页面显示当前版本号
- Dashboard 系统状态页面显示部署环境（development/production）
- 版本信息通过后端 `/health` API 获取
- 前端通过 branding store 管理版本和环境状态

### FR-2: 角色权限国际化完整实现
- 5 个内置角色名称支持三语言（中/英/日）
- 5 个内置角色描述支持三语言
- 29 个权限名称支持三语言
- 29 个权限描述支持三语言
- 角色管理页面权限列表正确显示翻译后的名称
- 权限列标题翻译键命名无冲突

### FR-3: 多环境配置分离
- docker-compose.yml 支持 env_file 两层加载（.env + .env.${ENVIRONMENT}）
- backend 服务加载两层环境变量
- frontend 服务加载两层环境变量
- .env.example 精简为通用配置模板
- manage.sh 支持多环境 .env 文件管理

### FR-4: 白名单删除修复
- 白名单删除端点支持查询参数方式（DELETE /?identifier=）
- 支持按 MAC 删除、按 IP 删除、按复合条目删除
- 删除后自动触发合规状态重算
- 删除操作记录审计日志

### FR-5: 超管角色初始化修复
- 数据库初始化时 admin 用户正确关联 superadmin 角色
- RBAC 种子数据确保 superadmin 角色存在
- 已存在的 admin 用户角色修复逻辑

### FR-6: 版本号统一更新
- manage.sh VERSION 更新为 3.4.0
- backend/config.py VERSION 更新为 3.4.0
- frontend/package.json version 更新为 3.4.0
- .env.example VERSION 更新为 3.4.0
- 所有文档版本号更新为 v3.4.0

### FR-7: 文档与发布记录
- changelog.md 添加 v3.4.0 条目
- release-notes.md 添加 v3.4.0 详细发布记录
- release-plan.md 更新为 v3.4.0
- 所有技术文档版本号同步更新

## Non-Functional Requirements

### NFR-1: 向后兼容性
- 所有变更向后兼容，不破坏现有 API 接口
- 数据库无需破坏性迁移
- 现有配置文件兼容新版本

### NFR-2: 性能影响
- 版本信息获取不增加显著延迟（< 10ms）
- i18n 翻译不影响页面渲染性能
- 多环境配置加载不增加启动时间

### NFR-3: 安全性
- 版本信息展示不泄露敏感信息
- 环境配置文件权限正确
- 多环境分离不降低安全配置标准

### NFR-4: 可测试性
- 后端单元测试全部通过
- 前端单元测试全部通过
- CI 流水线 6 个 Job 全部通过

## Constraints
- **技术**: 必须使用现有技术栈，不引入新的核心依赖
- **业务**: 版本号必须遵循语义化版本规范（Semantic Versioning）
- **时间**: 发布准备工作应在 1 个工作日内完成
- **流程**: 必须遵循 GitFlow 分支策略（develop → main → tag）

## Assumptions
- 当前 develop 分支代码可正常构建和运行
- CI/CD 流水线正常工作
- 所有已提交的 Bug 修复均经过基本验证
- 文档更新仅涉及版本号和新增功能描述

## Acceptance Criteria

### AC-1: 页脚版本号显示
- **Given**: 用户已登录系统
- **When**: 查看页面底部页脚
- **Then**: 页脚显示正确的版本号 "v3.4.0"
- **Verification**: `human-judgment`

### AC-2: Dashboard 系统状态显示版本与环境
- **Given**: 用户已登录并访问 Dashboard
- **When**: 查看系统状态卡片
- **Then**: 显示当前版本号 "v3.4.0" 和部署环境（development/production）
- **Verification**: `human-judgment`

### AC-3: 权限国际化完整
- **Given**: 用户访问角色管理页面
- **When**: 切换语言（中/英/日），查看角色列表和权限列表
- **Then**: 所有角色名称、角色描述、权限名称、权限描述均正确显示对应语言
- **Verification**: `human-judgment`

### AC-4: docker-compose 多环境配置
- **Given**: 项目根目录存在 .env 和 .env.production 文件
- **When**: 执行 `docker-compose config`
- **Then**: backend 和 frontend 服务正确加载两层环境变量
- **Verification**: `programmatic`

### AC-5: 白名单删除功能正常
- **Given**: 系统中存在白名单条目
- **When**: 调用删除 API 或在前端点击删除
- **Then**: 删除成功，返回 200，合规状态自动更新
- **Verification**: `programmatic`

### AC-6: 超管角色正确分配
- **Given**: 全新部署，执行数据库初始化
- **When**: 查询 admin 用户的角色
- **Then**: admin 用户关联 superadmin 角色
- **Verification**: `programmatic`

### AC-7: 版本号统一
- **Given**: 发布准备完成
- **When**: 检查 manage.sh、config.py、package.json、.env.example 中的版本号
- **Then**: 所有位置版本号均为 "3.4.0"
- **Verification**: `programmatic`

### AC-8: CI 验证通过
- **Given**: 代码提交到 develop 并创建 PR
- **When**: CI 流水线执行完成
- **Then**: 所有 6 个 Job（backend-lint/backend-test/frontend-lint/frontend-test/backend-build/frontend-build）全部通过
- **Verification**: `programmatic`

### AC-9: 文档完整
- **Given**: 发布完成
- **When**: 检查 changelog.md、release-notes.md
- **Then**: v3.4.0 条目完整，包含所有变更说明
- **Verification**: `human-judgment`

### AC-10: 向后兼容
- **Given**: v3.3.1 版本正常运行的系统
- **When**: 升级到 v3.4.0
- **Then**: 所有现有功能正常工作，数据无丢失，配置兼容
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要在 v3.4.0 中包含 manage.sh 多环境支持的完整实现？
- [ ] .env.example 精简的具体范围（保留哪些、移除哪些）？
- [ ] 是否需要更新生产就绪评估文档（production-readiness-assessment.md）？
