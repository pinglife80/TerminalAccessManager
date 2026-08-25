# 合规设置 i18n 和 manage.sh 修复计划

## 概述

修复两个问题：
1. 系统设置中合规/告警设置区域的参数描述未使用 i18n 翻译，显示的是后端硬编码的中文文本
2. manage.sh 脚本因 `set -u` 导致 `version bump` 无参数调用时报 `unbound variable` 错误

---

## 问题 1：合规设置 i18n 缺失

### 根因分析

在 `GeneralSettings.tsx` 的 `Field` 组件中，描述文本直接使用后端 API 返回的 `entry.description`：

- **Line 168**: `placeholder={entry.description || ''}` — 用作输入框 placeholder
- **Line 181**: `{entry.description && <p>{entry.description}</p>}` — 用作字段说明文本

后端存储的 `description` 是硬编码的中文（如 "compliant→non_compliant 翻转所需的连续确认次数"），没有经过 i18n 翻译。

而在 i18n 文件中（zh.ts/en.ts/ja.ts），已为以下配置项定义了多语言描述：
- `compliance_confirm_thresholdDesc`
- `alert_compliance_rate_thresholdDesc`
- `alert_compliance_critical_ratioDesc`
- `alert_block_count_thresholdDesc`
- `alert_offline_threshold_multiplierDesc`

但这些翻译没有被使用。

### 修改方案

**文件**: `frontend/src/pages/GeneralSettings.tsx`

1. 在 `Field` 组件前添加配置项 key 到 i18n 描述的映射表：

```typescript
// Config key → i18n description key mapping
const FIELD_DESC_I18N_KEYS: Record<string, string> = {
  'compliance_confirm_threshold': 'generalSettings.compliance_confirm_thresholdDesc',
  'alert_compliance_rate_threshold': 'generalSettings.alert_compliance_rate_thresholdDesc',
  'alert_compliance_critical_ratio': 'generalSettings.alert_compliance_critical_ratioDesc',
  'alert_block_count_threshold': 'generalSettings.alert_block_count_thresholdDesc',
  'alert_offline_threshold_multiplier': 'generalSettings.alert_offline_threshold_multiplierDesc',
};
```

2. 在 `Field` 组件中计算显示用的描述文本：

```typescript
const descI18nKey = FIELD_DESC_I18N_KEYS[entry.key];
const displayDesc = descI18nKey ? t(descI18nKey) : entry.description;
```

3. 用 `displayDesc` 替换 Line 168 和 Line 181 中的 `entry.description`

---

## 问题 2：manage.sh 修复

### 2a. `version bump` 无参数报错

**根因分析**

- **Line 62**: `set -euo pipefail` 启用了 `-u`（nounset）选项
- **Line 606**: `cmd_version_bump "$2"` — 当用户运行 `./manage.sh version bump`（不带版本号参数）时，`$2` 未定义，触发 `unbound variable` 错误

**修改方案**

**文件**: `manage.sh`

| 位置 | 修改前 | 修改后 |
|------|--------|--------|
| Line 606 | `cmd_version_bump "$2"` | `cmd_version_bump "${2:-}"` |

`cmd_version_bump` 函数内部已有空值检查（Line 720-726），会显示友好的错误提示，所以传递空字符串是安全的。

### 2b. 其他潜在的未绑定变量问题

搜索发现脚本中还有以下使用 `$2` 的位置，建议添加安全默认值：

| 位置 | 函数 | 当前代码 | 风险 |
|------|------|----------|------|
| Line 150 | `save_state()` | `local value="$2"` | 若调用时缺少第二参数会报错 |
| Line 483 | `set_env()` | `local value="$2"` | 同上 |
| Line 531 | `interactive_backup()` | `local description="$2"` | 同上 |

对于这些函数，将 `$2` 改为 `${2:-}` 以避免在参数缺失时出错。

---

## 实施步骤

### Step 1: 修复 manage.sh

**文件**: `manage.sh`

1. **Line 606**: `cmd_version_bump "$2"` → `cmd_version_bump "${2:-}"`
2. **Line 150**: `local value="$2"` → `local value="${2:-}"`
3. **Line 483**: `local value="$2"` → `local value="${2:-}"`
4. **Line 531**: `local description="$2"` → `local description="${2:-}"`

### Step 2: 修复合规设置 i18n

**文件**: `frontend/src/pages/GeneralSettings.tsx`

1. 在 Field 组件前添加 `FIELD_DESC_I18N_KEYS` 映射表
2. 修改 Field 组件：添加 `displayDesc` 变量，优先使用 i18n 翻译
3. 替换 placeholder 和 description 的显示逻辑

### Step 3: 验证

1. 运行 `bash -n manage.sh` 检查脚本语法
2. 运行 `./manage.sh version bump`（不带参数）应显示友好错误提示
3. VS Code 诊断检查前端文件
4. 前端合规设置区域描述文本应根据当前语言正确显示
