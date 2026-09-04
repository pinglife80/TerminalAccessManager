> 文档版本：v1.0  更新日期：2026-09-03

# 修复方案：终端页「非合规原因」标记（non_compliant_type）

## 一、摘要

诊断报告《合规状态震荡诊断与修复方案》5.1 节提出：non_compliant 徽标旁的标记应反映**真实不合规因素**（IP / MAC / BOTH），而非黑名单覆盖情况（`black_match_type`）。经核查，该改动**尚未实施**。

本计划实现 5.1 节内容：

- 后端给 `terminals` 新增结构化字段 `non_compliant_type`（`ip|mac|both`，可空）。
- 后端在 `_apply_compliance_result` 中由已计算的 `ip_found/mac_found/use_ip_only` 映射并写入该字段；compliant/bypass 时清空为 NULL。
- 通过 `TerminalResponse` 序列化暴露给前端。
- 前端 non_compliant 标识改用 `non_compliant_type` 展示；`black_match_type` 继续保留，仅用于黑名单解除时的标识符（IP/MAC）选择。

> 范围边界：本计划仅实施 5.1 节「BOTH 标签误导」修复，**不涉及** 5.2 节的震荡抑制、IPGuard 源数据、防火墙回写、IP 漂移收敛等内容。

## 二、现状与代码分析

### 2.1 数据流

1. `_apply_compliance_result`（[compliance_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1713-L2136)）在 `new_compliance == "non_compliant"` 时，已经调用 `_match_ipguard_in_memory` 得到 `(is_compliant, ip_found, mac_found)`，并据此生成 `block_reason`（`"IP 不合规，MAC 合规"` 等）写入黑名单 `reason`。
2. 但该「不合规因素」未落库到 `terminals` 的结构化字段，也没暴露给前端。
3. 前端 `Terminals.tsx` 自行用黑名单覆盖（`macInBlacklist` + `ipInBlacklist`）计算 `black_match_type`，被封锁终端因 IP/MAC 同时写入黑名单几乎恒为 `both`，故显示误导性 `(BOTH)`。

### 2.2 关键写入点（已确认）

`_apply_compliance_result` 中 [L1749-L1771](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1749-L1771) 是唯一已有的 `ip_found/mac_found/use_ip_only` 判定点，可直接复用其分支结构映射 `non_compliant_type`：

```python
if new_compliance == "non_compliant":
    scope_data = await self._load_scope_cache()
    use_ip_only = self._check_terminal_in_arp_scope(scope_data, ip_addr, mac_addr)
    use_or_match = self._check_terminal_in_or_scope(scope_data, ip_addr, mac_addr)
    ipguard_mac_prefixes = self._extract_ipguard_mac_prefixes(scope_data)

    if use_ip_only and not use_or_match:
        block_reason = "IP 不合规"            # → non_compliant_type = "ip"
    else:
        ipguard_data = await self._load_all_ipguard_cache()
        _, ip_found, mac_found = self._match_ipguard_in_memory(...)
        if not ip_found and not mac_found:       # → "both"
            block_reason = "IP 和 MAC 都不合规"
        elif not ip_found and mac_found:         # → "ip"
            block_reason = "IP 不合规，MAC 合规"
        elif ip_found and not mac_found:         # → "mac"
            block_reason = "MAC 不合规，IP 合规"
        else:                                    # both found → 不写（矛盾边缘，不出现）
            block_reason = "自动封锁：不合规"
```

后续 [L1832-L1833](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1832-L1833) 统一赋值 `terminal.compliance_status` / `terminal.wl_match_type`，是回填 `non_compliant_type` 的合适位置。

### 2.3 回滚边界（已确认）

[L2118-L2126](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L2118-L2126)：首次降级但所有防火墙封锁失败时，`compliance_status` 被静默回滚为 `old_compliance`。此处需**同步清空** `non_compliant_type`，避免出现 `compliance_status=compliant` 但 `non_compliant_type=ip` 的不一致残留。

## 三、修改方案

### 3.1 后端模型

文件：`backend/app/models/terminal.py`

在 `block_state` 列（[L41](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/models/terminal.py#L41)）附近新增列：

```python
non_compliant_type = Column(String(10), nullable=True)  # "ip" / "mac" / "both" / null（真实不合规因素）
```

### 3.2 Alembic 迁移

新建 `backend/alembic/versions/039_terminal_non_compliant_type.py`：

- `revision = '039_terminal_non_compliant_type'`
- `down_revision = '038_blacklist_unique_ip_firewall'`

```python
def upgrade() -> None:
    op.add_column('terminals', sa.Column('non_compliant_type', sa.String(length=10), nullable=True))

def downgrade() -> None:
    op.drop_column('terminals', 'non_compliant_type')
```

### 3.3 后端 Schema

文件：`backend/app/schemas/terminal.py`

在 `TerminalResponse`（[L26-L38](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/schemas/terminal.py#L26-L38)）新增字段（`block_state` 之后）：

```python
non_compliant_type: str | None = Field(None, description="Non-compliant factor: ip/mac/both/null")
```

> `TerminalResponse` 已 `from_attributes=True`，`/terminals/search`、`/terminals/{id}` 均直接返回 ORM 对象，新增列会自动序列化，无需改 endpoint 与 service 查询。

### 3.4 后端合规服务写入

文件：`backend/app/services/compliance_service.py`

1. 在 `_apply_compliance_result` 开头（`block_reason = "自动封锁：不合规"` 处，[L1749](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1749)）声明 `non_compliant_type = None`。
2. 在 `if new_compliance == "non_compliant":` 分支内，与 `block_reason` 同步赋值：
   - `use_ip_only and not use_or_match` → `non_compliant_type = "ip"`
   - `not ip_found and not mac_found` → `"both"`
   - `not ip_found and mac_found` → `"ip"`
   - `ip_found and not mac_found` → `"mac"`
   - `else`（both found）→ 保持 `None`（矛盾边缘，不显示）
3. 在 [L1832-L1833](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L1832-L1833) 的 `terminal.compliance_status = new_compliance` / `terminal.wl_match_type = new_wl_match_type` 之后，新增 `terminal.non_compliant_type = non_compliant_type`（compliant/bypass 时该值为 None，天然清空）。
4. 在首次降级封锁失败回滚分支 [L2118-L2126](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/compliance_service.py#L2118-L2126)，`terminal.compliance_status = old_compliance` 之后新增 `terminal.non_compliant_type = None`，与回滚状态保持一致。

### 3.5 前端类型

文件：`frontend/src/hooks/useTerminalData.ts`

在 `Terminal` 接口（[L18](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/hooks/useTerminalData.ts#L18)）新增字段（保留 `black_match_type`）：

```typescript
non_compliant_type: string | null;  // "ip" / "mac" / "both" / null（真实不合规因素）
```

### 3.6 前端页面展示

文件：`frontend/src/pages/Terminals.tsx`

1. 表格徽标 [L878-L880](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx#L878-L880)：将 `mac.black_match_type` 改为 `mac.non_compliant_type`：

```tsx
{mac.compliance_status === 'non_compliant' && mac.non_compliant_type && (
  <span className="ml-1 text-xs opacity-75">({mac.non_compliant_type.toUpperCase()})</span>
)}
```

2. 详情弹窗 [L1014-L1018](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx#L1014-L1018)：将条件与取值从 `black_match_type` 改为 `non_compliant_type`，标签 key 从 `terminal.blacklistMatch` 改为新的 `terminal.nonCompliantType`。

3. **保持不变**：[L357](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx#L357) 的 `blRemoveTarget.black_match_type === 'ip'` 仍用于黑名单解除标识符选择，以及 [L207-L228](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/frontend/src/pages/Terminals.tsx#L207-L228) 对 `black_match_type` 的计算，均不改动。

### 3.7 前端 i18n

分别在三个语言文件 `terminal` 命名空间下新增 `nonCompliantType`：

- `frontend/src/i18n/locales/zh.ts`：`nonCompliantType: '不合规因素',`
- `frontend/src/i18n/locales/en.ts`：`nonCompliantType: 'Non-compliant Factor',`
- `frontend/src/i18n/locales/ja.ts`：`nonCompliantType: '非適合要因',`

原有 `blacklistMatch` 保留（其它语言亦保留），避免不必要改动。

## 四、假设与决策

1. 字段取值严格采用文档 5.1 定义的 `ip|mac|both`；`use_ip_only` 场景固定为 `ip`。
2. `ip_found=True 且 mac_found=True` 却仍判 non_compliant 属矛盾边缘（正常 AND/OR 逻辑下不会出现），`non_compliant_type` 保持 NULL，前端不显示额外标记。
3. `non_compliant_type` 仅凭 `compliance_status` 状态流转写入/清空，不参与合规判定逻辑，避免影响现有判定与统计口径。
4. 封闭边界：不改 CSV 导出、不改黑名单页、不改 `black_match_type` 计算逻辑。

## 五、验证步骤

1. **后端编译**：`cd backend && python3 -m compileall app` 通过。
2. **迁移**：`./manage.sh upgrade` 执行 Alembic 039，`\d terminals` 确认 `non_compliant_type` 列存在。
3. **部署指纹校验**：`docker exec tam_backend grep -n "non_compliant_type" app/services/compliance_service.py app/models/terminal.py` 确认修复标记已生效。
4. **场景验证**（复用 4 终端场景，与 OR 匹配策略测试一致配置）：
   - 仅 IP 命中基线（MAC 命中/不命中按需）→ non_compliant 徽标显示 `(IP)`；IP-only scope → `(IP)`。
   - 仅 MAC 命中基线 → `(MAC)`。
   - IP/MAC 均不命中 → `(BOTH)`。
   - compliant / bypass 终端 → 无额外标记。
5. **回滚边界验证**：制造「首次降级 + 所有防火墙封锁失败」场景，确认 `compliance_status` 回滚后 `non_compliant_type` 同步为 NULL。
6. **前端类型/构建**：`cd frontend && npm run build`（或项目统一构建入口）通过，无 TS 类型错误。
7. **回归**：运行相关测试（`pytest backend/tests/`，重点 `test_compliance_service*.py`），确认新增字段不破坏既有的 1507 通过基线。