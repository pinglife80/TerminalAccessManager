# 系统设置/通知管理/合规操作 综合优化实现方案

> 文档版本：v1.0  更新日期：2026-07-02

## Context（背景）

经全面盘点前后端代码发现：后端 v3.5.0 实现 105 个端点功能完整度较高，但前端存在系统性缺口——配置管理类（品牌/系统配置）仅只读消费无管理 UI、可观测性类（通知日志）无入口、运维类（seed/invalidate-cache）缺失；同时存在 1 个后端 Bug（`PROMETHEUS_ENABLED` 字段缺失导致 `/system/config` 500 报错）、11 个 EventType 缺少 metadata、若干 i18n 键缺失、合规操作三件套端点为死代码。

此外，"常规设置 General" 子菜单当前指向 `/system-settings` 自身形成自循环，未承载任何实际配置；通知管理页面 UI/UX 存在事件类型与渠道脱节、缺启用 Toggle、暗色模式不可控、无日志页等问题。

本方案旨在：补齐所有功能缺口、修复 Bug、重构 General 页面承载后端全部系统运行/管理配置、优化通知管理页面 UI/UX 以适配整体设计风格。实现过程严格保证前后端调用一致性、幂等性和鲁棒性。

---

## 项目清单与依赖关系

| ID | 项目 | 类型 | 依赖 |
|----|------|------|------|
| A1 | 修复 PROMETHEUS_ENABLED Bug | 后端 Bug | - |
| B1 | 补全 EVENT_METADATA 11 项 | 后端补全 | - |
| F1 | 修复 i18n 缺失键 | 前端修复 | - |
| G3a | 补充 API_ENDPOINTS 常量 | 前端基础设施 | - |
| C5 | 新增 generalSettings i18n 命名空间 | 前端基础设施 | - |
| D8 | 新增 useNotificationLogs hook | 前端基础设施 | G3a |
| D1 | 消费 channel-types 元数据 + hook | 前端基础设施 | G3a |
| D2 | 创建 notifications/shared.ts 注册表 | 前端共享组件 | - |
| C2 | 创建 GeneralSettings.tsx 页面 | 前端新页面 | A1, C5, G3a |
| C1 | App.tsx 新增路由 + preload | 前端路由 | C2 |
| C4 | NAV_ITEMS + SystemSettings 卡片路径修正 | 前端导航 | C1 |
| D4 | Notifications.tsx Tabs 结构 | 前端改造 | - |
| D5 | 渠道卡片改进（Toggle+chips+暗色） | 前端改造 | D1 |
| D6 | Modal 事件手风琴分组 | 前端改造 | B1, D1 |
| D3 | 顶部统计栏 | 前端改造 | D8 |
| D7 | Send Logs Tab | 前端改造 | D8, D1 |
| E1 | 合规操作 UI 入口 | 前端补全 | G3a, C5 |
| G1/G2 | 幂等性/鲁棒性审查 | 跨切面 | 全部 |

---

## A1. 修复 PROMETHEUS_ENABLED Bug

**文件**：`backend/app/core/config.py`

**变更**：在 Settings 类第 70 行 `TZ` 之后、第 72 行 `# Upload` 之前，新增 Metrics 段：
```python
# Metrics
PROMETHEUS_ENABLED: bool = False
```

**API 影响**：修复后 `GET /api/v1/system/config`（[system.py:66](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/system.py#L66)）不再抛 AttributeError，返回 `{environment, version, debug, log_level, email_enabled, metrics_enabled}`。

**幂等性**：纯字段新增，pydantic-settings 自动从环境变量 `PROMETHEUS_ENABLED` 读取，默认 False。

**影响评估**：无破坏性。当前所有调用 `/system/config` 的请求都 500，修复后恢复正常。

**验证**：`manage.sh rebuild backend && manage.sh restart backend`，调用 `curl -H "Authorization: Bearer <token>" http://localhost:8080/api/v1/system/config`，确认 200 且含 `metrics_enabled: false`。

---

## B1. 补全 EVENT_METADATA 11 项

**文件**：`backend/app/services/notification_channels/event_types.py`

**变更**：在 `EVENT_METADATA` 字典（第 68-201 行）中补充以下 11 个缺失的 EventType 成员：

| EventType 枚举成员 | type 值 | name | description | severity | category |
|---|---|---|---|---|---|
| `TERMINAL_ONLINE` | `terminal.online` | 终端上线 | 终端网络连接已恢复 | info | terminal |
| `TERMINAL_OFFLINE` | `terminal.offline` | 终端离线 | 终端网络连接已断开 | warning | terminal |
| `PASSWORD_RESET` | `security.password_reset` | 密码重置 | 用户密码已被重置 | info | security |
| `EMAIL_VERIFIED` | `security.email_verified` | 邮箱验证 | 用户邮箱已验证 | info | security |
| `USER_UPDATED` | `security.user_updated` | 用户更新 | 用户信息已更新 | info | admin |
| `SYSTEM_ERROR` | `system.error` | 系统错误 | 系统发生错误 | error | system |
| `SYSTEM_WARNING` | `system.warning` | 系统警告 | 系统发出警告 | warning | system |
| `BLOCK_THRESHOLD_EXCEEDED` | `alert.block_threshold` | 封禁阈值超限 | 封禁数量超过预设阈值 | warning | alert |
| `CONFIG_CHANGED` | `admin.config_changed` | 配置变更 | 系统配置已修改 | info | admin |
| `ROLE_CHANGED` | `admin.role_changed` | 角色变更 | 用户角色已更改 | warning | admin |
| `PERMISSION_CHANGED` | `admin.permission_changed` | 权限变更 | 用户权限已变更 | warning | admin |

插入位置：按 category 分组插入到对应区域末尾。

**API 影响**：`GET /notifications/events` 返回事件数从 21 增至 30（覆盖全部 EventType 枚举）。

**幂等性**：字典追加，幂等。

**影响评估**：纯增量。前端 Notifications.tsx 的 `fetchEventTypes` 自动接收全部 30 个事件——与 D6 手风琴分组改造配合（30 个事件平铺不可读，分组后体验提升）。

**验证**：`curl -H "Authorization: Bearer <token>" http://localhost:8080/api/v1/notifications/events | jq '.events | length'`，确认 30。

---

## F1. 修复 i18n 缺失键

**文件**：`frontend/src/i18n/locales/zh.ts`、`en.ts`、`ja.ts`

**已验证的缺失键**（经 grep 确认）：

| 键路径 | 引用位置 | zh | en | ja |
|---|---|---|---|---|
| `common.download` | Backup.tsx:414 | 下载 | Download | ダウンロード |
| `auth.forgotPassword` | Login.tsx:509, PasswordReset.tsx:113 | 忘记密码？ | Forgot Password? | パスワードをお忘れですか？ |
| `auth.authMethod` | Login.tsx:360 | 认证方式 | Authentication Method | 認証方式 |
| `auth.resetPassword` | PasswordReset.tsx:113,298 | 重置密码 | Reset Password | パスワードリセット |

**重要修正**：`common.update` 已存在（zh.ts:45 `update: '更新'`），**不要添加**。

**变更位置**：
- `common.download`：添加到 `common` 命名空间内（zh.ts 第 44 行 `update` 附近）
- `auth.*` 三个键：添加到 `auth` 命名空间内（zh.ts 第 85-118 行，在 `secureAuthFooter` 之后闭合括号前）

**幂等性**：key 添加幂等。

**影响评估**：修复后 Backup 下载按钮、Login 认证方式标签、忘记密码链接、PasswordReset 标题正确显示翻译文本而非 key 字符串。

**验证**：切换三语，访问 Backup 页面确认下载按钮 tooltip、Login 页面确认认证方式标签和忘记密码链接、PasswordReset 页面确认标题。

---

## G3a. 补充 API_ENDPOINTS 常量

**文件**：`frontend/src/lib/constants.ts`

**变更**：在 `API_ENDPOINTS` 对象（第 39-88 行）中新增以下常量：
```typescript
SYSTEM_HEALTH: '/system/health',
SETTINGS_LIST: '/settings/list',
SETTINGS_UPDATE: '/settings/update',
SETTINGS_SEED: '/settings/seed',
SETTINGS_INVALIDATE_CACHE: '/settings/invalidate-cache',
SETTINGS_UPLOAD: '/settings/upload',
NOTIFICATION_CHANNEL_TYPES: '/notifications/channel-types',
```

**说明**：`SETTINGS`（`/settings/`）、`NOTIFICATION_LOGS`、`NOTIFICATION_EVENTS`、`SYSTEM_STATUS`、`SYSTEM_CONFIG` 已存在，复用。单条设置更新复用 `SETTINGS` + key（`${API_ENDPOINTS.SETTINGS}${key}`）。单条渠道操作复用 `NOTIFICATION_CHANNELS` + id。

**幂等性**：常量声明幂等。

**影响评估**：无破坏性，纯增量。

---

## C5. 新增 generalSettings i18n 命名空间

**文件**：`frontend/src/i18n/locales/zh.ts`、`en.ts`、`ja.ts`

**变更**：在 `systemSettings` 命名空间之后新增 `generalSettings` 命名空间。包含键：
```
title, description, systemStatus, healthCheck, uptime, database, redis,
version, environment, platform, pythonVersion, status, healthy, unhealthy,
branding, brandingDesc, security, securityDesc, rateLimit, rateLimitDesc,
network, networkDesc, scheduler, schedulerDesc, general, generalDesc,
operations, operationsDesc, seedDefaults, seedConfirm, seedSuccess,
seedNoChange, invalidateCache, invalidateConfirm, invalidateSuccess,
uploadBg, uploadFavicon, uploadSuccess, uploadFailed, saveSuccess,
saveFailed, partialFail, noChanges, readonly, seconds, loginBgUrl,
faviconUrl, fileTooLarge, invalidFileType
```

**幂等性**：命名空间新增幂等。

**影响评估**：纯增量，GeneralSettings.tsx 所有 `t()` 调用使用 `generalSettings.*` 前缀。

---

## D8. 新增 useNotificationLogs hook

**文件**：`frontend/src/hooks/useTerminalData.ts`

**变更**：在文件末尾新增：
```typescript
export interface NotificationLogItem {
  id: number;
  event_id: string;
  channel_name: string;
  event_type: string;
  status: 'sent' | 'failed' | 'pending';
  recipient: string | null;
  error_message: string | null;
  details: Record<string, unknown> | null;
  sent_at: string;
}

export interface NotificationLogsResponse {
  items: NotificationLogItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface NotificationLogsParams {
  channel_name?: string;
  event_type?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export const useNotificationLogs = (params?: NotificationLogsParams) => {
  return useQuery({
    queryKey: ['notification-logs', params],
    queryFn: async () => {
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_LOGS, { params });
      return response.data as NotificationLogsResponse;
    },
    placeholderData: keepPreviousData,
  });
};
```

**API 契约**：`GET /notifications/logs?channel_name?&event_type?&status?&limit(1-500,def 100)&offset(def 0)` → `{items, total, limit, offset}`。权限：`notification:read`。

**幂等性**：只读查询，queryKey 含完整 params，react-query 自动管理缓存。

**影响评估**：新 hook，无破坏性。D3（统计栏）和 D7（日志 Tab）共享相同 queryKey 时自动复用缓存。

---

## D1. 消费 channel-types 元数据 + hook

**文件**：`frontend/src/hooks/useTerminalData.ts`、`frontend/src/pages/Notifications.tsx`

**变更**：

1. 在 useTerminalData.ts 新增：
```typescript
export interface ChannelTypeInfo {
  type: string;
  name: string;
  description: string;
  config_fields: string[];
}
export const useNotificationChannelTypes = () => {
  return useQuery({
    queryKey: ['notification-channel-types'],
    queryFn: async () => {
      const response = await apiClient.get(API_ENDPOINTS.NOTIFICATION_CHANNEL_TYPES);
      return response.data.channels as ChannelTypeInfo[];
    },
  });
};
```

2. 在 Notifications.tsx 中：
   - 移除硬编码的 `CHANNEL_TYPES` 数组（第 43-49 行）
   - 改用 `useNotificationChannelTypes()` 获取
   - icon 映射保留前端（后端不返回 icon）：`{ email: Mail, webhook: Link2, feishu: MessageCircle, dingtalk: MessageCircle, wecom: MessageCircle }`
   - `getChannelIcon` 通过 type 查找 icon 映射

**API 契约**：`GET /notifications/channel-types` → `{channels: [{type, name, description, config_fields:[str]}]}`。权限：`get_current_user`。

**幂等性**：react-query 缓存，后端静态字典响应稳定。

**影响评估**：移除硬编码后，后端新增渠道类型时前端自动适配（icon 除外）。config_fields 仅字段名字符串，类型/标签由 D2 的前端注册表补充。

---

## D2. 创建 notifications/shared.ts 注册表

**文件（新建）**：`frontend/src/components/notifications/shared.ts`

**变更**：镜像 [datasources/shared.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/shared.ts) 的 `ConfigFieldDef` 模式，构建渠道配置字段注册表：

```typescript
import { ConfigFieldDef } from '@/components/datasources/shared';

export const CHANNEL_CONFIG_FIELDS: Record<string, ConfigFieldDef[]> = {
  email: [
    { key: 'smtp_server', label: 'SMTP Server', type: 'text', placeholder: 'smtp.example.com' },
    { key: 'smtp_port', label: 'SMTP Port', type: 'number', defaultValue: '587' },
    { key: 'smtp_username', label: 'SMTP Username', type: 'text' },
    { key: 'smtp_password', label: 'SMTP Password', type: 'password' },
    { key: 'smtp_use_ssl', label: 'Use SSL', type: 'select', options: [{value:'true',label:'Yes'},{value:'false',label:'No'}], defaultValue: 'false' },
    { key: 'default_from', label: 'Default From', type: 'text' },
  ],
  webhook: [
    { key: 'url', label: 'Webhook URL', type: 'text', placeholder: 'https://...' },
    { key: 'secret', label: 'Secret', type: 'password' },
  ],
  feishu: [{ key: 'webhook_url', label: 'Webhook URL', type: 'text' }],
  dingtalk: [
    { key: 'webhook_url', label: 'Webhook URL', type: 'text' },
    { key: 'secret', label: 'Secret', type: 'password' },
  ],
  wecom: [{ key: 'webhook_url', label: 'Webhook URL', type: 'text' }],
};
```

复用 `datasources/shared.ts` 的 `buildConfigPayload` 和 `populateConfigFromItem` 函数（接受 `ConfigFieldDef[]` 参数，通用）。

**幂等性**：纯数据注册表。

**影响评估**：Notifications.tsx Modal 中当前硬编码的 email/webhook/feishu/dingtalk/wecom 表单字段（第 446-557 行）改为动态生成，代码大幅简化。后端 `CHANNEL_METADATA.config_fields` 与前端注册表需保持一致（可添加运行时校验作为鲁棒性保障）。

---

## C2. 创建 GeneralSettings.tsx 页面

**文件（新建）**：`frontend/src/pages/GeneralSettings.tsx`

**布局**：遵循 [Backup.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Backup.tsx) 模式 `<div className="min-h-full bg-background p-4 sm:p-6 lg:p-8"><div className="max-w-6xl mx-auto">`。

**数据加载策略**：
- `useSettings()` → `GET /settings/` 获取类型化分组当前值（queryKey: `['settings']`）
- `useSettingsList()` → `GET /settings/list` 获取全部条目元数据（含 description/value_type/is_readonly）
- 客户端合并：以 list 元数据为字段定义，以 grouped 值为当前值。值序列化统一为字符串（bool→`"true"`/`"false"`，int→`String(n)`）

**状态管理**：`useState<Record<string, string>>` 维护表单状态，初始化从合并数据填充。各 Section 独立保存按钮。

**Sections（按顺序）**：

### 1. System Status 卡片
- 调用 `GET /system/status`（认证）+ `GET /system/health`（公开）
- 展示：uptime、database（status）、db、redis（health）、version、environment、platform、python_version
- 绿色/红色圆点指示健康状态

### 2. Branding 卡片（文本字段 + 文件上传）
- 11 个 branding key 从 `/settings/list?category=branding` 获取字段定义
- 文本字段：app_name、app_short_name、app_subtitle、login_heading、login_subheading、login_footer_text、footer_copyright、footer_icp_number、footer_icp_url（均 string，text input）
- login_bg_url 和 favicon_url：只读展示当前 URL + 文件上传组件
- 文件上传：`<input type="file" accept="image/jpeg,image/png,image/gif,image/x-icon" />`，FormData 封装，`POST /settings/upload?purpose=login_bg`（或 favicon）。前端校验：类型/大小(<5MB)/扩展名（与后端 `ALLOWED_IMAGE_TYPES`/`MAX_FILE_SIZE`/`ALLOWED_EXTENSIONS` 一致）
- 上传成功后：更新本地表单 url 字段 + 调用 `useBrandingStore.getState().loadFromBackend()` 刷新全局品牌状态（侧边栏名称、favicon、document.title 立即生效）
- 文本字段保存：收集变更项，`PUT /settings/update` 批量更新。保存后再调用 `loadFromBackend()`

### 3. Security 卡片（6 keys）
- max_login_attempts、lockout_duration_minutes、captcha_threshold、access_token_expire_minutes、refresh_token_expire_days（int → number input）
- allow_registration（bool → checkbox）

### 4. Rate Limit 卡片（2 keys）
- rate_limit_per_minute、auth_rate_limit_per_minute（int → number input）

### 5. Network 卡片（6 keys）
- sangfor_enabled、switch_enabled、ipguard_enabled（bool → checkbox）
- sangfor_base_url、switch_host、ipguard_host（string → text input）

### 6. Scheduler 卡片（5 keys）
- 5 个 interval key（int，30-86400 秒）→ number input + 描述提示单位（秒）

### 7. General 卡片（3 keys）
- environment、debug（readonly → disabled input）
- log_level（string → select: DEBUG/INFO/WARNING/ERROR）

### 8. Operations 卡片
- "Seed defaults" 按钮：`POST /settings/seed`（无 body）。响应 `{message, count}`。count=0 时提示"所有配置已存在"。确认对话框。
- "Invalidate cache" 按钮：`POST /settings/invalidate-cache`（无 body）。确认对话框。
- 两者成功后 `queryClient.invalidateQueries(['settings'])` + `queryClient.invalidateQueries(['settings-list'])`

**保存逻辑（每个 Section）**：
- 比较当前表单值与原始值，仅提交变更项
- 值序列化：`String(boolVal)`、`String(intVal)`
- 批量更新：`PUT /settings/update`，body 为**裸 JSON 数组** `[{key, value}, ...]`
- 响应处理：检查每个 `ConfigUpdateResult.success`。全成功→toast 成功 + invalidateQueries。部分失败→toast 警告并列出失败 key+message
- branding section 保存后额外调用 `useBrandingStore.getState().loadFromBackend()`
- 只读字段（is_readonly=true）渲染为 disabled input，不参与提交

**权限注意**：页面路由受 `system:manage` 保护。但后端 `GET /settings/` 需 `settings:read`，`PUT /settings/update` 需 `settings:write`，`POST /settings/upload` 需 `settings:upload`，`POST /settings/seed`/`invalidate-cache` 需 `settings:write`。需确保拥有 `system:manage` 权限的用户同时具备这些细粒度权限（或根据权限隐藏对应操作）。

**API 契约汇总**：

| 操作 | 端点 | 方法 | 请求体 | 响应 | 权限 |
|------|------|------|--------|------|------|
| 加载配置 | `/settings/` | GET | - | AllConfigs（类型化分组） | settings:read |
| 加载元数据 | `/settings/list` | GET | - | ConfigEntry[] | settings:read |
| 系统状态 | `/system/status` | GET | - | {uptime, database, version, environment, platform, python_version} | 已认证 |
| 健康检查 | `/system/health` | GET | - | {status, version, environment, db, redis} | 公开 |
| 批量更新 | `/settings/update` | PUT | [{key, value}] | [{key, success, message}] | settings:write |
| 上传品牌资源 | `/settings/upload` | POST | FormData(file) + ?purpose= | {url, config_key, updated, message} | settings:upload |
| 种入默认配置 | `/settings/seed` | POST | - | {message, count} | settings:write |
| 清除缓存 | `/settings/invalidate-cache` | POST | - | {message} | settings:write |

**幂等性**：
- `PUT /settings/update` 对相同值重复提交幂等（后端 set 直接覆盖为相同值）
- `POST /settings/seed` 幂等（跳过已存在 key）
- `POST /settings/invalidate-cache` 幂等（删除不存在的 key 不报错）
- 文件上传非幂等（每次新 UUID 文件名），但 UI 上传成功后立即更新表单状态，不会重复触发

**鲁棒性**：
- 所有 API 调用 try/catch + `getErrorMessage` + toast
- 加载状态：useSettings/useSettingsList 的 isLoading/isFetching
- 保存按钮 loading 状态防重复提交
- 非乐观更新：等待服务器响应成功后才更新本地状态
- 文件上传前端预校验（类型/大小/扩展名）与后端一致，避免无效请求
- 旧上传文件不清理（已知限制，可运维定期清理 UPLOAD_DIR）

**影响评估**：
- 新页面，不影响现有功能
- `useBrandingStore.loadFromBackend()` 调用触发全局品牌状态刷新（侧边栏名称、document.title、favicon）——期望行为
- `queryClient.invalidateQueries(['settings'])` 使所有使用 `useSettings()` 的组件重新获取数据

**验证**：
1. 导航到 `/general-settings`，确认所有卡片加载并显示当前配置值
2. 修改 branding 文本字段（如 app_name），保存，确认侧边栏标题实时更新
3. 上传图片作为 login_bg，确认 login_bg_url 更新且 branding store 刷新
4. 修改 security 配置（如 max_login_attempts 5→3），保存后刷新页面确认持久化
5. 点击 Seed defaults，确认提示新种入数量或"已存在"
6. 点击 Invalidate cache，确认成功提示
7. 提交无效值（int 字段填负数），确认后端 400 且 toast 显示错误

---

## C1. App.tsx 新增路由 + pagePreloadMap

**文件**：`frontend/src/App.tsx`

**变更**：
1. lazy import 区（第 26 行 SystemSettings 之后）添加：
   ```typescript
   const GeneralSettings = lazy(() => import('./pages/GeneralSettings'));
   ```
2. `pagePreloadMap`（第 30-44 行）添加：
   ```typescript
   '/general-settings': () => import('./pages/GeneralSettings'),
   ```
3. Layout 子路由区（第 181 行 system-settings 路由之后）添加：
   ```tsx
   <Route path="general-settings" element={
     <ProtectedRoute requiredPermission="system:manage">
       <GeneralSettings />
     </ProtectedRoute>
   } />
   ```

**影响评估**：新增独立路由，不影响现有 `/system-settings` 卡片页。hover 预加载自动生效。

**验证**：登录后导航到 `/general-settings` 确认加载；无 `system:manage` 权限用户访问重定向到 `/403`。

---

## C4. NAV_ITEMS + SystemSettings 卡片路径修正

**文件**：`frontend/src/lib/constants.ts`、`frontend/src/pages/SystemSettings.tsx`

**变更**：
1. constants.ts 第 29 行 General 子菜单 path：
   ```typescript
   // 原: { path: '/system-settings', label: 'General', ... }
   { path: '/general-settings', label: 'General', iconName: 'Settings', adminOnly: true, requiredPermission: 'system:manage' },
   ```
2. SystemSettings.tsx 第 14 行 General 卡片 path：
   ```typescript
   // 原: path: '/system-settings',
   path: '/general-settings',
   ```

**影响评估**：修复 General 子菜单点击自循环 bug。Sidebar.tsx 的 `expandedGroups` 初始值 `new Set(['/system-settings'])` 控制父级展开，不受子菜单 path 变更影响。NavLink 的 isActive 匹配会正确高亮。

**验证**：点击侧边栏 System Settings > General，确认导航到 `/general-settings` 且 NavLink 高亮；在 SystemSettings 卡片页点击 General 卡片，确认跳转到 `/general-settings`。

---

## D4. Notifications.tsx Tabs 结构

**文件**：`frontend/src/pages/Notifications.tsx`

**变更**：采用 [DataSources.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/DataSources.tsx) 的 inline tab 模式：
```tsx
const [activeTab, setActiveTab] = useState<'channels' | 'logs'>('channels');

<div className="mb-6 border-b border-border">
  <nav className="-mb-px flex space-x-8">
    <button onClick={() => setActiveTab('channels')} className={activeTab==='channels' ? 'border-blue-500 text-blue-600 ...' : 'border-transparent text-muted-foreground ...'}>
      <Bell className="h-4 w-4 inline mr-2" />{t('notifications.channels')}
    </button>
    <button onClick={() => setActiveTab('logs')} className={...}>
      <FileText className="h-4 w-4 inline mr-2" />{t('notifications.sendLogs')}
    </button>
  </nav>
</div>
{activeTab === 'channels' && <ChannelsContent ... />}
{activeTab === 'logs' && <LogsContent ... />}
```

**影响评估**：原右侧 "Event Types" 静态面板（第 336-351 行）移除（事件信息整合到 Modal 手风琴分组）。布局从 3 列 grid 改为全宽单列 + tabs。

---

## D5. 渠道卡片改进

**文件**：`frontend/src/pages/Notifications.tsx`

**变更**：

### 1. Enable/Disable Toggle
每张渠道卡片右上角添加 toggle 开关：
```typescript
const handleToggleEnabled = async (channel: NotificationChannel, enabled: boolean) => {
  try {
    await apiClient.put(`${API_ENDPOINTS.NOTIFICATION_CHANNELS}${channel.id}/`, { enabled });
    toast.success(enabled ? t('common.enabled') : t('common.disabled'));
    queryClient.invalidateQueries(['notification-channels']);
  } catch (err) {
    toast.error(getErrorMessage(err, t('notifications.failedToSave')));
  }
};
```
**关键**：传绝对值 `{enabled: bool}` 而非 toggle 语义——`NotificationChannelUpdate` schema 的 `enabled` 是 `bool | None`，仅传 enabled 时后端只更新此字段。重复调用 `PUT {enabled: true}` 结果一致（幂等）。

### 2. 订阅事件彩色 chips
卡片底部显示已订阅事件，按 category 着色（带 dark: 变体）：
- terminal → `bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200`
- security → `bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200`
- admin → `bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-200`
- system → `bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200`
- alert → `bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200`

超过 3 个显示 `+N`。需从 eventTypes（含 type 和 category）查找每个订阅事件的 category。

### 3. 渠道类型颜色区分
icon 圆圈背景按类型区分（带 dark: 变体）：
- email → `bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400`
- webhook → `bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400`
- feishu → `bg-cyan-100 text-cyan-600 dark:bg-cyan-900/30 dark:text-cyan-400`
- dingtalk → `bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400`
- wecom → `bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400`

### 4. 暗色模式适配
所有 `bg-blue-100 text-blue-700` 等硬编码颜色替换为带 `dark:` 变体版本。spinner 的 `border-blue-500` 改为 `border-primary border-t-transparent`。

**API 契约**：`PUT /notifications/channels/{id}` body `{enabled: bool}` → NotificationChannelResponse。权限：notification:manage（或 system:manage）。

**幂等性**：toggle 使用绝对值确保幂等。网络失败时 UI 不变更（非乐观更新，等服务器响应确认）。toggle 操作期间按钮 disabled + loading。

---

## D6. Modal 事件订阅手风琴分组

**文件**：`frontend/src/pages/Notifications.tsx`

**前置修正**（重要 Bug 修复）：
- 当前 `eventTypes` state 类型为 `{id, name, description}[]`——但后端返回的是 `{type, name, description, severity, category}[]`（无 id 字段，type 才是标识符）
- 当前 `toggleEvent` 使用 `event.id`——应改为 `event.type`
- 当前 `watch('events')` 比较使用 `e.id`——应改为 `e.type`
- 这些是现存 Bug，会导致事件订阅功能完全不工作（event.id 为 undefined）

**变更**：
1. 更新 `eventTypes` state 类型：`{type, name, description, severity, category}[]`
2. `toggleEvent` 参数改为 `eventType: string`
3. `watch('events')` 比较改为 `e.type`
4. 按 category 分组渲染手风琴：
```tsx
const eventsByCategory = useMemo(() => {
  const groups: Record<string, EventMeta[]> = {};
  eventTypes.forEach(evt => {
    if (!groups[evt.category]) groups[evt.category] = [];
    groups[evt.category].push(evt);
  });
  return groups;
}, [eventTypes]);

const categoryLabels: Record<string, string> = {
  terminal: t('notifications.categories.terminal'),
  security: t('notifications.categories.security'),
  admin: t('notifications.categories.admin'),
  system: t('notifications.categories.system'),
  alert: t('notifications.categories.alert'),
};

{Object.entries(eventsByCategory).map(([cat, events]) => {
  const selectedCount = events.filter(e => watch('events').includes(e.type)).length;
  return (
    <div key={cat} className="border border-border rounded-lg">
      <button onClick={() => toggleCategory(cat)} className="...">
        <span>{categoryLabels[cat]}</span>
        <span className="text-xs">({selectedCount}/{events.length})</span>
        <ChevronDown className={expandedCats[cat] ? 'rotate-180' : ''} />
      </button>
      {expandedCats[cat] && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3">
          {events.map(evt => (
            <label key={evt.type} className={...}>
              <input type="checkbox" checked={watch('events').includes(evt.type)} onChange={() => toggleEvent(evt.type)} />
              <span>{evt.name}</span>
              <span className="text-xs text-muted-foreground">{evt.description}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
})}
```
默认全部展开。移除 `max-h-60 overflow-y-auto`，整个事件区域用 `max-h-[60vh] overflow-y-auto`。

**需新增 i18n 键**：`notifications.categories.{terminal,security,admin,system,alert}` 和 `notifications.sendLogs`。

**影响评估**：修复事件订阅不工作的 Bug + 提升可读性。依赖 B1 补全后的 30 个事件。

---

## D3. 顶部统计栏

**文件**：`frontend/src/pages/Notifications.tsx`

**变更**：页面头部和 Tabs 之间添加 4 个统计卡片（`grid-cols-2 md:grid-cols-4`）：
- Total Channels：`channels.length`
- Enabled：`channels.filter(c => c.enabled).length`
- 24h Sent：从 logs 客户端计算
- 24h Failed：从 logs 客户端计算

24h 统计策略：调用 `useNotificationLogs({limit: 500})` 获取最近 500 条日志，客户端过滤 `sent_at` 在最近 24h 内（`Date.now() - 24*60*60*1000`），按 status 统计。与 D7 的 Logs Tab 共享相同 queryKey 时自动复用缓存。

**已知限制**：500 条可能不足以覆盖高流量 24h 全部记录。如需精确统计需后端添加聚合端点（本次不涉及）。

**幂等性**：只读计算，无副作用。

---

## D7. Send Logs Tab

**文件**：`frontend/src/pages/Notifications.tsx`（或抽取为 `frontend/src/components/notifications/LogsTab.tsx`）

**变更**：

### 筛选器区域
- channel_name：select，options 从 channels 列表提取 name
- event_type：select，options 从 eventTypes 提取 type + name
- status：select，options: sent / failed / pending
- 筛选变更时重置 offset 为 0

### 表格列
| 列 | 字段 | 格式化 |
|----|------|--------|
| Event ID | event_id | 文本（可 truncate） |
| Channel | channel_name | 文本 |
| Event Type | event_type | 查找 eventTypes 的 name 显示 |
| Status | status | 彩色 badge（sent=green, failed=red, pending=yellow） |
| Recipient | recipient | 文本，nullable |
| Sent At | sent_at | `formatDateTime` |
| Error | error_message | 文本，nullable，truncate |

### 分页
使用 `Pagination` 组件（[frontend/src/components/Pagination.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/Pagination.tsx)）。
- offset-based：`page = offset / limit + 1`，`totalPages = Math.ceil(total / limit)`
- pageSize 默认 20，options [10, 20, 50, 100]
- `onPageChange` → `setOffset((page-1) * pageSize)`
- `totalItems` 从响应 `total` 获取

### 数据获取
使用 D8 的 `useNotificationLogs(params)` hook。

**API 契约**：`GET /notifications/logs?channel_name&event_type&status&limit&offset` → `{items, total, limit, offset}`。权限：notification:read。

**幂等性**：只读查询，`placeholderData: keepPreviousData` 确保翻页无闪烁。

---

## E1. 合规操作 UI 入口

**文件**：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`、i18n 文件

**变更**：在 ComplianceBaselinesTab 表格上方添加操作按钮区：
```tsx
<div className="mb-4 flex flex-wrap gap-3">
  <PrimaryButton icon={ShieldCheck} label={t('compliance.runCheck')} variant="primary"
    onClick={handleComplianceCheck} loading={complianceLoading} />
  <PrimaryButton icon={Ban} label={t('compliance.autoBlock')} variant="danger"
    onClick={handleAutoBlock} loading={autoBlockLoading} />
  <PrimaryButton icon={Unlock} label={t('compliance.autoUnblock')} variant="success"
    onClick={handleAutoUnblock} loading={autoUnblockLoading} />
</div>
```

### ARP 源标签选择器（auto-block 必填）
auto-block 的 `arp_source_tag` 是必填字段。需在 auto-block 按钮旁或弹出的确认对话框中提供 ARP 源标签选择器（从 `useDataSources()` 获取 type 为 arp_ssh/arp_api 的数据源 tag 列表）。

### handler 函数
```typescript
const handleComplianceCheck = async () => {
  setComplianceLoading(true);
  try {
    const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_CHECK, {
      arp_source_tag: selectedTag || undefined, // 可选
      force: false,
    });
    const r = response.data;
    toast.success(t('compliance.checkComplete', {
      total: r.total_checked, compliant: r.compliant,
      bypass: r.bypass, nonCompliant: r.non_compliant
    }));
    queryClient.invalidateQueries(['terminals']);
  } catch (err) {
    toast.error(getErrorMessage(err, t('compliance.checkFailed')));
  } finally { setComplianceLoading(false); }
};

const handleAutoBlock = async () => {
  if (!selectedTag) { toast.warning(t('compliance.selectSourceTag')); return; }
  if (!confirm(t('compliance.confirmAutoBlock'))) return;
  setAutoBlockLoading(true);
  try {
    const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_AUTO_BLOCK, {
      arp_source_tag: selectedTag,
      block_time: '30d',
      dry_run: false,
    });
    const r = response.data;
    toast.success(t('compliance.autoBlockComplete', {
      total: r.total_non_compliant, blocked: r.blocked, skipped: r.skipped
    }));
    if (r.errors?.length) toast.warning(t('compliance.partialErrors', { count: r.errors.length }));
    queryClient.invalidateQueries(['terminals']);
    queryClient.invalidateQueries(['blacklist']);
  } catch (err) {
    toast.error(getErrorMessage(err, t('compliance.autoBlockFailed')));
  } finally { setAutoBlockLoading(false); }
};

const handleAutoUnblock = async () => {
  setAutoUnblockLoading(true);
  try {
    const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_AUTO_UNBLOCK);
    const r = response.data;
    toast.success(t('compliance.autoUnblockComplete', {
      total: r.total_auto_blocked, unblocked: r.unblocked, skipped: r.skipped
    }));
    if (r.errors?.length) toast.warning(t('compliance.partialErrors', { count: r.errors.length }));
    queryClient.invalidateQueries(['terminals']);
    queryClient.invalidateQueries(['blacklist']);
  } catch (err) {
    toast.error(getErrorMessage(err, t('compliance.autoUnblockFailed')));
  } finally { setAutoUnblockLoading(false); }
};
```

**API 契约（已验证 schema）**：

| 操作 | 端点 | 方法 | 请求体 | 响应 | 权限 |
|------|------|------|--------|------|------|
| 合规检查 | `/data-sources/compliance/check` | POST | `{arp_source_tag?: str, force: bool}` | `{total_checked, compliant, bypass, non_compliant, unknown, message?, details?}` | datasource:compliance |
| 自动封禁 | `/data-sources/compliance/auto-block` | POST | `{arp_source_tag: str (必填), block_time: str (默认"30d"), dry_run: bool (默认false)}` | `{total_non_compliant, blocked, skipped, errors: [str], details?}` | datasource:compliance |
| 自动解封 | `/data-sources/compliance/auto-unblock` | POST | 无 body | `{total_auto_blocked, unblocked, skipped, errors: [str], details?}` | datasource:compliance |

**权限注意**：需 `datasource:compliance` 权限。当前 DataSources 页面受 `datasource:read` 保护，但 compliance 操作需更高级权限。建议按钮上做权限检查：`user?.permissions?.includes('datasource:compliance')`，无权限时隐藏或 disabled。

**幂等性**：
- `compliance/check` force=false 时仅检查 unknown 状态，幂等；force=true 重查所有，语义明确
- `auto-block` 不严格幂等——每次封禁当前不合规终端，但已封禁的 skip。重复调用趋于稳定
- `auto-unblock` 类似——解封合规的，已解封的 skip

**鲁棒性**：
- auto-block 是破坏性操作（封禁终端），必须确认对话框
- `errors[]` 数组中的部分错误需展示给用户
- 操作后 invalidateQueries 刷新 terminals 和 blacklist 缓存
- loading 状态防重复提交

**影响评估**：激活死代码常量（COMPLIANCE_CHECK/AUTO_BLOCK/AUTO_UNBLOCK）。需新增 `compliance.*` i18n 键（runCheck/autoBlock/autoUnblock/checkComplete/confirmAutoBlock/selectSourceTag/partialErrors 等）。

**验证**：
1. 合规基线页面确认 3 个按钮显示
2. 点击 Run Compliance Check，toast 显示检查结果统计
3. 点击 Auto-Block，确认弹出 ARP 源选择 + 确认对话框，确认后显示封禁结果
4. 点击 Auto-Unblock，显示解封结果
5. 无 datasource:compliance 权限用户不应看到按钮

---

## G1/G2. 跨切面幂等性与鲁棒性审查

### 幂等性总表

| 操作 | 幂等性 | 说明 |
|------|--------|------|
| `POST /settings/seed` | ✅ 幂等 | 跳过已存在 key，count=0 时提示"无需种入" |
| `POST /settings/invalidate-cache` | ✅ 幂等 | 删除不存在的 key 不报错 |
| `PUT /settings/{key}` | ✅ 幂等 | 相同值覆盖结果一致 |
| `PUT /settings/update` | ✅ 幂等 | 同上，前端仅提交变更项进一步减少写入 |
| `PUT /notifications/channels/{id}` (enabled) | ✅ 幂等 | 使用绝对值 `{enabled: bool}` 而非 toggle 语义 |
| `POST /settings/upload` | ❌ 非幂等 | 每次新 UUID 文件名，但 UI 上传后立即更新状态不重复触发 |
| `POST /compliance/check` (force=false) | ✅ 幂等 | 仅检查 unknown 状态 |
| `POST /compliance/check` (force=true) | ⚠️ 语义明确非严格幂等 | 重查所有 |
| `POST /compliance/auto-block` | ⚠️ 趋于稳定 | 已封禁的 skip，重复调用 blocked=0 |
| `POST /compliance/auto-unblock` | ⚠️ 趋于稳定 | 已解封的 skip |

### 鲁棒性统一模式

**错误处理**：所有新 API 调用遵循
```typescript
try {
  const response = await apiClient.post/put/get(...);
  toast.success(successMessage);
  queryClient.invalidateQueries([relevantQueryKey]);
} catch (err) {
  toast.error(getErrorMessage(err, fallbackMessage));
} finally {
  setLoading(false);
}
```

**加载状态**：
- react-query hooks 自带 isLoading/isFetching/isError
- mutation 用本地 useState loading flag + PrimaryButton loading prop
- 页面级 spinner：`<div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />`

**缓存失效策略**：
- settings 变更后：`queryClient.invalidateQueries(['settings'])` + `['settings-list']`
- branding 变更后额外：`useBrandingStore.getState().loadFromBackend()`
- 通知渠道变更后：`queryClient.invalidateQueries(['notification-channels'])`
- 合规操作后：`queryClient.invalidateQueries(['terminals'])` + `['blacklist']`

**非乐观更新**：所有配置变更等待服务器响应成功后才更新本地状态/UI。

**边界情况**：
- useSettings/useSettingsList 返回 undefined（加载中）时表单显示骨架屏/disabled
- 只读字段（is_readonly=true）渲染 disabled input，提交时跳过
- 文件上传前端预校验（类型/大小/扩展名）与后端一致
- 未知渠道类型 fallback 显示通用文本输入

### 一致性保障

**值序列化**：前端→后端所有 config value 统一字符串（bool→`"true"`/`"false"`，int→`String(n)`）。后端→前端 `GET /settings/` 返回类型化值，`GET /settings/list` 返回字符串值，前端合并时类型化值转回字符串初始化表单。

**事件类型标识符**：后端 `EventType.value`（如 `"terminal.compliant"`）= 渠道 `events` 字段值 = `GET /notifications/events` 返回的 `type` 字段。前端 `toggleEvent` 使用 `event.type`（D6 修复了原来错误使用 `event.id` 的 Bug）。

**组件复用**：PrimaryButton/IconButton/ButtonGroup、Pagination、Modal、useForm、getErrorMessage、formatDateTime、downloadCSV。

---

## 实施顺序（依赖排序）

### 阶段 1：后端基础修复（可并行）
1. **A1** — 修复 PROMETHEUS_ENABLED（config.py）
2. **B1** — 补全 EVENT_METADATA（event_types.py）

### 阶段 2：前端 i18n 基础（可并行）
3. **F1** — 修复 i18n 缺失键（common.download, auth.forgotPassword/authMethod/resetPassword）

### 阶段 3：基础设施（依赖阶段 1-2）
4. **G3a** — constants.ts 补充 API_ENDPOINTS 常量
5. **C5** — 新增 generalSettings i18n 命名空间
6. **D8** — 新增 useNotificationLogs hook
7. **D1** — 新增 useNotificationChannelTypes hook
8. **D6 i18n** — 新增 notifications.categories.* 和 sendLogs 键
9. **E1 i18n** — 新增 compliance.* 键

### 阶段 4：共享组件（依赖阶段 3）
10. **D2** — 创建 notifications/shared.ts 注册表

### 阶段 5：新页面（依赖阶段 3-4）
11. **C2** — 创建 GeneralSettings.tsx
12. **C1** — App.tsx 新增路由 + pagePreloadMap
13. **C4** — NAV_ITEMS + SystemSettings 卡片路径修正

### 阶段 6：Notifications 改造（依赖阶段 1, 3-4）
14. **D4** — Tabs 结构搭建
15. **D5** — 渠道卡片改进（toggle + chips + 暗色模式）
16. **D6** — Modal 事件手风琴分组（含 event.id→event.type Bug 修复）
17. **D3** — 顶部统计栏
18. **D7** — Send Logs Tab

### 阶段 7：Compliance Ops（依赖阶段 3）
19. **E1** — ComplianceBaselinesTab 添加 3 个操作按钮

### 阶段 8：验证
20. **G1/G2** — 全面审查幂等性/鲁棒性/一致性
21. 本地 rebuild + 功能验证

---

## 验证方案（端到端）

### 后端验证
```bash
# A1: PROMETHEUS_ENABLED 修复
manage.sh rebuild backend && manage.sh restart backend
curl -H "Authorization: Bearer <token>" http://localhost:8080/api/v1/system/config
# 预期: 200, 含 metrics_enabled: false

# B1: EVENT_METADATA 补全
curl -H "Authorization: Bearer <token>" http://localhost:8080/api/v1/notifications/events | jq '.events | length'
# 预期: 30
```

### 前端验证
```bash
manage.sh rebuild frontend && manage.sh restart nginx
# 访问 http://localhost:8080
```

1. **General 页面**：导航到 `/general-settings`，确认 8 个 Section 加载；修改 branding app_name 保存，确认侧边栏实时更新；上传 login_bg，确认 Login 页背景变更；修改 security 配置保存后刷新确认持久化；点击 Seed defaults 和 Invalidate cache 确认提示
2. **通知页面**：确认 Tabs 切换（渠道/日志）；渠道卡片有 Toggle 开关和事件 chips；Modal 事件按 5 类手风琴分组；Send Logs Tab 表格+筛选+分页正常；顶部统计栏数字正确
3. **合规操作**：DataSources > Compliance Baselines Tab 确认 3 个按钮；点击 Run Check 显示统计；Auto-Block 弹出确认对话框+ARP源选择；Auto-Unblock 显示结果
4. **i18n**：切换三语，确认 Backup 下载按钮、Login 认证方式标签/忘记密码链接、PasswordReset 标题正确显示
5. **暗色模式**：切换主题，确认通知页面所有色块在暗色模式下可读

### 幂等性验证
- 连续点击 Seed defaults 两次，第二次确认 count=0
- 连续点击 Invalidate cache 两次，确认均成功
- 通知渠道 Toggle 连续点击 Enable 两次，确认状态保持 Enable
- 合规 auto-block 连续调用两次，第二次确认 blocked=0

---

## 关键文件索引

**后端**：
- [config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/config.py) — A1: 添加 PROMETHEUS_ENABLED
- [event_types.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/notification_channels/event_types.py) — B1: 补全 EVENT_METADATA

**前端基础设施**：
- [constants.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/lib/constants.ts) — G3a: API_ENDPOINTS + C4: NAV_ITEMS
- [App.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/App.tsx) — C1: 路由 + preload
- [useTerminalData.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/hooks/useTerminalData.ts) — D8/D1: 新 hooks
- [zh.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/zh.ts) / [en.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/en.ts) / [ja.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/ja.ts) — F1/C5/D6/E1 i18n

**前端新页面/组件**：
- GeneralSettings.tsx（新建）— C2
- [notifications/shared.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/notifications/shared.ts)（新建）— D2

**前端改造**：
- [Notifications.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Notifications.tsx) — D1/D3-D7
- [SystemSettings.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/SystemSettings.tsx) — C4: 卡片路径
- [ComplianceBaselinesTab.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/ComplianceBaselinesTab.tsx) — E1: 合规操作按钮

**参考文件**（复用模式）：
- [Backup.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Backup.tsx) — 配置编辑模式参考
- [DataSources.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/DataSources.tsx) — inline tab 模式参考
- [datasources/shared.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/shared.ts) — ConfigFieldDef 模式参考
- [branding.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/store/branding.ts) — loadFromBackend 调用
