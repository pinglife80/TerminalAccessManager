# 前端实现总结

> 文档版本：v3.2.0 | 更新日期：2026-06-10

## 概述

TerminalAccessManager 的前端已使用现代 React + TypeScript 技术栈完整实现，包含认证系统、终端合规监控、数据源管理、白名单/黑名单管理、审计日志、用户管理等全部核心功能，以及品牌动态配置系统。

---

## 已构建内容

### 1. 项目结构
```
frontend/
├── src/
│   ├── components/       # 可复用 UI 组件
│   │   ├── Layout.tsx           # 主布局（顶栏 + 侧边栏 + 内容 + 页脚）
│   │   ├── Sidebar.tsx          # 可折叠侧边栏导航（hover 预加载）
│   │   ├── HeaderControls.tsx   # 顶栏控件（主题切换 + 语言选择）
│   │   ├── Modal.tsx            # 统一模态框组件（ESC 关闭、焦点管理、ARIA 属性）
│   │   ├── Pagination.tsx       # 高级分页组件（top/bottom 变体）
│   │   ├── DateRangeFilter.tsx  # 日期范围过滤器
│   │   ├── Button.tsx           # 按钮组件（PrimaryButton/IconButton/ButtonGroup）
│   │   ├── StateDisplay.tsx     # 状态显示组件（EmptyState/LoadingState）
│   │   ├── Skeleton.tsx         # 骨架屏组件
│   │   ├── ProtectedRoute.tsx   # 路由保护包装器
│   │   ├── ErrorBoundary.tsx    # 错误边界组件
│   │   └── datasources/         # 数据源管理子组件
│   │       ├── DataSourcesTab.tsx
│   │       ├── ComplianceBaselinesTab.tsx
│   │       ├── BindingsTab.tsx
│   │       └── shared.ts        # 共享类型和配置
│   ├── config/           # 配置
│   │   └── branding.ts          # 品牌自定义配置
│   ├── hooks/            # 自定义 Hooks
│   │   ├── useTerminalData.ts    # 数据查询 Hooks（终端、白名单、统计）
│   │   └── useNetworkStatus.ts   # 网络状态检测 Hook
│   ├── i18n/             # 国际化
│   │   ├── index.ts             # i18n 配置（i18next + browser-languagedetector）
│   │   └── locales/             # 翻译文件
│   │       ├── zh.ts            # 中文翻译
│   │       ├── en.ts            # 英文翻译
│   │       └── ja.ts            # 日语翻译
│   ├── lib/              # 工具和 API 客户端
│   │   ├── api.ts               # 带拦截器的 Axios 客户端
│   │   ├── constants.ts         # 常量定义（状态、导航、API 端点等）
│   │   ├── utils.ts             # 工具函数（日期格式化、CSV 导出、MAC/IP 验证等）
│   │   ├── logger.ts            # 统一前端日志工具（debug/info/warn/error 四级，内存缓冲 + localStorage 持久化）
│   │   └── __tests__/    # 工具函数测试
│   │       └── utils.test.ts        # 工具函数测试（42 用例）
│   ├── pages/            # 页面组件
│   │   ├── Login.tsx            # 登录页（验证码、账户锁定、深色主题、i18n）
│   │   ├── Dashboard.tsx        # 主仪表板
│   │   ├── Terminals.tsx         # 终端管理
│   │   ├── Whitelist.tsx        # 白名单管理（MAC 格式无关搜索、keepPreviousData）
│   │   ├── Blacklist.tsx        # 黑名单管理（MAC 格式无关搜索、keepPreviousData）
│   │   ├── AuditLogs.tsx        # 审计日志（8 类分类过滤、彩色 badge、JSON details）
│   │   ├── DataSources.tsx      # 数据源管理（管理员专属，Tab 容器）
│   │   ├── Users.tsx            # 用户管理（管理员专属）
│   │   └── Profile.tsx          # 个人资料
│   ├── store/            # 状态管理
│   │   ├── auth.ts              # 认证状态管理（initializeAuth timeout 10s）
│   │   ├── branding.ts         # 品牌动态配置 store（useBrandingStore）
│   │   ├── theme.ts            # 主题状态管理（Light/Dark/System + localStorage 持久化）
│   │   └── __tests__/  # 状态管理测试
│   │       ├── theme.test.ts        # 主题 store 测试（8 用例）
│   │       └── auth.test.ts         # 认证 store 测试（8 用例）
│   ├── App.tsx           # 带路由的主应用（Suspense 在 Layout Outlet 外层）
│   ├── main.tsx          # 入口点
│   ├── index.css         # TailwindCSS 全局样式
│   └── vite-env.d.ts     # Vite 类型声明
│   ├── test/             # 测试
│   │   └── setup.ts             # 测试环境配置（jest-dom + matchMedia mock）
├── public/               # 静态资源
│   └── favicon.svg              # 网站图标
├── package.json          # 依赖和脚本
├── tsconfig.json         # TypeScript 配置
├── tsconfig.node.json    # Node 特定 TS 配置
├── vite.config.ts        # Vite 构建配置
├── vitest.config.ts      # Vitest 测试配置
├── .eslintrc.json        # ESLint 配置
├── tailwind.config.js    # TailwindCSS 配置
├── postcss.config.js     # PostCSS 配置
├── index.html            # HTML 入口点
├── .env.production       # 生产环境变量
├── nginx.conf            # Nginx 配置
├── Dockerfile            # Docker 构建
└── .gitignore            # Git 忽略规则
```

### 2. 核心功能

#### 认证系统
- 登录页面带表单验证
- 验证码机制：从后端 `GET /auth/captcha` 获取（返回 `captcha_id` + `question`），移除本地验证码生成和校验；提交时传 `captcha_id` + `captcha`（答案）参数
- 账户锁定机制（连续失败 5 次后锁定 15 分钟）
- 移除 `/auth/login-status` 轮询逻辑，改为从登录失败的错误响应体（JSON detail）获取 `captcha_required` / `locked` / `lock_remaining` 状态
- JWT 令牌存储在 sessionStorage
- 令牌过期时自动刷新
- 受保护路由（未认证时重定向到登录页）
- 登出功能
- 用户会话持久化
- 启动时认证状态恢复（`initializeAuth()`）：应用启动时检查 sessionStorage → 调用 `/auth/me` 验证 token → 失效则尝试 refresh → 全部失败则清除会话
- `initializeAuth` timeout 10s：网络异常时 10 秒后超时降级，避免页面永久加载
- `isInitializing` 状态：恢复期间为 `true`，页面显示加载状态，避免未认证闪烁
- App.tsx 启动时自动调用 `initializeAuth()`
- 全局错误监听：App.tsx useEffect 注册 `window.error` 和 `window.unhandledrejection` 事件监听，使用 `logger.error` 记录未捕获错误

#### API 集成
- 配置好的 Axios HTTP 客户端
- 请求拦截器（自动附加 JWT 令牌）
- 响应拦截器（处理 401 错误，自动刷新令牌）
- 401 拦截器并发控制：`isRefreshing` 标志锁定 + `failedQueue` 队列，多个 401 仅触发一次刷新
- 排队请求 `_retry` 防循环：标记已重试的请求，避免 refresh 失败后无限循环
- React Query 401 不重试：配置 `retry` 函数，401 状态码不触发自动重试
- 刷新失败时 toast 提示用户"会话已过期，请重新登录"
- 通过 toast 通知的错误处理
- Vite 开发服务器中配置的后端代理
- 30 秒请求超时

#### 状态管理
- Zustand store 管理认证
- Zustand store 管理品牌动态配置（useBrandingStore，从后端动态加载品牌设置）
- 跨页面重载的持久认证状态
- 类型安全的状态管理
- TanStack Query 管理服务端数据缓存

#### UI 组件
- 可折叠侧边栏导航（Logo 区域固定高度 `h-10`，防止折叠/展开时布局跳动，hover 预加载目标页面数据）
- HeaderControls 顶栏控件（主题切换浅色/深色/跟随系统三选项并列 + 语言选择 Globe 下拉菜单）
- 主布局（顶栏 + 侧边栏 + 内容区 + 页脚）
- 高级分页组件（支持 top/bottom 变体、每页条数选择）
- 日期范围过滤器
- 按钮组件（PrimaryButton/IconButton/ButtonGroup）
- 空状态和加载状态组件
- 骨架屏加载占位
- 统一 Modal 组件（ESC 关闭、焦点 trap、ARIA 属性、点击遮罩关闭、body 滚动锁定）
- 错误边界组件（使用 `logger.error` 记录捕获的错误，替代 `console.error`）
- Toast 通知（成功/错误消息）
- 确认对话框

#### 样式
- TailwindCSS 实用优先框架
- 自定义配色方案（主蓝色调色板）
- 响应式设计（移动优先）
- 现代图标（Lucide React）

#### 开发者体验
- TypeScript 类型安全
- 路径别名（@/* 导入）
- 热模块替换（Vite）
- ESLint 配置
- 全面的文档
- Vitest 测试框架（58 个测试用例）
- ESLint 代码质量检查（.eslintrc.json）

---

## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| 框架 | React 18 | UI 库 |
| 语言 | TypeScript | 类型安全 |
| 构建工具 | Vite 5 | 快速开发服务器和打包器 |
| 路由 | React Router 6 | 客户端路由 |
| 样式 | TailwindCSS 3 | 实用优先 CSS |
| 状态 | Zustand 4 | 轻量级状态管理 |
| 数据获取 | TanStack Query 5 | 服务端状态和缓存 |
| 表单 | React Hook Form 7 | 表单验证 |
| HTTP | Axios 1.6 | API 客户端 |
| 图标 | Lucide React | 图标库 |
| 通知 | Sonner | Toast 消息 |
| 国际化 | i18next + react-i18next + i18next-browser-languagedetector | 多语言支持（中文/英文/日语），自动检测浏览器语言，语言持久化 localStorage |

---

## 关键实现细节

### 1. 认证流程

```typescript
// 登录 → 存储令牌 → 重定向到仪表板
loginMutation.mutate({ username, password })
  ↓
onSuccess: (data) => {
  login(data.user, data.access_token, data.refresh_token)
  navigate('/dashboard')
}
  ↓
令牌存储在 sessionStorage
认证状态在 Zustand store 中更新
```

### 2. 验证码与账户锁定

```typescript
// 验证码从后端获取，不再本地生成
// GET /auth/captcha → { captcha_id: string, question: string }
// 登录时传 captcha_id + captcha（答案）参数

// 连续失败 5 次后锁定账户 15 分钟
const LOCK_THRESHOLD = 5;
const LOCK_DURATION = 15 * 60 * 1000;

// 登录失败时从错误响应体获取状态（不再轮询 /auth/login-status）
// 错误响应体格式：{"detail": {"message": "...", "captcha_required": true, "locked": false}}
```

### 3. 令牌刷新机制

```typescript
// Axios 响应拦截器 — 带并发控制 + 防循环
let isRefreshing = false;
let failedQueue: Array<{ resolve: Function; reject: Function }> = [];

if (error.response?.status === 401 && !originalRequest._retry) {
  if (isRefreshing) {
    // 已有刷新进行中，加入等待队列
    return new Promise((resolve, reject) => {
      failedQueue.push({ resolve, reject });
    }).then(token => {
      originalRequest.headers.Authorization = `Bearer ${token}`;
      return apiClient(originalRequest);
    });
  }

  originalRequest._retry = true; // 防止循环重试
  isRefreshing = true;
  // 使用刷新令牌获取新令牌（通过 Body 传递 refresh_token）
  const response = await axios.post('/auth/refresh', {
    refresh_token: refreshToken,
  })

  // 更新 sessionStorage
  sessionStorage.setItem('access_token', newAccessToken)
  sessionStorage.setItem('refresh_token', newRefreshToken)

  // 重试队列中所有等待的请求
  failedQueue.forEach(({ resolve }) => resolve(newAccessToken));
  failedQueue = [];
  isRefreshing = false;

  // 重试原始请求
  return apiClient(originalRequest)
}

// 刷新失败时：清除会话 + toast 提示
toast.error('会话已过期，请重新登录');
```

### 4. 受保护路由

```typescript
// 包裹任何需要认证的路由
<ProtectedRoute>
  <Layout />
</ProtectedRoute>

// 未认证时自动重定向到 /login
```

### 5. API 客户端配置

```typescript
const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// 自动为每个请求附加令牌
apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### 6. 统一日志工具（lib/logger.ts）

前端日志工具 `logger` 提供统一的日志记录接口，支持 debug/info/warn/error 四个级别：

- **环境分级输出**：开发环境输出所有级别日志，生产环境仅输出 warn/error
- **内存缓冲区**：保留最近 100 条日志记录，可通过 `logger.getBuffer()` 获取
- **localStorage 持久化**：自动持久化 warn/error 级别日志（最多 50 条），可通过 `logger.getStored()` 获取
- **日志导出与清理**：`logger.exportLogs()` 导出全部日志（含缓冲区和持久化），`logger.clearLogs()` 清除所有日志

```typescript
// API 概览
logger.debug('调试信息', { data });
logger.info('常规信息');
logger.warn('警告信息');
logger.error('错误信息', error);

logger.getBuffer();    // 获取内存缓冲区日志（最近 100 条）
logger.getStored();    // 获取 localStorage 持久化日志（warn/error，最多 50 条）
logger.exportLogs();   // 导出全部日志
logger.clearLogs();    // 清除所有日志
```

**日志时区本地化**：`formatTimestamp()` 使用本地时区 + 偏移量格式（如 `2026-06-10T14:30:00.123+08:00`），与后端日志时区保持一致（后端通过 TZ 配置项控制）。

**渐进式接入策略**：当前仅在 App.tsx（全局错误监听）和 ErrorBoundary 中使用，后续将逐步扩展到其他模块。

---

## 当前页面

### 1. 登录页面 (`/login`)
**功能：**
- 用户名/密码表单
- 实时验证
- 验证码机制：从后端 `GET /auth/captcha` 获取（`captcha_id` + `question`），移除本地验证码生成和校验；提交时传 `captcha_id` + `captcha`（答案）参数
- 账户锁定机制（连续失败 5 次后锁定 15 分钟）
- 移除 `/auth/login-status` 轮询逻辑，改为从登录失败的错误响应体（JSON detail）获取 `captcha_required` / `locked` / `lock_remaining` 状态
- 加载状态
- 通过 toast 显示错误消息
- 品牌自定义（标题、副标题、背景、按钮样式）
- 盾牌图标品牌
- 深色主题支持：背景改用 `bg-background` 语义化颜色，各区域添加 `dark:` 变体
- 副标题/页脚使用 i18n 翻译键（优先使用 i18n 翻译，回退到品牌配置）

### 2. 仪表板 (`/dashboard`)
**功能：**
- 带用户信息的欢迎头部
- 统计卡片（Total/Normal/Bypass/Blocked/Pending，共 5 个）
- 快速操作面板（跳转到终端管理、白名单、黑名单、审计日志）
- 系统状态指示器
- 骨架屏加载状态
- 错误状态处理

### 3. 终端管理 (`/terminals`)
**功能：**
- 终端列表数据表格
- 搜索过滤（debounce 防抖 + 服务端模糊搜索，按 IP/MAC 地址）
- 状态过滤（active/inactive/frozen/pending/unfrozen/bypass）
- 日期范围过滤
- 服务端分页（PaginatedResponse：items / total / page / page_size / total_pages）
- 封禁/解封操作
- 添加到白名单操作
- 终端详情弹窗
- CSV 导出
- 可折叠过滤器面板
- 空状态和加载状态

### 4. 白名单管理 (`/whitelist`)
**功能：**
- 白名单列表数据表格
- 搜索过滤（debounce 防抖 + 服务端模糊搜索，按 MAC/IP 地址）
- MAC 地址格式无关搜索（后端去除分隔符后 ILIKE 匹配，前端 `keepPreviousData` 防搜索闪烁）
- 日期范围过滤
- 服务端分页（PaginatedResponse）
- 添加白名单条目（支持 MAC 地址、IP 地址、CIDR/范围）
- 删除白名单条目（带确认对话框）
- MAC 地址格式自动标准化
- 输入验证（MAC 地址、IP 地址、CIDR/范围格式）
- CSV 导出
- 可折叠过滤器面板
- 空状态和加载状态

### 5. 黑名单管理 (`/blacklist`)
**功能：**
- 黑名单列表数据表格
- 搜索过滤（debounce 防抖 + 服务端模糊搜索，按 MAC/IP 地址）
- MAC 地址格式无关搜索（后端去除分隔符后 ILIKE 匹配，前端 `keepPreviousData` 防搜索闪烁）
- 日期范围过滤
- 服务端分页（PaginatedResponse）
- 添加黑名单条目（MAC 地址、IP 地址、原因、过期时间）
- 删除黑名单条目（带确认对话框）
- 查看详情弹窗
- MAC 地址格式自动标准化
- 输入验证
- CSV 导出
- 可折叠过滤器面板
- 空状态和加载状态

### 6. 审计日志 (`/audit-logs`)
**功能：**
- 审计日志列表数据表格
- 搜索过滤（debounce 防抖 + 服务端模糊搜索，按用户名、操作、详情）
- 8 类分类过滤（认证、终端操作、白名单、黑名单、用户管理、数据源、合规、配置变更）
- action 彩色 badge（不同操作类型使用不同颜色标识）
- resource 展示优化（突出显示资源类型和 ID）
- details JSON 解析展示（自动解析 JSON 格式的 details 字段，格式化展示结构化信息）
- 操作类型过滤
- 日期范围过滤
- 服务端分页（PaginatedResponse）
- 日志详情弹窗
- CSV 导出
- 可折叠过滤器面板
- 空状态和加载状态

### 7. 数据源管理 (`/data-sources`)（管理员专属）
**功能：**
- 数据源列表数据表格
- 添加/编辑/删除数据源
- 数据源绑定管理（绑定 MAC 地址到数据源）
- 合规检查操作
- 自动封禁/自动解封配置
- Compliance Baselines Tab（合规基准管理，支持 CRUD、测试连接、手动同步）
- DataSources 拆分为独立 Tab 组件（DataSourcesTab、ComplianceBaselinesTab、BindingsTab、shared）
- 搜索和过滤
- 高级分页
- 空状态和加载状态

### 8. 用户管理 (`/users`)（管理员专属）
**功能：**
- 用户列表数据表格
- 添加/编辑/删除用户
- 角色分配
- 搜索过滤
- 高级分页
- 空状态和加载状态

### 9. 个人资料 (`/profile`)
**功能：**
- 查看和编辑个人资料信息
- 修改密码
- 个人信息展示

---

## 创建的文件

### 配置文件（10）
1. `package.json` - 依赖和脚本
2. `tsconfig.json` - TypeScript 配置
3. `tsconfig.node.json` - Node 特定 TS 配置
4. `vite.config.ts` - Vite 构建配置（含代理）
5. `tailwind.config.js` - TailwindCSS 自定义
6. `postcss.config.js` - PostCSS 插件
7. `.env.production` - 生产环境变量
8. `.gitignore` - Git 忽略规则
9. `vitest.config.ts` - Vitest 测试配置
10. `.eslintrc.json` - ESLint 配置

### 基础设施文件（3）
1. `index.html` - HTML 入口点
2. `Dockerfile` - Docker 构建
3. `nginx.conf` - Nginx 配置

### 源代码文件（37）
1. `src/main.tsx` - React 入口点
2. `src/App.tsx` - 带路由的主应用
3. `src/index.css` - 带 Tailwind 的全局样式
4. `src/vite-env.d.ts` - Vite 类型声明
5. `src/lib/api.ts` - Axios 客户端设置
6. `src/lib/constants.ts` - 常量定义（已移除 `AUTH_LOGIN_STATUS` 常量，新增 `AUTH_CAPTCHA` 常量指向 `/auth/captcha`）
7. `src/lib/utils.ts` - 工具函数
8. `src/lib/logger.ts` - 统一前端日志工具（debug/info/warn/error 四级，内存缓冲 + localStorage 持久化）
9. `src/config/branding.ts` - 品牌自定义配置
10. `src/store/auth.ts` - 认证 store（登录错误处理改为解析结构化 JSON detail，而非响应头；错误响应体格式：`{"detail": {"message": "...", "captcha_required": true, "locked": false}}`）
11. `src/store/branding.ts` - 品牌动态配置 store（useBrandingStore）
12. `src/store/theme.ts` - 主题状态管理（Light/Dark/System + localStorage 持久化）
13. `src/hooks/useTerminalData.ts` - 数据查询 Hooks
14. `src/hooks/useNetworkStatus.ts` - 网络状态检测 Hook
15. `src/i18n/index.ts` - i18n 配置（i18next + browser-languagedetector）
16. `src/i18n/locales/zh.ts` - 中文翻译
17. `src/i18n/locales/en.ts` - 英文翻译
18. `src/i18n/locales/ja.ts` - 日语翻译
19. `src/components/Layout.tsx` - 主布局组件（顶栏 + 侧边栏 + 内容区 + 页脚）
20. `src/components/Sidebar.tsx` - 侧边栏导航（hover 预加载）
21. `src/components/HeaderControls.tsx` - 顶栏控件（主题切换 + 语言选择）
22. `src/components/Modal.tsx` - 统一模态框组件
23. `src/components/Pagination.tsx` - 分页组件
24. `src/components/DateRangeFilter.tsx` - 日期范围过滤器
25. `src/components/Button.tsx` - 按钮组件
26. `src/components/StateDisplay.tsx` - 状态显示组件
27. `src/components/Skeleton.tsx` - 骨架屏组件
28. `src/components/ProtectedRoute.tsx` - 路由守卫
29. `src/components/ErrorBoundary.tsx` - 错误边界（使用 logger.error 记录捕获的错误）
30. `src/components/datasources/DataSourcesTab.tsx` - 数据源 Tab 组件
31. `src/components/datasources/ComplianceBaselinesTab.tsx` - 合规基准 Tab 组件
32. `src/components/datasources/BindingsTab.tsx` - 绑定关系 Tab 组件
33. `src/components/datasources/shared.ts` - 数据源共享类型和配置
34. `src/test/setup.ts` - 测试环境配置
35. `src/lib/__tests__/utils.test.ts` - 工具函数测试
36. `src/store/__tests__/theme.test.ts` - 主题 store 测试
37. `src/store/__tests__/auth.test.ts` - 认证 store 测试

### 页面文件（9）
1. `src/pages/Login.tsx` - 登录页面
2. `src/pages/Dashboard.tsx` - 仪表板页面
3. `src/pages/Terminals.tsx` - 终端管理页面
4. `src/pages/Whitelist.tsx` - 白名单管理页面
5. `src/pages/Blacklist.tsx` - 黑名单管理页面
6. `src/pages/AuditLogs.tsx` - 审计日志页面
7. `src/pages/DataSources.tsx` - 数据源管理页面（管理员专属）
8. `src/pages/Users.tsx` - 用户管理页面（管理员专属）
9. `src/pages/Profile.tsx` - 个人资料页面

### 静态资源（1）
1. `public/favicon.svg` - 网站图标

---

## 当前可用功能

- 安装依赖：`npm install`
- 启动开发服务器：`npm run dev`
- 在 `http://localhost:3000` 查看登录页面
- 提交登录表单
- 验证码机制（从后端 `GET /auth/captcha` 获取，提交 `captcha_id` + `captcha` 答案）
- 账户锁定机制（连续失败 5 次后锁定 15 分钟）
- 从后端接收 JWT 令牌
- 在 sessionStorage 中存储令牌
- 登录后重定向到仪表板
- 查看带统计卡片的仪表板
- 快速操作跳转到各管理页面
- 终端管理：搜索、过滤、分页、封禁/解封、添加白名单、CSV 导出
- 白名单管理：增删查、搜索、分页、日期过滤、CSV 导出
- 黑名单管理：增删查、搜索、分页、日期过滤、详情查看、CSV 导出
- 审计日志：搜索、操作过滤、日期过滤、分页、详情查看、CSV 导出
- 点击登出按钮
- 清除令牌并重定向到登录页
- 受保护路由阻止未授权访问
- 自动刷新过期令牌
- 成功/错误的 Toast 通知
- 品牌自定义（应用名称、Logo、登录页样式、页脚信息）

---

## 品牌自定义

项目通过 `src/config/branding.ts` 实现品牌自定义，所有可定制的品牌元素集中在该配置文件中，修改此文件即可适配不同公司/部署场景。

### 可配置项

| 配置项 | 说明 |
|--------|------|
| `appName` | 应用名称，显示在侧边栏、登录页和浏览器标题 |
| `appShortName` | 侧边栏展开时的短名称 |
| `appSubtitle` | 侧边栏中应用名称下方的副标题 |
| `version` | 页脚显示的版本号 |
| `title` | 浏览器标签页标题 |
| `favicon` | 网站图标路径（文件放于 `public/` 目录） |
| `logo` | Logo 配置，支持 Lucide 图标（type: 'icon'）或自定义图片（type: 'image'） |
| `login.heading` | 登录页标题 |
| `login.subheading` | 登录页副标题（优先使用 i18n 翻译键 `login.subheading`，回退到品牌配置） |
| `login.footerText` | 登录卡片底部文字（优先使用 i18n 翻译键 `login.footerText`，回退到品牌配置） |
| `login.background` | 登录页背景，支持渐变（type: 'gradient'）或背景图片（type: 'image'） |
| `login.buttonGradient` | 登录按钮渐变色 |
| `login.headerGradient` | 登录页头部渐变色 |
| `footer.copyright` | 页脚版权信息（`{year}` 会被替换为当前年份） |
| `footer.icpNumber` | ICP 备案号（留空则隐藏） |
| `footer.icpUrl` | ICP 备案链接 |
| `footer.links` | 页脚额外链接列表 |

### 自定义示例

**使用自定义 Logo 图片：**
1. 将 Logo 文件放入 `public/` 目录
2. 修改 `branding.ts` 中 `logo.type` 为 `'image'`，并设置 `logo.path`

**使用自定义登录背景：**
1. 将背景图片放入 `public/` 目录
2. 修改 `branding.ts` 中 `login.background.type` 为 `'image'`，并设置 `imagePath`

---

## 与后端的集成点

### 已连接
- `POST /api/v1/auth/login` - 用户认证
- `GET /api/v1/auth/captcha` - 获取验证码（captcha_id + question）
- `POST /api/v1/auth/refresh` - 令牌刷新（refresh_token 通过 Body 传递）
- `GET /api/v1/auth/me` - 获取当前用户信息
- `POST /api/v1/auth/register` - 用户注册
- `GET /api/v1/auth/users` - 用户列表（CRUD）
- `POST /api/v1/auth/users` - 创建用户
- `PUT /api/v1/auth/users/{id}` - 更新用户
- `DELETE /api/v1/auth/users/{id}` - 删除用户
- `GET /api/v1/terminals/search` - 搜索终端
- `GET /api/v1/terminals/` - 列出终端
- `POST /api/v1/terminals/block/{ip}` - 封禁 IP
- `POST /api/v1/terminals/unblock/{ip}` - 解封 IP
- `GET /api/v1/whitelist/` - 列出白名单
- `POST /api/v1/whitelist/` - 添加到白名单
- `DELETE /api/v1/whitelist/{mac}` - 从白名单移除
- `GET /api/v1/blacklist/` - 列出黑名单
- `POST /api/v1/blacklist/` - 添加到黑名单
- `DELETE /api/v1/blacklist/{id}` - 从黑名单移除
- `GET /api/v1/logs/` - 列出审计日志
- `GET /api/v1/logs/search` - 搜索审计日志
- `GET /api/v1/logs/export` - 导出审计日志
- `GET /api/v1/data-sources/` - 列出数据源（CRUD）
- `POST /api/v1/data-sources/` - 创建数据源
- `PUT /api/v1/data-sources/{id}` - 更新数据源
- `DELETE /api/v1/data-sources/{id}` - 删除数据源
- `GET /api/v1/data-sources/bindings/` - 列出数据源绑定（CRUD）
- `POST /api/v1/data-sources/bindings/` - 创建数据源绑定
- `PUT /api/v1/data-sources/bindings/{id}` - 更新数据源绑定
- `DELETE /api/v1/data-sources/bindings/{id}` - 删除数据源绑定
- `POST /api/v1/data-sources/compliance/check` - 合规检查
- `POST /api/v1/data-sources/compliance/auto-block` - 自动封禁
- `POST /api/v1/data-sources/compliance/auto-unblock` - 自动解封
- `GET /api/v1/compliance-baselines/` - 列出合规基准
- `POST /api/v1/compliance-baselines/` - 创建合规基准
- `GET /api/v1/compliance-baselines/{id}` - 获取合规基准详情
- `PUT /api/v1/compliance-baselines/{id}` - 更新合规基准
- `DELETE /api/v1/compliance-baselines/{id}` - 删除合规基准
- `POST /api/v1/compliance-baselines/{id}/test` - 测试合规基准连接
- `POST /api/v1/compliance-baselines/{id}/sync` - 同步合规基准
- `GET /api/v1/stats/` - 统计数据
- `GET /api/v1/stats/system-status` - 系统状态
- `GET /api/v1/settings/` - 获取系统设置（含品牌配置）
- `PUT /api/v1/settings/` - 更新系统设置

---

## 性能优化

### 已实现
- 通过 Vite 代码分割
- Tree shaking（ES 模块）
- 懒加载就绪（React.lazy）
- 高效重渲染（React.memo 就绪）
- 查询缓存（TanStack Query，staleTime 30s 减少重复请求）
- 登录后数据预取（prefetchQuery）
- Sidebar hover 预加载（鼠标悬停时预加载目标页面数据）
- 骨架屏加载占位
- 搜索防抖（debounce 300ms，减少服务端请求）
- 服务端分页（PaginatedResponse 统一分页结构，避免前端全量加载）
- Suspense 位置优化（移到 Layout Outlet 外层，避免路由切换闪烁）
- keepPreviousData（白名单/黑名单搜索时保持旧数据，防止闪烁）

### 未来改进
- 大表格的虚拟滚动
- 图片优化
- 离线支持的 Service Worker
- 包大小监控

---

## 安全特性

### 已实现
- HTTPS 就绪（Vite 支持 SSL）
- XSS 保护（React 默认转义）
- CSRF 保护（JWT 在 Authorization 头中）
- 安全令牌存储（sessionStorage 带刷新）
- 输入验证（React Hook Form + 自定义验证）
- 受保护路由（需要认证）
- 验证码机制（后端验证码，防止暴力破解）
- 账户锁定机制（连续失败后锁定）
- 错误边界（防止 UI 崩溃，使用 logger.error 记录错误）

### 生产建议
- 启用 CSP 头
- 使用 HttpOnly cookies 替代 sessionStorage
- 启用 HSTS
- 定期更新依赖

---

## 测试策略

### 已实现

**测试框架：** Vitest + @testing-library/react + @testing-library/jest-dom

**测试配置：**

| 文件 | 说明 |
|------|------|
| `vitest.config.ts` | Vitest 配置（React 插件、jsdom 环境、路径别名、setup 文件） |
| `src/test/setup.ts` | 测试环境配置（引入 jest-dom matchers、window.matchMedia mock） |

**测试文件清单：**

| 文件 | 用例数 | 覆盖范围 |
|------|:------:|---------|
| `src/lib/__tests__/utils.test.ts` | 42 | 日期格式化、CSV 导出、MAC/IP 验证、状态映射等工具函数 |
| `src/store/__tests__/theme.test.ts` | 8 | 主题切换（Light/Dark/System）、localStorage 持久化 |
| `src/store/__tests__/auth.test.ts` | 8 | 登录/登出、token 存储、认证状态管理 |
| **合计** | **58** | |

**运行测试：**

```bash
npm test           # 运行所有测试
npm run test:watch # 监听模式
```

### 待实现

#### 集成测试
- 登录流程
- API 集成
- 路由导航
- 令牌刷新

#### E2E 测试
- 完整用户工作流
- 跨浏览器测试
- 移动响应性

**推荐工具：**
- Playwright 或 Cypress（E2E）

---

## 部署选项

### 选项 1：静态托管
```bash
npm run build
# 上传 dist/ 到 Netlify, Vercel, S3 等
```

### 选项 2：Docker（推荐）
```bash
./manage.sh deploy --demo   # 或 --prod
```

### 选项 3：Nginx
```bash
npm run build
# 使用项目自带的 nginx.conf 提供 dist/
```

---

## 浏览器支持

- Chrome（最新）
- Firefox（最新）
- Safari（最新）
- Edge（最新）
- 移动浏览器（iOS Safari, Chrome Mobile）

---

## 结论

前端已完整实现，包括：
- 现代技术栈
- 完整的认证系统（含后端验证码和账户锁定，登录错误解析结构化 JSON detail，initializeAuth timeout 10s）
- 全部 9 个页面（登录、仪表板、终端管理、白名单、黑名单、审计日志、数据源管理、用户管理、个人资料）
- 品牌自定义配置系统
- i18n 三语言支持（中文/英文/日语），自动检测浏览器语言，手动切换，语言持久化 localStorage
- 深浅色主题切换（Light/Dark/System）+ HeaderControls 统一控件
- 审计日志分类体系（8 类分类过滤 + 彩色 badge + JSON details 解析）
- MAC 地址格式无关搜索 + keepPreviousData 防闪烁
- 前端请求可靠性增强（refresh token Body 传递、_retry 防循环、401 不重试）
- 统一日志工具（lib/logger.ts，四级日志、内存缓冲 + localStorage 持久化、全局错误监听）
- 页面闪烁修复（Suspense 位置调整、staleTime 30s、hover 预加载）
- 前端测试基础设施（Vitest + 58 个测试用例）
- ESLint 代码质量检查
- 所有后端 API 已连接
- 响应式设计
- 开发者友好的设置

代码库已可用于生产，可以根据需要扩展额外功能（如图表分析、用户资料、设置页面等）。
