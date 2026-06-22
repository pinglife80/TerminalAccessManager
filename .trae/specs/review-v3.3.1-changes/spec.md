# v3.3.1 以来变更与文档匹配程度审查 - 产品需求文档

## Overview
- **Summary**: 对 Terminal Access Manager 项目自 v3.3.1 版本以来的所有代码变更进行全面审查，对比计划文档、官方发布文档与实际代码实现的匹配程度，识别差异、遗漏和不一致。
- **Purpose**: 确保代码变更有对应的文档记录，计划中的功能已正确实现，发布文档准确反映实际变更内容。
- **Target Users**: 项目维护者、版本发布管理者、质量保证人员。

## Goals
- 完整梳理 v3.3.1 以来所有代码变更（已提交 + 未提交）
- 验证每个变更是否有对应的文档记录
- 验证计划文档中的功能是否已正确实现
- 识别文档与实现的不一致
- 输出结构化的审查报告和改进建议

## Non-Goals (Out of Scope)
- 不修改任何代码或文档（仅审查，不修复）
- 不做功能测试验证（仅静态审查）
- 不审查 v3.3.1 及更早版本的内容
- 不审查第三方依赖和库的版本
- 不审查设计文档和架构文档的完整性

## Background & Context

### v3.3.1 版本基线
v3.3.1 是一个热修复版本，主要修复黑名单显示已解封记录的问题。该版本已打 tag，release-notes.md 和 changelog.md 均有记录。

### 当前状态
- v3.3.1 之后有 1 个已提交（白名单删除 404 修复）
- 工作目录中有大量未提交变更，涉及多个功能领域
- .trae/documents/ 中有多份计划文档，描述了计划中的功能改进
- .trae/specs/ 中有规格文档，记录了部分功能的详细需求

### 涉及的主要变更领域
1. 页脚版本号显示（从后端 /health API 获取）
2. Dashboard 系统状态新增版本和环境显示
3. 角色和权限 i18n 国际化
4. 超管角色初始化修复
5. 开发环境增强（热重载、HMR、端口暴露）
6. .env 文件分离（dev/prod 环境隔离）
7. manage.sh 脚本优化
8. Nginx 配置调整
9. 品牌配置调整
10. 白名单删除功能修复

## Functional Requirements

- **FR-1**: 变更清单梳理 - 完整列出 v3.3.1 以来所有代码变更，按功能领域分组
- **FR-2**: 文档匹配审查 - 对每个变更，检查是否有对应的文档记录（release-notes、changelog、计划文档、规格文档）
- **FR-3**: 实现完整性审查 - 对每个计划文档中的功能，检查是否已在代码中实现，以及实现是否符合计划
- **FR-4**: 版本号一致性检查 - 验证所有版本号位置（manage.sh、config.py、package.json、.env.example）是否一致
- **FR-5**: 差异识别 - 识别文档与实现不一致的地方，按严重程度分类
- **FR-6**: 审查报告输出 - 生成结构化的审查报告，包含发现、分类和建议

## Non-Functional Requirements

- **NFR-1**: 准确性 - 审查结果必须准确反映代码库的实际状态
- **NFR-2**: 可追溯性 - 每个发现都必须有对应的文件路径和行号作为证据
- **NFR-3**: 完整性 - 覆盖 v3.3.1 以来所有有意义的代码变更
- **NFR-4**: 清晰性 - 审查报告结构清晰，易于理解和行动

## Constraints
- **Technical**: 仅基于 git 历史和静态代码分析，不运行代码
- **Business**: 审查范围限于 v3.3.1 之后的变更
- **Dependencies**: 依赖 git 历史、文件系统和文档内容

## Assumptions
- v3.3.1 tag 正确标记了该版本的代码状态
- .trae/documents/ 中的计划文档代表了计划中的变更
- docs/ 目录下的 release-notes.md 和 changelog.md 是官方发布文档
- 工作目录中的未提交变更代表正在进行中的工作

## Acceptance Criteria

### AC-1: 变更清单完整
- **Given**: v3.3.1 tag 存在且正确
- **When**: 执行变更清单梳理
- **Then**: 所有 v3.3.1 以来的代码变更都被列出，包括已提交和未提交的
- **Verification**: `programmatic`
- **Notes**: 通过 `git diff --stat v3.3.1..HEAD` 和 `git status` 验证完整性

### AC-2: 文档匹配分析覆盖所有变更
- **Given**: 完整的变更清单
- **When**: 执行文档匹配审查
- **Then**: 每个变更都被分类为：有官方文档记录 / 有计划文档记录 / 无文档记录
- **Verification**: `programmatic`
- **Notes**: 分类结果必须有明确的文档链接作为证据

### AC-3: 实现完整性审查覆盖所有计划
- **Given**: .trae/documents/ 中的所有计划文档
- **When**: 执行实现完整性审查
- **Then**: 每个计划中的功能点都被标记为：已实现 / 部分实现 / 未实现
- **Verification**: `programmatic`
- **Notes**: 每个标记都必须有对应的代码文件作为证据

### AC-4: 版本号一致性验证
- **Given**: 项目中有多个版本号定义位置
- **When**: 执行版本号一致性检查
- **Then**: 所有位置的版本号一致，或明确记录不一致的原因
- **Verification**: `programmatic`
- **Notes**: 检查位置包括 manage.sh、backend/config.py、frontend/package.json、.env.example

### AC-5: 差异按严重程度分类
- **Given**: 识别出的所有文档与实现差异
- **When**: 执行差异分类
- **Then**: 差异被分为：严重（功能缺失/文档错误）、中等（部分实现/描述不一致）、轻微（命名差异/格式问题）
- **Verification**: `human-judgment`
- **Notes**: 分类标准需在报告中明确定义

### AC-6: 审查报告结构完整
- **Given**: 所有审查发现
- **When**: 生成审查报告
- **Then**: 报告包含：执行摘要、变更总览、详细审查结果、差异列表、改进建议
- **Verification**: `human-judgment`
- **Notes**: 报告必须包含具体的文件路径和行号引用

## Open Questions
- [ ] 未提交的变更是否应该被纳入审查范围？还是只审查已提交的？
- [ ] .trae/documents/ 中的计划文档是否应该被视为"官方文档"的一部分？
- [ ] 审查发现的问题是否需要在本次 spec 中安排修复？还是仅输出报告？
