# 终端管理和黑名单管理筛选修复计划

> 文档版本：v1.0 | 创建日期：2026-07-14
>
> **适用版本**：v3.6.11+
> **分支策略**：简化版 Git Flow

---

## 1. 问题分析

### 问题1：终端管理中的 Source 筛选下拉选项包含 AF 类型

**问题描述**：终端管理页面的 Source 筛选下拉选项中显示了所有数据源类型的标签，包括 Sangfor 防火墙（AF）类型的数据源。但终端数据只来源于 ARP 采集（`arp_ssh` / `arp_api`），不应该显示防火墙类型的数据源标签。

**代码位置**：
- `frontend/src/pages/Terminals.tsx` 第 239-243 行：`sourceTagOptions` 的生成逻辑未过滤数据源类型

```tsx
const sourceTagOptions = useMemo(() => {
  const tags = new Set<string>();
  dataSources?.forEach((ds) => { if (ds.tag) tags.add(ds.tag); });
  return Array.from(tags).sort();
}, [dataSources]);
```

**影响**：用户可以选择 AF 类型的数据源作为筛选条件，但实际上没有终端数据属于这些数据源，导致筛选结果为空，造成用户困惑。

### 问题2：黑名单管理不需要 Active 和 Unblocked 状态分类

**问题描述**：黑名单管理页面目前提供了三个标签页：`active`（活跃）、`unblocked`（已解封）、`all`（全部）。用户认为只需要显示当前真实被封锁的黑名单数据即可，解封的追溯可以通过审计日志查询。

**代码位置**：
- `frontend/src/pages/Blacklist.tsx` 第 24 行：定义了 `BlacklistTab` 类型
- 第 40 行：`activeTab` 状态，默认 `'active'`
- 第 46 行：根据 `activeTab` 决定 `statusParam`
- 第 144-148 行：标签页配置
- 第 170-187 行：标签页导航 UI

**影响**：多余的标签页增加了页面复杂度，且已解封数据的追溯应通过审计日志完成。

---

## 2. 修复方案

### 2.1 修复问题1：Source 筛选只显示 ARP 类型数据源

**修改文件**：`frontend/src/pages/Terminals.tsx`

**修改内容**：在生成 `sourceTagOptions` 时，只包含 `arp_ssh` 和 `arp_api` 类型的数据源标签。

```tsx
const sourceTagOptions = useMemo(() => {
  const tags = new Set<string>();
  dataSources?.forEach((ds) => {
    if (ds.tag && (ds.type === 'arp_ssh' || ds.type === 'arp_api')) {
      tags.add(ds.tag);
    }
  });
  return Array.from(tags).sort();
}, [dataSources]);
```

### 2.2 修复问题2：黑名单管理移除状态分类标签页

**修改文件**：`frontend/src/pages/Blacklist.tsx`

**修改内容**：
1. 删除 `BlacklistTab` 类型定义
2. 删除 `activeTab` 状态
3. 删除标签页配置和导航 UI
4. 固定使用 `status='active'` 参数，只显示活跃的黑名单记录

**具体修改点**：
- 第 24 行：删除 `type BlacklistTab = 'active' | 'unblocked' | 'all';`
- 第 40 行：删除 `const [activeTab, setActiveTab] = useState<BlacklistTab>('active');`
- 第 46 行：将 `statusParam` 固定为 `'active'`
- 第 75-78 行：删除 `handleTabChange` 函数
- 第 142-148 行：删除 `tabs` 配置和 `isExpired` 函数中与标签页相关的逻辑
- 第 170-187 行：删除标签页导航 UI
- 第 308、317、326、335 行：移除 `activeTab === 'active'` 的条件判断

---

## 3. 实施步骤

### Step 1：修复终端管理 Source 筛选

```bash
# 修改 Terminals.tsx
git add frontend/src/pages/Terminals.tsx
git commit -m "fix(terminal): filter source dropdown to ARP types only

- Source filter dropdown now only shows arp_ssh and arp_api data source tags
- Sangfor/AF type sources are excluded from the source filter"
```

### Step 2：修复黑名单管理状态分类

```bash
# 修改 Blacklist.tsx
git add frontend/src/pages/Blacklist.tsx
git commit -m "fix(blacklist): remove status tabs, show only active records

- Removed active/unblocked/all tab navigation
- Blacklist page now only shows currently blocked entries
- Unblocked history should be queried via audit logs"
```

### Step 3：推送并创建 PR

```bash
git push origin develop
```

---

## 4. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Source 筛选逻辑错误 | 低 | 中 | 验证过滤后只显示 ARP 类型数据源 |
| 黑名单数据显示异常 | 低 | 中 | 验证只显示活跃记录，解封操作正常 |
| 翻译键引用错误 | 低 | 低 | 检查 i18n 翻译文件引用 |

---

## 5. 验证方案

```bash
# 验证服务健康
./manage.sh health

# 验证前端构建
cd frontend && npm run build

# 手动验证：
# 1. 终端管理页面 - Source 下拉只显示 ARP 数据源，不显示 AF/Sangfor
# 2. 黑名单管理页面 - 无标签页切换，只显示活跃的封锁记录
# 3. 解封操作正常工作
```

---

## 6. 参考文档

- [终端管理页面](frontend/src/pages/Terminals.tsx)
- [黑名单管理页面](frontend/src/pages/Blacklist.tsx)

