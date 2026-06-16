# 品牌自定义指南

> 文档版本：v3.2.0-r8 | 更新日期：2026-06-16

## 概述

TerminalAccessManager 支持全面的品牌自定义，无需修改任何组件代码。品牌配置支持两种方式：

1. **后端动态配置（推荐）**：通过 `manage.sh config branding` 命令或后端 `/settings/` API 修改品牌配置，前端通过 useBrandingStore 动态加载，修改后刷新页面即可生效，无需重新构建
2. **静态配置文件**：修改 `frontend/src/config/branding.ts` 中的默认值，需要重新构建前端

运行时，前端会先使用 branding.ts 中的静态默认值，登录后从后端 `/settings/` API 加载动态配置并覆盖默认值。

## 配置方式

### 方式一：后端动态配置（推荐）

通过 `manage.sh` 命令管理品牌配置，修改后刷新页面即可生效：

```bash
# 查看所有品牌配置
./manage.sh config branding

# 修改应用名称
./manage.sh config branding app_name "我的安全平台"

# 修改页脚内容
./manage.sh config branding footer_copyright "© 2026 我的公司"

# 上传自定义登录页背景
./manage.sh config upload login_bg /path/to/background.jpg

# 上传自定义 Favicon
./manage.sh config upload favicon /path/to/favicon.ico
```

**优势**：
- 无需重新构建前端
- 修改后刷新页面即可生效
- 支持上传资源文件（背景图、Favicon）
- 配置存储在数据库中，Redis 缓存加速读取

**上传安全策略：**
- 文件扩展名白名单：仅支持 `.jpg` / `.jpeg` / `.png` / `.gif` / `.ico`（SVG 不再支持，可嵌入 JavaScript，存在 XSS 风险）
- 文件名使用 UUID 重命名（不可猜测，增强安全性）
- 双重校验：`content_type` + 扩展名都必须在白名单中
- 文件大小限制：5MB

### 方式二：静态配置文件

修改 `frontend/src/config/branding.ts` 中的默认值，适用于：
- 初始默认值定制
- 后端不可用时的回退值
- 开发环境快速迭代

修改后需重新构建前端：

```bash
# Docker 部署
./manage.sh update

# 开发环境
cd frontend && npm run build
```

## 配置文件位置

```
frontend/src/config/branding.ts
```

静态资源文件目录：

```
frontend/public/
```

## 配置项详解

### 完整接口定义

```typescript
interface BrandingConfig {
  appName: string;        // 应用全名，显示在侧边栏、登录页、浏览器标题
  appShortName: string;   // 应用短名，侧边栏展开时显示
  appSubtitle: string;    // 副标题，显示在侧边栏应用名下方
  version: string;        // 版本号，显示在页脚
  title: string;          // 浏览器标签页标题
  favicon: string;        // Favicon 路径
  logo: {                 // Logo 配置
    type: 'icon' | 'image';   // 'icon' 使用 Lucide 图标，'image' 使用图片文件
    name: string;             // Lucide 图标名称（type 为 'icon' 时生效）
    path: string;             // 图片路径（type 为 'image' 时生效）
    className: string;        // Tailwind CSS 类名（用于图标颜色等）
  };
  login: {                // 登录页配置
    heading: string;          // 登录页标题
    subheading: string;       // 登录页副标题
    footerText: string;       // 登录卡片底部文字
    background: {             // 登录页背景
      type: 'gradient' | 'image';    // 'gradient' 使用渐变色，'image' 使用背景图片
      gradientClass: string;         // Tailwind 渐变色类名（type 为 'gradient' 时生效）
      imagePath: string;             // 图片路径（type 为 'image' 时生效）
    };
    buttonGradient: string;   // 登录按钮渐变色类名
    headerGradient: string;   // 登录页头部渐变色类名
  };
  footer: {               // 页脚配置
    copyright: string;        // 版权信息，{year} 会被替换为当前年份
    icpNumber: string;        // ICP 备案号，留空则隐藏
    icpUrl: string;           // ICP 备案链接
    links: { label: string; url: string }[];  // 额外页脚链接
  };
}
```

### 配置项说明表

| 配置项 | 字段路径 | 类型 | 默认值 | 说明 |
|--------|----------|------|--------|------|
| 应用全名 | `appName` | string | `Terminal Access Manager` | 侧边栏、登录页标题 |
| 应用短名 | `appShortName` | string | `Terminal Access` | 侧边栏展开时显示 |
| 副标题 | `appSubtitle` | string | `Manager` | 侧边栏应用名下方 |
| 版本号 | `version` | string | `v2.0.0` | 页脚显示 |
| 浏览器标题 | `title` | string | `Terminal Access Manager` | 标签页标题 |
| Favicon | `favicon` | string | `/favicon.svg` | 浏览器标签图标路径 |
| Logo 类型 | `logo.type` | `'icon'` \| `'image'` | `'icon'` | 图标或图片模式 |
| Logo 图标名 | `logo.name` | string | `Shield` | Lucide 图标名称 |
| Logo 图片路径 | `logo.path` | string | `/logo.svg` | 图片文件路径 |
| Logo 样式 | `logo.className` | string | `text-blue-500` | Tailwind CSS 类名 |
| 登录标题 | `login.heading` | string | `Terminal Access Manager` | 登录页大标题 |
| 登录副标题 | `login.subheading` | string | `Sign in to your account` | 登录页副标题（优先使用 i18n 翻译键 `auth.signInToAccount`，branding 配置作为回退值） |
| 登录页脚文字 | `login.footerText` | string | `Secure authentication · Session-based access control` | 登录卡片底部（优先使用 i18n 翻译键 `auth.secureAuthFooter`，branding 配置作为回退值） |
| 背景类型 | `login.background.type` | `'gradient'` \| `'image'` | `'gradient'` | 渐变色或背景图片 |
| 渐变色类名 | `login.background.gradientClass` | string | `bg-gradient-to-br from-gray-50 via-blue-50 to-indigo-100` | Tailwind 渐变类 |
| 背景图片路径 | `login.background.imagePath` | string | `/login-bg.jpg` | 背景图片路径 |
| 按钮渐变色 | `login.buttonGradient` | string | `from-blue-600 to-indigo-600` | 登录按钮渐变 |
| 头部渐变色 | `login.headerGradient` | string | `from-blue-600 to-indigo-600` | 登录头部渐变 |
| 版权信息 | `footer.copyright` | string | `© {year} TerminalAccessManager (TAM)` | `{year}` 自动替换 |
| ICP 备案号 | `footer.icpNumber` | string | `""` | 留空隐藏 |
| ICP 链接 | `footer.icpUrl` | string | `https://beian.miit.gov.cn/` | 备案链接 |
| 额外链接 | `footer.links` | array | `[]` | 页脚附加链接 |

## 自定义操作指南

### 1. 修改应用名称

修改 `branding.ts` 中的以下字段：

```typescript
const branding: BrandingConfig = {
  appName: '我的安全平台',        // 全名 - 登录页标题、浏览器标题
  appShortName: '安全平台',       // 短名 - 侧边栏展开时
  appSubtitle: '管理系统',        // 副标题 - 侧边栏应用名下方
  title: '我的安全平台',          // 浏览器标签页标题
  // ...
};
```

**影响范围**：
- `appName` → 登录页标题、浏览器标题
- `appShortName` → 侧边栏展开时的名称
- `appSubtitle` → 侧边栏名称下方的副标题
- `title` → 浏览器标签页标题（通过 `document.title` 设置）

### 2. 修改 Logo

#### 方式一：使用 Lucide 图标（默认）

```typescript
logo: {
  type: 'icon',
  name: 'Shield',           // Lucide 图标组件名称
  path: '/logo.svg',        // 此项在 icon 模式下不生效，但需保留
  className: 'text-blue-500', // Tailwind 颜色类名
},
```

修改 `name` 为其他 Lucide 图标名称，修改 `className` 调整颜色。常用图标参见 [Lucide 图标参考](#lucide-图标参考)。

#### 方式二：使用自定义图片

1. 将 Logo 图片文件放入 `frontend/public/` 目录，例如 `frontend/public/company-logo.svg`
2. 修改配置：

```typescript
logo: {
  type: 'image',
  name: 'Shield',              // icon 模式备用，image 模式下不生效
  path: '/company-logo.svg',   // 指向 public/ 目录下的图片
  className: 'text-blue-500',  // image 模式下不生效
},
```

**支持的图片格式**：SVG（推荐）、PNG、JPG、WebP

**推荐尺寸**：64×64px 或更大（侧边栏显示为 32×32px，登录页显示为 40×40px）

### 3. 修改 Favicon

1. 将 Favicon 文件放入 `frontend/public/` 目录，例如 `frontend/public/favicon.ico`
2. 修改 `branding.ts` 配置：

```typescript
favicon: '/favicon.ico',
```

3. 同时修改 `frontend/index.html` 中的 `<link>` 标签：

```html
<link rel="icon" type="image/x-icon" href="/favicon.ico" />
```

**支持的格式**：SVG（推荐）、ICO、PNG

**推荐尺寸**：32×32px 或 64×64px

### 4. 修改登录页背景

> **深色主题说明**：登录页背景现在使用 `bg-background` 语义化颜色（支持深色主题自动适配），`gradientClass` 配置仍存在但在深色模式下被语义化颜色覆盖。如需自定义深色模式背景，请修改 Tailwind 的 `dark:bg-background` 变量。

#### 方式一：使用渐变色（默认）

```typescript
login: {
  // ...
  background: {
    type: 'gradient',
    gradientClass: 'bg-gradient-to-br from-gray-50 via-blue-50 to-indigo-100',
    imagePath: '/login-bg.jpg',   // gradient 模式下不生效，但需保留
  },
  // ...
},
```

修改 `gradientClass` 为其他 Tailwind 渐变色类名。常用渐变色参见 [Tailwind 渐变色参考](#tailwind-渐变色参考)。

#### 方式二：使用背景图片

1. 将背景图片放入 `frontend/public/` 目录，例如 `frontend/public/login-bg.jpg`
2. 修改配置：

```typescript
login: {
  // ...
  background: {
    type: 'image',
    gradientClass: 'bg-gradient-to-br from-gray-50 via-blue-50 to-indigo-100', // image 模式下不生效，但需保留
    imagePath: '/login-bg.jpg',
  },
  // ...
},
```

**推荐图片**：
- 格式：JPG 或 WebP（压缩率高）
- 尺寸：1920×1080px 或更大
- 文件大小：建议不超过 500KB

### 5. 修改登录页配色

登录页有两处渐变色可自定义：

```typescript
login: {
  // ...
  buttonGradient: 'from-blue-600 to-indigo-600',   // 登录按钮渐变色
  headerGradient: 'from-blue-600 to-indigo-600',   // 登录页头部色带渐变色
  // ...
},
```

**配色示例**：

| 风格 | buttonGradient | headerGradient |
|------|----------------|----------------|
| 蓝色（默认） | `from-blue-600 to-indigo-600` | `from-blue-600 to-indigo-600` |
| 绿色 | `from-emerald-600 to-teal-600` | `from-emerald-600 to-teal-600` |
| 紫色 | `from-purple-600 to-pink-600` | `from-purple-600 to-pink-600` |
| 橙色 | `from-orange-600 to-red-600` | `from-orange-600 to-red-600` |
| 深色 | `from-gray-800 to-gray-900` | `from-gray-800 to-gray-900` |

> 注意：`buttonGradient` 和 `headerGradient` 的值不需要加 `bg-gradient-to-r` 前缀，组件内部已自动添加。

### 6. 修改页脚信息

```typescript
footer: {
  copyright: '© {year} 我的公司',     // {year} 自动替换为当前年份
  icpNumber: '京ICP备12345678号',      // ICP 备案号，留空字符串 '' 则隐藏
  icpUrl: 'https://beian.miit.gov.cn/', // 备案链接
  links: [                              // 额外页脚链接
    { label: '隐私政策', url: 'https://example.com/privacy' },
    { label: '使用条款', url: 'https://example.com/terms' },
  ],
},
```

**页脚显示位置**：
- 主布局页脚（侧边栏右侧底部）
- 登录页底部

**ICP 备案**：`icpNumber` 为空字符串时，备案信息不会显示。

### 7. 修改版本号

```typescript
version: 'v2.1.0',
```

版本号显示在页脚版权信息旁边。

## 资源文件管理

### 目录结构

```
frontend/public/
├── favicon.svg          # 浏览器标签图标（默认）
├── logo.svg             # Logo 图片（如使用 image 模式）
├── login-bg.jpg         # 登录页背景图片（如使用 image 模式）
└── ...                  # 其他自定义资源
```

### 资源引用规则

- 所有静态资源放置在 `frontend/public/` 目录下
- 在 `branding.ts` 中使用绝对路径引用，以 `/` 开头
- 例如：文件 `frontend/public/company-logo.svg` → 配置路径 `/company-logo.svg`
- Vite 构建时会自动将 `public/` 目录内容复制到输出目录

### 上传资源访问控制（/uploads/ 路径）

通过 `config upload` 上传的品牌资源文件存储在 `/uploads/` 路径下，Nginx 对该路径实施了以下访问控制：

- **Referer 检查**：Nginx 添加 Referer 校验，恶意来源（非本站 Referer）返回 403
- **无 Referer 允许**：浏览器直接访问（无 Referer）和同站 Referer 允许访问
- **UUID 文件名**：上传文件使用 UUID 重命名，使 URL 不可枚举，防止暴力遍历

### 文件格式建议

| 资源类型 | 推荐格式 | 推荐尺寸 | 最大文件大小 |
|----------|----------|----------|-------------|
| Favicon | SVG、ICO | 32×32px | 10KB |
| Logo | SVG | 64×64px+ | 50KB |
| 登录背景 | WebP、JPG | 1920×1080px+ | 500KB |

## Lucide 图标参考

Logo 配置中 `type: 'icon'` 模式使用 [Lucide](https://lucide.dev/) 图标库。以下是适合安全/网络类应用的常用图标：

| 图标名称 | 描述 | 适合场景 |
|----------|------|----------|
| `Shield` | 盾牌 | 安全防护（默认） |
| `ShieldCheck` | 带勾盾牌 | 安全认证 |
| `ShieldAlert` | 警告盾牌 | 安全告警 |
| `Lock` | 锁 | 访问控制 |
| `Key` | 钥匙 | 认证授权 |
| `Network` | 网络 | 网络管理 |
| `Globe` | 地球 | 全球访问 |
| `Server` | 服务器 | 基础设施 |
| `Monitor` | 显示器 | 终端管理 |
| `Wifi` | 无线 | 无线网络 |
| `Fingerprint` | 指纹 | 身份认证 |
| `Eye` | 眼睛 | 监控审计 |
| `Radar` | 雷达 | 安全扫描 |
| `Scan` | 扫描 | 安全检测 |
| `CheckCircle` | 勾选圆圈 | 合规管理 |

> 完整图标列表请访问 [Lucide 官网](https://lucide.dev/icons/)。

### 图标颜色

通过 `logo.className` 设置图标颜色，使用 Tailwind 文字颜色类名：

| 颜色 | className |
|------|-----------|
| 蓝色（默认） | `text-blue-500` |
| 靛蓝色 | `text-indigo-500` |
| 绿色 | `text-emerald-500` |
| 紫色 | `text-purple-500` |
| 红色 | `text-red-500` |
| 橙色 | `text-orange-500` |
| 青色 | `text-cyan-500` |
| 灰色 | `text-gray-500` |

## Tailwind 渐变色参考

登录页背景和按钮/头部使用 Tailwind CSS 渐变色类名。

### 背景渐变色（用于 `login.background.gradientClass`）

背景渐变需要完整的 Tailwind 类名，包含 `bg-gradient-to-` 前缀：

| 风格 | gradientClass |
|------|---------------|
| 蓝白渐变（默认） | `bg-gradient-to-br from-gray-50 via-blue-50 to-indigo-100` |
| 蓝紫渐变 | `bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-100` |
| 绿白渐变 | `bg-gradient-to-br from-gray-50 via-emerald-50 to-teal-100` |
| 紫粉渐变 | `bg-gradient-to-br from-purple-50 via-pink-50 to-rose-100` |
| 暖色渐变 | `bg-gradient-to-br from-orange-50 via-amber-50 to-yellow-100` |
| 深色渐变 | `bg-gradient-to-br from-gray-800 via-gray-900 to-black` |
| 冷色渐变 | `bg-gradient-to-br from-slate-50 via-cyan-50 to-blue-100` |

### 方向关键字

渐变方向由 `bg-gradient-to-{direction}` 控制：

| 方向 | 类名 | 效果 |
|------|------|------|
| 右下 | `bg-gradient-to-br` | 左上 → 右下（推荐） |
| 右 | `bg-gradient-to-r` | 左 → 右 |
| 下 | `bg-gradient-to-b` | 上 → 下 |
| 右上 | `bg-gradient-to-tr` | 左下 → 右上 |

### 按钮/头部渐变色（用于 `login.buttonGradient` 和 `login.headerGradient`）

按钮和头部渐变**不需要** `bg-gradient-to-r` 前缀，组件内部已自动添加：

| 风格 | 渐变色值 |
|------|----------|
| 蓝色（默认） | `from-blue-600 to-indigo-600` |
| 绿色 | `from-emerald-600 to-teal-600` |
| 紫色 | `from-purple-600 to-pink-600` |
| 橙色 | `from-orange-600 to-red-600` |
| 青色 | `from-cyan-600 to-blue-600` |
| 深色 | `from-gray-700 to-gray-900` |

## 完整配置示例

### 示例一：企业安全平台

```typescript
const branding: BrandingConfig = {
  appName: 'Enterprise Security Center',
  appShortName: 'Security',
  appSubtitle: 'Center',
  version: 'v2.0.0',
  title: 'Enterprise Security Center',
  favicon: '/favicon.svg',

  logo: {
    type: 'icon',
    name: 'ShieldCheck',
    path: '/logo.svg',
    className: 'text-emerald-500',
  },

  login: {
    heading: 'Enterprise Security Center',
    subheading: 'Sign in to your account',
    footerText: 'Enterprise-grade security · Multi-factor authentication',
    background: {
      type: 'gradient',
      gradientClass: 'bg-gradient-to-br from-gray-50 via-emerald-50 to-teal-100',
      imagePath: '/login-bg.jpg',
    },
    buttonGradient: 'from-emerald-600 to-teal-600',
    headerGradient: 'from-emerald-600 to-teal-600',
  },

  footer: {
    copyright: '© {year} Enterprise Inc.',
    icpNumber: '',
    icpUrl: '',
    links: [
      { label: 'Privacy Policy', url: 'https://example.com/privacy' },
      { label: 'Terms of Service', url: 'https://example.com/terms' },
    ],
  },
};
```

### 示例二：使用自定义 Logo 和背景图片

```typescript
const branding: BrandingConfig = {
  appName: '网络准入管理平台',
  appShortName: '准入管理',
  appSubtitle: '平台',
  version: 'v2.0.0',
  title: '网络准入管理平台',
  favicon: '/favicon.ico',

  logo: {
    type: 'image',
    name: 'Shield',
    path: '/company-logo.svg',
    className: 'text-blue-500',
  },

  login: {
    heading: '网络准入管理平台',
    subheading: '请登录您的账户',
    footerText: '安全认证 · 会话访问控制',
    background: {
      type: 'image',
      gradientClass: 'bg-gradient-to-br from-gray-50 via-blue-50 to-indigo-100',
      imagePath: '/login-bg.jpg',
    },
    buttonGradient: 'from-blue-600 to-indigo-600',
    headerGradient: 'from-blue-600 to-indigo-600',
  },

  footer: {
    copyright: '© {year} 某某科技有限公司',
    icpNumber: '京ICP备12345678号-1',
    icpUrl: 'https://beian.miit.gov.cn/',
    links: [
      { label: '隐私政策', url: 'https://example.com/privacy' },
      { label: '服务条款', url: 'https://example.com/terms' },
    ],
  },
};
```

## 构建与生效

### 开发环境

修改 `branding.ts` 后，Vite 热模块替换（HMR）会自动刷新页面，无需手动重启。

```bash
cd frontend
npm run dev
```

### 生产构建

修改配置后需重新构建前端：

```bash
cd frontend
npm run build
```

### Docker 部署

使用 Docker 部署时，通过管理脚本重新构建：

```bash
./manage.sh update
```

或仅重建前端并重启：

```bash
docker compose up -d --build frontend
./manage.sh restart nginx
```

### 静态资源更新

如果替换了 `frontend/public/` 目录下的资源文件（如 Logo、Favicon、背景图片）：

1. **开发环境**：刷新浏览器即可（Vite 直接服务 `public/` 目录）
2. **生产环境**：需重新构建前端，因为资源会在构建时被复制到 `dist/` 目录
3. **Docker 环境**：需重新构建 frontend 容器

### 配置变更生效方式（v3.2.0-r2）

通过 `manage.sh config set` 修改配置时，系统会提示该配置变更的生效方式：

| 生效方式 | 配置项 | 说明 |
|---------|--------|------|
| **热重载**（无需重启） | 限流阈值、登录安全、调度间隔、JWT 有效期、品牌配置 | 修改后即时生效，ConfigService 写穿透 + Redis 缓存失效 |
| **需重启服务** | LOG_LEVEL、TZ、DEBUG、ENCRYPTION_KEY、数据库连接、Redis 连接 | 修改 .env 后需执行 `./manage.sh restart backend` |

`manage.sh config set` 执行时会自动判断并提示：
- 热重载配置：显示 "✓ 配置已热重载生效"
- 需重启配置：显示 "⚠ 此配置需要重启 backend 服务才能生效: ./manage.sh restart backend"

## 主题切换

主题切换功能已从 Sidebar 移至 **HeaderControls** 组件（页面顶部右上角），登录页和登录后均可见。

### 切换选项

| 选项 | 说明 |
|------|------|
| 浅色 | 固定使用浅色主题 |
| 深色 | 固定使用深色主题 |
| 跟随系统 | 自动匹配操作系统主题设置（默认） |

主题偏好持久化到 `localStorage`，刷新页面后保持不变。

### 深色主题兼容

登录页各区域已添加 `dark:` 变体适配深色主题：

- 背景使用 `bg-background` 语义化颜色，深色模式自动适配
- 锁定警告区、错误提示区、验证码区、输入框均已添加深色变体
- 自定义样式需注意深色模式兼容性，建议同时提供 `dark:` 变体

## 语言切换

语言切换功能位于 **HeaderControls** 组件中，通过 Globe 图标下拉菜单选择。

### 支持语言

| 语言 | 代码 | 说明 |
|------|------|------|
| 中文 | `zh` | 简体中文 |
| 英文 | `en` | 英语 |
| 日语 | `ja` | 日本語 |

### 语言检测与持久化

1. **自动检测**：首次访问时通过 `i18next-browser-languagedetector` 自动检测浏览器语言
2. **手动切换**：点击 Globe 图标下拉菜单选择语言
3. **持久化**：语言偏好保存到 `localStorage`，刷新页面后保持不变

### i18n 翻译优先级

登录页副标题和页脚文字优先使用 i18n 翻译键：

- 副标题：i18n 键 `auth.signInToAccount` → branding 配置 `login.subheading` 作为回退值
- 页脚文字：i18n 键 `auth.secureAuthFooter` → branding 配置 `login.footerText` 作为回退值

## Terminal 状态标签

终端状态在界面中以标签（Badge）形式展示，当前支持以下两种状态：

| 状态值 | 中文标签 | 英文标签 | 说明 |
|--------|---------|---------|------|
| `blocked` | 已封堵 | Blocked | 终端已被防火墙阻断 |
| `unblocked` | 未封堵 | Unblocked | 终端未被封堵（默认状态） |

> **v3.2.0-r4 变更说明：** 终端状态从 6 值（active/inactive/frozen/pending/unfrozen）精简为 2 值（blocked/unblocked），标签文案同步更新。合规状态由 `compliance_status` 字段独立追踪，不再混入终端状态。

## 数据源配置表单

数据源配置表单中，`arp_api` 类型支持以下认证方式：

| 认证方式 | auth_type 值 | 表单字段 | 说明 |
|---------|-------------|---------|------|
| Basic Auth | `basic`（默认） | 用户名 + 密码 | HTTP 基本认证 |
| Custom Header | `header` | Header 名称 + Header 值 | 自定义请求头认证（如 `X-API-Key`），选择此项后需填写 `header_name` 字段指定 Header 名称 |

> **Custom Header 认证说明：** 当 `auth_type=header` 时，系统在请求 API 时会将 `header_name` 指定的 Header 名称和密码字段中的值作为请求头发送，适用于基于 API Key 等非标准认证方式的数据源。

## 常见问题

### Q: 修改了 branding.ts 但页面没有变化？

**A:** 检查以下几点：
1. 确认修改的是 `frontend/src/config/branding.ts` 文件
2. 开发环境下检查浏览器控制台是否有编译错误
3. 生产环境下确认已重新构建（`npm run build`）
4. Docker 环境下确认已重新构建容器（`./manage.sh update`）
5. 清除浏览器缓存后重试

### Q: 使用自定义图片 Logo 但不显示？

**A:** 检查以下几点：
1. 确认图片文件已放入 `frontend/public/` 目录
2. 确认 `logo.type` 设置为 `'image'`
3. 确认 `logo.path` 以 `/` 开头，且文件名与实际文件一致
4. 确认图片文件名大小写与配置一致（Linux 区分大小写）
5. 检查浏览器控制台 Network 面板，确认图片请求返回 200

### Q: Favicon 没有更新？

**A:** Favicon 缓存较为顽固，需要：
1. 同时修改 `branding.ts` 中的 `favicon` 字段和 `frontend/index.html` 中的 `<link>` 标签
2. 强制刷新浏览器（Ctrl+Shift+R 或 Cmd+Shift+R）
3. 清除浏览器缓存
4. 如果仍不生效，尝试在路径后添加版本参数：`/favicon.svg?v=2`

### Q: 登录背景图片不显示？

**A:** 检查以下几点：
1. 确认 `login.background.type` 设置为 `'image'`
2. 确认图片文件已放入 `frontend/public/` 目录
3. 确认 `login.background.imagePath` 路径正确
4. 确认图片文件大小合理（建议不超过 500KB）
5. 检查浏览器控制台是否有图片加载错误

### Q: 渐变色类名不生效？

**A:** 检查以下几点：
1. 确认使用的是 Tailwind CSS 支持的类名
2. 背景渐变需要完整的类名（包含 `bg-gradient-to-` 前缀）
3. 按钮和头部渐变**不需要** `bg-gradient-to-r` 前缀
4. 如果使用自定义颜色，需在 `tailwind.config.js` 中配置
5. 确认类名拼写正确，Tailwind 类名不支持动态拼接

### Q: ICP 备案号如何隐藏？

**A:** 将 `footer.icpNumber` 设置为空字符串即可：

```typescript
footer: {
  icpNumber: '',  // 留空即可隐藏
  // ...
},
```

### Q: 如何添加多个页脚链接？

**A:** 在 `footer.links` 数组中添加：

```typescript
footer: {
  links: [
    { label: '隐私政策', url: 'https://example.com/privacy' },
    { label: '服务条款', url: 'https://example.com/terms' },
    { label: '帮助中心', url: 'https://example.com/help' },
  ],
},
```

### Q: 修改品牌配置是否需要修改组件代码？

**A:** 不需要。所有品牌配置通过 `branding.ts` 集中管理，组件通过 `import branding from '@/config/branding'` 读取配置。只需修改配置文件即可，无需修改任何组件代码。
