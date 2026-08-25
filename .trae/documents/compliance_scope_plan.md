# 合规计算策略：范围条件匹配实施方案

> 文档版本：v2.0  更新日期：2026-08-19
> 变更说明：修正数据流架构——范围条件在白名单检查之后执行

---

## 一、需求重定义

### 1.1 核心诉求

用户要求在合规计算流程中引入"范围条件"策略层：

| 场景 | 范围条件 | 终端 IP/MAC | 合规计算行为 |
|------|---------|------------|-------------|
| 在范围内 | IP CIDR: `192.168.0.0/16` | IP=`192.168.1.100`, MAC=`AA:BB:CC:DD:EE:FF` | **只检查 IP，忽略 MAC** |
| 在范围内 | MAC 前缀: `AA:BB:CC` | IP=`10.0.0.5`, MAC=`AA:BB:CC:11:22:33` | **只检查 IP，忽略 MAC** |
| 不在范围内 | （无匹配的范围条件） | IP=`10.0.0.5`, MAC=`11:22:33:44:55` | **保持现有逻辑（IP+MAC 联合检查）** |

### 1.2 职责划分（关键修正）

| 组件 | 职责 | 作用阶段 |
|------|------|---------|
| **白名单** | 过滤——哪些终端**跳过**合规计算 | **前置**：最先检查，命中则直接 bypass |
| **范围条件** | 策略——决定剩余终端**用什么方式**参与计算 | **中置**：白名单之后，IPGuard 之前 |
| **IPGuard** | 基线——作为合规判定的最终依据 | **后置**：范围条件之后，作为兜底判定 |

---

## 二、系统架构分析

### 2.1 当前合规计算数据流

```
终端 IP + MAC
    │
    ▼
┌───────────────────────┐
│  白名单检查            │  ← 前置过滤
│  _match_whitelist_    │     命中 → bypass（不再检查后续）
│  in_memory()          │
│  （IP + MAC 联合匹配） │
└──────────┬────────────┘
           │ 未命中
           ▼
┌───────────────────────┐
│  IPGuard 基线检查      │  ← 兜底判定
│  _match_ipguard_      │     命中 → compliant
│  in_memory()          │     未命中 → non_compliant
│  （IP + MAC 精确匹配） │
└───────────────────────┘
```

### 2.2 引入范围条件后的数据流（修正）

```
终端 IP + MAC
    │
    ▼
┌───────────────────────────────────┐
│  ① 白名单检查（前置过滤）          │
│  _match_whitelist_in_memory()     │
│  （IP + MAC 联合匹配）             │
│  命中 → bypass（不再往下走）      │
└──────────┬────────────────────────┘
           │ 未命中（继续合规计算）
           ▼
┌───────────────────────────────────┐
│  ② 范围条件检查（新增 · 策略选择）  │
│  _check_scope_match()             │
│  检查终端是否在某个范围条件内       │
└──────┬────────────────────────────┘
       │
    ┌──┴──┐
    ▼     ▼
  在范围内  不在范围内
    │        │
    ▼        ▼
┌──────┐  ┌────────────────────────────┐
│ 仅IP │  │  ③ IPGuard 基线检查（兜底） │
│ 匹配 │  │  _match_ipguard_in_memory()│
│      │  │  （IP + MAC 精确匹配）      │
│      │  │  命中 → compliant           │
│      │  │  未命中 → non_compliant     │
└──┬───┘  └──────────┬─────────────────┘
   │ 命中           │ 命中
   ▼                ▼
  compliant       compliant
                  或 non_compliant
```

**核心逻辑说明**：
1. **白名单优先**：命中白名单的终端直接 bypass，不参与后续流程
2. **范围条件决定策略**：在白名单之后、IPGuard 之前，根据范围条件决定"如何检查"
3. **范围内**：IPGuard 检查时**只匹配 IP**，忽略 MAC
4. **范围外**：IPGuard 检查时保持**现有 IP+MAC 精确匹配**
5. **IPGuard 兜底**：无论是否在范围内，最终判定依据都是 IPGuard 基线数据

---

## 三、数据模型设计

### 3.1 新增模型：`ComplianceScope`

**文件**：`backend/app/models/compliance_scope.py`

```python
class ComplianceScope(Base):
    """
    合规计算范围条件（策略层）。
    当终端 IP/MAC 落入此范围时，合规计算只检查 IP 地址，忽略 MAC 地址。
    
    scope_type: 'ip_cidr' | 'ip_range' | 'mac_prefix'
    scope_value: 
      - ip_cidr: '192.168.0.0/16'
      - ip_range: '192.168.1.1-255'  
      - mac_prefix: 'AA:BB:CC'
    """
    __tablename__ = "compliance_scope"
    
    id = Column(Integer, primary_key=True, index=True)
    scope_type = Column(String(20), nullable=False, index=True)  
    scope_value = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(UTC))
```

### 3.2 数据库迁移

需要创建 Alembic 迁移脚本：
- 创建 `compliance_scope` 表
- 索引：`scope_type` + `is_active`

---

## 四、后端实现计划

### 4.1 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/models/compliance_scope.py` | 合规范围数据模型 |
| `backend/app/schemas/compliance_scope.py` | Pydantic schemas |
| `backend/app/services/compliance_scope_service.py` | 范围条件 CRUD + 匹配逻辑 |
| `backend/app/api/v1/endpoints/compliance_scope.py` | REST API 端点 |
| `backend/migrations/..._compliance_scope.py` | Alembic 迁移脚本 |

### 4.2 修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/services/compliance_service.py` | 在白名单检查之后、IPGuard 检查之前增加范围判断逻辑 |
| `backend/app/services/terminal_service.py` | 集成范围检查 |
| `backend/app/main.py` | 注册新路由 |

### 4.3 核心逻辑变更

#### `compliance_service.py` — 范围检查在白名单之后执行

```python
# 新增方法
async def _load_scope_cache(self) -> list[dict]:
    """加载所有活跃的合规范围条件"""

def _check_in_scope(self, scopes: list[dict], ip_address: str, mac_address: str) -> bool:
    """
    检查终端是否落在某个范围条件内。
    返回 True 表示该终端应该使用"仅 IP"策略。
    """

# ===== 修正后的 check_compliance() 流程 =====
async def check_compliance(self, ip_address: str, mac_address: str) -> dict:
    # Step 1: 白名单检查（前置过滤）
    whitelist_hit = await self._check_whitelist(ip_address, mac_address)
    if whitelist_hit:
        return {"compliance_status": "bypass", "wl_match_type": ...}

    # Step 2: 范围条件检查（策略选择）
    scope_data = await self._load_scope_cache()
    use_ip_only = self._check_in_scope(scope_data, ip_address, mac_address)

    # Step 3: IPGuard 基线检查（兜底）
    if use_ip_only:
        ipguard_hit = await self._check_ipguard_ip_only(ip_address)
    else:
        ipguard_hit = await self._check_ipguard(ip_address, mac_address)

    # Step 4: 结果判定
    if ipguard_hit:
        return {"compliance_status": "compliant"}
    else:
        return {"compliance_status": "non_compliant"}
```

### 4.4 API 端点

```
GET    /api/v1/compliance-scope/           # 列表
POST   /api/v1/compliance-scope/           # 创建
GET    /api/v1/compliance-scope/{id}        # 详情
PUT    /api/v1/compliance-scope/{id}        # 更新
DELETE /api/v1/compliance-scope/{id}        # 删除
POST   /api/v1/compliance-scope/{id}/toggle # 启用/禁用
```

---

## 五、前端实现计划

### 5.1 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/api/complianceScope.ts` | API hooks |
| `frontend/src/pages/ComplianceScope.tsx` | 范围条件管理页面 |

### 5.2 修改文件

| 文件 | 改动 |
|------|------|
| `frontend/src/lib/constants.ts` | 添加 API 端点常量 |
| `frontend/src/i18n/locales/{zh,en,ja}.ts` | 添加翻译 |
| `frontend/src/App.tsx` | 添加路由 |

### 5.3 UI 设计

**范围条件管理页面**：
- 列表视图：显示所有范围条件
- 添加/编辑表单：
  - 范围类型下拉：IP CIDR / IP 范围 / MAC 前缀
  - 范围值输入：根据类型动态显示提示
  - 描述字段
  - 启用/禁用开关

---

## 六、实施步骤

```
Step 1: 创建数据模型 compliance_scope.py
Step 2: 创建 Alembic 迁移脚本
Step 3: 创建 Pydantic schemas
Step 4: 创建 CRUD service
Step 5: 创建 REST API 端点
Step 6: 修改 compliance_service.py（白名单后增加范围检查）
Step 7: 修改 terminal_service.py 集成
Step 8: 注册路由到 main.py
Step 9: 创建前端 API hooks
Step 10: 创建前端管理页面
Step 11: 添加 i18n 翻译
Step 12: 编译验证 + 功能测试
```

---

## 七、风险与考虑

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 性能影响 | 范围检查增加每次合规计算的开销 | 范围数据量有限（通常 <50 条），使用 Redis 缓存 |
| 与现有白名单冲突 | 范围条件可能与白名单条目重叠 | 白名单优先级更高（先检查白名单，命中则跳过范围检查） |
| 数据迁移 | 现有数据库无此表 | Alembic 迁移，向后兼容 |
| 范围条件过于宽泛 | 一个 /0 网段会影响所有终端 | 限制最小 CIDR 为 /24，前端警告提示 |
| MAC 前缀过于宽泛 | `AA:BB` 级别可能影响大量终端 | 限制至少 3 段 MAC（OUI 级别） |
| 缓存一致性 | 范围条件变更后需要刷新缓存 | 变更后自动 invalidate 并触发重算 |

---

## 八、典型场景

### 场景 1：OA 网段全部信任
```
白名单：office-printer (MAC 精确匹配)
范围条件：IP CIDR = 192.168.0.0/16

OA 网段终端：
  1. 先查白名单 → 命中打印机 → bypass
  2. 其他 OA 终端 → 查范围 → 在范围内 → IPGuard 仅匹配 IP → compliant/non_compliant
  
非 OA 网段终端：
  1. 查白名单 → 未命中
  2. 查范围 → 不在范围内 → IPGuard IP+MAC 精确匹配 → compliant/non_compliant
```

### 场景 2：打印机网段 MAC 不稳定
```
范围条件：IP CIDR = 192.168.50.0/24
打印机网段终端：只检查 IP 匹配（MAC 变化不影响判定）
其他终端：保持 IP+MAC 联合检查
```

### 场景 3：特定厂商设备按 OUI 信任
```
范围条件：MAC 前缀 = AA:BB:CC（某厂商 OUI）
该厂商设备：只检查 IP 匹配
其他设备：保持 IP+MAC 联合检查
```
