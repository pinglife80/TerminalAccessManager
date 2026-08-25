# v3.12.0 版本发布计划

> 发布日期：2026-08-20
> 遵循：[Git 敏捷开发指导手册](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docs/git-workflow-guide.md) 单人开发最佳实践

***

## 版本信息

| 项      | 值                        |
| ------ | ------------------------ |
| 当前版本   | v3.11.0                  |
| 新版本    | **v3.12.0** (Minor 版本升级) |
| 版本类型   | 新功能 + 重要Bug修复            |
| 发布分支   | main                     |
| 当前工作分支 | develop                  |

### 版本升级理由

本次更新包含多个新功能和核心逻辑重构，符合 SemVer Minor 版本递增：

* ✅ 新功能：合规筛选条件区分 MAC 前缀匹配对象（ARP来源/IPGuard基线来源）

* ✅ 新功能：终端以 MAC 地址为唯一标识重构，支持双网卡终端正确处理

* ✅ 重要修复：合规状态频繁震荡（封禁→解封→封禁循环）问题，三层防震荡保护

* ✅ 涉及 3 个数据库迁移脚本，核心合规计算逻辑重构

***

## 变更清单

### 新功能 (Features)

1. **合规范围条件增强** - MAC前缀筛选区分匹配数据源

   * 新增 `mac_prefix_arp`：仅匹配ARP采集的终端MAC，匹配后忽略MAC仅用IP匹配IPGuard

   * 新增 `mac_prefix_ipguard`：仅匹配IPGuard基线中的MAC，匹配后按IP-MAC精确匹配

   * 前端界面增加两种类型选项和说明

2. **终端唯一标识重构** - MAC地址作为终端主键

   * Terminal 表唯一约束从 (IP, MAC) 改为 MAC地址归一化值

   * ARP 入库逻辑重构：按MAC查询更新IP而非新建记录，DHCP换IP不再产生重复记录

   * 正确支持有线+无线双网卡终端（每个MAC独立一条记录，分别合规判断）

   * IPGuard基线解析支持多MAC-IP对格式：`MAC1(IP1)MAC2(IP2)...`

3. **合规状态防震荡机制** - 三层保护防止状态频繁切换

   * 确认阈值统一：bypass/unknown/compliant 降级到 non\_compliant 都需要连续N次确认（默认2次≈10分钟）

   * 对称确认计数：从 non\_compliant 回到 compliant/bypass 也需要连续N次匹配确认

   * 双向冷却期：自动封禁后10分钟内不自动解封，自动解封后10分钟内不自动重新封禁

   * IP变更宽限期：DHCP换IP后10分钟宽限期内不立即降级封禁，等待IPGuard同步新映射

   * 解封与状态变更解耦：auto\_unblock 仅处理防火墙操作，不直接修改合规状态

### Bug修复 (Fixes)

1. ✅ 修复左侧导航栏滚动条溢出问题（v3.11.0已部分修复，本次确认完整）
2. ✅ 修复 auto\_unblock 分组key未归一化MAC导致多防火墙解封不一致
3. ✅ 修复 main.py 定时合规检查中 result\_lookup 仍用IP为key（MAC唯一化改造后遗漏）
4. ✅ 修复 IPGuard同步后立即全量重算导致的ARP/IPGuard时序竞争问题
5. ✅ 修复 retry-block 逻辑重复封禁问题
6. ✅ 修复活跃黑名单查询条件按 (IP, MAC) 在DHCP换IP后查不到记录的问题

### 数据库迁移

* `032_mac_prefix_scope_type_split.py` - 将原有mac\_prefix类型数据迁移为mac\_prefix\_arp

* `033_terminal_mac_unique.py` - 数据去重后修改唯一约束为MAC归一化值

* `034_compliance_oscillation_fixes.py` - 新增compliant\_confirm\_count和ip\_changed\_at字段

***

## 修改文件列表

### Backend (9个文件修改 + 3个新迁移)

| 文件                                                             | 变更类型     |
| -------------------------------------------------------------- | -------- |
| `backend/app/models/compliance_scope.py`                       | 修改       |
| `backend/app/models/terminal.py`                               | 修改       |
| `backend/app/schemas/compliance_scope.py`                      | 修改       |
| `backend/app/services/compliance_scope_service.py`             | 修改       |
| `backend/app/services/compliance_service.py`                   | 修改（核心重构） |
| `backend/app/services/arp_collector_service.py`                | 修改（核心重构） |
| `backend/app/main.py`                                          | 修改       |
| `backend/alembic/versions/032_mac_prefix_scope_type_split.py`  | 新增       |
| `backend/alembic/versions/033_terminal_mac_unique.py`          | 新增       |
| `backend/alembic/versions/034_compliance_oscillation_fixes.py` | 新增       |

### Frontend (5个文件修改)

| 文件                                       | 变更类型 |
| ---------------------------------------- | ---- |
| `frontend/src/api/complianceScope.ts`    | 修改   |
| `frontend/src/pages/ComplianceScope.tsx` | 修改   |
| `frontend/src/i18n/locales/zh.ts`        | 修改   |
| `frontend/src/i18n/locales/en.ts`        | 修改   |
| `frontend/src/i18n/locales/ja.ts`        | 修改   |

### 文档更新 (6个文档文件)

| 文档                           | 更新内容                                                                                                                                     |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/changelog.md`          | 新增 v3.12.0 版本条目，详细记录所有新增功能、改进和修复                                                                                                         |
| `docs/business-workflow.md`  | 更新合规判定流程说明（三层防震荡机制、对称确认计数、冷却期、IP宽限期）、终端数据模型（新增compliant\_confirm\_count、ip\_changed\_at字段）、MAC唯一标识说明、双网卡终端处理逻辑、IPGuard基线格式支持（多MAC-IP对解析） |
| `docs/database.md`           | 新增 032/033/034 迁移脚本说明，Terminal表字段变更，compliance\_scope的scope\_type枚举值更新                                                                   |
| `docs/user-guide.md`         | 更新合规范围条件使用说明（两种MAC前缀类型区别），增加防震荡机制说明（确认阈值、冷却期），双网卡终端显示说明                                                                                  |
| `docs/operations-runbook.md` | 新增状态震荡排查指南，数据库迁移操作步骤说明，升级注意事项                                                                                                            |
| `docs/release-notes.md`      | 同步v3.12.0发布说明，包含升级步骤和注意事项                                                                                                                |

***

## 文档更新详细计划

### 文档1: docs/changelog.md

* 文档版本更新为 v3.12.0，更新日期 2026-08-20

* 新增 section `## [3.12.0] - 2026-08-20`

* **新增**：

  * 合规范围条件MAC前缀拆分为`mac_prefix_arp`和`mac_prefix_ipguard`两种类型，分别匹配ARP来源数据和IPGuard基线数据

  * 终端以MAC地址为唯一标识重构，支持有线+无线双网卡终端独立合规判断

  * IPGuard基线正确解析双网卡格式`MAC1(IP1)MAC2(IP2)...`

  * 三层合规状态防震荡机制：对称确认计数、双向冷却期、IP变更宽限期

* **改进**：

  * auto\_unblock与状态变更解耦，仅处理防火墙操作

  * IPGuard同步后不再立即全量重算，消除时序竞争

  * 活跃黑名单查询改为按MAC标识，正确处理DHCP换IP

* **修复**：

  * 修复auto\_unblock分组key未归一化MAC导致多防火墙解封不一致

  * 修复main.py定时合规检查result\_lookup遗漏MAC为key的问题

  * 修复retry-block逻辑重复封禁问题

* 记录关联文件和迁移脚本

### 文档2: docs/business-workflow\.md

* 文档版本更新为 v3.12.0，更新日期 2026-08-20

* 更新 2.5 数据模型：

  * 补充`compliant_confirm_count`字段说明（对称合规确认计数）

  * 补充`ip_changed_at`字段说明（IP变更时间戳，用于宽限期）

  * 说明唯一约束变更：`uq_terminal_mac`（MAC归一化唯一）

* 更新 3. 合规判定流程：

  * 更新判定规则说明，新增三层防震荡机制描述：

    1. 对称确认阈值：降级/升级都需要连续N次匹配（默认2次≈10分钟）
    2. 双向冷却期：封禁/解封后10分钟内不执行反向操作
    3. IP变更宽限期：DHCP换IP后10分钟内保持原状态等待基线同步

  * 更新Scope条件说明：4种scope类型（ip\_cidr/ip\_range/mac\_prefix\_arp/mac\_prefix\_ipguard）及其区别

  * 说明双网卡终端处理：每个MAC独立记录，分别合规判断；IPGuard基线支持多MAC-IP对格式解析

* 更新 7. 状态机流转图：补充对称确认计数状态转换

* 更新 8. 关键参数说明：新增cooldown\_minutes、grace\_minutes、compliant\_confirm\_count参数说明

### 文档3: docs/database.md

* 新增迁移记录：

  * 032\_mac\_prefix\_scope\_type\_split: scope\_type从mac\_prefix拆分为mac\_prefix\_arp，数据自动迁移

  * 033\_terminal\_mac\_unique: 数据去重（保留每个MAC最新/被封禁记录），唯一约束改为mac\_address\_normalized

  * 034\_compliance\_oscillation\_fixes: 新增compliant\_confirm\_count和ip\_changed\_at字段

* 更新compliance\_scope表scope\_type枚举值说明

* 更新terminals表字段列表和索引说明

### 文档4: docs/user-guide.md

* 更新合规范围条件管理章节：

  * 说明两种MAC前缀类型的区别和使用场景：

    * mac\_prefix\_arp: 匹配ARP采集到的终端MAC，命中后忽略MAC仅用IP匹配IPGuard基线

    * mac\_prefix\_ipguard: 匹配IPGuard基线中的MAC，命中后正常IP+MAC匹配

* 新增"合规状态稳定性说明"章节：

  * 说明确认阈值机制：状态变化需要连续2次检查确认（约10分钟），防止瞬态误判

  * 说明冷却期机制：自动封禁/解封后10分钟内不重复反向操作

  * 说明IP变更宽限期：DHCP换IP后不立即改变状态，等待基线同步

* 更新终端管理章节：

  * 说明双网卡终端会显示为两条独立记录（每个网卡/MAC一条）

  * 说明DHCP换IP后IP地址自动更新，不产生新终端记录

### 文档5: docs/operations-runbook.md

* 新增"合规状态震荡排查"章节：

  * 如何通过审计日志确认状态变更原因（查找"CONFIRMED downgrade/upgrade"日志）

  * 如何确认冷却期/宽限期是否生效（查找"Cooldown: skipping"日志）

  * 常见震荡原因排查指南

* 更新升级操作步骤：

  * 明确数据库迁移执行命令：`alembic upgrade head`

  * 迁移数据去重说明：保留每个MAC最新/被封禁记录

  * 升级后验证步骤

* 更新故障排查章节：补充状态不更新/频繁封禁解封的排查流程

### 文档6: docs/release-notes.md

* 新增v3.12.0发布说明

* 包含：主要变更摘要、升级步骤、数据库迁移说明、新功能使用指引、已知问题

***

## 发布步骤（按Git Workflow单人最佳实践）

> 因为本次变更**涉及数据库迁移 + 核心模块重构 + 超过5个文件修改**，按规范必须走 PR 流程。

### Step 1: 准备工作（在 develop 分支）

1. 更新前端版本号 `frontend/package.json` 中 `version` 为 `3.12.0`
2. 按照"文档更新详细计划"更新6个项目文档：

   * `docs/changelog.md` - 新增v3.12.0变更日志

   * `docs/business-workflow.md` - 更新业务流程、数据模型、状态机说明

   * `docs/database.md` - 更新迁移记录和表结构说明

   * `docs/user-guide.md` - 更新用户使用指南

   * `docs/operations-runbook.md` - 更新运维手册和排查指南

   * `docs/release-notes.md` - 同步发布说明
3. 确认所有修改已完成，Python语法检查通过
4. 确认本地 develop 与远程同步：`git pull origin develop`

### Step 2: 按功能拆分提交（Conventional Commits规范）

在 develop 分支上按逻辑提交，保持commit历史清晰：

```bash
# 1. MAC前缀类型拆分功能
git add backend/app/models/compliance_scope.py \
        backend/app/schemas/compliance_scope.py \
        backend/app/services/compliance_scope_service.py \
        backend/alembic/versions/032_mac_prefix_scope_type_split.py \
        frontend/src/api/complianceScope.ts \
        frontend/src/pages/ComplianceScope.tsx \
        frontend/src/i18n/locales/zh.ts \
        frontend/src/i18n/locales/en.ts \
        frontend/src/i18n/locales/ja.ts
git commit -m "feat(compliance-scope): split mac_prefix into arp and ipguard matching types"

# 2. 终端MAC唯一化重构
git add backend/app/models/terminal.py \
        backend/app/services/arp_collector_service.py \
        backend/alembic/versions/033_terminal_mac_unique.py
git commit -m "refactor(terminals): use MAC address as unique terminal identifier for dual-NIC support"

# 3. 合规状态防震荡修复
git add backend/app/services/compliance_service.py \
        backend/app/main.py \
        backend/alembic/versions/034_compliance_oscillation_fixes.py
git commit -m "fix(compliance): prevent status oscillation with symmetric confirm counts, cooldown, and IP grace period"

# 4. 版本号更新
git add frontend/package.json
git commit -m "chore(release): bump version to v3.12.0"

# 5. 项目文档更新
git add docs/changelog.md \
        docs/business-workflow.md \
        docs/database.md \
        docs/user-guide.md \
        docs/operations-runbook.md \
        docs/release-notes.md
git commit -m "docs: update documentation for v3.12.0 release"
```

### Step 3: 推送 develop 并创建 PR

```bash
git push origin develop
```

然后在 GitHub 上**手动创建 Pull Request**：

* 源分支：`develop` → 目标分支：`main`

* PR标题：`Release v3.12.0: compliance scope enhancements + anti-oscillation + MAC unique key`

* PR描述：简要列出主要变更（参考本计划的"新功能"和"Bug修复"章节）

* 等待CI自动运行（backend-lint/test、frontend-lint/test）

### Step 4: 自审与合并PR

1. 在PR页面查看完整diff，自审代码
2. 确认所有CI checks通过 ✅
3. 确认分支与main同步（按分支保护规则要求）
4. **Squash and merge** 或 **Merge pull request**（创建merge commit，保留历史）

   * 使用 `--no-ff` 合并，符合Git Flow规范

   * 合并commit信息：`Merge pull request #XX from pinglife80/develop - Release v3.12.0`

### Step 5: 打Tag并推送

PR合并到main后，在本地main分支打tag：

```bash
git checkout main
git pull origin main
git tag -a v3.12.0 -m "release v3.12.0:
- feat(compliance-scope): split mac_prefix into arp and ipguard matching types
- refactor(terminals): use MAC as unique identifier, support dual-NIC terminals
- fix(compliance): prevent status oscillation with 3-layer protection
  * symmetric confirm counts for upgrade/downgrade
  * 10-minute cooldown after block/unblock
  * 10-minute grace period after IP change
- fix(ui): sidebar scrollbar overflow fixes"
git push origin v3.12.0
```

### Step 6: 创建GitHub Release

在GitHub界面操作：

1. 进入 Releases → Draft a new release
2. 选择tag：`v3.12.0`
3. Release title：`v3.12.0`
4. Release notes 内容：

   * 新功能（Features）

   * Bug修复（Bug Fixes）

   * 数据库迁移说明（提示需要执行alembic upgrade head）

   * 升级注意事项
5. 发布Release

### Step 7: 同步回develop分支

按Git Flow规范，main发布后需要同步回develop：

```bash
git checkout develop
git pull origin develop
git merge main
git push origin develop
```

***

## 升级注意事项（写入Release Notes）

> ⚠️ **重要提示**
>
> 1. **必须执行数据库迁移**：升级后首次启动前（或启动时Alembic自动执行）确保执行：
>
>    ```bash
>    cd backend && alembic upgrade head
>    ```
>
>    迁移脚本包含数据去重逻辑，会保留每个MAC最新/被封禁记录，删除重复记录。
>
> 2. **合规判定延迟变化**：新增确认阈值后，状态从"不匹配"到"封禁"默认需要约10分钟（2次检查），从"封禁"到"解封"也需要约10分钟确认，这是预期行为用于防止震荡。
>
> 3. **IPGuard基线格式支持**：现在正确解析双网卡格式 `MAC1(IP1)MAC2(IP2)`，无需特殊配置。
>
> 4. **冷却期说明**：自动封禁/解封操作有10分钟冷却保护，手动操作不受影响。

***

## 验证清单（发布后确认）

### 代码与CI验证

* [ ] 所有CI checks通过（backend-lint/test、frontend-lint/test）

* [ ] 数据库迁移执行成功，无错误

* [ ] 服务正常启动，无报错

* [ ] 合规范围条件页面新增两种MAC前缀类型可正常选择保存

* [ ] 双网卡终端在终端列表中每个MAC显示一条记录（而非每个IP-MAC对一条）

* [ ] 审计日志确认：状态变更包含CONFIRMED日志，无快速震荡

### 文档验证

* [ ] changelog.md已更新v3.12.0完整变更记录

* [ ] business-workflow\.md已更新数据模型、合规流程、防震荡机制说明

* [ ] database.md已更新3个迁移脚本说明和表结构变更

* [ ] user-guide.md已更新MAC前缀类型使用说明和合规稳定性说明

* [ ] operations-runbook.md已更新升级步骤和状态震荡排查指南

* [ ] release-notes.md已同步v3.12.0发布说明

### 发布流程验证

* [ ] 创建GitHub Release完成，包含升级注意事项

* [ ] Tag v3.12.0已推送到远程

* [ ] develop分支已同步main的merge commit

