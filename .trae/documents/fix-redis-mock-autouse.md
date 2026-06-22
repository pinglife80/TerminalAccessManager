# 修复 Redis 不可用导致认证测试失败

> 文档版本：v3.3.0 | 更新日期：2026-06-17

## 问题

3 个认证测试失败（test_get_current_user, test_refresh_token, test_logout），因为 `is_token_blacklisted()` 在 Redis 不可用时返回 `True`（fail-closed），所有 token 被拒绝。

## 根因

`conftest.py` 定义了 `mock_redis` 和 `mock_redis_patch` fixture，但 `mock_redis_patch` 不是 `autouse`，`test_auth.py` 也没有引用它。测试时 Redis 连接失败 → fail-closed → token 被拒。

## 修复方案

将 `mock_redis_patch` 改为 `autouse=True`，所有测试自动获得 Redis mock。

### 修改文件

`backend/tests/conftest.py`：将 `mock_redis_patch` fixture 改为 `autouse=True`

### 不采用的方案

1. **fail-open 策略**：修改 `is_token_blacklisted()` 在非生产环境返回 `False` — 这会降低安全测试覆盖率，且生产环境行为与测试不一致
2. **在 test_auth.py 中单独添加 fixture** — 其他测试文件也会遇到同样问题，autouse 更彻底

## 实施步骤

1. 编辑 conftest.py，给 mock_redis_patch 添加 `autouse=True`
2. 提交并推送
