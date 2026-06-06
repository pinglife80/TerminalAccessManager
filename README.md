# MAC Security Platform

基于 MAC 地址的网络安全准入管理平台，提供终端监控、黑白名单管控、审计日志等完整功能。

## 功能特性

- **终端监控** — 实时 MAC 地址状态管理（Active / Inactive / Blocked / Pending / Unblocked / Bypass）
- **白名单管理** — 可信终端快速放行，支持搜索、过滤、分页
- **黑名单管理** — 安全威胁终端封禁，支持仅 MAC 地址封禁
- **审计日志** — 全操作审计追踪，支持日期范围过滤
- **仪表板** — 数据概览、快捷操作、系统状态
- **品牌自定义** — 集中式配置（应用名、Logo、Favicon、登录页、页脚），无需修改组件代码
- **登录安全** — 验证码（3 次失败后）、账户锁定（5 次失败后锁定 15 分钟）
- **HTTPS** — Nginx 反向代理 + SSL/TLS，HTTP 自动重定向 HTTPS
- **响应式 UI** — 可折叠侧边栏、可折叠搜索面板、双位置分页

## 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| FastAPI | 异步 Python Web 框架 |
| SQLAlchemy 2.0 | 异步 ORM |
| PostgreSQL 15 | 关系数据库 |
| Redis 7 | 缓存与会话管理 |
| JWT (python-jose) | 令牌认证 |
| Bcrypt | 密码哈希 |
| Uvicorn | ASGI 服务器 |

### 前端

| 技术 | 用途 |
|------|------|
| React 18 | UI 组件库 |
| TypeScript 5 | 类型安全 |
| Vite 5 | 构建工具 |
| TailwindCSS 3 | 样式框架 |
| TanStack Query 5 | 服务端状态管理 |
| Zustand 4 | 客户端状态管理 |
| React Router 6 | 路由 |
| React Hook Form 7 | 表单验证 |
| Lucide React | 图标库 |
| Recharts | 图表 |

## 快速开始

### 前提条件

- Docker 20.10+ 和 Docker Compose v2+
- 磁盘空间 5GB+

**无需本地安装 Python 或 Node.js**，所有服务运行在 Docker 容器中。

### 一键部署（Demo 模式）

```bash
git clone <repository-url>
cd mac_security_web
chmod +x manage.sh
./manage.sh deploy --demo
```

部署完成后访问：

- **HTTPS**: https://localhost:8443
- **HTTP**: http://localhost:8080（自动重定向到 HTTPS）
- **登录**: admin / admin123

> Demo 模式自动生成配置和演示数据，仅用于评估测试。

### 生产部署

```bash
./manage.sh deploy --prod
```

交互式向导引导配置数据库密码、Redis 密码、可选集成等。

详细部署说明请参阅 [部署与运维手册](docs/deployment.md)。

## 项目结构

```
mac_security_web/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/            # API 路由（auth, mac_addresses, whitelist, blacklist, logs）
│   │   ├── core/              # 核心模块（config, database, security）
│   │   ├── middleware/         # 中间件（logging, rate_limit）
│   │   ├── models/            # SQLAlchemy 数据模型
│   │   ├── schemas/           # Pydantic 数据模式
│   │   └── services/          # 业务逻辑层
│   ├── cli.py                 # 统一 CLI（setup / mock / validate）
│   ├── tests/                 # 测试套件
│   └── Dockerfile
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── components/        # UI 组件（Layout, Sidebar, Pagination, DateRangeFilter...）
│   │   ├── config/            # 配置文件
│   │   │   └── branding.ts    # 品牌自定义配置
│   │   ├── hooks/             # 自定义 Hooks
│   │   ├── lib/               # 工具库（api, constants, utils）
│   │   ├── pages/             # 页面组件（Dashboard, Login, MacAddresses, Whitelist, Blacklist, AuditLogs）
│   │   ├── store/             # Zustand 状态管理
│   │   ├── App.tsx            # 路由配置
│   │   └── main.tsx           # 入口文件
│   ├── public/                # 静态资源（favicon.svg, logo 等）
│   └── Dockerfile
├── nginx/                      # Nginx 配置与 SSL 证书
│   ├── etc/conf.d/            # Nginx 站点配置
│   └── certs/                 # SSL 证书（自动生成）
├── docs/                       # 项目文档
│   ├── deployment.md          # 部署与运维手册
│   ├── branding.md            # 品牌自定义指南
│   └── changelog.md           # 更新日志
├── backups/                    # 数据库备份（自动创建）
├── manage.sh                   # 统一管理脚本
├── docker-compose.yml          # Docker 编排配置
└── .env.example                # 环境变量模板
```

## 管理脚本

所有操作通过 `manage.sh` 统一管理：

```bash
./manage.sh deploy --demo       # Demo 部署
./manage.sh deploy --prod       # 生产部署（交互式向导）
./manage.sh start               # 启动服务
./manage.sh stop                # 停止服务
./manage.sh status              # 查看状态
./manage.sh health              # 深度健康检查
./manage.sh logs [service]      # 查看日志
./manage.sh backup              # 备份数据库
./manage.sh restore <file>      # 恢复数据库
./manage.sh mock generate       # 生成演示数据
./manage.sh mock clear          # 清除演示数据
./manage.sh shell [backend|db|redis]  # 服务 Shell
./manage.sh config              # 查看/修改配置
./manage.sh ssl                 # 管理 SSL 证书
./manage.sh update              # 更新并重建
./manage.sh clean               # 清理所有数据
./manage.sh help                # 完整帮助
```

全局选项：`-y`（非交互模式）、`-v`（调试输出）

完整命令参考请参阅 [部署与运维手册](docs/deployment.md)。

## 访问地址

| 服务 | 地址 |
|------|------|
| Web 管理界面 | https://localhost:8443 |
| API 文档 (Swagger) | https://localhost:8443/api/v1/docs |
| API 文档 (ReDoc) | https://localhost:8443/api/v1/redoc |
| 健康检查 | https://localhost:8443/api/v1/health |

> HTTP (8080) 自动重定向到 HTTPS (8443)。其他服务端口不对外暴露。

## 文档索引

| 文档 | 说明 |
|------|------|
| [部署与运维手册](docs/deployment.md) | 从零部署、命令参考、运维场景、故障排查、架构说明 |
| [品牌自定义指南](docs/branding.md) | Logo、Favicon、登录页、页脚等品牌配置操作指南 |
| [更新日志](docs/changelog.md) | 版本历史与变更记录 |
| [前端实现文档](frontend/docs/implementation.md) | 前端架构、组件、页面功能详细说明 |
| [前端 README](frontend/README.md) | 前端项目概览与开发指南 |

## 安全特性

- Bcrypt 密码哈希（work factor 12）
- JWT 令牌认证（过期 + 刷新机制）
- 认证端点速率限制
- CORS 跨域保护
- Pydantic 输入验证
- ORM 防 SQL 注入
- HTTPS 强制（Nginx 反向代理）
- 登录安全：验证码 + 账户锁定
- 环境变量管理密钥

## 许可证

MIT License
