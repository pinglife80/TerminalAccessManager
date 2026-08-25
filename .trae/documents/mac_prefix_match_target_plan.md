# MAC 前缀匹配对象区分（ARP vs IPGuard）实施方案

## 1. 需求分析

### 1.1 现状
当前 Compliance Scope 的 `mac_prefix` 类型仅匹配 ARP 数据源的终端 MAC，匹配成功后该终端使用 IP-only 策略匹配 IPGuard 基线。

### 1.2 需求
需要区分 MAC 前缀的匹配对象：
- **ARP 数据源 MAC 前缀**：匹配 ARP 采集的终端 MAC → 终端自身使用 IP-only 策略
- **合规基线（IPGuard）MAC 前缀**：匹配 IPGuard 基线中的 MAC → 这些基线记录在被匹配时只需 IP 匹配即可

### 1.3 业务场景理解
- **场景 A（现有）**：某类终端（如虚拟机、特殊设备）MAC 经常变化但 IP 固定，通过 ARP MAC 前缀标记这些终端，允许其 IP 直接匹配基线
- **场景 B（新增）**：IPGuard 中某些网段/部门的设备 MAC 登记不严格，只需 IP 匹配即可视为合规，通过 IPGuard MAC 前缀标记这些基线条目

---

## 2. 技术方案

### 2.1 数据模型变更

#### 2.1.1 扩展 ScopeType
```python
# 原有: ScopeType = Literal["ip_cidr", "ip_range", "mac_prefix"]
# 新增后:
ScopeType = Literal["ip_cidr", "ip_range", "mac_prefix_arp", "mac_prefix_ipguard"]
```

- `mac_prefix_arp`：原有 `mac_prefix` 重命名，匹配 ARP 终端 MAC
- `mac_prefix_ipguard`：新增，匹配 IPGuard 基线 MAC

> **迁移处理**：数据库中已有的 `scope_type='mac_prefix'` 记录需要迁移为 `mac_prefix_arp`，保持向后兼容。

### 2.2 数据库迁移
新增 Alembic 迁移脚本：
1. 将现有 `scope_type='mac_prefix'` 更新为 `mac_prefix_arp`
2. 不修改表结构，仅更新数据

### 2.3 匹配逻辑变更

#### 2.3.1 ARP MAC 前缀（`mac_prefix_arp`）
- 匹配位置：`_check_in_scope()` 中对终端 MAC 进行匹配（现有逻辑，重命名）
- 效果：终端 IP 匹配 IPGuard 时忽略 MAC（现有 IP-only 策略）

#### 2.3.2 IPGuard MAC 前缀（`mac_prefix_ipguard`）
- 匹配位置：IPGuard 匹配逻辑中（`_match_ipguard_in_memory` 等）
- 效果：在对比 IPGuard 条目时，如果该 IPGuard 条目的 MAC 匹配任何 `mac_prefix_ipguard` 条件，则仅比较 IP 即可判定匹配
- 实现方式：IPGuard 匹配时分两层检查：
  1. 精确 IP+MAC 匹配（现有）
  2. IP 匹配且 IPGuard 条目的 MAC 匹配 `mac_prefix_ipguard` 前缀（新增）

### 2.4 匹配流程更新

```
合规检查流程（更新后）:
1. 白名单检查 → bypass（不变）
2. 加载 Scope 条件
   - 分离 arp_scope（ip_cidr, ip_range, mac_prefix_arp）
   - 分离 ipguard_scope（mac_prefix_ipguard）
3. 检查终端是否在 arp_scope 内 → use_ip_only_for_terminal
4. IPGuard 基线匹配：
   a. 如果 use_ip_only_for_terminal → IP 精确匹配即可（现有 IP-only）
   b. 否则 → IP+MAC 精确匹配（现有）
   c. 新增：IP 精确匹配且 IPGuard.MAC 匹配 mac_prefix_ipguard → 视为匹配
```

---

## 3. 涉及文件修改

### 3.1 Backend

| 文件 | 修改内容 |
|------|----------|
| `backend/app/models/compliance_scope.py` | 更新 docstring 中的 scope_type 说明 |
| `backend/app/schemas/compliance_scope.py` | `ScopeType` 扩展为 `mac_prefix_arp` / `mac_prefix_ipguard` |
| `backend/app/services/compliance_scope_service.py` | 更新验证逻辑，支持两种 MAC 前缀类型（格式验证相同） |
| `backend/app/services/compliance_service.py` | 重构 `_check_in_scope` 和 IPGuard 匹配逻辑，分离两种 MAC 前缀匹配 |
| `backend/alembic/versions/032_*.py` | 数据迁移：`mac_prefix` → `mac_prefix_arp` |
| `backend/app/api/v1/endpoints/compliance_scope.py` | 无需修改（类型透传） |

### 3.2 Frontend

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/api/complianceScope.ts` | 更新类型定义 |
| `frontend/src/pages/ComplianceScope.tsx` | 添加两种 MAC 前缀选项、更新描述和验证提示 |
| `frontend/src/i18n/locales/zh.ts` | 新增翻译键 |
| `frontend/src/i18n/locales/en.ts` | 新增翻译键 |
| `frontend/src/i18n/locales/ja.ts` | 新增翻译键 |

---

## 4. 实施步骤

### Phase 1: 数据库迁移与模型更新
1. 创建 Alembic 迁移脚本 `032_mac_prefix_scope_type_split.py`
   - 将现有 `scope_type='mac_prefix'` 数据更新为 `mac_prefix_arp`
2. 更新 Model docstring
3. 更新 Schema 中的 `ScopeType` 类型定义

### Phase 2: 后端服务逻辑更新
1. 更新 `compliance_scope_service.py` 验证逻辑（支持两种 mac_prefix 类型）
2. 重构 `compliance_service.py`：
   - `_load_scope_cache()` 返回的 scope 数据保持不变
   - `_check_in_scope()` 重命名/调整为 `_check_terminal_in_arp_scope()`，仅处理 ip_cidr/ip_range/mac_prefix_arp
   - 新增 `_check_ipguard_entry_in_scope()` 检查 IPGuard MAC 是否匹配 mac_prefix_ipguard
   - 更新 `_match_ipguard_in_memory`：增加 IP+IPGuard MAC 前缀匹配路径
   - 更新 `_match_ipguard_ip_only_in_memory`：保持不变
   - 更新 `check_compliance()`、`batch_check_compliance()`、`auto_unblock_compliant()` 中的调用

### Phase 3: 前端更新
1. 更新 TypeScript 类型定义
2. 更新 ComplianceScope 页面下拉选项
3. 更新 i18n 翻译（中文/英文/日文）
4. 更新类型描述文字和 placeholder

### Phase 4: 缓存与测试
1. 确认缓存失效逻辑无需变更（invalidate_scope_cache 已覆盖）
2. 后端语法检查
3. 前端编译检查

---

## 5. 风险与注意事项

### 5.1 数据迁移风险
- 现有 `mac_prefix` 数据必须正确迁移为 `mac_prefix_arp`
- 迁移脚本需具备幂等性（可重复执行不报错）

### 5.2 向后兼容
- API 返回的 `scope_type` 值变更，前端需同步更新
- 如果有其他地方硬编码了 `mac_prefix` 字符串，需要一并更新

### 5.3 性能影响
- IPGuard 匹配时增加了一次前缀遍历检查，但 MAC 前缀数量通常很少（<100），性能影响可忽略
- 内存匹配方式保持 O(n*m) 但 n（scope）极小

### 5.4 逻辑优先级
- `mac_prefix_arp`（终端级别）优先级高于 `mac_prefix_ipguard`（基线级别）
- 即：如果终端已被 arp_scope 标记为 IP-only，则直接走 IP-only，不再检查 IPGuard MAC 前缀

---

## 6. 验证要点

1. **迁移验证**：现有 mac_prefix 规则是否正确迁移为 mac_prefix_arp 且功能正常
2. **ARP MAC 前缀**：原有功能不受影响
3. **IPGuard MAC 前缀**：新增规则生效，ARP 终端 IP 匹配到符合前缀的 IPGuard 记录时判定为合规
4. **组合场景**：同时配置 arp 和 ipguard mac_prefix 时逻辑正确
5. **禁用/启用**：scope 启用/禁用切换正常
6. **缓存失效**：scope 变更后缓存正确失效
