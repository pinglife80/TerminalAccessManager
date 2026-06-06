# 前端实现总结

## 概述

MAC Security Platform 的前端已使用现代 React + TypeScript 技术栈完整实现，包含认证系统、终端管理、白名单/黑名单管理、审计日志等全部核心功能，以及品牌自定义配置系统。

---

## 已构建内容

### 1. 项目结构
```
frontend/
├── src/
│   ├── components/       # 可复用 UI 组件
│   │   ├── Layout.tsx           # 主布局（侧边栏 + 内容 + 页脚）
│   │   ├── Sidebar.tsx          # 可折叠侧边栏导航
│   │   ├── Pagination.tsx       # 高级分页组件（top/bottom 变体）
│   │   ├── DateRangeFilter.tsx  # 日期范围过滤器
│   │   ├── Button.tsx           # 按钮组件（PrimaryButton/IconButton/ButtonGroup）
│   │   ├── StateDisplay.tsx     # 状态显示组件（EmptyState/LoadingState）
│   │   ├── Skeleton.tsx         # 骨架屏组件
│   │   ├── ProtectedRoute.tsx   # 路由保护包装器
│   │   └── ErrorBoundary.tsx    # 错误边界组件
│   ├── config/           # 配置
│   │   └── branding.ts          # 品牌自定义配置
│   ├── hooks/            # 自定义 Hooks
│   │   └── useMacData.ts        # 数据查询 Hooks（MAC 地址、白名单、统计）
│   ├── lib/              # 工具和 API 客户端
│   │   ├── api.ts               # 带拦截器的 Axios 客户端
│   │   ├── constants.ts         # 常量定义（状态、导航、API 端点等）
│   │   └── utils.ts             # 工具函数（日期格式化、CSV 导出、MAC/IP 验证等）
│   ├── pages/            # 页面组件
│   │   ├── Login.tsx            # 登录页（验证码、账户锁定）
│   │   ├── Dashboard.tsx        # 主仪表板
│   │   ├── MacAddresses.tsx     # 终端管理
│   │   ├── Whitelist.tsx        # 白名单管理
│   │   ├── Blacklist.tsx        # 黑名单管理
│   │   └── AuditLogs.tsx        # 审计日志
│   ├── store/            # 状态管理
│   │   └── auth.ts              # 认证状态管理
│   ├── App.tsx           # 带路由的主应用
│   ├── main.tsx          # 入口点
│   ├── index.css         # TailwindCSS 全局样式
│   └── vite-env.d.ts     # Vite 类型声明
├── public/               # 静态资源
│   └── favicon.svg              # 网站图标
├── package.json          # 依赖和脚本
├── tsconfig.json         # TypeScript 配置
├── tsconfig.node.json    # Node 特定 TS 配置
├── vite.config.ts        # Vite 构建配置
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
- 验证码机制（连续失败 3 次后显示验证码）
- 账户锁定机制（连续失败 5 次后锁定 15 分钟）
- JWT 令牌存储在 sessionStorage
- 令牌过期时自动刷新
- 受保护路由（未认证时重定向到登录页）
- 登出功能
- 用户会话持久化

#### API 集成
- 配置好的 Axios HTTP 客户端
- 请求拦截器（自动附加 JWT 令牌）
- 响应拦截器（处理 401 错误，自动刷新令牌）
- 通过 toast 通知的错误处理
- Vite 开发服务器中配置的后端代理
- 30 秒请求超时

#### 状态管理
- Zustand store 管理认证
- 跨页面重载的持久认证状态
- 类型安全的状态管理
- TanStack Query 管理服务端数据缓存

#### UI 组件
- 可折叠侧边栏导航
- 主布局（侧边栏 + 内容区 + 页脚）
- 高级分页组件（支持 top/bottom 变体、每页条数选择）
- 日期范围过滤器
- 按钮组件（PrimaryButton/IconButton/ButtonGroup）
- 空状态和加载状态组件
- 骨架屏加载占位
- 错误边界组件
- Toast 通知（成功/错误消息）
- 确认对话框

#### 样式
- TailwindCSS 实用优先框架
- 自定义配色方案（主蓝色调色板）
- 深色模式支持（CSS 变量）
- 响应式设计（移动优先）
- 现代图标（Lucide React）

#### 开发者体验
- TypeScript 类型安全
- 路径别名（@/* 导入）
- 热模块替换（Vite）
- ESLint 配置
- 全面的文档

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
// 连续失败 3 次后显示验证码
const CAPTCHA_THRESHOLD = 3;
// 连续失败 5 次后锁定账户 15 分钟
const LOCK_THRESHOLD = 5;
const LOCK_DURATION = 15 * 60 * 1000;
```

### 3. 令牌刷新机制

```typescript
// Axios 响应拦截器
if (error.response?.status === 401 && !originalRequest._retry) {
  // 使用刷新令牌获取新令牌
  const response = await axios.post('/auth/refresh', null, {
    params: { refresh_token: refreshToken },
  })

  // 更新 sessionStorage
  sessionStorage.setItem('access_token', newAccessToken)
  sessionStorage.setItem('refresh_token', newRefreshToken)

  // 重试原始请求
  return apiClient(originalRequest)
}
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

---

## 当前页面

### 1. 登录页面 (`/login`)
**功能：**
- 用户名/密码表单
- 实时验证
- 验证码机制（连续失败 3 次后触发）
- 账户锁定机制（连续失败 5 次后锁定 15 分钟）
- 加载状态
- 通过 toast 显示错误消息
- 品牌自定义（标题、副标题、背景、按钮样式）
- 盾牌图标品牌

### 2. 仪表板 (`/dashboard`)
**功能：**
- 带用户信息的欢迎头部
- 统计卡片（终端总数、白名单数、已封禁数、活跃数）
- 快速操作面板（跳转到终端管理、白名单、黑名单、审计日志）
- 系统状态指示器
- 骨架屏加载状态
- 错误状态处理

### 3. 终端管理 (`/mac-addresses`)
**功能：**
- 终端列表数据表格
- 搜索过滤（按 IP/MAC 地址搜索）
- 状态过滤（active/inactive/frozen/pending/unfrozen/bypass）
- 日期范围过滤
- 高级分页（top/bottom 变体、每页条数选择）
- 封禁/解封操作
- 添加到白名单操作
- 终端详情弹窗
- CSV 导出
- 可折叠过滤器面板
- 空状态和加载状态

### 4. 白名单管理 (`/whitelist`)
**功能：**
- 白名单列表数据表格
- 搜索过滤（按 MAC/IP 地址搜索）
- 日期范围过滤
- 高级分页
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
- 搜索过滤（按 MAC/IP 地址搜索）
- 日期范围过滤
- 高级分页
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
- 搜索过滤（按用户名、操作、详情搜索）
- 操作类型过滤
- 日期范围过滤
- 高级分页
- 日志详情弹窗
- CSV 导出
- 可折叠过滤器面板
- 空状态和加载状态

---

## 创建的文件

### 配置文件（8）
1. `package.json` - 依赖和脚本
2. `tsconfig.json` - TypeScript 配置
3. `tsconfig.node.json` - Node 特定 TS 配置
4. `vite.config.ts` - Vite 构建配置（含代理）
5. `tailwind.config.js` - TailwindCSS 自定义
6. `postcss.config.js` - PostCSS 插件
7. `.env.production` - 生产环境变量
8. `.gitignore` - Git 忽略规则

### 基础设施文件（3）
1. `index.html` - HTML 入口点
2. `Dockerfile` - Docker 构建
3. `nginx.conf` - Nginx 配置

### 源代码文件（19）
1. `src/main.tsx` - React 入口点
2. `src/App.tsx` - 带路由的主应用
3. `src/index.css` - 带 Tailwind 的全局样式
4. `src/vite-env.d.ts` - Vite 类型声明
5. `src/lib/api.ts` - Axios 客户端设置
6. `src/lib/constants.ts` - 常量定义
7. `src/lib/utils.ts` - 工具函数
8. `src/config/branding.ts` - 品牌自定义配置
9. `src/store/auth.ts` - 认证 store
10. `src/hooks/useMacData.ts` - 数据查询 Hooks
11. `src/components/Layout.tsx` - 主布局组件
12. `src/components/Sidebar.tsx` - 侧边栏导航
13. `src/components/Pagination.tsx` - 分页组件
14. `src/components/DateRangeFilter.tsx` - 日期范围过滤器
15. `src/components/Button.tsx` - 按钮组件
16. `src/components/StateDisplay.tsx` - 状态显示组件
17. `src/components/Skeleton.tsx` - 骨架屏组件
18. `src/components/ProtectedRoute.tsx` - 路由守卫
19. `src/components/ErrorBoundary.tsx` - 错误边界

### 页面文件（6）
1. `src/pages/Login.tsx` - 登录页面
2. `src/pages/Dashboard.tsx` - 仪表板页面
3. `src/pages/MacAddresses.tsx` - 终端管理页面
4. `src/pages/Whitelist.tsx` - 白名单管理页面
5. `src/pages/Blacklist.tsx` - 黑名单管理页面
6. `src/pages/AuditLogs.tsx` - 审计日志页面

### 静态资源（1）
1. `public/favicon.svg` - 网站图标

---

## 当前可用功能

- 安装依赖：`npm install`
- 启动开发服务器：`npm run dev`
- 在 `http://localhost:3000` 查看登录页面
- 提交登录表单
- 验证码机制（连续失败后触发）
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
| `login.subheading` | 登录页副标题 |
| `login.footerText` | 登录卡片底部文字 |
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
- `POST /api/v1/auth/refresh` - 令牌刷新
- `GET /api/v1/auth/me` - 获取当前用户信息
- `GET /api/v1/mac/search` - 搜索 MAC 地址
- `GET /api/v1/mac/` - 列出 MAC 地址
- `POST /api/v1/mac/block/{ip}` - 封禁 IP
- `POST /api/v1/mac/unblock/{ip}` - 解封 IP
- `GET /api/v1/whitelist/` - 列出白名单
- `POST /api/v1/whitelist/` - 添加到白名单
- `DELETE /api/v1/whitelist/{mac}` - 从白名单移除
- `GET /api/v1/blacklist/` - 列出黑名单
- `POST /api/v1/blacklist/` - 添加到黑名单
- `DELETE /api/v1/blacklist/{id}` - 从黑名单移除
- `GET /api/v1/logs/` - 列出审计日志

---

## 性能优化

### 已实现
- 通过 Vite 代码分割
- Tree shaking（ES 模块）
- 懒加载就绪（React.lazy）
- 高效重渲染（React.memo 就绪）
- 查询缓存（TanStack Query）
- 登录后数据预取（prefetchQuery）
- 骨架屏加载占位
- 防抖和节流工具函数

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
- 验证码机制（防止暴力破解）
- 账户锁定机制（连续失败后锁定）
- 错误边界（防止 UI 崩溃）

### 生产建议
- 启用 CSP 头
- 使用 HttpOnly cookies 替代 sessionStorage
- 启用 HSTS
- 定期更新依赖

---

## 测试策略（待实现）

### 单元测试
- 组件渲染
- 表单验证
- 状态管理
- 工具函数

### 集成测试
- 登录流程
- API 集成
- 路由导航
- 令牌刷新

### E2E 测试
- 完整用户工作流
- 跨浏览器测试
- 移动响应性

**推荐工具：**
- Vitest（单元测试）
- React Testing Library
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
- 完整的认证系统（含验证码和账户锁定）
- 全部 6 个页面（登录、仪表板、终端管理、白名单、黑名单、审计日志）
- 品牌自定义配置系统
- 所有后端 API 已连接
- 响应式设计
- 开发者友好的设置

代码库已可用于生产，可以根据需要扩展额外功能（如图表分析、用户资料、设置页面等）。
