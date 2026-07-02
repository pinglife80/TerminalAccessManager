# 黑名单批量检查 API 实施方案

## Context（背景）

**问题**：Terminals 页面通过 `useBlacklist({ skip: 0, limit: 200 })` 拉取全量黑名单在前端做匹配，用于标记终端是否在黑名单中。但后端 `GET /blacklist/` 限制 `limit ≤ 200`，导致第 201 条之后的黑名单无法被匹配，是逻辑缺陷（曾用 `limit: 9999` 导致 422 错误）。

**目标**：采用方案 C——新增批量检查 API，前端只发送当前页终端的 MAC/IP 列表，后端用索引化 `IN()` 查询返回命中条目。消除 200 条上限，降低网络传输量。

**影响范围**：仅改造 Terminals 页面的黑名单数据获取方式；Blacklist.tsx 管理页面（CRUD/分页/导出）不受影响，继续使用原 `useBlacklist`。

## 改造前后数据流对比

```
改造前: GET /blacklist/?skip=0&limit=200 → 最多 200 条全量记录 → 前端遍历匹配
改造后: POST /blacklist/check {macs:[...], ips:[...]} → 仅命中条目(0-10条) → 前端遍历匹配
```

## 实施步骤

### 步骤 1：后端新增 Schema

文件：`backend/app/schemas/terminal.py`（在 `BlacklistQuery` 之后新增）

```python
class BlacklistCheckRequest(BaseModel):
    """Request body for batch blacklist check"""
    mac_addresses: list[str] = Field(default_factory=list)
    ip_addresses: list[str] = Field(default_factory=list)


class BlacklistCheckItem(BaseModel):
    """A single blacklist match result"""
    mac_address: str | None = None
    ip_address: str | None = None
    firewall_tag: str | None = None
```

### 步骤 2：后端新增 Service 方法

文件：`backend/app/services/terminal_service.py`（Blacklist 区块内，复用模块级 `_normalize_mac` 第 27 行）

新增 `check_blacklist` 方法：
- 用 `_normalize_mac()` 将输入 MAC 转为 12 位大写形式，匹配 `mac_address_normalized` 列
- 用 `set()` 去重输入
- active 判定：`auto_unblocked == False AND (expires_at >= now OR expires_at IS NULL)`
- 查询模式参考第 1200-1209 行 `cleanup_expired_blacklist` 中的 `IN()` 批量查询
- 用 `select(Blacklist.mac_address, Blacklist.ip_address, Blacklist.firewall_tag)` 只查 3 列
- 返回 `list[dict]`，每项含 `mac_address`、`ip_address`、`firewall_tag`

### 步骤 3：后端新增端点

文件：`backend/app/api/v1/endpoints/blacklist.py`

```python
@router.post("/check", response_model=list[BlacklistCheckItem])
async def check_blacklist(
    request: BlacklistCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:read"))
):
    service = TerminalService(db)
    results = await service.check_blacklist(
        mac_addresses=request.mac_addresses,
        ip_addresses=request.ip_addresses,
    )
    return results
```

- 路径 `POST /blacklist/check`，权限 `blacklist:read`（只读）
- 与 `DELETE /{identifier}` 方法不同，无路由冲突

### 步骤 4：前端新增常量与 Hook

文件 1：`frontend/src/lib/constants.ts`（第 48 行后新增）
```typescript
BLACKLIST_CHECK: '/blacklist/check',
```

文件 2：`frontend/src/hooks/useTerminalData.ts`（`useBlacklist` 之后新增）
- 新增 `BlacklistCheckItem` 接口（3 字段：mac_address, ip_address, firewall_tag）
- 新增 `BlacklistCheckParams` 接口
- 新增 `useBlacklistCheck` hook：POST 请求，`enabled` 条件防止空列表请求，`placeholderData: keepPreviousData` 避免翻页闪烁

### 步骤 5：前端改造 Terminals.tsx

文件：`frontend/src/pages/Terminals.tsx`

**5.1 导入替换**（第 2 行）：`useBlacklist` → `useBlacklistCheck`

**5.2 数据获取替换**（第 154-157 行）：
- 从 `terminalsData.items` 提取 MAC/IP 列表（useMemo）
- 调用 `useBlacklistCheck({ mac_addresses, ip_addresses })`

**5.3 blackListItems 来源**（第 162 行）：`blackListData?.items ?? []` → `blackListCheckData ?? []`

**5.4 简化查找结构**（第 165-193 行）：
- `blackEntryMap` 值类型从 `{ firewall_tag, match_type }` 简化为 `string | null`
- 移除未被读取的 `match_type` 字段

**5.5 allTerminals 访问更新**（第 196-236 行）：
- `info?.firewall_tag` → 直接取 `blackEntryMap.get(key)` 的值

**5.6 refetchBlacklist 调用**：6 处调用点（第 305、332、359、382、406、453 行）保持不变。block/unblock 不改变终端 MAC/IP，queryKey 不变，`refetch()` 正确刷新。

## 关键复用点

| 复用项 | 位置 | 用途 |
|--------|------|------|
| `_normalize_mac()` | `terminal_service.py:27` | MAC 归一化为 12 位大写形式 |
| `IN()` 批量查询模式 | `terminal_service.py:1200-1209` | 单次查询替代 N 次循环 |
| `and_`, `or_` 导入 | `terminal_service.py:10` | 已导入，无需额外引入 |
| `require_permission` | `blacklist.py` 现有端点 | 权限守卫，用 `blacklist:read` |

## 边界情况处理

| 情况 | 处理 |
|------|------|
| 空 MAC/IP 列表 | 前端 `enabled: false`；后端 `match_conditions` 为空时直接返回 `[]` |
| 重复 MAC/IP | 后端 `set()` 去重 |
| MAC 格式不规范 | `_normalize_mac` 处理，不会匹配到任何 12 位标准化 MAC |
| 同一终端 MAC 和 IP 分别命中不同条目 | 后端返回多条，前端判定为 `both` |
| expires_at 为 NULL | `OR expires_at IS NULL` 防御性保留 |
| 翻页时 MAC/IP 变化 | queryKey 变化触发自动重新查询 |

## 对其他业务功能的影响评估

| 功能 | 是否受影响 | 说明 |
|------|-----------|------|
| Blacklist.tsx 管理页 | ❌ 不受影响 | 继续使用原 `useBlacklist`，完整字段+分页 |
| DeletePreviewModal.tsx | ❌ 不受影响 | 仅用 `blacklist_entries` 计数字段 |
| 审计日志/侧边栏/路由 | ❌ 不受影响 | 仅引用路径/翻译 |
| Dashboard 统计 | ❌ 不受影响 | 不依赖黑名单数据 |
| block/unblock 操作 | ❌ 不受影响 | refetch 机制保留，行为一致 |

## 验证方案

### 后端验证
```bash
# 1. 重建后端
./manage.sh rebuild backend

# 2. 空列表测试（应返回 []）
curl -s -X POST http://localhost:8080/api/v1/blacklist/check \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"mac_addresses":[],"ip_addresses":[]}'

# 3. 正常查询
curl -s -X POST http://localhost:8080/api/v1/blacklist/check \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"mac_addresses":["AA-BB-CC-DD-EE-FF"],"ip_addresses":["192.168.1.100"]}'
```

### 前端端到端验证
1. 重建前端：`./manage.sh rebuild frontend`
2. 打开 Terminals 页面，确认黑名单标记（MAC/IP/BOTH 后缀、Firewall Tag 列）正常显示
3. 翻页验证：黑名单数据随终端列表更新
4. block 操作：点击"封禁"，确认操作后出现黑名单标记
5. unblock 操作：点击"从黑名单移除"，确认标记消失
6. **回归测试**：打开 Blacklist 管理页，确认分页/搜索/CRUD 正常
7. 网络面板：确认不再有 `GET /blacklist/?skip=0&limit=200`，改为 `POST /blacklist/check`

### 性能对比
- 网络传输：从 ~200 条完整记录(~40KB) 降为 ~0-10 条精简记录(~0.8KB)
- 数据库：从全表扫描+分页 变为索引 `IN()` 查询

## 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| 串行依赖（终端数据→黑名单检查）导致加载稍慢 | 低 | 黑名单检查是索引查询 <50ms；`placeholderData` 保持旧数据 |
| `blackEntryMap` 类型变化 | 低 | 同步更新 `allTerminals` 中的访问方式 |
| `/check` 路由冲突 | 极低 | POST vs DELETE，方法不同无冲突 |
