# 合规作用域新增「IP 或 MAC 任一命中即合规」匹配策略 —— 实施计划

> 文档版本：v1.0  更新日期：2026-09-03

## 一、摘要

当前合规计算默认采用 **AND 逻辑**：终端要被判定为 `compliant`，必须满足「IPGuard 基线中存在 IP 且 MAC **同一条目同时命中**」（或 IP 命中 + `mac_prefix_ipguard` 前缀命中）。系统已有 `compliance_scope` 作用域可把某些网段/前缀切换为 **IP-only** 逻辑。

本计划新增第三种匹配策略 **OR 逻辑**：在指定的 **终端 MAC 前缀** 或 **终端 IP 范围/CIDR** 内，终端 IP 或 MAC **只要有一个在基线中出现**，即判定为 `compliant`。该策略通过新增 3 个 `compliance_scope.scope_type` 落地，与现有 IP-only 作用域**对称**（同样的筛选维度，不同的匹配策略），向后兼容、无需数据库迁移。

## 二、现状分析（已只读确证）

### 2.1 作用域解析流程

- 作用域数据加载：[compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1202-L1234) `_load_scope_cache`，Redis key `compliance_scope:all`（常量 `SCOPE_CACHE_KEY` 第 43 行），DB 回退读 `ComplianceScope.is_active=True`。
- 现有 `scope_type` 四类（[compliance_scope.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/compliance_scope.py#L13-L21)）：`ip_cidr`、`ip_range`、`mac_prefix_arp`、`mac_prefix_ipguard`。
- 策略翻译：[compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1259-L1298) `_check_terminal_in_arp_scope` 把 `ip_cidr`/`ip_range`/`mac_prefix_arp` 翻译成布尔 `use_ip_only`（是否走 IP-only 策略）。
- `mac_prefix_ipguard` 单独由 [compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1250-L1257) `_extract_ipguard_mac_prefixes` 提取，作为 AND 逻辑里「IP 命中 + 基线 MAC 前缀命中」的补充条件（[#L1142-L1144](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1142-L1144)）。

### 2.2 三种匹配路径的现状

- **AND**（默认）：`_match_ipguard_in_memory`（[#L1115-L1152](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1115-L1152)）返回三元组 `(is_compliant, ip_found, mac_found)`，仅「IP+MAC 同条目」或「IP+mac_prefix_ipguard」才 `is_compliant=True`；`ip_found`/`mac_found` 会被单独追踪但**不**单独判合规。
- **IP-only**：`_match_ipguard_ip_only_in_memory`（[#L1159-L1167](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1159-L1167)）只看 `ip_address`，忽略 MAC。
- **（新增）OR**：`ip_found OR mac_found`，即 IP 或 MAC 任一命中即合规。

### 2.3 需要同步修改的判定点（共 7 处策略分支 + 3 处 reason 分支）

判定/策略分支（`use_ip_only`）：
1. `check_compliance`（[#L127-L134](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L127-L134)）
2. `batch_check_compliance`（[#L183-L193](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L183-L193)）
3. `auto_block_non_compliant`（[#L596-L605](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L596-L605)，block_reason）
4. `auto_unblock_compliant`（[#L778-L782](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L778-L782)）
5. `_apply_compliance_result`（[#L1682-L1700](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1682-L1700)，block_reason）
6. `_apply_compliance_result`（[#L1849-L1855](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1849-L1855)，unblock_reason）
7. `recalculate_all_compliance`（[#L2151-L2155](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L2151-L2155)）

`_build_unblock_reason`（[#L1169-L1197](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1169-L1197)）的 3 个调用点：`auto_unblock_compliant` 成功路径 [#L878-L880](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L878-L880)、部分成功路径 [#L952-L954](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L952-L954)、`_apply_compliance_result` [#L1853-L1855](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1853-L1855)。

### 2.4 scope_type 白名单（三层，需同步新增）

1. API schema：`ScopeType = Literal[...]`（[schemas/compliance_scope.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/compliance_scope.py#L7)）。
2. 业务校验：`_validate_scope_value`（[compliance_scope_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_scope_service.py#L101-L155)）。
3. 策略分派：`_check_terminal_in_arp_scope` 的 if/elif（运行时语义）。

DB 层 `scope_type` 为 `String(20)`，无枚举/CHECK 约束，**无需迁移**（新值最长 14 字符 < 20）。

## 三、方案设计

新增 3 个 `scope_type`，命名与现有 IP-only 筛选维度对称（同一筛选维度 + `_any` 后缀表示「任一命中」）：

| 新 scope_type | 筛选维度 | 匹配策略 |
| --- | --- | --- |
| `mac_prefix_any` | 终端 MAC 匹配前缀（如 `AA:BB:CC`） | OR：IP 或 MAC 任一命中即合规 |
| `ip_cidr_any` | 终端 IP 在 CIDR 网段（如 `192.168.0.0/16`） | OR：IP 或 MAC 任一命中即合规 |
| `ip_range_any` | 终端 IP 在起止范围（如 `192.168.1.1-255`） | OR：IP 或 MAC 任一命中即合规 |

优先级（确定性）：**OR > IP-only > AND**（若终端同时命中 OR 与 IP-only 作用域，OR 生效，因为它更宽松且更精确地覆盖了 `ip_found OR mac_found`）。

## 四、具体修改（文件级 what/why/how）

### 4.1 后端 - 兼容服务（核心）

文件：[compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py)

**1）新增 `_match_ipguard_or_in_memory`（放在 `_match_ipguard_ip_only_in_memory` 之后，约 #L1167 之后）**

复用现有 `_match_ipguard_in_memory` 的 `ip_found`/`mac_found` 追踪，实现 OR 语义：

```python
def _match_ipguard_or_in_memory(
    self, ipguard_data: dict[str, list[dict]], ip_address: str, mac_address: str
) -> bool:
    """OR match: compliant if IP OR MAC is found anywhere in the IPGuard baseline."""
    _, ip_found, mac_found = self._match_ipguard_in_memory(ipguard_data, ip_address, mac_address)
    return ip_found or mac_found
```

**2）新增 `_check_terminal_in_or_scope`（放在 `_check_terminal_in_arp_scope` 之后，约 #L1298 之后）**

镜像 `_check_terminal_in_arp_scope`，只识别 `ip_cidr_any` / `ip_range_any` / `mac_prefix_any`，判断终端是否命中 OR 作用域：

```python
def _check_terminal_in_or_scope(self, scope_data: list[dict], ip_address: str, mac_address: str) -> bool:
    """Return True if the terminal should use OR strategy (IP or MAC, either matches)."""
    if not scope_data:
        return False
    for scope in scope_data:
        scope_type = scope.get("scope_type", "")
        scope_value = scope.get("scope_value", "")
        if scope_type == "ip_cidr_any":
            try:
                if ipaddress.ip_address(ip_address) in ipaddress.ip_network(scope_value, strict=False):
                    return True
            except (ValueError, TypeError):
                continue
        elif scope_type == "ip_range_any":
            try:
                start_ip_str, end_ip_str = scope_value.split("-")
                start_ip = int(ipaddress.IPv4Address(start_ip_str))
                end_ip = int(ipaddress.IPv4Address(end_ip_str))
                ip_val = int(ipaddress.IPv4Address(ip_address))
                if start_ip <= ip_val <= end_ip:
                    return True
            except (ValueError, TypeError):
                continue
        elif scope_type == "mac_prefix_any":
            try:
                if self._mac_matches_any_prefix(mac_address, [scope_value]):
                    return True
            except (ValueError, TypeError):
                continue
    return False
```

**3）扩展 `_build_unblock_reason` 签名与逻辑（#L1169-L1197）**

- 签名增加参数 `use_or_match: bool`（排在 `use_ip_only` 之后）。
- 逻辑：`if use_ip_only and not use_or_match: return "IP 合规"`；其余（含 OR、AND）走现有详细拆解分支（`_match_ipguard_in_memory` 得到 ip_found/mac_found 后分四类），该分支已能正确覆盖 OR 场景（任一命中→对应「IP 合规，MAC 不合规 / MAC 合规，IP 不合规 / IP 和 MAC 都合规」）。

**4）7 处判定点分支接入 `use_or_match`（统一模式）**

在每处 `use_ip_only = ...` 之后新增一行，并把匹配分支从「二选一」改为「三选一」：

```python
use_ip_only = self._check_terminal_in_arp_scope(scope_data, ip_addr, mac_addr)
use_or_match = self._check_terminal_in_or_scope(scope_data, ip_addr, mac_addr)
if use_or_match:
    ig_match = self._match_ipguard_or_in_memory(ipguard_data, ip_addr, mac_addr)
elif use_ip_only:
    ig_match = self._match_ipguard_ip_only_in_memory(ipguard_data, ip_addr)
else:
    ig_match, ip_found, mac_found = self._match_ipguard_in_memory(ipguard_data, ip_addr, mac_addr, ipguard_mac_prefixes)
```

具体位置与差异点：
- `check_compliance`（#127-134）：调用 `_check_ipguard_ip_only`/`_check_ipguard`，需同步加 `use_or_match` 分支（OR 走新增的 `_match_ipguard_or_in_memory` 封装，或直接调用；保持与其它位一致即可）。
- `batch_check_compliance`（#183-193）：需要把 `entry["use_ip_only"]`、`entry["ip_found"]`、`entry["mac_found"]` 相应填充；OR 命中时同样 `ip_found/mac_found` 来自 `_match_ipguard_in_memory`，可单独解包一次（或 `entry["ip_found"]=True if ...`，按最终代码定，保持结果字段语义不变）。
- `auto_block_non_compliant`（#596-605，block_reason）：把 `if use_ip_only:` 改为 `if use_ip_only and not use_or_match:`，其余 `else` 详细拆解分支自然覆盖 OR（non_compliant ⇒ 二者皆缺失 ⇒ `"IP 和 MAC 都不合规"`）。
- `auto_unblock_compliant`（#778-782）：匹配分支同三选一模式。
- `_apply_compliance_result` block_reason（#1682-1700）：同 `auto_block_non_compliant` 的 `use_ip_only and not use_or_match` 处理。
- `_apply_compliance_result` unblock_reason（#1849-1855）：计算 `use_or_match` 并传入 `_build_unblock_reason`。
- `recalculate_all_compliance`（#2151-2155）：匹配分支同三选一模式。

**5）`_build_unblock_reason` 的 3 个调用点**（#878-880、#952-954、#1853-1855）：补传 `use_or_match` 实参（前两处需在方法内已计算好 `use_or_match`，第 3 处在 4）中的 unblock_reason 处计算）。

### 4.2 后端 - schema 白名单

文件：[schemas/compliance_scope.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/compliance_scope.py#L7)

```python
ScopeType = Literal[
    "ip_cidr", "ip_range", "mac_prefix_arp", "mac_prefix_ipguard",
    "ip_cidr_any", "ip_range_any", "mac_prefix_any",
]
```

### 4.3 后端 - 作用域值校验

文件：[compliance_scope_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_scope_service.py#L107-L155) `_validate_scope_value`

- `ip_cidr_any`：复用 `ip_cidr` 的 CIDR 校验分支。
- `ip_range_any`：复用 `ip_range` 的范围校验分支。
- `mac_prefix_any`：加入 `mac_prefix_arp`/`mac_prefix_ipguard` 的 MAC 前缀校验分支。

实现方式：把现有 `if scope_type == "ip_cidr":` 改为 `if scope_type in ("ip_cidr", "ip_cidr_any"):`，`ip_range` 与 MAC 前缀同理；`else` 依旧抛 `Unknown scope type`。

### 4.4 后端 - 模型 docstring（可选，仅文档）

文件：[compliance_scope.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/compliance_scope.py#L13-L21)

在 docstring 中补充三类新语义：`ip_cidr_any`/`ip_range_any`/`mac_prefix_any` → OR 匹配（IP 或 MAC 任一命中即合规）。

### 4.5 前端 - TypeScript 类型

文件：[api/complianceScope.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/api/complianceScope.ts#L5)

```typescript
export type ScopeType =
  | 'ip_cidr' | 'ip_range' | 'mac_prefix_arp' | 'mac_prefix_ipguard'
  | 'ip_cidr_any' | 'ip_range_any' | 'mac_prefix_any';
```

### 4.6 前端 - 作用域管理页面

文件：[pages/ComplianceScope.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/ComplianceScope.tsx)

- `getScopeTypeLabel`（#40-48）：新增三类 label（引用新增 i18n key）。
- `getScopeTypeDesc`（#50-58）：新增三类 desc。
- `getScopePlaceholder`（#60-69）：`mac_prefix_any` → MAC 占位符；`ip_cidr_any` → CIDR 占位符；`ip_range_any` → range 占位符。
- 新增/编辑 `<select>` 选项（#289-298、#360-369）：各追加 3 个 `<option>`。

### 4.7 前端 - i18n 文案

文件（三个语言同步）：[zh.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/i18n/locales/zh.ts#L1497-L1525)、`en.ts`、`ja.ts` 的 `complianceScope` 块。

新增 key（中文示例，en/ja 对应翻译）：
- `typeMacPrefixAny`：`MAC 前缀（任一命中即合规）`
- `typeIpCidrAny`：`IP CIDR 网段（任一命中即合规）`
- `typeIpRangeAny`：`IP 地址范围（任一命中即合规）`
- `macPrefixAnyDesc`：`3-5 段 MAC 前缀。终端 MAC 匹配此前缀时，IP 或 MAC 任一命中合规基线即视为合规`
- `ipCidrAnyDesc`：`CIDR 网段。终端 IP 在此网段时，IP 或 MAC 任一命中合规基线即视为合规`
- `ipRangeAnyDesc`：`起止 IP 范围。终端 IP 在此范围时，IP 或 MAC 任一命中合规基线即视为合规`

（`valuePlaceholderCidr` / `valuePlaceholderRange` / `valuePlaceholderMac` 已存在，直接复用，不新增。）

同时将 `complianceScope.description` 文案由「控制合规计算时 IP-only 匹配策略」调整为「控制合规计算时的 IP-only 或任一命中（IP 或 MAC）匹配策略」（可选，仅文案准确性）。

## 五、假设与决策

1. **作用域数量**：新增 3 类（`mac_prefix_any` / `ip_cidr_any` / `ip_range_any`），与现有 IP-only 的三类筛选维度（`mac_prefix_arp` / `ip_cidr` / `ip_range`）对称。若用户仅需「IP 范围」而非「CIDR」，可删去 `ip_cidr_any`。
2. **命名约定**：`_any` 后缀表示「IP 或 MAC 任一命中即合规」，语义自文档化。
3. **优先级**：OR > IP-only > AND（确定性，避免重叠作用域时的非确定性）。
4. **OR 的判定口径**：`ip_found OR mac_found`，即终端 IP 或终端 MAC 在基线中「任意位置」出现即可，不要求同一条目、不叠加 `mac_prefix_ipguard`。
5. **无需数据库迁移**：`scope_type` 为 `String(20)`，无枚举约束，新值长度均在 20 字符内。
6. **不改动现有 4 类作用域语义**，向后兼容。
7. **`_match_ipguard_or_in_memory` 复用 `_match_ipguard_in_memory`**：`_match_ipguard_in_memory` 对「精确配对」会提前返回 `(True, True, True)`，此时 `ip_found=mac_found=True` → OR 仍为 `True`，语义正确。

## 六、验证步骤

1. **后端语法**：`cd backend && python3 -m compileall app` 通过。
2. **schema 校验**：新增 `scope_type` 能通过 `POST /api/v1/compliance-scope` 创建（422 之前会被 `Literal` 拦截，新增后可正常入库）。
3. **值校验**：分别用合法/非法值创建三类新作用域，验证 `_validate_scope_value` 分支（CIDR 最小 /24、范围格式、MAC 3-5 段）。
4. **匹配语义**（核心）：
   - 构造「IP 不在基线、MAC 在基线」的终端 → 命中 `mac_prefix_any`/`ip_range_any` 后应判 `compliant`（对比 AND 下判 `non_compliant`）。
   - 构造「IP、MAC 都在基线但不同条目」→ 命中 OR 作用域后应判 `compliant`。
   - 构造「IP、MAC 都不在基线」→ 仍判 `non_compliant`，block_reason 为 `"IP 和 MAC 都不合规"`。
5. **reason 一致性**：非合规/解封时的 `block_reason`/`unblock_reason` 与「IP/MAC 哪个命中」一致（尤其 OR 场景的 MAC-only / IP-only 命中）。
6. **回归**：默认（AND）与 IP-only 作用域的既有行为不变。
7. **前端**：ComplianceScope 页新增/编辑可选中 3 类新类型，标签/说明/占位符正确显示，中/英/日切换正常。
8. 验证通过后，按项目规范走 `./manage.sh update` 重建并核验（部署留待用户确认）。

## 七、涉及文件清单

后端：
- `backend/app/services/compliance_service.py`（核心）
- `backend/app/schemas/compliance_scope.py`
- `backend/app/services/compliance_scope_service.py`
- `backend/app/models/compliance_scope.py`（仅 docstring）

前端：
- `frontend/src/api/complianceScope.ts`
- `frontend/src/pages/ComplianceScope.tsx`
- `frontend/src/i18n/locales/zh.ts`
- `frontend/src/i18n/locales/en.ts`
- `frontend/src/i18n/locales/ja.ts`

（无数据库迁移文件。）