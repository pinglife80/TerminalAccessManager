# 版本跟踪记录

> 文档版本：v3.19.0 | 更新日期：2026-09-04
>
> 本文档记录 TerminalAccessManager 每个版本的详细发布过程，包括变更内容、提交记录、测试验证和发布操作。
>
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)，变更描述遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/) 规范。

---

## [v3.19.0] - 2026-09-04

### 合规作用域 OR 匹配策略、通知事件系统修复与非合规原因标记（Minor 版本）

#### 背景

自 v3.18.0 发布以来，围绕合规判定与通知可靠性展开三项工作：其一，新增合规作用域「OR 匹配策略」——指定网段/前缀内终端「IP 或 MAC 任一命中合规基线即判定 compliant」，缓解既有 AND 逻辑在 DHCP 换 IP / 同 MAC 多 IP 场景下的误降级；其二，审计通知事件系统，退役绕过管道、永不真正送达的 legacy 聚合器，并修复重试向全部渠道重复发送、渠道 `send()` 返回类型不一致、发射器调用签名错乱等缺陷；其三，新增 `non_compliant_type` 结构化字段，将前端非合规徽标从误导性的 `black_match_type`（封锁后恒为 BOTH）改为真实不合规因素（IP / MAC / BOTH）。因含面向用户的新能力（OR 匹配策略），故以 Minor 发布。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 合规作用域 OR 匹配策略（新功能） | 新增 `ip_cidr_any` / `ip_range_any` / `mac_prefix_any` 三种作用域类型，IP 或 MAC 任一命中即合规 |
| 通知事件系统审计修复 | 退役 legacy 聚合器、重试按渠道隔离、统一 `send()` 返回类型、修复发射器签名、补缺失触发点 |
| 非合规原因标记（迁移 039） | `terminals` 新增 `non_compliant_type` 列，前端徽标改按真实因素（IP/MAC/BOTH）展示 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 本次含数据库迁移 039（`terminals` 新增 `non_compliant_type` 列），`./manage.sh upgrade` 会自动执行 `alembic upgrade head`。
- 无破坏性变更；OR 匹配为新增作用域能力，默认 AND 与既有 IP-only 作用域行为不变。

## [v3.18.0] - 2026-09-02

### 黑名单唯一口径收敛、终端去重查重筛选与统计口径简化（Minor 版本）

#### 背景

自 v3.17.3 发布以来，围绕数据状态一致性主题继续收敛：其一，黑名单活跃唯一口径由 `(IP, MAC, 防火墙)` 收敛为 `(IP, 防火墙)`，对齐深信服按 IP 封堵、按 IP 幂等的真实行为，解决 DHCP 换 IP 场景下同 IP 多 MAC 产生重复活跃行、进而与防火墙实际封锁数错配并引发封/解振荡的问题；其二，新增终端「去重/查重」筛选能力，便于直接发现 DHCP 换 IP、同 IP 多终端等数据质量问题；其三，收敛统计口径并简化前端统计卡，移除 `pending_retry_block`/`unblockable_non_compliant` 等易混淆的中间口径；其四，修复令牌滑动续期误重置空闲计时器的问题。因含一项面向用户的新能力（终端去重/查重筛选），故以 Minor 发布。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 黑名单唯一口径收敛（迁移 038） | 活跃唯一索引 `(IP, MAC, 防火墙)` → `(IP, 防火墙)`；去重历史重复活跃行；新增 `_attach_active_blacklist` 幂等写入 |
| 对账口径与补封闭收敛 | 孤儿重置不再写 `block_state`；active 口径移除 `expires_at` 过期剔除；补封闭成功后回写 `Terminal.status/firewall_tag` 并清 `block_state` |
| 终端去重/查重筛选（新功能） | 新增「去重/查重维度」(IP/MAC/IP+MAC) 与「去重/查重模式」(去重/查重) 两个下拉框，服务端 SQL 实现 |
| 统计口径收敛与卡片简化 | `get_blacklist_stats` 移除中间口径；`pending_retry_unblock` MAC 归一化去重；导出 active_filter 补 `expires_at`；前端移除「待封锁/不可封锁非合规」卡 |
| 终端过滤精简 | 移除 `block_state` 与「仅启用 ARP 源」冗余过滤，统一为去重/查重维度/模式参数 |
| 会话滑动续期修复 | token 自动续期不再重置 idle 计时器、不关闭 idle 超时警告 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 本次含数据库迁移 038（黑名单活跃唯一索引收敛为 `(ip_address, firewall_tag)`），`./manage.sh upgrade` 会自动执行 `alembic upgrade head`。
- 迁移会去重历史活跃重复行（按 ip+firewall 保留最新、其余标记解封）并重建唯一索引，升级前请按惯例自动备份。
- 无破坏性变更；终端「去重/查重」筛选为新增能力，移除的 `block_state`/「仅启用 ARP」为冗余过滤项。

## [v3.17.3] - 2026-08-31

### 数据状态一致性问题根治：对齐统计口径 + 根治 non_compliant+unblocked 中间态（Patch 版本）

#### 背景

用户反馈三个长期无法消除的现象：① Dashboard/终端/黑名单页「非合规且封锁」统计总与防火墙实际封锁数对不上；② 终端管理页存在大量 non_compliant + unblocked（非合规未封锁）终端；③ 黑名单页总堆积大量 Block Pending Retry。经代码审查确认三者同源：统计口径混淆（三个本质不同对象被强行对齐）+ 中间态无出口（non_compliant+unblocked 无标记、永久堆积并重复计入 Block Pending Retry）。本次一次性根治。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 新增 `Terminal.block_state` 字段 | 037 迁移；`None`=正常 / `no_firewall`=无绑定防火墙不可封锁 / `block_failed`=封锁失败待重试 |
| 合规状态机落地 | `_apply_compliance_result`、`auto_block_non_compliant` 各封锁落点叠加 `block_state` |
| 调度器 retry-block 回填 | 无防火墙→`no_firewall`、失败→`block_failed`、成功→`None`，首轮后清除 NULL 残留 |
| 统计口径拆分 | `get_stats` 新增 `non_compliant_unblocked`；`get_blacklist_stats` 拆分可重试/不可封锁并曝光 `firewall_ip_count` |
| 对账自愈联动 | `_repair_stale_terminal_status` 重置时为 non_compliant 回填 `block_failed` |
| 前端显式化 | 终端页拆「非合规已封锁/待封锁」卡 + `block_state` 徽标；黑名单页新增「防火墙实际封锁」「不可封锁非合规」卡；新增 `block_state` 筛选跳转 |
| 深信服分页拉取修复 | `get_blocked_ips` 循环聚合全部分页（原仅第一页 200 条），根除对账每轮误重复封堵 |
| 会话超时自动注销修复 | 倒计时归零后延迟跳转，先落地 logout 状态，修复弹窗消失但未跳登录页的竞态 |
| 前端交互一致性 | 防火墙对账确认改用系统 `Modal`；终端统计卡标签统一最小高度对齐 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 本次含数据库迁移 037（`terminals` 新增 `block_state` 列），`./manage.sh upgrade` 会自动执行 `alembic upgrade head`。
- 历史 `block_state=NULL` 由调度器首轮 retry-block 自动回填，无需一次性数据迁移。
- 无破坏性变更；防火墙实际封锁数口径为「各防火墙封锁 IP 数之和，未跨防火墙去重」。

## [v3.17.2] - 2026-08-31

### RBAC 授权加固、i18n 三语补全与暗色模式统一（Patch 版本）

#### 背景

自 v3.17.1 发布以来，工作区积累了一批未提交改动，围绕四条主线：其一，全面检查系统 RBAC 授权发现 6 项遗漏与缺陷（新增 `compliance:read/write` 权限、为敏感接口补授权、移除死权限、修复种子早退）；其二，全面检查 en/zh/ja 三语 i18n，补齐 20 个断键与 22 个日语缺失、清理 9 个僵尸词条；其三，统一暗色模式样式（输入框字体对比度、表头背景、语义 token）并修复终端搜索框被挤压、备份列表无分页等 UX 问题；其四，修复备份服务、中文日志乱码、角色编辑误报、数据源删除统计等若干后端 bug。全部改动向后兼容、无新用户功能，故以 Patch 发布。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| RBAC 授权加固（6 项） | 新增 `compliance:read`(36)/`compliance:write`(37) 并幂等补种；`firewall-reconciliation` 加 `system:manage`；`email-available` 加登录鉴权；4 个备份读接口改用 `backup:read`；operator 移除死权限 `terminal:write` |
| 备份服务修复 | 修复失效 settings 引用、错误 imports、`SameFileError` 等 14+ 处问题，同步修复 15 个 pre-existing 失败用例 |
| 中文日志乱码 | JSON 日志 `ensure_ascii=False` |
| 角色编辑误报 | 唯一性校验排除当前 `role_id` |
| 数据源删除统计 | ARP/防火墙删除按 `firewall_tag` 过滤、合规基线按基线 tag 过滤 |
| 会话超时体验 | 对话框化 + 手动关闭 + 倒计时自动注销 |
| i18n 三语补全 | 补 20 断键 + 22 日语 + 清 9 僵尸，三语 leaf key=1421 对齐 |
| 暗色模式一致性 | 输入框对比度 + 表头 `bg-card` + 语义 token 迁移 |
| 终端搜索框 | 独占整行 |
| 备份列表分页 | 增加分页 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 本次新增 `compliance:read` / `compliance:write` 权限，须在存量环境触发 RBAC 种子补种（`_ensure_rbac_seed` 已改为按 `Permission.code` 幂等补齐），否则合规范围页面可能出现权限不符。
- 4 个备份读接口由 `backup:read` 权限控制，viewer 角色默认无该权限（admin 有）。
- 无数据库迁移、无破坏性变更。

## [v3.17.1] - 2026-08-28

### Pydantic v2 迁移、运行时回归修复与测试覆盖补全（Patch 版本）

#### 背景

自 v3.17.0 发布以来，工作区积累了一批未提交改动，围绕两条主线：其一，将后端迁移到 Pydantic v2 / SQLAlchemy 2.0 的推荐用法并修复若干运行时回归（本地 2FA 验证码生成、webhook 测试连接降级、compliance scope IP 范围校验、防火墙对账探测解包、通知日志事务）；其二，完成 6A–6E 测试链补测并启用 pytest 覆盖率门槛。全部改动向后兼容、无新用户功能，故以 Patch 发布。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| Pydantic v2 迁移 | 8 个文件（config + 7 schema）将弃用的 `class Config` → `model_config = ConfigDict/SettingsConfigDict(...)` |
| SQLAlchemy 2.0 文本 SQL | `system.py` 健康检查 `db.execute("SELECT 1")` → `db.execute(text("SELECT 1"))` |
| 本地 2FA 修复 | `two_factor_service.py` 将不存在的 `generate_verification_code` 改为 `generate_email_code` 并补 `await` |
| Webhook 测试连接修复 | `webhook_channel.py` 由捕获不存在的 `httpx.MethodNotAllowed` 改为按 `status_code == 405` 触发 HEAD→POST 降级 |
| Compliance Scope 校验修复 | `compliance_scope_service.py` 重写 `ip_range` 校验，解析「前缀 + 起止末位八位组」并校验 `start>end`、`end>255`、非法前缀 |
| 防火墙对账修复 | `firewall_reconciliation_service.py` `probe_ip` 元组解包修复、返回 `Set[str]` |
| 通知日志事务一致性（F） | `notification_service.py` `_log_notification` 传入 `self.db`，保持请求级事务 |
| 死代码清理 | 移除 `compliance_service.py` / `terminal_service.py` 失效的 `wl_comments` 参数与 `unblocked_at` 冗余赋值 |
| 品牌文案一致性 | `.env.example` 残留 `Terminal Access Platform` → `Terminal Access Manager` |
| 测试与覆盖率 | 6A–6E 测试补全（约 6000+ 行）；`pyproject.toml` 启用 `--cov=app`；`ci.yml` 增加 `--cov-fail-under=20`；默认邮件模板文件化 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 本次仅技术债迁移与 bug 修复，无数据库迁移、无配置变更，历史行为不变。
- CI 新增 `--cov-fail-under=20` 门槛（首期低基线），后续随补测逐轮上调。

## [v3.17.0] - 2026-08-26

### 合规状态机防抖参数可配置化与首次发现确认阈值保护（Minor 版本）

#### 背景

围绕「终端合规检测准确、稳定；谨慎降级 non_compliant、迅速升级 compliant、白名单迅速生效」的核心边界，复盘发现四类问题：其一，用于防抖的冷却期、IP 变更宽限期、白名单未命中阈值在上述路径中硬编码（10/10/6），无法按环境调节；其二，`_get_confirm_threshold` 因向 `ConfigService.get` 传入第二个参数触发 TypeError 被静默捕获，确认阈值配置从未生效；其三，首次发现终端（unknown）路径绕过确认阈值，直接降级封锁，存在误封锁风险；其四，NULL-MAC 终端在自动解封分组时坍缩到同一桶，及 MAC+IP 白名单存在瞬时误判。本版本将防抖参数全链参数化（后端 + 前端系统设置），为首次发现路径补上确认阈值保护，并修复上述缺陷。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 防抖参数可配置化 | 新增 `compliance_cooldown_minutes`（默认 10，clamp 1~60）、`compliance_ip_grace_minutes`（默认 10，clamp 1~60）、`compliance_whitelist_miss_threshold`（默认 6，clamp 2~20）三项系统配置，归入 compliance 组 |
| 前端系统设置同步 | compliance 分组新增 3 个可编辑字段 + 三语文案（zh/en/ja） |
| 首次发现确认阈值保护 | 新增 `apply_initial_compliance_result`，首次发现路径（arp_collector + main 调度兜底）不再瞬时封锁，非合规需累计达到确认阈值才降级封锁 |
| auto_block 白名单权威预检 | 自动封锁前强制校验白名单，命中则自愈为 bypass 并跳过封锁 |
| 配置读取修复 | `_get_confirm_threshold` 去除第二参数，修复「确认阈值配置从不生效」的静默失败 |
| NULL-MAC 分组修复 | 自动解封按 MAC 分组时空 MAC 回退 IP 分组，避免不同终端坍缩到同一桶 |
| MAC+IP 白名单即时生效校验 | 添加 both 白名单时校验终端当前 IP 是否匹配 ip_pattern，不匹配则交由下一轮重算评估 |
| TerminalStatus 导入修复 | 补齐 `TerminalStatus` 导入，修复 NameError |
| 死代码清理 | 移除 `arp_collector_service.py` 中未使用的 `_auto_block_task` |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 新增 3 个防抖参数默认值与历史行为一致，无需迁移，可在系统设置页 → 合规分组调整。
- 首次发现路径新增确认阈值后，新终端从 unknown 到 non_compliant（封锁）的延迟增加至「确认阈值 × 采集周期」，属预期的防误封锁行为。

## [v3.16.1] - 2026-08-25

### 修复 IPGuard 合规误判并新增缓存新鲜度门控（Patch 版本）

#### 背景

合规判定依赖 IPGuard 基线数据，存在两类误判问题：其一是 `_match_ipguard_in_memory` 返回三元组被直接当作布尔值使用（非空元组恒为 True），导致本应不合规的终端被误判为合规；其二是 IPGuard Redis 缓存存在同步时延，延迟登记的终端在窗口期被误判降级并封锁。本版本修复上述两类误判，并新增缓存新鲜度门控从根上缩小误判时间窗。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 元组真值误判修复 | `auto_unblock_compliant` 与 `recalculate_all_compliance` 正确解包 `ig_match, _, _ = ...` |
| IPGuard 缓存新鲜度门控 | 基线同步时间戳超过可配置阈值时跳过降级、hold 原状态 |
| 新增配置项 | `ipguard_stale_threshold_minutes`（默认 12 分钟，clamp 5~60），归入 compliance 配置组，系统设置页可编辑 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 新增配置项 `ipguard_stale_threshold_minutes` 默认 12 分钟，可在系统设置页调整（5~60 分钟）。
- IPGuard 缓存陈旧期间不执行合规降级，终端保持原状态，待缓存同步后由下一轮定时检查正常判定。

## [v3.16.0] - 2026-08-25

### 黑名单解封事件列与到期解封 reason（Minor 版本）

#### 背景

黑名单列表对「成功解封」的条目此前未展示解封原因与时间，且到期自动解封（`cleanup_expired_blacklist`）在写入解封记录时缺失独立 reason，难以区分是合规解封（白名单/IPGuard 匹配）还是封锁到期解封。本版本新增「解封事件」列提升可读性，并统一写入到期解封 reason。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 解封事件列 | 黑名单列表新增「解封事件」列，展示解封原因（reason）与时间（unblocked_at） |
| i18n | 新增 `unblockEvent` 三语文案（zh/en/ja） |
| 到期解封 reason | 统一写入「封锁时间到期自动解封」作为独立事件原因 |
| SQLite 适配 | `database.py` 仅在非 SQLite 数据库应用连接池参数，保障单测可运行 |
| 版本管理 | `manage.sh` 的 `version check`/`version bump` 统一从 `VERSION` 动态派生 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 新增「解封事件」列自动跟随黑名单列表展示，无需额外配置。
- 版本号统一从 `VERSION` 文件动态派生，`package.json` 由前端镜像构建期自动同步，无需手动修改。

## [v3.15.0] - 2026-08-25

### 黑名单封锁时长（block_time）可配置化（Minor 版本）

#### 背景

黑名单封锁时长此前在自动封锁、调度器 retry-block、合规自动封锁、防火墙对账补建各路径中硬编码为 30 天，且后端 `_get_block_time` 因 `config_service.get("block_time", "30d")` 传入第二参数触发 TypeError 被静默捕获，配置从未生效。本版本统一为可配置的 `block_time` 系统配置，并修复配置读取 bug。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 系统配置项 | 新增 `block_time`（compliance 分类，默认 30d，支持 1h/6h/12h/1d/3d/7d/15d/30d） |
| 系统设置页 | compliance 分组新增 block_time 下拉选择 |
| 自动封锁弹窗 | 新增封锁时长下拉，默认取系统配置值、可逐次覆盖 |
| 防火墙对账补建 | 改用系统配置 block_time，替代硬编码 30d |
| 配置读取修复 | `_get_block_time` 改为 `get("block_time") or "30d"`，修复 TypeError 静默失败 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

- 新增的 `block_time` 配置默认值为 `30d`，与历史行为一致，无需迁移。
- 若需调整默认封锁时长，登录系统设置页 → 合规分组 → block_time 下拉选择即可。

## [v3.14.0] - 2026-08-24

### 黑名单管理增强与统计口径统一（Minor 版本）

#### 背景

v3.13.0 发布后，围绕黑名单管理与合规状态一致性暴露出若干问题：封锁/解封结果缺乏可追踪的运行记录；统计口径（blocked / non_compliant / pending_retry_block / pending_retry_unblock / source）在仪表盘、终端页、黑名单页、调度器重试逻辑间不完全一致，DHCP 换 IP 会漏计或重复计数；防火墙对账的错误原因未结构化展示；删除数据源绑定后遗留孤立 `blocked` 终端。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 黑名单操作追踪 | 新增 `last_operation_type/status/error/at` 与 `retry_count` 字段，迁移 `036_blacklist_operation_tracking` |
| 状态不变量加强 | 强制 `non_compliant ⇒ blocked`；retry-block 忽略冷却期强制封锁中间态并做白名单权威预检 |
| 自动解封一致性 | 解封时同步写 `compliance_status`（bypass/compliant 按命中类型），阻断被重封震荡 |
| 统计口径统一 | blocked/non_compliant/pending_retry_* 口径统一；黑名单-终端关联改 MAC 归一化（NULL-MAC 回退 IP） |
| 防火墙对账增强 | 错误收集结构化 `[{tag, error}]` + 孤立 blocked 终端自愈 |
| 数据源安全删除 | `safe_delete_binding` 改用 MAC 归一化匹配终端；`create_binding` 后触发合规重算 |
| 前端展示 | 黑名单状态列、防火墙错误弹窗（tag/error/对账时间）、条件 Retry Unblock 按钮 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

⚠️ **必须执行数据库迁移**：036 迁移为黑名单表新增操作追踪字段（含 `server_default='0'` 的 `retry_count`，非破坏性）。
⚠️ **升级后验证**：刷新仪表盘 / 终端页 / 黑名单页，封锁计数一致；黑名单页可见状态列与防火墙错误弹窗；Retry Unblock 按钮仅在 compliant/bypass 终端显示。

---

## [v3.13.0] - 2026-08-21

### 防火墙实际统计展示与黑名单统计一致性（Minor 版本）

#### 背景

v3.12.1 发布后继续收敛黑名单统计口径：Dashboard、终端管理、黑名单三处封锁计数需对齐为 `blocked`（活跃黑名单去重 IP），并补充防火墙实际封锁数展示。

#### 主要变更

| 变更项 | 说明 |
|--------|------|
| 防火墙实际统计展示 | 新增 `_cache_reconcile_result`，对账结果缓存 Redis（`reconcile:latest`，TTL 1h），黑名单页新增「防火墙实际封锁数」卡片 |
| 黑名单统计不一致修复 | 三页面统一 `blocked` 口径；终端页改读 `stats.blocked`；移除对账服务重复缓存逻辑 |
| 状态不变量加强 | 确保 `non_compliant ⇒ blocked`；冷却期阻止降级而非阻止封锁；封锁失败回滚状态 |
| 白名单稳定性修复 | 白名单命中直接设 `bypass` 并清零确认计数；周期全量重算修复卡死状态 |

#### 升级步骤（推荐：一键升级）

```bash
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级注意事项

⚠️ **无新增数据库迁移**（本版本为逻辑与展示修复）。
⚠️ **升级后验证**：刷新三处页面封锁计数一致。

---

## [v3.12.1] - 2026-08-20

### 黑名单与防火墙同步问题修复（Patch版本）

#### 背景

v3.12.0发布后发现严重数据一致性问题：
- Dashboard/终端页面显示封锁数量与防火墙实际一致，但黑名单页面显示更多条目
- 防火墙封锁失败时Blacklist仍创建记录，导致幽灵记录
- 防火墙对账逻辑错误，可能错误删除有效记录
- Blacklist唯一约束缺少firewall_tag字段，多防火墙环境会产生重复记录

实际数据：Dashboard显示86条封锁，黑名单显示99条，存在13-15条不一致。

#### 主要变更

| 修复项 | 说明 |
|--------|------|
| 唯一约束修复 | Blacklist唯一索引从`(ip, mac)`改为`(ip, mac, firewall_tag)`，支持多防火墙独立记录 |
| 封锁结果判断 | 每个防火墙独立判断成功/失败，不再共用错误列表；部分成功只创建成功防火墙的记录 |
| 防火墙对账重写 | 以数据库为权威源，防火墙返回0条记录自动跳过，只补封缺失不错误解封 |
| 过期清理修复 | 按归一化MAC匹配终端，所有防火墙Blacklist过期才更新终端状态 |
| 重复检查修复 | recalculate中按防火墙查询已有活跃记录，每个防火墙独立幂等检查 |
| 数据清理迁移 | 035迁移自动清理15条孤儿记录（无firewall_tag、无MAC、重复记录） |

#### 升级步骤（推荐：一键升级）

```bash
# 生产环境直接使用upgrade一键完成pull+重建+迁移+验证
git checkout main
git pull origin main
./manage.sh upgrade
```

#### 升级步骤（分步）

```bash
git checkout main
git pull origin main
./manage.sh update
./manage.sh migrate
./manage.sh health
```

#### 升级注意事项

⚠️ **必须执行数据库迁移**：035迁移会自动清理历史脏数据（孤儿记录、重复记录），不删除有效封锁
⚠️ **迁移自动备份**：`./manage.sh upgrade`自动备份，`./manage.sh migrate`提示备份
⚠️ **服务自动重启**：升级过程服务会短暂重启，不影响数据
⚠️ **升级后验证**：刷新Dashboard/终端/黑名单页面，三个位置封锁计数一致

---

## [v3.12.0] - 2026-08-20

### MAC前缀类型拆分、终端MAC唯一标识重构、合规状态防震荡

#### 背景

v3.11.0发布后发现多个严重问题：
1. MAC前缀筛选条件无法区分匹配ARP终端还是IPGuard基线，功能不完整
2. 终端以(IP,MAC)联合主键导致DHCP换IP产生重复记录，双网卡终端处理错误
3. 合规状态频繁震荡（封禁→解封→封禁循环），由确认阈值不一致、时序竞争、缺少冷却期等多个根因导致

#### 主要变更

| 功能 | 说明 |
|------|------|
| MAC前缀类型拆分 | `mac_prefix`拆分为`mac_prefix_arp`（匹配ARP终端）和`mac_prefix_ipguard`（匹配IPGuard基线MAC） |
| 终端MAC唯一标识 | Terminal表唯一键改为MAC归一化值，ARP入库按MAC更新IP，支持双网卡正确处理 |
| 三层防震荡机制 | 对称确认计数、双向冷却期（10分钟）、IP变更宽限期（10分钟），彻底解决状态震荡 |
| IPGuard双网卡格式支持 | 正确解析`MAC1(IP1)MAC2(IP2)...`格式 |

#### 升级步骤

```bash
# 1. 拉取代码
git checkout main
git pull origin main

# 2. 执行数据库迁移（包含数据去重：保留每个MAC最新/被封禁记录）
cd backend && alembic upgrade head

# 3. 重启服务
docker compose up -d
```

#### 升级注意事项

⚠️ **必须执行数据库迁移**：包含3个迁移脚本，其中033会去重重复终端记录（保留每个MAC最新/被封禁记录）
⚠️ **合规判定延迟变化**：状态切换需要连续2次确认（约10分钟），防止瞬态误判，这是预期行为
⚠️ **冷却期保护**：自动封禁/解封后10分钟内不执行反向操作，手动操作不受限

#### 数据库迁移

- `032_mac_prefix_scope_type_split.py` - 原有mac_prefix数据自动迁移为mac_prefix_arp
- `033_terminal_mac_unique.py` - 数据去重后修改唯一约束为mac_address_normalized
- `034_compliance_oscillation_fixes.py` - 新增compliant_confirm_count和ip_changed_at字段

---

## [v3.11.0] - 2026-08-20

### Compliance Scope 条件管理与白名单导入增强

#### 背景

v3.10.4 发布后，业务场景提出新需求：希望能够根据网段范围或 MAC 前缀作为条件，在合规计算时仅将 IP 地址作为判断条件而忽略 MAC 地址。同时，白名单导入功能需要支持直接导入备份 ZIP/JSON 格式文件，黑名单导出存在字段引用错误。

#### 问题描述

1. **合规计算灵活性不足**：现有合规计算流程固定采用 IP+MAC 双重匹配策略，无法根据业务场景灵活切换为仅 IP 匹配
2. **黑名单导出报错**：`GET /blacklist/export` 端点引用了 Blacklist 模型不存在的字段（status、block_time、added_by、created_at），导致 AttributeError 和 HTTP 500
3. **白名单导入格式限制**：仅支持 CSV 格式导入，无法直接导入备份 ZIP/JSON 文件
4. **recalculate_all_compliance 逻辑遗漏**：重算方法未加载 Scope 条件数据，导致重算时所有终端都采用 IP+MAC 双重匹配策略

#### 根因分析

1. **合规计算流程单一**：白名单检查 → IPGuard 基准匹配的两阶段流程无法满足"条件化匹配策略"需求，需要在白名单检查后增加一个条件判断节点
2. **导出接口开发时未验证**：导出代码硬编码了 CSV 表头字段，未与实际模型字段对齐
3. **导入格式单一**：导入功能仅实现了 CSV 解析逻辑，缺少 ZIP/JSON 解析和冲突处理机制

#### 修复内容

| 项目 | 修改文件 | 说明 |
|------|---------|------|
| ComplianceScope 模型 | `compliance_scope.py` (model) | 新增 scope_type（ip_cidr/ip_range/mac_prefix）和 scope_value 字段 |
| ComplianceScope Schema | `compliance_scope.py` (schema) | 新增 Create/Update/Response Schema，含格式校验 |
| ComplianceScope Service | `compliance_scope_service.py` | 实现 CRUD、缓存失效、格式校验（CIDR /24+、IP 范围、MAC 前缀 3-5 段） |
| ComplianceScope API | `compliance_scope.py` (endpoint) | RESTful CRUD + toggle 端点，含权限检查 |
| 合规计算流程集成 | `compliance_service.py` | 白名单后增加 scope 检查节点，实现 IP-only vs IP+MAC 策略选择 |
| recalculate 修复 | `compliance_service.py` | 加载 scope 数据并应用条件匹配策略 |
| bypass 快速降级 | `compliance_service.py` | bypass 状态 1 个确认周期降级为 non_compliant |
| 黑名单导出修复 | `blacklist.py` | 替换为现有模型字段，新增 Status/Block Type/Auto Unblocked 列 |
| 白名单导入增强 | `whitelist.py`、`terminal_service.py` | 新增 .zip/.json 支持，冲突处理（skip/overwrite），savepoint 事务 |
| 前端 Scope 页面 | `ComplianceScope.tsx`、`complianceScope.ts` | 管理 UI、CRUD hooks、启用/禁用切换 |
| 前端侧边栏/路由 | `Sidebar.tsx`、`App.tsx`、`constants.ts` | 新增 Scope 导航项和路由 |
| UI 修复 | `Sidebar.tsx`、`index.css` | 修复折叠按钮裁剪，新增自定义滚动条样式 |
| 数据库迁移 | `031_compliance_scope.py` | 创建 compliance_scope 表及索引 |

#### 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/alembic/versions/031_compliance_scope.py` | 新增 | 数据库迁移：创建 `compliance_scope` 表 |
| `backend/app/models/compliance_scope.py` | 新增 | ComplianceScope ORM 模型 |
| `backend/app/schemas/compliance_scope.py` | 新增 | Pydantic Schema |
| `backend/app/services/compliance_scope_service.py` | 新增 | Service 层 |
| `backend/app/api/v1/endpoints/compliance_scope.py` | 新增 | API 端点 |
| `backend/app/services/compliance_service.py` | 修改 | 核心修改：scope 集成 + recalculate 修复 + bypass 降级 |
| `backend/app/api/v1/endpoints/blacklist.py` | 修改 | 黑名单导出字段修复 |
| `backend/app/api/v1/endpoints/whitelist.py` | 修改 | 白名单导入增强 |
| `backend/app/services/terminal_service.py` | 修改 | 白名单导入逻辑增强 |
| `backend/alembic/env.py` | 修改 | 注册 ComplianceScope 模型 |
| `backend/app/models/__init__.py` | 修改 | 注册模型到列表 |
| `backend/app/api/v1/api.py` | 修改 | 注册 compliance_scope 路由 |
| `backend/app/schemas/terminal.py` | 修改 | Terminal Schema 新增字段 |
| `frontend/src/api/complianceScope.ts` | 新增 | React Query hooks |
| `frontend/src/pages/ComplianceScope.tsx` | 新增 | Scope 管理页面 |
| `frontend/src/App.tsx` | 修改 | 路由注册 |
| `frontend/src/components/Sidebar.tsx` | 修改 | 侧边栏折叠按钮修复 + 导航项 |
| `frontend/src/index.css` | 修改 | 自定义滚动条样式 |
| `frontend/src/lib/constants.ts` | 修改 | 新增 COMPLIANCE_SCOPE 导航项 |
| `frontend/src/i18n/locales/{zh,en,ja}.ts` | 修改 | 三语言翻译 |
| `frontend/src/pages/Whitelist.tsx` | 修改 | 导入功能增强 |
| `frontend/src/pages/Blacklist.tsx` | 修改 | 页面小调整 |

#### 验证结果

- Python 语法检查：所有后端文件通过 `py_compile` ✅
- TypeScript 编译：所有前端文件通过 `tsc --noEmit` ✅
- ComplianceScope CRUD：正常创建、编辑、删除、切换启用状态 ✅
- Scope 条件合规计算：CIDR/IP 范围/MAC 前缀条件正确匹配 ✅
- 仅 IP 匹配策略：条件范围内终端使用 IP-only 匹配 ✅
- 双重匹配策略：条件范围外终端保持 IP+MAC 匹配 ✅
- recalculate_all_compliance：正确加载 Scope 数据并应用条件 ✅
- bypass 降级：1 个确认周期后降级为 non_compliant ✅
- 黑名单导出：CSV 包含正确字段 ✅
- 白名单 ZIP 导入：正确解析嵌套/扁平结构 ✅
- 白名单 JSON 导入：正确解析并处理冲突 ✅
- 侧边栏折叠：按钮完全可见，滚动条正常 ✅

#### 发布信息

- 版本号：v3.11.0
- 前一版本：v3.10.4
- 变更类型：功能新增 + 修复 + 改进 (feat + fix)
- 涉及模块：compliance_service.py, compliance_scope_service.py, blacklist.py, whitelist.py, terminal_service.py, ComplianceScope.tsx, Sidebar.tsx, Whitelist.tsx
- 新增文件：7 个
- 修改文件：17 个

---

## [v3.10.4] - 2026-08-10

### 后端日志与通知错误修复包

#### 背景

v3.10.3 发布后发现两个后端日志错误：
1. Loguru 在模块级代码触发日志时抛出 ValueError（`<module>` 被解析为颜色指令）
2. 通知 worker 对 SMTP 认证错误执行无意义重试，日志刷屏

#### 修改文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| backend/app/core/logging_config.py | 新增 | `_patcher()` 函数 + `logger.configure(patcher=...)` 注册 |
| backend/app/services/email_service.py | 修改 | 新增 `SMTPAuthenticationError` 捕获 + `AUTH_ERROR:` 标记；`import smtplib` 移至模块级 |
| backend/app/services/notification_channels/email_channel.py | 修改 | 检测 `AUTH_ERROR:` 前缀，设置 `error_code="AUTH_ERROR"` |
| backend/app/services/notification_workers.py | 修改 | `_deliver_notification()` 检测 `AUTH_ERROR` 跳过重试 |
| backend/app/services/config_service.py | 修改 | `email_password` 配置描述修正 |
| docs/changelog.md | 更新 | 新增 [3.10.4] 版本块 |
| docs/release-notes.md | 更新 | 新增 [v3.10.4] 版本块 |
| docs/logging-guide.md | 更新 | 补充 `_patcher` 机制说明 |
| docs/user-guide.md | 更新 | 修正 SMTP 密码"加密存储"误导描述 |
| docs/operations-runbook.md | 更新 | 新增通知 SMTP 认证错误排查条目 |
| docs/deployment.md | 更新 | 文档版本号 |
| docs/branding.md | 更新 | 文档版本号 |
| docs/production-readiness-assessment.md | 更新 | 文档版本号 + 跟踪表 |
| VERSION | 更新 | 3.10.3 → 3.10.4 |
| frontend/package.json | 更新 | 3.10.3 → 3.10.4 |
| frontend/package-lock.json | 更新 | 3.10.3 → 3.10.4 |

#### 验证

- 模块级日志（如 "Prometheus metrics enabled..."）正常输出 `[module]` 而非 `<module>`，无 ValueError
- SMTP 认证失败时通知 worker 跳过重试，日志输出 "Skipping retry for email: SMTP auth failed"
- 瞬时错误（网络超时等）仍正常触发重试机制

---

## [v3.10.3] - 2026-08-10

### 权限修复与品牌资源 403 修复包

#### 背景

v3.10.2 取消容器安全加固后，遗留两类问题：
1. Docker named volume 首次挂载以 root:root 创建目录，app 用户无法写入日志和上传目录
2. Nginx `/uploads/` 的 `valid_referers` 检查在 `server_name _` 下无法匹配 IP 访问，品牌资源加载 403

#### 修改文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| backend/Dockerfile | 新增 | 预创建 /var/log/tam、/app/uploads/backups、/app/uploads/branding + chown app:app |
| docker-compose.yml | 删除 | 4 处安全加固注释块 + postgres/backend 冗余 tmpfs |
| nginx/docker-entrypoint.sh | 新增 | tmpfs 目录 chown nginx:nginx 权限调整 |
| nginx/etc/conf.d/tam.conf.template | 删除 | valid_referers 检查块 |
| docs/changelog.md | 更新 | 新增 [3.10.3] 版本块 |
| docs/release-notes.md | 更新 | 新增 [v3.10.3] 版本块 |
| docs/production-readiness-assessment.md | 更新 | 文档版本跟踪表 |
| docs/deployment.md | 更新 | 文档版本号 |
| docs/branding.md | 更新 | 文档版本号 |
| VERSION | 更新 | 3.10.2 → 3.10.3 |
| frontend/package.json | 更新 | 3.10.2 → 3.10.3 |
| frontend/package-lock.json | 更新 | 3.10.2 → 3.10.3 |

#### 验证

- backend 容器内 /var/log/tam/app.log 正常写入，所有者 app:app
- /app/uploads/backups/ 和 /app/uploads/branding/ 目录可写
- Nginx 启动无 Permission denied 错误
- 浏览器通过 IP 访问登录页，品牌背景图和 favicon 加载 200 OK

---

## [v3.10.2] - 2026-08-06

### 生产模式部署可行性审查修复包

#### 背景

审查目标：`manage.sh deploy --prod` 在生产环境下能否完整端到端运行？

审查方法：manage.sh/docker-compose/cli.py/backup_service 等关键路径的静态深度审查 + 两个独立子代理交叉验证。

**总体评估（修复前）：❌ 生产模式部署不可行，存在 1 CRITICAL + 1 HIGH 严重问题。**

---

#### 问题清单与修复

##### CRITICAL. admin 密码永远硬编码为 Admin123

| 项目 | 说明 |
|------|------|
| 影响 | 生产向导让用户设置的 ADMIN_PASSWORD 仅写入 .env，但 backend 容器从未注入该变量，cli.py setup 也从未读取环境变量，创建 admin 时固定使用 hash_password("Admin123") |
| 后果 | 部署后 Web 登录密码永远是公开已知弱密码；管理工具部署摘要显示 `admin / [password you set]` 严重误导 |
| 修复 | 1) docker-compose.yml backend environment 新增 `ADMIN_PASSWORD` + `ENVIRONMENT` 注入；2) cli.py _create_admin_user 优先读 env；生产模式无强密码显式告警；生产模式密码输出脱敏 |
| 验证者共识 | 2/2 一致，severity=critical |

##### HIGH. backend 加固 tmpfs 与 uploads 命名卷路径冲突

| 项目 | 说明 |
|------|------|
| 影响 | docker-compose.prod.yml 同时声明 `tmpfs: [/tmp, /app/uploads]` 与基础 compose 的 `volume: tam-uploads:/app/uploads`，目标路径重叠在 Docker Compose 合并语义中属于未定义行为 |
| 后果 | 两种可能性：① tmpfs 优先 → 备份/branding/uploads 容器重启即丢失（数据灾难）；② 命名卷优先 → read_only 加固对上传目录失效（形同虚设） |
| 修复 | 从 docker-compose.prod.yml 的 backend tmpfs 中删除 `/app/uploads`，仅保留 `/tmp`；`tam-uploads:/app/uploads` 命名卷 + `tam-logs:/var/log/tam` 正常持久化 |
| 验证者共识 | 2/2 一致，severity=high |

##### MEDIUM. UPLOAD_DIR 相对路径与硬编码绝对路径混用

| 项目 | 说明 |
|------|------|
| 影响 | config.py `UPLOAD_DIR="./uploads"` 依赖 WORKDIR；backup_service.py 在三处混用 `settings.UPLOAD_DIR` 和 `getattr(..., '/app/uploads')` |
| 后果 | 一旦 WORKDIR 或启动 cwd 变化，相对路径解析出错；不同模块解析到不同路径导致上传/备份数据散落 |
| 修复 | config.py 改为 `/app/uploads`；backup_service 两处 `getattr` fallback 移除，统一直接读 settings |
| 验证者共识 | 2/2 一致，severity=medium |

##### MEDIUM. setup 提示与实际 manage.sh deploy 场景不一致

| 项目 | 说明 |
|------|------|
| 影响 | setup 完成后提示 "1. docker-compose up -d"，但 manage.sh deploy 在执行 setup 前已经 `dc up -d --build` 启动容器；提示 "2. localhost:8000/api/v1/docs" 仅在开发者机器场景正确 |
| 后果 | 生产用户看到错误指引，困惑下一步 |
| 修复 | 读取 `ENVIRONMENT` + 检测 `/.dockerenv`；容器场景提示 "Containers are already running" 并按 dev/prod 分别给出 HTTP:8080 / HTTPS:8443 的 Nginx 入口；裸机场景保留原提示 |
| 验证者共识 | 2/2 一致，severity=medium |

##### MEDIUM. is_initialized 仅看 state 文件，不检查 DB 实际状态

| 项目 | 说明 |
|------|------|
| 影响 | `is_initialized()` 只读取本地 state 文件 `db_initialized=true`，不查询 DB 中 admin 用户是否真实存在 |
| 后果 | 用户删除 postgres_data（DB 重置）但保留 .tam_state/state.env → 重新 deploy 直接跳过 setup → DB 完全空、无 admin 账号、无法登录 |
| 修复 | deploy Step 6/6 前新增 DB 侧 Python 探测：SELECT 1 FROM users WHERE username='admin' LIMIT 1。查得到 admin = 真·已初始化；查不到但 state 文件显示已初始化 = 警告并强制重跑 setup |
| 验证者共识 | 2/2 一致，severity=medium |

##### LOW. 部署验证 HTTP/HTTPS 顺序不区分部署模式

| 项目 | 说明 |
|------|------|
| 影响 | Dev 模式（tam.dev.conf 只监听 HTTP 8080）每次部署验证先超时 1 次 HTTPS 8443，再 fallback HTTP 通过，无意义等待和日志噪音 |
| 修复 | 按 `get_state deploy_mode` 分支：dev 先 HTTP，prod 先 HTTPS → fallback HTTP 301 |
| 验证者共识 | 2/2 一致，severity=low |

---

#### 修改文件

| 文件 | 变更类型 | 行数（估算） |
|------|----------|------------|
| docker-compose.yml | backend env 注入 ADMIN_PASSWORD + ENVIRONMENT | +2 行 |
| docker-compose.prod.yml | 删除 backend tmpfs 中的 /app/uploads | -1 行 |
| backend/cli.py | _create_admin_user 读 env；setup 输出按上下文感知 | +~55 / -~15 行 |
| backend/app/core/config.py | UPLOAD_DIR 改为 /app/uploads | ±1 行 |
| backend/app/services/backup_service.py | 2 处 getattr fallback 移除 | -4 / +2 行 |
| manage.sh | DB 探测 admin；验证顺序按 mode | +~40 / -~8 行 |
| docs/changelog.md | 新增 [3.10.2] 版本块 | +~30 行 |
| docs/release-notes.md | 新增 [v3.10.2] 版本块 | +~90 行 |
| VERSION + frontend/package*.json | 3.10.1 → 3.10.2 | +3 处更新 |

---

#### 验证结果

| 验证项 | 结果 |
|--------|------|
| Python 语法检查 (cli.py / config.py / backup_service.py) | ✅ 通过 |
| Bash 语法检查 (manage.sh bash -n) | ✅ 通过 |
| Docker Compose 合并验证 (yml + prod.yml) | ✅ 通过 |
| VS Code 诊断 (GetDiagnostics) | ✅ 无错误 |
| version bump 同步 package.json / package-lock | ✅ 一致 3.10.2 |

---

#### 风险评估

| 风险 | 缓解措施 |
|------|----------|
| admin 密码 env 注入在已有部署中 ADMIN_PASSWORD 未设置时回退 Admin123 | cli.py _create_admin_user 对 ENVIRONMENT=production + password==Admin123 情况给出醒目的黄字 WARNING 提示首次登录立刻修改 |
| 删除 /app/uploads tmpfs 后有人担心加固变弱 | read_only 根文件系统 + 精确的可写 volume 白名单才是容器最佳实践（CIS Docker Benchmark 也推荐 named volume 而非 tmpfs 用于需要持久化的应用数据），加固实际更严谨而非变弱 |
| UPLOAD_DIR 从相对改为绝对路径可能影响开发者本地裸机 | 如果本机不跑 /app，env 注入 `UPLOAD_DIR=./uploads` 可覆盖；pydantic Settings 支持 env var 覆盖 |

---

#### 端口变量化与架构简化

##### 端口全面变量化

| 项目 | 说明 |
|------|------|
| 背景 | Nginx/Backend 端口在配置文件中硬编码，改 `.env` 端口无效 |
| 修复 | 新增 `TAM_NGINX_PORT`/`TAM_NGINX_SSL_PORT`/`TAM_BACKEND_PORT`，通过 envsubst 动态注入 Nginx 配置；backend Dockerfile 使用 `BACKEND_PORT` env；manage.sh 端口检测函数化 |
| 影响 | `.env` 一处改端口，全链路生效 |

##### Nginx 配置架构重构

| 项目 | 说明 |
|------|------|
| 背景 | tam.conf / tam.dev.conf 双配置文件 + sed 替换端口，脆弱且易失效 |
| 修复 | 统一为 `tam.conf.template` + `envsubst`，仅替换 3 个变量不破坏 nginx 原生变量 |
| 删除 | tam.conf、tam.dev.conf |

##### 容器安全加固移除 + override 文件删除

| 项目 | 说明 |
|------|------|
| 背景 | 内网环境下 `cap_drop:ALL`/`read_only`/`no-new-privileges` 导致 nginx bind 失败、backend 卷写入失败 |
| 修复 | 全面移除安全加固配置；删除 docker-compose.dev.yml 和 docker-compose.prod.yml |
| dev/prod 差异 | 仅由 `.env` 中 `ENVIRONMENT` 变量控制（API 文档可见性、日志格式、启动校验严格度） |

##### Docker 卷重命名

| 项目 | 说明 |
|------|------|
| 背景 | 卷名 `tam-uploads`/`tam-logs` 加项目前缀后变成 `tam_tam-*`，冗余且语义不准确 |
| 修复 | 改为 `backend-data`/`backend-logs`，最终 Docker 卷名 `tam_backend-data`/`tam_backend-logs` |

##### env 全量传递 + healthcheck 修复

| 项目 | 说明 |
|------|------|
| 背景 | docker-compose.yml backend.environment 仅传 16 项，`.env` 中改 LOCKOUT_DURATION、LOG_LEVEL 等变量无效；healthcheck 硬编码 8000，自定义端口后服务被标记 unhealthy |
| 修复 | environment 扩充为 43 项覆盖全部 Settings 字段；healthcheck 改为容器内 `os.environ.get('BACKEND_PORT')` 动态读取 |

##### 备份服务修复

| 项目 | 说明 |
|------|------|
| 背景 | 三次连续备份失败：①POSTGRES_* 字段不存在 ②缺 pg_dump ③DB_HOST=localhost 覆盖 DATABASE_URL |
| 修复 | backup_service.py 优先从 DATABASE_URL 正则解析；Dockerfile 新增 postgresql-client；清理逻辑新增零字节文件删除 |

##### 日志/导入/构建修复

| 项目 | 说明 |
|------|------|
| loguru JSON 模板 | `{}` 未转义 → `{{}}` 转义 |
| main.py 导入 | 新增 get_config_value / emit_compliance_alert 导入 |
| .dockerignore/.gitignore | 排除 backups/uploads/zip 防止打包进镜像 |

---

## [v3.10.1] - 2026-08-06

### CLI 工具修复与合规率告警修正

#### 问题描述

1. **CLI 用户命令属性错误**：`user list` 命令报 `AttributeError: 'User' object has no attribute 'locked_until'`；`user unlock` 尝试修改不存在的 `failed_login_attempts`、`locked_until` 字段
2. **CLI 角色命令属性错误**：`role list` 命令报 `AttributeError: 'Role' object has no attribute 'is_builtin'` 和 `display_name`
3. **scheduler trigger compliance_check 参数缺失**：`batch_check_compliance()` 调用未传入 `entries` 参数导致 `TypeError`
4. **合规率计算公式错误**：原公式排除了 bypass（白名单旁路）和 unknown 终端，导致合规率被严重低估
5. **合规率告警数据源错误**：告警基于 per-source 本次检查结果（可能只有 32 个新终端），而非 DB 全局统计
6. **合规率告警阈值守卫缺失**：合规率达标（≥ 80%）时仍触发告警
7. **Shell 脚本未绑定变量错误**：`manage.sh` 中 4 处 `$2` 在 `set -u` 模式下报 `unbound variable`
8. **manage.sh 版本管理不统一**：`version bump/check` 命令同步文件过多、逻辑冗余
9. **manage.sh API 地址硬编码**：`scheduler status` 硬编码 `https://localhost:8443`
10. **合规设置参数描述未国际化**：GeneralSettings 页面 5 个配置项描述使用硬编码中文

#### 根因分析

1. **User/Role 模型字段变更**：User 模型移除了 `locked_until`、`failed_login_attempts` 字段，账户锁定状态迁移至 Redis；Role 模型 `is_builtin` 改为 `is_default`，`display_name` 改为 `name`
2. **合规率公式设计缺陷**：原实现未考虑 bypass 终端作为有效合规的一部分，且告警仅基于本次检查结果而非全局统计
3. **Shell 脚本安全编程问题**：`set -u` 模式下直接使用 `$2` 而无默认值保护
4. **版本管理缺少统一入口**：版本同步逻辑分散，缺少标准化流程

#### 修复内容

| 项目 | 修改文件 | 说明 |
|------|---------|------|
| `user list` Redis 锁查询 | `cli.py` | 批量查询 Redis `login_lock:{username}` TTL |
| `user unlock` Redis 清除 | `cli.py` | 调用 `reset_login_attempts()` 清除 Redis key |
| `role list` 字段修正 | `cli.py` | `is_builtin` → `is_default`，`display_name` → `name` |
| compliance_check 流程重写 | `cli.py` | 完整实现：数据源查找→unchecked 遍历→批量 check→结果应用→auto-block→全局告警 |
| 合规率公式修正 | `main.py` | `rate = (compliant + bypass) / total_checked` |
| 告警数据源修正 | `main.py` | 使用 `TerminalService.get_stats()` DB 全局统计 |
| 删除重复告警 | `main.py` | 移除 for 循环内 per-source 告警 |
| 阈值守卫 | `event_emitter.py` | `rate >= threshold` 时静默，不发告警 |
| 告警数据增强 | `event_emitter.py` | 新增 `total_checked`、`compliant_count`、`bypass_count` 字段 |
| Shell 变量修复 | `manage.sh` | 4 处 `$2` → `${2:-}` |
| 版本管理重写 | `manage.sh` | 仅同步必要文件（VERSION → package.json） |
| API URL 动态化 | `manage.sh`、`.env.example` | `_API_BASE_URL` 改为函数，支持 `CLI_API_BASE_URL` 覆盖 |
| 参数描述 i18n | `GeneralSettings.tsx` | `FIELD_DESC_I18N_KEYS` 映射表 |
| Dockerfile 版本同步 | `Dockerfile` | 构建时 sed 从 VERSION 同步 package.json |

#### 验证结果

| 验证项 | 预期结果 | 实际结果 |
|--------|---------|---------|
| `./manage.sh user list` | 正常显示用户列表及锁定状态 | ✅ 5 个用户，锁定状态从 Redis 查询 |
| `./manage.sh role list` | 正常显示角色列表 | ✅ 5 个角色，字段名正确 |
| `./manage.sh scheduler trigger compliance_check` | 完整执行合规检查流程 | ✅ 显示 DB 全局统计 |
| 合规率公式 | `(compliant+bypass)/total` | ✅ `(329+954)/1515 = 84.7%` |
| 阈值守卫 | rate ≥ 80% 时静默 | ✅ 84.7% 时无告警 |
| 告警数据增强 | 包含 total/compliant/bypass | ✅ 字段齐全 |

#### 提交信息

```
fix: CLI tool errors and compliance alert formula (v3.10.1)

- fix(cli.py): replace u.locked_until with Redis lock query in _list_users
- fix(cli.py): use reset_login_attempts() instead of removing locked_until field
- fix(cli.py): r.is_builtin -> r.is_default, r.display_name -> r.name in _list_roles
- fix(cli.py): implement compliance_check trigger with proper entries parameter
- fix(main.py): correct compliance rate formula - include bypass+unknown in denominator
- fix(main.py): remove duplicate per-source alert, use global DB stats only
- fix(event_emitter.py): add threshold guard, extended data fields
- fix(manage.sh): ${2:-} for unbound variable errors in 4 functions
- fix(manage.sh): rewrite version bump/check to sync only necessary files
- fix(manage.sh): _API_BASE_URL as function, support CLI_API_BASE_URL override
- fix(GeneralSettings.tsx): add FIELD_DESC_I18N_KEYS for compliance settings
- fix(Dockerfile): add sed command to sync VERSION -> package.json
```

#### 变更统计

- **修改文件**：10 个
- **新增行**：+307
- **删除行**：-98

#### 风险评估

| 风险项 | 等级 | 缓解措施 |
|--------|------|----------|
| 合规率告警逻辑变更 | 低 | 已验证公式正确性；阈值守卫确保合规率达标时不告警 |
| CLI 工具行为变更 | 低 | 仅修复错误行为，不引入新功能；向后兼容 |
| 版本同步流程 | 低 | Dockerfile 已配置自动同步；`manage.sh version bump` 手动同步 |

---

## [v3.10.0] - 2026-08-06

### 备份管理完备性修复与告警阈值配置化

#### 问题描述

1. **备份选项不生效**：手动备份端点（`POST /api/v1/backup/run`、`POST /api/v1/backup/whitelist`）未加载用户保存的备份配置，导致数据库备份、配置备份、白名单备份、日志备份等选项被忽略，始终执行全量备份。
2. **白名单备份不受选项控制**：`run_backup()` 中白名单备份无条件执行，未检查 `self.config.backup_whitelist` 选项。
3. **备份配置文件不完整**：`_backup_config()` 未包含 `nginx.conf` 和 `alembic.ini`。
4. **系统配置 DB 恢复无事务保护**：`_restore_system_config_db()` 在恢复过程中若某张表失败，已恢复的表无法回滚，导致数据不一致。
5. **远程备份无过期清理**：`_cleanup_old_backups()` 仅清理本地过期备份，SFTP/FTP 远程存储中的过期备份不会被清理。
6. **恢复功能不完整**：`restore_backup()` 未恢复白名单数据和日志文件。
7. **PostgreSQL 未配置时静默成功**：`_backup_database()` 在 PostgreSQL 未配置时返回成功而非报错。
8. **Backup.tsx 默认值缺失**：`defaultValues` 中 `backup_whitelist` 为 `undefined`，导致初始渲染异常。
9. **告警阈值硬编码**：4 个告警阈值参数（合规率阈值 0.8、危险比例 0.5、封锁数量 50、离线倍数 3）散布在后端代码中，无法通过前端配置。
10. **合规率告警量纲 bug**：`emit_compliance_alert()` 中 `compliance_rate`（0-100）与 `threshold`（0-1）量纲不一致，导致 `is_critical` 判断永远为 False，严重告警从未触发。

#### 根因分析

1. **备份选项不生效**：手动备份端点直接创建 `BackupService` 实例，未调用 `load_config()` 加载用户保存的配置，使用的是默认配置（所有选项为 True）。
2. **白名单备份不受控制**：`run_backup()` 中数据库、配置、日志备份均有 `if self.config.backup_xxx:` 条件检查，唯独白名单备份遗漏。
3. **量纲 bug**：`main.py` 传入 `threshold=0.8`（0-1 量纲），但 `compliance_rate` 为 0-100 量纲（如 80.0），比较 `80.0 < 0.8 * 0.5 = 0.4` 永远为 False。

#### 修复内容

| 项目 | 修改文件 | 说明 |
|------|---------|------|
| 手动备份加载配置 | `backup.py` | `POST /backup/run` 和 `POST /backup/whitelist` 端点添加 `load_config()` 调用 |
| 白名单备份条件检查 | `backup_service.py` | `run_backup()` 中白名单备份添加 `if self.config.backup_whitelist:` 条件 |
| 配置文件备份扩展 | `backup_service.py` | `_backup_config()` 新增 `nginx.conf`、`alembic.ini` |
| 系统配置DB恢复事务保护 | `backup_service.py` | `_restore_system_config_db()` 使用 `begin_nested()` 逐表事务保护 |
| 远程备份清理 | `backup_service.py` | `_cleanup_old_backups()` 新增 SFTP/FTP 远程过期备份清理逻辑 |
| 白名单恢复 | `backup_service.py` | 新增 `_restore_whitelist_from_zip()` 和 `_restore_whitelist_from_json()` |
| 日志恢复 | `backup_service.py` | 新增 `_restore_logs_from_zip()` |
| PostgreSQL 报错 | `backup_service.py` | `_backup_database()` 未配置时抛出异常而非静默成功 |
| 备份审计日志增强 | `backup.py`、`main.py` | 审计日志新增 `checksum`、`options` 字段 |
| Backup.tsx 修复 | `Backup.tsx` | `defaultValues` 补全 `backup_whitelist: true`；移除 `encrypt_backup` UI |
| 告警阈值配置化 | `system_config.py`、`config_service.py` | 新增 `ALERT` 分类、`AlertConfigResponse` 模型、4 条默认配置 |
| 合规率阈值从配置读取 | `main.py` | `threshold=0.8` → `get_config_value("alert_compliance_rate_threshold", 80)` |
| 危险比例从配置读取 | `event_emitter.py` | `threshold * 0.5` → `threshold * get_config_value("alert_compliance_critical_ratio", 50) / 100` |
| 封锁阈值从配置读取 | `compliance_service.py` | `block_threshold = 50` → `get_config_value("alert_block_count_threshold", 50)` |
| 离线倍数从配置读取 | `arp_collector_service.py` | `interval * 3` → `interval * get_config_value("alert_offline_threshold_multiplier", 3)` |
| 量纲 bug 修复 | `event_emitter.py` | 统一使用 0-100 百分比量纲 |
| 前端告警阈值配置 | `GeneralSettings.tsx`、`useTerminalData.ts` | 新增「告警阈值配置」分区、`AlertConfig` 接口 |
| i18n 标签 | `zh.ts`、`en.ts`、`ja.ts` | 4 组告警阈值标签（中/英/日） |

#### 验证结果

- Python 语法检查（6 个后端文件）：全部通过 ✅
- VS Code 诊断（5 个前端文件）：零错误 ✅
- 备份选项配置化验证：关闭白名单备份 → 手动备份 → 备份内容不含白名单 ✅
- 告警阈值配置化验证：系统设置页面显示「告警阈值配置」分区，4 个可编辑字段 ✅

#### 发布信息

- 版本号：v3.10.0
- 前一版本：v3.9.0
- 变更类型：功能新增 + 修复 (feat + fix)
- 涉及模块：backup_service.py, backup.py, main.py, event_emitter.py, compliance_service.py, arp_collector_service.py, system_config.py, config_service.py, GeneralSettings.tsx, useTerminalData.ts, Backup.tsx, zh.ts, en.ts, ja.ts

---

## [v3.9.0] - 2026-08-05

### 通知系统重构与定时备份 cron 调度

#### 问题描述

1. **通知管道黑洞**：`emit_event()` 优先将事件投递到 `NotificationAggregator`，导致 Worker 管道被绕过，所有事件（terminal.blocked、system.error 等）均被吞噬，通知功能完全失效。
2. **定时备份缺失**：`main.py` 的 `lifespan()` 中未注册 `scheduled_backup` 任务，即使备份配置已启用且设置了 cron 表达式，定时备份也从未执行。
3. **备份时间戳/路径错误**：远端备份时间戳少 8 小时（UTC→本地时区未转换），备份路径出现双斜杠（如 `/TAM//backup_full_20260805_181522.zip`）。
4. **事件类型字符串不匹配**：`system.error`、`system.warning`、`system.alert` 三个事件类型字符串与 `EventType` 枚举值不一致。
5. **备份列表排序 TypeError**：本地备份 `created_at`（无时区）与远端备份 `created_at`（有时区）无法比较。
6. **通知统计缺失 event_coverage**：统计 API 未返回事件覆盖率数据。

#### 根因分析

1. **通知管道黑洞**：`event_emitter.py` 的 `emit_event()` 方法优先检查 `NotificationAggregator.should_aggregate()`，若通过则直接投递到聚合器并返回，导致 Worker 管道（Redis Queue → Worker Pipeline）完全被绕过。
2. **定时备份缺失**：`main.py` 的 `lifespan()` 中仅注册了 5 个定时任务（scheduled_compliance_check、scheduled_ipguard_sync、scheduled_arp_collection、scheduled_firewall_sync、scheduled_notification_cleanup），遗漏了 `scheduled_backup`。
3. **备份时间戳/路径**：FTP MDTM 命令返回 UTC 时间，未调用 `astimezone(get_timezone())` 转换；`remote_path` 尾部斜杠未在拼接前去除。

#### 修复内容

| 项目 | 修改文件 | 说明 |
|------|---------|------|
| 通知管道黑洞修复 | `event_emitter.py` | 移除 `NotificationAggregator` 优先路径，直接调用 `NotificationService.emit()` |
| 事件类型字符串修正 | `event_emitter.py` | 修正 `system.error`、`system.warning`、`system.alert` 三个事件类型 |
| 实时事件分类 | `event_types.py` | 新增 `REALTIME_EVENT_TYPES` 集合和 `is_realtime_event()` 函数 |
| 事件覆盖率监控 | `notification_service.py` | 新增 `_get_event_coverage()` 方法，`get_statistics()` 返回 `event_coverage` |
| 自动封堵事件发射 | `compliance_service.py` | `auto_block_non_compliant` 新增 `emit_auto_block_triggered` 调用 |
| 终端离线检测 | `arp_collector_service.py` | 基于 `last_seen` 时间戳检测离线终端，发射 `TERMINAL_OFFLINE` 事件 |
| 定时备份 cron 调度 | `main.py` | 重写 `scheduled_backup()` 函数，支持 cron 表达式解析 |
| cron 匹配器 | `main.py` | 新增 `_should_run_backup_now()` 函数，支持 `*`、逗号、步长值 |
| Redis 去重 | `main.py` | 使用 Redis 键 `notify:last_backup_run` 防止同一分钟内重复执行 |
| 备份审计日志 | `main.py` | 定时备份结果写入 `audit_logs` 表，action=`scheduled_backup` |
| FTP 时间戳修复 | `backup_service.py` | UTC 时间转换为本地时区 (UTC+8) |
| FTP 路径修复 | `backup_service.py` | 使用 `remote_path.rstrip('/')` 去除尾部斜杠 |
| 备份排序修复 | `backup.py` | 统一 datetime 对象为无时区进行比较 |
| 备份轮询间隔配置 | `system_config.py`、`config_service.py` | 新增 `scheduler_backup_interval` 配置项 |
| 前端配置项 | `useTerminalData.ts`、`GeneralSettings.tsx` | 新增 `scheduler_backup_interval` 类型定义和前端配置项 |

#### 验证结果

- **通知管道**：触发 terminal.blocked 事件，notification_logs 表正确产生记录 ✅
- **事件字符串**：订阅 system.error 事件，触发后正确收到通知 ✅
- **cron 调度**：设置 schedule 为 `* * * * *`，60 秒内触发备份 ✅
- **FTP 时间戳**：`/api/v1/backup/list` 返回远端备份时间戳为本地时间（+08:00） ✅
- **FTP 路径**：`file_path` 为 `/TAM/backup_xxx.zip`（无双斜杠） ✅
- **审计日志**：`audit_logs` 表有 `scheduled_backup` 记录 ✅
- **事件覆盖率**：`/api/v1/notifications/statistics` 返回 `event_coverage` 字段 ✅

#### 发布信息

- 版本号：v3.9.0
- 前一版本：v3.8.0
- 变更类型：修复 + 功能新增 (fix + feat)
- 涉及模块：event_emitter.py, notification_service.py, main.py, backup_service.py, compliance_service.py, arp_collector_service.py

---

## [v3.8.0] - 2026-08-05

### 缓存 TTL 可配置化与 Blacklist 数据一致性修复

#### 问题描述

1. **缓存 TTL 硬编码**：IPGuard 和白名单缓存有效期在 `compliance_service.py` 中硬编码为常量，无法通过系统设置动态调整。
2. **Blacklist 重复记录**：黑名单管理显示数量（236）与实际防火墙封堵数量（235）不一致，根因为数据库索引非唯一、并发竞态条件、重封堵逻辑缺失。
3. **BlacklistResponse 500 错误**：`blocked_at` 字段定义为非空 `datetime`，但数据库部分记录为 NULL，导致 API 返回 500。

#### 根因分析

1. **缓存 TTL 硬编码**：`IPGUARD_CACHE_TTL = 900` 和 `WHITELIST_CACHE_TTL = 300` 为模块级常量，无法通过配置中心动态调整。
2. **Blacklist 重复记录**：
   - `idx_blacklist_unique_active` 索引虽命名为 "unique"，但实际为普通索引
   - `auto_block_non_compliant()` 和 `_apply_compliance_result()` 存在 check-then-act 竞态条件
   - 终端已封堵但 blacklist 条目被解封后，重封堵逻辑基于 `terminal.status != "blocked"` 判断，跳过了需要重建 blacklist 条目的场景
3. **BlacklistResponse 500**：`blocked_at: datetime`（非空）与数据库 NULL 值冲突。

#### 修复内容

| 项目 | 修改文件 | 说明 |
|------|---------|------|
| 缓存 TTL 可配置 | `system_config.py` (schemas) | 新增 `CacheConfigResponse`，扩展 `AllConfigsResponse` |
| 缓存 TTL 可配置 | `config_service.py` | 新增 `cache_ipguard_ttl`/`cache_whitelist_ttl` 默认配置 |
| 缓存 TTL 可配置 | `compliance_service.py` | 替换硬编码 TTL 为动态 `get_config_value()` 读取 |
| 缓存 TTL UI | `GeneralSettings.tsx`、i18n | 新增缓存配置分组 UI 和多语言翻译 |
| Blacklist 唯一索引 | `blacklist.py` | `idx_blacklist_unique_active` 改为 `unique=True` |
| Blacklist 竞态修复 | `compliance_service.py` | `auto_block_non_compliant` 添加 `IntegrityError` 捕获和回滚 |
| Blacklist 竞态修复 | `compliance_service.py` | `recalculate_all_compliance` 添加 `IntegrityError` 捕获和回滚 |
| Blacklist 重封堵 | `compliance_service.py` | `_apply_compliance_result` 修复 `mac_norm` 未定义，重封堵判断改为基于 blacklist 活跃条目 |
| Schema 修复 | `terminal.py` | `blocked_at: datetime` → `blocked_at: datetime \| None = None` |
| 前端功能补全 | `SystemSettings.tsx`、`Notifications.tsx`、`constants.ts`、`LDAPImportModal.tsx` | 配置摘要、通知重试、LDAP 常量化 |
| 数据库迁移 | `030_blacklist_unique_index.py` | 清理重复记录 + 创建唯一部分索引 |

#### 验证结果

- **Blacklist 数据一致性**：blacklist_active（200）= terminal_blocked（200）✅
- **重复记录检查**：total_active（200）= unique_ip_mac（200）✅
- **唯一索引**：`CREATE UNIQUE INDEX idx_blacklist_unique_active` ✅
- **后端错误日志**：0 条 ERROR ✅
- **Blacklist API**：正常返回，`blocked_at` 字段可空 ✅
- **迁移脚本**：`029_terminal_non_compliant_confirm_count → 030_blacklist_unique_index` 成功执行 ✅

---

## [v3.7.1] - 2026-08-04

### 前端桥接虚拟机场景修复与系统设置 500 错误修复

#### 问题描述

1. **桥接虚拟机场景状态显示错误**：终端列表中宿主机（10.8.14.100）因 MAC（C0-3C-59-01-9B-A9）在黑名单中被错误显示为 non_compliant，但实际 IP+MAC 组合在 IPGuard 中为 compliant。

2. **系统设置 General 页面 500 错误**：admin 超管用户访问系统设置 General 页面时，前端报 500 内部错误，后端日志显示 `ValidationError`。

#### 根因分析

1. **前端覆盖逻辑错误**：`Terminals.tsx` 存在对 `compliance_status` 的二次覆盖逻辑：
   ```javascript
   // 修复前
   let complianceStatus = mac.compliance_status || 'unknown';
   if (blackMatchType && complianceStatus !== 'bypass' && complianceStatus !== 'non_compliant') {
       complianceStatus = 'non_compliant'; // 错误覆盖
   }
   ```
   桥接虚拟机场景下，虚拟机（10.8.14.32）被封堵后，MAC 被加入黑名单。前端发现宿主机（10.8.14.100）的 MAC 在黑名单中，强制将其 compliance_status 从 `compliant` 覆盖为 `non_compliant`。

2. **ConfigCategory 枚举缺失**：v3.7.0 新增的 `compliance_confirm_threshold` 配置项存在两个问题：
   - `category='compliance'` 不在 `ConfigCategory` 枚举值列表中
   - `is_readonly=NULL` 但 schema 要求为 `bool` 类型
   
   `SystemConfigResponse.model_validate()` 校验失败，抛出 `ValidationError`，导致 settings 相关 API 全部返回 500。

#### 修复内容

| 项目 | 修改文件 | 说明 |
|------|---------|------|
| 前端覆盖逻辑移除 | `frontend/src/pages/Terminals.tsx` | 移除对 compliance_status 和 firewall_tag 的二次覆盖，直接使用后端返回值 |
| 枚举扩展 | `system_config.py` (schemas) | 新增 `COMPLIANCE = "compliance"` |
| Schema 新增 | `system_config.py` (schemas) | 新增 `ComplianceConfigResponse` |
| 分组响应 | `system_config.py` (schemas) | `AllConfigsResponse` 新增 `compliance` 字段 |
| 配置服务 | `config_service.py` | 导入新 Schema、seed defaults、get_all_grouped |
| 数据修复 | `system_config` 表 | `UPDATE ... SET is_readonly = false WHERE is_readonly IS NULL` |

#### 业务验证结果

**桥接虚拟机场景验证**：
- 宿主机 10.8.14.100：后端 compliant，前端显示 compliant ✅
- 虚拟机 10.8.14.32：后端 non_compliant，前端显示 non_compliant ✅
- 全量检查：1420 终端状态与后端一致
- 桥接场景统计：20 个桥接场景终端状态正确

**Settings API 验证**：
- `GET /api/v1/settings/` → 200 OK，返回 compliance 分类
- `GET /api/v1/settings/list` → 200 OK，`compliance_confirm_threshold` 正常显示

**全量终端合规验证**：
- 合规终端：372 个（全部在 IPGuard 中，全部未封堵）
- 非合规终端：200 个（全部不在白名单和 IPGuard 中，全部已封堵）
- 豁免终端：830 个（全部在白名单中，全部未封堵）
- 非合规数 = 封堵数：200 = 200 ✅

#### 发布信息

- 版本号：v3.7.1
- 前一版本：v3.7.0
- 变更类型：修复 (fix)
- 涉及模块：frontend/src/pages/Terminals.tsx、backend/app/schemas/system_config.py、backend/app/services/config_service.py

---

## [v3.7.0] - 2026-08-03

### 合规判定优化：消除合规振荡与封堵失败修复

#### 问题描述

- 非合规终端数（199）大于已封堵终端数（193），存在 6 个 non_compliant+unblocked 异常终端
- 审计日志显示 compliant→non_compliant 状态翻转达 189 次，远超预期，导致防火墙频繁封堵/解封堵（合规振荡）

#### 根因分析

1. **合规振荡**：IPGuard OCULAR3 的 `AGENT.AGT_IP_MAC_STR` 字段记录 agent 当前上报的 IP+MAC 绑定关系，当终端 DHCP 续租或重连时该字段更新，导致 TAM 的 IP+MAC 精确匹配失败。每次 IPGuard 同步数据波动（1132~1139 条之间变化）都直接触发 compliant→non_compliant 翻转并立即封堵，下次同步恢复后又立即解封堵。
2. **封堵失败无重试**：防火墙 API 调用失败后终端停留在 non_compliant+unblocked，`scheduled_compliance_check` 只查询 unknown 终端，不会重试已标记 non_compliant 的终端。
3. **缓存 TTL 等于同步间隔**：IPGUARD_CACHE_TTL=600s 与同步间隔 600s 完全相等，同步执行期间缓存已过期。
4. **同步失败返回空列表**：`_load_all_ipguard_cache` 同步失败时返回空列表 `[]`，导致所有终端被判定为 non_compliant。

#### 修复内容

| 改进项 | 修改文件 | 说明 |
|--------|----------|------|
| 翻转确认机制 | `compliance_service.py`、`terminal.py`、`029_terminal_non_compliant_confirm_count.py` | compliant→non_compliant 需连续 N 次同步确认（默认 2）后才变更状态 |
| 封堵失败重试 | `main.py` | `scheduled_compliance_check` 增加 non_compliant+unblocked 终端封堵重试 |
| 缓存 TTL 修正 | `compliance_service.py` | TTL 600s→900s（1.5 倍同步间隔） |
| 同步失败数据保护 | `compliance_service.py` | 新增备份缓存；同步失败时从备份加载；数据完全不可用时中止重算 |
| 配置项支持 | `system_config` 表 | 新增 `compliance_confirm_threshold` 配置项（默认 2，范围 1-10） |

#### 数据库变更

- 新增字段：`terminals.non_compliant_confirm_count`（INTEGER, NOT NULL, DEFAULT 0）
- 迁移脚本：`backend/alembic/versions/029_terminal_non_compliant_confirm_count.py`

#### 业务验证结果

- 非合规未封堵终端数：6 → 0（重试机制修复全部异常终端）
- 合规重算状态变化：1349 终端全部 unchanged（确认机制生效，0 次 compliant→non_compliant 翻转）
- IPGuard 缓存 TTL：891 秒（接近 900，符合预期）
- 备份缓存：已创建（EXISTS=1, TTL=-1 永久）
- 健康检查：所有服务 healthy，DB/Redis 连接正常
- 终端状态分布：bypass 779 + compliant 367 + non_compliant 203(blocked) = 1349，非合规数 = 封堵数

#### 发布信息

- 版本号：v3.7.0
- 前一版本：v3.6.18
- 变更类型：功能新增+优化 (feat+perf)
- 涉及模块：backend/app/services/compliance_service.py、backend/app/main.py、backend/app/models/terminal.py、backend/alembic/versions/029_terminal_non_compliant_confirm_count.py

---

## [v3.6.18] - 2026-07-16

### 防火墙封锁状态一致性修复

#### 问题描述

- IP `10.8.12.206` 在 Web 终端列表中显示为"已被封锁"状态，但实际防火墙上没有该条封锁记录。

- 数据库状态与防火墙实际状态脱节，存在安全误报风险。

#### 根因分析

合规自动封锁（`auto_block_non_compliant`）使用异步队列（fire-and-forget）调用防火墙 API：

1. `enqueue_operation()` 将封锁操作放入 `asyncio.Queue`，立即返回
2. 代码判断 `all_success = len(errors) == 0`（只检查入队是否成功）
3. 入队成功就立即更新 Terminal.status = blocked、创建 Blacklist 记录
4. 实际防火墙 API 调用在后台队列中异步执行
5. 如果防火墙调用失败（网络问题、API 错误等），只打日志，不回滚数据库状态
6. 导致 Web 显示已封锁但防火墙无数据

受影响的函数：
- `auto_block_non_compliant` - 合规自动封锁
- `_block_on_firewall` - 单防火墙封锁
- `_unblock_on_firewall` - 单防火墙解封

#### 修复内容

将以上三个函数全部改为同步调用防火墙 API，确认成功后再更新数据库：

| 函数 | 修改前 | 修改后 |
|------|-------|-------|
| `auto_block_non_compliant` | 入队后立即更新 DB | 同步调用 block_ip，成功后更新 DB |
| `_block_on_firewall` | 入队后返回 True | 同步调用 block_ip，返回实际结果 |
| `_unblock_on_firewall` | 入队后返回 True | 同步调用 unblock_ip，返回实际结果 |

#### 验证方法

- 语法检查：python -m py_compile 验证通过
- 生产环境建议升级后执行一次防火墙对账，修正历史不一致数据
- 对账 API：POST /api/v1/system/firewall-reconciliation

#### 额外修复：对账服务 NameError

- 问题：`firewall_reconciliation_service.py` 缺少 `or_` 导入，导致对账服务自始至终无法运行
- 修复：补充 `from sqlalchemy import select, delete, or_`
- 业务验证：修复后对账成功运行，确认防火墙 188 条记录与数据库 188 条记录完全同步

#### 业务验证结果

- 合规重算：1320 个终端全部处理，0 状态变更，0 错误，耗时 1 秒
- 防火墙对账：188 vs 188 完全同步，0 错误
- Terminal#723 (10.8.28.241)：blocked 状态正确，黑名单记录存在，防火墙有对应记录
- Terminal#724 (10.8.28.130)：blocked 状态正确，黑名单记录存在，防火墙有对应记录
- 10.8.12.206：当前 unblocked 状态，无黑名单记录（历史不一致已修正）

#### 发布信息

- 版本号：v3.6.18
- 前一版本：v3.6.18
- 涉及模块：backend/app/services/compliance_service.py
- 变更类型：修复 (fix)

---

## [v3.6.18] - 2026-07-16

### 审计日志系统修复与优化

#### 问题诊断

- **审计日志爆炸增长（13万条/天）**
  - 根因：ARP 采集服务在更新已存在终端时，强制将 `compliance_status` 重置为 `"unknown"`、`wl_match_type` 重置为 `None`
  - 导致每次 ARP 采集（5分钟间隔）后合规检查都认为终端状态从 unknown 变为 compliant/bypass，产生大量无意义的 `compliance_status_changed` 日志
  - 数据验证：131,854 条合规状态变更日志中，131,398 条（99.7%）的 old_compliance 为 `unknown`，真正的状态变更仅 456 条

- **筛选下拉菜单与实际结果不匹配**
  - 根因：前端 action 值与后端生成的 action 值不一致（如前端用 `add_whitelist`，后端实际为 `whitelist_create`）
  - 前端分类体系缺少防火墙、合规基线等类别，无法正确归类部分日志

- **Action 字段格式不统一**
  - 混合使用不同命名规范（`block_terminal` vs `firewall_block` vs `add_whitelist`）
  - 统一为 `snake_case` 格式和 `<noun>_<verb>` 命名模式

#### 修复内容

- **后端：ARP 采集服务修复**
  - 移除已存在终端更新时对 `compliance_status` 和 `wl_match_type` 的强制重置
  - 保留 `updated_at`、`source_tag`、`source` 等必要字段更新
  - 关联文件：`backend/app/services/arp_collector_service.py`

- **前端：审计日志筛选与展示全面优化**
  - 重写 `ACTION_CATEGORIES`、`actionLabelKeys`、`ACTION_CATEGORY_MAP`，确保所有 action 值与后端完全一致
  - 新增 `firewall`（防火墙）和 `baseline`（合规基线）分类
  - 添加向后兼容的旧 action 名称映射（`block_ip`→`firewall_block`、`add_whitelist`→`whitelist_create` 等）
  - 新增 `CATEGORY_BADGE_STYLES` 样式映射，完善各分类徽章样式
  - 关联文件：`frontend/src/pages/AuditLogs.tsx`

- **i18n：翻译补全**
  - 新增 `firewall`、`baseline` 分类标签翻译
  - 新增 `password_reset`、`recalculate_compliance` 等动作标签翻译
  - 新增防火墙、合规基线等资源类型翻译
  - 关联文件：`frontend/src/i18n/locales/{zh,en,ja}.ts`

- **数据清理**
  - 清理历史无效审计日志：删除所有 `old_compliance = 'unknown'` 的 `compliance_status_changed` 日志
  - 清理效果：132,394 条 → 996 条，减少 99.2%

#### 验证结果

- 终端合规状态分布：bypass 510、compliant 312、non_compliant 147，无 unknown 状态
- ARP 采集正常运行，不再重置终端合规状态
- 所有 24 种 action 值均为 snake_case 格式，前后端一致
- 前端筛选下拉菜单分类与实际日志数据匹配

#### 提交记录

- Commit: `fix(audit): 修复审计日志爆炸增长、筛选不匹配和action格式不一致问题`
- 版本号：v3.6.18 (Patch)

---

## [v3.6.16] - 2026-07-16

### 合规基线管理按钮交互体验优化

#### 变更内容

- **Run Compliance Check 添加 Force Re-check 选项**
  - 问题：前端硬编码 `force: false`，只检查 unknown 终端，但 ARP 采集时已自动处理所有终端
  - 修复：添加 `forceCheck` 复选框 state，传递到 API 请求
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

- **Auto Block 确认对话框优化**
  - 问题：使用浏览器原生 `window.confirm`，与项目 UI 设计不一致
  - 修复：用自定义 Modal 组件替换，拆分为 `handleAutoBlockClick`（打开 Modal）和 `handleAutoBlockConfirm`（确认执行）
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

- **Auto Block / Auto Unblock 提示优化**
  - 问题：返回0条操作时仅显示数字，用户不理解原因
  - 修复：Auto Block 返回0条时 toast.info 提示"所有不合规终端已封锁，无需重复操作"
  - 修复：Auto Unblock 返回0解封时 toast.info 提示"被封锁终端均未变为合规状态，暂无需要解封的终端"
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

- **后端 message 字段补全**
  - 问题：`AutoBlockResult` 和 `AutoUnblockResult` schema 缺失 message 字段
  - 修复：两个 schema 添加 `message: str | None = None`；`auto_unblock_compliant` 方法返回 message
  - 关联文件：`backend/app/schemas/data_source.py`、`backend/app/services/compliance_service.py`

- **i18n 翻译补全**
  - 新增4条翻译 key：`forceRecheck`、`autoBlockWarning`、`autoBlockNoAction`、`autoUnblockNoAction`
  - 关联文件：`frontend/src/i18n/locales/{zh,en,ja}.ts`

#### 提交记录

- Commit: `fix(compliance): 优化合规基线管理按钮交互体验`
- 版本号：v3.6.16 (Patch)

---

## [v3.6.15] - 2026-07-16

### 黑名单数据一致性修复

#### 功能变更

- **黑名单过期时间过滤修复**
  - 变更描述：修复黑名单管理页面与防火墙、Dashboard、终端管理统计数量不一致问题
  - 变更内容：
    - `get_blacklist` 方法添加 `expires_at` 过滤条件
    - `get_blacklist_count` 方法添加 `expires_at` 过滤条件
    - `get_blacklist_stats` 方法添加 `expires_at` 过滤条件
  - 根因：黑名单管理页面未过滤已过期记录，导致显示数量偏多（158 vs 146）
  - 关联文件：`backend/app/services/terminal_service.py`

- **防火墙对账记录类型修复**
  - 变更描述：修复对账服务创建的记录被错误标记为手动封锁
  - 变更内容：
    - `_create_db_entries` 方法中 `is_auto_blocked` 从 `False` 改为 `True`
    - `_get_db_active_blacklist` 方法添加 `expires_at` 过滤条件
  - 根因：对账服务自动创建的记录应标记为自动封锁
  - 关联文件：`backend/app/services/firewall_reconciliation_service.py`

- **防火墙查询导入修复**
  - 变更描述：修复 `terminal_service.py` 中 `decrypt_config` 未导入导致的 NameError
  - 根因：`_get_sangfor_service_by_tag` 方法调用 `decrypt_config` 但未导入
  - 关联文件：`backend/app/services/terminal_service.py`

- **防火墙查询结果解析修复**
  - 变更描述：修复 `cli.py` 中防火墙查询结果解析逻辑
  - 变更内容：`result.get("data", [])` 修正为 `result.get("data", {}).get("items", [])`
  - 根因：防火墙 API 返回格式为 `{"data": {"items": [...]}}`，原代码将 `data` 当作列表处理
  - 关联文件：`backend/cli.py`

#### 代码变更清单

| 文件 | 变更内容 | 类型 |
|------|---------|------|
| `backend/app/services/terminal_service.py` | 添加 decrypt_config 导入、3个方法添加 expires_at 过滤 | fix |
| `backend/app/services/firewall_reconciliation_service.py` | 添加 expires_at 过滤、is_auto_blocked 改为 True | fix |
| `backend/cli.py` | 修复防火墙查询结果解析逻辑 | fix |

#### 数据库变更

无数据库迁移，仅数据修复：
- 删除 12 条 reconciliation 来源的 Manual 类型冗余记录
- 重新激活 1 条被误标为解封的黑名单记录（IP: 10.8.19.175）

#### 测试验证

- 数据库验证：活跃黑名单 147 条，与防火墙一致
- 防火墙查询验证：`./manage.sh scheduler trigger firewall_query` 返回 147 条
- Manual 类型记录：0 条

#### 文档更新

| 文件 | 更新内容 |
|------|---------|
| `docs/changelog.md` | 添加 v3.6.15 变更记录 |
| `docs/release-notes.md` | 添加 v3.6.15 发布记录 |
| `docs/git-workflow-guide.md` | 更新文档版本号 |

---

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

---

## [v3.6.13] - 2026-07-14

### 业务逻辑闭环优化

#### 功能变更

- **移除手动封锁/解封功能**
  - 变更描述：系统核心业务逻辑闭环改为合规自动判断封锁和解封锁，移除所有手动操作入口
  - 根因：手动操作可能导致状态不一致，违背合规自动管理原则
  - 变更内容：
    - 删除手动封锁 API 端点：`POST /terminals/block/{ip_address}`
    - 删除手动解封 API 端点：`POST /terminals/unblock/{ip_address}`
    - 删除黑名单手动添加端点：`POST /blacklist/`
    - 删除黑名单手动删除端点：`DELETE /blacklist/{identifier}`
    - 删除后端服务方法：`block_ip`, `unblock_ip`, `add_to_blacklist`, `delete_from_blacklist`
  - 关联文件：`backend/app/api/v1/endpoints/terminals.py`, `backend/app/api/v1/endpoints/blacklist.py`, `backend/app/services/terminal_service.py`

- **终端管理优化**
  - 变更描述：优化终端管理页面操作权限，确保业务操作统一
  - 变更内容：
    - 合规终端（compliant）无任何操作按钮
    - 白名单终端（bypass）无移出白名单操作，移除动作集中在白名单管理中
    - 仅不合规（non_compliant）和未知（unknown）终端保留加白操作
  - 关联文件：`frontend/src/pages/Terminals.tsx`

- **黑名单管理优化**
  - 变更描述：移除解封按钮和状态标签页，只显示当前被封锁的记录
  - 变更内容：
    - 移除解封按钮和删除确认模态框
    - 移除状态标签页（Active/Unblocked），只显示当前被封锁的记录
    - 封锁和解封的追溯通过完整的审计日志查询
  - 关联文件：`frontend/src/pages/Blacklist.tsx`

#### 代码变更清单

| 文件 | 变更内容 | 类型 |
|------|---------|------|
| `backend/app/api/v1/endpoints/terminals.py` | 删除手动封锁/解封端点 | feat |
| `backend/app/api/v1/endpoints/blacklist.py` | 删除手动添加/删除黑名单端点 | feat |
| `backend/app/services/terminal_service.py` | 删除手动封锁/解封服务方法 | feat |
| `frontend/src/pages/Terminals.tsx` | 优化终端操作权限逻辑 | feat |
| `frontend/src/pages/Blacklist.tsx` | 移除解封按钮和状态标签页 | feat |
| `docs/business-workflow.md` | 更新业务工作流文档 | docs |
| `docs/api.md` | 更新 API 文档 | docs |

#### 测试验证

- API 端点验证：手动封锁/解封端点返回 404/405 错误
- 前端构建验证：`./manage.sh -y update` 构建成功
- 服务状态验证：`./manage.sh status` 所有服务正常
- 业务流程验证：合规自动封锁/解封逻辑正常运行

---

## [v3.6.11] - 2026-07-14

### 系统稳定性优化

#### Bug 修复

- **数据库连接泄漏**
  - 问题描述：日志中频繁出现 `The garbage collector is trying to clean up non-checked-in connection` 错误
  - 根因：`notification_logging.py` 中数据库会话管理不当，使用 `async with` 创建会话后立即返回导致连接泄漏
  - 修复方案：重构所有日志方法，使用 try/finally 模式确保会话正确关闭
  - 关联文件：`backend/app/services/notification_logging.py`, `backend/app/core/database.py`

- **邮件限流**
  - 问题描述：`Rate limit exceeded for qiangnian.zheng@inceptio.ai`
  - 根因：合规计算时大量终端状态变化触发大量邮件发送，超过 SMTP 服务限流
  - 修复方案：所有通知事件先经过 `NotificationAggregator` 聚合，5分钟窗口内同类事件合并发送
  - 关联文件：`backend/app/services/event_emitter.py`, `backend/app/services/compliance_service.py`

- **防火墙并发限制**
  - 问题描述：`当前在线用户已超过最大并发用户限制`
  - 根因：合规计算时多个终端并发调用 Sangfor API，超过设备并发连接限制
  - 修复方案：防火墙操作改为队列串行处理，使用信号量限制最大并发连接数为3
  - 关联文件：`backend/app/services/compliance_service.py`, `backend/app/services/sangfor_service.py`

#### 架构优化

- **合规计算分批处理**：将合规计算改为分批事务处理，每批100个终端
  - 每批独立执行 flush() 和 commit()，避免长事务锁定
  - 减少单事务处理时间，降低连接持有时间

- **通知聚合器**：新增 `NotificationAggregator` 模块
  - 实现事件收集、合并和异步发送逻辑
  - 支持时间窗口聚合（5分钟）
  - 支持定期发送任务（每30秒检查并发送聚合通知）

#### 代码变更清单

| 文件 | 变更内容 | 类型 |
|------|---------|------|
| `backend/app/core/database.py` | 优化连接池配置 | fix |
| `backend/app/services/notification_logging.py` | 重构数据库会话管理 | fix |
| `backend/app/services/event_emitter.py` | 修改 emit_event 经过聚合器 | fix |
| `backend/app/services/compliance_service.py` | 分批处理 + 队列化防火墙操作 | fix |
| `backend/app/services/sangfor_service.py` | 队列处理逻辑（已有） | — |
| `backend/app/services/notification_aggregator.py` | 新增通知聚合器模块 | feat |

#### 验证方式

```bash
# 验证服务健康
./manage.sh health

# 触发合规计算验证
./manage.sh scheduler trigger compliance_check

# 检查日志无错误
./manage.sh logs backend -n 100 | grep -E "garbage|rate limit|并发用户"
# 预期结果：无匹配输出
```

#### 文档更新

| 文件 | 更新内容 |
|------|---------|
| `docs/changelog.md` | 添加 v3.6.11 变更记录 |
| `docs/release-notes.md` | 添加 v3.6.11 发布记录 |
| `.trae/documents/code-review-commit-plan.md` | 代码审查和提交计划 |

---

## [v3.6.10] - 2026-07-09

### 备份管理优化

#### 新增功能

- **定时备份白名单选项**：备份配置新增 `backup_whitelist` 字段，支持定时备份时选择是否包含白名单数据
  - `BackupConfig` 数据类添加 `backup_whitelist: bool = True` 字段
  - API Schema (`BackupConfigResponse`, `BackupConfigUpdate`) 添加对应字段
  - 前端定时备份设置表单添加"备份白名单"复选框

#### Bug 修复

- **手动备份失败**：修复 `create_archive()` 方法签名参数不匹配问题
  - 原方法定义：`create_archive(self, temp_dir, files)`
  - 修复后：`create_archive(self, temp_dir, files, backup_type="full")`
- **白名单备份失败**：修复 `NotificationRule` 模型字段映射错误
  - 移除不存在的 `conditions` 字段
  - 添加正确的字段：`suppress_enabled`, `suppress_window`, `escalate_enabled`, `escalate_threshold`, `escalate_window`, `escalate_severity`

#### 代码变更

| 文件 | 变更内容 |
|------|---------|
| `backend/app/services/backup_service.py` | 修复 `create_archive()` 方法签名，添加 `backup_type` 参数 |
| `backend/app/services/backup_service.py` | 修复 `_backup_system_config_db()` 中 `NotificationRule` 字段映射 |
| `backend/app/services/backup_service.py` | 修复 `_restore_system_config_db()` 中 `NotificationRule` 字段映射 |
| `backend/app/services/backup_service.py` | `BackupConfig` 添加 `backup_whitelist` 字段 |
| `backend/app/schemas/backup.py` | `BackupConfigResponse` 添加 `backup_whitelist` 字段 |
| `backend/app/schemas/backup.py` | `BackupConfigUpdate` 添加 `backup_whitelist` 字段 |
| `backend/app/api/v1/endpoints/backup.py` | `/config` GET 返回添加 `backup_whitelist` |
| `backend/app/api/v1/endpoints/backup.py` | `/config` PUT 更新添加 `backup_whitelist` |
| `frontend/src/pages/Backup.tsx` | `BackupConfig` 接口添加 `backup_whitelist` 字段 |
| `frontend/src/pages/Backup.tsx` | 定时备份设置表单添加白名单备份复选框 |
| `frontend/src/i18n/locales/zh.ts` | 添加 `backupWhitelist` 翻译 |
| `frontend/src/i18n/locales/en.ts` | 添加 `backupWhitelist` 翻译 |
| `frontend/src/i18n/locales/ja.ts` | 添加 `backupWhitelist` 和相关备份选项翻译 |

#### i18n 翻译覆盖

| 语言 | 翻译项 |
|------|--------|
| 中文 | `backupWhitelist: '备份白名单'` |
| 英文 | `backupWhitelist: 'Backup Whitelist'` |
| 日文 | `backupWhitelist: 'ホワイトリストをバックアップ'` |

#### 文档更新

| 文件 | 更新内容 |
|------|---------|
| `docs/changelog.md` | 添加 v3.6.10 变更记录 |
| `docs/release-notes.md` | 添加 v3.6.10 发布记录 |
| `.trae/documents/v3.6.10-release-plan.md` | v3.6.10 发布计划文档 |

#### 验证方式

```bash
# 验证版本一致性
./manage.sh version check

# 验证服务健康
./manage.sh health

# 验证备份功能
# 1. 手动执行全量备份
# 2. 手动执行白名单备份
# 3. 验证定时备份配置包含白名单选项
```

---

## [v3.6.9] - 2026-07-08

### 合规判断逻辑一致性优化

#### 新增功能

- **数据导出功能**：终端管理、白名单管理、黑名单管理页面新增导出功能
  - 支持全量导出和按筛选条件导出
  - 后端新增 `GET /terminals/export`、`GET /whitelist/export`、`GET /blacklist/export` 端点
  - 前端修改 `handleExport` 调用后端 API，传递所有筛选条件

#### Bug 修复

- **通知渠道创建 500 错误**：修复 `notifications.py` 中 `channel.channel_type` 属性访问错误
- **合规判断逻辑不一致**：ARP 采集和定时任务的合规检查路径与白名单变更触发的全量重算路径行为不一致

#### 代码变更

| 文件 | 变更内容 |
|------|---------|
| `backend/app/services/compliance_service.py` | 新增 `_apply_compliance_result` 共享方法，修改 `recalculate_all_compliance` 和 `batch_check_compliance` |
| `backend/app/services/arp_collector_service.py` | 使用共享方法 `_apply_compliance_result` |
| `backend/app/main.py` | 定时任务使用共享方法 `_apply_compliance_result` |
| `backend/app/api/v1/endpoints/notifications.py` | 修复 `channel.channel_type` → `channel.type` |
| `backend/app/api/v1/endpoints/terminals.py` | 新增 `GET /terminals/export` 端点 |
| `backend/app/api/v1/endpoints/whitelist.py` | 新增 `GET /whitelist/export` 端点 |
| `backend/app/api/v1/endpoints/blacklist.py` | 新增 `GET /blacklist/export` 端点 |
| `frontend/src/pages/Terminals.tsx` | 修改 `handleExport` 调用后端 API |
| `frontend/src/pages/Whitelist.tsx` | 修改 `handleExport` 调用后端 API |
| `frontend/src/pages/Blacklist.tsx` | 修改 `handleExport` 调用后端 API |

#### 功能一致性对比

| 功能 | 修改前（ARP/定时） | 修改后（统一） |
|------|------------------|---------------|
| 更新 comments（白名单备注） | ❌ | ✅ |
| 触发事件通知 | ❌ | ✅ |
| 自动解封 | ❌ | ✅ |
| 自动封堵（同步） | ❌（异步） | ✅（同步） |

#### 文档更新

| 文件 | 更新内容 |
|------|---------|
| `docs/changelog.md` | 添加 v3.6.9 变更记录 |
| `docs/release-notes.md` | 添加 v3.6.9 发布记录 |
| `docs/backend.md` | 更新合规检查流程说明 |
| `docs/datasource-lifecycle.md` | 更新 ARP 采集后的合规处理流程 |
| `docs/business-workflow.md` | 更新合规判定流程 |

#### 验证方式

```bash
# 验证版本一致性
./manage.sh version check

# 验证服务健康
./manage.sh health

# 验证数据一致性
# bypass 终端备注完整性：SELECT COUNT(*) FROM terminals WHERE compliance_status='bypass' AND comments IS NULL
```

---

## [v3.6.8] - 2026-07-08

### 数据导出与通知渠道修复

#### Bug 修复

- **数据导出功能**：前端数据导出仅支持导出当前页数据，改为调用后端 API 支持全量导出和筛选导出
- **通知渠道 500 错误**：创建通知渠道时报 500 内部错误但实际创建成功的问题

---

## [v3.6.7] - 2026-07-08

### 版本统一管理优化

#### 新增功能

- **版本一致性检查命令**：`./manage.sh version check`
  - 检查 7 个版本号文件：VERSION、frontend/package.json、.env、.env.example、docker-compose.yml、manage.sh、frontend/vite.config.ts
  - 显示每个文件的版本状态（一致/不一致）
  - 不一致时给出修复建议

- **一键版本升级命令**：`./manage.sh version bump <version>`
  - 自动更新所有版本号文件到指定版本
  - 版本格式验证（X.Y.Z）
  - 提供后续操作指引

#### 代码变更

| 文件 | 变更内容 |
|------|---------|
| `manage.sh` | 新增 `cmd_version_check()` 和 `cmd_version_bump()` 函数，修复 VERSION fallback 值 |
| `frontend/vite.config.ts` | 修复 getVersion() fallback 值为 3.6.6 |

#### 文档更新

| 文件 | 更新内容 |
|------|---------|
| `docs/manage-sh-reference.md` | 版本命令文档补充 check/bump 子命令 |
| `docs/deployment.md` | 版本命令说明补充 check/bump 子命令 |
| `docs/changelog.md` | 添加 v3.6.7 变更记录 |
| `docs/release-notes.md` | 添加 v3.6.7 发布记录 |

#### 验证方式

```bash
# 验证版本一致性
./manage.sh version check

# 验证服务健康
./manage.sh health

# 验证 API 版本
curl -sk http://localhost:8000/api/v1/system/health
```

---

## [v3.6.6] - 2026-07-08

### Bug 修复与数据一致性增强

#### 黑名单管理修复

- **Unblocked 标签筛选不出数据**：统一 active/unblocked 筛选逻辑，同时考虑 `auto_unblocked` 和 `unblocked_at` 两个字段；通过数据迁移 026 补全历史记录缺失的 `unblocked_at` 字段
- **统计基于当前页数据**：新增 `GET /api/v1/blacklist/stats` 服务端统计接口，Active Tab 下使用全局统计数据
- **Unblocked 标签显示一致性**：UI 标签显示条件从 `auto_unblocked` 改为 `auto_unblocked || unblocked_at`
- **自动解封未设置 unblocked_at**：compliance_service.py 中 3 处自动解封逻辑补全 `unblocked_at` 字段

#### 终端管理修复

- **timestamp 被覆盖**：ARP 采集更新终端时错误更新 `timestamp`（创建时间），新增 `updated_at` 字段（迁移 025），采集仅更新 `updated_at`
- **白名单备注不一致**：白名单备注更新逻辑优化（支持备注变更时替换旧备注）；白名单删除时清除关联终端备注和 `wl_match_type`（支持 CIDR 和 IP 范围匹配）

#### 角色管理修复

- **角色名称修改不生效**：`RoleUpdate` schema 添加 `name` 字段，`update_role` 支持自定义角色重命名，保护 5 个内置角色不可重命名，检查名称唯一性

#### 数据源管理增强

- **Operation Source 子菜单**：在数据源管理页面新增 Operation Source 标签页，独立管理 Sangfor 防火墙数据源，位于 Data Sources 和 Bindings 之间
- **Sangfor 测试连接 Last Test 不更新**：测试连接成功后使用直接 UPDATE 语句更新 `last_sync_at`（绕过 ORM expunge 问题）

#### 备份管理增强

- **FTP 远程备份**：备份列表/下载/删除支持远程存储（FTP/SFTP），备份列表显示存储位置标签
- **备份计划预设国际化**：预设选项改用 i18n 翻译键

#### 前端修复

- **导航栏菜单同时选中**：父级菜单高亮基于路由匹配（`isGroupActive`）而非展开状态
- **通知时间戳时区不一致**：所有通知渠道统一使用 `format_timestamp()` 转换为 Asia/Shanghai 时区
- **前端时间戳格式不一致**：统一 `formatDate` 为 `formatDateTime`，支持多语言和时区
- **翻译键命名错误**：白名单 `identifier` 重命名为 `macAddress`/`ipAddress`

#### 数据库迁移

- `025_terminal_updated_at.py`：终端表添加 `updated_at` 列
- `026_blacklist_fix_unblocked_at.py`：修复历史 `auto_unblocked=True` 但 `unblocked_at IS NULL` 的记录

#### 文档更新

- 更新 `changelog.md` 添加 v3.6.6 变更记录
- 更新 `database.md` 补充 terminals/`updated_at` 和 blacklist/`unblocked_at`/`unblocked_by` 字段
- 更新 `api.md` 添加 `/blacklist/stats` 接口说明
- 更新 `user-guide.md` 添加 Operation Source 功能说明
- 统一所有文档版本号至 v3.6.6

---

## [v3.6.5] - 2026-07-07

### 评估报告修复补充 - 事件触发点完善/黑名单软删除/文档更新

#### 事件触发点完善

- **安全事件**：在 `auth.py` 中添加 `PASSWORD_CHANGED`、`USER_CREATED`、`USER_DELETED`、`USER_UPDATED` 事件触发点
- **合规告警**：在 `compliance_service.py` 中添加 `BLOCK_THRESHOLD_EXCEEDED`、`POLICY_VIOLATION`、`TERMINAL_COMPLIANT`、`TERMINAL_NON_COMPLIANT` 事件触发点
- **管理事件**：在 `roles.py`、`settings.py`、`data_source_service.py`、`arp_collector_service.py` 中添加角色变更、配置变更、数据源变更、终端事件触发点
- **事件发射器**：在 `event_emitter.py` 中新增多个事件触发函数，事件覆盖率提升至85%

#### 黑名单软删除

- 在 `blacklist.py` 模型中添加 `unblocked_at` 和 `unblocked_by` 字段
- 在 `terminal_service.py` 中将删除操作改为软删除（标记而非删除）
- 更新查询逻辑，默认只返回活跃（未解封）记录
- 创建数据库迁移脚本 `024_blacklist_soft_delete.py`

#### Bug修复

- 修复 `cleanup_expired_blacklist` 函数中 datetime 变量作用域问题
- 修复 `emit_terminal_non_compliant` 调用时传入错误参数的问题
- 更新测试用例以适应软删除行为

#### 文档更新

- 创建 `business-workflow.md`，详细说明合规判定和封锁/解封流程
- 更新 `api.md`，补充通知统计、日志、重试、归档和备份FTP配置等API端点说明
- 更新 `logging-guide.md`，新增日志监控与告警、紧急处理流程等章节
- 统一所有文档版本号至 v3.6.5

#### 测试验证

- 后端测试：131+ 测试通过（2个原有mock问题测试失败可忽略）
- 服务健康检查：全部通过
- 业务链条测试：用户认证、用户管理、黑名单管理等核心功能正常

---

## [v3.6.3] - 2026-07-07

### 备份管理增强 + Bug 修复 + 版本统一管理

#### FTP备份支持

- 新增 FTP 存储类型，支持普通 FTP 和 FTPS（SSL）两种模式
- 后端 `backup_service.py` 新增 `_upload_via_ftp()` 方法，使用 ftplib 实现安全传输
- 前端 `Backup.tsx` 添加 FTP 配置选项（主机、端口、用户名、密码、远程路径、SSL 开关）
- API `/backup/test` 端点支持 FTP 连接测试

#### 备份配置持久化

- 创建 `BackupConfigModel` 数据库模型（`backup_config` 表），实现配置持久化
- 包含字段：enabled、schedule、retention_days、storage_type、storage_config、backup_database、backup_config、backup_logs、encrypt_backup
- 后端 `backup_service.py` 新增 `load_config()` 和 `save_config()` 方法
- API `GET/PUT /backup/config` 使用数据库存储，刷新页面后配置保留

#### 定时任务预设选择器

- 前端 `Backup.tsx` 添加 SCHEDULE_PRESETS 预设选择器（每天凌晨2点、每天凌晨3点、每周日凌晨2点、自定义）
- 只有选择"自定义"时才显示 crontab 输入栏
- 添加 CRON 格式正则校验，失去焦点时触发校验并显示错误提示
- 新增国际化翻译键（`cronRequired`、`cronInvalid`）

#### 登录页页脚样式优化

- 页脚区域移出 `max-w-md` 容器限制，内容横向自适应扩展
- 使用 `flex-col` 确保页脚在登录框下方而非并排
- 移除 `overflow-hidden` 和 `text-ellipsis`，取消长度限制
- 保留 `whitespace-nowrap` 确保一行显示不换行

#### FTP连接测试Bug修复

- 修复 `ftplib.FTP.__init__()` 不支持 `port` 参数的问题
- 改为先创建实例再调用 `connect(host, port)` 方法
- 修复范围：`backup_service.py` 和 `backup.py` API 端点

#### 版本号统一管理

- 创建 `VERSION` 文件作为单一版本源（`3.6.3`）
- `manage.sh`：从 VERSION 文件读取版本号并注入环境变量
- `config.py`：添加 `_load_version()` 函数动态读取
- `vite.config.ts`：添加 `getVersion()` 函数注入 `VITE_APP_VERSION`
- `.env` 和 `.env.example`：更新版本号为 3.6.3

### 数据库迁移

- **023_backup_config_table**：创建 backup_config 表

### 变更文件

**后端（3 个修改 + 2 个新增）：**

- `backend/app/services/backup_service.py` — FTP上传方法、配置持久化
- `backend/app/api/v1/endpoints/backup.py` — 配置持久化、FTP测试
- `backend/app/core/config.py` — 版本号动态读取
- `backend/app/models/backup_config.py` — BackupConfigModel（新增）
- `backend/alembic/versions/023_backup_config_table.py` — 数据库迁移（新增）

**前端（2 个修改 + 1 个配置）：**

- `frontend/src/pages/Backup.tsx` — FTP配置、预设选择器、CRON校验
- `frontend/src/pages/Login.tsx` — 页脚布局优化
- `frontend/vite.config.ts` — 版本号注入
- `frontend/src/config/branding.ts` — 使用环境变量版本

**基础设施（2 个修改 + 1 个新增）：**

- `manage.sh` — 版本号读取和环境变量注入
- `.env` / `.env.example` — 版本号更新
- `VERSION` — 统一版本源文件（新增）

**文档（2 个修改）：**

- `docs/release-notes.md` — 本文档
- `docs/changelog.md` — 追加 [3.6.3] 条目

### 提交记录

```
feat(backup): add FTP backup support with SSL option
feat(backup): implement backup config persistence with database
feat(backup): add schedule preset selector with CRON validation
fix(backup): fix FTP connection test port parameter error
fix(login): optimize footer layout to allow full width display
chore(version): unify version management with VERSION file
docs(release): add v3.6.3 release notes
docs(changelog): add v3.6.3 changelog
```

### 测试验证

- ✅ FTP配置测试验证通过
- ✅ 备份配置持久化验证通过（刷新后配置保留）
- ✅ 定时任务预设选择器验证通过（自定义时显示输入栏）
- ✅ CRON格式校验验证通过（无效格式显示错误）
- ✅ 登录页页脚布局验证通过（在登录框下方，内容完整显示）
- ✅ 版本号统一管理验证通过（所有位置显示3.6.3）
- ✅ 数据库迁移 023 执行成功
- ✅ Docker Compose 构建成功

---

## [v3.6.2] - 2026-07-06

### 通知管理增强版本：日志归档、通配符匹配、优先级控制

#### 通知日志管理功能

- 新增日志归档功能：支持单条归档和批量归档（30天前日志）
- 新增日志清理功能：清理90天前的已归档日志（永久删除）
- 新增日志删除功能：支持单条日志删除
- 数据库新增 `archived` 字段，用于标记归档状态
- 前端监控页面添加归档/清理/删除操作按钮和确认对话框

#### 模板和规则通配符匹配

- 支持通配符 `*` 匹配所有事件类型，实现通用模板/规则兜底
- 精确匹配优先于通配符匹配，确保特定事件使用专用模板
- 添加 `priority` 字段控制匹配顺序（数值越小优先级越高）
- 前端模板和规则表单添加通配符选项和优先级输入框

#### 监控统计修复

- 修复监控统计内部服务错误：替换 PostgreSQL 特定函数为标准 SQL 函数
- 优化异常处理，添加详细错误日志
- 前端监控组件添加错误信息展示

#### Channel 开关颜色优化

- 启用状态改为绿色（bg-green-500），更加直观
- 关闭状态改为灰色（bg-gray-300），提升辨识度

#### 提交记录

```
fix(notification): 修复监控统计SQL兼容性和异常处理
feat(notification): 添加通知日志归档和清理功能
feat(notification): 模板和规则支持通配符匹配与优先级
style(notification): 优化Channel开关颜色显示
chore(version): bump version to 3.6.2
docs(changelog): add v3.6.2 changelog
docs(release): add v3.6.2 release notes
```

#### 测试验证

- ✅ 通知服务测试 10/10 通过
- ✅ 日志归档/清理/删除功能验证通过
- ✅ 模板通配符匹配和优先级验证通过
- ✅ 规则通配符匹配和优先级验证通过
- ✅ Channel 开关颜色显示验证通过

---

## [v3.6.1] - 2026-07-06

### 稳定性修复版本：品牌配置同步、密码校验、时区处理

#### 品牌配置同步修复

- 登录页面支持动态加载 `login_heading`、`login_footer_text`、`footer_copyright`、`footer_icp_number`、`footer_icp_url` 字段
- 配置修改后刷新页面即可生效，无需重新构建
- 回退机制：后端不可用时使用 `branding.ts` 静态默认值

#### 密码系统优化

- 密码复杂度规则统一：至少8位，必须包含大写字母、小写字母和数字，允许特殊字符
- 密码重置流程优化：成功提示 → 2秒延迟 → 跳转登录页
- 邮箱重复使用确认：管理员可确认后使用重复邮箱（`force_email` 参数）

#### 时区处理统一

- 后端时间戳统一使用 `app.core.timezone.now()`（Asia/Shanghai）
- 前端日期格式化统一使用 `Intl.DateTimeFormat` 指定 Asia/Shanghai 时区
- 通知日志修复：aware datetime → naive datetime 转换，解决写入 `TIMESTAMP WITHOUT TIME ZONE` 字段失败问题

#### 事件通知增强

- 新增6个安全事件类型，覆盖用户全生命周期操作：
  - `security.user_deleted`：用户删除事件
  - `security.user_updated`：用户更新事件
  - `security.password_changed`：密码修改事件
  - `security.role_changed`：角色变更事件
  - `security.login_locked`：登录锁定事件
  - `security.password_reset_requested`：密码重置请求事件
- 登录锁定事件自动触发通知，提升安全监控能力

#### 会话管理增强

- 新增 `useTokenExpiration` hook：前端主动检测 JWT 令牌过期时间
- 支持令牌自动刷新和超时自动登出
- 会话过期前1分钟显示警告提示

#### 用户体验优化

- 用户管理页面区分显示 Active/Locked/Disabled 三种状态（Locked 状态从 Redis 获取）
- 忘记密码链接仅在密码输入错误次数触发安全校验后显示
- 密码重置时自动传递用户名到重置页面，无需用户重复输入

#### API 数据源测试认证修复

- 修复 ARP API 类型数据源测试连接时未处理自定义 Header 认证的问题
- 支持 bearer 和 header 两种认证方式

#### 提交记录

```
fix(branding): sync login page branding config from backend
feat(event): add security event emitters for user operations
feat(auth): add token expiration detection and email availability check
i18n: add missing auth translation keys
refactor(notification): optimize service and channel implementations
chore(service): minor service optimizations
docs(changelog): update changelog for v3.6.1
docs(branding): update branding guide to v3.6.1
docs(release): add v3.6.1 release notes
```

#### 测试验证

- ✅ 品牌配置动态加载验证通过
- ✅ 密码重置流程端到端验证通过
- ✅ 通知日志时区错误修复验证通过
- ✅ 事件发射器集成测试通过
- ✅ 后端单元测试 131 个通过（2 个失败为 v3.6.0 已存在的测试代码问题）

---

## [v3.6.0] - 2026-07-03

### 功能增强版本：消息模板、通知规则、异步队列与监控

#### 消息模板系统（P1）

- **Jinja2 模板引擎**：集成 Jinja2 模板渲染引擎，支持每个事件-渠道组合配置独立的消息模板
- **模板 CRUD**：支持模板创建、编辑、删除、列表、筛选（按事件类型/渠道类型）
- **模板预览**：提供模板预览端点，管理员可在保存前查看渲染效果
- **Jinja2 变量参考**：前端侧栏展示可用变量列表（event_type、event_name、severity、timestamp、data 等）
- **默认模板标记**：支持 is_default 标记，未配置自定义模板时使用系统默认渲染

#### 国内 IM 应用模式（P1）

- **飞书应用模式**：支持飞书自建应用模式，通过 tenant_access_token 发送消息，token 缓存 Redis（7000s TTL）
- **钉钉应用模式**：支持钉钉企业内部应用模式，通过 access_token 发送消息，token 缓存 Redis
- **企业微信应用模式**：支持企业微信应用模式，通过 access_token 发送消息，token 缓存 Redis
- **双模式切换**：每个渠道可在 Webhook 模式和应用模式之间切换，配置字段动态调整
- **邮件配置页面**：独立的 SMTP 邮件系统配置页面，支持配置测试与加密存储

#### 通知规则系统（P2）

- **消息抑制（Suppression）**：同一事件在抑制窗口内仅发送一次，后续事件被静默，使用 Redis TTL key 实现
- **消息聚合（Aggregation）**：窗口内事件计数，用于统计和升级判定
- **消息升级（Escalation）**：达到阈值后自动提升 severity（如 warning → critical），确保重要告警被关注
- **升级绕过抑制**：escalated 事件自动设置 bypass_suppression 标志，确保升级后的消息总能送达
- **PostgreSQL 部分唯一索引**：使用 `uq_rule_event_null_channel` 和 `uq_rule_event_specific_channel` 解决 NULL channel_name 唯一性约束

#### 异步队列与重试机制（P3）

- **Redis List 异步队列**：`notify:queue:main` 作为主队列，事件发布采用 fire-and-forget 模式，不阻塞请求
- **Redis ZSet 重试队列**：`notify:queue:retry` 管理待重试任务，按 next_retry_at 时间排序
- **指数退避重试**：默认最大 3 次重试，首重试延迟 10s，后续指数增长（10s → 20s → 40s）
- **通知日志增强**：notification_logs 表新增 retry_count、next_retry_at、completed_at 字段
- **手动重试 API**：支持单条失败通知重发（`/logs/{id}/retry`）和批量重发（`/logs/retry-all`）
- **双 Worker 架构**：main_worker 处理主队列，retry_worker 扫描到期重试任务

#### 监控统计面板（P3）

- **8 个核心统计卡片**：总发送量、成功数、失败数、成功率、待重试、平均延迟、渠道数、规则数
- **各渠道成功率**：按渠道维度展示成功率进度条
- **30 秒自动刷新**：监控页面默认每 30 秒自动刷新统计数据
- **统计聚合**：基于 PostgreSQL `func.cast` 条件聚合，一次查询返回全部统计指标

#### 权限一致性修复

- **通知模块**：9 处 `notification:manage` → `notification:write`，与数据库权限定义一致
- **备份模块**：6 处 `system.manage` → `backup:write`，修正点号格式并细化到备份模块
- **认证提供者模块**：4 处 `auth.manage` → `settings:write`，使用系统已有权限码

#### 基础设施优化

- **Nginx 缓存头修复**：移除 `expires -1`，消除与 `add_header Cache-Control` 的重复冲突，确保 index.html 正确禁用缓存
- **前端邮件入口**：新增侧边栏邮件设置导航项，完善图标映射与国际化

### 数据库迁移

- **017_notification_templates**：创建 notification_templates 表（id、name、event_type、channel_type、subject_template、body_template、is_default、created_by、created_at、updated_at）
- **018_notification_rules**：创建 notification_rules 表（id、name、event_type、channel_name、enabled、suppress_window、aggregate_window、escalate_threshold、escalate_severity、created_by、created_at、updated_at），含 2 个部分唯一索引
- **019_notification_async_retry**：notification_logs 表新增 retry_count（int, default 0）、next_retry_at（timestamp, nullable）、completed_at（timestamp, nullable）字段

### 变更文件

**后端（18 个修改 + 3 个新增）：**

- `backend/app/core/config.py` — VERSION 升级至 3.6.0
- `backend/app/main.py` — lifespan 中启动/停止通知 worker
- `backend/app/models/notification.py` — NotificationTemplate、NotificationRule、NotificationLog 新字段
- `backend/app/schemas/notification.py` — Templates/Rules/Stats/Preview 的 Pydantic schemas
- `backend/app/schemas/system_config.py` — EmailConfigResponse schema
- `backend/app/api/v1/endpoints/notifications.py` — 新增 templates/rules/stats/retry 端点，权限码修正
- `backend/app/api/v1/endpoints/settings.py` — 邮件配置 API 端点
- `backend/app/api/v1/endpoints/auth_providers.py` — 权限码修正（auth.manage → settings:write）
- `backend/app/api/v1/endpoints/backup.py` — 权限码修正（system.manage → backup:write）
- `backend/app/api/v1/endpoints/auth.py` — /auth/me 返回 provider 字段
- `backend/app/services/notification_service.py` — Jinja2 模板、Redis 队列、重试、统计聚合
- `backend/app/services/config_service.py` — 邮件默认配置 seed
- `backend/app/services/email_service.py` — 邮件发送增强
- `backend/app/services/event_emitter.py` — 事件发射器对接通知服务
- `backend/app/services/compliance_service.py` — 合规事件触发通知
- `backend/app/services/notification_channels/feishu_channel.py` — 应用模式 + Redis token 缓存
- `backend/app/services/notification_channels/dingtalk_channel.py` — 应用模式 + Redis token 缓存
- `backend/app/services/notification_channels/wecom_channel.py` — 应用模式 + Redis token 缓存
- `backend/app/services/notification_channels/email_channel.py` — 模板渲染集成
- `backend/alembic/versions/017_notification_templates.py` — 新迁移（新增）
- `backend/alembic/versions/018_notification_rules.py` — 新迁移（新增）
- `backend/alembic/versions/019_notification_async_retry.py` — 新迁移（新增）

**前端（9 个修改 + 4 个新增）：**

- `frontend/src/App.tsx` — /email-settings 路由
- `frontend/src/lib/constants.ts` — 新增 email 侧栏入口、P2/P3 API 端点常量
- `frontend/src/components/Sidebar.tsx` — Mail 图标 + nav.email 标签映射
- `frontend/src/pages/Notifications.tsx` — 新增 templates/rules/monitor 三个 Tab
- `frontend/src/pages/SystemSettings.tsx` — 增加邮件设置卡片入口
- `frontend/src/hooks/useTerminalData.ts` — AllConfigs 增加 EmailConfig 接口
- `frontend/src/components/notifications/shared.ts` — 飞书/钉钉/企微 webhook+app 模式切换字段
- `frontend/src/i18n/locales/zh.ts` — 4 个命名空间翻译
- `frontend/src/i18n/locales/en.ts` — 4 个命名空间翻译
- `frontend/src/pages/EmailSettings.tsx` — SMTP 邮件配置页面（新增）
- `frontend/src/components/notifications/NotificationTemplates.tsx` — 模板 CRUD + 预览（新增）
- `frontend/src/components/notifications/NotificationRules.tsx` — 规则 CRUD + 帮助侧栏（新增）
- `frontend/src/components/notifications/NotificationMonitor.tsx` — 监控统计面板（新增）

**基础设施（2 个修改）：**

- `nginx/etc/conf.d/tam.conf` — 移除 `expires -1`
- `nginx/etc/conf.d/tam.dev.conf` — 移除 `expires -1`

**文档（待更新）：**

- `docs/changelog.md` — 已更新 [3.6.0] 条目
- `docs/release-notes.md` — 本文档

### 验证结果

- ✅ Docker Compose 构建成功（backend + frontend + nginx）
- ✅ Alembic 迁移 017 → 018 → 019 顺序执行成功
- ✅ 通知模板 CRUD 全流程通过
- ✅ 通知规则 CRUD 全流程通过
- ✅ 抑制行为验证通过（3 次事件仅 2 条日志）
- ✅ 升级行为验证通过（threshold=3 后 severity 升级到 critical）
- ✅ 升级绕过抑制验证通过
- ✅ 删除规则后抑制不再生效验证通过
- ✅ 监控统计 API 正常返回（200）
- ✅ 飞书/钉钉/企微应用模式 token 缓存正常
- ✅ 权限码一致性验证通过（operator 角色可访问通知管理）
- ✅ Nginx Cache-Control 头验证通过（单条，无重复）

---

## [v3.5.1] - 2026-07-03

### 热修复版本：用户体验优化与问题修复

#### LDAP用户体验优化

- **Profile页面信息精简**：LDAP用户的个人信息页面仅显示从LDAP同步的信息（用户名、邮箱、角色、状态），完全隐藏邮箱更新和密码修改功能，避免用户困惑
- **邮箱显示位置调整**：将邮箱信息移至账户信息卡片中，与用户名、角色、状态统一展示，信息结构更清晰

#### 模态框交互优化

- **Modal点击外部不关闭**：Import LDAP Users等重要操作模态框，点击灰色遮罩层不再关闭，防止误操作导致数据丢失
- **关闭方式**：仅通过右上角关闭按钮或ESC键关闭模态框

#### LDAP认证编辑体验优化

- **Bind Password可选**：编辑LDAP认证提供者时，Bind Password字段变为可选项，留空则保持原有密码
- **提示信息**：编辑时显示"留空以保持当前密码"提示，用户明确知晓行为
- **后端兼容**：更新API支持密码字段为空时保留原有密码

#### 认证提供者管理精简

- **移除Local类型选项**：认证提供者管理页面中移除Local类型选项（Local认证为系统内置功能，无需用户手动配置）
- **默认选中LDAP**：新建认证提供者时默认选中LDAP类型，简化操作流程

#### 翻译修复

- **Profile页面邮箱标签**：修复LDAP用户Profile页面邮箱标签显示为`profile.email`的翻译键名错误，正确显示为"Email Address"

### 变更文件

- `frontend/src/pages/Profile.tsx` — LDAP用户信息展示优化
- `frontend/src/pages/AuthProviders.tsx` — 移除Local类型、Bind Password可选
- `frontend/src/components/Modal.tsx` — 点击外部不关闭
- `frontend/src/i18n/locales/en.ts` — 新增leaveBlankToKeep翻译
- `frontend/src/i18n/locales/zh.ts` — 新增leaveBlankToKeep翻译
- `backend/app/api/v1/endpoints/auth.py` — /auth/me和/me/profile返回provider字段
- `backend/app/api/v1/endpoints/auth_providers.py` — 更新时保留原有密码
- `docs/changelog.md` — 追加 [3.5.1] 条目

---

## [v3.5.0] - 2026-07-01

### 功能增强 + 安全修复 + 性能优化

#### 事件通知服务

- 事件总线架构：支持多渠道事件发布订阅
- 通知渠道类型：邮件（SMTP）、钉钉（Webhook）、企业微信（Webhook）、通用 Webhook
- 通知日志：完整记录每条通知发送状态、重试次数、错误信息
- 测试连接：支持通知渠道连通性测试
- 事件类型：登录、终端封堵、终端解封、合规变更、配置变更、备份完成等

#### 认证提供者系统

- 插件化认证架构：接口抽象 + 具体实现模式
- 本地认证：用户名密码验证（已有）
- LDAP认证：支持 Active Directory 和 OpenLDAP，用户名验证和 DN 注入防护
- OAuth认证：预留接口，支持后续扩展
- 认证提供者管理：CRUD API + 前端配置页面

#### SFTP备份服务

- 数据库备份：pg_dump 全量备份
- 配置文件备份：docker-compose.yml、manage.sh（排除 .env 敏感文件）
- SFTP远程上传：paramiko 安全传输，主机密钥验证
- 备份轮转：按保留天数自动清理旧备份
- 校验和验证：SHA256 完整性校验

#### 系统设置前端页面

- 统一导航入口："系统设置"分组
- 通用设置：系统名称、Logo、页脚等品牌配置
- 认证提供者：LDAP/本地认证配置管理
- 备份配置：存储类型、保留策略、SFTP参数配置
- 通知管理：通知渠道配置、测试、日志查看
- 用户管理：用户 CRUD、角色分配
- 角色管理：角色 CRUD、权限配置

#### 安全修复

- **路径遍历漏洞**：backup.py 添加路径检查和文件名净化
- **LDAP DN注入**：ldap_provider.py 添加用户名验证和特殊字符转义
- **2FA验证码暴力破解防护**：email_service.py 添加最大尝试次数限制（5次）
- **敏感信息备份泄露**：backup_service.py 排除 .env 文件备份
- **FTP支持移除**：强制使用 SFTP 安全传输
- **SFTP主机密钥验证**：添加主机密钥验证策略

#### 性能优化

- **N+1查询优化**：roles.py 使用 JOIN 批量获取权限和用户计数
- **异步性能优化**：backup_service.py 使用 asyncio.to_thread 包装同步操作
- **通知模块权限控制**：notifications.py 添加 permission 依赖

#### 前端优化

- **导航重构**：嵌套导航结构，系统设置分组
- **国际化完善**：补全备份、认证、通知模块中/英/日翻译
- **Nginx限流调整**：API限流 60→300 r/m，认证限流 10→30 r/m

### 变更文件

- `manage.sh` — VERSION 3.4.0 → 3.5.0
- `backend/app/core/config.py` — VERSION 3.4.0 → 3.5.0
- `frontend/package.json` — version 3.4.0 → 3.5.0
- `.env.example` — VERSION 3.4.0 → 3.5.0
- `backend/app/services/notification_service.py` — 新增通知服务
- `backend/app/services/auth_providers/ldap_provider.py` — LDAP认证实现
- `backend/app/services/auth_providers/base.py` — 认证提供者接口
- `backend/app/services/backup_service.py` — SFTP备份服务
- `backend/app/api/v1/endpoints/notifications.py` — 通知模块API
- `backend/app/api/v1/endpoints/auth_providers.py` — 认证提供者API
- `backend/app/api/v1/endpoints/backup.py` — 备份服务API
- `frontend/src/pages/Settings.tsx` — 系统设置页面
- `frontend/src/pages/AuthProviders.tsx` — 认证提供者页面
- `frontend/src/pages/Backup.tsx` — 备份配置页面
- `frontend/src/pages/Notifications.tsx` — 通知管理页面
- `nginx/etc/conf.d/tam.conf` — 限流配置调整
- `docs/changelog.md` — 追加 [3.5.0] 条目
- `docs/release-notes.md` — 追加 [v3.5.0] 条目

---

## [v3.4.0] - 2026-06-22

### 功能增强 + Bug 修复

#### 系统版本与环境展示
- 前端页脚显示系统版本号（从 /health API 获取）
- Dashboard System Status 页面显示版本号和部署模式
- 新增 `/health` API 返回版本和环境信息
- Nginx 配置添加 /health 路径代理

#### 角色权限国际化
- 5 个内置角色名称和描述三语言翻译（中文/英文/日语）
- 29 个权限码名称和描述三语言翻译
- 修复 roles.permissions 键命名冲突（表头 vs 权限对象）
- i18n 配置禁用 nsSeparator 支持权限代码中的冒号

#### 多环境配置分离
- docker-compose.yml 支持双层 env_file（.env + .env.{ENVIRONMENT}）
- 开发环境配置模板 .env.dev
- 生产环境配置模板 .env.prod
- Nginx 镜像版本锁定为 1.27-alpine

#### Bug 修复
- 白名单删除 404 错误：修复删除端点路由匹配问题
- 白名单删除 MAC 匹配错误：使用 mac_address_normalized 字段查询
- 超管角色初始化错误：修复 admin 用户未正确关联 superadmin 角色

### 变更文件

- `manage.sh` — VERSION 3.3.1 → 3.4.0
- `frontend/package.json` — version 3.3.1 → 3.4.0
- `backend/app/core/config.py` — VERSION 3.3.1 → 3.4.0
- `.env.example` — VERSION 3.3.1 → 3.4.0
- `.env.dev` — 新增开发环境配置模板
- `.env.prod` — 新增生产环境配置模板
- `frontend/Dockerfile.dev` — 新增开发环境 Dockerfile
- `docker-compose.yml` — 添加双层 env_file 配置、锁定 nginx 版本
- `nginx/etc/conf.d/tam.conf` — 添加 /health 路径代理
- `frontend/src/store/branding.ts` — 添加系统版本和环境状态
- `frontend/src/pages/Dashboard.tsx` — System Status 页面显示版本信息
- `frontend/src/components/Layout.tsx` — 页脚显示版本号
- `frontend/src/i18n/index.ts` — 添加 nsSeparator: false
- `frontend/src/i18n/locales/en.ts` — 角色权限翻译
- `frontend/src/i18n/locales/zh.ts` — 角色权限翻译
- `frontend/src/i18n/locales/ja.ts` — 角色权限翻译
- `frontend/src/pages/Roles.tsx` — 权限列标题翻译键修正
- `backend/cli.py` — 修复 admin 用户角色关联
- `backend/app/services/terminal_service.py` — 修复白名单删除逻辑
- `backend/app/api/v1/endpoints/whitelist.py` — 修复删除端点
- `docs/changelog.md` — 追加 [3.4.0] 条目
- `docs/release-notes.md` — 追加 [v3.4.0] 条目
- `docs/release-plan.md` — 更新为 v3.4.0 内容

---

## [v3.3.1] - 2026-06-17

### Bug 修复

- **黑名单显示已解封记录**：黑名单管理页面默认查询不再返回 `auto_unblocked=True` 的历史记录，仅展示当前仍被封堵的活跃记录。新增 `status` 查询参数和前端 Tab 切换支持查看已解封历史记录。

### 变更文件

- `backend/app/services/terminal_service.py` — get_blacklist/get_blacklist_count 添加 auto_unblocked 过滤
- `backend/app/schemas/terminal.py` — BlacklistQuery 添加 status 字段
- `backend/app/api/v1/endpoints/blacklist.py` — get_blacklist endpoint 添加 status 参数
- `frontend/src/hooks/useTerminalData.ts` — BlacklistSearchParams 添加 status 字段
- `frontend/src/pages/Blacklist.tsx` — 添加 Tab 切换、已解封记录样式区分、隐藏解封按钮
- `frontend/src/i18n/locales/zh.ts` — 添加中文翻译键
- `frontend/src/i18n/locales/en.ts` — 添加英文翻译键
- `frontend/src/i18n/locales/ja.ts` — 添加日文翻译键
- `manage.sh` — VERSION 3.3.0 → 3.3.1
- `backend/app/core/config.py` — VERSION 3.3.0 → 3.3.1
- `frontend/package.json` — version 3.3.0 → 3.3.1
- `.env.example` — VERSION 3.3.0 → 3.3.1
- `docs/changelog.md` — 追加 [3.3.1] 条目
- `docs/release-notes.md` — 追加 [v3.3.1] 条目

---

## [v3.3.0] - 2026-06-17

### RBAC 权限控制 + 审计日志优化 + 生产就绪改进

#### RBAC 权限控制
- 4 张核心表（roles/permissions/user_roles/role_permissions），5 个预设角色（superadmin/admin/operator/auditor/viewer），29 个权限码覆盖 10 个功能模块
- `require_permission` 权限检查工厂函数：FastAPI 依赖注入 + Redis 缓存（TTL 300s）+ superuser 短路
- 角色 CRUD API：7 个端点（列表/详情/创建/编辑/删除/权限列表/角色用户列表）
- 前端 `usePermission` Hook + `ProtectedRoute` 路由守卫 + 侧边栏导航过滤
- 角色管理页面：角色列表、创建/编辑弹窗、权限按模块分组、删除确认
- 超管隔离机制：非超管不可见/不可管理超管用户
- 初始管理员 4 层保护：不可删除/降级/停用/角色变更

#### 审计日志优化
- Action 命名统一为 verb_resource 格式（block_terminal, auto_block_terminal, change_role 等）
- 新增 resource_name 列，存储人类可读资源名称
- 审计日志搜索支持 keyset 分页（cursor 参数）
- CSV 导出新增 Resource Name 列
- 前端 AuditLogs.tsx 新增 action 分类体系和 resource_name 优先展示

#### 生产就绪改进
- Docker 安全加固：docker-compose.prod.yml（no-new-privileges, cap_drop:ALL, read_only）
- Docker 健康检查：所有服务添加 healthcheck 配置
- Sangfor API 指数退避重试：最多 3 次重试，指数等待
- N+1 查询优化：cleanup_expired_blacklist 和 batch_check_compliance 批量预加载
- 核心服务单元测试：22 个 compliance_service 测试用例

#### 部署模式统一
- deploy --dev 替代 --demo，自动设置 ENVIRONMENT 变量
- docker-compose 三层架构：base + dev/prod override
- Nginx 环境差异化：开发 HTTP+宽松限流 vs 生产 HTTPS+标准限速
- 生产环境禁止 mock generate

#### Mock 数据业务对齐
- 28 种 verb_resource action 覆盖所有业务场景
- JSON 格式 details 替代纯文本
- resource_name 字段完整设置
- firewall_tag 与 DataSourceBinding 绑定关系一致
- 自动封堵 blocked_by="system"

#### 终端封堵与合规改进
- 终端封堵绑定验证：封堵终端前强制检查绑定关系，无绑定时显示防火墙选择器和无绑定错误提示
- 数据源标签页绑定状态列：数据源列表新增绑定状态列，已禁用 ARP 数据源显示"合规状态已冻结"
- 绑定关系下拉框包含已禁用数据源，以 `[已禁用]` 后缀标识
- ARP 数据源禁用触发合规重置：禁用 ARP 数据源时自动重置关联终端 compliance_status 为 unknown
- 两阶段删除机制：数据源、绑定关系、合规基准删除前提供影响预览 API
- 安全删除：自动解封终端、清理黑名单记录、清理 Redis 缓存、触发合规重算
- Sangfor 数据源移除"同步"按钮：Sangfor 为推送型防火墙，无数据同步语义

#### 合规生命周期修复
- 黑名单 mac_address_normalized 字段补全
- 多防火墙解封原子性
- 过期清理安全性增强
- 手动解封触发合规重算
- 统一解封行为对齐

#### 用户手册
- 新增用户使用手册（docs/user-guide.md）：12 章完整操作指引
- 新增快速上手指南（docs/quick-start-guide.md）：8 步核心操作流程
- 新增发布方案文档（docs/release-plan.md）
- 修正用户使用手册与实际系统功能不一致的描述：仪表板快捷操作、终端封堵不支持批量选择、终端详情字段、黑名单详情字段、合规基准页面为标签页、系统设置无前端管理界面（仅 API）、Logo 不支持动态上传、密码策略为硬编码、移除不存在的 SSO 和并发会话控制
- 修正快速上手指南终端封堵操作描述（不支持批量勾选）

### 提交记录

| 提交 | 说明 |
|------|------|
| af1960c | feat(rbac): add RBAC data models, migration and role management API |
| 48735ac | feat(rbac): implement permission control across all endpoints and frontend |
| 82ec0e0 | docs(rbac): update role and access control documentation to v2.0 |
| 707eefb | fix(search): fix search returning empty results on whitelist/blacklist/audit-logs |
| 3c5b758 | fix(perf): resolve API blocking and improve rate limit config |
| 7b4a0dc | fix(rbac): enforce superadmin protection and single-role-per-user model |
| d7a5838 | fix(frontend): improve UX and fix CSP/307 redirect issue |
| 06dbe11 | fix(i18n): complete i18n coverage for zh/en/ja locales |
| 253acb6 | test: add RBAC tests and fix security test assertions |
| 9100a8d | fix(search): increase debounce delay from 300ms to 500ms across all pages |
| 2f2add5 | fix: prevent superadmin role modification and fix Users search flickering |
| 0b36d78 | docs: update RBAC documentation to v3.0 with current implementation |
| da420a4 | fix(audit): unify action naming, add resource_name for meaningful display |
| c65466b | chore: remove sangfor_api docs and todos.md from git tracking |
| 3ed025c | feat(production-readiness): P0-P3 improvements for production deployment |
| 7722146 | refactor(deploy): unify deployment modes to dev/prod, fix mock data business alignment |
| 42b3f06 | docs: comprehensive documentation update to v3.2.0-r12 |
| 9f00100 | docs: rewrite README.md as concise project onboarding guide |

### 文件变更
- 93 个文件，+16288/-2027 行（相比 v3.2.0）

---

## [v3.2.0-r11] - 2026-06-16

### 综合审计修复

#### 核心业务逻辑修复
- 黑名单 `mac_address_normalized` 字段补全：封堵/解封操作同步写入标准化 MAC 列，确保 MAC 维度查询一致性
- 多防火墙解封原子性：`unblock_ip` 改为按 `firewall_tag` 逐个解封并独立处理异常，单个防火墙解封失败不影响其他防火墙
- 过期清理安全性：`cleanup_expired_blacklist` 增加 `mac_address` 维度匹配，避免同 IP 多终端误解封；Sangfor 解封失败时保留 Blacklist 记录并延长重试

#### 合规生命周期修复
- 手动解封触发合规重算：`unblock_ip` 解封后自动调用 `recalculate_all_compliance`，确保合规状态及时更新
- 统一解封行为：手动解封与自动解封行为对齐，均更新 Terminal 状态、清理 Blacklist 记录、重置合规状态

#### 文档一致性修复
- 32 项文档一致性修复：所有文档版本号统一至 v3.2.0-r11，修正版本号对齐、术语一致性、文档清单补全（logging-guide.md、git-workflow-guide.md）

---

## [v3.2.0-r10] - 2026-06-16

#### 新增
- 终端封堵绑定验证：终端封堵前强制检查绑定关系，无绑定时显示防火墙选择器和无绑定错误提示
- 数据源标签页绑定状态列：数据源列表新增绑定状态列，已禁用 ARP 数据源显示"合规状态已冻结"
- 启用无绑定数据源确认对话框：启用未绑定防火墙的 ARP 数据源时弹出确认提示

#### 改进
- 绑定关系下拉框包含已禁用数据源：ARP 和防火墙数据源下拉框现在包含已禁用的数据源，以 `[已禁用]` 后缀标识
- ARP 数据源禁用触发合规重置：禁用 ARP 数据源时自动重置关联终端 `compliance_status` 为 `unknown`

#### 提交记录

| 提交 | 说明 |
|------|------|
| be0a24d | feat: 终端封堵绑定验证+绑定状态列+禁用数据源合规重置 |

#### 文件变更
- `frontend/src/pages/Terminals.tsx` — 封堵前绑定检查，显示防火墙选择器和无绑定错误
- `frontend/src/components/datasources/BindingsTab.tsx` — ARP 和防火墙下拉框包含已禁用数据源（`[已禁用]` 后缀）
- `frontend/src/components/datasources/DataSourcesTab.tsx` — 新增绑定状态列，禁用 ARP 源显示"合规状态已冻结"，启用无绑定确认对话框
- `backend/app/api/v1/endpoints/data_sources.py` — ARP 数据源禁用时触发合规状态重置
- `backend/app/services/terminal_service.py` — 合规状态批量重置方法
- `frontend/src/i18n/locales/zh.ts` — 新增绑定状态、合规冻结、无绑定封堵提示翻译键
- `frontend/src/i18n/locales/en.ts` — 新增绑定状态、合规冻结、无绑定封堵提示翻译键
- `frontend/src/i18n/locales/ja.ts` — 新增绑定状态、合规冻结、无绑定封堵提示翻译键

---

## [v3.2.0-r9] - 2026-06-16

#### 新增
- 两阶段删除机制：数据源、绑定关系、合规基准删除前提供影响预览（delete-preview API）
- 安全删除：自动解封终端、清理黑名单、清理 Redis 缓存、触发合规重算
- 前端 DeletePreviewModal 组件：展示影响范围、操作清单、受影响统计
- 数据源和合规基准 tag 修改禁止（tag 为系统全局标识符）

#### 修复
- compliance_service.py 导入错误（app.models.audit_log → app.models.log）

#### 文件变更
- `backend/app/api/v1/endpoints/data_sources.py` — 新增 delete-preview 端点，修改删除端点
- `backend/app/api/v1/endpoints/compliance_baselines.py` — 新增 delete-preview 端点，修改删除端点，tag 修改禁止
- `backend/app/schemas/data_source.py` — 新增 DeletePreviewAffected、DeletePreviewResponse Schema
- `backend/app/services/data_source_service.py` — 新增 preview/safe delete 方法，tag 修改禁止
- `backend/app/services/compliance_service.py` — 修复导入错误
- `frontend/src/components/DeletePreviewModal.tsx` — 新建删除预览弹窗组件
- `frontend/src/components/datasources/DataSourcesTab.tsx` — 集成两阶段删除
- `frontend/src/components/datasources/BindingsTab.tsx` — 集成两阶段删除
- `frontend/src/components/datasources/ComplianceBaselinesTab.tsx` — 集成两阶段删除
- `frontend/src/i18n/locales/{zh,en,ja}.ts` — 新增 deletePreview 翻译
- `frontend/src/lib/constants.ts` — 新增 API 端点常量

---

## [v3.2.0-r8] - 2026-06-16

### Fixed

- `recalculate_all_compliance` 自动封堵/解封改为多防火墙路由（`_get_bound_firewall_tags`），与 `auto_block_non_compliant` 行为一致
- `recalculate_all_compliance` 自动封堵创建的 Blacklist 记录补全 `expires_at` 和 `blocked_by` 字段，避免永不过期
- `cleanup_expired_blacklist` Sangfor 解封失败时保留 Blacklist 记录（延长 30 分钟重试），避免本地与防火墙状态不一致
- `cleanup_expired_blacklist` Terminal 查询增加 MAC 维度匹配，避免同 IP 多终端误解封
- `cleanup_expired_blacklist` 完成后触发 `recalculate_all_compliance`，确保不合规终端及时重新封堵
- `unblock_ip` 增加 `mac_address` 参数，支持按 MAC 精确解封，避免同 IP 多终端误解封
- `auto_unblock_compliant` Terminal 查询增加 MAC 维度匹配
- `auto_block_non_compliant` / `auto_unblock_compliant` / `recalculate_all_compliance` 补全审计日志
- `block_ip` / `unblock_ip` 审计日志补充 `ip_address`（客户端 IP）字段
- `block_ip` / `unblock_ip` API 端点增加 `Request` 依赖注入，记录操作来源 IP

### Changed

- ComplianceService 新增 `_get_bound_firewall_tags`（多防火墙）、`_get_block_time`、`log_action` 方法

### 文档修复

- database.md：compliance_baselines 表定义从旧 7 字段修正为实际 11 字段，ER 图同步更新
- api.md：第 9 节合规基准端点全面重写（请求/响应体、权限码、业务规则）
- datasource-lifecycle.md：frozen/unfrozen 术语替换为 blocked/unblocked；第 8.4 节 Sangfor API 从旧 blockip 更新为 whiteblacklist API
- architecture.md：Redis 故障策略从 fail-open 修正为混合策略（token 黑名单/验证码 fail-closed，其余 fail-open）
- backend.md：Redis 故障策略同步修正
- RBAC.md：审计日志 action 值 block_ip/unblock_ip 修正为 block_terminal/unblock_terminal；锁定时长从 30 分钟修正为 15 分钟（可配置）

---

## [v3.2.0-r7] - 2026-06-16

### Changed

- Sangfor 数据源移除"同步"按钮：Sangfor 为推送型防火墙，无数据同步语义，前端按 `ds.type !== 'sangfor'` 条件隐藏同步按钮
- Sangfor 同步接口行为调整：`POST /data-sources/{id}/sync` 对 sangfor 类型不再调用 `test_connection`，改为返回"Sync is not applicable"提示信息

### 提交记录

| 提交 | 说明 |
|------|------|
| 8dae3d4 | fix(datasource): remove sync button for Sangfor firewalls |

### 文件变更列表

| 文件 | 变更 |
|------|------|
| frontend/src/components/datasources/DataSourcesTab.tsx | Sangfor 类型隐藏同步按钮 |
| backend/app/api/v1/endpoints/data_sources.py | sangfor 同步接口返回不适用提示 |

---

## [v3.2.0-r6] - 2026-06-16

### Added

- Terminal 模型新增 `firewall_tag` 字段，封堵操作时同步写入防火墙标签，解封时清除
- 数据库迁移脚本 `007_firewall_tag.py`：terminals 表新增 firewall_tag 列
- 终端管理搜索栏支持 `source` 和 `firewall_tag` 过滤（后端 TerminalQuery 新增 source_tag/firewall_tag 参数）
- 封堵/解封操作支持 `comments` 参数，写入 Terminal.comments 字段
- 审计日志分类体系补全：新增 `role`（角色管理）和 `compliance`（合规基线）分类
- 审计日志 action 枚举补全 15 个缺失项（login_failed、token_refresh、change_password、bind/unbind_datasource、role_change、assign_role、create/update/delete_role、create/update/delete_baseline、upload_branding、export_audit_logs）
- 审计日志详情 key 翻译映射（23 个 key：ip→IP地址、mac→MAC地址 等）

### Changed

- 终端管理操作按钮矩阵重构：compliant+unblocked 仅查看，non_compliant+blocked 仅查看，各状态组合操作明确
- 封堵/解封/移出黑名单操作新增确认对话框，支持 comment 填写
- 黑名单管理页面移除手动添加功能，定位为审计视图（封堵操作统一从终端管理发起）
- 审计日志 details 列从图标按钮改为 message 文本预览（点击展开完整 Modal）
- 审计日志统计卡片优化：移除"独立用户数"和"独立操作数"，替换为"安全事件"统计
- 审计日志 IP 列：系统操作（username=system）显示"系统"而非"-"
- 审计日志 resource_id 格式化：数字 ID 类型显示为"类型名 #ID"（如"用户 #3"）
- 白名单 comments 自动同步到终端（bypass 终端 comments 显示 `Whitelist: {comments}`）
- Comments 超长内容支持鼠标悬浮显示完整文本（title 属性）
- Dashboard 系统状态动态检测（Sangfor AF 和 ARP 数据源状态实时查询）

### Fixed

- `token_refresh`、`change_password`、`upload_branding` 操作 IP 地址未记录（`ip_address=None`）
- blocked 终端 `firewall_tag` 为空（封堵操作未写入 Terminal.firewall_tag）
- 封堵/解封操作未更新 Terminal.comments（手动封堵/解封缺少操作记录）
- 白名单 comments 与终端 comments 不一致（bypass 终端未同步白名单备注）

### 提交记录

| 提交 | 说明 |
|------|------|
| (pending) | feat: 终端操作矩阵重构+firewall_tag字段+审计日志优化+黑名单审计视图 (v3.2.0-r6) |

### 文件变更列表

| 文件 | 变更 |
|------|------|
| backend/app/models/terminal.py | 新增 firewall_tag 字段 |
| backend/app/schemas/terminal.py | TerminalQuery 新增 source_tag/firewall_tag；TerminalResponse 新增 firewall_tag |
| backend/app/api/v1/endpoints/terminals.py | block/unblock 新增 comments 参数；搜索新增 source_tag/firewall_tag |
| backend/app/api/v1/endpoints/auth.py | refresh_token/change_password 新增 Request 参数记录 IP |
| backend/app/api/v1/endpoints/settings.py | upload_branding_asset 新增 Request 参数记录 IP |
| backend/app/services/terminal_service.py | search_macs 新增过滤；block/unblock 写入 firewall_tag+comments |
| backend/app/services/compliance_service.py | 封堵/解封写入 firewall_tag；bypass 同步白名单 comments |
| backend/alembic/versions/007_firewall_tag.py | 新增迁移脚本 |
| frontend/src/pages/Terminals.tsx | 操作矩阵重构+确认对话框+搜索过滤+comments tooltip |
| frontend/src/pages/Blacklist.tsx | 移除手动添加功能 |
| frontend/src/pages/AuditLogs.tsx | 分类补全+详情预览+统计优化+key翻译 |
| frontend/src/pages/Dashboard.tsx | 系统状态动态检测 |
| frontend/src/hooks/useTerminalData.ts | TerminalSearchParams 新增字段 |
| frontend/src/i18n/locales/zh.ts | 新增 40+ 翻译键 |
| frontend/src/i18n/locales/en.ts | 新增 40+ 翻译键 |
| frontend/src/i18n/locales/ja.ts | 新增 40+ 翻译键 |

---

## [v3.2.0-r5] - 2026-06-15

### Added

- Sangfor AF API 完全重写：从临时 `blockip` API 迁移到 `whiteblacklist` 永久封堵 API
  - 封堵：`POST /api/v1/namespaces/public/whiteblacklist`（`type=BLACK`，永久生效）
  - 解封：`DELETE /api/v1/namespaces/public/whiteblacklist/{ip}`（按 IP 精确删除）
  - 查询：`GET /api/v1/namespaces/public/whiteblacklist?type=BLACK`
  - TAM 描述前缀机制（`TAM-{tag}-{reason}`）实现幂等操作和安全删除
  - `_sanitize_description` 过滤 AF 禁止的特殊字符
  - `_find_blacklist_entry` 封堵前查询，确保幂等性
  - Token 保活：`GET /api/v1/namespaces/public/keepalive`
  - 独立 `test_connection()` 方法，分步验证认证+API
- 合规基准多数据库类型支持：MSSQL（pyodbc+FreeTDS）、MySQL（aiomysql）、PostgreSQL（asyncpg）
- IPGuard OCULAR3 数据库解析：从 `AGENT.AGT_IP_MAC_STR` 字段提取 IP+MAC 映射
- IPGuard 同步后自动触发合规重算（`recalculate_all_compliance`）
- `scheduled_compliance_check` 发现 non_compliant 终端后自动触发封堵
- 封堵/解封操作更新 Terminal `comments` 字段，记录防火墙标签和操作信息
- `datasource-lifecycle.md` 新增第 16 章「数据源安全性评估」

### Changed

- 所有 Sangfor AF API URL 添加 `/api` 前缀（根因修复：缺少前缀导致 302 重定向）
- `_get_bound_firewall_tag` 改用 `DataSourceBinding` 表查询（修复字段名/值错误）
- `recalculate_all_compliance` 自动解封/封堵通过 `terminal.source_tag` 查找 `DataSourceBinding` 获取防火墙标签
- `batch_check_compliance` 移除 1000 条限制，始终返回 details
- `cleanup_expired_blacklist` 解封后重置 `compliance_status` 为 `unknown`
- ARP 采集更新已有终端时重置 `compliance_status` 为 `unknown`，确保重新评估
- `auto_unblock_compliant` 处理 `firewall_tag=None`：通过 `DataSourceBinding` 回退查询

### Fixed

- Sangfor AF 登录 302 重定向（API URL 缺少 `/api` 前缀）
- `_get_bound_firewall_tag` 使用错误字段名 `source_type`/`sangfor_firewall`（应为 `type`/`sangfor`）
- `recalculate_all_compliance` 读取不存在的 `terminal.firewall_tag` 属性
- `recalculate_all_compliance` 封堵后不创建 Blacklist 记录（导致后续无法自动解封）
- `batch_check_compliance` 超 1000 条时 `details=None` 导致 `AttributeError`
- Sangfor AF description 包含禁止字符（冒号等）导致添加黑名单失败
- UNFROZEN/FROZEN 状态值残留（`arp_collector_service.py`、`terminal_service.py`、`cli.py`、`terminals.py`）

### 提交记录

| 提交 | 说明 |
|------|------|
| TBD | feat(sangfor): rewrite Sangfor AF API with whiteblacklist permanent blocking |
| TBD | feat(compliance): add multi-database support for IPGuard baseline sync |
| TBD | fix(compliance): fix firewall binding lookup and Blacklist record creation |
| TBD | fix(compliance): remove 1000-entry limit in batch_check_compliance |
| TBD | fix(sangfor): sanitize description to remove AF forbidden characters |
| TBD | fix(terminal): replace UNFROZEN/FROZEN with UNBLOCKED/BLOCKED in all files |
| TBD | feat(scheduler): trigger compliance recalculation after IPGuard sync |
| TBD | feat(scheduler): trigger auto-block after scheduled compliance check |
| TBD | fix(cleanup): reset compliance_status to unknown after blacklist expiry |
| TBD | fix(arp): reset compliance_status on existing terminal update |

---

## [v3.2.0-r4] - 2026-06-15

### Added
- API 数据源响应解析扩展：支持 `arp`/`devices`/`records` 包装键和 `ipv4_address` 字段兼容
- API 数据源认证增强：新增 `header` 类型，支持自定义 Header 名+值（如 `X-Auth-Token`）
- 前端数据源配置：Auth Type 新增 "Custom Header" 选项，`header_name` 字段条件显示（`showWhen` 属性）
- 白名单增删后自动触发合规状态批量重算（`recalculate_all_compliance`）
- 合规重算联动封堵/解封：状态变更时自动调用防火墙 API

### Changed
- Terminal STATUS 字段精简：6 值（`active`/`inactive`/`frozen`/`pending`/`unfrozen`/`bypass`）→ 2 值（`blocked`/`unblocked`）
- Dashboard 统计字段精简：移除 `active`/`inactive`/`pending`，新增 `unblocked`
- 白名单添加不再删除终端记录，改为合规状态重算

### Fixed
- 白名单增删后终端合规状态和封堵状态不更新的问题

### Migration
- 数据库 `terminals` 表 `status` 字段：`frozen`→`blocked`，`unfrozen`→`unblocked`，其他遗留值→`unblocked`

### 提交记录

| 提交 | 说明 |
|------|------|
| TBD | feat(datasource): extend API response parsing and add header auth type |
| TBD | fix(compliance): recalculate compliance on whitelist changes |
| TBD | refactor(terminal): simplify status enum to blocked/unblocked |

---

## [v3.2.0-r3] - 2026-06-11

**发布类型**：Bug 修复 + 文案修正 | **合并方式**：Fast-forward

### 变更概要

修复数据源服务层多个 Bug（expunge 导致更新/删除失败、明文密码回写、定时任务未解密配置），SSH 采集从 paramiko 迁移到 netmiko，前端错误处理和合规状态标签修正。

### 变更明细

#### Bug 修复

| 变更项 | 文件 | 说明 |
|--------|------|------|
| SSH 采集库迁移 | `arp_collector_service.py` | paramiko → netmiko，支持自动分页、多设备类型回退（Huawei/H3C/Cisco） |
| update/delete expunge Bug | `data_source_service.py` | `update_data_source`/`delete_data_source` 不再通过 `get_data_source_by_id` 获取对象（expunge 导致 DetachedInstanceError），改为直接查询 |
| decrypt_config 明文回写 | `data_source_service.py` | 解密前先 `db.expunge(source)` 分离对象，防止明文密码在 commit 时回写数据库 |
| update_sync_status expunge Bug | `data_source_service.py` | 改为直接查询 DB，避免 expunge 后 session 不可用 |
| 定时任务未解密配置 | `compliance_service.py` | 3 处添加 `decrypt_config`：IPGuard 同步、防火墙封堵、防火墙解封 |
| ARP 采集 entries=0 状态未更新 | `arp_collector_service.py` | entries 为空时也调用 `update_sync_status(source.id, "success")` |
| 定时采集未解密配置 | `arp_collector_service.py` | `run_scheduled_collection` 添加 `decrypt_config(source.config)` |
| 前端 getErrorMessage 对象渲染 | `utils.ts` | 处理 `detail` 为对象（`{message, error_id}`）的情况，修复 React #31 错误 |

#### 文案修正

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 合规状态标签 | `en.ts`/`zh.ts`/`ja.ts` | `non_compliant`：已封禁/Blocked → 不合规/Non-compliant；`unknown`：待定 → 待判定 |

#### 文档更新

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 相似命令对比 | `manage-sh-reference.md` | 新增第九章：9 组相似命令差异化对比 |
| 数据源生命周期 | `datasource-lifecycle.md` | 新增完整数据源生命周期文档 |

### 影响文件

```
backend/app/services/arp_collector_service.py  | 113 ++++++++++++++---
backend/app/services/compliance_service.py      |  10 ++
backend/app/services/data_source_service.py     |  26 ++++-
frontend/src/lib/utils.ts                       |   2 +-
frontend/src/i18n/locales/en.ts                 |   2 +-
frontend/src/i18n/locales/ja.ts                 |   2 +-
frontend/src/i18n/locales/zh.ts                 |   4 +-
docs/manage-sh-reference.md                     | 134 ++++++++++++++++++
docs/datasource-lifecycle.md                    | new file
```

---

## [v3.2.0-r2] - 2026-06-11

**发布类型**：Bug 修复 + 功能增强 | **合并方式**：Fast-forward

### 变更概要

manage.sh 全面审查修复与功能增强，修复 6 项 Bug，增强容错机制和备份安全，新增 7 个运维命令和 4 组环境变量。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `be61e90` | fix | manage.sh 全面审查修复与功能增强 |

### 变更明细

#### Bug 修复

| 变更项 | 文件 | 说明 |
|--------|------|------|
| `log_ok` 未定义 | `manage.sh` | 3处 `log_ok` 改为 `log_success` |
| `backup-schedule disable` 管道语法 | `manage.sh` | 修复 `|| true` 优先级导致管道断裂 |
| 硬编码容器名 | `manage.sh` | `tam_db`/`tam_redis` 统一为 `dc exec -T`，`tam_admin` 改为 `get_env DB_USER` |
| ADMIN_PASSWORD 环境变量缺失 | `manage.sh` + `cli.py` | demo/prod/init 三处写入 .env |
| `_run_setup` 不填充 RBAC 数据 | `cli.py` | 新增 `_ensure_rbac_seed(db)` 调用，init 时自动种子 5 角色 + 29 权限 |
| backup/health 硬编码用户名 | `manage.sh` | 改为 `get_env "DB_USER"` |

#### 核心增强

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 破坏性操作备份机制 | `manage.sh` | `interactive_backup` 函数，clean/redis flush/migrate 增加备份选项 |
| 日志开关 | `manage.sh` | `--log` 全局参数 + `TAM_LOG_ENABLED` 环境变量，30天自动清理 |
| 容错机制加强 | `manage.sh` | `require_services` 自动启动选项 + `check_disk_space`/`check_db_connection` 预检查 |
| 备份信息展示 | `manage.sh` | `auto_backup` 显示备份文件路径和大小 |
| SQL 注入防护 | `manage.sh` | `logs-export` 命令参数转义单引号 |

#### 新增功能

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 密码重置 | `manage.sh` + `cli.py` | `password reset <username> [--password <pw>]` |
| 用户管理 CLI | `manage.sh` + `cli.py` | `user list` / `user unlock <username>` |
| 审计日志导出 | `manage.sh` | `logs-export [--days N] [--output file] [--username user] [--action action]` |
| RBAC 角色查看 | `manage.sh` + `cli.py` | `role list` / `role permissions` |
| 服务单独重建 | `manage.sh` | `rebuild frontend/backend/nginx` |
| IPGuard 配置 | `manage.sh` | 部署向导增加 IPGuard 和 SWITCH_PORT 配置步骤 |
| 备份轮转 | `manage.sh` | `BACKUP_RETAIN_COUNT` 环境变量控制保留数量 |
| 配置热重载区分 | `manage.sh` | 区分热重载和需重启的配置键 |

#### 新增环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | — | 自定义初始管理员密码 |
| `BACKUP_RETAIN_COUNT` | `0`（保留全部） | 备份保留数量 |
| `TAM_LOG_ENABLED` | `false` | manage.sh 操作日志开关 |
| `IPGUARD_*` / `SWITCH_PORT` | — | 部署向导新增配置项 |

#### 文档更新

| 文档 | 版本 | 更新内容 |
|------|------|---------|
| `docs/release-notes.md` | v3.2.0-r1 → v3.2.0-r2 | 新增 r2 条目 |
| `docs/backend.md` | v3.2.0-r1 → v3.2.0-r2 | CLI 章节补充新子命令 + setup 行为变更 |
| `docs/RBAC.md` | v3.2.0-r1 → v3.2.0-r2 | 修正过时方案 + 补充 CLI 运维操作 |
| `docs/logging-guide.md` | v3.2.0 → v3.2.0-r2 | 补充 --log/TAM_LOG_ENABLED/logs-export |
| `docs/architecture.md` | v3.2.0-r1 → v3.2.0-r2 | 补充新环境变量 |
| `docs/production-readiness-assessment.md` | v3.2.0-r1 → v3.2.0-r2 | 运维工具覆盖表更新 |
| `docs/database.md` | v3.2.0-r1 → v3.2.0-r2 | 备份轮转策略 + RBAC seed 行为 |
| `docs/branding.md` | v3.2.0-r1 → v3.2.0-r2 | 配置热重载/重启区分 |
| `docs/api.md` | v3.2.0-r1 → v3.2.0-r2 | CLI 替代方案引用 |

### 变更统计

- **2 个文件变更**，+799 / -46 行
- **manage.sh**: +753 / -41 行（6 项 Bug 修复 + 3 项核心增强 + 7 项新增功能）
- **backend/cli.py**: +46 / -5 行（RBAC seed + 5 个新子命令）

---

## [v3.2.0-r1] - 2026-06-10

**发布类型**：功能迭代 | **合并方式**：Fast-forward | **标签**：`v3.2.0`

### 变更概要

本次版本聚焦于日志体系完善，新增 Request-ID 链路追踪、时区全局控制、审计日志补全和前端日志基础设施。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `5842dab` | feat(logging) | 新增 Request-ID 链路追踪中间件 + 集中式日志配置 |
| `daa8f24` | feat(config) | 时区全局控制 + Docker 安全加固注释化 |
| `aad35e1` | feat(audit) | 审计日志补全 + 前端日志基础设施 |
| `4a33c1a` | docs | 文档更新至 v3.2.0 |

### 变更明细

#### 新增功能

| 变更项 | 文件 | 说明 |
|--------|------|------|
| Request-ID 链路追踪 | `backend/app/middleware/request_id.py` | RequestIDMiddleware + ContextVar，12 位 hex request_id，支持上游 X-Request-ID 透传 |
| 集中式日志配置 | `backend/app/core/logging_config.py` | loguru + InterceptHandler + _log_format() 动态注入 request_id + time.tzset() 时区控制 |
| 时区全局控制 | `config.py` / `docker-compose.yml` / `logger.ts` | TZ 配置项贯穿 5 个 Docker 服务 + PostgreSQL + 后端日志 + 前端日志 |
| 前端日志工具 | `frontend/src/lib/logger.ts` | 分级输出 + 内存缓冲 100 条 + localStorage 持久化 50 条 + 本地时区格式 |
| 前端全局错误监听 | `frontend/src/App.tsx` | window.error + window.unhandledrejection |
| 日志说明文档 | `docs/logging-guide.md` | 16 章节完整日志文档 |

#### 改进优化

| 变更项 | 文件 | 说明 |
|--------|------|------|
| 请求日志增强 | `backend/app/middleware/logging.py` | 日志消息增加 req_id= 字段 |
| 审计日志补全 | `auth.py` / `compliance_baselines.py` / `data_sources.py` / `logs.py` / `settings.py` | 新增 login_failed/change_password/token_refresh/create_baseline/update_baseline/delete_baseline/bind_datasource/unbind_datasource/upload_branding/export_audit_logs 审计事件 |
| 后端日志统一 | `security.py` / `crypto.py` | logging.getLogger 改为 loguru logger |
| Docker 安全加固注释化 | `docker-compose.yml` | security_opt/cap_drop/read_only 注释，标注 Production hardening |
| 运维命令扩展 | `manage.sh` | 新增 logs-cleanup / logs-archive / audit-cleanup |
| Nginx 日志配置 | `nginx/etc/conf.d/tam.conf` | access_log / error_log 指令 |
| ErrorBoundary 日志 | `frontend/src/components/ErrorBoundary.tsx` | console.error 改为 logger.error |

#### 文档更新

| 文档 | 版本 | 更新内容 |
|------|------|---------|
| `docs/changelog.md` | v3.1.0 → v3.2.0 | 新增 [3.2.0] 条目 |
| `docs/backend.md` | v3.1.0 → v3.2.0 | 项目结构、中间件、配置、日志章节 |
| `docs/architecture.md` | v3.1.0 → v3.2.0 | 请求流程、日志架构、时区控制架构 |
| `docs/deployment.md` | v3.1.0 → v3.2.0 | 安全加固、TZ 配置、PG 时区 |
| `docs/database.md` | v3.1.0 → v3.2.0 | PostgreSQL 时区参数 |
| `docs/production-readiness-assessment.md` | v3.1.0 → v3.2.0 | 评分 8.6→8.7，Docker 安全策略说明 |
| `frontend/docs/implementation.md` | v3.1.0 → v3.2.0 | logger.ts、全局错误、时区说明 |
| `docs/logging-guide.md` | 新增 v3.2.0 | 16 章节完整日志文档 |

### 变更统计

- **27 个文件变更**，+2402 / -129 行
- **4 个新文件**：request_id.py、logging_config.py、logger.ts、logging-guide.md

### 验证结果

| 验证项 | 结果 |
|--------|------|
| Docker 构建后端 | ✅ 通过 |
| Docker 构建前端 | ✅ 通过 |
| 5 个服务启动 | ✅ Healthy |
| 后端日志时区 `+0800` | ✅ |
| 后端日志格式含 request_id | ✅ |
| 请求日志含 `req_id=` | ✅ |
| 响应头 `X-Request-ID` | ✅ |
| 响应头 `X-Response-Time` | ✅ |
| PostgreSQL 时区 `Asia/Shanghai` | ✅ |

### 发布操作

```bash
# 1. develop 分支提交（4 个 commit）
git add <files> && git commit  # ×4

# 2. 推送 develop
git push origin develop

# 3. 合并到 main
git checkout main
git merge develop              # Fast-forward

# 4. 打标签
git tag -a v3.2.0 -m "release: v3.2.0 — Request-ID链路追踪、时区全局控制、日志体系完善"

# 5. 推送 main + tag
git push origin main --tags

# 6. 切回 develop
git checkout develop
```

### 已知问题

| 问题 | 影响 | 状态 |
|------|------|------|
| Docker 安全加固项默认注释 | 开发环境安全限制降低，生产环境需手动取消注释 | 已标注 Production hardening 注释 |
| 前端 logger.ts 渐进式接入 | 仅 App.tsx/ErrorBoundary 使用，其他组件仍用 console | 后续迭代逐步替换 |

---

## [v3.1.0] - 2026-06-09

**发布类型**：安全加固 | **合并方式**：Fast-forward | **标签**：`v3.1.0`

### 变更概要

安全加固迭代，包括 Redis fail-open 降级、全局异常处理、Docker 安全策略、测试基础设施、CI/CD 配置和容器安全。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `5d13591` | release | v3.1.0 — 安全加固、测试基础设施、CI/CD、容器安全 |

### 变更明细

#### 新增功能

- Redis fail-open 降级策略：10 个 Redis 交互函数统一 try/except
- 全局异常处理器：HTTPException / ValidationError / Unhandled
- Docker 安全加固：security_opt / cap_drop / read_only / tmpfs
- CI/CD：GitHub Actions 测试 + 超时保护
- 测试基础设施：pytest-asyncio + conftest.py + 7 个测试文件
- LICENSE：MIT License
- Git 分支策略：main + develop + 分支保护规则
- Git 敏捷开发指导手册：docs/git-workflow-guide.md

#### 文档更新

7 个文档同步更新至 v3.1.0：changelog.md、backend.md、database.md、architecture.md、deployment.md、manage-sh-reference.md、frontend/docs/implementation.md

### 变更统计

- 多文件变更，详见 git diff v3.0.0..v3.1.0

---

## [v3.0.0] - 2026-06-08

**发布类型**：Bug 修复 | **合并方式**：— | **标签**：`v3.0.0`

### 变更概要

二次生产部署 bug 修复。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `20263ae` | fix | 二次生产部署bug修复 |

---

## [v2.5.0] - 2026-06-07

**发布类型**：功能迭代 | **合并方式**：— | **标签**：`v2.5.0`

### 变更概要

早期功能迭代版本。

### 提交记录

| Commit | 类型 | 说明 |
|--------|------|------|
| `263d6eb` | — | v2.5.0 |
