# 生产模式部署可行性审查与修复计划 (v3.10.2)

> 审查目标：`manage.sh deploy --prod` 在生产环境是否能完整端到端运行？
> 审查方法：代码静态深度审查 + 2 个子代理独立交叉验证（高置信度共识）
> 审查时间：2026-08-06

---

## 一、审查结论（总览）

| 分类 | 数量 | 说明 |
|------|------|------|
| **CRITICAL 致命** | 1 | 必须修复，否则生产部署存在严重安全漏洞 |
| **HIGH 高危** | 1 | 配置冲突，会导致数据丢失或加固策略失效 |
| **MEDIUM 中危** | 3 | 功能正确性问题 / 脆弱性 / 幂等性 |
| **LOW 低危** | 2 | UX 不一致 / 验证顺序不够严谨 |

**总体评估：当前生产模式部署** ❌ **不可行，存在严重安全问题和数据风险。**

---

## 二、问题清单（按严重性排序）

### 🟥 ISSUE-1 [CRITICAL] admin 密码被硬编码为 `Admin123`，.env 中 `ADMIN_PASSWORD` 完全失效

- **验证共识**：2/2 验证者确认（置信度 100%）
- **影响范围**：[cli.py `_create_admin_user()`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L49-L84)
- **证据**：
  - `cli.py:65` → `hashed_password=hash_password("Admin123")`
  - 整个 `_create_admin_user()` 函数**从未读取** `os.environ["ADMIN_PASSWORD"]` 或任何环境变量
  - 对应 [manage.sh 生产向导](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L1113-L1117) 让用户输入的 `ADMIN_PASSWORD` 只写入 `.env`，**绝不传递给 `cli.py setup`**
- **后果**：
  1. 生产模式下用户设置的强管理员密码被完全忽略
  2. 部署后 Web 登录密码永远是 `Admin123`（公开已知弱密码）
  3. [manage.sh 部署摘要 `L989-992`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L989-L992) 显示 `Login: admin / [password you set]` — 这是**严重的误导性输出**
  4. 用户后续用 `manage.sh password reset admin newpass` 才能修正，但新部署的前几分钟系统对任何知道 `Admin123` 的人敞开大门

---

### 🟧 ISSUE-2 [HIGH] backend 加固冲突：`docker-compose.prod.yml` 的 `tmpfs: /app/uploads` 与基础 compose 的 `tam-uploads` 命名卷目标路径重叠

- **验证共识**：2/2 验证者确认冲突存在（1/2 认为 tmpfs 优先会丢数据；另 1/2 认为命名卷优先导致加固形同虚设）
- **影响范围**：[docker-compose.prod.yml `L22-L26`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.prod.yml#L22-L26) + [docker-compose.yml `L130-L134`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/docker-compose.yml#L130-L134)
- **证据**：
  - 基础配置：`volumes: tam-uploads:/app/uploads`（持久化命名卷，可写）
  - 生产加固：`tmpfs: [/tmp, /app/uploads]`（内存文件系统，容器重启即丢）
- **Docker Compose 合并语义实际行为**：同路径存在 `tmpfs` 和 `volume` 属于**未定义行为**，不同 Compose 版本表现不同。结果不可预测：
  - **场景 A（tmpfs 优先）**：备份文件 (`/app/uploads/backups`)、自定义品牌资源 (`/app/uploads/branding`)、所有导入导出 **容器重启即丢失** → 数据灾难
  - **场景 B（命名卷优先）**：`read_only: true` 对 `/app/uploads` 路径完全不起作用 → 加固形同虚设
- **修复方向**：从 `docker-compose.prod.yml` 的 `tmpfs` 列表中**删除 `/app/uploads`**（命名卷已提供持久化可写路径，这正是我们想要的）。仅保留 `tmpfs: [/tmp]`。

---

### 🟨 ISSUE-3 [MEDIUM] `UPLOAD_DIR="./uploads"` 相对路径在代码中与硬编码绝对路径混用

- **验证共识**：2/2 验证者确认（置信度 100%）
- **影响范围**：[config.py `L87`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/core/config.py#L87) + [backup_service.py `L95, L547-L548, L575-L576`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/app/services/backup_service.py#L547-L548)
- **证据**：
  - `config.py:87` → `UPLOAD_DIR: str = "./uploads"`（相对，解析取决于 cwd）
  - `backup_service.py:547` → `getattr(settings, 'UPLOAD_DIR', '/app/uploads')`（兜底是绝对路径 `/app/uploads`）
  - 另有多处 `os.path.join(settings.UPLOAD_DIR, ...)`
- **脆弱性**：
  - 当前 `backend/Dockerfile WORKDIR=/app`（`L4` 和 `L18`）所以碰巧都解析到 `/app/uploads`
  - **一旦 Dockerfile 或 cli.py 启动方式改变 cwd**（例如从 `/tmp` 运行 `python /app/cli.py setup`），相对路径解析立刻出错，上传写入失败
- **修复方向**：`config.py` 改为 `UPLOAD_DIR = "/app/uploads"`（绝对路径，单一真相源）；backup_service 删除 `/app/uploads` 的硬编码兜底，统一从 settings 读。

---

### 🟨 ISSUE-4 [MEDIUM] `cli.py setup` 打印的提示与 `manage.sh deploy` 实际场景不一致

- **验证共识**：2/2 验证者确认（置信度 100%）
- **影响范围**：[cli.py `_run_setup()` L116-L119](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L116-L119)
- **证据**：
  ```
  Next steps:
  1. Start the application: docker-compose up -d   ← 容器已经在运行了！
  2. Access the API docs: http://localhost:8000/api/v1/docs  ← 该端口只在 compose 127.0.0.1 暴露
  ```
- **上下文**：[manage.sh `L875`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L875) 先 `dc up -d --build`，在 `L931` 才执行 `dc exec -T backend python cli.py setup` — 所以 setup 执行时容器已经启动完毕。
- **修复方向**：新增 `--context docker` / 读取 `ENVIRONMENT` 环境变量，动态打印对应提示：
  - docker/managed 场景：提示 "容器已启动，访问 https://host:8443"
  - 裸机/local 场景：保留原提示

---

### 🟨 ISSUE-5 [MEDIUM] `is_initialized()` 只看本地 state 文件，不验证数据库实际状态

- **验证共识**：2/2 验证者确认（置信度 100%）
- **影响范围**：[manage.sh `is_initialized() L172-L174`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L172-L174)
- **证据**：
  - 逻辑：`get_state 'db_initialized' == 'true'` 即判定已初始化
  - 不查询数据库的 user / role / settings 表
- **风险场景**：
  - 用户删除命名卷 `postgres_data`（DB 重置）
  - 但保留 `.tam_state/state.env`（或 `.env`）
  - 重新 `deploy --prod` → 直接跳过 setup → **DB 完全空，没有 admin 账号，无法登录**
- **补充说明**：`cli.py setup` 本身是幂等的（`_create_admin_user` 先查 `User.username == "admin"`，存在就跳过），所以重复执行 setup 无害。
- **修复方向**：`deploy` 流程在调用 setup 前增加一个 DB 侧探测：`dc exec -T backend python -c "from sqlalchemy import text; ... SELECT 1 FROM users WHERE username='admin' LIMIT 1"`。查得到 admin 才 skip，否则强制重跑 setup（即使 state 文件标记 true）。

---

### 🟩 ISSUE-6 [LOW] 部署验证 HTTP/HTTPS 顺序不区分 dev/prod 模式

- **验证共识**：2/2 验证者确认（验证者 1 判定 LOW，验证者 2 判定 MEDIUM — 实际功能都有 fallback 所以归 LOW）
- **影响范围**：[manage.sh `L960-L970`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/manage.sh#L960-L970)
- **表现**：
  - Dev 模式：Nginx 只有 HTTP 8080（[tam.dev.conf](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/nginx/etc/conf.d/tam.dev.conf#L18-L30)），每次验证先失败 1 次 HTTPS 探测（超时/拒绝），再 fallback HTTP 通过 → 不必要的等待和日志噪音
  - Prod 模式：顺序是对的（HTTPS 优先）
- **修复方向**：按已保存的 `deploy_mode` 状态来走不同顺序
  - prod：HTTPS 8443 → fallback HTTP 8080 看 redirect（当前行为，不变）
  - dev：HTTP 8080 直接测（一步到位）

---

### 🟩 ISSUE-7 [LOW] `cli.py setup` 成功时显示的密码与 ISSUE-1 呼应

- **影响范围**：[cli.py `L78-L81`](file:///home/dada/Codespace/TraeCN/TerminalAccessManager/backend/cli.py#L78-L81)
- **证据**：
  ```python
  print("  Username: admin")
  print("  Password: Admin123 (CHANGE THIS IMMEDIATELY!)")
  ```
- 修复 ISSUE-1 后，这里应同步改为从环境变量读取并实际显示用户设置的密码（prod 模式）或仍显示 Admin123（dev 模式）。

---

## 三、修复实施步骤

### Step 1: 修复 CRITICAL (ISSUE-1 + ISSUE-7) — admin 密码读取环境变量 + 注入缺失变量

**文件**：
1. `backend/cli.py`
   - 修改 `_create_admin_user()`：
     - 读取 `os.environ.get("ADMIN_PASSWORD")`
     - 若 `ENVIRONMENT=production` 且 `ADMIN_PASSWORD` 为空/为 `Admin123` → 抛出警告甚至失败（强制用户用强密码）
     - dev 模式 fallback 到 `Admin123`（兼容）
   - 修改 setup 成功时的密码打印：
     - 若 password != 原始环境变量则不打印实际密码（安全），只打印提示；dev 模式或环境变量存在时打印实际密码

2. **`docker-compose.yml`（新增！前置检查已确认：变量缺失）**
   - 在 backend 的 `environment:` 块中**新增两行注入**：
     - `ADMIN_PASSWORD: "${ADMIN_PASSWORD:-}"`
     - `ENVIRONMENT: "${ENVIRONMENT:-development}"`
   - 否则 cli.py 即使改了也读不到值，ISSUE-1 修复完全无效

### Step 2: 修复 HIGH (ISSUE-2) — 移除冲突的 tmpfs 条目

**文件**：`docker-compose.prod.yml`
- `backend` 服务 `tmpfs` 列表改为仅 `[/tmp]`，**删除 `/app/uploads`**
- `backend` 的 `volumes` 由基础 compose 的 `tam-uploads:/app/uploads` 和 `tam-logs:/var/log/tam` 接管（它们在 read_only 世界中是可写的例外，这是正确设计）

### Step 3: 修复 MEDIUM (ISSUE-3) — 统一 UPLOAD_DIR 为绝对路径

**文件**：
1. `backend/app/core/config.py` — `UPLOAD_DIR: str = "/app/uploads"`
2. `backend/app/services/backup_service.py` — 删除所有 `getattr(settings, 'UPLOAD_DIR', '/app/uploads')`，统一直接用 `settings.UPLOAD_DIR`

### Step 4: 修复 MEDIUM (ISSUE-4) — setup 提示上下文感知

**文件**：`backend/cli.py`
- 新增 `ENVIRONMENT` env var 判断：
  - `production` 或存在 `container=docker` 标记 → 提示 "系统已启动，访问 https://host:8443"
  - 否则保留原提示

### Step 5: 修复 MEDIUM (ISSUE-5) — setup 幂等性升级

**文件**：`manage.sh`
- 在 deploy Step 6/6 (`L926-938`) 中：
  - 先尝试 DB 探测 admin 账号是否存在
  - 只有 DB 探测失败才看 state 文件
  - 两者都显示"未初始化"才真正执行 `cli.py setup`

### Step 6: 修复 LOW (ISSUE-6) — 验证顺序模式化

**文件**：`manage.sh`
- `L960` 前加判断：读取 `get_state 'deploy_mode'`
- dev：直接 HTTP 8080
- prod：先 HTTPS 再 fallback HTTP

---

## 四、风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| ISSUE-1 修复后，某些场景 ADMIN_PASSWORD env 没传到容器 | 中 | admin 创建失败 | docker-compose.yml 已在 backend env 中显式传递 `ADMIN_PASSWORD` 吗？→ **需要检查当前 docker-compose.yml 是否注入该变量** |
| ISSUE-2 移除 /app/uploads tmpfs 后，某些恶意代码写入 /app/uploads 持久化 | 低 | 加固变弱但正确 | 这是正确取舍：备份/品牌资源必须持久化。read_only 根文件系统 + 精确的可写目录白名单才是最佳实践 |
| ISSUE-3 改绝对路径后，本地裸机开发不再工作 | 低 | 破坏开发者体验 | 允许 `UPLOAD_DIR` 被 env var 覆盖；Dockerfile 通过 env 注入 `/app/uploads`，本地无 env 时 fallback 到 `./uploads` |

---

## 五、已完成的前置检查结果

1. **`ADMIN_PASSWORD` 是否注入 backend？** → ❌ **已确认缺失**，已加入 Step 1.2 修改 docker-compose.yml
2. **`ENVIRONMENT` 是否注入 backend？** → ❌ **已确认缺失**，已加入 Step 1.2 修改 docker-compose.yml
3. 运行一次完整端到端 `./manage.sh deploy --prod` 冒烟测试（实施后做，需要隔离环境）。

---

## 六、发布后验证清单（执行修复后）

```bash
# ☐ deploy 流程不报错
./manage.sh deploy --prod

# ☐ 登录验证：用生产向导输入的密码，NOT Admin123
curl -X POST https://localhost:8443/api/v1/login -d '{"username":"admin","password":"USER_SET_PASS"}'

# ☐ /app/uploads 是命名卷（不是 tmpfs），容器重启后文件仍在
echo test > /tmp/test.txt
dc cp /tmp/test.txt backend:/app/uploads/test.txt
dc restart backend
dc exec backend cat /app/uploads/test.txt   # 应打印 'test'

# ☐ setup 输出的提示与实际场景匹配
# ☐ 重新 deploy（不清除数据）不重复初始化、不报错
# ☐ 清除 postgres_data 卷后重新 deploy，会正确重新执行 setup（不因 state 文件跳过）
```
