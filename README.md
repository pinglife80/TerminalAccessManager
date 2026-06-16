# TerminalAccessManager

基于 MAC/IP 的网络终端准入管控平台，自动合规判定 + 防火墙封堵/解封。

## 核心概念

- **终端合规状态**：`compliant` / `non_compliant` / `bypass` / `unknown`
- **合规引擎**：白名单 → bypass，黑名单 → non_compliant，IPGuard 匹配 → compliant，否则 unknown
- **封堵路由**：ARP 数据源 → 绑定关系 → 防火墙 Tag → Sangfor API 封堵/解封
- **权限体系**：5 角色（superadmin / admin / operator / auditor / viewer）× 29 权限码，superadmin 系统保留

## 快速开始

**前提**：Docker 20.10+ / Docker Compose v2+ / 磁盘 5GB+

```bash
git clone https://github.com/pinglife80/TerminalAccessManager.git
cd TerminalAccessManager
chmod +x manage.sh
```

**开发环境**（一键启动 + 可选 Mock 数据）：

```bash
./manage.sh deploy --dev
```

**生产环境**（交互式配置向导）：

```bash
./manage.sh deploy --prod
```

部署完成后访问：

- **地址**：`https://<HOST_IP>:8443`（开发环境 `http://<HOST_IP>:8080`）
- **登录**：admin / Admin123（开发环境默认密码，生产环境自定义）

> `<HOST_IP>` 为实际部署主机 IP 地址，本机部署时使用 `localhost`。

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Python / FastAPI / SQLAlchemy 2.0 / PostgreSQL 15 / Redis 7 |
| 前端 | React 18 / TypeScript 5 / TailwindCSS 3 / TanStack Query 5 |
| 基础设施 | Docker Compose / Nginx / manage.sh 运维脚本 |

## 文档导航

| 我想… | 看这个 |
|--------|--------|
| 了解系统架构 | [architecture.md](docs/architecture.md) |
| 部署上线 | [deployment.md](docs/deployment.md) + [operations-runbook.md](docs/operations-runbook.md) |
| 开发后端功能 | [backend.md](docs/backend.md) |
| 开发前端功能 | [implementation.md](frontend/docs/implementation.md) |
| 查 API 接口 | [api.md](docs/api.md) |
| 管理权限角色 | [RBAC.md](docs/RBAC.md) |
| 排查故障 | [operations-runbook.md](docs/operations-runbook.md) + [disaster-recovery.md](docs/disaster-recovery.md) |
| 定制品牌外观 | [branding.md](docs/branding.md) |
| 查数据库结构 | [database.md](docs/database.md) |
| 查 manage.sh 命令 | [manage-sh-reference.md](docs/manage-sh-reference.md) |
| 查数据源生命周期 | [datasource-lifecycle.md](docs/datasource-lifecycle.md) |
| 查日志规范 | [logging-guide.md](docs/logging-guide.md) |
| 查 Git 工作流 | [git-workflow-guide.md](docs/git-workflow-guide.md) |
| 查生产就绪评估 | [production-readiness-assessment.md](docs/production-readiness-assessment.md) |
| 查版本变更 | [changelog.md](docs/changelog.md) + [release-notes.md](docs/release-notes.md) |

## 许可证

MIT License
