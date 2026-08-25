# 移除黑名单表格中的「类型」「封禁人」两列

## Summary

用户指出黑名单数据展示表格中的「类型」（TYPE）与「封禁人」（Blocked By）两列无实际意义：

* 「类型」基于 `is_auto_blocked` 渲染，生产环境所有真实业务代码均写死为 `True`，恒显示「自动」。

* 「封禁人」基于 `blocked_by` 渲染，生产环境所有真实业务代码均写死为 `"system"`，恒显示「system」。

经与用户确认，移除范围限定为：**仅移除表格中的这两列**。详情弹窗、CSV 导出、后端字段与 i18n 翻译键均保持不变。

## Current State Analysis

表格定义位于 [Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L302-L447)：

* 表头共 9 个 `<th>`（MAC、IP、原因、类型、封禁人、防火墙、封禁时间、过期时间、操作）。

* 「类型」表头：第 317-319 行，`t('whitelist.type')`。

* 「封禁人」表头：第 320-322 行，`t('blacklist.blockedBy')`。

* 数据行：

  * 「类型」单元格：第 373-388 行，根据 `item.is_auto_blocked` 渲染「自动/手动」徽章，并附带 `auto_unblocked/unblocked_at` 的「已解封」徽章。

  * 「封禁人」单元格：第 389-391 行，渲染 `item.blocked_by`。

* 空状态 `<td>` 使用 `colSpan={9}`（第 340 行）。

`is_auto_blocked` 仍用于行高亮（第 354 行 `bg-orange-50/30`），本次不改动。

## Proposed Changes

仅修改一个文件：`frontend/src/pages/Blacklist.tsx`。

1. **删除表头「类型」列**：移除第 317-319 行的 `<th>{t('whitelist.type')}</th>`。
2. **删除表头「封禁人」列**：移除第 320-322 行的 `<th>{t('blacklist.blockedBy')}</th>`。
3. **删除数据行「类型」单元格**：移除第 373-388 行的 `is_auto_blocked` 徽章块（含「自动/手动」徽章及「已解封」徽章）。
4. **删除数据行「封禁人」单元格**：移除第 389-391 行的 `{item.blocked_by}` 单元格。
5. **修正空状态 colSpan**：将第 340 行的 `colSpan={9}` 改为 `colSpan={7}`。

不改动：i18n 翻译键（`whitelist.type`、`blacklist.blockedBy`、`blacklist.auto`、`blacklist.manual` 等保留），后端 `blocked_by`/`is_auto_blocked` 字段及 schema，CSV 导出日志，详情弹窗。

## Assumptions & Decisions

* 移除范围仅限表格两列，不涉及详情弹窗、导出、后端与翻译文件。

* 保留 `is_auto_blocked` 用于行高亮逻辑，避免越界改动。

## Verification

1. 运行前端本地构建/lint，确认无 TS 未使用变量报错（`isExpired` 等仍被使用，不受影响）。
2. 打开黑名单页面，确认表格仅剩 7 列：MAC、IP、原因、防火墙、封禁时间、过期时间、操作。
3. 确认空状态行跨列显示正常（colSpan=7）。
4. 确认详情弹窗仍正常显示「封禁类型」「封禁人」两行（未受影响）。

