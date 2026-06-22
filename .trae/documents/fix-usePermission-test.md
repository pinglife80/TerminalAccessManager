# 修复 usePermission 测试 React 上下文缺失

> 文档版本：v3.3.0 | 更新日期：2026-06-17

## 问题

`usePermission.test.ts` 直接调用 `usePermission()` hook，但该 hook 内部调用 `useAuthStore()` 使用 Zustand React 绑定，需要 React 渲染上下文。直接调用导致 `useRef` 为 null。

## 修复方案

使用 `@testing-library/react` 的 `renderHook` 包装 hook 调用。

项目已有 `@testing-library/react@^15.0.0`，其内置 `renderHook`，不需要额外安装 `@vitest/react`。

### 修改文件

`frontend/src/hooks/__tests__/usePermission.test.ts`

### 修改内容

1. 添加 `import { renderHook } from '@testing-library/react'`
2. 所有 `const { xxx } = usePermission()` 改为 `const { result } = renderHook(() => usePermission())`
3. 所有 `xxx(...)` 改为 `result.current.xxx(...)`

共 11 处 hook 调用需要修改。

## 实施步骤

1. 编辑测试文件
2. 提交并推送
