# v3.4.0 版本发布方案 - 验证清单

## Phase 1: 开发收尾

### 权限描述 i18n
- [x] en.ts 包含所有 29 个权限的 `_desc` 翻译键
- [x] zh.ts 包含所有 29 个权限的 `_desc` 翻译键
- [x] ja.ts 包含所有 29 个权限的 `_desc` 翻译键
- [x] Roles.tsx 中权限描述使用翻译
- [ ] 三种语言切换均正常显示

### docker-compose env_file 环境覆盖
- [x] docker-compose.yml 中 backend 有 `env_file` 配置（两行：.env + 环境覆盖）
- [x] docker-compose.yml 中 frontend 有 `env_file` 配置（两行：.env + 环境覆盖）
- [x] docker-compose.dev.yml 中的 env_file 配置正确
- [x] docker-compose.prod.yml 中的 env_file 配置正确
- [ ] `docker compose config` 能正确显示合并后的环境变量

### manage.sh .env 分离支持
- [ ] dc() 函数正确传递 `--env-file` 参数
- [ ] deploy --dev 生成 .env 和 .env.dev
- [ ] deploy --prod 生成 .env 和 .env.prod
- [ ] check_weak_defaults() 检查正确的文件
- [ ] 环境切换时共享配置保持不变

### .env.example 精简
- [ ] .env.example 只包含环境共享的配置项
- [ ] .env.dev 包含开发环境特有配置
- [ ] .env.prod 包含生产环境特有配置
- [ ] 三个文件组合后配置完整无遗漏

## Phase 2: 发布准备

### 代码提交
- [ ] 所有变更已提交到 develop 分支
- [ ] 提交信息符合 Conventional Commits 规范
- [ ] 无未提交的工作目录变更

### Release 分支
- [ ] release/v3.4.0 分支已创建
- [ ] release 分支基于最新 develop
- [ ] release 分支无新功能提交（仅版本号和文档更新）

### 版本号更新
- [x] manage.sh VERSION 更新为 3.4.0
- [x] backend/app/core/config.py VERSION 更新为 3.4.0
- [x] frontend/package.json version 更新为 3.4.0
- [x] .env.example VERSION 更新为 3.4.0
- [x] 所有位置版本号一致

### Changelog 更新
- [x] changelog.md 新增 [3.4.0] 条目
- [x] Added 部分列出所有新功能
- [x] Changed 部分列出所有改进
- [x] Fixed 部分列出所有 Bug 修复
- [x] 版本日期正确

### Release Notes 更新
- [x] release-notes.md 新增 [v3.4.0] 条目
- [x] 功能分类清晰
- [x] 每个功能描述准确
- [x] 变更文件清单完整
- [x] 包含版本亮点

### 其他文档
- [x] 受影响的文档版本号已更新
- [ ] 文档内容与 v3.4.0 功能一致
- [ ] 无文档与实现不一致的情况

## Phase 3: 执行发布

### CI 验证
- [ ] CI 6 个 job 全部通过
- [ ] 无新增 lint 警告或错误
- [ ] 测试通过率 100%
- [ ] 构建成功

### 合并与打 Tag
- [ ] PR 已合并到 main
- [ ] main 分支代码正确
- [ ] v3.4.0 tag 已创建
- [ ] tag 已推送到远程
- [ ] GitHub Release 已创建
- [ ] Release 包含 changelog 内容

### 同步 Develop
- [ ] develop 分支已合并 main
- [ ] 合并无冲突
- [ ] develop 与 main 的 v3.4.0 代码一致

## Phase 4: 发布后验证

### 部署验证
- [ ] `./manage.sh upgrade v3.4.0` 执行成功
- [ ] 所有服务状态为 running
- [ ] `./manage.sh version` 显示 v3.4.0
- [ ] 后端 /health API 返回 version: 3.4.0
- [ ] 容器日志无错误

### 功能验证
- [ ] 登录页页脚显示 v3.4.0
- [ ] 主布局页脚显示 v3.4.0
- [ ] Dashboard 显示系统版本 v3.4.0
- [ ] Dashboard 显示运行环境（生产/开发）
- [ ] 角色管理页面权限列表头正确显示
- [ ] 角色描述支持国际化
- [ ] 权限名称支持国际化
- [ ] 超管用户角色显示正确（Super Admin）
- [ ] 白名单删除功能正常
- [ ] Nginx /health 路径可访问

### 回滚验证
- [ ] v3.3.1 tag 存在
- [ ] `./manage.sh upgrade v3.3.1` 命令可用
- [ ] 回滚后 v3.3.1 功能正常
- [ ] 数据在版本降级后无损坏

## 发布前最终检查清单
- [ ] 所有功能已开发完成
- [ ] 所有 Bug 已修复
- [ ] 所有测试通过
- [ ] 所有文档已更新
- [ ] 版本号已更新
- [ ] Changelog 已更新
- [ ] Release notes 已更新
- [ ] CI 全量通过
- [ ] 回滚预案已准备
- [ ] 发布时间已确认