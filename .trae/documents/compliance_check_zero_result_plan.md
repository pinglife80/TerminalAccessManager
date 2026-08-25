# Run Compliance Check 返回 0 结果分析与修复计划

> 创建日期：2026-07-16

***

## 一、根因分析

### 1.1 问题现象

点击 "Run Compliance Check" 按钮后立即返回：

```
Check complete: 0 total, 0 compliant, 0 bypass, 0 non-compliant
```

### 1.2 根因

**前端硬编码** **`force: false`**（[ComplianceBaselinesTab.tsx:312](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/components/datasources/ComplianceBaselinesTab.tsx#L312)）：

```javascript
const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_CHECK, {
  arp_source_tag: selectedTag || undefined,
  force: false,  // ← 硬编码
});
```

**后端逻辑**（[data\_sources.py:532-533](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/data_sources.py#L532-L533)）：

```python
if not request.force:
    conditions.append(Terminal.compliance_status == "unknown")
```

当 `force=false` 时，只查询 `compliance_status == "unknown"` 的终端。但数据库中 **没有 unknown 状态的终端**：

| compliance\_status | 数量    |
| ------------------ | ----- |
| bypass             | 510   |
| compliant          | 313   |
| non\_compliant     | 146   |
| unknown            | **0** |

### 1.3 为什么没有 unknown 终端？

因为 ARP 采集服务在采集到新终端时会**立即自动执行合规检查**（[arp\_collector\_service.py:330-353](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L330-L353)）：

1. 新终端创建时 `compliance_status = "unknown"`
2. 同一个 sync 操作中立即运行 `batch_check_compliance`
3. 将状态更新为 `bypass` / `compliant` / `non_compliant`

此外，定时任务（默认300秒间隔）也会处理 unknown 终端。

### 1.4 结论

**不是 Bug，是设计行为**。手动按钮的 `force=false` 只检查 unknown 终端，但系统已经在 ARP 采集时自动处理了。用户需要一个强制重新检查的选项。

***

## 二、修复方案

### 2.1 方案：添加 Force Re-check 复选框

在 "Run Compliance Check" 按钮旁添加一个复选框，允许用户选择 `force=true` 重新检查所有终端。

后端已支持 `force` 参数（[data\_source.py:96](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/data_source.py#L96)），只需修改前端。

### 2.2 需要修改的文件

| 文件                                                               | 修改内容               |
| ---------------------------------------------------------------- | ------------------ |
| `frontend/src/components/datasources/ComplianceBaselinesTab.tsx` | 添加 force 复选框状态和 UI |
| `frontend/src/i18n/locales/zh.ts`                                | 添加中文翻译             |
| `frontend/src/i18n/locales/en.ts`                                | 添加英文翻译             |
| `frontend/src/i18n/locales/ja.ts`                                | 添加日文翻译             |

### 2.3 具体修改

#### 文件1: ComplianceBaselinesTab.tsx

**修改A - 添加 state**（第302行后）：

```javascript
const [forceCheck, setForceCheck] = useState(false);
```

**修改B - 修改 handleComplianceCheck**（第311-312行）：

```javascript
const response = await apiClient.post(API_ENDPOINTS.COMPLIANCE_CHECK, {
  arp_source_tag: selectedTag || undefined,
  force: forceCheck,
});
```

**修改C - 添加复选框 UI**（第387行前，Run Compliance Check 按钮之前）：

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

#### 文件2: zh.ts（第1348行后）

```javascript
forceRecheck: '强制重新检查',
```

#### 文件3: en.ts（第1348行后）

```javascript
forceRecheck: 'Force Re-check',
```

#### 文件4: ja.ts（第1336行后）

```javascript
forceRecheck: '強制再チェック',
```

***

## 三、验证步骤

1. 重新构建前端：`./manage.sh update`
2. 不勾选 "Force Re-check" → 点击 Run Compliance Check → 应返回 0 total（正常，因为没有 unknown 终端）
3. 勾选 "Force Re-check" → 选择 ARP 源 → 点击 Run Compliance Check → 应返回实际检查数量（bypass + compliant + non\_compliant）
4. 不勾选 "Force Re-check" → 选择 All → 点击 Run Compliance Check → 应返回 0 total

