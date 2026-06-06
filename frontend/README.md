# MAC Security Platform - Frontend

基于 React + TypeScript 的 MAC Security Platform 现代化前端。

---

## 技术栈

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 框架 | React | 18 | UI 库 |
| 语言 | TypeScript | 5.3 | 类型安全 |
| 构建工具 | Vite | 5 | 快速开发服务器和打包器 |
| 路由 | React Router | 6 | 客户端路由 |
| 样式 | TailwindCSS | 3 | 实用优先 CSS |
| 状态管理 | Zustand | 4 | 轻量级状态管理 |
| 数据获取 | TanStack Query | 5 | 服务端状态和缓存 |
| 表单 | React Hook Form | 7 | 表单验证 |
| HTTP | Axios | 1.6 | API 客户端 |
| 图标 | Lucide React | 0.294 | 图标库 |
| 图表 | Recharts | 2.10 | 数据可视化 |
| 通知 | Sonner | 1.2 | Toast 消息 |

---

## 安装与设置

### 前提条件

- Node.js 18+
- npm 或 yarn

### 安装

```bash
cd frontend
npm install
```

### 配置环境

在 `frontend/` 目录下创建 `.env` 文件：

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

> 在 Docker 部署中，API 请求通过 Nginx 代理，无需配置此变量。

### 启动后端

确保后端正在运行：

```bash
# 使用 Docker
./manage.sh start

# 或本地开发
cd ../backend
uvicorn app.main:app --reload
```

后端应在 `http://localhost:8000` 可访问（Docker 部署时通过 Nginx 代理为 `https://localhost:8443`）。

### 启动前端开发服务器

```bash
cd frontend
npm run dev
```

前端将在 `http://localhost:3000` 可用（开发模式）。生产环境通过 Nginx 代理访问 `https://localhost:8443`。

### 登录

使用默认管理员凭据：
- **用户名**: admin
- **密码**: admin123

（或后端初始化时设置的密码）

---

## 项目结构

```
frontend/
├── public/                    # 静态资源
│   └── favicon.svg                 # 浏览器标签图标
├── src/
│   ├── components/            # 可复用 UI 组件
│   │   ├── Layout.tsx              # 主布局（侧边栏 + 内容区 + 页脚）
│   │   ├── Sidebar.tsx             # 可折叠侧边栏导航
│   │   ├── Pagination.tsx          # 高级分页组件
│   │   ├── DateRangeFilter.tsx     # 日期范围过滤器
│   │   ├── Button.tsx              # 通用按钮组件
│   │   ├── ErrorBoundary.tsx       # 错误边界组件
│   │   ├── ProtectedRoute.tsx      # 路由保护包装器
│   │   ├── Skeleton.tsx            # 骨架屏加载组件
│   │   └── StateDisplay.tsx        # 空状态/加载/错误状态组件
│   ├── config/                # 配置文件
│   │   └── branding.ts             # 品牌自定义配置
│   ├── lib/                   # 工具和 API 客户端
│   │   ├── api.ts                  # 带拦截器的 Axios 客户端
│   │   ├── constants.ts            # 常量定义
│   │   └── utils.ts                # 工具函数
│   ├── pages/                 # 页面组件
│   │   ├── Login.tsx               # 认证页面
│   │   ├── Dashboard.tsx           # 主仪表板
│   │   ├── MacAddresses.tsx        # MAC 地址管理
│   │   ├── Whitelist.tsx           # 白名单管理
│   │   ├── Blacklist.tsx           # 黑名单管理
│   │   └── AuditLogs.tsx           # 审计日志查看器
│   ├── store/                 # 状态管理
│   │   └── auth.ts                 # 认证状态管理
│   ├── App.tsx                # 带路由的主应用
│   ├── main.tsx               # 入口点
│   └── index.css              # TailwindCSS 全局样式
├── package.json               # 依赖和脚本
├── tsconfig.json              # TypeScript 配置
├── tsconfig.node.json         # Node 特定 TS 配置
├── vite.config.ts             # Vite 构建配置（含代理）
├── tailwind.config.js         # TailwindCSS 自定义
├── postcss.config.js          # PostCSS 插件
├── index.html                 # HTML 入口点
├── Dockerfile                 # Docker 构建
└── .gitignore                 # Git 忽略规则
```

---

## 功能

### 已实现

- 用户认证（登录/登出，验证码，账户锁定）
- JWT 令牌管理与自动刷新
- 受保护路由
- 响应式仪表板布局
- MAC 地址管理（搜索、过滤、分页、状态管理）
- 白名单管理（增删查、搜索、过滤、分页）
- 黑名单管理（增删查、搜索、过滤、分页）
- 审计日志查看器（搜索、日期过滤、分页）
- 可折叠侧边栏导航
- 高级分页组件（顶部/底部双展示、每页条数选择、页码跳转）
- 日期范围过滤器（快捷选项 + 自定义范围）
- 可折叠搜索面板
- 品牌自定义配置（logo、favicon、标题、页脚、ICP备案）
- 统一卡片风格（rounded-2xl、渐变色条、section header）
- 登录安全（3次失败显示验证码，5次失败锁定15分钟）
- 状态提示（侧边栏折叠时悬停显示导航文字）
- 骨架屏加载状态
- 空状态/加载/错误状态组件
- Toast 通知
- 表单验证
- 路径别名（@/* 导入）
- 热模块替换（Vite）
- CSV 导出
- MAC/IP 地址验证

---

## 品牌自定义配置

所有品牌相关配置集中在 `src/config/branding.ts` 文件中，修改此文件即可自定义：

| 配置项 | 字段 | 说明 |
|--------|------|------|
| 应用名称 | `appName` / `appShortName` / `appSubtitle` | 侧边栏、登录页标题 |
| 版本号 | `version` | 页脚显示 |
| 浏览器标题 | `title` | 标签页标题 |
| Favicon | `favicon` | 浏览器标签图标 |
| Logo | `logo.type` / `logo.path` / `logo.name` | 支持 Lucide 图标或自定义图片 |
| 登录背景 | `login.background.type` / `gradientClass` / `imagePath` | 支持渐变色或背景图片 |
| 登录按钮/头部 | `login.buttonGradient` / `headerGradient` | 渐变色 Tailwind 类名 |
| 页脚版权 | `footer.copyright` | `{year}` 自动替换为当前年份 |
| ICP 备案 | `footer.icpNumber` / `footer.icpUrl` | 留空则隐藏 |
| 额外链接 | `footer.links` | 页脚附加链接数组 |

详细操作说明参见项目根目录 `docs/branding.md`。

---

## API 集成

前端通过 Axios 拦截器与 FastAPI 后端通信：

- **请求拦截器**：自动在请求头中附加 JWT 令牌
- **响应拦截器**：处理 401 错误，自动刷新令牌
- **错误处理**：通过 toast 通知显示错误

### 认证流程

```
登录 → 存储令牌 → 重定向到仪表板
  ↓
onSuccess: (data) => {
  login(data.user, data.access_token, data.refresh_token)
  navigate('/dashboard')
}
  ↓
令牌存储在 sessionStorage
认证状态在 Zustand store 中更新
```

### 令牌刷新机制

```
Axios 响应拦截器
if (error.response?.status === 401 && !originalRequest._retry) {
  // 使用刷新令牌获取新令牌
  const response = await axios.post('/auth/refresh', ...)

  // 更新 sessionStorage
  sessionStorage.setItem('access_token', newAccessToken)

  // 重试原始请求
  return apiClient(originalRequest)
}
```

---

## 安全特性

- HTTPS 就绪（Vite 支持 SSL）
- XSS 保护（React 默认转义）
- CSRF 保护（JWT 在 Authorization 头中）
- 安全令牌存储（sessionStorage 带刷新）
- 输入验证（React Hook Form）
- 受保护路由（需要认证）
- 登录安全：3次失败后显示验证码，5次失败后锁定账户15分钟
- 品牌自定义：集中配置，无需修改组件代码

### 生产建议

- 启用 CSP 头
- 使用 HttpOnly cookies 替代 sessionStorage
- 启用 HSTS
- 定期更新依赖

---

## 浏览器支持

- Chrome（最新）
- Firefox（最新）
- Safari（最新）
- Edge（最新）
- 移动浏览器（iOS Safari, Chrome Mobile）

---

## 资源

- [React 文档](https://react.dev/)
- [TypeScript 手册](https://www.typescriptlang.org/docs/)
- [TailwindCSS 文档](https://tailwindcss.com/docs)
- [TanStack Query](https://tanstack.com/query/latest)
- [Zustand](https://github.com/pmndrs/zustand)
- [React Hook Form](https://react-hook-form.com/)
- [Lucide 图标](https://lucide.dev/)
