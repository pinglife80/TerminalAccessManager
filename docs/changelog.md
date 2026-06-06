# 更新日志

本文件记录 MAC Security Platform 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [2.0.0] - 2026-06

### 新功能

- **统一管理脚本**：整合 `manage.sh`、`deploy.sh`、`quickstart.sh` 为单一 `manage.sh`，支持 17 个子命令（deploy/start/stop/restart/status/health/logs/update/init/test/mock/backup/restore/shell/ssl/config/validate/clean/version），幂等设计，非交互模式（`-y`），调试输出（`-v`）
- **生产部署向导**：`deploy --prod` 交互式配置数据库密码、Redis 密码、JWT 密钥、深信服 API、网络交换机集成
- **深度健康检查**：`health` 命令执行 8 项检查（Docker/容器/数据库/Redis/后端/Web/SSL/磁盘）
- **配置管理**：`config` 命令查看/修改环境变量，敏感信息自动脱敏
- **SSL 证书管理**：`ssl` 命令幂等生成自签名证书，`--force` 强制重新生成，Nginx 自动 reload
- **数据库备份恢复**：`backup`/`restore` 命令，自动清理旧备份（保留 10 个），恢复前自动备份
- **自动备份**：`update`/`restore`/`mock clear` 操作前自动备份数据库
- **部署状态管理**：`.manage/state.env` 跟踪部署状态，实现幂等性控制
- **品牌自定义**：集中式品牌配置（`branding.ts`），支持自定义应用名称、Logo、Favicon、登录页样式、页脚信息、ICP 备案等，无需修改组件代码
- **可折叠侧边栏**：侧边栏支持展开/折叠切换，折叠时显示图标与悬停提示
- **高级分页**：分页组件支持顶部/底部双展示、每页条数选择（10/20/50/100）、快速跳转指定页码
- **日期范围过滤**：`DateRangeFilter` 组件，支持快捷选项和自定义日期范围
- **可折叠搜索面板**：搜索与过滤条件区域支持折叠/展开
- **登录安全增强**：3 次失败后显示验证码，5 次失败后锁定账户 15 分钟
- **状态提示**：6 种状态（Active/Inactive/Blocked/Pending/Unblocked/Bypass）悬停 Tooltip 解释
- **统一卡片风格**：所有页面卡片采用 `rounded-2xl` 圆角、渐变色条、Section Header 统一风格
- **页脚信息**：主布局和登录页页脚显示版权信息、版本号、ICP 备案号及自定义链接
- **Nginx 安全代理**：仅 Nginx 对外暴露端口（8080→80, 8443→443），HTTP 自动重定向 HTTPS，其他服务端口不对外暴露

### 改进

- **登录错误提示**：登录失败提示改为持久显示，支持手动关闭
- **图标一致性**：Dashboard 与导航栏图标统一（Whitelisted=List, Blocked=ShieldOff）
- **Blacklist ip_address 可空**：黑名单 IP 地址字段改为可选，支持仅基于 MAC 地址的封禁
- **空值保护**：增强各组件对空值/未定义值的容错处理
- **依赖顺序启停**：按基础设施→应用→代理顺序启动，反向停止
- **前端构建产物保护**：`dist_backup` 机制防止 Docker Volume 覆盖构建产物

### Bug 修复

- 修复 DateRangeFilter onChange 不触发的问题
- 修复 Blocked 页面 `Cannot read properties of null (reading 'toLowerCase')` 错误
- 修复黑名单无法单独添加 MAC 地址（ip_address NOT NULL 约束）
- 修复 Docker 构建 TypeScript 编译错误（`NodeJS.Timeout`、`as const` 类型推断、Fragment 包裹）
- 修复 PostgreSQL 健康检查 `mac_admin does not exist`（需指定 `-d mac_security`）
- 修复 Redis 健康检查（需 `-a password` 参数）
- 修复前端容器构建产物被 Volume 覆盖的问题
- 修复 Nginx HTTPS 端口映射（内部 443，对外 8443）

---

## [1.0.0] - 2025-12

### 初始实现

- **FastAPI 后端**：基于 FastAPI + SQLAlchemy 2.0 的异步 API 服务
- **React 前端**：基于 React 18 + TypeScript + Vite 的现代化前端
- **Docker 部署**：完整的 Docker Compose 编排，包含 PostgreSQL、Redis、Nginx
- **用户认证**：JWT 令牌认证，支持登录/登出/令牌刷新
- **MAC 地址管理**：搜索、过滤、分页、状态管理
- **白名单管理**：增删查、搜索、过滤、分页
- **黑名单管理**：增删查、搜索、过滤、分页
- **审计日志**：操作记录查看、搜索、日期过滤、分页
- **仪表板**：数据概览与统计图表
- **HTTPS 支持**：Nginx 配置 SSL/TLS
- **速率限制**：认证端点请求频率限制
- **CORS 保护**：跨域请求安全配置
