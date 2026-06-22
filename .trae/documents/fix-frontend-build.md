# 修复 CI frontend-build 失败计划

## 当前状态分析

### GitHub 分析是错误的
GitHub Job 81821683659 的分析声称 `Cannot find module '@/lib/api'` 和 `'@/lib/utils'`，建议创建这两个文件。
**这是错误的** — 两个文件都已存在且内容完整：
- [api.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/lib/api.ts) — axios 客户端 + token 刷新机制（121行）
- [utils.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/lib/utils.ts) — 16个工具函数

路径别名配置也正确：
- [tsconfig.json](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/tsconfig.json) — `baseUrl: "."`, `paths: { "@/*": ["./src/*"] }`
- [vite.config.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/vite.config.ts) — `alias: { '@': path.resolve(__dirname, './src') }`

### 真正的 TypeScript 编译错误

**问题：`api.ts` 中 `originalRequest._retry` 属性访问**

[api.ts:54](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/lib/api.ts#L54)、[api.ts:60](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/lib/api.ts#L60)、[api.ts:69](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/lib/api.ts#L69) 使用了 `originalRequest._retry`，但 `InternalAxiosRequestConfig` 类型上不存在 `_retry` 属性。

在 `tsconfig.json` 的 `strict: true` 模式下，这会导致编译错误：
```
error TS2339: Property '_retry' does not exist on type 'InternalAxiosRequestConfig<any>'.
```

这是 axios 拦截器中防循环重试的标准模式，但 TypeScript 严格模式不允许访问未定义的属性。

### 构建流程
- `package.json` 的 `build` 脚本：`"tsc && vite build"`
- Docker 构建执行 `npm run build`，先运行 `tsc` 类型检查，再 `vite build` 打包
- 任何 TS 编译错误都会导致 `tsc` 失败，进而 Docker 构建失败

## 修复方案

### 修改 1：添加 axios 模块类型扩展

**文件**：`frontend/src/types/axios.d.ts`（新建）

**内容**：为 axios 的 `InternalAxiosRequestConfig` 接口添加 `_retry` 可选属性声明。

```typescript
import 'axios';

declare module 'axios' {
  export interface InternalAxiosRequestConfig {
    _retry?: boolean;
  }
}
```

**原因**：这是 TypeScript 中扩展第三方库类型的标准做法，不会影响运行时行为，仅在编译时提供类型信息。`_retry` 是 axios 拦截器中广泛使用的约定属性，用于防止 token 刷新的无限循环。

**对业务功能的影响**：无。纯类型声明，不影响运行时逻辑。

### 修改 2：验证编译通过

执行 `cd frontend && npx tsc --noEmit` 确认无其他 TS 错误。

## 不需要做的事

- **不需要创建 `lib/api.ts` 和 `lib/utils.ts`**：这两个文件已存在
- **不需要修改 `tsconfig.json`**：当前配置正确
- **不需要修改 `vite.config.ts`**：路径别名配置正确
- **不需要修改 `api.ts` 源码**：`_retry` 的使用逻辑正确，只需补充类型声明

## 验证步骤

1. 创建 `frontend/src/types/axios.d.ts`
2. 在本地运行 `cd frontend && npx tsc --noEmit` 确认无错误
3. 提交并推送到 develop 分支
4. 等待 CI 重新运行，确认 frontend-build job 通过
