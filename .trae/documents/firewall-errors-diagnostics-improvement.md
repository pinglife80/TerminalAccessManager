# Firewall Errors 弹窗诊断信息完善计划

> 文档版本：v1.0  更新日期：2026-08-24

## 1. 问题背景

黑名单管理页的「防火墙异常」（`statsFirewallErrors`）标签点击后，弹窗内只有 Firewall Errors 标签点击后的弹窗内容仅有 `af`，没有其它信息。

经排查，「防火墙异常」弹窗当前只展示了防火墙的 `tag`（数据源标识名，本例为 `af`），**没有展示具体错误原因**，也没有展示对账时间，不符合业务逻辑。

### 根因

数据流中 `firewall_errors` 全程被当成 `list[str]`（只存防火墙 tag）处理：

1. [firewall_reconciliation_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L49-L58) 初始化 `firewall_errors = []`。
2. 两处出错分支只追加 tag：
   - 「0 IP 保护」分支 [L126](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L126)：`results["firewall_errors"].append(fw_tag)`
   - 异常分支 [L155-L156](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/firewall_reconciliation_service.py#L155-L156)：`firewall_errors.append(fw_tag)`，同时把真正原因写进了另一个字段 `errors.append(f"{fw_tag}: {str(e)}")`。
3. [main.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L85-L99) 的 `_cache_reconcile_result` 只缓存了 `firewall_errors`（tag 列表），**没有缓存 `errors`**，导致错误原因丢失。
4. [terminal_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/terminal_service.py#L1578-L1590) 从缓存读取 `firewall_errors` 直接返回。
5. 前端 [BlacklistStats](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/hooks/useTerminalData.ts#L51-L58) 定义为 `string[]`，[Blacklist.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Blacklist.tsx#L597-L618) 弹窗仅渲染 `{fw}`。

因此，业务上应展示「防火墙 tag + 具体错误原因 + 对账时间」。

## 2. 目标

点击「防火墙异常」标签后，弹窗展示完整的诊断信息：

- 每个异常防火墙的 `tag`；
- 该防火墙对应的具体错误原因；
- 本次对账的时间（`synced_at`）。

## 3. 涉及文件与改动

### 3.1 后端 `backend/app/services/firewall_reconciliation_service.py`

将 `firewall_errors` 由 `list[str]` 升级为 `list[dict]`，每项结构为 `{"tag": str, "error": str}`。

- **初始化**（L56 注释同步更新，保持 `firewall_errors: []` 不变，语义变化为对象列表）。
- **「0 IP 保护」分支**（L126 附近）：当前在两个子分支（probe 命中 / 未命中）共用一次 `append(fw_tag)` 后 `continue`。改为根据 `probe_hit` 追加结构化的错误原因：

  ```python
  # probe 命中分支
  results["firewall_errors"].append({
      "tag": fw_tag,
      "error": "返回0个封锁IP但数据库存在活跃条目，单点探测命中，疑似列表接口异常（已跳过对账以防数据丢失）",
  })
  # probe 未命中分支
  results["firewall_errors"].append({
      "tag": fw_tag,
      "error": "返回0个封锁IP但数据库存在活跃条目，单点探测未命中，无法区分外部清空与接口故障（已保守跳过对账以防数据丢失）",
  })
  ```

  实现方式：在 `if len(fw_ips) == 0 and db_count_for_fw > 0:` 代码块内，将两处 `logger.warning` 之后统一构造 `reason` 变量（依据 `probe_hit` 二选一），再执行一次 `results["firewall_errors"].append({"tag": fw_tag, "error": reason})`。

- **异常分支**（L154-L156）：

  ```python
  except Exception as e:
      logger.error(f"Failed to reconcile firewall '{fw_tag}': {str(e)}")
      results["firewall_errors"].append({"tag": fw_tag, "error": str(e)})
      results["errors"].append(f"{fw_tag}: {str(e)}")
  ```

  `errors` 字段保留（供 [system.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/system.py#L108-L127) 手动对账接口 `**results` 透传日志用）。

> 说明：`main.py` 的 `_cache_reconcile_result` 已使用 `results.get("firewall_errors", [])` 配合 `json.dumps`，`list[dict]` 会被自动正确序列化，**无需改动 main.py**。

### 3.2 后端 `backend/app/services/terminal_service.py`

`get_blacklist_stats` 读取缓存处（L1578-L1590）增加对旧缓存格式的防御性规范化（旧缓存 TTL 1h，可能仍是字符串列表），统一输出为对象列表：

```python
firewall_errors: list[dict] = []
...
if cached:
    payload = json.loads(cached)
    raw_errors = payload.get("firewall_errors", [])
    for item in raw_errors:
        if isinstance(item, dict):
            firewall_errors.append({
                "tag": item.get("tag", ""),
                "error": item.get("error", ""),
            })
        elif isinstance(item, str):
            firewall_errors.append({"tag": item, "error": ""})
    synced_at = payload.get("synced_at")
```

并将该处类型注解 `firewall_errors: list[str]` 改为 `list[dict]`。

### 3.3 前端 `frontend/src/hooks/useTerminalData.ts`

新增接口并更新 `BlacklistStats`：

```ts
export interface FirewallError {
  tag: string;
  error: string;
}

export interface BlacklistStats {
  // ...其余不变
  firewall_errors: FirewallError[];
  synced_at: string | null;
}
```

（将 L56 的 `firewall_errors: string[]` 改为上述类型。）

### 3.4 前端 `frontend/src/pages/Blacklist.tsx`

更新「Firewall Errors Modal」（L597-L618），展示 tag、错误原因、对账时间：

```tsx
<Modal
  isOpen={showFirewallErrorsModal}
  onClose={() => setShowFirewallErrorsModal(false)}
  title={t('blacklist.firewallErrorsTitle')}
  size="md"
>
  <div className="space-y-3">
    {stats?.synced_at && (
      <p className="text-xs text-muted-foreground">
        {t('blacklist.firewallReconcileTime')}: {formatDate(stats.synced_at)}
      </p>
    )}
    {stats?.firewall_errors?.length ? (
      <ul className="space-y-3">
        {stats.firewall_errors.map((fw, idx) => (
          <li key={idx} className="rounded-lg border border-red-100 bg-red-50 p-3">
            <div className="flex items-center gap-2 text-sm font-medium text-foreground">
              <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
              {fw.tag}
            </div>
            {fw.error && (
              <p className="mt-1 pl-6 text-sm text-muted-foreground">{fw.error}</p>
            )}
          </li>
        ))}
      </ul>
    ) : (
      <p className="text-sm text-muted-foreground">{t('blacklist.noFirewallErrors')}</p>
    )}
  </div>
</Modal>
```

`AlertCircle`、`formatDate` 均已在文件顶部导入，无需新增 import。组件内 `fw` 的类型自动由 `BlacklistStats` 推断为对象，map 渲染从 `{fw}` 改为 `{fw.tag}` / `{fw.error}`。

### 3.5 前端 i18n 三语言补键

在三个语言文件的 `blacklist` 块内补充 `firewallReconcileTime`：

- [zh.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/zh.ts#L457-L458) 附近：

  ```ts
  firewallErrorsTitle: '防火墙错误',
  noFirewallErrors: '无错误',
  firewallReconcileTime: '对账时间',   // 新增
  ```

- [en.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/en.ts#L456-L457) 附近：

  ```ts
  firewallErrorsTitle: 'Firewall Errors',
  noFirewallErrors: 'No errors',
  firewallReconcileTime: 'Reconciliation Time',   // 新增
  ```

- [ja.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/ja.ts#L453-L454) 附近：

  ```ts
  firewallErrorsTitle: 'ファイアウォールエラー',
  noFirewallErrors: 'エラーなし',
  firewallReconcileTime: '照合時間',   // 新增
  ```

## 4. 决策与假设

- **错误原因语言**：诊断原因由后端生成、前后端不翻译；其中「0 IP 保护」两种场景使用中文文案（面向用户），异常分支沿用 `str(e)`（Sangfor 原始异常信息）。这与现有 `reason` 字段的英文字符串并存、不统一的情况一致，符合当前仅中文站点的实际使用场景。
- **向后兼容**：通过 `terminal_service.py` 的规范化逻辑兼容旧缓存（字符串列表），旧数据展示为 tag + 空错误原因，不报错、不遗漏 tag。
- **不新增字段**：复用现有 `synced_at` 展示对账时间，不引入新的缓存字段。
- **`errors` 字段**：保留原样，仅用于手动对账接口透出，不影响前端展示。

## 5. 验证步骤

1. 后端语法/类型检查：确认改动文件无报错（`python -m py_compile` 或项目既有 lint）。
2. 本地重构建：`./manage.sh update` 重建后端与前端。
3. 触发对账：调用手动对账接口 `POST /system/firewall-reconciliation`（或等待调度任务），构造一个防火墙异常场景（如停用 Sangfor、错误 base_url 或触发「0 IP 保护」）。
4. 校验缓存：`docker exec tam_backend redis-cli GET reconcile:latest` 确认 `firewall_errors` 为对象列表且包含 `tag`、`error`，并含 `synced_at`。
5. 校验 API：`curl` 或前端调用 `/blacklist/stats`，确认 `firewall_errors` 返回对象列表。
6. 前端验证：进入「黑名单管理」点击「防火墙异常」标签，弹窗应展示每个防火墙的 tag、具体错误原因、对账时间；无异常时显示「无错误」。