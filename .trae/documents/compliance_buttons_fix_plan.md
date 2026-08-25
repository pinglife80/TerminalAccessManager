# 合规基线管理 - 三个操作按钮问题分析与修复计划

> 创建日期：2026-07-16
> 涉及组件：数据源管理 → 合规基线管理 Tab

---

## 一、问题总览

| 按钮 | 现象 | 根因 | 行为是否合理 |
|------|------|------|------------|
| Run Compliance Check | 返回 "0 total, 0 compliant, 0 bypass, 0 non-compliant" | 前端硬编码 `force: false`，只检查 unknown 终端，但数据库无 unknown 终端 | 合理（设计行为） |
| Auto Block | 弹出浏览器原生 confirm；确认后返回 "0 non-compliant, 0 blocked, 0 skipped" | UI 使用 `window.confirm`；146条 non_compliant 终端全部已封锁 | 合理（行为正确） |
| Auto Unblock | 返回 "146 auto-blocked, 0 unblocked, 146 skipped" | 146条被封锁终端在白名单/IP-Guard 中不匹配 | 合理（行为正确） |

**核心结论**：三个按钮的后端逻辑都正确，问题在于前端缺少操作选项和提示信息不够清晰。

---

## 二、根因分析

### 2.1 Run Compliance Check 返回 0

**前端硬编码** `force: false`（[ComplianceBaselinesTab.tsx:312](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/ComplianceBaselinesTab.tsx#L312)）：

```javascript
const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_CHECK, {
  arp_source_tag: selectedTag || undefined,
  force: false,  // ← 硬编码
});
```

**后端逻辑**（[data_sources.py:532-533](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/data_sources.py#L532-L533)）：

```python
if not request.force:
    conditions.append(Terminal.compliance_status == "unknown")
```

当 `force=false` 时，只查询 `compliance_status == "unknown"` 的终端。但数据库中 **没有 unknown 状态的终端**：

| compliance_status | 数量 |
|-------------------|------|
| bypass | 510 |
| compliant | 313 |
| non_compliant | 146 |
| unknown | **0** |

**原因**：ARP 采集服务在采集到新终端时会**立即自动执行合规检查**（[arp_collector_service.py:330-353](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L330-L353)），新终端创建后马上从 unknown 变为 bypass/compliant/non_compliant。定时任务（300秒间隔）也会处理 unknown 终端。

### 2.2 Auto Block 返回 0

**后端逻辑**（[compliance_service.py:376-384](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L376-L384)）：

```python
stmt = (
    select(Terminal)
    .where(
        (Terminal.source_tag == arp_source_tag) &
        (Terminal.compliance_status == "non_compliant") &
        (Terminal.status != "blocked")  # ← 排除已封锁的终端
    )
)
```

数据库实际情况：

| 条件 | 数量 |
|------|------|
| compliance_status = non_compliant | 146 |
| 其中 status = blocked | 146 |
| 其中 status != blocked（可操作） | **0** |

所有 146 条 non_compliant 终端都已经被封锁，Auto Block 无需重复封锁。

### 2.3 Auto Unblock 返回 146 skipped

**后端逻辑**（[compliance_service.py:637-644](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L637-L644)）：

```python
for (ip_addr, mac_addr), entries in entry_groups.items():
    wl_match = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)
    ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

    if not (wl_match or ig_match):
        skipped += len(entries)  # ← 不合规，跳过
        continue
```

146 条被封锁的终端在白名单和 IP-Guard 中都不匹配（仍然是 non_compliant），所以全部跳过。

### 2.4 Auto Block 浏览器原生 confirm 问题

前端代码 [ComplianceBaselinesTab.tsx:329](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/ComplianceBaselinesTab.tsx#L329)：

```javascript
if (!window.confirm(t('compliance.confirmAutoBlock'))) return;
```

项目已有自定义 [Modal 组件](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/Modal.tsx)，其他页面（如 DataSourcesTab）均使用 Modal 做确认操作。

---

## 三、修复方案

### 3.1 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `frontend/src/components/datasources/ComplianceBaselinesTab.tsx` | 添加 force 复选框；用 Modal 替换 window.confirm；优化 toast 提示 |
| `backend/app/schemas/data_source.py` | AutoBlockResult 和 AutoUnblockResult 添加 message 字段 |
| `backend/app/services/compliance_service.py` | auto_unblock_compliant 方法添加 message 返回 |
| `frontend/src/i18n/locales/zh.ts` | 添加中文翻译 |
| `frontend/src/i18n/locales/en.ts` | 添加英文翻译 |
| `frontend/src/i18n/locales/ja.ts` | 添加日文翻译 |

### 3.2 具体修改

#### 文件1: `backend/app/schemas/data_source.py`

**修改A - AutoBlockResult 添加 message**（第117-124行）：

```python
class AutoBlockResult(BaseModel):
    """Result of auto-blocking operation"""
    total_non_compliant: int = 0
    blocked: int = 0
    skipped: int = 0
    errors: list[str] = []
    details: list[dict[str, Any]] | None = None
    message: str | None = None  # 新增
```

**修改B - AutoUnblockResult 添加 message**（第126-132行）：

```python
class AutoUnblockResult(BaseModel):
    """Result of auto-unblocking operation"""
    total_auto_blocked: int = 0
    unblocked: int = 0
    skipped: int = 0
    errors: list[str] = []
    details: list[dict[str, Any]] | None = None
    message: str | None = None  # 新增
```

#### 文件2: `backend/app/services/compliance_service.py`

**修改 - auto_unblock_compliant 返回 message**（第761-767行）：

```python
return AutoUnblockResult(
    total_auto_blocked=len(auto_blocked_entries),
    unblocked=unblocked,
    skipped=skipped,
    errors=errors,
    details=details if len(details) <= 100 else None,
    message="All blocked terminals are still non-compliant" if unblocked == 0 and skipped > 0 else None,
)
```

#### 文件3: `frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

**修改A - 添加 state**（第302行后）：

```javascript
const [forceCheck, setForceCheck] = useState(false);
const [showAutoBlockModal, setShowAutoBlockModal] = useState(false);
```

**修改B - handleComplianceCheck 使用 forceCheck**（第311-312行）：

```javascript
const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_CHECK, {
  arp_source_tag: selectedTag || undefined,
  force: forceCheck,
});
```

**修改C - handleAutoBlock 拆分为两步**（第327-349行）：

```javascript
// 第一步：打开 Modal
const handleAutoBlockClick = () => {
  if (!selectedTag) { toast.warning(t('compliance.selectSourceTag')); return; }
  setShowAutoBlockModal(true);
};

// 第二步：确认后执行
const handleAutoBlockConfirm = async () => {
  setShowAutoBlockModal(false);
  setAutoBlockLoading(true);
  try {
    const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_AUTO_BLOCK, {
      arp_source_tag: selectedTag,
      block_time: '30d',
      dry_run: false,
    });
    const r = response.data;
    toast.success(t('compliance.autoBlockComplete', {
      total: r.total_non_compliant, blocked: r.blocked, skipped: r.skipped,
    }));
    if (r.total_non_compliant === 0) {
      toast.info(t('compliance.autoBlockNoAction'));
    }
    if (r.errors?.length) toast.warning(t('compliance.partialErrors', { count: r.errors.length }));
    queryClient.invalidateQueries({ queryKey: ['terminals'] });
    queryClient.invalidateQueries({ queryKey: ['blacklist'] });
  } catch (err) {
    toast.error(getErrorMessage(err, t('compliance.autoBlockFailed')));
  } finally {
    setAutoBlockLoading(false);
  }
};
```

**修改D - handleAutoUnblock 优化提示**（第351-367行）：

```javascript
const handleAutoUnblock = async () => {
  setAutoUnblockLoading(true);
  try {
    const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_AUTO_UNBLOCK);
    const r = response.data;
    toast.success(t('compliance.autoUnblockComplete', {
      total: r.total_auto_blocked, unblocked: r.unblocked, skipped: r.skipped,
    }));
    if (r.unblocked === 0 && r.skipped > 0) {
      toast.info(t('compliance.autoUnblockNoAction'));
    }
    if (r.errors?.length) toast.warning(t('compliance.partialErrors', { count: r.errors.length }));
    queryClient.invalidateQueries({ queryKey: ['terminals'] });
    queryClient.invalidateQueries({ queryKey: ['blacklist'] });
  } catch (err) {
    toast.error(getErrorMessage(err, t('compliance.autoUnblockFailed')));
  } finally {
    setAutoUnblockLoading(false);
  }
};
```

**修改E - 添加 Force Re-check 复选框**（第387行前，Run Compliance Check 按钮之前）：

```jsx
<label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
  <input
    type="checkbox"
    checked={forceCheck}
    onChange={(e) => setForceCheck(e.target.checked)}
    className="rounded border-input"
  />
  {t('compliance.forceRecheck')}
</label>
```

**修改F - Auto Block 按钮 onClick 改为打开 Modal**：

```jsx
<PrimaryButton
  icon={Ban}
  label={t('compliance.autoBlock')}
  onClick={handleAutoBlockClick}
  loading={autoBlockLoading}
  variant="danger"
/>
```

**修改G - 添加 Auto Block 确认 Modal**（按钮区域之后）：

```jsx
<Modal isOpen={showAutoBlockModal} onClose={() => setShowAutoBlockModal(false)} title={t('compliance.confirmAutoBlock')} size="sm">
  <div className="space-y-4">
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
        <Ban className="h-5 w-5 text-red-600" />
      </div>
      <p className="text-sm text-muted-foreground">{t('compliance.autoBlockWarning')}</p>
    </div>
    <div className="flex justify-end gap-2">
      <PrimaryButton label={t('common.cancel')} onClick={() => setShowAutoBlockModal(false)} variant="secondary" />
      <PrimaryButton label={t('common.confirm')} onClick={handleAutoBlockConfirm} variant="danger" loading={autoBlockLoading} />
    </div>
  </div>
</Modal>
```

#### 文件4-6: i18n 翻译

**zh.ts**（compliance 区块末尾添加）：

```javascript
forceRecheck: '强制重新检查',
autoBlockWarning: '将对不合规终端执行自动封禁（30天）。是否继续？',
autoBlockNoAction: '所有不合规终端已封锁，无需重复操作',
autoUnblockNoAction: '被封锁终端均未变为合规状态，暂无需要解封的终端',
```

**en.ts**：

```javascript
forceRecheck: 'Force Re-check',
autoBlockWarning: 'This will auto-block non-compliant terminals for 30 days. Continue?',
autoBlockNoAction: 'All non-compliant terminals are already blocked',
autoUnblockNoAction: 'No blocked terminals have become compliant yet',
```

**ja.ts**：

```javascript
forceRecheck: '強制再チェック',
autoBlockWarning: '非準拠の端末を30日間自動ブロックします。続行しますか？',
autoBlockNoAction: 'すべての非準拠端末は既にブロックされています',
autoUnblockNoAction: 'ブロックされた端末はまだ準拠状態になっていません',
```

---

## 四、验证步骤

1. `./manage.sh update` 重新构建

2. **Run Compliance Check**：
   - 不勾选 Force Re-check → 点击 → 应返回 0 total（正常，因为没有 unknown 终端）
   - 勾选 Force Re-check → 选择 ARP 源 → 点击 → 应返回实际检查数量

3. **Auto Block**：
   - 未选 ARP 源 → 点击 → 提示选择数据源
   - 选择 ARP 源 → 点击 → 弹出自定义 Modal（非浏览器原生）
   - 确认 → toast 显示 "0 non-compliant, 0 blocked, 0 skipped"
   - 紧接着 toast.info 提示 "所有不合规终端已封锁，无需重复操作"

4. **Auto Unblock**：
   - 点击 → toast 显示 "146 auto-blocked, 0 unblocked, 146 skipped"
   - 紧接着 toast.info 提示 "被封锁终端均未变为合规状态，暂无需要解封的终端"
