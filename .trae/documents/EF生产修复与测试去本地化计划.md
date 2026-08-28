# E/F 生产代码修复与测试环境去本地化计划

> 文档版本：规划稿  更新日期：2026-08-26

## 1. 摘要（Summary）

本轮计划完成两件事：

1. **修复 E、F 两处生产代码 bug**（用户已确认「规划并实现 E、F」）：
   - E：`local_provider.py` 缺失 `await`，导致本地账号登录完全失效。
   - F：`notification_service.py` 的 `_log_notification` 丢弃注入的 `self.db` session，破坏请求级事务一致性。
2. **补充测试环境说明**（用户已确认「沿用 manage.sh test」）：
   - 在 `docs/manage-sh-reference.md` 的 `test` 命令章节写明「测试在 backend Docker 容器内运行，本地无需 Python/venv/依赖」，不改动测试基础设施。

## 2. 现状分析（Current State Analysis）

### 2.1 E — 本地登录失效（高危）

文件：`backend/app/services/auth_providers/local_provider.py`

- 第 55 行 `authenticate()`：`user = result.scalar_one_or_none()` 缺少 `await`。
- 第 102 行 `get_user_info()`：`user = result.scalar_one_or_none()` 缺少 `await`。

SQLAlchemy 异步模式下 `scalar_one_or_none()` 返回协程，未 `await` 时 `user` 恒为协程对象（恒真），随后访问 `user.is_active` / `user.id` 抛 `AttributeError`，被外层 `except` 捕获并统一返回失败。结果是**本地账号登录与用户信息查询全部失效**（生产环境所有 local 用户无法登录）。修复仅补 `await`，低风险、高价值。

### 2.2 F — 通知日志 session 被丢弃（事务一致性 bug）

文件：`backend/app/services/notification_service.py`

- 第 337 行 `_log_notification()`：`await logger_inst.log_notification(event, channel_name, result)` 未传入 `self.db`。
- 下游 `NotificationLogger.log_notification/log_sent/log_failed` 的 `db` 形参收到 `None`，于是即便在「请求级 session」模式下也绕开注入 session，改走 `async_session_factory()` 新开会话。

影响：通知日志写入发生在独立于请求事务的 session 中，日志与业务操作不再同事务；测试注入 mock session 时日志被写入真实 session，等价于日志「丢失」（对应 `test_log_notification` 失败）。修复为在 `_log_notification` 中显式传入 `self.db`。

### 2.3 测试环境（已基本去本地化）

- `manage.sh` 已有 `test` 命令：`dc exec -T backend python -m pytest tests/`（在 backend Docker 容器内跑）。
- `.github/workflows/ci.yml` 的 `backend-test` 在 GitHub Actions 用 `pip install -r requirements.txt` 后跑 pytest，也不依赖本地。
- `pytz`/`jinja2`/`pytest` 等均已在 `backend/requirements.txt` 声明；本地 `.venv` 缺 pytz/jinja2 只是本地环境未装全，非代码问题。
- 现有 `docs/manage-sh-reference.md` 第 547–554 行 `3.1 test` 章节只给了命令格式，未说明「在容器内运行、本地无需依赖」，需补充。

## 3. 拟议变更（Proposed Changes）

### 3.1 `backend/app/services/auth_providers/local_provider.py`（E）

- 第 55 行：`user = result.scalar_one_or_none()` → `user = await result.scalar_one_or_none()`
- 第 102 行：`user = result.scalar_one_or_none()` → `user = await result.scalar_one_or_none()`

原因：补上 SQLAlchemy 异步调用缺失的 `await`，恢复本地登录与用户信息查询。

### 3.2 `backend/app/services/notification_service.py`（F）

- 第 337 行：
  `await logger_inst.log_notification(event, channel_name, result)`
  → `await logger_inst.log_notification(event, channel_name, result, self.db)`

原因：把注入的请求级 session 传给日志器，保证日志写入与请求同 session/事务。单例模式（`self.db is None`）下语义不变，仍走 `async_session_factory()`。

### 3.3 `docs/manage-sh-reference.md`（测试说明）

- 在第 547–554 行 `3.1 test — 运行测试` 章节中，补充说明（在现有命令格式后追加，不改动结构）：
  - `./manage.sh test` 在 backend Docker 容器内执行 pytest（`dc exec -T backend python -m pytest tests/`）。
  - 仅需本地 Docker 与已构建的 backend 镜像，**无需本地 Python/venv/pip 依赖**。
  - 服务未启动时命令会先 `dc up -d` 并等待 postgres/redis/backend 就绪；单元测试已 mock 数据库与 Redis，不依赖真实数据。
  - CI 的 `backend-test` 作业在 GitHub Actions 运行同一套测试用例，可作为远程验证兜底。

## 4. 假设与决策（Assumptions & Decisions）

- E 修复同时覆盖 `authenticate` 与 `get_user_info` 两处（同一根因，均缺 `await`）。
- F 修复范围仅为 `log_notification` 链路（对应失败测试与 summary 中的 F）。`_render_template`（第 346 行）存在同样「未传 db」的模式，但**不在本轮范围内**，仅记录不处理，避免扩大改动边界。
- 测试基础设施不新增/不改动（沿用 `manage.sh test`），本轮仅补文档说明。
- 不改动 `requirements.txt`、CI、Dockerfile、manage.sh 逻辑。

## 5. 验证（Verification）

1. 触达后端容器的测试入口（本机只需 Docker）：
   ```bash
   ./manage.sh test
   ```
   预期：`test_auth_providers.py` 的 `test_authenticate_success`、`test_authenticate_invalid_password` 由失败转通过；`test_notification_service.py` 的 `test_log_notification` 由失败转通过；无新增失败。
2. 如需只跑受影响用例（容器已运行时）：
   ```bash
   ./manage.sh shell backend   # 或 docker compose exec backend bash
   python -m pytest tests/test_auth_providers.py tests/test_notification_service.py -v
   ```
3. 拉取诊断确认无语法/类型问题：`GetDiagnostics` 或 `ruff check`（如有需要）。