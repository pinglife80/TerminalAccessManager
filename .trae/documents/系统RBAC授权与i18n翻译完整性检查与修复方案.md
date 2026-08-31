# 系统 RBAC 授权与 i18n 翻译完整性检查与修复方案

> 文档版本：1.0  更新日期：2026-08-31

## 一、摘要

对系统进行两项全量排查：

1. **RBAC 授权**：核对后端所有 API 端点的权限保护（`require_permission` / `get_current_user`）与权限种子数据（`cli.py::_ensure_rbac_seed`）、预置角色（superadmin/admin/operator/auditor/viewer）之间的对应关系，找出遗漏与缺陷。
2. **i18n 翻译**：以 `frontend/src/i18n/locales/en.ts` / `zh.ts` / `ja.ts` 三份语言包 + 前端源码中 `t('...')` 实际调用为基准，找出缺失词条与三语不一致。

结论：发现 **RBAC 缺陷 6 项**（含 3 项高风险），**i18n 缺失词条 42 项**（含 20 项"代码在使用但三语全部缺失"的断键，会导致界面显示原始 key），以及少量僵尸词条需要清理。

---

## 二、现状分析

### 2.1 RBAC 架构

- 权限判定核心：`backend/app/core/security.py` 中的 `require_permission(code)` 依赖工厂。逻辑：superuser 直接放行；否则通过 `get_user_permissions()` 查询用户角色→权限集合，命中则放行，否则 403。
- 权限定义/种子：`backend/cli.py` 第 558 行 `_ensure_rbac_seed()`，硬编码 35 条权限（id 1~35）与 5 个预置角色及其 `role_permissions` 映射。
  - 关键点：函数开头 `if role_count >= 5: return`（第 566 行）——**已有 5 个角色时会整段跳过，包括新增权限的插入**。这是后续新增权限在存量部署上不生效的根源。
- 模型：`Role` / `Permission` / `UserRole` / `RolePermission`（`app/models/role.py`），用户→角色→权限多对多。
- 权限缓存：`get_user_permissions` 写 Redis（TTL 300s）；角色/用户角色变更时通过 `invalidate_user_permissions` 失效（roles.py、auth.py 均已正确调用）。

### 2.2 i18n 架构

- `frontend/src/i18n/index.ts` 注册 en/zh/ja 三语，`fallbackLng: 'en'`。
- 三重对照：`en.ts`（1401 叶子键）、`zh.ts`（1402）、`ja.ts`（1387）；前端源码实际调用 `t('...')` 共 1044 个唯一键。

---

## 三、RBAC 检查结论（问题清单）

| 级别 | # | 问题 | 位置 | 影响 |
|---|---|---|---|---|
| 高 | R1 | `compliance:read` / `compliance:write` 被使用但**未在种子数据中定义** | [compliance_scope.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/compliance_scope.py) 使用；[cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L588-L625) 缺失 | 合规范围页面（列表/新增/编辑/删除/启停）对所有非 superuser 永久 403，功能不可用 |
| 高 | R2 | `system:manage` 权限已种子但**从未被任何端点强制**，`/system/*` 仅 `get_current_user` | [system.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/system.py#L24-L127) | 任意登录用户（含只读 viewer）可触发 `POST /system/firewall-reconciliation`（敏感重操作）→ 越权 |
| 高 | R3 | `GET /auth/users/email-available` **无任何鉴权**，泄露 id+username | [auth.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/auth.py#L573-L598) | 未认证即可枚举邮箱对应的用户名与用户 id（信息泄露/用户枚举） |
| 中 | R4 | `backup:read`（id 32）已种子但**未被使用**；备份读接口用 `get_current_user`，写接口用 `backup:write` | [backup.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/backup.py#L38-L280) | 权限模型不一致：读接口无权限门槛，`backup:read` 形同虚设 |
| 中 | R5 | `terminal:write`（id 2）已种子并分配给 operator，但**已无任何端点在用** | [terminals.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/terminals.py) 仅 terminal:read | 死权限（封禁/解封已迁移到 blacklist），权限集冗余 |
| 低 | R6 | 种子打印 `5 roles, 29 permissions` 与实际 35 条不符 | [cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L659) | 文案误导 |

---

## 四、i18n 检查结论（问题清单）

### 4.1 代码在使用但三语全部缺失（20 个，会导致界面显示原始 key，最高优先级）

这些 key 在 `en.ts`/`zh.ts`/`ja.ts` 中均不存在，却被前端 `t('...')` 调用。

| key | 使用位置 | 建议 en / zh / ja |
|---|---|---|
| auth.checkEmail | PasswordReset.tsx:167（`{email}` 插值） | Check your email / 请检查您的邮箱 / メールをご確認ください |
| auth.verificationCodeSent | PasswordReset.tsx:164 | Verification code sent / 验证码已发送 / 認証コードを送信しました |
| common.confirmDelete | ComplianceScope.tsx:424（弹窗标题） | Confirm Delete / 确认删除 / 削除の確認 |
| common.email | LDAPImportModal.tsx:309（表头） | Email / 邮箱 / メール |
| common.errorLoadingData | LDAPImportModal.tsx:85 | Error loading data / 加载数据失败 / データの読み込みに失敗しました |
| common.locked | Users.tsx:411 | Locked / 已锁定 / ロック中 |
| terminal.unblocked | Terminals.tsx:277 | Unblocked / 已解封 / ブロック解除済み |
| notifications.subscribedEvents | Notifications.tsx:916 | Subscribed Events / 已订阅事件 / 購読イベント |
| dataSources.config | OperationSourceTab.tsx | Configuration / 配置 / 設定 |
| dataSources.status | OperationSourceTab.tsx | Status / 状态 / ステータス |
| dataSources.loading | OperationSourceTab.tsx | Loading... / 加载中... / 読み込み中... |
| dataSources.enterName | OperationSourceTab.tsx | Please enter a name / 请输入名称 / 名前を入力してください |
| dataSources.enterTag | OperationSourceTab.tsx | Please enter a tag / 请输入标签 / タグを入力してください |
| dataSources.editSource | OperationSourceTab.tsx | Edit Data Source / 编辑数据源 / データソースを編集 |
| dataSources.noSources | OperationSourceTab.tsx | No data sources / 暂无数据源 / データソースがありません |
| dataSources.addFirstSource | OperationSourceTab.tsx | Add your first data source / 添加第一个数据源 / 最初のデータソースを追加 |
| dataSources.connectionSuccess | OperationSourceTab.tsx | Connection successful / 连接成功 / 接続成功 |
| dataSources.disableWarning | OperationSourceTab.tsx | Disable Warning / 禁用警告 / 無効化の警告 |
| dataSources.disableImpactWarning | OperationSourceTab.tsx | Disabling will impact the following / 禁用将影响以下内容 / 無効化すると以下に影響します |
| dataSources.affectedTerminals | OperationSourceTab.tsx | Affected Terminals / 受影响终端 / 影響を受ける端末 |

> 注：上述 dataSources.* 12 个词条集中出现在 `components/datasources/OperationSourceTab.tsx`（运维数据源 Tab），说明该 Tab 曾改用了新的 `dataSources.*` 命名，但词条未同步写入三个语言包。

### 4.2 仅 ja.ts 缺失（22 个，en/zh 已有，日语缺失 → 日语界面回退英文）

| key | 建议 ja |
|---|---|
| auth.passwordComplexity | 大文字・小文字・数字を含める必要があります |
| auth.resendCodeIn | 再送信（{{seconds}}秒） |
| authProviders.anonymousSearch | 匿名検索 |
| authProviders.bindDnRequired | Bind DN は必須です |
| authProviders.bindPasswordRequired | Bind パスワードは必須です |
| authProviders.leaveBlankToKeep | 空欄のままにすると現在値を保持します |
| authProviders.optional | 任意 |
| backup.backupInProgress | バックアップ実行中... |
| backup.backupList | バックアップ一覧 |
| backup.backupNow | 今すぐバックアップ |
| backup.confirmDelete | バックアップ「{{ filename }}」を削除しますか？ |
| backup.confirmRestore | バックアップ「{{ filename }}」から復元しますか？ |
| backup.cronInvalid | Cron 形式が無効です。正しい 5 フィールド形式を入力してください |
| backup.cronRequired | Cron 式を入力してください |
| backup.delete | 削除 |
| backup.ftp | FTP |
| backup.restoreInProgress | 復元中... |
| backup.running | 実行中 |
| backup.settings | バックアップ設定 |
| common.select | 選択... |
| users.emailAlreadyInUse | このメールはユーザー {{username}} が既に使用しています |
| users.forceUseEmail | このメールを使用することを確認 |

### 4.3 僵尸/多余词条（建议清理，低优先级）

| key | 现状 |
|---|---|
| whitelist.importLogAction | 仅 zh 有，en/ja 缺失，且代码未使用 → 建议统一删除，或补入 en/ja 保持一致 |
| authProviders.local / authProviders.localDesc | 仅 ja 有，代码未使用 |
| notifications.timeType.daily/hourly/minute/monthly/weekly | 仅 ja 有（5 个），代码未使用 |
| users.assignRoles | 仅 ja 有，代码未使用 |

---

## 五、修改方案

### 5.1 RBAC 修复

#### R1 — 补齐 `compliance:read` / `compliance:write` 权限（核心）

文件：[cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L588-L625)

1. 在 `permissions_data` 追加两条（沿用现有 `compliance` module，id 取 36、37）：

```python
{"id": 36, "code": "compliance:read", "name": "查看合规范围", "module": "compliance", "description": "查看合规范围配置"},
{"id": 37, "code": "compliance:write", "name": "管理合规范围", "module": "compliance", "description": "创建/编辑/删除合规范围"},
```

2. 将 `admin_perms` 追加 `36, 37`；`viewer_perms` 追加 `36`（只读）。operator/auditor 不授予（合规范围属于系统配置，仅管理员可管理）。

3. **修复早退逻辑（关键，否则存量部署不生效）**：将 `_ensure_rbac_seed` 开头的整体早退改为"权限数据总是幂等补齐"。具体：把 `if role_count >= 5: return` 移除，改为按 `Permission.code` 逐条 `if not existing` 幂等插入（角色与 `role_permissions` 仍保持"仅当缺失时才插入"的现有幂等写法，避免覆盖管理员自定义）。并同步修正结尾打印为 `35 + 2 = 37 permissions`（见 R6）。

> 存量部署迁移：本次修改后需对既有环境触发一次权限补齐。因 `_ensure_rbac_seed` 仅在 `_run_setup` / `_run_mock_generate` 调用，需提供一个幂等的入口（见 5.3 假设与决策 D2），否则已有数据库不会新增这两条权限、`require_permission("compliance:read")` 会继续 403。

#### R2 — 为 `system.py` 端点强制 `system:manage`

文件：[system.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/system.py)

- `POST /system/firewall-reconciliation`：`Depends(get_current_user)` → `Depends(require_permission("system:manage"))`。
- `GET /system/status`、`GET /system/config`：维持 `get_current_user`（返回 only-safe 值，供 Dashboard 使用；如后续收紧可再评估）。两者为只读、非敏感，不在本次范围内升级。
- `GET /system/health`：保持无鉴权（作为健康检查探针，与 `api.py` 的 `/health` 一致，切勿加鉴权）。

#### R3 — 为 `email-available` 加鉴权

文件：[auth.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/auth.py#L573-L598)

- 给 `check_email_available` 增加 `current_user: User = Depends(get_current_user)`，仅登录用户可查询。
- `used_by` 中的 `id` / `username` 保留（前端创建/编辑用户时用于提示 `users.emailAlreadyInUse`），但仅在已认证前提下返回。

#### R4 — 备份读接口改用 `backup:read`（权限模型对齐）

文件：[backup.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/api/v1/endpoints/backup.py)

将以下读接口的 `Depends(get_current_user)` 改为 `Depends(require_permission("backup:read"))`：
- `GET /backup/config`
- `GET /backup/list`
- `GET /backup/whitelist/list`
- `GET /backup/{filename}/contents`

> `backup:read`（id 32）已在 admin_perms 中，业务上备份管理属管理员范畴，收紧符合预期；写接口维持 `backup:write` 不变。

#### R5 — `terminal:write` 死权限清理

文件：[cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L588-L625)

- 从 `permissions_data` 删除 `{"id": 2, "code": "terminal:write", ...}`，并从 `operator_perms` 移除 `2`。
- 若评估后倾向"保留以兼容未来封禁接口"，则可仅在本方案中标注为已知冗余、暂不删除（见 5.3 假设与决策 D3，默认采用保守：**仅移除 operator 分配、保留权限记录**，避免影响已有的用户自定义角色引用）。

#### R6 — 修正种子打印文案

文件：[cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L659)

- 打印改为动态统计：`f"✓ RBAC preset data seeded (5 roles, {len(permissions_data)} permissions)"`。

### 5.2 i18n 修复

文件：`frontend/src/i18n/locales/en.ts` / `zh.ts` / `ja.ts`

1. **三语各补 20 个"使用中缺失"词条**（见 4.1 表），按表内 en/zh/ja 三列分别写入对应语言包对应命名空间。
   - `auth` 命名空间：checkEmail、verificationCodeSent
   - `common` 命名空间：confirmDelete、email、errorLoadingData、locked
   - `terminal` 命名空间：unblocked
   - `notifications` 命名空间：subscribedEvents
   - `dataSources` 命名空间：config、status、loading、enterName、enterTag、editSource、noSources、addFirstSource、connectionSuccess、disableWarning、disableImpactWarning、affectedTerminals（12 个）
2. **ja.ts 补 22 个日语词条**（见 4.2 表）。
3. **僵尸词条清理**（见 4.3 表）：删除 zh 的 `whitelist.importLogAction`（en/ja 均无、且未使用）；删除 ja 中未使用的 `authProviders.local`、`authProviders.localDesc`、`notifications.timeType.*`（5 个）、`users.assignRoles`。保持三语 key 集合严格对齐。

---

## 六、假设与决策（Assumptions & Decisions）

- **D1**：以 `en.ts` 为词条基准（fallback 语言），`zh`/`ja` 必须与 `en` 的叶子 key 完全对齐；僵尸词条在确认无 `t('...')` 引用后统一删除。
- **D2（存量迁移）**：新增 `compliance:read/write` 需要对存量库补种。推荐在 `cli.py` 增加一个幂等入口（如 `seed-rbac` 子命令，或复用 `_ensure_rbac_seed` 改造后的"权限幂等补齐"逻辑并在 `manage.sh update/upgrade` 流程中可选触发）。具体入口由执行者按现有部署流程选择，但**必须确保存量环境新增权限后 `compliance:read` 可被授予/查询**。
- **D3（R5 处理口径）**：默认**保守**——保留 `terminal:write` 权限记录本体、仅从 `operator_perms` 移除分配；如需彻底删除请与用户确认（可能影响自定义角色引用）。
- **D4**：`GET /system/health` 与 `api.py` 的 `/health` 保持无鉴权，作为探针，不纳入本次收紧范围。
- **D5**：R3 仅加 `get_current_user`，不额外加 `user:read`（避免破坏"注册流程关闭/开启"及用户自助场景下的可用性）；如需更强控制可后续再议。

---

## 七、验证步骤

### 7.1 RBAC

1. 后端单测/回归：在 `backend` 目录运行 pytest，确保既有 `test_*` 全部通过（重点 `test_backup_service.py`）。
2. 补种验证：执行 `_ensure_rbac_seed`（新幂等版本）后，查询 `permissions` 表含 `compliance:read`、`compliance:write`，且 admin 角色的 `role_permissions` 含 36、37。
3. 权限矩阵手工验证：
   - 用非 superuser 的 admin 角色用户调用 `POST /compliance-scope`，应 200（有 compliance:write）。
   - 用 viewer 用户调用 `POST /compliance-scope`，应 403；调用 `GET /compliance-scope`，应 200（有 compliance:read）。
   - 用 viewer 用户调用 `POST /system/firewall-reconciliation`，应 403；admin 应 200。
   - 未登录调用 `GET /auth/users/email-available`，应 401。
   - viewer 调用 `GET /backup/list`，应 403；admin 应 200。
4. 部署指纹验证：`docker exec tam_backend grep -n "compliance:write" /app/cli.py` 确认新代码已进容器（遵循既有 "deployed code fingerprint" 教训）。

### 7.2 i18n

1. 复跑本方案使用的 key 提取脚本，确认：
   - "使用中缺失 en/zh/ja" 数量归 0；
   - `en/zh/ja` 三语叶子 key 集合完全一致（en == zh == ja）。
2. 前端构建：本地无 node/npm，需 `./manage.sh update` 走 Docker 构建，确认 TS 编译无错。
3. 界面抽查：切换 en/zh/ja，检查"数据源运维 Tab""合规范围删除确认""用户列表锁定列""LDAP 导入邮件列""密码重置页"等位置不再显示原始 key（如 `common.email`、`dataSources.loading`）。

---

## 八、涉及文件汇总

| 文件 | 改动 |
|---|---|
| `backend/cli.py` | 追加 2 条权限、`admin_perms`/`viewer_perms` 调整、修复 `_ensure_rbac_seed` 早退逻辑、修正打印、R5 处理 |
| `backend/app/api/v1/endpoints/system.py` | `firewall-reconciliation` 加 `require_permission("system:manage")` |
| `backend/app/api/v1/endpoints/auth.py` | `email-available` 加 `get_current_user` |
| `backend/app/api/v1/endpoints/backup.py` | 4 个读接口改用 `require_permission("backup:read")` |
| `frontend/src/i18n/locales/en.ts` | 补 20 个词条（+ 与 zh/ja 对齐处理 `whitelist.importLogAction`） |
| `frontend/src/i18n/locales/zh.ts` | 补 20 个词条；删 `whitelist.importLogAction` |
| `frontend/src/i18n/locales/ja.ts` | 补 20 + 22 个词条；删 8 个僵尸词条 |