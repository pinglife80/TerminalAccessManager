# 更新日志

> 文档版本：v3.17.2  更新日期：2026-08-31

本文件记录 TerminalAccessManager 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

***

## [3.17.2] - 2026-08-31

### 修复

- **RBAC 授权加固（6 项）**：种子新增 `compliance:read`(36) / `compliance:write`(37) 权限并改为按 `Permission.code` 幂等补种；`POST /system/firewall-reconciliation` 增加 `system:manage` 权限；`GET /auth/users/email-available` 增加登录鉴权防邮箱枚举；4 个备份读接口改用 `backup:read`；operator 角色移除死权限 `terminal:write`
  - 关联文件：`cli.py`、`endpoints/system.py`、`endpoints/auth.py`、`endpoints/backup.py`
- **备份服务修复**：修复失效 settings 引用、错误 imports 与 `SameFileError` 等 14+ 处备份服务问题，并同步修复 15 个 pre-existing 失败用例
  - 关联文件：`services/backup_service.py`、`tests/test_backup_service.py`
- **中文日志乱码**：日志 JSON 序列化 `ensure_ascii=False`，修复中文日志 unicode 乱码
  - 关联文件：`core/logging_config.py`
- **角色编辑"已存在"误报**：角色更新唯一性校验排除当前 `role_id`
  - 关联文件：`endpoints/roles.py`
- **数据源删除统计偏差**：删除 ARP/防火墙数据源时影响统计改用 `firewall_tag` 过滤；删除合规基线按基线 tag 过滤
  - 关联文件：`services/data_source_service.py`、`endpoints/compliance_baselines.py`
- **会话超时体验**：超时提醒改为可手动关闭的对话框 + 倒计时自动注销
  - 关联文件：`App.tsx`、`useTokenExpiration.ts`
- **i18n 三语补全**：补齐 20 个断键 + 22 个日语缺失，清理 9 个僵尸词条，三语 leaf key 完全对齐（1421）
  - 关联文件：`i18n/locales/{en,zh,ja}.ts`

### 改进

- **暗色模式一致性**：输入/筛选/下拉框字体对比度修复 + 全站数据表表头统一 `bg-card` + 合规范围等页语义 token 迁移
  - 关联文件：`index.css` 及 16 个 `.tsx`
- **终端搜索框布局**：搜索框独占整行，避免被相邻筛选条件挤压
  - 关联文件：`Terminals.tsx`
- **备份列表分页**：备份列表增加分页
  - 关联文件：`Backup.tsx`

## [3.17.1] - 2026-08-28

### 修复

- **Pydantic v2 迁移**：8 个文件将弃用的 `class Config` 改为 `model_config = ConfigDict/SettingsConfigDict(...)`，消除弃用告警并适配 v2 `from_attributes` 语义
  - 关联文件：`config.py`、`schemas/{auth,auth_provider,compliance_baseline,compliance_scope,data_source,notification,role,terminal}.py`
- **SQLAlchemy 2.0 文本 SQL**：系统状态健康检查 `db.execute("SELECT 1")` 改为 `db.execute(text("SELECT 1"))`
  - 关联文件：`endpoints/system.py`
- **本地 2FA 验证码生成失效**：`two_factor_service.py` 引用不存在的 `generate_verification_code`，改为 `generate_email_code` 并补 `await`
  - 关联文件：`services/auth_providers/two_factor_service.py`
- **Webhook 测试连接降级逻辑**：`webhook_channel.py` 捕获不存在的 `httpx.MethodNotAllowed`，改为按 `status_code == 405` 触发 HEAD→POST 降级
  - 关联文件：`services/notification_channels/webhook_channel.py`
- **Compliance Scope IP 范围校验**：`compliance_scope_service.py` 重写 `ip_range` 校验，正确解析「前缀 + 起止末位八位组」格式并校验 `start>end`、`end>255`、非法前缀
  - 关联文件：`services/compliance_scope_service.py`
- **防火墙对账探测元组解包**：`firewall_reconciliation_service.py` `probe_ip` 解包修复、`_get_db_active_blacklist_by_firewall` 返回类型 `Set[Tuple]` → `Set[str]`
  - 关联文件：`services/firewall_reconciliation_service.py`
- **通知日志事务一致性（F）**：`notification_service.py` `_log_notification` 传入注入的 `self.db`，保持请求级事务
  - 关联文件：`services/notification_service.py`
- **死代码清理**：移除 `compliance_service.py` / `terminal_service.py` 中失效的 `wl_comments` 参数与 `unblocked_at` 冗余赋值
  - 关联文件：`services/compliance_service.py`、`services/terminal_service.py`
- **品牌文案一致性**：`.env.example` 残留 `Terminal Access Platform` → `Terminal Access Manager`
  - 关联文件：`.env.example`

### 改进

- **测试覆盖补全（6A–6E）**：新增/扩充 9 个测试文件与 `conftest.py`，覆盖认证安全链、核心合规链、通知投递链、备份/邮件链（约 6000+ 行）
- **覆盖率基础设施**：`pyproject.toml` 启用 `--cov=app`，`ci.yml` 增加 `--cov-fail-under=20` 门槛
- **默认邮件模板文件化**：新增 6 个 `backend/templates/email/*.html` 默认模板，全新部署即可正常渲染

## [3.17.0] - 2026-08-26

### 新增

- **合规防抖参数全链可配置化**：新增 `compliance_cooldown_minutes`（默认 10，clamp 1~60）、`compliance_ip_grace_minutes`（默认 10，clamp 1~60）、`compliance_whitelist_miss_threshold`（默认 6，clamp 2~20）三项系统配置，归入 compliance 组，系统设置页可编辑
  - 关联文件：`config_service.py`、`system_config.py`、`compliance_service.py`、`GeneralSettings.tsx`、`useTerminalData.ts`、`i18n/locales/{zh,en,ja}.ts`
- **首次发现确认阈值保护**：新增 `apply_initial_compliance_result`，首次发现路径（arp_collector + main 调度兜底）非合规需累计达到确认阈值才降级封锁
  - 关联文件：`compliance_service.py`、`arp_collector_service.py`、`main.py`
- **auto_block 白名单权威预检**：自动封锁前强制校验白名单，命中则自愈为 bypass 并跳过封锁
  - 关联文件：`compliance_service.py`

### 修复

- **确认阈值配置从不生效**：`_get_confirm_threshold` 向 `ConfigService.get` 传入第二参数触发 TypeError 被静默捕获，改为 `get(...) or "2"`
  - 关联文件：`compliance_service.py`
- **NULL-MAC 自动解封分组坍塌**：自动解封按 MAC 分组时空 MAC 回退 IP 分组，避免不同终端坍缩到同一桶
  - 关联文件：`compliance_service.py`
- **MAC+IP 白名单瞬时误判**：添加 both 白名单时校验终端当前 IP 是否匹配 ip_pattern，不匹配则交由下一轮重算评估
  - 关联文件：`terminal_service.py`
- **TerminalStatus 导入 NameError**：补齐 `TerminalStatus` 导入
  - 关联文件：`compliance_service.py`
- **死代码清理**：移除 `arp_collector_service.py` 中未使用的 `_auto_block_task`
  - 关联文件：`arp_collector_service.py`

## [3.16.1] - 2026-08-25

### 修复

- **IPGuard 匹配元组真值误判**：`_match_ipguard_in_memory` 返回 `(is_compliant, ip_found, mac_found)` 三元组，此前在 `auto_unblock_compliant` 与 `recalculate_all_compliance` 中把该元组直接当布尔值使用（非空元组恒为 True），导致本应不合规的终端被误判为合规；改为正确解包 `ig_match, _, _ = ...`
  - 关联文件：`compliance_service.py`
- **IPGuard 缓存陈旧导致的误判降级**：`recalculate_all_compliance` 依赖 IPGuard Redis 缓存做合规判定，缓存存在同步时延，导致「IPGuard 外部系统延迟登记」的终端在窗口期被误判 `non_compliant` 并封锁；新增缓存新鲜度门控，当基线同步时间戳超过可配置阈值时跳过降级、hold 原状态
  - 关联文件：`compliance_service.py`

### 新增

- **系统配置项 `ipguard_stale_threshold_minutes`**：IPGuard 缓存陈旧阈值（默认 12 分钟，clamp 5~60），归入 compliance 配置组，系统设置页可编辑
  - 关联文件：`config_service.py`、`system_config.py`、`GeneralSettings.tsx`、`useTerminalData.ts`

## [3.16.0] - 2026-08-25

### 新增

- **黑名单「解封事件」列**：
  - 黑名单列表新增「解封事件」列，成功解封条目显示解封原因（reason）与时间（unblocked_at）
  - 三语 i18n 新增 `unblockEvent` 文案（zh/en/ja）
  - 关联文件：`Blacklist.tsx`、`locales/zh.ts`、`locales/en.ts`、`locales/ja.ts`

### 修复

- **到期自动解封缺失独立 reason**：`cleanup_expired_blacklist` 到期解封时未写入解封原因，现统一写入「封锁时间到期自动解封」作为独立事件原因，与合规解封（whitelist match / IPGuard match）区分
  - 关联文件：`terminal_service.py`、`test_compliance_service.py`
- **SQLite 连接池参数报错**：`database.py` 对 SQLite 也传入 `pool_timeout`/`pool_use_lifo` 等不支持的参数导致单测失败；改为仅在非 SQLite 数据库时应用
  - 关联文件：`database.py`
- **manage.sh 版本管理逻辑**：`version check`/`version bump` 改为统一从 `VERSION` 动态派生，移除对 `package.json`/`package-lock.json` 的静态写入与比对
  - 关联文件：`manage.sh`

## [3.15.0] - 2026-08-25

### 新增

- **黑名单封锁时长（block_time）可配置化**：
  - 新增 `block_time` 系统配置项（compliance 分类，默认 30d，支持 1h/6h/12h/1d/3d/7d/15d/30d）
  - 系统设置页（GeneralSettings）compliance 分组新增 block_time 下拉选择
  - 自动封锁弹窗（ComplianceBaselinesTab）新增封锁时长下拉，默认取系统配置值、可逐次覆盖
  - 防火墙对账补建条目改用系统配置 block_time，替代硬编码 30d
  - 关联文件：`config_service.py`、`system_config.py`、`firewall_reconciliation_service.py`、`useTerminalData.ts`、`GeneralSettings.tsx`、`ComplianceBaselinesTab.tsx`

### 修复

- **`_get_block_time` 配置读取 bug**：原 `config_service.get("block_time", "30d")` 传入第二参数导致 TypeError 被静默捕获，配置从不生效；改为 `get("block_time") or "30d"`
  - 关联文件：`compliance_service.py`

## [3.14.0] - 2026-08-24

### 新增

- **黑名单操作追踪**：
  - 新增 `last_operation_type/status/error/at` 与 `retry_count` 字段，追踪最近一次封锁/解封结果与重试次数
  - 新增 Alembic 迁移 `036_blacklist_operation_tracking`
  - 关联文件：`models/blacklist.py`、`schemas/terminal.py`、`endpoints/blacklist.py`

- **黑名单展示能力增强**：
  - 前端新增黑名单状态列、防火墙错误弹窗（展示结构化 `tag/error` 与对账同步时间）
  - Retry Unblock 按钮按 `terminal_compliance_status`（compliant/bypass）条件显示
  - 关联文件：`Blacklist.tsx`、`Terminals.tsx`、`useTerminalData.ts`、`i18n/locales/*`

### 修复

- **合规状态不变量与重试防护**：
  - 强制 `compliance_status='non_compliant'` ⇒ `status='blocked'`，消除中间态
  - retry-block 忽略冷却期、对 `non_compliant+unblocked` 强制封锁，并做白名单权威自愈预检
  - 自动解封同步写 `compliance_status`（bypass/compliant 按命中类型落地），阻断被重封震荡
  - 关联文件：`compliance_service.py`、`main.py`

- **统计口径统一（MAC 归一化）**：
  - blocked / non_compliant / pending_retry_block / pending_retry_unblock / source 口径统一
  - 黑名单-终端关联改用 MAC 归一化（NULL-MAC 回退 IP）去重，消除 DHCP 换 IP 漏计
  - 关联文件：`terminal_service.py`、`endpoints/terminals.py`

- **防火墙对账增强**：
  - 错误收集改为结构化 `[{tag, error}]`，支持前端展示
  - 新增孤立 `blocked` 终端自愈（`_repair_stale_terminal_status`）
  - 关联文件：`firewall_reconciliation_service.py`

- **数据源安全删除**：
  - `safe_delete_binding` 改用 MAC 归一化匹配终端，删除绑定后不再遗留孤立 blocked 终端
  - `create_binding` 创建后触发 `recalculate_all_compliance()`
  - 关联文件：`data_source_service.py`

## [3.13.0] - 2026-08-21

### 新增

- **防火墙实际统计展示**：
  - 新增 `_cache_reconcile_result` 函数，将对账结果缓存到 Redis（TTL 1 小时）
  - 黑名单页面新增"防火墙实际封锁数"统计卡片
  - 手动触发对账端点也会缓存结果
  - 关联文件：`main.py`、`system.py`、`Blacklist.tsx`

### 修复

- **黑名单统计不一致问题**：
  - 统一三个页面统计口径：Dashboard、终端管理、黑名单都使用 `blocked` 计数
  - 终端管理页面从 `stats.non_compliant` 改为 `stats.blocked`
  - 移除 `firewall_reconciliation_service.py` 中重复的缓存逻辑，统一使用 `main.py` 实现
  - 修复前端 fallback 统计逻辑：从 `compliance_status` 改为 `status === 'blocked'`
  - 关联文件：`firewall_reconciliation_service.py`、`Terminals.tsx`、`terminal_service.py`

- **状态不变量加强**：
  - 确保 `compliance_status='non_compliant'` 意味着 `status='blocked'`
  - 冷却期阻止合规状态降级而非阻止封锁动作
  - non_compliant 降级后封锁失败回滚状态
  - retry-block 对已有中间态强制封锁
  - 关联文件：`compliance_service.py`、`main.py`

- **白名单终端稳定性修复**：
  - 白名单匹配时直接设置 `compliance_status='bypass'` 并清零确认计数
  - 增加周期性全量重算，修复卡死状态
  - 消除震荡闭环，保持稳定的 bypass 状态
  - 关联文件：`compliance_service.py`、`main.py`

***

## [3.12.1] - 2026-08-20

### 修复

- **黑名单与防火墙状态不同步问题修复**：
  - 修复唯一约束：Blacklist 表唯一索引增加 `firewall_tag` 字段，支持多防火墙部署下每个防火墙独立一条记录，避免跨防火墙去重错误
  - 修复封锁结果判断逻辑：原代码中多个防火墙共用同一个错误列表，任意一个防火墙失败会导致所有结果都判定为失败，现在每个防火墙独立判断成功/失败
  - 防火墙部分成功场景：部分防火墙封锁成功、部分失败时，仅为成功的防火墙创建 Blacklist 记录，失败的防火墙由下一轮对账自动补封
  - 重写防火墙对账逻辑：以数据库为权威源，防火墙仅返回 0 条记录时自动跳过，不会错误解封；对账只补封防火墙缺失的记录，不会误删有效条目
  - 修复过期清理逻辑：按归一化 MAC 匹配终端，所有防火墙 Blacklist 都过期才更新终端状态
  - 修复 recalculate 中重复检查逻辑：按防火墙查询已有活跃记录，每个防火墙独立幂等检查
  - 新增 Alembic 迁移 `035_blacklist_fix_sync_issues`：自动清理 15 条孤儿记录（无 firewall_tag、无 MAC、重复记录），更新唯一索引
  - 关联文件：`blacklist.py`（model）、`compliance_service.py`、`firewall_reconciliation_service.py`、`terminal_service.py`

### 问题说明

- v3.12.0 发布后发现：Dashboard/终端页面显示封锁 85 条，防火墙实际 85 条，但黑名单页面显示 99 条，存在 14 条不一致
- 根因：旧逻辑在防火墙封锁失败时仍创建 Blacklist 记录，对账逻辑错误删除/标记记录，以及唯一约束错误导致重复记录
- v3.12.1 修复后：防火墙封锁失败不创建记录，每个防火墙独立对账，迁移自动清理历史脏数据，三个位置统计保持一致

***

## [3.12.0] - 2026-08-20

### 新增

- **Compliance Scope 条件增强 - MAC前缀匹配数据源区分**：
  - 原 `mac_prefix` 类型拆分为 `mac_prefix_arp` 和 `mac_prefix_ipguard` 两种独立类型
  - `mac_prefix_arp`：匹配 ARP 采集的终端 MAC，命中后忽略 MAC 仅用 IP 匹配 IPGuard 基线
  - `mac_prefix_ipguard`：匹配 IPGuard 基线中的 MAC，命中后按 IP+MAC 精确匹配
  - 前端界面新增两种类型选项和说明，自动迁移原有 `mac_prefix` 数据为 `mac_prefix_arp`
  - 新增 Alembic 迁移 `032_mac_prefix_scope_type_split`
  - 关联文件：`compliance_scope.py`（model/schema/service）、`ComplianceScope.tsx`、`complianceScope.ts`、i18n 多语言文件

- **终端唯一标识重构 - MAC地址作为终端主键**：
  - Terminal 表唯一约束从 `(ip_address, mac_address)` 改为 `mac_address_normalized`（MAC归一化值）
  - ARP 入库逻辑重构：按 MAC 查询现有记录并更新 IP 地址，DHCP 换 IP 不再产生重复终端记录
  - 新增终端支持有线+无线双网卡场景：每个 MAC 对应一条独立记录，分别进行合规判断
  - IPGuard 基线解析正确支持多 MAC-IP 对格式：`MAC1(IP1)MAC2(IP2)...`
  - 数据迁移自动去重：保留每个 MAC 最新/被封禁记录，删除冲突的重复记录
  - 新增 Alembic 迁移 `033_terminal_mac_unique`
  - 关联文件：`terminal.py`（model）、`arp_collector_service.py`、`compliance_service.py`

- **合规状态防震荡机制（三层保护）**：
  - **对称确认计数**：降级（任何状态→non_compliant）和升级（non_compliant→compliant/bypass）都需要连续 N 次检查确认（默认 N=2≈10分钟），防止一次瞬态不匹配就触发状态切换
  - **双向冷却期**：自动封禁后 10 分钟内不自动解封，自动解封后 10 分钟内不自动重新封禁
  - **IP 变更宽限期**：DHCP 换 IP 后 10 分钟宽限期内不立即降级封禁，给 IPGuard 基线同步新 IP-MAC 映射留出时间
  - **解封与状态变更解耦**：`auto_unblock` 仅处理防火墙 API 解封操作，不直接设置 `compliance_status`，合规状态由下一轮定时检查按确认计数逻辑正常更新
  - 新增 Alembic 迁移 `034_compliance_oscillation_fixes`
  - 关联文件：`compliance_service.py`、`main.py`、`terminal.py`（model）、`arp_collector_service.py`

### 改进

- **时序竞争消除**：IPGuard 基线同步完成后不再立即触发全量合规重算，避免"新基线+旧ARP数据"导致的误判，由下一轮定时合规检查自然使用新缓存
- **黑名单查询优化**：活跃黑名单查询、重试封禁逻辑改为按 normalized MAC 查询标识，正确处理 DHCP 换 IP 场景，避免重复封禁/漏解封
- **Auto-unblock 分组改进**：按 normalized MAC 分组处理同一终端的多防火墙条目，合规检查使用终端当前最新 IP，防火墙解封使用黑名单中记录的原始封禁 IP
- **重试封禁逻辑增强**：retry-block 增加重复检查和冷却保护，防止同一终端重复添加封禁条目
- **状态变更日志增强**：确认计数变化输出 debug 日志，达到阈值发生状态变更时输出 INFO 日志明确记录 "CONFIRMED downgrade/upgrade" 原因

### 修复

- **修复 auto_unblock 分组 key 未归一化**：原始 (ip, mac) 作为分组 key 未处理 MAC 格式差异，导致同一物理终端多防火墙条目被拆分到不同组，解封不一致
- **修复 main.py 定时合规检查 result_lookup key 遗漏**：MAC 唯一化改造后，`scheduled_compliance_check` 仍用 IP 作为 result_lookup 的 key，导致双网卡/换 IP 场景结果应用错误
- **修复 bypass 状态降级阈值硬编码为 1**：从 bypass 降级到 non_compliant 原来只需要 1 次不匹配就立即封禁，改为使用统一的配置确认阈值
- **修复 unknown 状态无确认阈值**：新终端/IP 变更后的 unknown 状态第一次不匹配就直接 non_compliant，改为也需要达到确认阈值
- **修复活跃黑名单查询条件**：在 MAC 唯一化后仍按 (IP, MAC) 查询活跃黑名单，DHCP 换 IP 后查不到已存在封禁记录，导致重复封禁

***

## [3.11.0] - 2026-08-20

### 新增

- **Compliance Scope 条件管理**：支持根据网段范围或 MAC 前缀作为条件，在合规计算时只将 IP 地址作为判断条件而忽略 MAC 地址
  - 新增 `compliance_scope` 数据表，支持三种条件类型：`ip_cidr`（IP 网段）、`ip_range`（IP 范围）、`mac_prefix`（MAC 前缀）
  - 新增 ComplianceScope ORM 模型、Schema、Service 层和 REST API 端点
  - 新增前端 Scope 管理页面，支持条件的增删改查和启用/禁用切换
  - 合规计算流程集成：白名单检查 → Scope 条件检查 → IPGuard 基准匹配
  - Scope 条件范围内的终端采用"仅 IP 匹配"策略，范围外保持"IP+MAC 双重匹配"
  - 新增缓存失效机制，Scope 变更时自动清除相关缓存
  - 新增 Alembic 迁移 `031_compliance_scope`
  - 关联文件：`compliance_scope.py`（model/schema/service/endpoint）、`compliance_service.py`、`ComplianceScope.tsx`、`complianceScope.ts`

### 改进

- **白名单导入增强**：支持直接导入备份 ZIP/JSON 格式文件
  - `POST /whitelist/import` 端点新增 `.zip` 和 `.json` 文件格式支持
  - 自动识别 ZIP 文件内部结构（嵌套 `whitelist/whitelist.json` 或扁平 `whitelist.json`）
  - 支持冲突处理模式：`skip`（跳过已存在条目）、`overwrite`（覆盖已存在条目）
  - 采用 savepoint 事务隔离行级导入错误，单行失败不影响整体导入
  - 导入完成后自动失效合规缓存
  - 关联文件：`whitelist.py`、`terminal_service.py`、`Whitelist.tsx`

### 修复

- **黑名单导出字段引用错误**：修复 `GET /blacklist/export` 端点引用了 Blacklist 模型不存在的 `status`、`block_time`、`added_by`、`created_at` 字段
  - 替换为现有模型字段：`blocked_at`、`blocked_by`、`source_tag`
  - `status` 字段从 `auto_unblocked` / `unblocked_at` 动态派生
  - CSV 表头新增 'Status'、'Block Type'、'Auto Unblocked' 列
  - 关联文件：`blacklist.py`

- **合规 recalculate_all_compliance 缺少 Scope 条件集成**：`recalculate_all_compliance()` 方法未加载 Scope 条件数据，导致重算时所有终端都采用 IP+MAC 双重匹配策略
  - 修复：加载 Scope 数据并根据条件应用"仅 IP 匹配"策略
  - 新增 bypass 状态快速降级机制（1 个确认周期而非默认阈值）
  - 关联文件：`compliance_service.py`

- **侧边栏折叠按钮裁剪问题**：侧边栏折叠按钮右侧被页面内容覆盖
  - 修复：移除 `<aside>` 元素的 `overflow-hidden`，为 `<nav>` 添加 `min-h-0`
  - 新增自定义细滚动条样式（6px 宽度，暗色主题）
  - 关联文件：`Sidebar.tsx`、`index.css`

***

## [3.10.4] - 2026-08-10

### 修复

- **Loguru 控制台日志 ValueError**：模块级代码（如 `main.py` 的 Prometheus 初始化）触发日志时，`{function}` 字段值为 `<module>`，loguru colorizer 将其解析为颜色指令标签并抛出 `ValueError: Tag '<module>' interpreted as a color directive`
  - 修复方案：新增 `_patcher()` 函数，通过 `logger.configure(patcher=...)` 在格式化前将 `<module>` 中的尖括号替换为方括号 `[module]`
  - 关联文件：backend/app/core/logging_config.py

- **通知 worker SMTP 认证错误无脑重试**：邮件通知发送失败时，SMTP 认证错误（"invalid username-password pair or user is disabled"）被统一包装为 `EmailSendError`，通知 worker 无法区分认证失败与瞬时错误，对永久性认证错误执行无意义的指数退避重试（3 次，最多 40 秒），浪费资源并刷屏日志
  - 修复方案：`EmailSender.send()` 新增 `smtplib.SMTPAuthenticationError` 专门捕获，标记 `AUTH_ERROR:` 前缀；`EmailChannel` 传播 `error_code="AUTH_ERROR"`；`NotificationWorkers._deliver_notification()` 检测到 `AUTH_ERROR` 跳过重试，直接记录失败并输出引导用户检查 SMTP 凭证的警告
  - 关联文件：backend/app/services/email_service.py、backend/app/services/notification_channels/email_channel.py、backend/app/services/notification_workers.py

### 改进

- **邮件密码配置描述修正**：`email_password` 系统配置项描述从"stored encrypted in DB"改为"use authorization code/授权码 for QQ/163"，消除误导（密码实际以明文存储于 system_config 表）
  - 关联文件：backend/app/services/config_service.py

***

## [3.10.3] - 2026-08-10

### 修复

- **品牌资源加载 403**：Nginx `/uploads/` location 中的 `valid_referers` 检查在 `server_name _` 配置下无法匹配生产环境 IP 访问的 Referer，导致品牌背景图和 favicon 加载返回 403
  - 修复方案：移除 `valid_referers` + `if ($invalid_referer)` 检查块；品牌资源文件名使用 UUID 生成不可猜测，无需 Referer 访问控制
  - 关联文件：nginx/etc/conf.d/tam.conf.template

- **容器 volume 挂载权限**：取消容器安全加固后，Docker named volume 首次挂载以 root:root 创建挂载点目录，app 用户（非 root）无法写入 `/var/log/tam` 和 `/app/uploads`
  - 修复方案：backend/Dockerfile 在 `USER app` 前预创建 `/var/log/tam`、`/app/uploads/backups`、`/app/uploads/branding` 并设置 `app:app` 所有者；nginx/docker-entrypoint.sh 补充 tmpfs 目录 `chown nginx:nginx`
  - 关联文件：backend/Dockerfile、nginx/docker-entrypoint.sh

### 改进

- **清理安全加固残留配置**：删除 docker-compose.yml 中 4 处 `Production hardening` 注释块和 postgres/backend 冗余 tmpfs（取消 read_only 后不再需要）
  - 关联文件：docker-compose.yml

***

## [3.10.2] - 2026-08-06

### 修复

- **CRITICAL — admin 密码硬编码为 Admin123**：生产模式向导收集的 `ADMIN_PASSWORD` 只写入 `.env`，从未注入 backend 容器也从未被 `cli.py setup` 读取，导致部署后管理员密码永远是公开已知的 `Admin123`
  - 修复方案：
    1. `docker-compose.yml` backend environment 中新增 `ADMIN_PASSWORD` 和 `ENVIRONMENT` 注入
    2. `cli.py` `_create_admin_user()` 优先从 `ADMIN_PASSWORD` env var 取密码；生产模式无强密码时明确告警；创建成功的密码输出按生产模式脱敏
  - 关联文件：[docker-compose.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L103-L106)、[cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L49-L106)

- **HIGH — backend 加固冲突**：`docker-compose.prod.yml` 为 backend 同时声明 `tmpfs: /app/uploads` 和基础 compose 的 `volume: tam-uploads:/app/uploads`，目标路径重叠属于 Docker Compose 未定义行为（要么丢持久化，要么加固失效）
  - 修复方案：移除生产加固 `tmpfs` 中 `/app/uploads`，仅保留 `tmpfs: [/tmp]`；上传目录由命名卷正确持久化
  - 关联文件：[docker-compose.prod.yml](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.prod.yml#L22-L25)

### 改进

- **上传目录绝对路径统一**：`config.py` `UPLOAD_DIR` 从相对路径 `./uploads` 改为绝对路径 `/app/uploads`；`backup_service.py` 移除 `getattr(settings, 'UPLOAD_DIR', '/app/uploads')` 的不一致兜底，直接读取 `settings.UPLOAD_DIR`
  - 关联文件：[config.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/config.py#L87)、[backup_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L547-L548)、[backup_service.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L575-L576)

- **setup 提示上下文感知**：`cli.py setup` 完成后按 `ENVIRONMENT` / 容器检测动态打印 Next steps（容器内：提示 Nginx 入口；外部裸机：保留原提示）
  - 关联文件：[cli.py](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L135-L157)

- **deploy setup DB 权威探测**：manage.sh deploy 第 6/6 步不再只看本地 state 文件来判断是否跳过 setup；新增 DB 侧 `users:admin` 真实存在性探测，避免 `postgres_data` 被清空后 state 残留导致永远跳过初始化、无法登录
  - 关联文件：[manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L925-L974)

- **部署验证按模式选择顺序**：dev 模式先验证 HTTP 8080（tam.dev.conf 无 SSL）；prod 模式先验证 HTTPS 8443 → fallback HTTP 8080 301 redirect，消除不必要的 curl 失败/等待
  - 关联文件：[manage.sh](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L991-L1023)

- **端口全面变量化**：新增 `TAM_NGINX_PORT`、`TAM_NGINX_SSL_PORT`、`TAM_BACKEND_PORT` 环境变量，`.env` 一处配置全链路生效（Nginx listen、upstream backend_api、backend uvicorn --port、healthcheck、manage.sh curl 检测）
  - 关联文件：docker-compose.yml、nginx/etc/conf.d/tam.conf.template、nginx/docker-entrypoint.sh、backend/Dockerfile、manage.sh、.env.example

- **Nginx 配置架构重构**：删除静态 `tam.conf` / `tam.dev.conf`，统一为 `tam.conf.template` + `envsubst` 动态生成；消除 dev/prod 双配置文件的维护负担
  - 关联文件：nginx/etc/conf.d/tam.conf.template、nginx/docker-entrypoint.sh

- **容器安全加固移除**：内网部署环境下 `cap_drop:ALL`、`read_only:true`、`no-new-privileges` 等加固措施导致权限冲突（nginx bind 80 失败、backend 卷写入失败），全面移除；删除 `docker-compose.dev.yml` 和 `docker-compose.prod.yml` 覆盖文件，dev/prod 差异仅由 `.env` 中 `ENVIRONMENT` 变量控制
  - 关联文件：docker-compose.yml、docker-compose.dev.yml(删除)、docker-compose.prod.yml(删除)

- **COMPOSE_PROJECT_NAME 统一**：`.env` 中新增 `COMPOSE_PROJECT_NAME=tam`，消除 `terminalaccessmanager-*` 冗余前缀资源
  - 关联文件：.env.example、manage.sh

- **Docker 卷重命名**：`tam-uploads`→`backend-data`、`tam-logs`→`backend-logs`，消除 `tam_tam-*` 冗余前缀，名称准确反映业务语义
  - 关联文件：docker-compose.yml

- **env 全量传递**：docker-compose.yml backend.environment 从 16 项扩充为 43 项，覆盖 Settings 类全部可配置字段；healthcheck 从硬编码 `localhost:8000` 改为容器内 `os.environ.get('BACKEND_PORT')` 动态读取
  - 关联文件：docker-compose.yml

- **备份服务连接修复**：backup_service.py 优先从 `DATABASE_URL` 正则解析连接参数，fallback 到 `DB_*` 字段；backend Dockerfile 新增 `postgresql-client` 提供 `pg_dump`；备份清理逻辑新增零字节文件删除
  - 关联文件：backend/app/services/backup_service.py、backend/Dockerfile

- **日志格式修复**：loguru JSON 格式化模板中 `{}` 未转义导致 `KeyError: '"timestamp"'`，改为 `{{}}` 转义
  - 关联文件：backend/app/core/logging_config.py

- **缺失导入修复**：main.py 新增 `get_config_value` 和 `emit_compliance_alert` 导入，修复 v3.10.1 引入的 NameError
  - 关联文件：backend/app/main.py

- **构建产物清理**：backend/.dockerignore 和 backend/.gitignore 新增，排除 `uploads/backups/`、`backups/`、`*.zip`、`uploads/`，防止运行时文件打包进镜像
  - 关联文件：backend/.dockerignore、backend/.gitignore

***

## [3.10.1] - 2026-08-06

### 修复

- **CLI 用户命令属性错误**：`user list`、`user unlock` 命令引用 User 模型不存在的 `locked_until`、`failed_login_attempts` 字段
  - 修复方案：锁定状态改为从 Redis `login_lock:{username}` 查询 TTL；解锁使用 `reset_login_attempts()` 清除 Redis key
  - 关联文件：`cli.py`

- **CLI 角色命令属性错误**：`role list` 命令引用 Role 模型不存在的 `is_builtin`、`display_name` 字段
  - 修复方案：改为 `is_default`、`name`
  - 关联文件：`cli.py`

- **scheduler trigger compliance_check 参数缺失**：`batch_check_compliance()` 调用未传入 `entries` 参数导致 `TypeError`
  - 修复方案：完整实现 compliance_check 流程：查找 ARP 数据源→遍历 unchecked→批量 check→应用结果→auto-block→全局告警
  - 关联文件：`cli.py`

- **合规率计算公式错误**：原公式 `rate = compliant / (compliant + non_compliant)` 排除了 bypass（白名单旁路）和 unknown 终端，严重低估合规率
  - 修复方案：`rate = (compliant + bypass) / (compliant + bypass + non_compliant + unknown)`
  - 关联文件：`main.py`

- **合规率告警数据源错误**：原告警基于 per-source 本次检查结果（仅含新检查的 unknown 终端），导致告警显示 `0.0%` 或 `nan`
  - 修复方案：使用 `TerminalService.get_stats()` 读取 DB 全局统计；删除 for 循环内重复告警
  - 关联文件：`main.py`

- **合规率告警阈值守卫缺失**：合规率达标（≥ 80%）时仍触发 `alert.compliance_rate_low` 告警
  - 修复方案：新增阈值守卫 `if compliance_rate >= threshold: return []`
  - 关联文件：`event_emitter.py`

- **Shell 脚本未绑定变量错误**：`manage.sh` 中 4 处 `$2` 在 `set -u` 模式下报 `unbound variable`
  - 修复方案：改为 `${2:-}` 语法
  - 关联文件：`manage.sh`

- **manage.sh 版本管理不统一**：`version bump/check` 命令同步文件过多、逻辑冗余
  - 修复方案：重写为仅同步必要文件（VERSION → package.json）
  - 关联文件：`manage.sh`

- **manage.sh API 地址硬编码**：`scheduler status` 硬编码 `https://localhost:8443`，不适配实际部署
  - 修复方案：`_API_BASE_URL` 改为函数，默认 `http://localhost:8080/api/v1`，支持 `.env` 中 `CLI_API_BASE_URL` 覆盖
  - 关联文件：`manage.sh`、`.env.example`

- **合规设置参数描述未国际化**：GeneralSettings 页面 5 个配置项描述未使用 i18n 翻译
  - 修复方案：新增 `FIELD_DESC_I18N_KEYS` 映射表，优先显示翻译文本
  - 关联文件：`GeneralSettings.tsx`

- **前端 package.json 版本不同步**：Docker 构建时 package.json 版本可能与 VERSION 文件不一致
  - 修复方案：Dockerfile 在 `npm ci` 前用 sed 从 VERSION 读取并同步 package.json version
  - 关联文件：`Dockerfile`

### 新增

- **合规率告警数据增强**：`emit_compliance_alert()` 事件数据新增 `total_checked`、`compliant_count`、`bypass_count` 字段，便于排障
  - 关联文件：`event_emitter.py`

***

## [3.10.0] - 2026-08-06

### 新增

- **告警阈值前端可配置化**：4 个硬编码阈值参数提取为系统配置项
  - 新增 `alert` 配置分类和 `AlertConfigResponse` 模型
  - 合规率告警阈值（`alert_compliance_rate_threshold`，默认 80%）
  - 合规率危险比例（`alert_compliance_critical_ratio`，默认 50%）
  - 封锁数量告警阈值（`alert_block_count_threshold`，默认 50）
  - 离线检测倍数（`alert_offline_threshold_multiplier`，默认 3）
  - 系统设置 General 页面新增「告警阈值配置」分区
  - 关联文件：`system_config.py`、`config_service.py`、`main.py`、`event_emitter.py`、`compliance_service.py`、`arp_collector_service.py`、`GeneralSettings.tsx`、`useTerminalData.ts`、`en.ts`、`ja.ts`、`zh.ts`

- **备份恢复增强**：新增白名单恢复、配置文件解包、日志恢复
  - `_restore_whitelist_from_zip()` / `_restore_whitelist_from_json()` / `_restore_logs_from_zip()`
  - 系统配置 DB 恢复使用 `begin_nested()` 逐表事务保护

- **远程备份过期清理**：SFTP/FTP 远程存储中的过期备份自动清理

### 修复

- **备份选项不生效**：手动备份端点未加载用户保存的配置，导致备份选项（数据库/配置/白名单/日志）被忽略
  - `POST /api/v1/backup/run` 和 `POST /api/v1/backup/whitelist` 端点添加 `load_config()` 调用
  - 白名单备份添加 `if self.config.backup_whitelist:` 条件检查

- **合规率告警量纲 bug**：`emit_compliance_alert()` 中 `compliance_rate`（0-100）与 `threshold`（0-1）量纲不一致，导致 `is_critical` 判断永远为 False
  - 统一使用 0-100 百分比量纲

- **备份配置文件不完整**：`_backup_config()` 未包含 `nginx.conf` 和 `alembic.ini`

- **PostgreSQL 未配置时静默成功**：`_backup_database()` 在 PostgreSQL 未配置时返回成功而非报错

- **Backup.tsx 默认值缺失**：`defaultValues` 中 `backup_whitelist` 为 `undefined`，导致初始渲染异常

***

## [3.9.0] - 2026-08-05

### 新增

- **scheduler_backup_interval 配置项**：定时备份任务轮询间隔从硬编码改为系统配置项
  - 新增配置项 `scheduler_backup_interval`（默认 3600s，范围 60-86400）
  - 系统设置 General 页面「调度器配置」分组新增该项
  - 关联文件：`system_config.py`、`config_service.py`、`useTerminalData.ts`、`GeneralSettings.tsx`

- **通知系统架构优化**：
  - 事件覆盖率监控：统计 API 新增 `event_coverage` 字段
  - 终端离线检测：ARP 采集中检测离线终端并发射 `terminal.offline` 事件
  - 实时事件类型集合：`REALTIME_EVENT_TYPES` 区分实时/聚合事件
  - `alert.auto_block_triggered` 事件发射：合规自动封堵时触发通知

- **定时备份 cron 调度**：定时备份按 `backup_config.schedule` 指定的 cron 表达式执行
  - 重写 `scheduled_backup()` 函数，支持 cron 表达式解析
  - 新增 `_should_run_backup_now()` 函数匹配 cron 表达式
  - 使用 Redis 去重防止同一分钟内重复执行
  - 定时备份结果写入 audit_logs 表

### 修复

- **通知管道黑洞**：`emit_event()` 移除聚合器优先路径，恢复 Worker 管道
  - 根因：`emit_event()` 优先将事件投递到 `NotificationAggregator`，导致 Worker 管道被绕过，所有事件被吞噬
  - 修复：直接调用 `NotificationService.emit()`，事件走 Redis Queue → Worker 管道
  - 关联文件：`event_emitter.py`

- **事件类型字符串不匹配**：修复 `system.error`、`system.warning`、`system.alert` 三个事件类型字符串
  - 根因：`emit_system_error()` 等函数传入的事件类型字符串与 `EventType` 枚举值不一致
  - 修复：修正事件类型字符串匹配枚举值
  - 关联文件：`event_emitter.py`

- **定时备份未执行**：`main.py` 中 `scheduled_backup` 任务未注册到调度器
  - 根因：`lifespan()` 中未创建 `scheduled_backup` 任务
  - 修复：在 `lifespan()` 中注册 `scheduled_backup` 任务
  - 关联文件：`main.py`

- **FTP 备份时间戳时区错误**：远端备份文件时间戳少 8 小时
  - 根因：FTP MDTM 返回 UTC 时间，未转换为本地时区 (UTC+8)
  - 修复：将 UTC 时间转换为本地时区
  - 关联文件：`backup_service.py`

- **FTP 备份路径双斜杠**：备份路径出现 `/TAM//backup_xxx.zip`
  - 根因：`remote_path` 尾部有斜杠，拼接时产生双斜杠
  - 修复：使用 `remote_path.rstrip('/')` 去除尾部斜杠
  - 关联文件：`backup_service.py`

- **备份列表排序 TypeError**：本地备份 `created_at` 无时区，远端备份 `created_at` 有时区，无法比较
  - 修复：统一将 datetime 对象转换为无时区对象进行比较
  - 关联文件：`backup.py`

### 变更

- `emit_event` 重构为直接发射链路：业务模块 → NotificationService.emit → Redis Queue → Worker
- 通知服务改用模块级单例替代 ContextVar
- 升级规则 break 逻辑修正

***

## [3.8.0] - 2026-08-05

### 新增

- **缓存 TTL 可配置化**：IPGuard 和白名单缓存有效期从硬编码改为系统配置项
  - 新增配置项 `cache_ipguard_ttl`（默认 900s，范围 60-7200）
  - 新增配置项 `cache_whitelist_ttl`（默认 300s，范围 60-3600）
  - 系统设置 General 页面新增「缓存配置」分组
  - 关联文件：`system_config.py`、`config_service.py`、`compliance_service.py`、`GeneralSettings.tsx`、`useTerminalData.ts`、i18n

- **前端功能补全**：
  - 系统设置页面新增配置摘要展示
  - 通知日志页面新增重试功能
  - LDAP API 路径常量化

### 修复

- **Blacklist 重复记录问题**：修复黑名单管理显示数量与实际封堵数量不一致的 bug
  - 根因：数据库 `idx_blacklist_unique_active` 索引非唯一、并发竞态条件、重封堵逻辑缺失
  - 修复：索引改为唯一部分索引、代码添加 `IntegrityError` 捕获和回滚、重封堵判断改为基于 blacklist 活跃条目
  - 验证：blacklist_active 与 terminal_blocked 数量完全一致（200=200）
  - 关联文件：`blacklist.py`、`compliance_service.py`

- **BlacklistResponse Schema 修复**：`blocked_at` 字段改为可空，修复 NULL 记录导致的 500 错误
  - 关联文件：`terminal.py`

### 数据库变更

- 新建 `030_blacklist_unique_index.py` 迁移脚本
- 清理 2 条重复 blacklist 记录
- 创建唯一部分索引 `idx_blacklist_unique_active`

***

## [3.7.1] - 2026-08-04

### 修复

- **前端终端状态覆盖逻辑移除**：移除 Terminals.tsx 中对 compliance_status 和 firewall_tag 的二次覆盖逻辑
  - 背景：桥接虚拟机场景下，同 MAC 不同 IP 的终端（如宿主机 10.8.14.100 compliant + 虚拟机 10.8.14.32 non_compliant）因 MAC 在黑名单中导致宿主机被错误显示为 non_compliant
  - 方案：前端直接使用后端返回的 compliance_status，不再通过黑名单 MAC 匹配覆盖
  - 验证：1420 终端全量检查通过，20 个桥接场景终端状态正确
  - 关联文件：`frontend/src/pages/Terminals.tsx`

- **系统设置 General 页面 500 错误修复**：修复 `GET /api/v1/settings/` 和 `GET /api/v1/settings/list` 返回 500 错误
  - 背景：新增的 `compliance_confirm_threshold` 配置项 category='compliance' 不在 ConfigCategory 枚举中，is_readonly 为 NULL
  - 方案：新增 `COMPLIANCE = "compliance"` 枚举值、`ComplianceConfigResponse` schema、数据库字段修复
  - 验证：API 正常返回 200，包含 compliance 分类
  - 关联文件：`backend/app/schemas/system_config.py`、`backend/app/services/config_service.py`

### 验证结果

- 非合规未封堵终端数：6 → 0（重试机制修复）
- 合规重算状态变化：1349 终端全部 unchanged（确认机制生效）
- compliant→non_compliant 翻转：189 次/周期 → 0 次（重算路径）
- 非合规终端数 = 封堵终端数：200 = 200
- 前端桥接场景：宿主机 10.8.14.100 正确显示为 compliant
- 全量终端验证：1421 终端中 1402 条与数据库判定一致（98.7%）
- Settings API：200 OK，新增 compliance 分类

***

## [3.7.0] - 2026-08-03

### 新增

- **合规状态翻转确认机制**：compliant→non_compliant 状态变化不再立即生效，需连续 N 次同步确认后才正式变更
  - 背景：IPGuard OCULAR3 的 `AGENT.AGT_IP_MAC_STR` 字段存在动态波动（DHCP 续租、agent 重连等），导致合规数据瞬时变化引发"合规振荡"（189 次/周期的 compliant→non_compliant 翻转）
  - 方案：`recalculate_all_compliance` 中对 compliant/bypass→non_compliant 的翻转引入 `non_compliant_confirm_count` 计数器，达到配置阈值（默认 2 次）后才变更状态并触发封堵
  - 首次发现的新终端（unknown→non_compliant）仍立即封堵，不受影响
  - 新增配置项：`compliance_confirm_threshold`（默认 2，范围 1-10）
  - 新增数据库字段：`terminals.non_compliant_confirm_count`
  - 关联文件：`backend/app/services/compliance_service.py`、`backend/app/models/terminal.py`、`backend/alembic/versions/029_terminal_non_compliant_confirm_count.py`

- **封堵失败重试机制**：`scheduled_compliance_check` 调度器增加对 `non_compliant + unblocked` 终端的封堵重试
  - 背景：防火墙 API 调用失败后终端停留在 non_compliant+unblocked 状态，原有调度器只处理 unknown 终端，不会重试
  - 方案：每 300 秒扫描一次 non_compliant+unblocked 终端，重新调用防火墙封堵 API
  - 关联文件：`backend/app/main.py`

### 优化

- **IPGuard 缓存 TTL 修正**：缓存 TTL 从 600 秒调整为 900 秒（1.5 倍同步间隔），消除缓存过期与同步间隔之间的空窗期
  - 关联文件：`backend/app/services/compliance_service.py`

- **IPGuard 同步失败数据保护**：引入备份缓存机制
  - 同步成功时额外写入无 TTL 的备份缓存 `ipguard:backup:{tag}`
  - 同步失败且主缓存过期时，从备份缓存加载上次成功数据，避免空列表导致全部终端误判为 non_compliant
  - IPGuard 数据完全不可用时中止合规重算，保持终端原有状态
  - 关联文件：`backend/app/services/compliance_service.py`

### 验证结果

- 非合规未封堵终端数：6 → 0（重试机制修复）
- 合规重算状态变化：1349 终端全部 unchanged（确认机制生效）
- compliant→non_compliant 翻转：189 次/周期 → 0 次（重算路径）
- 非合规终端数 = 封堵终端数：是

***

## [3.6.18] - 2026-07-16

### 修复

- **防火墙封锁状态不一致**：修复终端在 Web 显示已封锁但防火墙上无数据的问题
  - 原因：合规自动封锁（auto_block_non_compliant）使用异步队列（fire-and-forget）调用防火墙 API，入队成功即更新数据库状态为 blocked，但实际防火墙操作在后台执行，失败时不会回滚
  - 修复：将 `auto_block_non_compliant`、`_block_on_firewall`、`_unblock_on_firewall` 全部改为同步调用防火墙 API，确认成功后再更新 Terminal 状态和创建 Blacklist 记录
  - 影响：Terminal.status 现在准确反映防火墙实际封锁状态，避免误报和状态反复横跳
  - 关联文件：`backend/app/services/compliance_service.py`

- **防火墙对账服务崩溃**：修复对账服务因缺少 `or_` 导入导致完全无法运行的问题
  - 原因：`firewall_reconciliation_service.py` 第 12 行 `from sqlalchemy import select, delete` 漏导 `or_`，第 153 行使用 `or_()` 时抛出 `NameError`
  - 修复：补充 `or_` 导入
  - 影响：对账服务恢复正常，能够自动检测和修正数据库与防火墙之间的状态不一致
  - 关联文件：`backend/app/services/firewall_reconciliation_service.py`

### 数据修复建议

- 升级后建议执行一次防火墙对账（Firewall Reconciliation），以修正历史数据中可能存在的不一致记录
- 对账 API：`POST /api/v1/system/firewall-reconciliation`

***

## [3.6.17] - 2026-07-16

### 修复

- **审计日志爆炸增长**：修复 ARP 采集服务重置终端 `compliance_status` 导致日志量异常问题
  - 原因：每次 ARP 采集更新已存在终端时，强制将 `compliance_status` 重置为 `"unknown"`，导致合规检查认为状态发生变化
  - 修复：移除 `arp_collector_service.py` 中 `_upsert_terminals` 对已存在终端的 `compliance_status` 和 `wl_match_type` 重置
  - 效果：日志量从 13万条/天降至正常水平，减少 99.2% 的无效日志
  - 关联文件：`backend/app/services/arp_collector_service.py`

- **审计日志筛选不匹配**：修复前端筛选下拉菜单选项与实际日志数据不匹配问题
  - 原因：前端 action 值与后端实际生成的值不一致（如 `add_whitelist` vs `whitelist_create`）
  - 修复：重写 `actionLabelKeys`、`ACTION_CATEGORIES`、`ACTION_CATEGORY_MAP`，确保与后端完全对齐
  - 关联文件：`frontend/src/pages/AuditLogs.tsx`

### 优化

- **审计日志 Action 命名统一**：统一为 `snake_case` 格式和 `<noun>_<verb>` 命名模式
  - 新增向后兼容映射，确保历史日志仍能正确显示和筛选（`block_ip`→`firewall_block`、`add_whitelist`→`whitelist_create` 等）
  - 新增 `firewall`（防火墙）和 `baseline`（合规基线）分类
  - 关联文件：`frontend/src/pages/AuditLogs.tsx`

### 国际化

- **审计日志翻译补全**：三语言（中/英/日）新增分类标签、动作标签、资源类型翻译
  - 关联文件：`frontend/src/i18n/locales/{zh,en,ja}.ts`

### 文档

- 更新 release-notes.md 添加 v3.6.18 发布记录
- 统一所有文档版本号至 v3.6.18

***

## \[3.6.13] - 2026-07-14

### 变更

- **移除手动封锁/解封功能**：系统核心业务逻辑闭环改为合规自动判断封锁和解封锁
  - 删除手动封锁 API 端点：`POST /terminals/block/{ip_address}`
  - 删除手动解封 API 端点：`POST /terminals/unblock/{ip_address}`
  - 删除黑名单手动添加端点：`POST /blacklist/`
  - 删除黑名单手动删除端点：`DELETE /blacklist/{identifier}`
  - 删除后端服务方法：`block_ip`, `unblock_ip`, `add_to_blacklist`, `delete_from_blacklist`

- **终端管理优化**：
  - 合规终端（compliant）无任何操作按钮
  - 白名单终端（bypass）无移出白名单操作，移除动作集中在白名单管理中
  - 仅不合规（non_compliant）和未知（unknown）终端保留加白操作

- **黑名单管理优化**：
  - 移除解封按钮和删除确认模态框
  - 移除状态标签页（Active/Unblocked），只显示当前被封锁的记录
  - 封锁和解封的追溯通过完整的审计日志查询

### 文档更新

- 更新业务工作流文档，移除手动封锁/解封流程章节
- 更新 API 文档，移除已删除的 API 端点
- 更新所有文档版本号至 v3.6.13

***

## [3.6.16] - 2026-07-16

### 修复

- **合规检查 Force Re-check 选项**：Run Compliance Check 按钮添加强制重新检查复选框
  - 原因：前端硬编码 `force: false`，只检查 unknown 终端，但 ARP 采集时已自动处理
  - 变更：添加 `forceCheck` state，传递到 API 请求
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

- **Auto Block 确认对话框优化**：用自定义 Modal 替换浏览器原生 window.confirm
  - 原因：`window.confirm` 与项目 UI 设计不一致
  - 变更：添加 `showAutoBlockModal` state，拆分为 `handleAutoBlockClick` 和 `handleAutoBlockConfirm`
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

- **Auto Block / Auto Unblock 提示优化**：0条操作时添加 toast.info 说明原因
  - 变更：Auto Block 返回0条时提示"所有不合规终端已封锁"
  - 变更：Auto Unblock 返回0解封时提示"被封锁终端均未变为合规状态"
  - 关联文件：`frontend/src/components/datasources/ComplianceBaselinesTab.tsx`

### 新增

- **后端 message 字段**：AutoBlockResult 和 AutoUnblockResult 添加 message 字段
  - 原因：后端已返回 message 但 schema 缺失字段
  - 变更：`auto_unblock_compliant` 方法返回 `message` 提示
  - 关联文件：`backend/app/schemas/data_source.py`、`backend/app/services/compliance_service.py`

- **i18n 翻译**：三语言添加4条合规相关翻译
  - `forceRecheck`、`autoBlockWarning`、`autoBlockNoAction`、`autoUnblockNoAction`
  - 关联文件：`frontend/src/i18n/locales/{zh,en,ja}.ts`

***

## [3.6.15] - 2026-07-16

### 修复

- **黑名单数据一致性修复**：修复黑名单管理页面与防火墙、Dashboard、终端管理统计数量不一致问题
  - `get_blacklist`、`get_blacklist_count`、`get_blacklist_stats` 方法添加过期时间过滤
  - 原因：黑名单管理页面未过滤已过期记录，导致显示数量偏多
  - 关联文件：`backend/app/services/terminal_service.py`

- **防火墙对账记录类型修复**：修复对账服务创建的记录被错误标记为手动封锁
  - `_create_db_entries` 方法中 `is_auto_blocked` 从 `False` 改为 `True`
  - `_get_db_active_blacklist` 方法添加过期时间过滤
  - 关联文件：`backend/app/services/firewall_reconciliation_service.py`

- **防火墙查询导入修复**：修复 `terminal_service.py` 中 `decrypt_config` 未导入导致的 NameError
  - 关联文件：`backend/app/services/terminal_service.py`

- **防火墙查询结果解析修复**：修复 `cli.py` 中防火墙查询结果解析逻辑
  - 原代码 `result.get("data", [])` 修正为 `result.get("data", {}).get("items", [])`
  - 关联文件：`backend/cli.py`

### 文档更新

- 更新 changelog.md 添加 v3.6.15 变更记录
- 更新 release-notes.md 添加 v3.6.15 发布记录
- 统一所有文档版本号至 v3.6.15

***

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

***

## \[Unreleased]

### 修复

- **数据库连接泄漏**：修复 `notification_logging.py` 中数据库会话未正确关闭导致的连接泄漏问题
  - 重构会话管理逻辑，使用 try/finally 确保会话正确释放
  - 优化连接池配置（pool\_size=30, max\_overflow=100, pool\_recycle=300）
- **邮件限流**：修复大量合规状态变化事件触发 SMTP 限流问题
  - 所有通知事件先经过 `NotificationAggregator` 聚合后再发送
  - 实现时间窗口聚合（5分钟），同类事件合并发送
- **防火墙并发限制**：修复合规计算时并发调用 Sangfor API 超过设备限制问题
  - 防火墙操作改为队列串行处理，使用信号量限制最大并发连接数为3
  - 实现指数退避重试机制

### 优化

- **合规计算分批处理**：将合规计算改为分批事务处理，每批100个终端，减少长事务风险
- **通知聚合器**：新增 `NotificationAggregator` 模块，实现事件收集、合并和异步发送

### 新增

- **备份管理功能**：实现完整的备份配置管理功能
  - 新增备份配置模型和数据库迁移
  - 实现备份服务 CRUD 操作
  - 添加备份管理 API 端点
  - 添加备份管理前端页面
- **防火墙对账服务**：新增防火墙状态对账服务
  - 实现本地黑名单与防火墙状态同步逻辑
  - 支持定期对账任务
- **终端管理优化**：增强终端管理功能
  - 优化终端 API 端点
  - 改进终端服务逻辑UI
  - 更新终端管理&#x20;

***

## \[3.6.10] - 2026-07-09

### 新增

- **定时备份白名单选项**：备份配置新增 `backup_whitelist` 字段，支持定时备份时选择是否包含白名单数据

### 修复

- **手动备份失败**：修复 `create_archive()` 方法签名参数不匹配问题
- **白名单备份失败**：修复 `NotificationRule` 模型字段映射错误（不存在的 `conditions` 字段）
- **i18n 翻译缺失**：完善中文、英文、日文翻译文件，添加备份选项相关翻译

### 优化

- **备份配置字段完善**：`BackupConfig`、API Schema、前端接口统一添加 `backup_whitelist` 字段支持

***

## \[3.6.9] - 2026-07-08

### 新增

- **数据导出功能**：终端管理、白名单管理、黑名单管理页面新增导出功能，支持全量导出和按筛选条件导出，后端新增 `GET /terminals/export`、`GET /whitelist/export`、`GET /blacklist/export` 端点

### 修复

- **通知渠道创建 500 错误**：修复 `notifications.py` 中 `channel.channel_type` 属性访问错误（数据库模型字段名为 `type`）
- **合规判断逻辑不一致**：ARP 采集和定时任务的合规检查路径与白名单变更触发的全量重算路径行为不一致，抽取 `_apply_compliance_result` 共享方法统一处理

### 优化

- **合规检查路径统一**：所有合规检查路径（ARP 采集、定时任务、白名单变更）统一使用 `_apply_compliance_result` 方法，确保以下行为一致：
  - 更新 compliance\_status 和 wl\_match\_type
  - 更新 comments（白名单备注）
  - 状态变更时触发事件通知
  - 自动封堵/解封逻辑
- **`batch_check_compliance`** **返回白名单备注**：新增 `wl_comments` 字段，支持下游调用方获取匹配的白名单备注信息

***

## \[3.6.8] - 2026-07-08

### 修复

- **数据导出功能**：前端数据导出仅支持导出当前页数据，改为调用后端 API 支持全量导出和筛选导出
- **通知渠道 500 错误**：创建通知渠道时报 500 内部错误但实际创建成功的问题

***

## \[3.6.7] - 2026-07-08

### 新增

- **版本一致性检查命令**：`./manage.sh version check`，检查所有版本号文件（VERSION、package.json、.env、.env.example、docker-compose.yml、manage.sh、vite.config.ts）是否一致
- **一键版本升级命令**：`./manage.sh version bump <ver>`，自动更新所有版本号文件到指定版本，避免手动修改遗漏

### 优化

- **版本号 fallback 统一**：所有 fallback 版本号统一为 3.6.6，确保单一版本源失效时仍显示正确版本

***

## \[3.6.6] - 2026-07-08

### 新增

- **Operation Source 子菜单**：在数据源管理页面新增 Operation Source 标签页，独立管理 Sangfor 防火墙类型数据源，位于 Data Sources 和 Bindings 之间
- **黑名单服务端统计接口**：新增 `GET /api/v1/blacklist/stats` 接口，提供全局统计数据（活跃/自动封锁/手动封锁/过期/活跃封锁数），解决前端统计基于当前页数据不准确的问题
- **FTP 远程备份管理**：备份列表/下载/删除支持远程存储（FTP/SFTP），备份列表显示存储位置标签
- **终端表 updated\_at 字段**：新增 `updated_at` 字段区分创建时间和更新时间，ARP 采集仅更新 `updated_at` 不覆盖 `timestamp`

### 修复

- **黑名单 Unblocked 标签筛选不出数据**：统一筛选逻辑，active 同时检查 `auto_unblocked=False` 和 `unblocked_at IS NULL`，unblocked 检查 `auto_unblocked=True OR unblocked_at IS NOT NULL`；通过数据迁移 026 补全历史记录的 `unblocked_at` 字段
- **角色名称修改不生效**：后端 `RoleUpdate` schema 添加 `name` 字段，`update_role` 支持自定义角色重命名并保护内置角色
- **终端 timestamp 被覆盖**：ARP 采集更新终端时错误更新 `timestamp`（创建时间），现仅更新 `updated_at`
- **白名单备注不一致**：白名单备注更新逻辑优化，支持备注变更时替换旧备注；白名单删除时清除关联终端备注（支持 CIDR 和 IP 范围匹配）
- **Sangfor 测试连接 Last Test 不更新**：测试连接成功后使用直接 UPDATE 语句更新 `last_sync_at`（绕过 ORM expunge 问题）
- **导航栏菜单同时选中**：父级菜单高亮基于路由匹配而非展开状态
- **自动解封未设置 unblocked\_at**：自动解封逻辑中 3 处补全 `unblocked_at = datetime.now(UTC)`
- **通知时间戳时区不一致**：所有通知渠道统一使用 `format_timestamp()` 转换为 Asia/Shanghai 时区
- **前端时间戳格式不一致**：统一 `formatDate` 为 `formatDateTime`，支持多语言和时区
- **翻译键命名错误**：白名单 `identifier` 重命名为 `macAddress`/`ipAddress`，移除 `ipPattern`
- **备份计划预设未国际化**：预设选项改用 i18n 翻译键

### 优化

- **黑名单 Unblocked 标签显示一致性**：UI 标签显示条件从 `auto_unblocked` 改为 `auto_unblocked || unblocked_at`，与后端筛选逻辑一致
- **Sangfor 数据源独立管理**：DataSourcesTab 过滤 sangfor 类型，由 OperationSourceTab 专门管理

***

## \[3.6.5] - 2026-07-07

### 新增

- **安全事件触发点**：在 `auth.py` 中添加 `PASSWORD_CHANGED`、`USER_CREATED`、`USER_DELETED`、`USER_UPDATED` 事件触发点
- **合规告警触发点**：在 `compliance_service.py` 中添加 `BLOCK_THRESHOLD_EXCEEDED`、`POLICY_VIOLATION`、`TERMINAL_COMPLIANT`、`TERMINAL_NON_COMPLIANT` 事件触发点
- **管理事件触发点**：在 `roles.py`、`settings.py`、`data_source_service.py`、`arp_collector_service.py` 中添加角色变更、配置变更、数据源变更、终端事件触发点
- **事件发射器增强**：在 `event_emitter.py` 中新增多个事件触发函数
- **业务流程文档**：创建 `business-workflow.md`，详细说明合规判定和封锁/解封流程

### 修复

- **黑名单软删除**：在 `blacklist.py` 模型中添加 `unblocked_at` 和 `unblocked_by` 字段，实现软删除
- **cleanup\_expired\_blacklist bug**：修复 `terminal_service.py` 中 datetime 变量作用域问题
- **emit\_terminal\_non\_compliant 参数错误**：修复调用时传入错误参数的问题

### 优化

- **API文档补充**：更新 `api.md`，补充通知统计、日志、重试、归档和备份FTP配置等API端点说明
- **日志指南增强**：更新 `logging-guide.md`，新增日志监控与告警、紧急处理流程等章节

***

## \[3.6.3] - 2026-07-07

### 新增

- **FTP备份支持**：新增 FTP 存储类型，支持普通 FTP 和 FTPS（SSL）两种模式，API `/backup/test` 端点支持 FTP 连接测试
- **备份配置持久化**：创建 `backup_config` 数据库表，实现配置持久化，刷新页面后配置保留
- **定时任务预设选择器**：添加预设选项（每天凌晨2点/3点、每周日凌晨2点、自定义），选择自定义时才显示 crontab 输入栏

### 修复

- **FTP连接测试异常**：修复 `ftplib.FTP.__init__()` 不支持 `port` 参数的问题，改为 `connect(host, port)` 方法
- **登录页页脚换行**：页脚区域移出宽度限制容器，内容横向自适应扩展，一行显示不换行
- **CRON格式校验**：添加正则校验，无效格式显示错误提示

### 优化

- **版本号统一管理**：创建 `VERSION` 文件作为单一版本源，所有需要版本号的地方（manage.sh、config.py、vite.config.ts、.env）统一引用

***

## \[3.6.2] - 2026-07-06

### 新增

- **通知日志管理**：支持日志归档、批量归档（30天前）、清理（90天前归档日志）、单条删除操作
- **模板/规则优先级**：支持通过优先级字段控制匹配顺序（数值越小优先级越高）
- **模板/规则通用兜底**：支持通配符 `*` 匹配所有事件类型，精确匹配优先于通配符匹配

### 修复

- **监控统计内部服务错误**：修复SQL函数兼容性问题，优化异常处理，添加详细错误日志
- **Channel开关颜色显示**：启用状态改为绿色，关闭状态改为灰色，更加直观

***

## \[3.6.1] - 2026-07-06

### 新增

- **事件发射器扩展**：新增6个安全事件（用户删除/更新、密码修改、角色变更、登录锁定、密码重置请求），支持实时通知告警
- **令牌过期主动检测**：前端新增 `useTokenExpiration` hook，支持JWT解码、过期时间存储、主动式令牌刷新和自动登出
- **邮箱可用性检查**：新增 `GET /auth/users/email-available` API，支持用户创建/编辑时实时检查邮箱是否被占用
- **邮箱重复确认机制**：支持用户确认后使用重复邮箱（`force_email` 参数），平衡安全性和灵活性

### 修复

- **品牌配置同步**：修复登录页面ICP备案号、footer text、heading等品牌配置字段未从后端动态加载的问题
- **密码复杂度校验**：修复前端正则禁止特殊字符的问题，统一前后端规则（大写+小写+数字，允许特殊字符）
- **密码重置流程**：修复密码重置成功后直接跳转无提示的问题，添加成功toast提示和延迟跳转；修复表单状态同步问题
- **通知日志时区错误**：修复 `now()` 返回带时区信息导致写入 `TIMESTAMP WITHOUT TIME ZONE` 字段失败的问题
- **API数据源测试认证**：修复ARP API类型数据源测试连接时未处理自定义Header认证的问题
- **消息通知时间戳时区**：统一后端时间戳生成和前端时间格式化，使用Asia/Shanghai时区

### 优化

- **用户状态显示**：用户管理页面区分显示Active/Locked/Disabled三种状态（Locked从Redis获取）
- **忘记密码显示逻辑**：仅在密码输入错误次数触发安全校验后显示忘记密码链接
- **密码重置邮箱传递**：密码重置时自动传递用户名到重置页面，无需用户重复输入

***

## \[3.6.0] - 2026-07-03

### 新增

- **消息模板系统（P1）**：支持基于 Jinja2 模板引擎的消息自定义，每个事件-渠道组合可配置独立模板，提供模板预览功能
- **国内 IM 应用模式（P1）**：飞书、钉钉、企业微信支持 Webhook 模式和应用模式双模式切换，应用模式接入 token 缓存（7000s TTL）到 Redis
- **系统邮件配置页面（P1）**：独立的 SMTP 邮件配置页面，支持配置测试与保存，邮件配置加密存储
- **通知规则系统（P2）**：支持消息抑制（同一事件窗口内去重）、消息聚合（计数统计）、消息升级（达到阈值后 severity 升级），升级通知自动绕过抑制规则
- **通知规则管理页面（P2）**：规则列表/过滤/创建/编辑/删除，含规则配置帮助侧栏
- **通知模板管理页面（P1）**：模板列表/过滤/创建/编辑/删除/预览，含 Jinja2 变量参考侧栏
- **异步通知队列（P3）**：基于 Redis List 的异步任务队列，事件发布采用 fire-and-forget 模式，不阻塞请求
- **重试机制（P3）**：失败通知自动指数退避重试（默认 3 次，首重试 10s），使用 Redis ZSet 管理重试调度
- **监控统计面板（P3）**：8 个核心统计卡片（总发送、成功数、失败数、成功率、待重试、平均延迟、渠道数、规则数），各渠道成功率进度条，30 秒自动刷新
- **手动重试功能（P3）**：支持单条失败通知重发和批量重发所有失败通知
- **3 个新数据库迁移**：017\_notification\_templates、018\_notification\_rules、019\_notification\_async\_retry

### 修复

- **通知统计接口 500 错误**：修复 `notification_service.py` 中 `Integer` 未导入导致的 `NameError`
- **通知模块权限码不一致**：将 `notification:manage`（9 处）修正为 `notification:write`，与数据库权限定义一致
- **备份模块权限码格式错误**：将 `system.manage`（6 处，点号格式）修正为 `backup:write`，使用正确的冒号格式并细化到备份模块
- **认证提供者模块权限码缺失**：将 `auth.manage`（4 处）修正为 `settings:write`，使用系统已有权限码
- **Nginx 重复 Cache-Control 头**：移除 `expires -1` 指令，消除与 `add_header Cache-Control` 的冲突，确保 index.html 正确禁用缓存
- **前端邮件设置入口缺失**：在侧边栏导航中添加邮件设置入口，完善图标映射和国际化标签

### 优化

- **通知服务架构优化**：采用 request-scoped + singleton 双模式设计，API 端点与后台 worker 复用同一服务类
- **PostgreSQL 部分唯一索引**：notification\_rules 表使用部分唯一索引解决 NULL channel\_name 唯一性约束问题
- **升级通知绕过抑制**：escalated 事件自动设置 `bypass_suppression` 标志，确保升级后的 severity 总能送达
- **前端国际化完善**：补全 emailSettings、notificationTemplates、notificationRules、notificationMonitor 四个命名空间的中/英翻译（各 45+ 键）

***

## \[3.5.1] - 2026-07-03

### 修复

- **LDAP用户Profile页面优化**：LDAP用户仅显示从LDAP获取的信息（用户名、邮箱、角色、状态），隐藏邮箱更新和密码修改功能
- **Modal组件交互优化**：Import LDAP Users等模态框点击外部遮罩层不再关闭，仅通过关闭按钮或ESC键关闭
- **LDAP认证编辑体验优化**：编辑LDAP认证提供者时Bind Password变为可选项，留空则保持原有密码，无需每次重新输入
- **认证提供者类型精简**：移除认证提供者管理页面中无实际意义的Local类型选项（Local认证为系统内置，无需用户配置）
- **Profile页面翻译修复**：修复LDAP用户Profile页面邮箱标签显示为`profile.email`的翻译键名错误

***

## \[3.5.0] - 2026-07-01

### 新增

- **事件通知服务**：事件总线架构、多通知渠道（邮件/钉钉/企业微信/Webhook）、通知日志、测试连接
- **认证提供者系统**：插件化认证架构，支持本地认证、LDAP认证（Active Directory/OpenLDAP）、OAuth认证预留
- **SFTP备份服务**：数据库备份、配置文件备份、SFTP远程上传、备份轮转、校验和验证
- **系统设置前端页面**：统一系统设置导航入口，包含通用设置、认证提供者、备份配置、通知管理、用户管理、角色管理
- **前端导航重构**：嵌套导航结构，创建"系统设置"分组，整合配置管理页面

### 修复

- **路径遍历漏洞**：backup.py download/restore/delete端点添加路径检查和文件名净化
- **LDAP DN注入**：ldap\_provider.py添加用户名验证和特殊字符转义函数
- **2FA验证码暴力破解防护**：email\_service.py添加验证码最大尝试次数限制（默认5次）
- **敏感信息备份泄露**：backup\_service.py移除.env文件备份，只备份docker-compose.yml和manage.sh
- **FTP支持移除**：删除FTP上传代码，强制使用SFTP安全传输
- **SFTP主机密钥验证**：添加AutoAddPolicy主机密钥验证策略

### 优化

- **N+1查询优化**：roles.py使用JOIN一次性获取所有角色权限和用户计数
- **异步性能优化**：backup\_service.py使用asyncio.to\_thread包装同步文件操作
- **通知模块权限控制**：notifications.py添加notification:read/manage权限检查
- **Nginx限流调整**：API限流从60r/m提升至300r/m，认证限流从10r/m提升至30r/m
- **前端国际化完善**：补全备份、认证、通知模块的中/英/日翻译

***

## \[3.4.0] - 2026-06-22

### 新增

- 系统版本和环境信息展示：前端页脚和 Dashboard System Status 页面显示版本号和部署模式
- 角色权限 i18n 完整实现：5个内置角色和29个权限的三语言翻译（中文/英文/日语）
- 多环境配置分离：支持双层 env\_file（.env + .env.{ENVIRONMENT}），开发/生产环境独立配置
- Nginx 镜像版本锁定：docker-compose.yml 锁定 nginx:1.27-alpine

### 修复

- 白名单删除 404 错误：修复删除端点路由匹配问题，支持 MAC-only、IP-only、复合条目删除
- 白名单删除 MAC 匹配错误：使用 mac\_address\_normalized 字段查询，确保标准化格式匹配
- 超管角色初始化错误：修复系统初始化时 admin 用户未正确关联 superadmin 角色的问题
- 权限列 i18n 命名冲突：修复 roles.permissions 键同时定义为字符串和对象的问题

***

## \[3.3.1] - 2026-06-17

### Fixed

- 黑名单管理页面默认不再显示已自动解封的历史记录
- 后端 `GET /blacklist/` 查询默认过滤 `auto_unblocked=True` 的记录
- 新增 `status` 查询参数支持查看已解封记录（active/unblocked/all）
- 前端黑名单页面添加 Tab 切换（活跃封堵/已解封/全部）
- 已解封记录不再显示"解封"按钮，行样式降低透明度区分

***

## \[3.3.0] - 2026-06-17

### 新增

- 审计日志 `resource_name` 字段：存储人类可读资源名称（用户名、数据源名称、IP 地址等），替代无意义的 #id 显示
- 审计日志 keyset 分页：`/api/v1/logs/search` 新增 cursor 参数，支持深分页高性能查询
- Docker 安全加固：docker-compose.prod.yml 实现容器安全最佳实践（no-new-privileges、cap\_drop:ALL、read\_only）
- Docker 健康检查：所有服务添加 healthcheck 配置，支持容器编排健康探测
- Sangfor API 指数退避重试：`_request_with_backoff` 方法，最多 3 次重试，等待时间指数增长（1s→2s→4s，上限 10s）
- 核心服务单元测试：compliance\_service 22 个测试用例（状态转换、自动封堵/解封、过期清理、白名单匹配、合规重算）
- 灾难恢复计划：docs/disaster-recovery.md（故障分级 P0-P3、各组件恢复步骤、RPO/RTO 目标）
- 运维操作手册：docs/operations-runbook.md（日常巡检、故障排查、定时任务管理、升级回滚）
- 部署模式统一：`deploy --dev` 替代 `deploy --demo`，自动设置 ENVIRONMENT 变量
- 开发环境 Nginx 配置：tam.dev.conf（HTTP 直连 + 放宽限流 120r/m+30r/m）
- docker-compose.dev.yml：开发环境 override 文件，自动加载 tam.dev.conf
- Mock 数据业务对齐：28 种 verb\_resource action、JSON details、resource\_name、firewall\_tag 绑定关系一致

### 改进

- 审计日志 action 命名统一为 verb\_resource 格式：block\_ip→block\_terminal, unblock\_ip→unblock\_terminal, auto\_block→auto\_block\_terminal, auto\_unblock→auto\_unblock\_terminal, cleanup\_expired→cleanup\_expired\_blacklist, role\_change→change\_role
- N+1 查询优化：cleanup\_expired\_blacklist 批量预加载 Terminal + 批量检查活跃 Blacklist + 缓存 SangforService；batch\_check\_compliance 一次性加载白名单和 IPGuard 数据
- Nginx 生产限速调整：api\_limit 30r/m→60r/m，auth\_limit 5r/m→10r/m，避免前端正常操作触发限速
- 生产环境禁止 mock generate：`cmd_mock()` 检测 ENVIRONMENT=production 时拒绝执行
- Mock 数据 blocked\_by 修正：自动封堵 blocked\_by="system"，手动封堵使用操作者用户名
- 从 git 移除 sangfor\_api 文件夹和 todos.md：仅保留本地，不再追踪到仓库
- 终端封堵绑定验证：封堵终端前强制检查绑定关系，无绑定时显示防火墙选择器和无绑定错误提示（Terminals.tsx）
- 数据源标签页绑定状态列：数据源列表新增绑定状态列，已禁用 ARP 数据源显示"合规状态已冻结"（DataSourcesTab.tsx）
- 启用无绑定数据源确认对话框：启用未绑定防火墙的 ARP 数据源时弹出确认提示（DataSourcesTab.tsx）
- 绑定关系下拉框包含已禁用数据源：ARP 和防火墙数据源下拉框现在包含已禁用的数据源，以 `[已禁用]` 后缀标识（BindingsTab.tsx）
- ARP 数据源禁用触发合规重置：禁用 ARP 数据源时自动重置关联终端 `compliance_status` 为 `unknown`（data\_sources.py、terminal\_service.py）
- i18n 三语言补全：新增绑定状态、合规冻结、无绑定封堵提示等翻译键（zh.ts、en.ts、ja.ts）
- 两阶段删除机制：数据源、绑定关系、合规基准删除前提供影响预览 API（`POST /{id}/delete-preview`）
- 安全删除：自动解封终端、清理黑名单记录、清理 Redis 缓存、触发合规重算
- 前端 DeletePreviewModal 组件：展示影响范围、操作清单、受影响资源统计
- 数据源 tag 和合规基准 tag 修改禁止（tag 为系统全局标识符，修改会导致关联数据断裂）
- RBAC 角色权限控制：4张核心表（roles/permissions/user\_roles/role\_permissions），5个预设角色（superadmin/admin/operator/auditor/viewer），29个权限码覆盖10个功能模块
- `require_permission` 权限检查工厂函数：FastAPI 依赖注入 + Redis 缓存（TTL 300s）+ superuser 短路
- 角色 CRUD API：7个端点（列表/详情/创建/编辑/删除/权限列表/角色用户列表）
- 用户角色分配 API：`PUT /roles/users/{id}/roles`（单角色分配）
- 前端 `usePermission` Hook：4个权限判断方法（hasPermission/hasAnyPermission/hasAllPermissions/hasRole）
- 前端 `ProtectedRoute` 路由守卫：支持 `requiredPermission` / `requiredAnyPermissions`
- 前端侧边栏导航过滤：根据 `requiredPermission` 过滤导航项
- 角色管理页面：角色列表、创建/编辑弹窗、权限按模块分组、删除确认
- 超管隔离机制：非超管不可见/不可管理超管用户，超管只能自己管理自己
- 初始管理员4层保护：不可删除/降级/停用/角色变更
- RBAC 后端测试：11个测试用例（权限缓存、权限检查、缓存失效）
- RBAC 前端测试：20个 usePermission Hook 测试用例
- RBAC 文档：`docs/RBAC.md`（从"角色管理与用户访问控制说明文档"重命名）
- 数据源删除操作从直接删除改为安全删除（先自动善后再删除）
- 绑定关系删除操作从直接删除改为安全删除（先解封终端再删除绑定）
- 合规基准删除操作增加 Redis 缓存清理和合规重算步骤
- Sangfor 数据源移除"同步"按钮：Sangfor 为推送型防火墙，无数据同步语义，前端按类型条件隐藏同步按钮，后端同步接口对 sangfor 类型返回"不适用"提示
- 合规重算（`recalculate_all_compliance`）自动封堵/解封改为多防火墙路由，与 `auto_block_non_compliant` 行为一致
- 合规重算创建的 Blacklist 记录补全 `expires_at` 和 `blocked_by` 字段
- 过期黑名单清理 Sangfor 解封失败时保留 Blacklist 记录并延长重试，避免本地与防火墙状态不一致
- 过期清理完成后触发合规重算，确保不合规终端及时重新封堵
- `unblock_ip` 增加 `mac_address` 参数，支持按 MAC 精确解封
- `auto_unblock_compliant` / `cleanup_expired_blacklist` Terminal 查询增加 MAC 维度匹配
- 自动封堵/解封/合规重算操作补全审计日志
- `block_ip` / `unblock_ip` 审计日志补充客户端 IP 地址
- 单角色模型：`role_ids: list[int]` → `role_id: int`，前端 checkbox 多选 → select 单选下拉
- 搜索防抖统一为 500ms（Terminals/Whitelist/Blacklist/AuditLogs），`keepPreviousData` 防搜索闪屏
- Redis 客户端添加超时配置（`socket_timeout`/`socket_connect_timeout`），防止无限阻塞
- API 速率限制从 60→120 次/分钟，认证限制从 5→10 次/分钟
- i18n 三语言补全：`superadminRoleFixed`/`selectRole` 等 RBAC 相关 key
- 9个后端端点文件从 `get_current_user` 替换为 `require_permission`，实现真正的 RBAC 权限校验

### 修复

- 修复 compliance\_service.py 导入错误（`app.models.audit_log` → `app.models.log`）导致后端启动失败
- 搜索返回空结果（Whitelist/Blacklist/AuditLogs）：`_escape_like` 对已包裹 `%` 的字符串转义导致 LIKE 模式错误
- AuditLog 搜索缺少 action 字段：搜索只覆盖 ip\_address/username/details
- MAC 搜索从前缀匹配改为包含匹配：`ilike(f"{value}%")` → `ilike(f"%{value}%")`
- API 全局阻塞（30s+）：paramiko SSH 同步操作阻塞 asyncio 事件循环，改用 `asyncio.to_thread()`
- 307 重定向 + CSP 错误：前端 API 路径带尾部斜杠，后端路由不带
- 超管角色可被分配给其他用户：创建/编辑用户时过滤 superadmin 角色
- 超管编辑自己时仍显示角色修改选项：超管或自己编辑时隐藏角色下拉框，显示只读文本
- Users 搜索框闪屏/失焦：添加 `keepPreviousData` + `useDebounce(500ms)`

### 修正

- 用户使用手册（user-guide.md）修正与实际系统功能不一致的描述：仪表板快捷操作（4 个非 5 个）、终端封堵不支持批量选择、终端详情字段修正、黑名单详情移除不存在的审计日志关联、合规基准页面为标签页非独立页面、系统设置无前端管理界面（仅 API）、Logo 不支持动态上传、密码策略为硬编码不可配置、移除不存在的 SSO 和并发会话控制
- 快速上手指南（quick-start-guide.md）修正终端封堵操作描述（不支持批量勾选）

***

## \[3.2.0] - 2026-06-10

### 新增

- Request-ID 链路追踪：新增 `RequestIDMiddleware` + `ContextVar`，每个 HTTP 请求自动分配 12 位 hex request\_id（优先读取客户端 `X-Request-ID` 请求头），响应头返回 `X-Request-ID`，日志格式自动注入 request\_id 字段
- 时区全局控制：`config.py` 新增 `TZ` 配置项（默认 `Asia/Shanghai`），`docker-compose.yml` 5 个服务统一添加 `TZ` 环境变量，PostgreSQL 添加 `log_timezone`/`timezone` 参数，后端启动时调用 `time.tzset()` 使 loguru `ZZ` 显示正确时区偏移
- 前端日志本地时区：`logger.ts` 的 `formatTimestamp()` 从 UTC ISO 格式（`Z` 后缀）改为本地时区+偏移量格式（如 `+08:00`），日志时间与用户本地时间一致

### 改进

- 日志格式函数化：`logging_config.py` 从静态 `LOG_FORMAT` 字符串改为 `_log_format()` 动态函数，运行时自动从 ContextVar 注入 request\_id，非请求上下文显示 `-`
- 请求日志增强：`RequestLoggingMiddleware` 日志消息增加 `req_id=` 字段，与格式字段中的 request\_id 一致
- Docker 安全加固注释化：`security_opt`/`cap_drop`/`read_only` 等生产加固项改为注释（标注 `Production hardening`），开发环境直接运行，生产环境取消注释即可启用
- 日志文档补全：`logging-guide.md` 新增 7 个章节（文档版本历史、日志监控与告警、紧急处理流程、性能影响说明、日志分析常用命令、日志配置变更指南、Request-ID 链路追踪）+ 3 项修正（审计归档 cron 示例、前端日志渐进式接入标注、Request-ID 与 error\_id 关联说明）

***

## \[3.1.0] - 2026-06-09

### 新增

- Redis fail-open 降级策略：`security.py` 中 10 个 Redis 交互函数统一添加 try/except 异常处理，Redis 不可用时按策略降级（黑名单放行、版本号返回 0、登录防护放行等），避免 Redis 故障导致服务不可用
- MAC 地址标准化列：`terminals`/`whitelist`/`blacklist` 三张表新增 `mac_address_normalized` 列（VARCHAR(12)，去除分隔符的大写 MAC），Alembic 005 迁移脚本含数据回填和索引创建，6 处 MAC 搜索从 `func.replace()` 变换改为标准化列查询，4 处 MAC 写入点自动填充标准化列
- 全局异常处理中间件：新增 `error_handler.py`，注册 3 个异常处理器（HTTPException 透传、RequestValidationError 保留 422 格式、未捕获异常返回 500 + error\_id + 日志），统一错误响应格式
- CI/CD 流水线：新增 `.github/workflows/ci.yml`（6 个 Job：lint-backend/test-backend/lint-frontend/test-frontend/build-backend/build-frontend），`backend/pyproject.toml`（ruff 配置），`frontend/.eslintrc.json`
- 后端测试基础设施：重写 `conftest.py`（mock\_redis fixture + 内存模拟 Redis），新增 `test_security.py`（4 个测试类 19 用例）、`test_terminals.py`（2 个测试类 10 用例）、`test_whitelist.py`（2 个测试类 3 用例）、`test_blacklist.py`（2 个测试类 2 用例），修复 `test_app.py`/`test_auth.py`/`test_core.py` 与代码变更同步
- 前端测试基础设施：新增 `vitest.config.ts`、`src/test/setup.ts`、3 个测试文件（`utils.test.ts` 42 用例、`theme.test.ts` 8 用例、`auth.test.ts` 8 用例），共 58 个测试用例
- LICENSE 文件：项目根目录新增 MIT License 文件
- manage.sh `cmd_restore` Redis RDB 恢复：恢复数据库时同步恢复 Redis RDB 文件

### 改进

- docker-compose.yml：`postgres` 和 `redis` 服务添加 `restart: unless-stopped`，容器异常退出后自动重启
- docker-compose.yml：5 个服务统一添加 `cap_drop: [ALL]`，`nginx` 添加 `cap_add: [NET_BIND_SERVICE]`（绑定低位端口），容器安全加固
- 评估文档综合评分从 8.6 提升至 8.8（安全 8.5→9.0，鲁棒性 8.5→9.0）

***

## \[3.0.0] - 2026-06-09

### 安全修复（Critical）

- 服务端验证码机制：新增 `GET /auth/captcha` 端点生成算术验证码，答案存入 Redis（5 分钟 TTL），登录时校验 captcha\_id + 答案，前端移除本地验证码生成和校验逻辑
- 加密密钥分离：新增 `ENCRYPTION_KEY` 配置字段，生产环境启动时强制校验（未设置或与 SECRET\_KEY 相同则拒绝启动），开发环境回退到 SECRET\_KEY 并输出警告日志
- 移除不安全默认密码：docker-compose.yml 移除 `DB_PASSWORD:-password`、`REDIS_PASSWORD:-redis_password`、`SECRET_KEY:-your-secret-key-change-in-production` 等弱默认值，改用 `:?` 必填语法；manage.sh 新增 `_check_required_env` 函数检查必需环境变量

### 安全修复（High）

- 移除 `/auth/login-status` 公开端点：防止未认证用户枚举有效用户名
- 移除登录响应头信息泄露：删除 `X-Captcha-Required`、`X-Account-Locked`、`X-Lock-Remaining` 响应头，改为在错误响应 JSON detail 中返回 `captcha_required`/`locked`/`lock_remaining` 字段
- LIKE 通配符注入防护：新增 `_escape_like()` 工具函数，21 处 ilike 查询统一转义 `%` 和 `_` 通配符
- Token 版本号机制：JWT payload 新增 `ver` 字段，密码变更/重置时递增用户 Token 版本号，旧 Token 自动失效
- terminals 表联合唯一约束：新增 `(ip_address, mac_address)` 联合唯一约束 `uq_terminal_ip_mac`，Alembic 004 迁移脚本含去重逻辑
- `_auto_block_task` 会话生命周期修复：改用 `async_session_factory()` 创建独立数据库会话，含 commit/rollback

### 安全修复（Medium）

- JWT Token 类型区分：access token 添加 `"type": "access"` 字段，refresh token 添加 `"type": "refresh"` 字段，refresh 端点验证 Token 类型
- 上传文件安全加固：新增 `ALLOWED_EXTENSIONS` 扩展名白名单（.jpg/.jpeg/.png/.gif/.ico），移除 SVG 支持（XSS 风险），双重校验 content\_type + 扩展名，文件名 UUID 重命名
- /uploads/ 访问控制：Nginx 添加 Referer 检查，恶意来源返回 403
- 审计日志导出权限：导出端点从 `get_current_user` 改为 `get_current_active_superuser`，仅超管可导出
- Redis 密码安全：manage.sh 22 处 `redis-cli -a` 改为 `REDISCLI_AUTH` 环境变量，密码不再暴露在进程列表
- CORS 安全校验：`allow_origins=["*"]` 时自动降级 `allow_credentials=False`

### 改进

- Alembic env.py 修复 asyncpg 驱动兼容性，迁移不再依赖 psycopg2
- 修复伪测试：`TestSecretKeyValidation` 和 `TestLoginSecurity` 重写为有效测试
- 新增 `_escape_like` 和 `token_version` 单元测试
- 修复 `test_login_wrong_password` 断言适配结构化 detail 响应

***

## \[2.5.0] - 2026-06-09

### 新增

- i18n 国际化：i18next + react-i18next + i18next-browser-languagedetector，支持中文(zh)/英文(en)/日语(ja)三种语言，自动检测浏览器语言，手动切换（HeaderControls Globe 下拉菜单），语言持久化到 localStorage，14 个页面/组件全部 i18n 替换，翻译文件 en.ts/zh.ts/ja.ts
- HeaderControls 组件：新增 `frontend/src/components/HeaderControls.tsx`，页面顶部右上角（登录页和登录后均可见），主题切换浅色/深色/跟随系统三选项并列，语言选择 Globe 图标下拉菜单
- Layout 顶栏：内容区顶部新增一行顶栏，右侧显示 HeaderControls
- 审计日志前端分类过滤：8 类操作分类过滤（认证/终端/白名单/黑名单/数据源/用户/配置/系统），彩色 badge 标识，resource 展示优化，details JSON 解析展示
- MAC 地址格式无关搜索：后端 whitelist/blacklist 搜索使用 `func.replace` 去除 MAC 分隔符后 ILIKE 匹配，前端 `keepPreviousData` 防搜索闪烁

### 改进

- 审计日志 action 统一命名：`block_ip` → `block_terminal` 等规范化，启动时自动迁移旧值
- 审计日志 details 改为 JSON 格式，补充 login/logout/数据源/用户管理/配置变更审计记录
- 审计日志新增 `log_action` 公共函数 + `ip_address` 字段
- Sidebar 简化：移除主题和语言切换按钮（移至 HeaderControls），只保留 Profile 和 Logout
- 品牌名称替换：Terminal Access Platform → Terminal Access Manager，代码 19 处 + package.json + 后端启动时自动迁移数据库
- 前端请求超时和可靠性增强：`initializeAuth` timeout 10s、refresh token 传递统一为 body、排队请求 `_retry` 防循环、React Query 401 不重试、`api.ts` refresh timeout 10s、sonner 动态 import `.catch()`

### 修复

- 登录深色主题适配：背景从 `branding.login.background.gradientClass` 改为 `bg-background` 语义化颜色，锁定警告区/错误提示区/验证码区/输入框全部添加 `dark:` 变体
- 页面闪烁修复：Suspense 移到 Layout Outlet 外层、QueryClient `staleTime` 30s、Sidebar hover 预加载页面组件
- 搜索闪烁修复：前端使用 `keepPreviousData` 防止搜索时页面闪烁

***

## \[2.4.0] - 2026-06-09

### 新增

- 搜索优化：4个搜索API返回 `PaginatedResponse`（含 items/total/skip/limit），支持真正的服务端分页
- Terminals 搜索改为 ILIKE 模糊搜索 + OR 逻辑（IP 或 MAC 任一匹配即可）
- Terminals 搜索新增 `compliance_status` 过滤参数
- 前端4个页面搜索输入框添加 300ms debounce，减少无效 API 请求
- 前端4个页面实现服务端分页，支持浏览全部数据
- 数据库索引优化：whitelist.created\_at、blacklist.blocked\_at/expires\_at、audit\_logs.ip\_address
- 数据库迁移脚本 003\_search\_indexes.py
- 认证状态恢复机制：`initializeAuth()` 在应用启动时从 sessionStorage 恢复认证状态
- 401 拦截器并发控制：多个 401 请求只触发一次 token 刷新，排队的请求用新 token 重发
- 会话过期提示：token 刷新失败时 toast 提示"Session expired"

### 改进

- 移除 passlib 依赖，直接使用 bcrypt 库，彻底解决 bcrypt 版本兼容性警告
- Sidebar Logo 区域固定高度（h-10），折叠/展开时不再位置跳动
- health check 中 frontend 容器 exited(0) 视为正常（构建完成），不再误报 ERROR

### 修复

- 修复会话超时后不会自动退出登录的问题
- 修复页面刷新后认证状态丢失的问题
- 修复 Terminals 搜索使用精确匹配导致部分输入无法搜到结果的问题
- 修复前端分页与后端分页矛盾导致只能看到前50条数据的问题
- 修复 logs/export 无 limit 限制可能导致 OOM 的问题（新增 limit 参数，默认10000，最大50000）

***

## \[2.3.0] - 2026-06-08

### 新增

- `upgrade` 命令：从远程仓库拉取新版本代码并升级，支持指定版本（tag/branch/commit）、`--check` 仅检查模式、前置安全检查、版本差异展示、红色警告框、强制自动备份、自动数据库迁移、迁移失败恢复方案
- 危险命令结构化警告：`restore`、`mock clear`、`migrate`、`redis flush`、`redis del`、`config set`（安全类配置）执行前显示影响范围和确认提示
- `config set` 新旧值对比显示，安全类配置（锁定策略、限流、验证码等）二次确认
- 定时任务暂停机制真正生效：`_is_task_paused()` 函数在任务循环中检查 Redis 键 `scheduler:ctrl:{task}`
- 新增 `docs/manage-sh-reference.md` 命令行操作手册

### 改进

- `update` 命令移除 git pull，改为仅重建+重启本地代码（不再有 `--no-git` 参数）
- `scheduler pause/resume` 现在真正控制定时任务执行（之前仅设置 Redis 键但任务未检查）

### 修复

- `firewall_query` 定时任务改用 `TerminalService._get_sangfor_service_by_tag()` + `SangforService.get_blocked_ips()`（原调用不存在的 `query_firewall_blacklist` 方法）

***

## \[2.2.0] - 2026-06

### 重构

- **MacAddress → Terminal 重命名**：数据库表 `mac_addresses` → `terminals`，后端模型 `MacAddress` → `Terminal`，Schema `MacAddressBase/Create/Update/Response/Query` → `TerminalBase/Create/Update/Response/Query`，服务 `MacService` → `TerminalService`，API 路由 `/mac` → `/terminals`，前端组件 `MacAddresses` → `Terminals`，前端路由 `/mac-addresses` → `/terminals`，前端 Hook `useMacAddresses` → `useTerminals`，前端类型 `MacAddress` → `Terminal`，文件名 `mac_address.py` → `terminal.py`、`mac_service.py` → `terminal_service.py`、`mac_addresses.py` → `terminals.py`、`MacAddresses.tsx` → `Terminals.tsx`、`useMacData.ts` → `useTerminalData.ts`
- **API 路由** **`/mac`** **→** **`/terminals`**：`GET /api/v1/mac/` → `GET /api/v1/terminals/`，`GET /api/v1/mac/search` → `GET /api/v1/terminals/search`，`POST /api/v1/mac/block/{ip}` → `POST /api/v1/terminals/block/{ip}`，`POST /api/v1/mac/unblock/{ip}` → `POST /api/v1/terminals/unblock/{ip}`，`GET /api/v1/mac/{id}` → `GET /api/v1/terminals/{id}`
- **IP Guard → ComplianceBaseline 分离**：新增 `compliance_baselines` 数据库表，新增 `ComplianceBaseline` 模型、Schema、Endpoint，DataSource 的 `type` 不再包含 `ipguard`（只保留 `arp_ssh`/`arp_api`/`sangfor`），新增 API 路由 `/compliance-baselines/`（CRUD + test + sync），前端 DataSources 页面新增 "Compliance Baselines" Tab，数据库迁移脚本 `002_terminal_baseline.py`

***

## \[2.1.0] - 2026-06

### 新功能

- **数据源管理系统**：新增 DataSource 和 DataSourceBinding 数据模型，统一管理 ARP 数据源（SSH/API）、IP Guard 合规基准、深信服防火墙，支持数据源 CRUD、测试连接、手动同步
- **合规检查引擎**：新增 ComplianceService，4 种合规状态判定（compliant/bypass/non\_compliant/unknown），白名单匹配类型标记（wl\_match\_type: mac/ip/both），IPGuard 基准匹配，自动封禁/解封按防火墙 Tag 路由
- **多防火墙支持**：数据源绑定（DataSourceBinding）关联 ARP 数据源与防火墙，封禁/解封操作按 Tag 路由到对应防火墙，多防火墙场景创建独立 Blacklist 记录
- **定时任务可配置**：5 个定时任务频率参数（ARP 采集、IPGuard 同步、防火墙查询、合规检查、自动解封），支持 30 秒 - 1 天间隔，通过 `manage.sh config set` 修改
- **Scheduler 配置分类**：系统配置新增 `scheduler` 分类，SchedulerConfigResponse 包含 5 个间隔配置项
- **前端自动刷新**：Terminal 和 Blacklist 页面支持手动刷新按钮和自动刷新选择器（30 秒 / 1 分钟 / 5 分钟 / 10 分钟）
- **DataSources 页面**：新增数据源管理页面（管理员专属），包含 Data Sources / Bindings / Compliance 三个 Tab，支持编辑数据源、手动同步、合规检查操作
- **Users 页面**：新增用户管理页面（管理员专属），用户 CRUD 操作
- **Profile 页面**：新增个人资料页面
- **品牌动态加载**：新增 useBrandingStore Zustand store，登录后从后端 `/settings/` API 动态加载品牌配置，替代纯静态 branding.ts
- **manage.sh config 增强**：新增 `config list`、`config get`、`config set`、`config branding`、`config upload` 子命令，支持数据库系统配置和品牌资源管理
- **Whitelist 详情查看**：白名单页面新增详情弹窗，comments 字段改为必填
- **Terminal 合规状态**：终端页面从 6 种状态改为 4 种合规状态（Normal/Bypass/Blocked/Pending），集成黑名单数据展示，Bypass 显示匹配类型（MAC/IP/Both），Blocked 显示防火墙 Tag
- **Terminal 快捷操作**：Bypass 条目支持"从白名单移除"，Blocked 条目支持"从黑名单移除"
- **Dashboard 合规统计**：统计卡片更新为 5 个（Total/Normal/Bypass/Blocked/Pending），compliance\_status 分组统计
- **导航权限控制**：NAV\_ITEMS 新增 adminOnly 字段，Data Sources 和 Users 页面仅管理员可见

### 改进

- **终端总数统计**：Total 统计仅计算 ARP 数据源条目（source='arp'），不再包含白名单独立条目
- **黑名单手动封禁**：手动封禁 source\_tag 标记为 "manual"，compliance\_status 设置为 "non\_compliant"
- **黑名单手动解封**：按 firewall\_tag 过滤删除 Blacklist 记录，compliance\_status 设置为 "unknown"
- **白名单 CIDR 匹配**：存储原始 pattern，使用 ipaddress 模块判断包含关系，不展开 CIDR
- **合规检查缓存**：IPGuard 数据 Redis 缓存 10 分钟 TTL，白名单数据 Redis 缓存 5 分钟 TTL
- **ARP 采集后合规更新**：ARP 采集完成后自动运行合规检查，更新 compliance\_status 和 wl\_match\_type
- **Demo 默认密码**：Demo 模式默认密码从 admin123 改为 Admin123（满足密码复杂度要求）
- **前端类型对齐**：MacAddress、WhitelistEntry、BlacklistEntry、DataSourceItem 等类型定义与后端 schema 完全对齐
- **前端 UI 统一**：所有页面按钮使用默认 md 尺寸，Dashboard Overview 放在页面标题下方

### Bug 修复

- 修复 Stats API `GET /mac/stats` 被 `GET /mac/{mac_id}` 路由匹配的问题
- 修复 Scheduler 配置未出现在 settings API 的问题（AllConfigsResponse 缺少 scheduler 字段）
- 修复 ConfigService 缺少 get\_value 方法导致 \_get\_scheduler\_interval 调用失败
- 修复 MacAddress 模型缺少 wl\_match\_type 字段导致前端类型不匹配
- 修复 arp\_collector\_service.py 合规检查后未更新 wl\_match\_type
- 修复 main.py scheduled\_compliance\_check 未更新 wl\_match\_type
- 修复前端 MacAddresses.tsx 中 removingWlId/removingBlId/whitelistId 与 mac.id 类型比较错误（string | null vs number）
- 修复前端 MacAddresses.tsx 中 CheckCircle 未使用导入导致构建失败

***

## \[2.0.0] - 2026-06

### 新功能

- **统一管理脚本**：整合 `manage.sh`、`deploy.sh`、`quickstart.sh` 为单一 `manage.sh`，支持 17 个子命令（deploy/start/stop/restart/status/health/logs/update/init/test/mock/backup/restore/shell/ssl/config/validate/clean/version），幂等设计，非交互模式（`-y`），调试输出（`-v`）
- **生产部署向导**：`deploy --prod` 交互式配置数据库密码、Redis 密码、JWT 密钥、深信服 API、网络交换机集成
- **深度健康检查**：`health` 命令执行 8 项检查（Docker/容器/数据库/Redis/后端/Web/SSL/磁盘）
- **配置管理**：`config` 命令查看/修改环境变量，敏感信息自动脱敏
- **SSL 证书管理**：`ssl` 命令幂等生成自签名证书，`--force` 强制重新生成，Nginx 自动 reload
- **数据库备份恢复**：`backup`/`restore` 命令，自动清理旧备份（保留 10 个），恢复前自动备份
- **自动备份**：`update`/`restore`/`mock clear` 操作前自动备份数据库
- **部署状态管理**：`.manage/state.env` 跟踪部署状态，实现幂等性控制
- **品牌自定义**：集中式品牌配置（`branding.ts`），支持自定义应用名称、Logo、Favicon、登录页样式、页脚信息、ICP 备案等，无需修改组件代码
- **可折叠侧边栏**：侧边栏支持展开/折叠切换，折叠时显示图标与悬停提示
- **高级分页**：分页组件支持顶部/底部双展示、每页条数选择（10/20/50/100）、快速跳转指定页码
- **日期范围过滤**：`DateRangeFilter` 组件，支持快捷选项和自定义日期范围
- **可折叠搜索面板**：搜索与过滤条件区域支持折叠/展开
- **登录安全增强**：3 次失败后显示验证码，5 次失败后锁定账户 15 分钟
- **状态提示**：6 种状态（Active/Inactive/Blocked/Pending/Unblocked/Bypass）悬停 Tooltip 解释
- **统一卡片风格**：所有页面卡片采用 `rounded-2xl` 圆角、渐变色条、Section Header 统一风格
- **页脚信息**：主布局和登录页页脚显示版权信息、版本号、ICP 备案号及自定义链接
- **Nginx 安全代理**：仅 Nginx 对外暴露端口（8080→80, 8443→443），HTTP 自动重定向 HTTPS，其他服务端口不对外暴露

### 改进

- **登录错误提示**：登录失败提示改为持久显示，支持手动关闭
- **图标一致性**：Dashboard 与导航栏图标统一（Whitelisted=List, Blocked=ShieldOff）
- **Blacklist ip\_address 可空**：黑名单 IP 地址字段改为可选，支持仅基于 MAC 地址的封禁
- **空值保护**：增强各组件对空值/未定义值的容错处理
- **依赖顺序启停**：按基础设施→应用→代理顺序启动，反向停止
- **前端构建产物保护**：`dist_backup` 机制防止 Docker Volume 覆盖构建产物

### Bug 修复

- 修复 DateRangeFilter onChange 不触发的问题
- 修复 Blocked 页面 `Cannot read properties of null (reading 'toLowerCase')` 错误
- 修复黑名单无法单独添加 MAC 地址（ip\_address NOT NULL 约束）
- 修复 Docker 构建 TypeScript 编译错误（`NodeJS.Timeout`、`as const` 类型推断、Fragment 包裹）
- 修复 PostgreSQL 健康检查 `tam_admin does not exist`（需指定 `-d tam_db`）
- 修复 Redis 健康检查（需 `-a password` 参数）
- 修复前端容器构建产物被 Volume 覆盖的问题
- 修复 Nginx HTTPS 端口映射（内部 443，对外 8443）

***

## \[1.0.0] - 2025-12

### 初始实现

- **FastAPI 后端**：基于 FastAPI + SQLAlchemy 2.0 的异步 API 服务
- **React 前端**：基于 React 18 + TypeScript + Vite 的现代化前端
- **Docker 部署**：完整的 Docker Compose 编排，包含 PostgreSQL、Redis、Nginx
- **用户认证**：JWT 令牌认证，支持登录/登出/令牌刷新
- **MAC 地址管理**：搜索、过滤、分页、状态管理
- **白名单管理**：增删查、搜索、过滤、分页
- **黑名单管理**：增删查、搜索、过滤、分页
- **审计日志**：操作记录查看、搜索、日期过滤、分页
- **仪表板**：数据概览与统计图表
- **HTTPS 支持**：Nginx 配置 SSL/TLS
- **速率限制**：认证端点请求频率限制
- **CORS 保护**：跨域请求安全配置

