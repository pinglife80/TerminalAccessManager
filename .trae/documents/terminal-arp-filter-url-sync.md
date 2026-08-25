# 终端页筛选状态与 URL 双向同步（Block Pending Retry 跳转一致性优化）

> 文档版本：v1.0  更新日期：2026-08-24

## 1. 摘要（Summary）

「Block Pending Retry」统计标签跳转到终端管理页这一交互**本身符合业务逻辑**（该类为 `non_compliant + unblocked` 的终端，无黑名单记录，只能在终端页展示）。本次优化针对其附带的一致性缺陷：

1. 端页的「仅启用 ARP 数据源」筛选（`arp_enabled_only`）通过 URL 注入后**无 UI 控件可关闭、无法重置**，导致跳转后该筛选被"锁定"。
2. 筛选状态与 URL **单向**（仅在初始化时读取），用户在终端页内修改/重置筛选后，URL 不随之更新，刷新或重复跳转时会出现状态脱节。

目标：让跳转携带的 `status` / `compliance_status` / `arp_enabled_only` 三个参数在「进入—修改—重置—刷新—再次跳转」全链路保持一致。

## 2. 现状分析（Current State Analysis）

- 黑名单页卡片跳转：[Blacklist.tsx#L99-L101](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L99-L101)
  ```ts
  const handlePendingRetryBlock = () => {
    navigate('/terminals?compliance_status=non_compliant&status=unblocked&arp_enabled_only=1');
  };
  ```

- 终端页当前实现（[Terminals.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx)）：
  - L82：`const [searchParams] = useSearchParams();`（只读，无 `setSearchParams`）。
  - L84-L85：`filterStatus`、`filterCompliance` 用 lazy `useState` 从 URL 初始化，**有 setter**。
  - L88：`const [filterArpEnabledOnly] = useState<boolean>(() => searchParams.get('arp_enabled_only') === '1');` —— **无 setter**。
  - L136：`arp_enabled_only: filterArpEnabledOnly || undefined` 已传入查询；hook 侧 `TerminalSearchParams.arp_enabled_only?: boolean`（useTerminalData.ts#L135）已存在，**无需改动 hook**。
  - L400-L410：`handleReset` 重置了 status/compliance/source/firewallTag/日期，但**未重置 arp_enabled_only**。
  - L532-L607：筛选区有 status/compliance/source/firewallTag 四个下拉，**无 arp_enabled_only 控件**。

结论：核心缺陷集中在 `filterArpEnabledOnly` 只读、无 UI、无 reset，以及整体 URL 单向同步。

## 3. 拟议改动（Proposed Changes）

### 3.1 终端页 URL 双向同步 + arp 筛选可切换 —— `frontend/src/pages/Terminals.tsx`

**改动点 1：引入 `setSearchParams` 与 `useEffect`**
- L1：`import React, { useState, useEffect, useMemo } from 'react';`（补充 `useEffect`）。
- L82：`const [searchParams, setSearchParams] = useSearchParams();`（补 `setSearchParams`）。

**改动点 2：`filterArpEnabledOnly` 补 setter**
- L88：`const [filterArpEnabledOnly, setFilterArpEnabledOnly] = useState<boolean>(() => searchParams.get('arp_enabled_only') === '1');`

**改动点 3：新增 URL 同步 effect**（放在状态声明区之后，`useState` 块附近，约 L96 `autoRefresh` 之后）
```tsx
// 将跳转相关的三个筛选状态回写 URL，保证刷新/重复跳转不脱节
useEffect(() => {
  const params = new URLSearchParams();
  if (filterStatus !== 'all') params.set('status', filterStatus);
  if (filterCompliance !== 'all') params.set('compliance_status', filterCompliance);
  if (filterArpEnabledOnly) params.set('arp_enabled_only', '1');
  setSearchParams(params, { replace: true });
}, [filterStatus, filterCompliance, filterArpEnabledOnly, setSearchParams]);
```
- 用 `{ replace: true }` 避免每次筛选产生浏览器历史记录。
- 仅同步跳转涉及的三个参数；`source_tag`/`firewall_tag`/日期/搜索为终端页本地临时筛选，不纳入本次范围（见 §5 假设）。

**改动点 4：`handleReset` 增加 arp 重置**
- 在 L403-L404 附近新增：`setFilterArpEnabledOnly(false);`
- URL 清除交由改动点 3 的 effect 自动完成（状态回到默认值 → 生成空 params → replace）。

**改动点 5：筛选区新增「仅启用 ARP 源」控件**（在 L568-L587 Source Filter 之后、L589 Firewall Filter 之前插入）
```tsx
{/* Enabled-ARP-Only Filter */}
<label className="flex items-center gap-2 bg-background rounded-xl px-3 py-1.5 cursor-pointer">
  <Server className="h-4 w-4 text-muted-foreground flex-shrink-0" />
  <span className="text-sm text-muted-foreground font-medium">{t('terminal.onlyEnabledArp')}</span>
  <input
    type="checkbox"
    checked={filterArpEnabledOnly}
    onChange={(e) => { setFilterArpEnabledOnly(e.target.checked); setCurrentPage(1); }}
    className="h-4 w-4 cursor-pointer"
  />
</label>
```
- 复用现有胶囊式筛选样式与 `Server` 图标（已 import），不新增组件。

### 3.2 新增 i18n 文案 —— `frontend/src/i18n/locales/{zh,en,ja}.ts`

在 `terminal` 命名空间、`allSource` 附近各新增一条：
- zh：`onlyEnabledArp: '仅启用 ARP 源',`
- en：`onlyEnabledArp: 'Enabled ARP only',`
- ja：`onlyEnabledArp: '有効な ARP のみ',`

## 4. 假设与决策（Assumptions & Decisions）

1. **跳转本身不改动**：维持跳转到终端页的交互与 URL 参数（口径已正确）。
2. **URL 同步范围收敛**：仅同步 `status` / `compliance_status` / `arp_enabled_only` 三个由黑名单跳转携带的参数；`source_tag`、`firewall_tag`、日期、搜索属于终端页本地临时筛选，高频/易变（搜索为 debounce），不纳入本次 URL 持久化，避免范围蔓延。
3. **初始化行为保持兼容**：首次挂载时读取 URL 的逻辑不变，仅新增回写；因回写内容与当前 URL 一致，无视觉抖动。
4. **仅前端改动**：后端统计口径、API 参数无变化，无需迁移或后端重建。

## 5. 验证步骤（Verification）

1. 前端构建：`./manage.sh update`（或仅前端热更新），确认无 TS 编译错误。
2. 功能验证：
   - 在黑名单页点击「Block Pending Retry」卡片 → 跳转终端页，地址含 `compliance_status=non_compliant&status=unblocked&arp_enabled_only=1`，筛选区 status=unblocked、compliance=non_compliant、「仅启用 ARP 源」勾选。
   - 取消勾选「仅启用 ARP 源」→ URL 中 `arp_enabled_only` 消失，列表恢复为全部终端，可再次勾选还原。
   - 修改 status/compliance → URL 实时同步对应参数。
   - 点击「重置」→ 筛选全部归 `all`，`arp_enabled_only` 取消勾选，URL query 清空。
   - 刷新页面 → 筛选状态与 URL 一致（不脱节）。
3. 口径回归：确认从黑名单跳转后终端页筛选结果数 == `pending_retry_block` 卡片数字（当前为 0）。