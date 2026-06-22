# TerminalAccessManager v3.4.0 版本发布 - 验证清单

## 一、代码功能验证

### 1.1 权限国际化
- [ ] 三种语言（中/英/日）翻译文件中包含全部 29 个权限的名称翻译
- [ ] 三种语言翻译文件中包含全部 29 个权限的描述翻译（`_desc` 后缀）
- [ ] 三种语言翻译文件中包含 5 个内置角色的名称翻译
- [ ] 三种语言翻译文件中包含 5 个内置角色的描述翻译（`_desc` 后缀）
- [ ] 权限列标题翻译键为 `permissionsColumn`（避免与 `permissions` 对象命名冲突）
- [ ] i18n 配置中 `nsSeparator: false` 已正确设置
- [ ] 角色管理页面权限列表正确显示翻译后的名称
- [ ] 切换语言时权限和角色翻译正确更新

### 1.2 系统版本与环境显示
- [ ] 前端页脚显示版本号 "v3.4.0"
- [ ] Dashboard 系统状态卡片显示版本号 "v3.4.0"
- [ ] Dashboard 系统状态卡片显示部署环境（development/production）
- [ ] 后端 `/health` API 返回 version 和 environment 字段
- [ ] 前端 branding store 包含 systemVersion 和 systemEnvironment 状态
- [ ] 版本信息获取不影响页面加载性能

### 1.3 白名单删除修复
- [ ] DELETE /api/v1/whitelist/ 端点接受查询参数 identifier
- [ ] 支持按 IP 地址删除白名单条目
- [ ] 支持按 MAC 地址删除白名单条目
- [ ] 支持按 IP+MAC 复合条目删除
- [ ] 删除后自动触发终端合规状态重算
- [ ] 删除操作记录审计日志（action: delete_whitelist）
- [ ] 删除成功返回 200 状态码
- [ ] 删除不存在的条目返回 404 且有明确错误提示

### 1.4 超管角色初始化
- [ ] 全新数据库初始化后 admin 用户关联 superadmin 角色
- [ ] user_roles 表中有 admin-superadmin 关联记录
- [ ] 重复执行 init 命令不创建重复角色关联
- [ ] _ensure_rbac_seed 函数包含 admin 用户角色修复逻辑
- [ ] 已存在 admin 用户但角色不正确时可自动修复

### 1.5 多环境配置
- [ ] docker-compose.yml 中 backend 服务 env_file 包含 .env 和 .env.${ENVIRONMENT:-development}
- [ ] docker-compose.yml 中 frontend 服务 env_file 包含 .env 和 .env.${ENVIRONMENT:-development}
- [ ] 环境变量加载顺序正确（.env 先加载，环境特定文件后加载覆盖）
- [ ] 缺少 .env.${ENVIRONMENT} 文件时不报错
- [ ] .env.example 文件包含通用配置项

## 二、版本号一致性验证

### 2.1 代码中的版本号
- [ ] manage.sh 中 VERSION = "3.4.0"
- [ ] backend/app/core/config.py 中 VERSION = "3.4.0"
- [ ] frontend/package.json 中 version = "3.4.0"
- [ ] .env.example 中 VERSION = 3.4.0
- [ ] /health API 返回的 version 字段为 "3.4.0"
- [ ] manage.sh version 命令输出 "3.4.0"

### 2.2 文档中的版本号
- [ ] docs/changelog.md 文档头部版本号为 v3.4.0
- [ ] docs/release-notes.md 文档头部版本号为 v3.4.0
- [ ] docs/release-plan.md 文档头部版本号为 v3.4.0
- [ ] 所有技术文档（backend.md、database.md、architecture.md 等）版本号更新为 v3.4.0
- [ ] 所有文档日期更新为发布日期

## 三、文档完整性验证

### 3.1 changelog.md
- [ ] [3.4.0] 条目已添加，包含正确的发布日期
- [ ] [Unreleased] 区块存在且为空
- [ ] 条目分类正确（Added/Changed/Fixed）
- [ ] 包含所有 v3.3.1 以来的变更
- [ ] 格式符合 Keep a Changelog 规范

### 3.2 release-notes.md
- [ ] [v3.4.0] 条目已添加
- [ ] 包含版本概要说明
- [ ] 包含功能变更分类列表
- [ ] 包含提交记录列表
- [ ] 包含文件变更清单
- [ ] 包含验证结果

### 3.3 release-plan.md
- [ ] 更新为 v3.4.0 发布方案
- [ ] 包含发布概要（版本号、发布类型、发布日期）
- [ ] 包含发布前状态检查
- [ ] 包含发布准备步骤
- [ ] 包含发布流程步骤
- [ ] 包含生产部署步骤
- [ ] 包含回滚方案

## 四、CI/CD 验证

### 4.1 后端
- [ ] backend-lint (ruff) 通过
- [ ] backend-test (pytest) 通过
- [ ] backend-build (Docker build) 通过

### 4.2 前端
- [ ] frontend-lint (ESLint) 通过
- [ ] frontend-test (vitest) 通过
- [ ] frontend-build (Docker build) 通过

### 4.3 总体
- [ ] 所有 6 个 CI Job 全部通过
- [ ] 无新引入的 lint 错误
- [ ] 无测试用例失败

## 五、发布流程验证

### 5.1 Git 流程
- [ ] develop 分支包含所有发布准备变更
- [ ] PR (develop → main) 已创建且描述完整
- [ ] PR 已合并到 main 分支
- [ ] main 分支历史完整（使用 Merge commit）
- [ ] v3.4.0 tag 已创建（annotated tag）
- [ ] v3.4.0 tag 已推送到远程
- [ ] develop 分支已同步 main（包含 tag）

### 5.2 GitHub Release
- [ ] GitHub Release 已创建
- [ ] Release 关联正确的 tag (v3.4.0)
- [ ] Release 标题为 "v3.4.0"
- [ ] Release Notes 内容完整
- [ ] 标记为正式发布（非 Pre-release）

## 六、向后兼容性验证

### 6.1 API 兼容
- [ ] 所有现有 API 端点路径和参数保持不变
- [ ] API 响应格式与 v3.3.1 兼容
- [ ] 无破坏性 API 变更

### 6.2 数据库兼容
- [ ] 无新增必填的数据库迁移
- [ ] 现有数据结构不变
- [ ] 升级后数据完整

### 6.3 配置兼容
- [ ] 现有 .env 文件可直接使用
- [ ] 新增配置项有合理的默认值
- [ ] 无必需的配置变更

### 6.4 升级验证
- [ ] `./manage.sh upgrade v3.4.0` 执行成功
- [ ] 升级后版本号显示为 v3.4.0
- [ ] 升级后所有核心功能正常
- [ ] 升级后数据完整

## 七、回滚预案验证

- [ ] `./manage.sh upgrade v3.3.1` 可成功回滚
- [ ] 回滚后版本号显示为 v3.3.1
- [ ] 回滚后核心功能正常
- [ ] 回滚后数据完整
- [ ] 回滚文档清晰可操作

## 八、发布前最终检查

- [ ] 所有 P0 优先级任务已完成
- [ ] 所有阻塞性问题已解决
- [ ] 发布日期和版本号已确认
- [ ] 相关人员已通知
- [ ] 回滚预案已准备就绪
