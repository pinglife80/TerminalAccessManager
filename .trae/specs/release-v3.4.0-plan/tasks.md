# v3.4.0 版本发布方案 - 实施计划

## 发布流程总览

```
Phase 1: 开发收尾 → Phase 2: 发布准备 → Phase 3: 执行发布 → Phase 4: 发布后验证
```

---

## Phase 1: 开发收尾（Development Finalization）

### [x] Task 1: 补全权限描述 i18n 翻译
- **Priority**: P1
- **Depends On**: None
- **Description**:
  - 在 en.ts、zh.ts、ja.ts 中添加所有 29 个权限的描述翻译（`${code}_desc`）
  - 在 Roles.tsx 中使用翻译后的权限描述
  - 保持与现有权限名称翻译的一致性
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-1.1: 三个语言文件中均包含 29 个权限的 `_desc` 翻译键 ✓
  - `human-judgement` TR-1.2: Roles.tsx 中权限描述正确显示翻译文本 ✓
  - `human-judgement` TR-1.3: 三种语言切换均正常显示 ✓
- **Notes**: 如时间紧张可考虑推迟到 v3.4.1
- **Status**: 已完成 ✅

### [x] Task 2: 完善 docker-compose env_file 环境覆盖
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - docker-compose.yml 中添加环境特定的 env_file（`.env.${ENVIRONMENT:-development}`）
  - 确保 dev 和 prod 环境的差异配置能正确加载
  - 验证变量优先级（environment > env_file）
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: docker-compose.yml 中 backend 和 frontend 均有两行 env_file ✓
  - `programmatic` TR-2.2: `docker compose config` 能正确显示合并后的环境变量 ✓
  - `human-judgement` TR-2.3: .env.dev 中的 DEBUG=true 在开发环境生效 ✓
- **Notes**: 这是 .env 分离功能的核心部分
- **Status**: 已完成 ✅

### [ ] Task 3: 验证 manage.sh .env 分离支持
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - 验证 dc() 函数正确处理多 env_file
  - 验证 deploy --dev 生成 .env + .env.dev
  - 验证 deploy --prod 生成 .env + .env.prod
  - 验证 check_weak_defaults() 检查正确的文件
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-3.1: dc() 函数传递 `--env-file` 参数正确
  - `human-judgement` TR-3.2: `deploy --dev` 生成的文件内容正确
  - `human-judgement` TR-3.3: 环境切换时共享配置保持不变
- **Notes**: 需要实际运行测试验证

### [ ] Task 4: 精简 .env.example
- **Priority**: P2
- **Depends On**: None
- **Description**:
  - 将 .env.example 精简为仅含共享配置
  - 环境特有配置移至 .env.dev 和 .env.prod 模板
  - 添加注释说明环境分离的使用方式
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `human-judgement` TR-4.1: .env.example 只包含环境共享的配置项
  - `human-judgement` TR-4.2: .env.dev 和 .env.prod 包含各自的特有配置
  - `human-judgement` TR-4.3: 三个文件组合后配置完整无遗漏

---

## Phase 2: 发布准备（Release Preparation）

### [ ] Task 5: 代码提交与合并
- **Priority**: P0
- **Depends On**: Task 1, Task 2, Task 3, Task 4
- **Description**:
  - 将所有未提交的变更按功能分组提交
  - 确保每个提交信息符合 Conventional Commits 规范
  - 推送到 develop 分支
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-5.1: `git status` 显示无未提交变更
  - `programmatic` TR-5.2: 所有提交均有清晰的 type 前缀（feat/fix/improve/docs 等）
  - `human-judgement` TR-5.3: 提交粒度合理，按功能模块分组

### [ ] Task 6: 创建 release 分支
- **Priority**: P0
- **Depends On**: Task 5
- **Description**:
  - 从 develop 分支创建 `release/v3.4.0` 分支
  - 在 release 分支上进行版本号更新和文档收尾
  - 不允许在 release 分支上添加新功能，只允许修复发布阻塞问题
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-6.1: `release/v3.4.0` 分支存在且基于最新 develop
  - `programmatic` TR-6.2: release 分支与 develop 的差异仅限版本号和文档更新

### [x] Task 7: 更新版本号
- **Priority**: P0
- **Depends On**: Task 6
- **Description**:
  - manage.sh: VERSION="3.3.1" → "3.4.0"
  - backend/app/core/config.py: VERSION = "3.3.1" → "3.4.0"
  - frontend/package.json: "version": "3.3.1" → "3.4.0"
  - .env.example: VERSION=3.3.1 → 3.4.0
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-7.1: 所有 4 个位置的版本号均更新为 3.4.0 ✓
  - `programmatic` TR-7.2: `grep -r "3.3.1" --include="*.py" --include="*.sh" --include="*.json"` 无遗漏 ✓
  - `human-judgement` TR-7.3: 文档中的版本号引用需同步检查 ✓
- **Status**: 已完成 ✅

### [x] Task 8: 更新 changelog.md
- **Priority**: P0
- **Depends On**: Task 6
- **Description**:
  - 在 `[Unreleased]` 和 `[3.3.1]` 之间插入 `[3.4.0]` 条目
  - 按 Keep a Changelog 格式组织：Added / Changed / Fixed
  - 每个条目简明扼要，准确反映变更内容
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `human-judgement` TR-8.1: 新增功能（Added）部分完整列出所有新功能 ✓
  - `human-judgement` TR-8.2: 功能改进（Changed）部分完整列出所有改进 ✓
  - `human-judgement` TR-8.3: Bug 修复（Fixed）部分完整列出所有修复 ✓
  - `human-judgement` TR-8.4: 日期和版本号正确 ✓
- **Status**: 已完成 ✅

### [x] Task 9: 更新 release-notes.md
- **Priority**: P0
- **Depends On**: Task 6
- **Description**:
  - 在 v3.3.1 条目之前插入 v3.4.0 条目
  - 按功能分类详细描述每个变更
  - 列出所有变更的文件清单
  - 包含版本亮点和升级说明
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `human-judgement` TR-9.1: 版本说明结构清晰，包含亮点、详细说明、变更文件 ✓
  - `human-judgement` TR-9.2: 每个功能描述准确，与实际实现一致 ✓
  - `human-judgement` TR-9.3: 变更文件清单完整 ✓
- **Status**: 已完成 ✅

### [ ] Task 10: 检查其他文档版本号
- **Priority**: P1
- **Depends On**: Task 6
- **Description**:
  - 检查 docs/ 目录下所有文档的版本号头部
  - 根据文档是否受 v3.4.0 影响决定是否更新
  - 不受影响的文档保持 v3.3.0 或 v3.3.1 版本号
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `human-judgement` TR-10.1: 受影响的文档版本号已更新为 v3.4.0
  - `human-judgement` TR-10.2: 不受影响的文档版本号保持不变
  - `human-judgement` TR-10.3: 文档内容与 v3.4.0 功能一致
- **Notes**: 已更新 release-plan.md、changelog、release-notes
- **Status**: 部分完成

---

## Phase 3: 执行发布（Release Execution）

### [ ] Task 11: CI 验证
- **Priority**: P0
- **Depends On**: Task 7, Task 8, Task 9, Task 10
- **Description**:
  - 推送 release/v3.4.0 分支
  - 创建 PR（release/v3.4.0 → main）
  - 等待 CI 所有 6 个 job 通过
  - 如有失败，在 release 分支上修复后重新验证
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-11.1: 6 个 CI job 全部通过（lint、test、build 等）
  - `programmatic` TR-11.2: 无新增的 lint 警告或错误
  - `human-judgement` TR-11.3: 测试覆盖率不降低

### [ ] Task 12: 合并到 main 并打 tag
- **Priority**: P0
- **Depends On**: Task 11
- **Description**:
  - 合并 PR 到 main 分支
  - 检出 main 并拉取最新
  - 打 tag v3.4.0
  - 推送 tag 到远程
  - 创建 GitHub Release
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-12.1: main 分支 HEAD 与 release 分支合并结果一致
  - `programmatic` TR-12.2: `git tag v3.4.0` 存在且指向正确的 commit
  - `programmatic` TR-12.3: GitHub Release 已创建，包含 changelog 内容

### [ ] Task 13: 同步到 develop
- **Priority**: P0
- **Depends On**: Task 12
- **Description**:
  - 检出 develop 分支
  - 合并 main 分支（即合并 v3.4.0 发布版本）
  - 推送到远程
  - 确保 develop 与 main 的 v3.4.0 版本同步
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-13.1: develop 分支包含 v3.4.0 tag 的所有提交
  - `programmatic` TR-13.2: 合并无冲突
  - `human-judgement` TR-13.3: develop 和 main 的 v3.4.0 代码一致

---

## Phase 4: 发布后验证（Post-Release Verification）

### [ ] Task 14: 生产部署
- **Priority**: P0
- **Depends On**: Task 12
- **Description**:
  - 在生产环境执行 `./manage.sh upgrade v3.4.0`
  - 监控部署过程日志
  - 确认所有服务正常启动
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-14.1: `./manage.sh status` 显示所有服务 running
  - `programmatic` TR-14.2: `./manage.sh version` 显示 v3.4.0
  - `programmatic` TR-14.3: 后端 /health API 返回 version 为 3.4.0
  - `human-judgement` TR-14.4: 容器日志无错误

### [ ] Task 15: 功能验证
- **Priority**: P0
- **Depends On**: Task 14
- **Description**:
  - 验证页脚版本号显示
  - 验证 Dashboard 系统状态
  - 验证角色权限 i18n
  - 验证白名单删除功能
  - 验证开发环境功能（可选，如开发环境验证）
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `human-judgement` TR-15.1: 登录页和主布局页脚显示 v3.4.0
  - `human-judgement` TR-15.2: Dashboard 显示系统版本和运行环境
  - `human-judgement` TR-15.3: 角色管理页面权限名称正确翻译
  - `human-judgement` TR-15.4: 白名单删除功能正常
  - `human-judgement` TR-15.5: admin 用户角色显示为 Super Admin

### [ ] Task 16: 回滚预案验证
- **Priority**: P1
- **Depends On**: Task 15
- **Description**:
  - 验证回滚命令 `./manage.sh upgrade v3.3.1` 可用
  - （可选）在测试环境执行一次完整回滚验证
  - 确认数据兼容性（v3.4.0 → v3.3.1 无数据丢失）
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-16.1: v3.3.1 tag 存在，可被 upgrade 命令使用
  - `human-judgement` TR-16.2: 回滚后 v3.3.1 功能正常
  - `human-judgement` TR-16.3: 数据在版本降级后无损坏

---

## 风险与缓解

| 风险 | 等级 | 概率 | 影响 | 缓解措施 |
|------|------|------|------|----------|
| 权限描述 i18n 工作量大，推迟发布 | 低 | 中 | 低 | 可先发布 v3.4.0，权限描述 i18n 放入 v3.4.1 |
| .env 分离不完善，导致部署问题 | 中 | 中 | 高 | 发布前充分测试，保留回滚能力 |
| CI 失败，阻塞发布 | 低 | 中 | 中 | 在 release 分支上快速修复，不影响 develop |
| 生产部署失败 | 低 | 低 | 高 | 准备回滚预案，发布后 30 分钟内重点监控 |
| 文档更新遗漏 | 中 | 高 | 低 | 发布前逐项核对，发布后及时补全 |
