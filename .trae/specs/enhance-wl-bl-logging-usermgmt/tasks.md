# Tasks

- [x] Task 1: 白名单/黑名单添加逻辑校验增强
  - [x] 1.1: 后端 WhitelistCreate/BlacklistCreate Schema 新增 MAC+IP 绑定时禁止 CIDR/范围的校验器
  - [x] 1.2: 后端 whitelist endpoint 添加 MAC+IP 绑定校验（仅允许单个 IP）
  - [x] 1.3: 后端 blacklist endpoint 添加同样的校验逻辑
  - [x] 1.4: 前端 Whitelist.tsx 添加表单校验提示（MAC+IP 绑定时 IP 仅允许单个地址）
  - [x] 1.5: 前端 Blacklist.tsx 添加同样的表单校验提示

- [x] Task 2: 黑名单新增 comments 字段
  - [x] 2.1: 后端 Blacklist 数据库模型新增 comments 列（Text, nullable）
  - [x] 2.2: 后端 BlacklistCreate/BlacklistResponse Schema 新增 comments 字段
  - [x] 2.3: 前端 Blacklist.tsx 添加表单新增 comments 输入框
  - [x] 2.4: 前端 Blacklist.tsx 表格和详情弹窗中显示 comments

- [x] Task 3: 日志系统增强
  - [x] 3.1: 后端 config.py 新增日志配置项（LOG_FILE, LOG_ROTATION_SIZE, LOG_RETENTION_DAYS）
  - [x] 3.2: 后端 main.py 日志配置改为同时输出 stdout + 文件，统一 UTC 时区格式
  - [x] 3.3: 配置 loguru 文件轮转（10MB/文件，保留 5 个归档）和定期清理（30 天）
  - [x] 3.4: docker-compose.yml 挂载日志 volume

- [x] Task 4: manage.sh 用户管理命令
  - [x] 4.1: 新增 `user unlock <username>` 命令（清除 Redis 锁定）
  - [x] 4.2: 新增 `user create <username> [--password] [--superuser]` 命令
  - [x] 4.3: 新增 `user delete <username>` 命令（禁止删除 admin）
  - [x] 4.4: 新增 `user list` 命令
  - [x] 4.5: 新增 `user reset-password <username> [--password]` 命令
  - [x] 4.6: 后端 cli.py 新增对应的 user 子命令实现

- [x] Task 5: 用户管理页面
  - [x] 5.1: 后端新增用户管理 API（GET /users/, POST /users/, DELETE /users/{id}, PUT /users/{id}/password, PUT /users/me/password）
  - [x] 5.2: 前端新增 UserManagement.tsx 页面（用户列表、创建、删除、重置密码）
  - [x] 5.3: 前端新增 Profile.tsx 页面（个人密码修改，需验证旧密码）
  - [x] 5.4: 前端路由和侧边栏菜单新增入口

- [x] Task 6: 前端搜索框 hint 提示优化
  - [x] 6.1: MacAddresses.tsx 搜索框 placeholder 更新
  - [x] 6.2: Whitelist.tsx 搜索框 placeholder 更新
  - [x] 6.3: Blacklist.tsx 搜索框 placeholder 更新（包含 comments）
  - [x] 6.4: AuditLogs.tsx 搜索框 placeholder 更新

# Task Dependencies
- Task 2 依赖 Task 1（黑名单校验和 comments 字段一起修改 Schema）
- Task 5.1 依赖 Task 4.6（用户管理 API 可复用 cli.py 的逻辑）
- Task 6 独立，可并行执行
