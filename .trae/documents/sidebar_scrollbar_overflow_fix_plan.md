# 侧边栏滚动条溢出修复方案

## 问题分析

### 现象
点击"系统设置"展开子菜单后，左侧导航栏出现下滑条，但下滑条溢出到了导航栏外部（跨越了侧边栏边界）。

### 根因
**根因定位：** [Sidebar.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/Sidebar.tsx#L201-L204) 第201行的 `<aside>` 元素缺少 `overflow-hidden` 约束。

#### 详细分析

当前 `Sidebar.tsx` 布局结构：
```
<aside className="h-full flex flex-col relative">  ← 缺少 overflow-hidden
  <div>Logo/Brand</div>           ← 固定高度头部
  <button>折叠按钮(absolute定位)</button>
  <nav className="flex-1 overflow-y-auto">  ← 导航区域（有溢出滚动）
    <ul>菜单列表</ul>
  </nav>
  <div>用户信息/底部</div>         ← 固定高度底部
</aside>
```

**问题链路：**
1. `aside` 设置了 `h-full`（即 `h-screen`），但 **没有** `overflow-hidden`
2. `nav` 设置了 `flex-1 overflow-y-auto`，当子菜单展开后内容超出可用空间
3. 由于 `aside` 没有 `overflow-hidden`，浏览器无法将滚动条限制在侧边栏内部
4. 折叠按钮使用 `absolute -right-3` 定位，右侧 `3px` 超出了 `aside` 边界
5. 当滚动条出现时，它被渲染在错误的层级（body 或父容器上），看起来"溢出"了侧边栏

**对比正确的 `Layout.tsx` 主内容区（第25行）：**
```jsx
<div className="flex-1 flex flex-col overflow-hidden">  ← 有 overflow-hidden
```

## 修复方案

### 变更文件
- **文件**: `frontend/src/components/Sidebar.tsx`
- **位置**: 第201行 `<aside>` 元素的 className

### 修改内容

将：
```jsx
className={`${collapsed ? 'w-[4.5rem]' : 'w-64'} bg-gray-900 text-white flex flex-col h-full transition-all duration-300 ease-in-out relative`}
```

改为：
```jsx
className={`${collapsed ? 'w-[4.5rem]' : 'w-64'} bg-gray-900 text-white flex flex-col h-full overflow-hidden transition-all duration-300 ease-in-out relative`}
```

**仅增加 `overflow-hidden` 一个类名。**

### 修复原理

添加 `overflow-hidden` 后的布局行为：
1. `aside` 获得固定高度 (`h-full`) 和溢出裁剪 (`overflow-hidden`)
2. 内部 flex 布局正确分配空间：
   - 头部 Logo 区：`flex-shrink`（自然高度）
   - 导航 `<nav>`：`flex-1`（填充剩余空间）+ `overflow-y-auto`（内部滚动）
   - 底部用户信息：`flex-shrink`（自然高度）
3. 滚动条被限制在 `<nav>` 元素内部，不再溢出
4. 折叠按钮的 `absolute -right-3` 超出部分被 `overflow-hidden` 裁剪

### 风险评估
- **风险等级**: 极低
- **影响范围**: 仅影响侧边栏的 CSS 溢出行为
- **回归风险**: 无。此修改仅添加一个 CSS 类，不会改变任何功能逻辑
- **兼容性**: `overflow-hidden` 是标准 CSS 属性，所有现代浏览器均支持

### 验证方式
1. TypeScript 编译检查通过
2. 页面加载后点击"系统设置"展开/收起子菜单
3. 确认滚动条出现在导航区域内部
4. 确认侧边栏边界无溢出内容
5. 确认折叠按钮的交互正常
