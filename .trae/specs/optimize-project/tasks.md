# Tasks

- [x] Task 1: 后端 API 分页与搜索优化 — 将所有列表接口改为服务端分页，返回 `{items, total, page, page_size}` 结构
  - [x] SubTask 1.1: 创建通用分页响应 Schema（`PaginatedResponse` 泛型模型）
  - [x] SubTask 1.2: 改造 `/mac/search` 接口支持服务端分页和搜索，返回分页结果
  - [x] SubTask 1.3: 改造 `/whitelist/` 接口支持服务端分页和搜索
  - [x] SubTask 1.4: 改造 `/blacklist/` 接口支持服务端分页和搜索
  - [x] SubTask 1.5: 改造 `/logs/` 接口支持服务端分页、按 action/username/日期范围搜索
  - [x] SubTask 1.6: 改造 `mac_service.py` 中对应的查询方法，支持 count 查询和 offset/limit

- [x] Task 2: Dashboard 统计接口 — 新增 `/stats` 接口，返回仪表板所需统计数据
  - [x] SubTask 2.1: 创建 `StatsResponse` Schema
  - [x] SubTask 2.2: 在 `mac_service.py` 中实现 `get_stats()` 方法（使用 SQL COUNT 聚合查询）
  - [x] SubTask 2.3: 创建 `/stats` 端点

- [x] Task 3: 后端输入校验增强 — 在 Schema 层添加 MAC 地址和 IP 地址格式校验
  - [x] SubTask 3.1: 在 `mac_address.py` Schema 中添加 MAC 地址格式校验器（支持多种分隔符格式）
  - [x] SubTask 3.2: 在 `mac_address.py` Schema 中添加 IP 地址格式校验器
  - [x] SubTask 3.3: 在 `BlacklistCreate` 和 `WhitelistCreate` 中应用校验器

- [x] Task 4: 审计日志记录操作者 IP — 从请求中提取客户端 IP 并写入审计日志
  - [x] SubTask 4.1: 修改 `mac_service.py` 中的 `_log_action` 方法，增加 `ip_address` 参数
  - [x] SubTask 4.2: 在各 endpoint 中从 `Request` 对象提取客户端 IP（X-Forwarded-For / remote host）
  - [x] SubTask 4.3: 将 IP 地址传递到 service 层的审计日志方法

- [x] Task 5: 健康检查与安全修复
  - [x] SubTask 5.1: 修复 `/health` 端点的 Redis 连接泄漏，复用 `security.py` 中的 Redis 客户端
  - [x] SubTask 5.2: 移除 Prometheus 的 `or True` 硬编码，改为配置项控制
  - [x] SubTask 5.3: 修改 CORS 默认配置，生产环境不使用硬编码默认值

- [x] Task 6: SangforService 连接管理优化 — 改为上下文管理器模式
  - [x] SubTask 6.1: 将 `SangforService` 改为异步上下文管理器（`__aenter__`/`__aexit__`）
  - [x] SubTask 6.2: 更新 `mac_service.py` 中的调用方式，使用 `async with` 模式

- [x] Task 7: 黑名单过期标记 — 查询时自动标记过期状态
  - [x] SubTask 7.1: 在 `BlacklistResponse` Schema 中添加 `is_expired` 计算字段
  - [x] SubTask 7.2: 在查询时计算并返回过期状态

- [x] Task 8: 前端 Token 自动刷新机制
  - [x] SubTask 8.1: 在 `apiClient` 拦截器中实现 401 自动刷新逻辑
  - [x] SubTask 8.2: 刷新失败时清除 token 并跳转登录页
  - [x] SubTask 8.3: 处理并发请求时的 token 刷新（避免多次刷新）

- [x] Task 9: 前端服务端分页改造 — 所有列表页面改为服务端分页
  - [x] SubTask 9.1: 改造 `useMacData.ts` hooks，传递分页/搜索参数给后端
  - [x] SubTask 9.2: 改造 `MacAddresses.tsx` 使用服务端分页
  - [x] SubTask 9.3: 改造 `Whitelist.tsx` 使用服务端分页
  - [x] SubTask 9.4: 改造 `Blacklist.tsx` 使用服务端分页
  - [x] SubTask 9.5: 改造 `AuditLogs.tsx` 使用服务端分页

- [x] Task 10: Dashboard 系统状态实时检测
  - [x] SubTask 10.1: 新增 `useSystemStatus` hook 调用 `/health` 接口
  - [x] SubTask 10.2: 改造 `Dashboard.tsx` 的系统状态区域，显示真实后端/DB/Redis 状态

- [x] Task 11: Sidebar 登出调用后端 API
  - [x] SubTask 11.1: 修改 `auth.ts` store 的 `logout` 方法，先调用后端 `/auth/logout`
  - [x] SubTask 11.2: 即使后端调用失败也清除本地 token

- [x] Task 12: 前端 404 和全局错误页面
  - [x] SubTask 12.1: 创建 `NotFound.tsx` 404 页面组件
  - [x] SubTask 12.2: 在 `App.tsx` 路由中添加 `*` 通配路由

# Task Dependencies
- [Task 9] depends on [Task 1] — 前端分页改造依赖后端分页接口
- [Task 10] depends on [Task 5] — Dashboard 系统状态依赖健康检查修复
- [Task 8] 可独立进行
- [Task 2] 可独立进行，但前端 Dashboard 统计展示依赖此接口
- [Task 3, 4, 6, 7, 11, 12] 可独立并行进行
