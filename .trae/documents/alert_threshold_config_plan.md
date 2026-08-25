# 事件告警阈值参数前端可配置化方案

## 概述

将通知事件系统中所有硬编码的阈值参数提取为系统配置项，支持从前端「通用设置」页面自定义配置。

## 当前状态分析

通过代码审查，发现以下 **4 个硬编码阈值** 散布在后端代码中：

| # | 硬编码值  | 位置                                                                                                                                             | 含义                          | 默认值  |
| - | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ---- |
| 1 | `0.8` | [main.py#L338](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py#L338)                                              | 合规率告警阈值（低于此值触发告警）           | 80%  |
| 2 | `0.5` | [event\_emitter.py#L281](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/event_emitter.py#L281)                  | 合规率危险比例（低于阈值×此比例为 critical） | 50%  |
| 3 | `50`  | [compliance\_service.py#L590](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L590)        | 单次自动封锁数量告警阈值                | 50 台 |
| 4 | `3`   | [arp\_collector\_service.py#L415](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py#L415) | 终端离线检测倍数（ARP采集间隔×此值=离线阈值）   | 3 倍  |

### 现有配置系统架构

* **后端模型**: `SystemConfig` 表，字段含 key/value/category/value\_type/description/is\_readonly

* **配置分类枚举**: `ConfigCategory` (security, rate\_limit, auth, network, scheduler, general, logging, branding, email, compliance, cache)

* **配置读取**: `ConfigService.get(key)` 或模块级 `get_config_value(key, default)` — Redis 缓存 → DB → .env 回退

* **分组返回**: `get_all_grouped()` 返回 `AllConfigsResponse`，前端按分类渲染

* **前端页面**: [GeneralSettings.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/GeneralSettings.tsx)，通过 `SECTION_FIELDS` 映射分类→字段列表，`Field` 组件根据 `value_type` 自动渲染输入控件

* **前端类型**: [useTerminalData.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/hooks/useTerminalData.ts) 定义 `AllConfigs` 接口

* **i18n**: zh.ts / en.ts / ja.ts 中以 `config.{key}` 和 `config.${key}Desc` 格式定义标签

## 方案设计

### 新增配置分类：`alert`

在现有 `ConfigCategory` 枚举中新增 `ALERT = "alert"` 分类，专门管理告警阈值参数。这 4 个参数都与"何时触发告警通知"相关，语义上独立于 compliance（合规策略）和 scheduler（调度间隔）。

### 新增配置项（4 项）

| key                                  | value | value\_type | category | description                 | 范围      |
| ------------------------------------ | ----- | ----------- | -------- | --------------------------- | ------- |
| `alert_compliance_rate_threshold`    | `0.8` | string      | alert    | 合规率告警阈值（0-1，低于此值触发告警）       | 0.0-1.0 |
| `alert_compliance_critical_ratio`    | `0.5` | string      | alert    | 合规率危险比例（低于阈值×此比例触发严重告警）     | 0.0-1.0 |
| `alert_block_count_threshold`        | `50`  | int         | alert    | 单次自动封锁数量告警阈值                | 1-10000 |
| `alert_offline_threshold_multiplier` | `3`   | int         | alert    | 终端离线检测倍数（ARP采集间隔×此值=离线判定秒数） | 1-10    |

> `alert_compliance_rate_threshold` 和 `alert_compliance_critical_ratio` 使用 string 类型（存浮点数），因为现有配置系统的 value\_type 仅支持 string/int/bool/json，不包含 float。读取时用 `float()` 转换。

## 修改步骤

### 1. 后端 Schema：新增 ALERT 分类和响应模型

**文件**: [system\_config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/system_config.py)

* `ConfigCategory` 枚举添加 `ALERT = "alert"`

* 新增 `AlertConfigResponse` 模型，含 4 个字段

* `AllConfigsResponse` 添加 `alert: AlertConfigResponse` 字段

### 2. 后端 Service：新增默认配置和分组返回

**文件**: [config\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/config_service.py)

* `DEFAULT_CONFIGS` 列表中添加 4 条新配置项（category="alert"）

* `get_all_grouped()` 方法中添加 `alert=AlertConfigResponse(...)` 构造逻辑

### 3. 后端业务代码：替换硬编码为配置读取

#### 3a. 合规率告警阈值

**文件**: [main.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/main.py) \~L330-339

```python
# Before:
threshold=0.8,

# After:
from app.services.config_service import get_config_value
alert_threshold = float(await get_config_value("alert_compliance_rate_threshold", 0.8))
await emit_compliance_alert(
    compliance_rate=rate,
    non_compliant_count=result.non_compliant,
    threshold=alert_threshold,
)
```

#### 3b. 合规率危险比例

**文件**: [event\_emitter.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/event_emitter.py) \~L275-296

```python
# Before:
is_critical = compliance_rate < threshold * 0.5

# After:
from app.services.config_service import get_config_value
critical_ratio = float(await get_config_value("alert_compliance_critical_ratio", 0.5))
is_critical = compliance_rate < threshold * critical_ratio
```

> 注意：`emit_compliance_alert` 是 async 函数，可以直接 await `get_config_value`。

#### 3c. 自动封锁数量阈值

**文件**: [compliance\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py) \~L588-592

```python
# Before:
block_threshold = 50
if blocked > block_threshold:

# After:
from app.services.config_service import get_config_value
block_threshold = await get_config_value("alert_block_count_threshold", 50)
if blocked > block_threshold:
```

#### 3d. 终端离线检测倍数

**文件**: [arp\_collector\_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/arp_collector_service.py) \~L411-415

```python
# Before:
offline_threshold_seconds = interval * 3

# After:
from app.services.config_service import get_config_value
offline_multiplier = await get_config_value("alert_offline_threshold_multiplier", 3)
offline_threshold_seconds = interval * offline_multiplier
```

### 4. 前端类型定义

**文件**: [useTerminalData.ts](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/hooks/useTerminalData.ts) \~L352-371

* 新增 `AlertConfig` 接口（4 个字段）

* `AllConfigs` 接口添加 `alert: AlertConfig` 字段

### 5. 前端设置页面

**文件**: [GeneralSettings.tsx](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/GeneralSettings.tsx)

* `SECTION_FIELDS` 添加 `alert` 分组及 4 个字段名

* `flattenConfigs` 的 `allGroups` 数组添加 `configs.alert`

* 新增 alert 分组的 SectionCard 渲染（图标用 `Bell` 或 `AlertTriangle`）

### 6. 前端 i18n

**文件**: zh.ts, en.ts, ja.ts

添加 4 组标签（key + keyDesc）：

```
alert: '告警阈值配置'
alertDesc: '通知事件告警触发阈值参数'
alert_compliance_rate_threshold: '合规率告警阈值'
alert_compliance_rate_thresholdDesc: '合规率低于此值时触发告警（0-1，如0.8表示80%）'
alert_compliance_critical_ratio: '合规率危险比例'
alert_compliance_critical_ratioDesc: '合规率低于阈值×此比例时触发严重告警（0-1，如0.5表示50%）'
alert_block_count_threshold: '封锁数量告警阈值'
alert_block_count_thresholdDesc: '单次自动封锁终端数超过此值时触发告警'
alert_offline_threshold_multiplier: '离线检测倍数'
alert_offline_threshold_multiplierDesc: 'ARP采集间隔×此倍数=终端离线判定秒数'
```

## 风险与注意事项

1. **`emit_compliance_alert`** **改为读取配置**：该函数已有 `async` 修饰，添加 `await get_config_value()` 不改变签名。但需确保 Redis 不可用时有正确的 fallback（`get_config_value` 已有 try/except 回退到 DB 和默认值）。

2. **配置缓存延迟**：ConfigService 使用 Redis 缓存（TTL 300 秒），修改配置后最长可能有 5 分钟延迟才生效。`set()` 方法已包含缓存失效逻辑，所以通过 API 修改的配置会立即生效。

3. **数据库种子初始化**：新配置项通过 `seed_defaults()` 在服务启动时自动插入。已有数据库只需重启服务即可获得新配置项（`seed_defaults` 是幂等的，跳过已存在的 key）。

4. **float 类型存储**：`alert_compliance_rate_threshold` 和 `alert_compliance_critical_ratio` 使用 string 类型存储浮点数（如 "0.8"），前端 number input 渲染时需确保 string↔number 转换正确。现有 `Field` 组件对 string 类型渲染为 text input，需要在前端为这两个字段特殊处理为 number input 或在 i18n description 中提示用户输入小数。

   **解决方案**：将这两个字段也设为 `int` 类型，存储百分比值（如 80 表示 80%），后端读取时除以 100。这样前端可直接用 number input，与现有 int 字段渲染逻辑一致。

   **修订配置项定义**：

   | key                                  | value | value\_type | description               |
   | ------------------------------------ | ----- | ----------- | ------------------------- |
   | `alert_compliance_rate_threshold`    | `80`  | int         | 合规率告警阈值（%，低于此值触发告警）       |
   | `alert_compliance_critical_ratio`    | `50`  | int         | 合规率危险比例（%，低于阈值×此比例触发严重告警） |
   | `alert_block_count_threshold`        | `50`  | int         | 单次自动封锁数量告警阈值              |
   | `alert_offline_threshold_multiplier` | `3`   | int         | 终端离线检测倍数                  |

   **后端读取逻辑调整**：

   * main.py: `threshold = (await get_config_value("alert_compliance_rate_threshold", 80)) / 100.0`

   * event\_emitter.py: `critical_ratio = (await get_config_value("alert_compliance_critical_ratio", 50)) / 100.0`

## 验证步骤

1. `python -m py_compile` 检查修改的 3 个后端文件语法
2. 前端 TypeScript 编译检查
3. VS Code 诊断检查所有修改文件
4. `manage.sh update` 重新构建验证
5. 功能验证：

   * 系统设置页面出现「告警阈值配置」分区，含 4 个可编辑字段

   * 修改合规率阈值 → 触发定时合规检查 → 确认告警按新阈值触发

   * 修改离线检测倍数 → 确认终端离线判定时间相应变化

