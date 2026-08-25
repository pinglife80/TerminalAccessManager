# 基于 MAC 前缀 / 网段范围的合规计算模式分析建议

> 文档版本：v1.0  更新日期：2026-08-19

***

## 一、需求理解

### 1.1 核心诉求

用户希望支持一种新的白名单匹配模式：**按 MAC 前缀（OUI）或网段范围作为匹配条件**，在合规计算时**只检查 IP 地址条件，忽略 MAC 地址**。

### 1.2 具体场景举例

| 场景            | 白名单规则                                              | 终端数据                                        | 期望结果                   |
| ------------- | -------------------------------------------------- | ------------------------------------------- | ---------------------- |
| 网段范围（忽略 MAC）  | `ip_pattern=192.168.0.0/16`，`pattern_type=?`       | IP=`192.168.1.100`, MAC=`AA:BB:CC:DD:EE:FF` | **bypass**（仅 IP 匹配）    |
| MAC 前缀（忽略 IP） | `mac_address=AA:BB:CC:*`，`pattern_type=?`          | IP=`10.0.0.5`, MAC=`AA:BB:CC:11:22:33`      | **bypass**（仅 MAC 前缀匹配） |
| 精确 MAC（现有逻辑）  | `mac_address=AA:BB:CC:DD:EE:FF`, `ip_pattern=None` | IP=`10.0.0.5`, MAC=`AA:BB:CC:DD:EE:FF`      | **bypass**（MAC 精确匹配）   |

***

## 二、现有白名单匹配逻辑分析

### 2.1 当前 `pattern_type` 枚举值

| 值           | 含义         | 匹配逻辑                                |
| ----------- | ---------- | ----------------------------------- |
| `single_ip` | 单 IP       | `ip_address == ip_pattern`          |
| `cidr`      | CIDR 网段    | `ip_address in network(ip_pattern)` |
| `ip_range`  | IP 范围      | `ip_address in range(start, end)`   |
| `mac_only`  | 仅 MAC      | `mac_address == entry_mac`          |
| `both`      | IP+MAC 双条件 | 两者必须同时匹配                            |

### 2.2 当前 `_match_whitelist_in_memory()` 匹配逻辑

```
对每条白名单记录逐一检查：
  1. pattern_type == "mac_only" → 仅 MAC 精确匹配
  2. 有 ip_pattern + 有 mac_address → 两者必须同时匹配
  3. 仅 ip_pattern → 仅 IP 匹配
  4. 仅 mac_address → 仅 MAC 匹配
```

### 2.3 当前不足

* **MAC 前缀匹配**：完全不支持。现有 `mac_only` 和 `both` 模式均使用 `==` 精确匹配。

* **IP-only 模式（忽略 MAC）**：部分支持。当 `ip_pattern` 有值且 `mac_address` 为 `None` 时，确实只检查 IP。但这依赖于"是否填写了 MAC 字段"，而非显式的模式声明。

* **语义不明确**：当前没有显式的"忽略 MAC"或"忽略 IP"的模式类型，匹配逻辑依赖于字段是否为空，容易引起混淆。

***

## 三、方案设计

### 方案 A：新增 `pattern_type` 枚举值（推荐）

#### 3.1 新增模式类型

| 新 pattern\_type | 含义          | 匹配逻辑                                                              |
| --------------- | ----------- | ----------------------------------------------------------------- |
| `mac_prefix`    | MAC 前缀匹配    | `mac_address` 以 `entry.mac_address_normalized` 开头（前缀匹配），**忽略 IP** |
| `ip_only`       | 仅 IP 匹配（显式） | 仅检查 IP 地址（支持 single\_ip/cidr/ip\_range），**忽略 MAC**                |

#### 3.2 与现有模式的兼容性矩阵

| 现有 pattern\_type    | 新增需求       | 兼容性     | 处理方式                                           |
| ------------------- | ---------- | ------- | ---------------------------------------------- |
| `single_ip`         | 按 IP 匹配    | ✅ 已兼容   | 直接使用，当 `mac_address` 为空时即为忽略 MAC               |
| `cidr`              | 按网段匹配      | ✅ 已兼容   | 同上                                             |
| `ip_range`          | 按 IP 范围匹配  | ✅ 已兼容   | 同上                                             |
| `mac_only`          | MAC 前缀匹配   | ⚠️ 部分兼容 | `mac_only` 是精确匹配；`mac_prefix` 是前缀匹配，语义不同       |
| `both`              | IP+MAC 双条件 | ✅ 已兼容   | 不影响                                            |
| **新增** `mac_prefix` | MAC 前缀匹配   | 需新增实现   | —                                              |
| **新增** `ip_only`    | 显式忽略 MAC   | 可选增强    | 等价于现有 `single_ip`/`cidr`/`ip_range` 且无 MAC 的情况 |

#### 3.3 具体实现方案

**3.3.1 数据模型层（`models/whitelist.py`）**

不需要修改数据库 schema。`pattern_type` 字段为 `String(20)`，已能容纳新值。

**3.3.2 校验层（`schemas/terminal.py`）**

在 `WhitelistCreate` 中增加校验：

* `pattern_type` 允许值增加 `mac_prefix`、`ip_only`

* `mac_prefix` 模式：`mac_address` 必填，格式验证 MAC 前缀（3-5 段）

* `ip_only` 模式：`ip_address` 必填，`mac_address` 必须为 `None`

**3.3.3 服务层（`services/compliance_service.py`）**

在 `_match_whitelist_in_memory()` 中增加处理分支：

```python
# 新增 mac_prefix 模式匹配
if entry.get("pattern_type") == "mac_prefix":
    if entry.get("mac_address"):
        entry_mac_norm = _normalize_mac(entry["mac_address"])
        if normalized_mac.startswith(entry_mac_norm):
            return {"match_type": "mac_prefix", "comments": entry.get("comments")}
    continue

# 新增 ip_only 模式匹配（跳过 MAC 检查）
if entry.get("pattern_type") == "ip_only":
    if entry.get("ip_pattern"):
        if self._ip_matches_pattern(ip_address, entry["ip_pattern"], entry.get("sub_type", "single_ip")):
            return {"match_type": "ip", "comments": entry.get("comments")}
    continue
```

**3.3.4 MAC 前缀格式校验**

```python
# MAC 前缀允许的格式：
# AA:BB:CC (3段, OUI)
# AA:BB:CC:DD (4段)
# AA:BB:CC:DD:EE (5段)
# 不允许 AA:BB:CC:DD:EE:FF (6段, 这是完整 MAC)
```

**3.3.5 IP-only 的 sub\_type 设计**

`ip_only` 模式需要一个子类型字段来区分 single\_ip / cidr / ip\_range：

* 方案 1：复用现有 `pattern_type` 的子类型（如 `ip_only_single`、`ip_only_cidr`、`ip_only_range`）

* 方案 2：新增 `sub_pattern_type` 字段

* **推荐方案 1**：保持 `pattern_type` 为 `ip_only`，实际的 IP 模式通过 `ip_pattern` 内容自动推断（已有逻辑支持）

#### 3.4 前端 UI 变更

在白名单添加/编辑表单中：

* `Pattern Type` 下拉框增加 `MAC Prefix` 和 `IP Only` 选项

* 选择 `MAC Prefix` 时，`MAC Address` 标签变为 `MAC Prefix (e.g., AA:BB:CC)`

* 选择 `IP Only` 时，`IP Address` 标签变为 `IP / CIDR / Range`

* `IP Only` 模式下，MAC 字段自动禁用且标记为"忽略"

***

### 方案 B：扩展现有 `pattern_type` 语义（最小改动）

将现有 `single_ip`/`cidr`/`ip_range` 的匹配逻辑改为：**当** **`mac_address`** **字段为** **`None`** **时，自动忽略 MAC**。同时新增 `mac_prefix` 前缀匹配。

#### 分析

这个方案的核心是：

* 不改变现有 `pattern_type` 枚举

* 现有逻辑已基本实现"IP-only when mac is None"（见 `_match_whitelist_in_memory()` 第 838-840 行）

* 只需新增 `mac_prefix` 模式

#### 优势

* 改动最小

* 现有数据无需迁移

* 用户已熟悉的行为

#### 劣势

* "忽略 MAC"是隐式行为（依赖于 MAC 字段是否为空），对用户不够直观

* 前端需要额外说明

***

## 四、最终推荐方案

### 4.1 采用方案 A（显式模式），但简化实现

**核心思路**：新增 `mac_prefix` 作为新的 `pattern_type`，同时将"忽略 MAC"作为现有 IP 模式的**显式可选属性**。

#### 具体改动清单

| 层级          | 文件                               | 改动                                                                                                                |
| ----------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **模型**      | `models/whitelist.py`            | `pattern_type` 字段无需修改                                                                                             |
| **Schema**  | `schemas/terminal.py`            | `WhitelistCreate.pattern_type` 增加 `Literal["mac_prefix", "single_ip", "cidr", "ip_range", "mac_only", "both"]` 校验 |
| **Service** | `services/compliance_service.py` | `_match_whitelist_in_memory()` 新增 `mac_prefix` 匹配分支；`_ip_matches_pattern()` 对 `ip_only` 类型的路由                     |
| **Service** | `services/terminal_service.py`   | `create_whitelist()` 中新增 `mac_prefix` 模式的 MAC 前缀格式校验                                                              |
| **前端**      | `pages/Whitelist.tsx`            | 添加/编辑表单中 Pattern Type 下拉增加 `MAC Prefix` 选项；选择时显示 MAC 前缀提示                                                         |
| **前端**      | `constants.ts`                   | API 路径不变                                                                                                          |
| **i18n**    | `locales/{zh,en,ja}.ts`          | 新增 `macPrefix` 相关翻译                                                                                               |

#### 实现步骤

```
Step 1: 扩展 WhitelistCreate schema 的 pattern_type 枚举
Step 2: 实现 _match_whitelist_in_memory() 中的 mac_prefix 匹配
Step 3: 添加 MAC 前缀格式校验（3-5 段 MAC）
Step 4: 更新前端 Pattern Type 下拉选项
Step 5: 添加 i18n 翻译
Step 6: 端到端测试
```

***

## 五、兼容性分析

### 5.1 向后兼容性

| 场景        | 影响                           |
| --------- | ---------------------------- |
| 现有白名单数据   | ✅ 无影响，新 `pattern_type` 仅新增   |
| 现有 API 调用 | ✅ 无影响，`pattern_type` 参数新增可选值 |
| 前端现有功能    | ✅ 无影响，下拉框新增选项                |
| 合规计算结果    | ✅ 仅对新增模式生效，现有模式行为不变          |

### 5.2 导出/导入兼容性

| 场景          | 影响                                       |
| ----------- | ---------------------------------------- |
| CSV 导出      | ✅ 无影响，`pattern_type` 字段原样导出              |
| CSV 导入      | ⚠️ 需支持新 `pattern_type` 值，导入时需校验 MAC 前缀格式 |
| ZIP/JSON 导入 | ✅ 无影响，`pattern_type` 字段原样导入              |

### 5.3 备份恢复兼容性

现有备份文件中的 `pattern_type` 字段为 `single_ip`/`cidr`/`ip_range`/`mac_only`/`both`，恢复时不会产生冲突。

***

## 六、风险点与缓解措施

| 风险                             | 影响                                                  | 缓解措施                            |
| ------------------------------ | --------------------------------------------------- | ------------------------------- |
| MAC 前缀过于宽泛（如 AA:BB）            | 可能导致误匹配                                             | 限制至少 3 段（OUI 级别），前端校验提示         |
| `mac_prefix` 与现有 `mac_only` 冲突 | 用户可能混淆                                              | 前端清晰区分描述，文档说明差异                 |
| 性能影响                           | 前缀匹配比精确匹配稍慢                                         | 白名单数据量有限（通常 <10000 条），内存匹配影响可忽略 |
| 与 IPGuard 的优先级                 | 白名单 bypass 优先级 > IPGuard compliant > non\_compliant | 不改变优先级，保持现有逻辑                   |

***

## 七、后续扩展考虑

1. **MAC 前缀通配符**：未来可支持 `AA:BB:CC:*:*:*` 格式（如仅指定 OUI + 部分段）
2. **网段+MAC 前缀组合**：`pattern_type = mac_prefix_in_cidr`（MAC 前缀 + CIDR 双条件）
3. **时间窗口白名单**：在现有基础上扩展有效期字段（生效时间/过期时间）
4. **优先级白名单**：多条匹配时按优先级取最高的 bypass 规则

