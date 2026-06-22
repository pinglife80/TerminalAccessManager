# manage.sh 优化验证执行计划

> 文档版本：v1.0  更新日期：2026-06-18

## 一、概述

基于对 manage.sh（v3.3.1, 3855行）的全面评估，识别出 5 个维度共 18 项问题。本计划对每项修改进行**业务破坏性影响评估**，并制定分阶段、可验证的优化执行方案。

### 评估维度与问题统计

| 维度 | 评分 | 高危 | 中危 | 低危 |
|------|------|------|------|------|
| 鲁棒性 | 8.0 | 2 | 1 | 3 |
| 原子性 | 5.0 | 3 | 3 | 2 |
| 安全性 | 7.0 | 2 | 3 | 2 |
| 幂等性 | 8.0 | 0 | 2 | 2 |
| 可用性 | 9.0 | 0 | 1 | 5 |

---

## 二、逐项修改的业务破坏性影响评估

### P0 级 — 必须立即修复

#### 1. [R7] `acquire_lock` 未被任何命令调用

- **修改内容**: 在 `main()` 函数中 `ensure_env` 之后添加 `acquire_lock`
- **影响范围**: 所有 manage.sh 命令的并发行为
- **业务破坏性评估**: ⚠️ **低风险**
  - 新增锁机制不会改变任何命令的执行逻辑，仅阻止并发执行
  - **潜在风险**: 若某个命令异常退出且 EXIT trap 未触发（如 `kill -9`），锁文件可能残留，导致后续命令无法执行
  - **缓解措施**: `acquire_lock` 已有 stale PID 检测逻辑（检查 PID 是否存活），可自动清理过期锁
  - **对业务功能的影响**: 无。所有命令仍可正常执行，仅增加了并发保护
- **验证方法**:
  1. 执行 `./manage.sh status`，确认正常输出
  2. 在另一终端执行 `./manage.sh health`，确认被锁阻止
  3. `kill -9` 第一个进程后，确认第二个进程可自动获取锁

#### 2. [R6] `dc()` 函数依赖未初始化的 `ENVIRONMENT` 变量

- **修改内容**: 将 `dc()` 中的 `${ENVIRONMENT}` 改为 `$(get_env "ENVIRONMENT")`
- **影响范围**: 所有调用 `dc()` 的命令（约 60+ 处调用）
- **业务破坏性评估**: ⚠️ **中风险**
  - 当前 `dc()` 使用 shell 变量 `${ENVIRONMENT}`，在 `set -u` 模式下若未定义会报错退出
  - 但实际运行中，`deploy` 命令会通过 `set_env "ENVIRONMENT" "development/production"` 写入 .env，且 `docker compose --env-file` 会加载 .env 中的变量到容器环境
  - **关键问题**: `dc()` 中的 `${ENVIRONMENT}` 是 **shell 环境变量**，不是 .env 文件变量。docker compose 的 `--env-file` 仅将变量传给容器，不影响当前 shell
  - **实际影响**: 如果用户直接运行 `./manage.sh start`（非 deploy），且 shell 中无 ENVIRONMENT 变量，`set -u` 会报 `ENVIRONMENT: unbound variable` 退出
  - **修改后行为**: `get_env` 从 .env 文件读取值，与当前行为一致但更可靠
  - **对业务功能的影响**: 修复后不影响任何业务逻辑，仅确保 ENVIRONMENT 变量可靠读取
- **验证方法**:
  1. `unset ENVIRONMENT && ./manage.sh status`，确认不再报错
  2. `./manage.sh deploy --dev`，确认 compose 文件选择正确（加载 docker-compose.dev.yml）
  3. `./manage.sh deploy --prod`，确认 compose 文件选择正确（加载 docker-compose.prod.yml）

#### 3. [R3/S1] `eval` 代码注入 — `prompt_input` 和 `prompt_password`

- **修改内容**: 将 `eval "${var_name}='${input}'"` 改为 `printf -v "${var_name}" '%s' "${input}"`
- **影响范围**: `prompt_input`（L226）和 `prompt_password`（L243）的所有调用点
- **业务破坏性评估**: ✅ **无风险**
  - `printf -v` 是 bash 内建命令，功能等价于变量赋值，但不执行任何代码
  - 所有调用点（Sangfor URL/用户名/密码、Switch 配置、生产部署向导等）的输入值会被原样存储，与 `eval` 在正常输入下行为完全一致
  - **唯一差异**: `eval` 会展开变量引用（如 `$HOME`），`printf -v` 不会。但 manage.sh 的 prompt 场景中，用户输入不应包含变量引用
  - **对业务功能的影响**: 无。正常业务输入不受影响
- **验证方法**:
  1. `./manage.sh deploy --prod`，在交互式向导中输入含特殊字符的密码（如 `P@ss'w"rd!`），确认密码正确存储
  2. `./manage.sh config set app_name "Test App"`，确认配置正确设置
  3. 输入含 `$` 的值，确认不被展开

#### 4. [S2] 密码通过命令行参数传递

- **修改内容**: `_config_get_admin_token` 中 curl 传参改用 `--data-urlencode` 或 stdin
- **影响范围**: 仅 `_config_get_admin_token` 函数（L2443-2446）
- **业务破坏性评估**: ✅ **无风险**
  - 修改仅改变 curl 的传参方式，HTTP 请求体内容不变
  - `--data-urlencode` 会自动 URL 编码，与当前手动拼接 `username=admin&password=${admin_password}` 的区别在于：密码中的特殊字符（如 `&`, `=`, `+`）会被正确编码
  - **当前 bug**: 若密码含 `&` 字符，当前方式会破坏 form 格式（如 `pass&word` 被解析为 `pass` + `word=...`），修改后反而修复了这个潜在 bug
  - **对业务功能的影响**: 无。API 调用行为不变，且修复了特殊字符密码的潜在问题
- **验证方法**:
  1. `./manage.sh config list`，确认 token 获取成功
  2. 修改 ADMIN_PASSWORD 为含特殊字符的密码（如 `P@ss&w=rd`），确认 config 命令仍可正常认证
  3. `ps aux | grep curl`，确认密码不出现在进程参数中

---

### P1 级 — 应尽快修复

#### 5. [A2] `cmd_restore` 无回滚

- **修改内容**: DROP DATABASE 前先 RENAME 为 `tam_db_pre_restore`，import 成功后再 DROP 旧库
- **影响范围**: `cmd_restore` 函数（L2242-2284）
- **业务破坏性评估**: ⚠️ **中风险**
  - **新增行为**: 在恢复前保留旧数据库（RENAME 而非 DROP），增加了安全性
  - **潜在风险**:
    1. RENAME 操作需要额外的磁盘空间（旧库仍占空间），若磁盘空间不足可能导致 RENAME 失败
    2. 旧库 `tam_db_pre_restore` 若已存在（上次恢复残留），RENAME 会失败
    3. 恢复成功后需清理旧库，若清理失败会持续占用磁盘
  - **缓解措施**:
    1. RENAME 前先 `DROP DATABASE IF EXISTS tam_db_pre_restore`
    2. 检查磁盘空间是否足够（已有 `check_disk_space` 函数）
    3. 恢复成功后自动清理旧库，失败时提示手动清理
  - **对业务功能的影响**: 无。恢复操作本身是破坏性的，新增回滚机制仅在恢复失败时提供保护
- **验证方法**:
  1. 正常恢复流程：`./manage.sh restore <backup>`，确认数据正确恢复
  2. 模拟恢复失败：提供损坏的 SQL 文件，确认旧库仍存在可回滚
  3. 磁盘空间不足场景：确认 RENAME 前有检查
  4. 残留旧库场景：确认自动清理 `tam_db_pre_restore`

#### 6. [A3] `cmd_upgrade` 迁移失败无自动回滚

- **修改内容**: 迁移失败时自动 `git checkout` 回滚到原分支 + 提示数据库恢复
- **影响范围**: `cmd_upgrade` 函数（L1896-1907）
- **业务破坏性评估**: ⚠️ **中风险**
  - **新增行为**: alembic 迁移失败后自动回滚代码到升级前的分支
  - **潜在风险**:
    1. git checkout 可能失败（如有未提交的本地修改）
    2. 代码回滚后，数据库 schema 可能处于中间状态（部分迁移已执行），与回滚后的代码不兼容
    3. 自动回滚可能掩盖真正的问题，用户可能不知道发生了什么
  - **缓解措施**:
    1. checkout 前检查 `git status --porcelain`，有未提交修改时不自动回滚
    2. 回滚后明确提示用户需要手动恢复数据库
    3. 回滚操作需要用户确认（非静默执行）
  - **对业务功能的影响**: 无。仅在迁移失败时提供回滚，正常升级流程不受影响
- **验证方法**:
  1. 正常升级流程：确认迁移成功后无回滚
  2. 模拟迁移失败：创建一个会失败的 alembic 迁移脚本，确认代码自动回滚
  3. 有未提交修改时升级：确认不自动回滚，提示用户手动处理

#### 7. [A1] `cmd_update` build 失败服务不可用

- **修改内容**: 将 `dc up -d --build` 拆分为 `dc build` + `dc up -d`
- **影响范围**: `cmd_update` 函数（L1630-1647）
- **业务破坏性评估**: ✅ **低风险**
  - **当前行为**: `dc up -d --build` 会先构建再启动，如果构建失败，旧容器可能已停止
  - **修改后行为**: 先 `dc build`，构建成功后再 `dc up -d`。若构建失败，旧容器继续运行
  - **潜在风险**:
    1. `dc build` 和 `dc up -d` 之间有短暂时间窗口，但这不影响运行中的容器
    2. `dc build` 可能成功但 `dc up -d` 失败（如端口冲突），此时行为与修改前一致
  - **对业务功能的影响**: 正面。修改后服务可用性更高，构建失败时旧服务继续运行
- **验证方法**:
  1. 正常更新：确认 build → up 流程正常
  2. 构建失败场景：在代码中引入语法错误，确认旧容器继续运行
  3. 确认 `dc up -d` 在 build 成功后正常启动新容器

#### 8. [S3] `config set` JSON 注入

- **修改内容**: key/value 使用 python3 json.dumps 编码
- **影响范围**: `cmd_config` 的 set 子命令（L2689-2692）
- **业务破坏性评估**: ✅ **无风险**
  - 修改仅改变 JSON 构造方式，HTTP 请求语义不变
  - `json.dumps` 会正确转义双引号、反斜杠等特殊字符，与当前手动拼接相比更安全
  - **当前 bug**: 若 value 含 `"` 字符，当前方式会生成无效 JSON，修改后修复此问题
  - **对业务功能的影响**: 无。正常配置值不受影响，特殊字符值反而修复了 bug
- **验证方法**:
  1. `./manage.sh config set app_name "Test App"`，确认正常
  2. `./manage.sh config set app_name 'Test "App"'`，确认 JSON 正确编码
  3. `./manage.sh config list`，确认配置正确存储

#### 9. [S4] `audit-cleanup` DAYS 参数无类型验证

- **修改内容**: 添加 `[[ "${DAYS}" =~ ^[0-9]+$ ]]` 验证
- **影响范围**: `cmd_audit_cleanup` 函数（L1498）
- **业务破坏性评估**: ✅ **无风险**
  - 仅增加输入验证，拒绝非数字输入
  - 当前默认值 180 和 `--days` 参数均为数字，正常使用不受影响
  - **对业务功能的影响**: 无。仅阻止无效输入
- **验证方法**:
  1. `./manage.sh audit-cleanup --days 30`，确认正常
  2. `./manage.sh audit-cleanup --days abc`，确认被拒绝
  3. `./manage.sh audit-cleanup --days -1`，确认被拒绝

#### 10. [U1] `auto_backup` 失败不阻止操作

- **修改内容**: `auto_backup` 失败时返回非零退出码，调用方检查并决定是否继续
- **影响范围**: `cmd_update`/`cmd_upgrade`/`cmd_restore`/`cmd_mock` 中的 `auto_backup` 调用
- **业务破坏性评估**: ⚠️ **中风险**
  - **当前行为**: 备份失败仅 warn，操作继续执行
  - **修改后行为**: 备份失败时操作被阻止（除非 `-y` 模式）
  - **潜在风险**:
    1. 服务未运行时 `auto_backup` 跳过备份（返回 0），此行为应保持不变
    2. 数据库不可达时备份失败，但操作可能仍需执行（如 restore 本身就是修复数据库）
    3. 过于严格的备份要求可能阻止必要的运维操作
  - **缓解措施**:
    1. 仅在 `cmd_upgrade` 和 `cmd_update` 中强制要求备份成功
    2. `cmd_restore` 中备份失败不阻止（因为 restore 本身就是恢复操作）
    3. 提供 `--skip-backup` 选项允许跳过备份
  - **对业务功能的影响**: 正面。增加数据安全保护，但需注意不阻塞必要操作
- **验证方法**:
  1. 正常流程：备份成功，操作继续
  2. 备份失败场景：停止数据库后执行 update，确认操作被阻止
  3. `--skip-backup` 场景：确认可跳过备份继续操作

---

### P2 级 — 建议修复

#### 11. [R1] 锁文件竞态条件

- **修改内容**: 使用 `flock` 替代文件锁
- **影响范围**: `acquire_lock`/`release_lock` 函数
- **业务破坏性评估**: ⚠️ **低风险**
  - `flock` 是 Linux 标准工具，但 Alpine Linux 默认不安装（需 `util-linux` 包）
  - 当前项目使用 `postgres:15-alpine`、`redis:7-alpine` 等，但 manage.sh 运行在宿主机
  - **潜在风险**: 宿主机可能未安装 `flock`（特别是旧版 CentOS/Debian）
  - **缓解措施**: 检测 `flock` 是否可用，不可用时回退到当前文件锁方式
  - **对业务功能的影响**: 无。锁机制不影响业务逻辑
- **验证方法**:
  1. 确认宿主机 `flock` 可用
  2. 并发执行测试
  3. 无 `flock` 环境下的回退测试

#### 12. [R2] 锁文件在 /tmp

- **修改内容**: `LOCK_FILE` 改为 `${STATE_DIR}/manage.lock`
- **影响范围**: 仅 `LOCK_FILE` 变量定义（L71）
- **业务破坏性评估**: ✅ **无风险**
  - 仅改变锁文件路径，不影响任何业务逻辑
  - `${STATE_DIR}` 为 `.manage/`，目录权限已在 `ensure_dirs` 中设置
- **验证方法**:
  1. `./manage.sh status`，确认锁文件在 `.manage/manage.lock`
  2. 并发执行测试

#### 13. [A6] `set_env` 非原子写入

- **修改内容**: 先写临时文件，成功后 `mv` 原子替换
- **影响范围**: `set_env` 函数（L461-470）
- **业务破坏性评估**: ✅ **无风险**
  - 修改仅改变文件写入方式，.env 文件内容不变
  - `mv` 在同一文件系统上是原子操作
  - **对业务功能的影响**: 无。增加写入可靠性
- **验证方法**:
  1. `./manage.sh deploy --dev`，确认 .env 正确生成
  2. 并发写入测试：同时修改多个环境变量

#### 14. [A7] Redis 恢复逻辑缺陷

- **修改内容**: 先 docker cp RDB 文件到 Redis 数据卷，再启动 Redis
- **影响范围**: `cmd_restore` 中的 Redis 恢复部分（L2264-2269）
- **业务破坏性评估**: ⚠️ **中风险**
  - **当前行为**: 启动 Redis（加载旧 RDB）→ docker cp 新 RDB → 重启 Redis
  - **修改后行为**: docker cp 新 RDB 到数据卷 → 启动 Redis（加载新 RDB）
  - **潜在风险**:
    1. Redis 数据卷路径可能因 Docker 版本或配置不同而变化
    2. 需要确定数据卷在宿主机上的挂载路径
    3. docker cp 到已停止的容器可能失败（容器需存在）
  - **缓解措施**: 使用 `docker volume inspect` 获取数据卷宿主路径，直接复制文件
  - **对业务功能的影响**: 正面。修复 Redis 恢复时短暂加载旧数据的问题
- **验证方法**:
  1. 正常恢复流程，确认 Redis 数据正确
  2. 检查恢复后 Redis 中无旧数据残留

#### 15. [I1] `_configure_dev_env` 每次覆盖 .env

- **修改内容**: 仅在 .env 不存在时创建，已存在时保留用户自定义项
- **影响范围**: `_configure_dev_env` 函数（L844-871）
- **业务破坏性评估**: ⚠️ **中风险**
  - **当前行为**: 每次 `deploy --dev` 都删除重建 .env，确保干净的开发环境
  - **修改后行为**: 保留已有 .env，仅补充缺失的变量
  - **潜在风险**:
    1. 旧 .env 可能有过时的配置项（如版本升级后新增的变量）
    2. 用户可能在 .env 中设置了错误的值，不再被重置
    3. 开发环境的一致性可能受影响
  - **缓解措施**:
    1. 对比 .env 和 .env.example，自动补充新增变量
    2. 提供 `--reset-env` 选项允许强制重建
    3. 在部署前显示 .env 差异
  - **对业务功能的影响**: 需权衡。开发环境便利性 vs 一致性
- **验证方法**:
  1. 首次 `deploy --dev`，确认 .env 正确创建
  2. 修改 .env 中某值后再次 `deploy --dev`，确认自定义值保留
  3. `deploy --dev --reset-env`，确认 .env 被重建

#### 16. [U2] `clean` 确认提示不一致

- **修改内容**: 修改提示文本与 `confirm` 函数匹配
- **影响范围**: `cmd_clean` 中的确认提示（L3621）
- **业务破坏性评估**: ✅ **无风险**
  - 仅修改提示文本，不影响任何逻辑
- **验证方法**: 执行 `./manage.sh clean`，确认提示文本正确

#### 17. [S7] `redis keys` 阻塞风险

- **修改内容**: 生产环境使用 `SCAN` 替代 `KEYS`
- **影响范围**: `cmd_redis` 的 keys 子命令（L3057）
- **影响评估**: ⚠️ **低风险**
  - `SCAN` 返回游标，需要循环调用，实现更复杂
  - 开发环境可保留 `KEYS`（数据量小）
  - **对业务功能的影响**: 无。仅改变 Redis 查询方式
- **验证方法**:
  1. `./manage.sh redis keys '*'`，确认结果正确
  2. 大数据量场景下确认不阻塞

#### 18. [U4] `backup-schedule` cron 无日志

- **修改内容**: crontab 条目添加日志重定向
- **影响范围**: `cmd_backup_schedule` 的 enable 子命令（L2308）
- **业务破坏性评估**: ✅ **无风险**
  - 仅添加日志重定向，不影响备份逻辑
- **验证方法**:
  1. `./manage.sh backup-schedule enable`，确认 crontab 条目包含日志重定向
  2. 等待 cron 执行，确认日志文件生成

---

## 三、业务破坏性影响总结

| 风险等级 | 数量 | 问题编号 |
|----------|------|---------|
| ✅ 无风险 | 8 | #3, #4, #8, #9, #12, #13, #16, #18 |
| ⚠️ 低风险 | 3 | #1, #11, #17 |
| ⚠️ 中风险 | 6 | #2, #5, #6, #10, #14, #15 |
| ❌ 高风险 | 0 | — |

**结论**: 所有 18 项修改均无高业务破坏性风险。6 项中风险修改均有明确的缓解措施，且修改本身是增强系统安全性和可靠性的，不会改变正常业务流程的预期行为。

---

## 四、分阶段执行计划

### 阶段 1: P0 安全修复（4 项）

**目标**: 修复安全漏洞和关键缺陷，零业务影响

| 步骤 | 修改 | 文件:行号 | 具体变更 | 预期影响 |
|------|------|-----------|---------|---------|
| 1.1 | [R7] 启用锁机制 | manage.sh:3759-3801 | 在 `main()` 中 `ensure_env` 后添加 `acquire_lock` | 所有命令增加并发保护 |
| 1.2 | [R6] 修复 ENVIRONMENT 变量 | manage.sh:266-278 | `dc()` 中 `${ENVIRONMENT}` 改为 `$(get_env "ENVIRONMENT" 2>/dev/null || echo "")` | 确保环境变量可靠读取 |
| 1.3 | [R3/S1] 修复 eval 注入 | manage.sh:226,243 | `eval "${var_name}='${input}'"` → `printf -v "${var_name}" '%s' "${input}"` | 消除代码注入风险 |
| 1.4 | [S2] 密码传递安全 | manage.sh:2443-2446 | curl 使用 `--data-urlencode` 替代 `-d` 字符串拼接 | 防止密码泄露和特殊字符问题 |

**验证步骤**:
1. 语法检查: `bash -n manage.sh`
2. 基础功能: `./manage.sh help`、`./manage.sh version`、`./manage.sh status`
3. 并发测试: 两个终端同时执行 `./manage.sh health`
4. 交互测试: `./manage.sh deploy --prod` 向导中输入含特殊字符的密码
5. API 测试: `./manage.sh config list` 确认认证正常
6. 完整部署: `./manage.sh deploy --dev` → `./manage.sh health`

### 阶段 2: P1 原子性增强（6 项）

**目标**: 增强关键操作的原子性和回滚能力

| 步骤 | 修改 | 文件:行号 | 具体变更 | 预期影响 |
|------|------|-----------|---------|---------|
| 2.1 | [A1] update 拆分构建 | manage.sh:1630-1647 | `dc up -d --build` → `dc build && dc up -d` | 构建失败时旧服务继续运行 |
| 2.2 | [A2] restore 增加回滚 | manage.sh:2249-2253 | DROP 前 RENAME 为 `tam_db_pre_restore`，成功后清理 | 恢复失败可回滚 |
| 2.3 | [A3] upgrade 增加回滚 | manage.sh:1896-1907 | 迁移失败时自动 git checkout + 提示 DB 恢复 | 升级失败可回滚代码 |
| 2.4 | [S3] config set JSON 安全 | manage.sh:2689-2692 | 使用 python3 json.dumps 编码 key/value | 防止 JSON 注入 |
| 2.5 | [S4] DAYS 参数验证 | manage.sh:1498 | 添加 `[[ "${DAYS}" =~ ^[0-9]+$ ]]` | 防止 SQL 注入 |
| 2.6 | [U1] auto_backup 失败阻止 | manage.sh:477-504,1864 | auto_backup 失败返回非零；upgrade/update 中检查 | 增强数据安全 |

**验证步骤**:
1. 语法检查: `bash -n manage.sh`
2. update 测试: 引入代码语法错误后 `./manage.sh update`，确认旧服务继续运行
3. restore 测试:
   - 正常恢复: `./manage.sh restore <backup>`
   - 失败回滚: 使用损坏 SQL 文件，确认旧库可回滚
   - 残留清理: 确认 `tam_db_pre_restore` 被自动清理
4. upgrade 测试:
   - 正常升级流程
   - 模拟迁移失败，确认代码自动回滚
5. config set 测试: 含特殊字符的 value
6. audit-cleanup 测试: `--days abc` 被拒绝
7. auto_backup 测试: 停止数据库后执行 update，确认操作被阻止
8. 完整业务链: deploy → init → mock generate → backup → restore → health

### 阶段 3: P2 健壮性优化（8 项）

**目标**: 提升系统健壮性和用户体验

| 步骤 | 修改 | 文件:行号 | 具体变更 | 预期影响 |
|------|------|-----------|---------|---------|
| 3.1 | [R1] 锁竞态修复 | manage.sh:247-263 | 使用 `flock`（可用时）替代文件锁 | 消除竞态条件 |
| 3.2 | [R2] 锁文件路径 | manage.sh:71 | `LOCK_FILE="${STATE_DIR}/manage.lock"` | 防止 /tmp 篡改 |
| 3.3 | [A6] set_env 原子写入 | manage.sh:461-470 | 先写临时文件后 mv | 防止 .env 损坏 |
| 3.4 | [A7] Redis 恢复修复 | manage.sh:2264-2269 | 先 cp RDB 再启动 Redis | 修复短暂加载旧数据 |
| 3.5 | [I1] dev env 保留配置 | manage.sh:844-871 | 仅在 .env 不存在时创建，已存在时补充缺失变量 | 保留用户自定义 |
| 3.6 | [U2] 确认提示一致 | manage.sh:3621 | 修改提示文本 | 用户体验改善 |
| 3.7 | [S7] redis keys 安全 | manage.sh:3057 | 生产环境使用 SCAN | 防止阻塞 |
| 3.8 | [U4] cron 日志重定向 | manage.sh:2308 | 添加 `>> logfile 2>&1` | 备份失败可追溯 |

**验证步骤**:
1. 语法检查: `bash -n manage.sh`
2. 锁机制测试: 并发执行 `./manage.sh health`
3. .env 原子性: 并发修改多个环境变量
4. Redis 恢复: 完整 restore 流程，检查数据正确性
5. dev env 保留: 修改 .env 后再次 deploy --dev
6. cron 日志: `./manage.sh backup-schedule enable`，检查 crontab 条目
7. 完整业务链验证

---

## 五、每个阶段后的完整业务链验证

每个阶段完成后，执行以下完整业务链测试：

```
1. 环境清理:    ./manage.sh clean -y
2. 开发部署:    ./manage.sh deploy --dev
3. 服务检查:    ./manage.sh health
4. 数据初始化:  ./manage.sh init
5. Mock 数据:   ./manage.sh mock generate
6. 配置管理:    ./manage.sh config list
7. 数据备份:    ./manage.sh backup
8. 数据恢复:    ./manage.sh restore <backup_file>
9. 服务更新:    ./manage.sh update
10. 健康检查:   ./manage.sh health
11. 日志检查:   ./manage.sh logs
12. 状态检查:   ./manage.sh status
```

---

## 六、回滚方案

每个阶段修改前，创建 git 分支：

- 阶段 1: `fix/manage-sh-p0-security`
- 阶段 2: `fix/manage-sh-p1-atomicity`
- 阶段 3: `fix/manage-sh-p2-robustness`

若任何阶段验证失败：
1. `git checkout main -- manage.sh` 恢复到修改前状态
2. 重新执行完整业务链验证确认系统正常
3. 分析失败原因，调整修改后重新执行

---

## 七、假设与决策

1. **假设**: 宿主机为 Linux 系统，bash >= 4.0（支持 `printf -v`）
2. **假设**: 宿主机已安装 `flock`（util-linux 包），若未安装则回退到文件锁
3. **假设**: Docker Compose V2（`docker compose` 而非 `docker-compose`）
4. **决策**: `auto_backup` 失败时，upgrade/update 阻止操作，restore 不阻止（restore 本身是恢复手段）
5. **决策**: `_configure_dev_env` 保留覆盖行为但增加 `--reset-env` 选项（P2 阶段再改）
6. **决策**: Redis 恢复逻辑修改放在 P2，因为需要深入理解 Docker volume 挂载路径
7. **决策**: 所有修改仅涉及 manage.sh 单一文件，不涉及后端/前端代码变更
