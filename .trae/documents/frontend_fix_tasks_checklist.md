# 前端功能缺失修复 — 开发任务清单

> 文档版本：v1.1  更新日期：2026-08-05
> 前置文档：`frontend_backend_gap_analysis_plan.md`
> 修正说明：v1.1 修正了 AdvisorTool 指出的 5 处假设性错误（i18n key 不存在、API 响应字段错误、hook 刷新方法错误、导入缺失）

---

## 任务依赖关系

```
任务5（LDAP常量规范化）──→ 无依赖，可独立实施
任务1（合规配置子菜单） ──→ 依赖任务5（常量规范风格参考）
任务2（通知单条重试）   ──→ 依赖任务1（UI组件复用风格）
任务3（防火墙对账）     ──→ 依赖任务1（按钮组件复用风格）
任务4（SystemSettings） ──→ 依赖任务1、任务3（卡片/按钮组件复用）
```

**推荐实施顺序**：任务5 → 任务1 → 任务2 → 任务3 → 任务4

---

## 任务 5：LDAP API 常量规范化（P1 · 独立可先做）

### 步骤 5.1：新增常量定义
**文件**：`frontend/src/lib/constants.ts`
**位置**：L40-L109（`API_ENDPOINTS` 对象内）

在现有常量后追加：
```typescript
  LDAP_OUS: '/ldap/ous',
  LDAP_SEARCH: '/ldap/search',
  LDAP_IMPORT: '/ldap/import',
```

### 步骤 5.2：替换内联字符串
**文件**：`frontend/src/components/LDAPImportModal.tsx`
**替换映射**：
| 原代码行 | 替换为 |
|---------|--------|
| L91: `apiClient.get('/ldap/ous')` | `apiClient.get(API_ENDPOINTS.LDAP_OUS)` |
| L109/L129: `apiClient.post('/ldap/search', ...)` | `apiClient.post(API_ENDPOINTS.LDAP_SEARCH, ...)` |
| L172: `apiClient.post('/ldap/import', ...)` | `apiClient.post(API_ENDPOINTS.LDAP_IMPORT, ...)` |

### 步骤 5.3：验证
- 运行前端编译无错误
- LDAP 导入功能正常工作（OUS 加载、搜索、导入）

---

## 任务 1：实现合规配置子菜单（P0 · 核心功能）

### 步骤 1.1：扩展 AllConfigs 接口
**文件**：`frontend/src/hooks/useTerminalData.ts`
**位置**：L351-L359

新增 `ComplianceConfig` 接口（已验证：后端 `ComplianceConfigResponse` 只有 `compliance_confirm_threshold` 一个字段，类型为 `int`）：
```typescript
export interface ComplianceConfig {
  compliance_confirm_threshold: number;
}
```

扩展 `AllConfigs` 接口：
```typescript
export interface AllConfigs {
  // ... 现有字段（security, rate_limit, network, scheduler, general, branding, email）...
  compliance: ComplianceConfig;  // 新增
}
```

### 步骤 1.2：更新 flattenConfigs
**文件**：`frontend/src/pages/GeneralSettings.tsx`
**位置**：L53-L67

在 `allGroups` 数组中增加 `configs.compliance`：
```typescript
const allGroups = [
  configs.security, configs.rate_limit, configs.network,
  configs.scheduler, configs.general, configs.branding,
  configs.compliance,  // 新增
];
```

### 步骤 1.3：新增 SECTION_FIELDS 分组
**文件**：`frontend/src/pages/GeneralSettings.tsx`
**位置**：L27-L50

在 `SECTION_FIELDS` 对象中增加：
```typescript
const SECTION_FIELDS: Record<string, string[]> = {
  // ... 现有字段 ...
  compliance: ['compliance_confirm_threshold'],  // 新增
};
```

### 步骤 1.4：渲染合规配置 SectionCard
**文件**：`frontend/src/pages/GeneralSettings.tsx`
**位置**：现有 SectionCard 渲染区域（约 L534 附近，General 区块之后）

在 General 区块之后新增合规配置区块（注意：现有代码是用 `Object.entries(SECTION_FIELDS).map(...)` 渲染所有区块，因此只需在 `SECTION_FIELDS` 中添加 `compliance` 即可自动渲染）：

确认现有渲染逻辑：
```typescript
{Object.entries(SECTION_FIELDS).map(([category, fields]) => {
  // ... 现有逻辑已覆盖所有 category ...
  // 新增 compliance 后，此处会自动渲染合规配置区块
})}
```

### 步骤 1.5：添加 i18n 翻译
**文件**：`frontend/src/i18n/locales/zh.ts`、`en.ts`、`ja.ts`

在 `generalSettings` 命名空间下新增：
```typescript
compliance: '合规配置',
complianceDesc: '合规状态翻转确认相关配置',
compliance_confirm_threshold: '确认阈值 (次)',
compliance_confirm_thresholdDesc: '连续多少次检测到非合规后才翻转状态',
```

### 步骤 1.6：验证
- 前端编译无错误
- General Settings 页面显示"合规配置"区块
- 修改阈值后保存成功
- 刷新后持久化生效

---

## 任务 2：实现通知单条日志重试（P0 · 核心功能）

### 步骤 2.1：确认 API 常量已就绪
**文件**：`frontend/src/lib/constants.ts`
**位置**：L102
**状态**：✅ `NOTIFICATION_LOGS_RETRY` 已定义，无需修改

### 步骤 2.2：添加单条重试按钮
**文件**：`frontend/src/pages/Notifications.tsx`
**位置**：L774-L790（日志表格操作栏）

在现有"归档"和"删除"按钮之前新增重试按钮：
```typescript
<td className="py-2 px-3">
  <div className="flex items-center gap-1">
    {/* 新增：重试按钮（仅对失败日志显示） */}
    {log.status === 'failed' && (
      <button
        onClick={() => handleRetryLog(log.id)}
        className="p-1.5 text-muted-foreground hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
        title={t('notificationLogs.retry')}
      >
        <RefreshCw className="h-3.5 w-3.5" />
      </button>
    )}
    {/* 现有：归档、删除按钮 */}
    <button onClick={...} title="Archive">
      <Archive className="h-3.5 w-3.5" />
    </button>
    <button onClick={...} title="Delete">
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  </div>
</td>
```

### 步骤 2.3：实现 handleRetryLog 方法
**文件**：`frontend/src/pages/Notifications.tsx`
**位置**：L350-L400（现有日志操作方法区域）

新增方法（使用 `queryClient.invalidateQueries` 刷新列表，而非 `refetch()`）：
```typescript
const handleRetryLog = async (logId: number) => {
  try {
    await apiClient.post(API_ENDPOINTS.NOTIFICATION_LOGS_RETRY.replace('{{id}}', String(logId)));
    toast.success(t('notificationLogs.retrySuccess'));
    // 刷新日志列表（使用 queryClient 失效缓存）
    const queryClient = useQueryClient();
    queryClient.invalidateQueries({ queryKey: ['notification-logs'] });
  } catch (err) {
    toast.error(getErrorMessage(err));
  }
};
```

### 步骤 2.4：导入 RefreshCw 图标和 useQueryClient
**文件**：`frontend/src/pages/Notifications.tsx`
**位置**：L1-L11

在 imports 中增加：
```typescript
import React, { useState, useEffect, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';  // 新增 useQueryClient
// ... 现有 imports ...
import {
  Bell, Plus, Edit2, Trash2, CheckCircle, AlertCircle, TestTube, Save, X,
  Mail, Link2, MessageCircle, FileText, ChevronDown, Send, XCircle,
  LayoutTemplate, Shield, BarChart3, Archive, RefreshCw,  // 新增 RefreshCw
} from 'lucide-react';
```

### 步骤 2.5：添加缺失的 i18n 翻译（⚠️ 之前假设已存在，实际不存在）
**文件**：`frontend/src/i18n/locales/zh.ts`、`en.ts`、`ja.ts`

在 `notificationLogs` 命名空间下新增（⚠️ 注意：不是 `notificationMonitor` 命名空间）：
```typescript
retry: '重试',
retrySuccess: '已加入重试队列',
```

**验证**：搜索确认 `notificationMonitor.retry` 不存在，`notificationLogs` 命名空间下也无 `retry` 相关 key。

### 步骤 2.6：验证
- 前端编译无错误
- 失败日志行显示重试按钮
- 点击重试后状态更新为 pending/sent
- 刷新后列表正确

---

## 任务 3：实现防火墙对账功能（P0 · 核心功能）

### 步骤 3.1：新增 API 常量
**文件**：`frontend/src/lib/constants.ts`
**位置**：L42-L44（`SYSTEM_CONFIG` 附近）

在 `SYSTEM_CONFIG` 之后新增：
```typescript
  SYSTEM_STATUS: '/system/status',
  SYSTEM_CONFIG: '/system/config',
  FIREWALL_RECONCILIATION: '/system/firewall-reconciliation',  // 新增
```

### 步骤 3.2：添加防火墙对账按钮
**文件**：`frontend/src/pages/GeneralSettings.tsx`
**位置**：L210-L215（现有系统状态检查区域）

在"检查系统状态"按钮旁新增：
```typescript
const [reconciling, setReconciling] = useState(false);

const handleFirewallReconciliation = async () => {
  if (!confirm(t('generalSettings.firewallReconciliationConfirm'))) return;
  setReconciling(true);
  try {
    const res = await apiClient.post(API_ENDPOINTS.FIREWALL_RECONCILIATION);
    // 后端实际返回字段（已验证 FirewallReconciliationService.reconcile()）：
    // firewall_ip_count, db_entry_count, missing_in_db[], missing_in_firewall[],
    // created_in_db, marked_unblocked, unblocked_on_firewall, errors[]
    const result = res.data;
    toast.success(t('generalSettings.firewallReconciliationSuccess', {
      firewallCount: result.firewall_ip_count || 0,
      dbCount: result.db_entry_count || 0,
      missingDb: result.missing_in_db?.length || 0,
      missingFirewall: result.missing_in_firewall?.length || 0,
      created: result.created_in_db || 0,
      errors: result.errors?.length || 0,
    }));
  } catch (err) {
    toast.error(getErrorMessage(err));
  } finally {
    setReconciling(false);
  }
};
```

### 步骤 3.3：渲染按钮 UI
**文件**：`frontend/src/pages/GeneralSettings.tsx`
**位置**：Network SectionCard 末尾区域

在 Network 区块末尾增加：
```typescript
<div className="mt-4 pt-4 border-t border-border/50">
  <PrimaryButton
    variant="secondary"
    icon={Shield}
    label={t('generalSettings.firewallReconciliation')}
    onClick={handleFirewallReconciliation}
    loading={reconciling}
  />
  <p className="text-xs text-muted-foreground mt-2">
    {t('generalSettings.firewallReconciliationDesc')}
  </p>
</div>
```

### 步骤 3.4：添加 i18n 翻译
**文件**：`frontend/src/i18n/locales/zh.ts`、`en.ts`、`ja.ts`

在 `generalSettings` 命名空间下新增：
```typescript
firewallReconciliation: '防火墙对账',
firewallReconciliationDesc: '同步防火墙封堵记录与数据库，修复不一致状态',
firewallReconciliationConfirm: '确定要触发防火墙对账吗？此操作会同步所有数据源的封堵状态。',
firewallReconciliationSuccess: '对账完成：防火墙 {{firewallCount}} 条，数据库 {{dbCount}} 条，新增 {{created}} 条，缺失 {{missingDb}} 条，不一致 {{missingFirewall}} 条',
```

### 步骤 3.5：验证
- 前端编译无错误
- 按钮显示在 General Settings 页面
- 点击后触发对账并显示结果
- 后端日志显示对账执行

---

## 任务 4：SystemSettings 页面增强（P1 · 体验优化）

### 步骤 4.1：读取现有 SystemSettings.tsx
**文件**：`frontend/src/pages/SystemSettings.tsx`
**当前状态**：导航卡片集合，无实际 API 调用

### 步骤 4.2：实现系统配置展示
**文件**：`frontend/src/pages/SystemSettings.tsx`

改造为（⚠️ 注意：需添加必要的导入）：
```typescript
import React from 'react';
import { useQuery } from '@tanstack/react-query';  // ⚠️ 新增导入
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { Skeleton } from '@/components/Skeleton';  // ⚠️ 新增导入

// ... 现有 ConfigItem 组件或导入 ...

const SystemSettings: React.FC = () => {
  const { data: systemConfig, isLoading } = useQuery({
    queryKey: ['system-config'],
    queryFn: async () => {
      const res = await apiClient.get(API_ENDPOINTS.SYSTEM_CONFIG);
      return res.data;
    },
  });

  return (
    <div className="space-y-6">
      {/* 现有导航卡片（保留） */}
      
      {/* 新增：系统配置摘要卡片 */}
      <div className="bg-card rounded-lg border border-border p-6">
        <h2 className="text-lg font-semibold mb-4">{t('systemSettings.systemConfig')}</h2>
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <ConfigItem label={t('systemSettings.version')} value={systemConfig?.version} />
            <ConfigItem label={t('systemSettings.environment')} value={systemConfig?.environment} />
            <ConfigItem label={t('systemSettings.debugMode')} value={systemConfig?.debug ? t('systemSettings.enabled') : t('systemSettings.disabled')} />
            <ConfigItem label={t('systemSettings.logLevel')} value={systemConfig?.log_level} />
            <ConfigItem label={t('systemSettings.emailService')} value={systemConfig?.email_enabled ? t('systemSettings.enabled') : t('systemSettings.disabled')} />
            <ConfigItem label={t('systemSettings.metricsService')} value={systemConfig?.metrics_enabled ? t('systemSettings.enabled') : t('systemSettings.disabled')} />
          </div>
        )}
      </div>
    </div>
  );
};
```

### 步骤 4.3：添加 i18n 翻译
**文件**：`frontend/src/i18n/locales/zh.ts`、`en.ts`、`ja.ts`

在 `systemSettings` 命名空间下新增：
```typescript
systemConfig: '系统配置',
version: '版本',
environment: '环境',
debugMode: '调试模式',
logLevel: '日志级别',
emailService: '邮件服务',
metricsService: '监控指标',
enabled: '已启用',
disabled: '未启用',
```

### 步骤 4.4：验证
- 前端编译无错误
- System Settings 页面显示系统配置摘要
- 数据来自 `/system/config` API
- 版本、环境等信息正确显示

---

## 通用验证步骤（每个任务完成后）

1. **编译检查**：在 `frontend/` 目录执行 `npx tsc --noEmit`
2. **类型检查**：确认无 TypeScript 类型错误
3. **功能测试**：启动前端开发服务器，手动测试对应功能
4. **回归测试**：确认现有功能未受影响
5. **API 测试**：使用 curl 或 Postman 确认对应后端 API 正常响应

---

## 风险提示

| 任务 | 风险 | 缓解措施 |
|------|------|---------|
| 任务1 | `compliance_confirm_threshold` 字段类型需为 int | ✅ 已验证后端 `ComplianceConfigResponse` 中该字段为 `int` 类型 |
| 任务2 | 重试失败通知可能触发业务告警 | 仅对 `status === 'failed'` 的日志显示重试按钮 |
| 任务2 | `useNotificationLogs` 返回的 hook 需正确刷新 | ✅ 使用 `queryClient.invalidateQueries` 而非 `refetch()` |
| 任务3 | 防火墙对账为写操作，可能改变终端状态 | 增加确认弹窗，展示对账结果摘要 |
| 任务3 | 响应字段名易出错 | ✅ 已验证后端返回字段：firewall_ip_count, db_entry_count, missing_in_db 等 |
| 任务4 | `/system/config` API 需登录态 | ✅ 已确认该 API 要求 `get_current_user` 依赖 |
| 任务4 | 缺少必要导入导致编译失败 | ✅ 已补充 `useQuery`、`Skeleton` 导入 |
| 任务5 | 无风险 | — |

---

## 附录：v1.0 → v1.1 修正记录

| 修正项 | v1.0 错误 | v1.1 修正 | 修正依据 |
|--------|----------|----------|---------|
| 任务2 i18n | 声称 `notificationMonitor.retry` 已存在 | 新增 `notificationLogs.retry` 翻译 | Grep 确认不存在该 key |
| 任务2 刷新方法 | 使用 `refetch()` | 改用 `queryClient.invalidateQueries` | `useNotificationLogs` hook 返回 `useQuery` 结果，需通过 queryClient 刷新 |
| 任务3 响应字段 | 使用 `matched_count`/`mismatched_count` | 改用 `firewall_ip_count`/`db_entry_count` 等 | 阅读 `firewall_reconciliation_service.py` 确认实际返回字段 |
| 任务4 导入 | 缺少必要导入 | 补充 `useQuery`、`Skeleton` 导入 | 代码片段中引用但未导入 |
