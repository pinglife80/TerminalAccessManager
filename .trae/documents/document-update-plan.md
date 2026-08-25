# TerminalAccessManager 文档更新计划

> 文档版本：v1.0  更新日期：2026-07-16

---

## 一、文档审核结论

### 1.1 当前版本状态

| 项目 | 当前值 |
|------|--------|
| VERSION 文件 | 3.6.14 |
| 大部分文档版本号 | v3.6.13 |
| 上次文档更新日期 | 2026-07-14 |

### 1.2 文档变更缺口分析

根据最近代码变更（v3.6.14），以下功能变更尚未在文档中体现：

| 变更项 | 影响文档 | 当前状态 | 优先级 |
|--------|---------|---------|:------:|
| 白名单匹配类型逻辑修复（MAC+IP双重匹配） | business-workflow.md, api.md, user-guide.md | 未更新 | 高 |
| 白名单删除逻辑修复（支持多种IP格式） | api.md, user-guide.md | 未更新 | 高 |
| 白名单备注必填验证 | api.md, user-guide.md | 未更新 | 高 |
| Firewall tag 业务逻辑修复（仅blocked终端有firewall_tag） | business-workflow.md, api.md, user-guide.md | 未更新 | 高 |
| 合规状态一致性修复（bypass状态必须unblocked） | business-workflow.md | 未更新 | 高 |
| i18n翻译补充（匹配类型、备注验证） | user-guide.md | 未更新 | 中 |
| 文档版本号统一更新 | 所有文档 | 未更新 | 高 |

### 1.3 文档规范检查

根据项目规范要求：
- ✅ 文档版本号格式：`文档版本：vX.Y.Z`
- ✅ 更新日期格式：`更新日期：YYYY-MM-DD`
- ❌ 版本号不一致：文档版本仍为 v3.6.13，项目版本已升级到 3.6.14
- ❌ 发布记录缺失：release-notes.md 缺少 v3.6.14 发布记录
- ❌ changelog.md 缺少 v3.6.14 变更记录

---

## 二、文档更新计划

### 2.1 更新清单

| 序号 | 文件 | 更新内容 | 版本号更新 |
|------|------|---------|:----------:|
| 1 | docs/changelog.md | 添加 v3.6.14 变更记录 | ✅ |
| 2 | docs/release-notes.md | 添加 v3.6.14 发布记录 | ✅ |
| 3 | docs/business-workflow.md | 更新白名单匹配逻辑、firewall_tag逻辑、合规状态流转 | ✅ |
| 4 | docs/api.md | 更新白名单API备注必填要求、firewall_tag说明 | ✅ |
| 5 | docs/user-guide.md | 更新白名单操作说明、firewall_tag显示规则 | ✅ |
| 6 | docs/production-readiness-assessment.md | 更新评估版本和日期 | ✅ |

### 2.2 详细更新内容

#### 文档1：docs/changelog.md

**更新位置**：文档头部版本号 + 新增 [3.6.14] 章节

**变更记录内容**：

```markdown
## [3.6.14] - 2026-07-15

### 修复

- **白名单匹配类型逻辑**：修复添加白名单时 pattern_type 设置错误问题
  - 当同时提供 MAC 和 IP 时，pattern_type 设置为 'both'（双重匹配）
  - 仅提供 MAC 时，pattern_type 设置为 'mac_only'
  - 仅提供 IP 时（包括不带掩码和/32 CIDR），pattern_type 设置为 'single_ip'
  - CIDR 类型（非/32）设置为 'cidr'
  - IP范围类型设置为 'ip_range'
  - 关联文件：`backend/app/services/compliance_service.py`, `frontend/src/pages/Terminals.tsx`, `frontend/src/pages/Whitelist.tsx`

- **白名单删除逻辑**：修复删除白名单时的500错误
  - 支持多种IP格式删除（带/不带掩码）
  - 修复重复条目导致的删除失败问题
  - 添加数据库唯一约束防止重复条目
  - 关联文件：`backend/app/services/terminal_service.py`, `backend/app/api/v1/endpoints/whitelist.py`

- **白名单备注必填**：添加备注必填验证
  - 前端：添加白名单时必填备注字段
  - 后端：WhitelistCreate schema 中 comments 设置为必填
  - 关联文件：`backend/app/schemas/terminal.py`, `frontend/src/pages/Terminals.tsx`, `frontend/src/pages/Whitelist.tsx`

- **Firewall tag 业务逻辑**：修复 firewall_tag 状态不一致问题
  - 只有 status='blocked' 的终端才保留 firewall_tag
  - 终端状态变为非 blocked 时自动清除 firewall_tag
  - 前端仅在 blocked 状态时显示 firewall_tag
  - 关联文件：`backend/app/services/compliance_service.py`, `frontend/src/pages/Terminals.tsx`

- **合规状态一致性**：修复 bypass 状态终端可能显示 blocked 的问题
  - 当 compliance_status 变为 'bypass' 时，强制设置 status='unblocked'
  - 确保白名单终端始终处于未封锁状态
  - 关联文件：`backend/app/services/compliance_service.py`

### 国际化

- **白名单匹配类型翻译**：添加匹配类型选择器的三语言翻译
  - 新增翻译键：matchTypeSelector, matchTypeMacOnly, matchTypeSingleIp, matchTypeBoth
  - 关联文件：`frontend/src/i18n/locales/zh.ts`, `frontend/src/i18n/locales/en.ts`, `frontend/src/i18n/locales/ja.ts`

- **备注必填翻译**：添加白名单备注必填提示翻译
  - 新增翻译键：whitelistCommentRequired
  - 关联文件：`frontend/src/i18n/locales/zh.ts`, `frontend/src/i18n/locales/en.ts`, `frontend/src/i18n/locales/ja.ts`

### 文档更新

- 更新 business-workflow.md 白名单匹配逻辑和 firewall_tag 逻辑
- 更新 api.md 白名单API备注必填要求
- 更新 user-guide.md 白名单操作说明
- 更新 release-notes.md 添加 v3.6.14 发布记录
- 统一所有文档版本号至 v3.6.14
```

#### 文档2：docs/release-notes.md

**更新位置**：文档头部版本号 + 新增 [v3.6.14] 章节

**发布记录内容**：

```markdown
## [v3.6.14] - 2026-07-15

### 白名单业务逻辑优化

#### 功能变更

- **白名单匹配类型完善**
  - 变更描述：修复白名单添加时 pattern_type 设置错误的问题，确保不同场景添加的白名单具有正确的匹配类型
  - 变更内容：
    - MAC+IP 条目：pattern_type 设置为 'both'，需要双重匹配
    - 仅 MAC：pattern_type 设置为 'mac_only'
    - 仅 IP（不含/32）：pattern_type 设置为 'single_ip'
    - CIDR（/32 除外）：pattern_type 设置为 'cidr'
    - IP范围：pattern_type 设置为 'ip_range'
    - 终端管理页面新增匹配类型选择器（mac_only/single_ip/both）
  - 根因：之前添加白名单时没有根据添加场景正确设置匹配类型，导致后续匹配逻辑失效
  - 关联文件：`backend/app/services/compliance_service.py`, `frontend/src/pages/Terminals.tsx`, `frontend/src/pages/Whitelist.tsx`

- **白名单删除逻辑修复**
  - 变更描述：修复删除白名单时的500错误，支持多种IP格式删除
  - 变更内容：
    - 支持带掩码和不带掩码的IP格式删除（如 10.8.25.121 和 10.8.25.121/32）
    - 添加数据库唯一约束防止重复条目
    - 优化删除逻辑处理重复条目情况
  - 根因：数据库中存在重复的白名单条目，删除时触发主键冲突
  - 关联文件：`backend/app/services/terminal_service.py`, `backend/app/api/v1/endpoints/whitelist.py`

- **白名单备注必填**
  - 变更描述：添加白名单时备注字段设为必填
  - 变更内容：
    - 前端：添加白名单表单验证，备注为空时显示错误提示
    - 后端：API schema 中 comments 设置为必填字段
  - 关联文件：`backend/app/schemas/terminal.py`, `frontend/src/pages/Terminals.tsx`, `frontend/src/pages/Whitelist.tsx`

- **Firewall tag 业务逻辑修复**
  - 变更描述：修复 firewall_tag 与终端状态不一致的问题
  - 变更内容：
    - 后端：终端状态变为非 blocked 时自动清除 firewall_tag
    - 前端：仅在 blocked 状态时显示 firewall_tag，其他状态显示 "-"
  - 根因：终端解除封锁后 firewall_tag 没有被清除，导致状态不一致
  - 关联文件：`backend/app/services/compliance_service.py`, `frontend/src/pages/Terminals.tsx`

- **合规状态一致性修复**
  - 变更描述：修复白名单终端可能同时显示 blocked 和 bypass 状态的问题
  - 变更内容：当 compliance_status 变为 'bypass' 时，强制设置 status='unblocked'
  - 关联文件：`backend/app/services/compliance_service.py`

#### 国际化更新

- 添加白名单匹配类型选择器翻译（中文/英文/日语）
- 添加白名单备注必填提示翻译（中文/英文/日语）

#### 代码变更清单

| 文件 | 变更内容 | 类型 |
|------|---------|------|
| `backend/app/services/compliance_service.py` | 修复 pattern_type 设置逻辑、添加 firewall_tag 清理逻辑 | fix |
| `backend/app/services/terminal_service.py` | 修复白名单删除逻辑、添加备注必填验证 | fix |
| `backend/app/schemas/terminal.py` | WhitelistCreate comments 设为必填 | fix |
| `backend/app/api/v1/endpoints/whitelist.py` | 更新删除端点支持多种IP格式 | fix |
| `frontend/src/pages/Terminals.tsx` | 添加匹配类型选择器、备注验证、firewall_tag 显示逻辑 | fix |
| `frontend/src/pages/Whitelist.tsx` | 添加 'both' 类型显示支持 | fix |
| `frontend/src/i18n/locales/zh.ts` | 添加匹配类型和备注验证翻译 | i18n |
| `frontend/src/i18n/locales/en.ts` | 添加匹配类型和备注验证翻译 | i18n |
| `frontend/src/i18n/locales/ja.ts` | 添加匹配类型和备注验证翻译 | i18n |

#### 数据库变更

- 添加白名单表唯一约束：`ALTER TABLE whitelist ADD CONSTRAINT uq_whitelist_unique UNIQUE (mac_address, ip_pattern);`
- 清理非 blocked 终端的 firewall_tag：`UPDATE terminals SET firewall_tag = NULL WHERE status != 'blocked' AND firewall_tag IS NOT NULL;`

#### 测试验证

- API 端点验证：白名单 CRUD 操作正常，备注必填验证生效
- 前端构建验证：`./manage.sh -y update` 构建成功
- 服务状态验证：`./manage.sh status` 所有服务正常
- 业务流程验证：
  - 白名单添加时根据选择的匹配类型正确设置 pattern_type
  - 白名单删除支持多种IP格式
  - 终端状态变更时 firewall_tag 正确清理
  - bypass 终端状态始终为 unblocked
  - 前端仅在 blocked 状态时显示 firewall_tag

#### 文档更新

| 文件 | 更新内容 |
|------|---------|
| `docs/changelog.md` | 添加 v3.6.14 变更记录 |
| `docs/release-notes.md` | 添加 v3.6.14 发布记录 |
| `docs/business-workflow.md` | 更新白名单匹配逻辑和 firewall_tag 逻辑 |
| `docs/api.md` | 更新白名单API备注必填要求 |
| `docs/user-guide.md` | 更新白名单操作说明 |
```

#### 文档3：docs/business-workflow.md

**更新内容**：

1. **文档头部版本号**：更新为 v3.6.14
2. **3.6 白名单备注管理章节**：添加匹配类型说明
3. **4.3 自动封锁流程**：更新 firewall_tag 设置逻辑
4. **5.3 自动解封流程**：添加 firewall_tag 清除逻辑
5. **7.1 终端状态机**：更新状态流转图，体现 bypass→unblocked 强制关系
6. **8.1 终端相关参数**：更新 firewall_tag 说明

**具体变更**：

```markdown
## 3.7 白名单备注管理

白名单条目支持备注（comment）字段，用于记录添加原因或管理信息。备注信息会同步写入匹配终端的 `remarks` 字段，便于在终端列表中追溯白名单来源。

### 3.7.1 白名单匹配类型

白名单支持以下匹配类型：

| 类型 | 说明 | 匹配条件 |
|------|------|---------|
| `mac_only` | 仅MAC匹配 | 只提供MAC地址 |
| `single_ip` | 单IP匹配 | 只提供单个IP（含/32 CIDR） |
| `cidr` | CIDR匹配 | 提供CIDR网段（非/32） |
| `ip_range` | IP范围匹配 | 提供IP范围（如 192.168.1.1-192.168.1.100） |
| `both` | MAC+IP双重匹配 | 同时提供MAC和IP地址 |

### 3.7.2 添加白名单

添加白名单条目时可填写备注（**必填**），系统会根据添加内容自动确定匹配类型：
- 仅 MAC 地址：匹配类型为 `mac_only`，匹配单个终端
- 仅 IP 地址（不含/32）：匹配类型为 `single_ip`，匹配单个终端
- IP 地址带/32：匹配类型为 `single_ip`，匹配单个终端
- CIDR 网段：匹配类型为 `cidr`，匹配网段内所有终端
- IP 范围：匹配类型为 `ip_range`，匹配范围内所有终端
- MAC + IP：匹配类型为 `both`，IP和MAC都必须匹配

### 3.7.3 删除白名单

删除白名单条目时，系统会自动清除关联终端的备注信息和 `wl_match_type`，确保备注与白名单状态一致。
```

```markdown
## 4.3 详细步骤

#### 步骤4：更新数据库

```python
# 更新终端状态
entry.status = "blocked"
entry.firewall_tag = firewall_tags[0] if len(firewall_tags) == 1 else ",".join(firewall_tags)
# 注意：firewall_tag 仅在 status='blocked' 时设置
```
```

```markdown
## 5.3 详细步骤

#### 步骤3：更新数据库

```python
# 更新终端状态
terminal.status = "unblocked"
terminal.firewall_tag = None  # 状态变为非blocked时必须清除firewall_tag

# 更新黑名单记录（软删除）
bl_entry.unblocked_at = datetime.now(UTC)
bl_entry.unblocked_by = "system"
bl_entry.auto_unblocked = True
```
```

```markdown
## 8.1 终端相关参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 防火墙封锁状态：blocked/unblocked |
| `compliance_status` | string | 合规状态：compliant/bypass/non_compliant/unknown |
| `source_tag` | string | ARP数据源标签 |
| `firewall_tag` | string | 绑定的防火墙标签（**仅blocked状态时有值**，其他状态为null） |
| `wl_match_type` | string | 白名单匹配类型：mac/ip/both |
```

#### 文档4：docs/api.md

**更新内容**：

1. **文档头部版本号**：更新为 v3.6.14
2. **4.2 POST /whitelist/**：更新请求体，将 comments 改为必填

**具体变更**：

```markdown
### 4.2 POST /whitelist/

添加白名单条目。支持 MAC 地址、单 IP、CIDR 子网、IP 范围、MAC+IP 双重匹配。

- **认证要求**：需认证

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mac_address | string | 否 | MAC 地址 |
| ip_address | string | 否 | 单 IP / CIDR / IP 范围（如 `192.168.1.1-192.168.1.50`） |
| comments | string | **是** | 备注（必填） |
| match_type | string | 否 | 匹配类型：mac_only/single_ip/both（终端管理页面添加时使用） |

> mac_address 和 ip_address 至少提供一个。
> match_type 参数仅在终端管理页面添加白名单时使用，白名单管理页面添加时根据提供的内容自动推断。

**成功响应** `201`

```json
{
  "message": "Added to whitelist successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 添加失败（格式错误、重复、备注为空等） |
| 422 | 请求参数验证失败（备注必填） |
```

#### 文档5：docs/user-guide.md

**更新内容**：

1. **文档头部版本号**：更新为 v3.6.14
2. **5. 白名单管理**：更新添加白名单的操作说明
3. **4. 终端管理**：更新 firewall_tag 显示规则

**具体变更**：

```markdown
## 5. 白名单管理

### 5.1 添加白名单

1. 在白名单管理页面点击 **添加白名单** 按钮
2. 填写以下信息：
   - **MAC地址**（可选）：终端的MAC地址
   - **IP地址**（可选）：可以是单IP、CIDR网段或IP范围
   - **备注**（必填）：添加白名单的原因或管理信息
3. 点击 **确定** 按钮

> **注意**：MAC地址和IP地址至少填写一项。系统会根据填写内容自动确定匹配类型：
> - 仅填写MAC：仅MAC匹配
> - 仅填写IP：单IP匹配
> - 同时填写MAC和IP：IP和MAC都必须匹配（双重匹配）

### 5.2 在终端管理中添加白名单

1. 在终端管理页面找到目标终端
2. 点击操作栏的 **加白** 按钮
3. 选择匹配类型：
   - **仅MAC匹配**：只根据MAC地址匹配
   - **仅IP匹配**：只根据IP地址匹配
   - **IP和MAC都匹配**：IP和MAC都必须匹配
4. 填写备注（必填）
5. 点击 **确定** 按钮

### 5.3 删除白名单

1. 在白名单列表中找到目标条目
2. 点击操作栏的 **删除** 按钮
3. 在确认对话框中点击 **确定**

> **注意**：删除白名单后，关联终端的合规状态将重新计算。
```

```markdown
## 4. 终端管理

### 4.1 终端列表字段说明

| 字段 | 说明 |
|------|------|
| IP地址 | 终端的IP地址 |
| MAC地址 | 终端的MAC地址 |
| 状态 | 终端的封锁状态（blocked/unblocked） |
| 合规状态 | 终端的合规状态（compliant/bypass/non_compliant/unknown） |
| 匹配类型 | 白名单匹配类型（mac/ip/both），仅bypass状态显示 |
| 防火墙标签 | 终端被封锁在哪个防火墙上，**仅blocked状态显示**，其他状态显示"-" |
| 备注 | 白名单备注信息 |
```

#### 文档6：docs/production-readiness-assessment.md

**更新内容**：

1. **文档头部评估版本**：更新为 v3.6.14
2. **文档头部评估日期**：更新为 2026-07-15

---

## 三、实施步骤

### 步骤1：更新 changelog.md

- 更新文档头部版本号为 v3.6.14
- 更新文档头部日期为 2026-07-15
- 在 [Unreleased] 前添加 [3.6.14] 章节

### 步骤2：更新 release-notes.md

- 更新文档头部版本号为 v3.6.14
- 更新文档头部日期为 2026-07-15
- 在文档开头添加 [v3.6.14] 章节

### 步骤3：更新 business-workflow.md

- 更新文档头部版本号为 v3.6.14
- 更新文档头部日期为 2026-07-15
- 更新 3.7 白名单备注管理章节，添加匹配类型说明
- 更新 4.3 自动封锁流程 firewall_tag 设置逻辑
- 更新 5.3 自动解封流程 firewall_tag 清除逻辑
- 更新 8.1 终端相关参数 firewall_tag 说明

### 步骤4：更新 api.md

- 更新文档头部版本号为 v3.6.14
- 更新文档头部日期为 2026-07-15
- 更新 4.2 POST /whitelist/ 请求体，将 comments 改为必填

### 步骤5：更新 user-guide.md

- 更新文档头部版本号为 v3.6.14
- 更新文档头部日期为 2026-07-15
- 更新 5. 白名单管理章节，添加匹配类型选择说明
- 更新 4. 终端管理章节，添加 firewall_tag 显示规则

### 步骤6：更新 production-readiness-assessment.md

- 更新评估版本为 v3.6.14
- 更新评估日期为 2026-07-15

---

## 四、验证方案

### 4.1 文档一致性验证

1. **版本号一致性**：检查所有文档版本号是否统一为 v3.6.14
2. **日期一致性**：检查所有文档更新日期是否统一为 2026-07-15
3. **内容一致性**：检查各文档之间对同一功能的描述是否一致

### 4.2 文档完整性验证

1. **changelog.md**：确认 v3.6.14 变更记录包含所有代码变更
2. **release-notes.md**：确认 v3.6.14 发布记录完整
3. **business-workflow.md**：确认白名单匹配逻辑和 firewall_tag 逻辑正确描述
4. **api.md**：确认白名单API备注必填要求正确标注
5. **user-guide.md**：确认白名单操作说明完整准确

### 4.3 验证命令

```bash
# 检查文档版本号
grep -r "文档版本" docs/ | sort

# 检查文档日期
grep -r "更新日期" docs/ | sort

# 检查 changelog 是否包含 v3.6.14
grep "3.6.14" docs/changelog.md

# 检查 release-notes 是否包含 v3.6.14
grep "3.6.14" docs/release-notes.md
```

---

## 五、风险处理

### 风险1：文档版本号遗漏

**处理方案**：使用 grep 命令检查所有文档的版本号，确保没有遗漏。

### 风险2：文档内容与代码不一致

**处理方案**：更新文档前仔细核对代码实现，确保描述准确反映实际行为。

### 风险3：格式错误

**处理方案**：更新后使用 Markdown 工具检查格式正确性。

---

## 六、提交方案

### 6.1 提交信息

```
docs: update documentation for v3.6.14

- Update changelog.md with v3.6.14 changes
- Update release-notes.md with v3.6.14 release record
- Update business-workflow.md with whitelist match logic and firewall_tag logic
- Update api.md with whitelist comments required constraint
- Update user-guide.md with whitelist operation instructions
- Update production-readiness-assessment.md version and date
- Unify all document versions to v3.6.14
```

### 6.2 推送流程

1. 提交到 develop 分支
2. 创建 PR 到 main 分支
3. 审核通过后合并
4. 按照 git-workflow-guide.md 执行版本发布流程
