# Auto Block / Auto Unblock 按钮问题分析与修复计划

> 创建日期：2026-07-16

***

## 一、问题分析

### 1.1 Auto Block 按钮问题

**问题A - 浏览器原生 confirm 对话框**

前端代码 [ComplianceBaselinesTab.tsx:329](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/ComplianceBaselinesTab.tsx#L329)：

```javascript
if (!window.confirm(t('compliance.confirmAutoBlock'))) return;
```

使用了 `window.confirm()` 浏览器原生对话框，与项目的 UI 设计不一致。项目已有自定义 [Modal 组件](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/Modal.tsx)，其他页面（如 DataSourcesTab）都使用 Modal 做确认操作。

**问题B - 返回 "0 non-compliant, 0 blocked, 0 skipped"**

这是**合理的行为**，但提示信息让用户困惑。

后端逻辑 [compliance\_service.py:376-384](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L376-L384)：

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

| 条件                                  | 数量    |
| ----------------------------------- | ----- |
| compliance\_status = non\_compliant | 146   |
| 其中 status = blocked                 | 146   |
| 其中 status != blocked                | **0** |

所有 146 条 non\_compliant 终端都已经被封锁了，所以 Auto Block 查询到 0 条需要新封锁的终端。

**问题C - message 字段丢失**

后端返回了 `message="No non-compliant entries found"`（[第401行](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L401)），但 `AutoBlockResult` schema 中没有 `message` 字段，前端也没有使用。

### 1.2 Auto Unblock 按钮问题

**问题 - 返回 "146 auto-blocked, 0 unblocked, 146 skipped"**

这也是**合理的行为**，但提示信息让用户困惑。

后端逻辑 [compliance\_service.py:637-644](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L637-L644)：

```python
for (ip_addr, mac_addr), entries in entry_groups.items():
    # Check if now compliant
    wl_match = self._match_whitelist_in_memory(whitelist_data, ip_addr, mac_addr)
    ig_match = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr)

    if not (wl_match or ig_match):
        skipped += len(entries)  # ← 不合规，跳过
        continue
```

146 条被封锁的终端在白名单和 IP-Guard 中都不匹配（仍然是 non\_compliant），所以全部跳过，没有被解封。这是正确的行为——只有终端变为合规后才会解封。

### 1.3 问题总结

| 按钮           | 行为是否合理     | UI 是否有问题          | 提示是否清晰      |
| ------------ | ---------- | ----------------- | ----------- |
| Auto Block   | 合理（0条需要封锁） | 浏览器原生 confirm 对话框 | 不清晰（没有说明原因） |
| Auto Unblock | 合理（0条需要解封） | 无                 | 不清晰（没有说明原因） |

***

## 二、修复方案

### 2.1 需要修改的文件

| 文件                                                               | 修改内容                                              |
| ---------------------------------------------------------------- | ------------------------------------------------- |
| `frontend/src/components/datasources/ComplianceBaselinesTab.tsx` | 用 Modal 替换 window\.confirm；优化 toast 提示            |
| `backend/app/schemas/data_source.py`                             | AutoBlockResult 和 AutoUnblockResult 添加 message 字段 |
| `backend/app/services/compliance_service.py`                     | auto\_unblock\_compliant 方法添加 message 返回          |
| `frontend/src/i18n/locales/zh.ts`                                | 添加翻译文案                                            |
| `frontend/src/i18n/locales/en.ts`                                | 添加翻译文案                                            |
| `frontend/src/i18n/locales/ja.ts`                                | 添加翻译文案                                            |

### 2.2 具体修改

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

**修改A - auto\_unblock\_compliant 返回 message**（第761-767行）：

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

**修改A - 添加 Modal 状态**（第302行后）：

```javascript
const [forceCheck, setForceCheck] = useState(false);
const [showAutoBlockModal, setShowAutoBlockModal] = useState(false);
```

**修改B - handleAutoBlock 拆分为两步**（第327-349行）：

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
    // 显示原因提示
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

**修改C - handleAutoUnblock 优化提示**（第351-367行）：

```javascript
const handleAutoUnblock = async () => {
  setAutoUnblockLoading(true);
  try {
    const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_AUTO_UNBLOCK);
    const r = response.data;
    toast.success(t('compliance.autoUnblockComplete', {
      total: r.total_auto_blocked, unblocked: r.unblocked, skipped: r.skipped,
    }));
    // 显示原因提示
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

**修改D - 添加 Auto Block 确认 Modal**（按钮区域之后）：

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

**修改E - 按钮 onClick 修改**：

```jsx
// Run Compliance Check 按钮前添加 Force Re-check 复选框（同上一个计划）
<label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
  <input type="checkbox" checked={forceCheck} onChange={(e) => setForceCheck(e.target.checked)} className="rounded border-input" />
  {t('compliance.forceRecheck')}
</label>

// Auto Block 按钮 onClick 改为 handleAutoBlockClick
<PrimaryButton
  icon={Ban}
  label={t('compliance.autoBlock')}
  onClick={handleAutoBlockClick}  // ← 改为打开 Modal
  loading={autoBlockLoading}
  variant="danger"
/>
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

***

## 三、验证步骤

1. `./manage.sh update` 重新构建
2. Auto Block：

   * 未选 ARP 源 → 点击 → 提示选择数据源

   * 选择 ARP 源 → 点击 → 弹出自定义 Modal（非浏览器原生）

   * 确认 → toast 显示 "0 non-compliant, 0 blocked, 0 skipped"

   * 紧接着 toast.info 提示 "所有不合规终端已封锁，无需重复操作"
3. Auto Unblock：

   * 点击 → toast 显示 "146 auto-blocked, 0 unblocked, 146 skipped"

   * 紧接着 toast.info 提示 "被封锁终端均未变为合规状态，暂无需要解封的终端"
4. Run Compliance Check：

   * 不勾选 Force Re-check → 0 total（正常）

   * 勾选 Force Re-check → 选择 ARP 源 → 返回实际检查数量

