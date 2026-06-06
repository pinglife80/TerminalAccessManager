# MAC Security Platform 项目优化 Spec

## Why
项目已完成核心功能（终端监控、黑白名单、审计日志、登录安全），但在安全性、性能、代码质量、前端体验和运维能力方面存在多处可优化项，需要系统性梳理和改进以提升生产就绪度。

## What Changes
- 修复后端安全隐患（Token 刷新无类型区分、CORS 配置硬编码、健康检查 Redis 连接泄漏、生产环境 Prometheus 强制开启）
- 优化后端性能（全量数据加载改为服务端分页/搜索、Dashboard 统计接口、SangforService 连接复用）
- 完善后端代码质量（缺少 MAC/IP 格式校验、Alembic 迁移未实际使用、测试覆盖不足、审计日志未记录操作者 IP）
- 优化前端体验（Token 过期自动刷新、前端分页改为服务端分页、Dashboard 系统状态硬编码改为实时、黑名单过期自动清理）
- 增强运维能力（前端缺少全局 Loading/404 页面、Sidebar 登出未调用后端 API、缺少用户管理功能）

## Impact
- Affected specs: 后端 API 接口、前端所有页面、数据库模型、中间件
- Affected code:
  - `backend/app/core/security.py` — Token 刷新逻辑
  - `backend/app/core/config.py` — CORS 配置
  - `backend/app/main.py` — 健康检查、Prometheus
  - `backend/app/services/mac_service.py` — 全量查询优化
  - `backend/app/services/sangfor_service.py` — 连接管理
  - `backend/app/api/v1/endpoints/*.py` — 分页/搜索参数
  - `backend/app/schemas/mac_address.py` — 校验规则
  - `backend/app/models/*.py` — 数据库模型
  - `frontend/src/hooks/useMacData.ts` — 数据获取
  - `frontend/src/pages/*.tsx` — 所有页面
  - `frontend/src/store/auth.ts` — Token 管理
  - `frontend/src/App.tsx` — 路由/全局处理

## ADDED Requirements

### Requirement: 后端 API 分页与搜索优化
后端所有列表接口 SHALL 支持服务端分页和搜索，返回总数信息，避免全量数据加载。

#### Scenario: 获取终端列表
- **WHEN** 前端请求 `/mac/search?page=1&page_size=10&status=frozen`
- **THEN** 返回 `{items: [...], total: 100, page: 1, page_size: 10}`

#### Scenario: 获取审计日志
- **WHEN** 前端请求 `/logs/?page=1&page_size=20&action=login`
- **THEN** 返回分页结果，支持按 action/username/日期范围过滤

### Requirement: Dashboard 统计接口
后端 SHALL 提供专用 `/stats` 接口返回仪表板统计数据，避免前端多次请求后本地计算。

#### Scenario: 获取仪表板统计
- **WHEN** 前端请求 `/stats`
- **THEN** 返回 `{total: 100, whitelisted: 30, blocked: 5, active: 65, recent_logs: [...]}`

### Requirement: Token 自动刷新机制
前端 SHALL 在 access_token 过期时自动使用 refresh_token 刷新，无需用户重新登录。

#### Scenario: Token 过期自动刷新
- **WHEN** API 请求返回 401 且 refresh_token 有效
- **THEN** 自动刷新 token 并重试原始请求

#### Scenario: Refresh Token 也过期
- **WHEN** refresh_token 也过期
- **THEN** 跳转到登录页

### Requirement: 后端输入校验增强
后端 SHALL 对 MAC 地址和 IP 地址进行格式校验，拒绝非法输入。

#### Scenario: 提交非法 MAC 地址
- **WHEN** 请求包含格式错误的 MAC 地址（如 "ZZ:ZZ:ZZ:ZZ:ZZ:ZZ"）
- **THEN** 返回 422 错误，提示 MAC 格式不合法

#### Scenario: 提交非法 IP 地址
- **WHEN** 请求包含格式错误的 IP 地址
- **THEN** 返回 422 错误，提示 IP 格式不合法

### Requirement: 审计日志记录操作者 IP
审计日志 SHALL 记录操作者的客户端 IP 地址。

#### Scenario: 用户执行操作
- **WHEN** 用户执行白名单/黑名单操作
- **THEN** 审计日志中记录客户端 IP（从 X-Forwarded-For 或请求中获取）

### Requirement: 健康检查 Redis 连接复用
健康检查端点 SHALL 复用已有的 Redis 连接，而非每次创建新连接。

#### Scenario: 健康检查
- **WHEN** 请求 `/health`
- **THEN** 使用 `security.py` 中已有的 Redis 客户端进行 ping 检查，不创建新连接

### Requirement: 前端 404 和全局错误页面
前端 SHALL 提供 404 页面和全局错误处理。

#### Scenario: 访问不存在的路由
- **WHEN** 用户访问 `/unknown-page`
- **THEN** 显示 404 页面，提供返回首页链接

### Requirement: Sidebar 登出调用后端 API
前端登出操作 SHALL 调用后端 `/auth/logout` 接口将 token 加入黑名单。

#### Scenario: 用户点击登出
- **WHEN** 用户点击登出按钮
- **THEN** 调用后端 logout API，清除本地 token，跳转登录页

### Requirement: Dashboard 系统状态实时检测
Dashboard 系统状态 SHALL 通过后端健康检查接口实时获取，而非前端硬编码。

#### Scenario: 查看系统状态
- **WHEN** 用户访问 Dashboard
- **THEN** 系统状态区域显示后端、数据库、Redis 的真实连接状态

### Requirement: 黑名单过期条目自动标记
黑名单过期条目 SHALL 在查询时自动标记为过期状态，前端可区分显示。

#### Scenario: 查询黑名单
- **WHEN** 黑名单条目的 `expires_at` 已过期
- **THEN** 后端返回 `is_expired: true` 字段

## MODIFIED Requirements

### Requirement: CORS 配置
CORS 允许源 SHALL 从环境变量 `BACKEND_CORS_ORIGINS` 读取，不再硬编码默认值。生产环境必须显式配置。

### Requirement: Prometheus 监控
Prometheus 监控 SHALL 仅在非生产环境或显式配置 `ENABLE_METRICS=true` 时启用，移除 `or True` 的硬编码。

### Requirement: SangforService 连接管理
SangforService SHALL 使用上下文管理器模式管理 HTTP 客户端生命周期，避免连接泄漏。当前 `close()` 方法依赖调用方手动调用，容易遗漏。

## REMOVED Requirements

### Requirement: 前端全量数据加载+本地分页
**Reason**: 数据量大时性能差，改为服务端分页
**Migration**: 前端所有列表页面改为传递分页参数给后端，后端返回分页结果
