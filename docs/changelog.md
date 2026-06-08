# 更新日志

本文件记录 TerminalAccessManager 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [2.3.0] - 2026-06-08

### 新增

- `upgrade` 命令：从远程仓库拉取新版本代码并升级，支持指定版本（tag/branch/commit）、`--check` 仅检查模式、前置安全检查、版本差异展示、红色警告框、强制自动备份、自动数据库迁移、迁移失败恢复方案
- 危险命令结构化警告：`restore`、`mock clear`、`migrate`、`redis flush`、`redis del`、`config set`（安全类配置）执行前显示影响范围和确认提示
- `config set` 新旧值对比显示，安全类配置（锁定策略、限流、验证码等）二次确认
- 定时任务暂停机制真正生效：`_is_task_paused()` 函数在任务循环中检查 Redis 键 `scheduler:ctrl:{task}`
- 新增 `docs/manage-sh-reference.md` 命令行操作手册

### 改进

- `update` 命令移除 git pull，改为仅重建+重启本地代码（不再有 `--no-git` 参数）
- `scheduler pause/resume` 现在真正控制定时任务执行（之前仅设置 Redis 键但任务未检查）

### 修复

- `firewall_query` 定时任务改用 `TerminalService._get_sangfor_service_by_tag()` + `SangforService.get_blocked_ips()`（原调用不存在的 `query_firewall_blacklist` 方法）

---

## [2.2.0] - 2026-06

### 重构

- **MacAddress → Terminal 重命名**：数据库表 `mac_addresses` → `terminals`，后端模型 `MacAddress` → `Terminal`，Schema `MacAddressBase/Create/Update/Response/Query` → `TerminalBase/Create/Update/Response/Query`，服务 `MacService` → `TerminalService`，API 路由 `/mac` → `/terminals`，前端组件 `MacAddresses` → `Terminals`，前端路由 `/mac-addresses` → `/terminals`，前端 Hook `useMacAddresses` → `useTerminals`，前端类型 `MacAddress` → `Terminal`，文件名 `mac_address.py` → `terminal.py`、`mac_service.py` → `terminal_service.py`、`mac_addresses.py` → `terminals.py`、`MacAddresses.tsx` → `Terminals.tsx`、`useMacData.ts` → `useTerminalData.ts`
- **API 路由 `/mac` → `/terminals`**：`GET /api/v1/mac/` → `GET /api/v1/terminals/`，`GET /api/v1/mac/search` → `GET /api/v1/terminals/search`，`POST /api/v1/mac/block/{ip}` → `POST /api/v1/terminals/block/{ip}`，`POST /api/v1/mac/unblock/{ip}` → `POST /api/v1/terminals/unblock/{ip}`，`GET /api/v1/mac/{id}` → `GET /api/v1/terminals/{id}`
- **IP Guard → ComplianceBaseline 分离**：新增 `compliance_baselines` 数据库表，新增 `ComplianceBaseline` 模型、Schema、Endpoint，DataSource 的 `type` 不再包含 `ipguard`（只保留 `arp_ssh`/`arp_api`/`sangfor`），新增 API 路由 `/compliance-baselines/`（CRUD + test + sync），前端 DataSources 页面新增 "Compliance Baselines" Tab，数据库迁移脚本 `002_terminal_baseline.py`

---

## [2.1.0] - 2026-06

### 新功能

- **数据源管理系统**：新增 DataSource 和 DataSourceBinding 数据模型，统一管理 ARP 数据源（SSH/API）、IP Guard 合规基准、深信服防火墙，支持数据源 CRUD、测试连接、手动同步
- **合规检查引擎**：新增 ComplianceService，4 种合规状态判定（compliant/bypass/non_compliant/unknown），白名单匹配类型标记（wl_match_type: mac/ip/both），IPGuard 基准匹配，自动封禁/解封按防火墙 Tag 路由
- **多防火墙支持**：数据源绑定（DataSourceBinding）关联 ARP 数据源与防火墙，封禁/解封操作按 Tag 路由到对应防火墙，多防火墙场景创建独立 Blacklist 记录
- **定时任务可配置**：5 个定时任务频率参数（ARP 采集、IPGuard 同步、防火墙查询、合规检查、自动解封），支持 30 秒 - 1 天间隔，通过 `manage.sh config set` 修改
- **Scheduler 配置分类**：系统配置新增 `scheduler` 分类，SchedulerConfigResponse 包含 5 个间隔配置项
- **前端自动刷新**：Terminal 和 Blacklist 页面支持手动刷新按钮和自动刷新选择器（30 秒 / 1 分钟 / 5 分钟 / 10 分钟）
- **DataSources 页面**：新增数据源管理页面（管理员专属），包含 Data Sources / Bindings / Compliance 三个 Tab，支持编辑数据源、手动同步、合规检查操作
- **Users 页面**：新增用户管理页面（管理员专属），用户 CRUD 操作
- **Profile 页面**：新增个人资料页面
- **品牌动态加载**：新增 useBrandingStore Zustand store，登录后从后端 `/settings/` API 动态加载品牌配置，替代纯静态 branding.ts
- **manage.sh config 增强**：新增 `config list`、`config get`、`config set`、`config branding`、`config upload` 子命令，支持数据库系统配置和品牌资源管理
- **Whitelist 详情查看**：白名单页面新增详情弹窗，comments 字段改为必填
- **Terminal 合规状态**：终端页面从 6 种状态改为 4 种合规状态（Normal/Bypass/Blocked/Pending），集成黑名单数据展示，Bypass 显示匹配类型（MAC/IP/Both），Blocked 显示防火墙 Tag
- **Terminal 快捷操作**：Bypass 条目支持"从白名单移除"，Blocked 条目支持"从黑名单移除"
- **Dashboard 合规统计**：统计卡片更新为 5 个（Total/Normal/Bypass/Blocked/Pending），compliance_status 分组统计
- **导航权限控制**：NAV_ITEMS 新增 adminOnly 字段，Data Sources 和 Users 页面仅管理员可见

### 改进

- **终端总数统计**：Total 统计仅计算 ARP 数据源条目（source='arp'），不再包含白名单独立条目
- **黑名单手动封禁**：手动封禁 source_tag 标记为 "manual"，compliance_status 设置为 "non_compliant"
- **黑名单手动解封**：按 firewall_tag 过滤删除 Blacklist 记录，compliance_status 设置为 "unknown"
- **白名单 CIDR 匹配**：存储原始 pattern，使用 ipaddress 模块判断包含关系，不展开 CIDR
- **合规检查缓存**：IPGuard 数据 Redis 缓存 10 分钟 TTL，白名单数据 Redis 缓存 5 分钟 TTL
- **ARP 采集后合规更新**：ARP 采集完成后自动运行合规检查，更新 compliance_status 和 wl_match_type
- **Demo 默认密码**：Demo 模式默认密码从 admin123 改为 Admin123（满足密码复杂度要求）
- **前端类型对齐**：MacAddress、WhitelistEntry、BlacklistEntry、DataSourceItem 等类型定义与后端 schema 完全对齐
- **前端 UI 统一**：所有页面按钮使用默认 md 尺寸，Dashboard Overview 放在页面标题下方

### Bug 修复

- 修复 Stats API `GET /mac/stats` 被 `GET /mac/{mac_id}` 路由匹配的问题
- 修复 Scheduler 配置未出现在 settings API 的问题（AllConfigsResponse 缺少 scheduler 字段）
- 修复 ConfigService 缺少 get_value 方法导致 _get_scheduler_interval 调用失败
- 修复 MacAddress 模型缺少 wl_match_type 字段导致前端类型不匹配
- 修复 arp_collector_service.py 合规检查后未更新 wl_match_type
- 修复 main.py scheduled_compliance_check 未更新 wl_match_type
- 修复前端 MacAddresses.tsx 中 removingWlId/removingBlId/whitelistId 与 mac.id 类型比较错误（string | null vs number）
- 修复前端 MacAddresses.tsx 中 CheckCircle 未使用导入导致构建失败

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
- 修复 PostgreSQL 健康检查 `tam_admin does not exist`（需指定 `-d tam_db`）
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
