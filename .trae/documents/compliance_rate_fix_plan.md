# 合规率计算逻辑修复计划

## 概述

将合规率计算的分母从"全部终端（合规+白名单+不合规）"改为"需要检查的终端（合规+不合规）"，排除白名单终端。

## 当前问题

代码位置：[main.py#L334-335](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L334-L335)

```python
total_checked = result.compliant + result.bypass + result.non_compliant
rate = (result.compliant / total_checked * 100) if total_checked > 0 else 100.0
```

当前公式：`合规率 = 合规 / (合规 + 白名单 + 不合规)`

白名单终端（bypass）是"免检"的，计入分母但不计入分子，人为压低了合规率。

## 修改方案

**仅修改 1 个文件，1 处代码**

文件：`backend/app/main.py` \~L334-335

```python
# After:
total_for_rate = result.compliant + result.non_compliant
rate = (result.compliant / total_for_rate * 100) if total_for_rate > 0 else 100.0
```

修改后公式：`合规率 = 合规 / (合规 + 不合规)`

> 注意：`total_checked` 变量名改为 `total_for_rate` 以避免与 `ComplianceCheckResult.total_checked`（含白名单）混淆。

## 边界情况

* 当 `compliant + non_compliant == 0`（所有终端都是白名单）→ rate = 100.0（合理：无需检查的终端全部合规）

* 该改动不影响 `result.total_checked`、`result.bypass` 等其他字段的值，仅影响告警的 `compliance_rate` 参数

## 验证

1. `python3 -m py_compile backend/app/main.py`
2. VS Code 诊断检查

