# v3.3.1 以来变更与文档匹配程度审查 - 实施计划

## [x] Task 1: 收集 v3.3.1 以来所有代码变更
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 使用 git 命令获取 v3.3.1 以来的所有已提交变更
  - 检查工作目录中的未提交变更
  - 按功能领域对变更进行分组
  - 建立完整的变更清单
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: `git log --oneline v3.3.1..HEAD` 列出所有提交
  - `programmatic` TR-1.2: `git diff --stat v3.3.1..HEAD` 列出已提交变更的文件统计
  - `programmatic` TR-1.3: `git status --short` 列出未提交变更文件
  - `human-judgement` TR-1.4: 变更按功能领域（前端/后端/DevOps/文档）正确分组
- **Notes**: 未提交变更包括已修改和新增的文件

## [x] Task 2: 文档匹配审查 — 官方发布文档
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - 检查 docs/release-notes.md 中 v3.3.1 之后的条目
  - 检查 docs/changelog.md 中 v3.3.1 之后的条目
  - 对比官方文档记录与实际代码变更
  - 识别：有记录的变更 / 缺失记录的变更 / 文档描述不准确的变更
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: release-notes.md 中存在 v3.3.1 之后的版本条目
  - `programmatic` TR-2.2: changelog.md 中存在 v3.3.1 之后的版本条目
  - `human-judgement` TR-2.3: 每个代码变更都有对应的文档记录（或明确标记为缺失）
  - `human-judgement` TR-2.4: 文档描述与实际代码变更内容一致

## [x] Task 3: 文档匹配审查 — 计划与规格文档
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - 审阅 .trae/documents/ 中所有相关计划文档
  - 审阅 .trae/specs/ 中所有相关规格文档
  - 将计划文档中的功能点与实际代码变更对比
  - 识别：已实现的计划 / 部分实现的计划 / 未实现的计划 / 计划外的变更
- **Acceptance Criteria Addressed**: AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: 列出 .trae/documents/ 和 .trae/specs/ 中所有相关文档
  - `human-judgement` TR-3.2: 每个计划文档中的功能点都有实现状态标记（已实现/部分/未实现）
  - `human-judgement` TR-3.3: 计划外的变更被识别并记录

## [x] Task 4: 版本号一致性检查
- **Priority**: P1
- **Depends On**: Task 1
- **Description**:
  - 检查所有定义版本号的位置
  - 验证版本号是否一致
  - 记录不一致的情况和原因
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: manage.sh 中的 VERSION 变量
  - `programmatic` TR-4.2: backend/app/core/config.py 中的 VERSION
  - `programmatic` TR-4.3: frontend/package.json 中的 version
  - `programmatic` TR-4.4: .env.example 中的 VERSION
  - `human-judgement` TR-4.5: 所有位置版本号一致，或明确记录不一致的合理性

## [x] Task 5: 差异分析与分类
- **Priority**: P0
- **Depends On**: Task 2, Task 3, Task 4
- **Description**:
  - 汇总所有审查发现的差异
  - 按严重程度分类（严重/中等/轻微）
  - 为每个差异提供证据和说明
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `human-judgement` TR-5.1: 严重差异定义明确且被正确分类
  - `human-judgement` TR-5.2: 中等差异定义明确且被正确分类
  - `human-judgement` TR-5.3: 轻微差异定义明确且被正确分类
  - `programmatic` TR-5.4: 每个差异都关联到具体的文件和行号

## [x] Task 6: 生成审查报告
- **Priority**: P0
- **Depends On**: Task 5
- **Description**:
  - 整合所有审查结果
  - 生成结构化的审查报告
  - 包含执行摘要、详细发现、改进建议
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `human-judgement` TR-6.1: 报告结构完整（摘要/总览/详细/建议）
  - `human-judgement` TR-6.2: 报告中的每个断言都有证据支持（文件路径+行号）
  - `human-judgement` TR-6.3: 改进建议具体可行
- **Notes**: 报告是本审查任务的最终交付物
