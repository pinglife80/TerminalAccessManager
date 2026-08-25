# 合规误判审计与 IPGuard 缓存新鲜度优化计划

> 文档版本：r2  更新日期：2026-08-25

## 1. 摘要

本次对「修复元组真值 bug 后」系统内全部封锁终端做了一次全量合规复核。结论：**208 个封锁终端中 205 个判定准确，3 个误判**（误判均已自愈，当前为 compliant + unblocked）。误判根因是 **IPGuard 基线同步延迟**——`recalculate_all_compliance` 依赖的 IPGuard Redis 缓存存在最长约 15 分钟（TTL 900s + 同步间隔 600s）的时延，导致「IPGuard 外部系统延迟登记」的终端在窗口期被误判 `non_compliant` 并封锁。

本计划的核心交付是：在 `recalculate_all_compliance` 中新增 **IPGuard 缓存新鲜度门控**——当缓存陈旧时跳过降级（hold 原状态），从根上缩小误判时间窗。

## 2. 当前状态分析（审计结论）

修复部署后，终端状态分布（`terminals`）：

| compliance\_status | status    | 数量  |
| ------------------ | --------- | --- |
| bypass             | unblocked | 632 |
| compliant          | unblocked | 374 |
| non\_compliant     | blocked   | 208 |

对 208 个 `non_compliant + blocked` 终端，逐一复刻业务判定逻辑（白名单 CIDR → ARP 作用域 → IPGuard 精确/IP+MAC 匹配）对照当前 IPGuard 基线（1192 条）后：

* **205 个准确封锁**：IP+MAC 均不在 IPGuard、不在白名单、不在 ip-only 作用域。

* **3 个误判**（本应 compliant 却被封锁，现已自愈为 compliant + unblocked）：

  * `10.8.13.147 / A8-93-4A-2E-B5-C9`（source\_tag `yp`）

  * `10.8.17.19 / E6-EF-B7-14-D6-09`（source\_tag `yp`）

  * `10.8.18.51 / 64-BC-58-41-72-5B`（source\_tag `yp`）

## 3. 根因分析

### 3.1 证据链（时间线，均为北京时间）

| 时间             | 事件                                                                         | 依据                                                                                                      |
| -------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| 14:14 \~ 14:20 | 修复后 recalculate 纠正 bug 误判：这 3 个终端 `ipguard=False` → 判 `non_compliant` → 封锁 | 后端日志 `misclassification corrected ... ipguard=False`；blacklist reason `IP 和 MAC 都不合规` / `IP 不合规，MAC 合规` |
| 14:23:58       | IPGuard 同步完成，这 3 个 IP+MAC 写入缓存                                             | `compliance_baselines.last_sync_at = 14:23:58`                                                          |
| 14:29:42       | 下一轮 recalculate 判 `compliant` → 自动解封（自愈）                                   | terminal `updated_at = 14:29:42`，`compliance_status = compliant`，`status = unblocked`                   |

### 3.2 关键证据修正

* 这 3 个终端 `timestamp` 为 **5\~6 天前**（`08-19` / `08-20` / `08-24`），**并非新上线**。

* 这 3 个终端 `ip_changed_at` 为 **NULL**，**并非换 IP**。

因此，现有两道防线都没有覆盖它们：

1. **IP 变更宽限期**（`recalculate_all_compliance` L2054，仅当 `ip_changed_at is not None` 才生效）不触发。
2. **反振荡确认阈值**（`compliance_confirm_threshold=2`，约 2 个周期 10 分钟）短于 IPGuard 同步时延（最长 15 分钟），不足以等待缓存刷新。

### 3.3 根本原因

`recalculate_all_compliance` 依赖 IPGuard Redis 缓存（`_load_all_ipguard_cache`，缓存 TTL 900s）做判定，而缓存由 `scheduled_ipguard_sync`（间隔 600s）刷新。当终端在 IPGuard 外部系统里「延迟登记」时，缓存窗口期缺失其 IP+MAC 映射，recalculate 即误判为 `non_compliant`。核心缺陷是缺失「缓存新鲜度」判断，使用陈旧缓存直接就降级。

## 4. 拟议变更

> 说明：用户原选「新终端首见宽限期」，但 3.2 的新证据表明本次误判终端并非新上线，该方案对本次场景无效。因此修正为更通用的 **IPGuard 缓存新鲜度门控**，可同时覆盖「新上线」「换 IP」「系统延迟登记」三种场景。此变更单文件完成。

### 4.1 文件：`backend/app/services/compliance_service.py`

**改动 1 —— 新增可配置阈值读取方法**（仿现有 `_get_confirm_threshold` L2255 范式）

```python
async def _get_ipguard_stale_threshold_minutes(self) -> int:
    """Get IPGuard cache stale threshold from system config (default 12min)."""
    try:
        from app.services.config_service import ConfigService
        config_service = ConfigService(self.db)
        value = await config_service.get("ipguard_stale_threshold_minutes", "12")
        threshold = int(value)
        return max(5, min(60, threshold))
    except Exception:
        return 12
```

**改动 2 —— 新增缓存新鲜度判断方法**

```python
async def _is_ipguard_cache_stale(self) -> bool:
    """Return True if IPGuard cache is stale (last sync exceeds threshold)."""
    threshold = await self._get_ipguard_stale_threshold_minutes()
    stmt = select(ComplianceBaseline).where(ComplianceBaseline.enabled == True)
    result = await self.db.execute(stmt)
    baselines = result.scalars().all()
    if not baselines:
        return True
    sync_times = [b.last_sync_at for b in baselines if b.last_sync_at is not None]
    if not sync_times:
        return True  # never synced yet
    newest = max(sync_times)
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    age_minutes = (datetime.now(UTC) - newest).total_seconds() / 60.0
    return age_minutes > threshold
```

**改动 3 ——** **`recalculate_all_compliance`** **接入门控**

* 在 L1984 `ipguard_data = await self._load_all_ipguard_cache()` 之后，新增：

```python
ipguard_cache_stale = await self._is_ipguard_cache_stale()
if ipguard_cache_stale:
    logger.warning("IPGuard cache is stale; downgrades to non_compliant will be held this cycle")
```

* 在状态机降级分支（L2090 `elif not in_ip_grace_period:` 处），当 `ipguard_cache_stale` 为 True 时跳过降级、hold 原状态：

```python
elif not in_ip_grace_period:
    if ipguard_cache_stale:
        current_check_status = "compliant"
        new_compliance = old_compliance  # hold，缓存陈旧不降级
        stale_skip_count += 1
    else:
        current_check_status = "non_compliant"
        ...  # 原有 downgrade 逻辑
```

> 升级（upgrade：`non_compliant → compliant`）分支不受影响，仍可正常解封已误判的终端。

**改动 4 —— 日志与返回值补充**

* 新增局部计数 `stale_skip_count = 0`（与现有 `corrected_count` 并列，L2022 附近）。

* 最终汇总 `logger.info`（L2179 附近）与 `log_action` 消息中追加 `ipguard_cache_stale` 与 `stale_skip_count`。

* 返回值 dict 中追加 `"ipguard_cache_stale": ipguard_cache_stale`、`"stale_skip_count": stale_skip_count`。

### 4.2 文件：`backend/app/services/config_service.py`

注册新配置项，使其能落库（seeding）并同时出现在 `/settings/`（分组响应）与 `/settings/list`（扁平列表响应）中，供前端读取与编辑。

* 在 `DEFAULT_CONFIGS` 的「Compliance」分组（现有 `block_time` L147-149 之后）新增：

```python
{"key": "ipguard_stale_threshold_minutes", "value": "12", "category": "compliance",
 "value_type": "int", "description": "IPGuard cache stale threshold in minutes (5-60)",
 "is_readonly": False},
```

* 在 `get_all_grouped`（L532-535）的 `ComplianceConfigResponse(...)` 中新增字段映射：

```python
compliance=ComplianceConfigResponse(
    compliance_confirm_threshold=_val("compliance_confirm_threshold", 2),
    block_time=_val("block_time", "30d"),
    ipguard_stale_threshold_minutes=_val("ipguard_stale_threshold_minutes", 12),
),
```

### 4.3 文件：`backend/app/schemas/system_config.py`

在 `ComplianceConfigResponse`（L145-148）新增字段，使 `/settings/` 分组响应包含该项：

```python
class ComplianceConfigResponse(BaseModel):
    """Compliance policy config values"""
    compliance_confirm_threshold: int
    block_time: str
    ipguard_stale_threshold_minutes: int
```

### 4.4 文件：`frontend/src/pages/GeneralSettings.tsx`（必需）

在 `SECTION_FIELDS`（L50）的 `compliance` 分组新增该 key，使其在「合规」设置卡片中渲染为可编辑字段：

```typescript
compliance: ['compliance_confirm_threshold', 'block_time', 'ipguard_stale_threshold_minutes'],
```

> 说明：前端字段渲染由 `SECTION_FIELDS[category]` 驱动，缺这一步则该 key 不会出现在设置页，即便后端已返回数据。

### 4.5 文件：`frontend/src/hooks/useTerminalData.ts`（推荐，类型正确性）

在 `ComplianceConfig` 接口（L382-385）新增字段，保证类型一致（`flattenConfigs` 靠运行时 `Object.entries` 也能纳入，但接口应同步）：

```typescript
export interface ComplianceConfig {
  compliance_confirm_threshold: number;
  block_time: string;
  ipguard_stale_threshold_minutes: number;
}
```

## 5. 配置项

新增系统配置项 `ipguard_stale_threshold_minutes`，默认 `12`（clamp 5\~60），归入「compliance」配置组。

* **后端读取**：`compliance_service._get_ipguard_stale_threshold_minutes` 用 `config_service.get("ipguard_stale_threshold_minutes", "12")` 读取，缺省/异常回退 `12`，因此即便未落库也不影响门控逻辑运行。

* **前端展示/编辑**：需上面 4.2\~4.4 的改动，否则该项不会出现在系统设置页。4.2 的 seeding 会自动落库——`main.py` L711 启动时调用 `seed_defaults()`，后端重启后即写入新键。`value_type=int` 会以数字输入框渲染。

* **默认语义**：12 分钟略大于 IPGuard 同步间隔 600s，正常情况不触发；仅同步延迟/失败超过该窗口才 hold 降级。

* **可选（非必需）**：若需中文描述，可在 `frontend/src/i18n/locales/zh.ts` 的 `generalSettings` 下新增 `ipguard_stale_threshold_minutesDesc`，并在 `GeneralSettings.tsx` 的 `FIELD_DESC_I18N_KEYS` 注册；不注册时前端直接显示后端 description。

## 6. 假设与决策

* **门控仅作用于「降级」方向**，不阻断「升级/解封」方向，保证已误判终端能尽快自愈。

* 阈值采用可配置 + 默认值（12min），遵循项目「反硬编码」约定，范式对齐现有 `_get_confirm_threshold`。

* 不新增数据库字段，复用已有 `compliance_baselines.last_sync_at`。

* 不触发 IPGuard 同步或全量重算，避免 main.py 中已注明的「IPGuard 更新但 ARP 未刷新」竞争风险。

## 7. 验证步骤

1. `python3 -m py_compile backend/app/services/compliance_service.py` 语法校验。
2. `docker exec tam_backend python -c "import app.services.compliance_service"` 导入校验。
3. `./manage.sh rebuild backend` 重建部署；`docker exec tam_backend grep` 校验改动指纹。
4. 功能验证：构造/等待一次 IPGuard 同步延迟，确认陈旧期间不会新增误判降级，日志输出 `IPGuard cache is stale ... held`，汇总含 `stale_skip_count`。
5. 回归：确认升级/解封方向不受影响，已有误判终端（若有）仍能正常自愈。

