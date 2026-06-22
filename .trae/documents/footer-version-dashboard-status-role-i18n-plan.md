# 页脚版本号、Dashboard 系统信息、角色 i18n 改善计划

> 文档版本：v1.0  更新日期：2026-06-18

---

## 一、现状分析

### 1.1 页脚版本号

| 位置 | 当前状态 | 问题 |
|------|---------|------|
| 登录页 Footer ([Login.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Login.tsx) L457) | 显示 `branding.version`（硬编码 `v2.0.0`） | 版本号与后端 `3.3.1` 不一致 |
| 主布局 Footer ([Layout.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/Layout.tsx) L49-67) | 仅显示版权和 ICP 备案号 | **不显示版本号** |
| 前端品牌配置 ([branding.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/config/branding.ts) L55) | `version: 'v2.0.0'` | 硬编码，与后端不同步 |
| 后端 Health API (`GET /health`) | 返回 `version` + `environment` | 前端未调用 |

### 1.2 Dashboard 系统状态

| 位置 | 当前状态 | 问题 |
|------|---------|------|
| [Dashboard.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Dashboard.tsx) L89-116 | 显示 Backend API、Database、Sangfor AF、Network Scanner 状态 | **不显示版本号和运行环境** |
| `/api/v1/stats/system-status` API | 返回 4 项连接状态 | **不包含版本和环境字段** |
| `GET /health` API | 返回 `version` + `environment` | Dashboard 未使用此数据 |

### 1.3 角色 i18n

| 位置 | 当前状态 | 问题 |
|------|---------|------|
| 角色名称 (name) | 前端 `t('roles.${role.name}')` | ✅ 已 i18n |
| 角色描述 (description) | 前端直接显示 `role.description` | ❌ 硬编码中文 |
| 权限名称 (perm.name) | 前端直接显示 `perm.name` | ❌ 硬编码中文 |
| 权限描述 (perm.description) | 前端直接显示 `perm.description` | ❌ 硬编码中文 |
| 后端种子数据 ([cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py) L508-514) | 5 个角色描述全为中文 | 切换语言后仍显示中文 |
| 后端种子数据 ([cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py) L524-554) | 29 个权限名称/描述全为中文 | 切换语言后仍显示中文 |

---

## 二、修改方案

### 2.1 页脚自动填充系统版本

**策略**: 从后端 `/health` API 获取版本号，存入 branding store，在 Footer 中显示。

**修改文件**:

#### A. `frontend/src/store/branding.ts`
- 在 `BrandingState` 接口中添加 `systemVersion: string` 和 `systemEnvironment: string` 字段
- 在 `fetchBranding()` 方法中，调用 `GET /health` 获取 `version` 和 `environment`，存入 store

#### B. `frontend/src/components/Layout.tsx`
- 在 Footer 的版权信息旁添加版本号显示，格式：`v{systemVersion}`
- 从 `useBrandingStore()` 获取 `systemVersion`

#### C. `frontend/src/config/branding.ts`
- 删除硬编码的 `version: 'v2.0.0'`（L55）
- 从 `BrandingConfig` 接口中移除 `version` 字段（L15）

#### D. `frontend/src/pages/Login.tsx`
- 将 `branding.version` 改为从 store 获取 `systemVersion`

### 2.2 Dashboard 系统状态新增版本和环境

**策略**: 在 Dashboard 的 System Status 区域添加版本号和运行环境显示。

**修改文件**:

#### A. `frontend/src/pages/Dashboard.tsx`
- 在 System Status 卡片中，在现有 4 个状态项之前，添加"系统版本"和"运行环境"两项
- 数据从 `useBrandingStore()` 的 `systemVersion` 和 `systemEnvironment` 获取
- 版本号显示格式：`v3.3.1`
- 环境显示格式：`生产环境` / `开发环境`（通过 i18n 翻译）

#### B. `frontend/src/i18n/locales/zh.ts` / `en.ts` / `ja.ts`
- 在 `dashboard` 命名空间中添加 `systemVersion`、`systemEnvironment`、`envProduction`、`envDevelopment` 翻译键

### 2.3 角色和权限描述 i18n

**策略**: 前端根据 `role.name` 和 `perm.code` 映射到 i18n 翻译键，不再直接显示后端返回的硬编码文本。后端种子数据保持不变（数据库中仍存储中文描述，作为 API 直接调用时的回退）。

**理由**: 
- 修改后端数据库存储方式（如存 i18n 键）会破坏 API 兼容性，且需要数据迁移
- 前端 i18n 映射是最小侵入方案，不影响后端逻辑和数据库
- 后端硬编码描述作为 API 直接调用（如 curl）时的可读回退

**修改文件**:

#### A. `frontend/src/i18n/locales/zh.ts`
- 在 `roles` 命名空间中添加角色描述翻译键：
  - `roles.superadmin_desc`: "拥有系统全部权限"
  - `roles.admin_desc`: "管理用户、数据源、系统配置"
  - `roles.operator_desc`: "操作终端、白名单、黑名单"
  - `roles.auditor_desc`: "查看审计日志和导出"
  - `roles.viewer_desc`: "仅查看各模块数据"
- 添加权限翻译键（按模块分组）：
  - `permissions.terminal:read`: "查看终端"
  - `permissions.terminal:read_desc`: "查看终端列表和详情"
  - `permissions.terminal:write`: "操作终端"
  - ... 共 29 个权限的 name 和 description

#### B. `frontend/src/i18n/locales/en.ts`
- 添加对应的英文翻译

#### C. `frontend/src/i18n/locales/ja.ts`
- 添加对应的日文翻译

#### D. `frontend/src/pages/Roles.tsx`
- 角色描述显示：`role.description` → `t('roles.${role.name}_desc', role.description)`
- 权限名称显示：`perm.name` → `t('permissions.${perm.code}', perm.name)`
- 权限描述显示：`perm.description` → `t('permissions.${perm.code}_desc', perm.description)`

#### E. 其他涉及角色/权限显示的组件
- `Users.tsx` — 角色名称已用 i18n，检查描述是否需要
- `Profile.tsx` — 角色名称已用 i18n
- `Sidebar.tsx` — 角色名称已用 i18n

---

## 三、详细实施步骤

### 步骤 1: branding store 添加版本和环境字段

**文件**: `frontend/src/store/branding.ts`

1. 在 `BrandingState` 接口中添加：
   ```ts
   systemVersion: string;
   systemEnvironment: string;
   ```
2. 在初始状态中设置默认值：
   ```ts
   systemVersion: '',
   systemEnvironment: '',
   ```
3. 在 `fetchBranding()` 方法末尾，添加 `/health` API 调用：
   ```ts
   try {
     const healthRes = await fetch('/health');
     if (healthRes.ok) {
       const healthData = await healthRes.json();
       set({ systemVersion: healthData.version || '', systemEnvironment: healthData.environment || '' });
     }
   } catch { /* non-critical */ }
   ```

### 步骤 2: 删除前端硬编码版本号

**文件**: `frontend/src/config/branding.ts`

1. 删除 `BrandingConfig` 接口中的 `version: string;` 字段（L15）
2. 删除 `defaultBranding` 中的 `version: 'v2.0.0'`（L55）

**文件**: `frontend/src/pages/Login.tsx`

1. 修改 L457 附近的版本号显示，从 `branding.version` 改为 `useBrandingStore().systemVersion`
2. 需要在 Login 组件中引入 `useBrandingStore`

### 步骤 3: Layout Footer 添加版本号

**文件**: `frontend/src/components/Layout.tsx`

1. 从 `useBrandingStore()` 解构 `systemVersion`
2. 在 Footer 版权信息旁添加版本号：
   ```tsx
   <span>{copyrightText}</span>
   {systemVersion && <span>v{systemVersion}</span>}
   ```

### 步骤 4: Dashboard 添加版本和环境

**文件**: `frontend/src/pages/Dashboard.tsx`

1. 从 `useBrandingStore()` 解构 `systemVersion` 和 `systemEnvironment`
2. 在 System Status 区域添加两项（在现有状态项之前）：
   ```tsx
   {/* System Version */}
   <div className="flex items-center justify-between py-2">
     <span className="text-sm text-muted-foreground">{t('dashboard.systemVersion')}</span>
     <span className="text-sm font-medium">v{systemVersion}</span>
   </div>
   {/* Environment */}
   <div className="flex items-center justify-between py-2">
     <span className="text-sm text-muted-foreground">{t('dashboard.systemEnvironment')}</span>
     <span className="text-sm font-medium">
       {systemEnvironment === 'production' ? t('dashboard.envProduction') : t('dashboard.envDevelopment')}
     </span>
   </div>
   ```

### 步骤 5: i18n 翻译文件更新

**三个文件**: `frontend/src/i18n/locales/zh.ts`, `en.ts`, `ja.ts`

Dashboard 部分添加：
```ts
systemVersion: '系统版本',
systemEnvironment: '运行环境',
envProduction: '生产环境',
envDevelopment: '开发环境',
```

Roles 部分添加角色描述：
```ts
superadmin_desc: '拥有系统全部权限',
admin_desc: '管理用户、数据源、系统配置',
operator_desc: '操作终端、白名单、黑名单',
auditor_desc: '查看审计日志和导出',
viewer_desc: '仅查看各模块数据',
```

Permissions 部分添加（29 个权限的 name 和 desc）：
```ts
permissions: {
  'terminal:read': '查看终端',
  'terminal:read_desc': '查看终端列表和详情',
  'terminal:write': '操作终端',
  'terminal:write_desc': '封禁/解封终端',
  // ... 其余 27 个
}
```

### 步骤 6: Roles.tsx 使用 i18n 翻译

**文件**: `frontend/src/pages/Roles.tsx`

1. 角色描述（L186-188）：
   ```tsx
   // 修改前
   {role.description || '—'}
   // 修改后
   {t(`roles.${role.name}_desc`, role.description) || '—'}
   ```

2. 权限名称（L330）：
   ```tsx
   // 修改前
   {perm.name}
   // 修改后
   {t(`permissions.${perm.code}`, perm.name)}
   ```

3. 权限描述（如有显示）：
   ```tsx
   // 修改后
   {t(`permissions.${perm.code}_desc`, perm.description)}
   ```

4. 查看角色弹窗中的描述（L302-303）：
   ```tsx
   // 修改后
   {t(`roles.${viewingRole.name}_desc`, viewingRole.description) || '—'}
   ```

---

## 四、验证步骤

1. **语法检查**: `cd frontend && npx tsc --noEmit`
2. **登录页验证**: 访问登录页，确认 Footer 显示 `v3.3.1`（而非 `v2.0.0`）
3. **主布局 Footer 验证**: 登录后，确认主页面 Footer 显示版本号
4. **Dashboard 验证**: 确认 System Status 区域显示"系统版本"和"运行环境"
5. **角色 i18n 验证**:
   - 切换到英文，确认角色描述和权限名称显示英文
   - 切换到日文，确认角色描述和权限名称显示日文
   - 切换回中文，确认显示中文
6. **API 兼容性**: 确认 `/api/v1/roles/` API 返回的描述字段仍为中文（后端不变）

---

## 五、不修改的内容

- **后端角色种子数据**: 保持硬编码中文描述，作为 API 直接调用时的可读回退
- **后端 API 响应**: 角色和权限的 `description`/`name` 字段保持中文，不做国际化
- **数据库 schema**: 不添加 i18n 相关字段
