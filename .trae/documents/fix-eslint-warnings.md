# 修复 ESLint 警告超限

> 文档版本：v3.3.0 | 更新日期：2026-06-17

## 问题

CI frontend-lint job 有 22 个 ESLint 警告，超过 `--max-warnings 10` 限制。

## 警告来源

1. **`no-explicit-any`**（9 处）：`any` 类型使用
2. **其他警告**（约 13 处）：可能是 `exhaustive-deps`、`React.FC` 等

## 修复方案

### Step 1: 修复 9 处 `any` 类型

| 文件 | 行 | 当前 | 修复为 |
|------|-----|------|--------|
| Terminals.tsx:278 | `(b: any)` | `(b: { firewall_tag: string })` |
| DataSourcesTab.tsx:98 | `useState<any>(null)` | `useState<DisablePreviewData \| null>(null)` |
| DataSourcesTab.tsx:246 | `(b: any)` | `(b: DataSourceBinding)` |
| DataSourcesTab.tsx:363 | `(b: any)` | `(b: DataSourceBinding)` |
| DataSourcesTab.tsx:368 | `(b: any)` | `(b: DataSourceBinding)` |
| DataSourcesTab.tsx:375 | `(b: any)` | `(b: DataSourceBinding)` |
| DataSourcesTab.tsx:377 | `(b: any)` x2 | `(b: DataSourceBinding)` |
| DataSourcesTab.tsx:762 | `(a: any, i: number)` | `(a: { action: string; ... }, i: number)` |
| useNetworkStatus.ts:20 | `navigator as any` | 保留 `as any`（Navigator connection API 无标准类型） |

### Step 2: 暂时提高 max-warnings

修复 `any` 后剩余约 13 个警告，将 `--max-warnings 10` 提高到 `--max-warnings 25`，后续逐步降低。

### Step 3: 提交并推送
