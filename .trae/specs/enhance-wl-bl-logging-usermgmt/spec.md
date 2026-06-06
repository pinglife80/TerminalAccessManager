# 白名单/黑名单逻辑增强、日志系统优化、用户管理 Spec

## Why
当前白名单/黑名单添加逻辑不够严谨（MAC+IP 绑定时允许 CIDR/范围），黑名单缺少 comments 字段，日志系统缺少文件输出/归档/清理能力，manage.sh 缺少用户管理命令，且缺少用户管理页面和搜索提示优化。

## What Changes
- 白名单添加逻辑：MAC+IP 绑定时仅允许单个 IP，单独添加时支持 MAC/IP/CIDR/范围
- 黑名单添加逻辑：与白名单一致，新增 comments 字段
- 日志系统：统一时区、可配置 level、文件输出+归档+定期清理
- manage.sh：新增用户锁定重置、用户创建、用户删除命令
- 新增用户管理页面：个人密码修改、管理员用户列表管理
- 前端搜索框：明确 hint 提示支持搜索的字段

## Impact
- Affected specs: 白名单/黑名单 API、Schema、数据库模型、前端表单
- Affected code:
  - `backend/app/schemas/mac_address.py` — BlacklistCreate 新增 comments
  - `backend/app/models/blacklist.py` — 新增 comments 列
  - `backend/app/api/v1/endpoints/whitelist.py` — 添加逻辑校验
  - `backend/app/api/v1/endpoints/blacklist.py` — 添加逻辑校验
  - `backend/app/main.py` — 日志配置增强
  - `backend/app/core/config.py` — 日志相关配置项
  - `manage.sh` — 新增用户管理命令
  - `frontend/src/pages/Whitelist.tsx` — 表单校验+搜索提示
  - `frontend/src/pages/Blacklist.tsx` — 表单校验+comments 字段+搜索提示
  - `frontend/src/pages/MacAddresses.tsx` — 搜索提示
  - `frontend/src/pages/AuditLogs.tsx` — 搜索提示
  - 新增 `frontend/src/pages/UserManagement.tsx` — 用户管理页面
  - 新增 `frontend/src/pages/Profile.tsx` — 个人密码修改页面

## ADDED Requirements

### Requirement: 白名单添加逻辑校验
系统 SHALL 在添加白名单时执行以下校验：
- 仅添加 MAC 地址：允许单个 MAC 地址
- 仅添加 IP 地址/范围：允许单个 IP、CIDR（如 192.168.1.0/24）、IP 范围（如 192.168.1.1-100）
- 同时添加 MAC 和 IP：仅允许单个 IP 地址（不允许 CIDR 或 IP 范围），实现 MAC-IP 一对一绑定

#### Scenario: 仅添加 MAC
- **WHEN** 用户只填写 MAC 地址，不填 IP
- **THEN** 系统接受并创建白名单条目

#### Scenario: 仅添加 CIDR
- **WHEN** 用户只填写 CIDR 格式 IP（如 192.168.1.0/24），不填 MAC
- **THEN** 系统接受并展开为多个白名单条目

#### Scenario: MAC+IP 绑定使用 CIDR
- **WHEN** 用户同时填写 MAC 和 CIDR 格式 IP
- **THEN** 系统拒绝并返回错误提示 "MAC-IP binding only supports a single IP address"

### Requirement: 黑名单添加逻辑校验
系统 SHALL 在添加黑名单时执行与白名单一致的校验逻辑，并新增 comments 字段用于备注信息。

#### Scenario: 黑名单添加带 comments
- **WHEN** 用户填写 MAC/IP + reason + comments
- **THEN** 系统创建黑名单条目，包含 comments 信息

### Requirement: 黑名单 comments 字段
系统 SHALL 在黑名单数据库模型、Schema 和前端表单中新增 comments 字段（可选，文本类型）。

### Requirement: 日志系统增强
系统 SHALL 提供以下日志能力：
- 统一时区为 UTC，日志时间戳格式统一为 `YYYY-MM-DD HH:mm:ss UTC`
- 支持通过环境变量 `LOG_LEVEL` 配置日志级别（DEBUG/INFO/WARNING/ERROR）
- 支持文件日志输出，路径通过 `LOG_FILE` 环境变量配置（默认 `/var/log/mac_security/app.log`）
- 日志文件自动归档：按 10MB 大小轮转，保留最近 5 个归档文件
- 日志定期清理：归档文件超过 30 天自动删除

### Requirement: manage.sh 用户管理命令
系统 SHALL 在 manage.sh 中新增以下命令：
- `user unlock <username>` — 重置用户锁定状态（清除 Redis 中的 login_lock 和 login_attempts）
- `user create <username> [--password <pw>] [--superuser]` — 创建新用户
- `user delete <username>` — 删除用户（不可删除 admin）
- `user list` — 列出所有用户
- `user reset-password <username> [--password <pw>]` — 重置用户密码

### Requirement: 用户管理页面
系统 SHALL 提供用户管理页面：
- 管理员可查看所有用户列表（用户名、邮箱、角色、状态、创建时间）
- 管理员可创建/删除用户、重置用户密码
- 每个用户可在个人设置中修改自己的密码（需输入旧密码验证）

### Requirement: 前端搜索框 hint 提示
系统 SHALL 在所有搜索框 placeholder 中明确提示支持搜索的字段：
- Terminal 页：`Search by MAC, IP, or comments...`
- Whitelist 页：`Search by MAC, IP, or comments...`
- Blacklist 页：`Search by MAC, IP, reason, or comments...`
- AuditLogs 页：`Search by username, action, IP, or details...`

## MODIFIED Requirements

### Requirement: 白名单/黑名单添加 API
原有逻辑：允许同时填写 MAC 和 CIDR/范围 IP。
修改后：同时填写 MAC 和 IP 时，仅允许单个 IP 地址。

### Requirement: 日志配置
原有逻辑：仅输出到 stdout，无文件归档。
修改后：同时输出到 stdout 和文件，支持轮转归档和定期清理。

## REMOVED Requirements
无移除项。
