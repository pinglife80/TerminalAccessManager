# TerminalAccessManager API 文档

> 文档版本：v3.2.0-r8 | 更新日期：2026-06-16

> 基于 MAC 地址和 IP 地址的网络终端准入管理平台

> 本文档中所有 API 示例使用 `<HOST_IP>` 代表实际部署主机 IP 地址，本机部署时替换为 `localhost`。
> API 通过 Nginx 反向代理对外提供，基础路径为 `https://<HOST_IP>:8443/api/v1`。

- 基础路径：`/api/v1`
- 认证方式：Bearer Token（JWT）
- 内容类型：`application/json`（文件上传除外）

> 每个请求响应头包含 `X-Request-ID`，用于链路追踪

---

## 目录

- [通用约定](#通用约定)
- [1. 认证模块 /auth](#1-认证模块-auth)
- [2. 用户管理 /auth/users](#2-用户管理-authusers)
- [3. 终端管理 /terminals](#3-终端管理-terminals)
- [4. 白名单管理 /whitelist](#4-白名单管理-whitelist)
- [5. 黑名单管理 /blacklist](#5-黑名单管理-blacklist)
- [6. 数据源管理 /data-sources](#6-数据源管理-data-sources)
- [7. 数据源绑定 /data-sources/bindings](#7-数据源绑定-data-sourcesbindings)
- [8. 合规操作 /data-sources/compliance](#8-合规操作-data-sourcescompliance)
- [9. 合规基准管理 /compliance-baselines](#9-合规基准管理-compliance-baselines)
- [10. 审计日志 /logs](#10-审计日志-logs)
- [11. 统计 /stats](#11-统计-stats)
- [12. 系统设置 /settings](#12-系统设置-settings)
- [13. 角色管理 /roles](#13-角色管理-roles)
- [14. 权限码参考](#14-权限码参考)
- [15. 健康检查 /health](#15-健康检查-health)

---

## 通用约定

### 认证方式

除标注为"公开"的端点外，所有请求须在 Header 中携带：

```
Authorization: Bearer <access_token>
```

### 认证级别说明

| 级别 | 说明 |
|------|------|
| 公开 | 无需认证 |
| 需认证 | 需要有效的 access_token |
| 超管专用 | 需要有效的 access_token 且用户 is_superuser = true |
| 超管专用（新增） | 原需认证的审计日志导出端点已升级为超管专用 |

### 通用错误响应

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证或 Token 无效/过期 |
| 403 | 权限不足（非超管访问超管端点，或账户被禁用） |
| 404 | 资源不存在 |
| 423 | 账户已锁定 |
| 429 | 请求频率超限 |

```json
{
  "detail": "错误描述信息"
}
```

> **注意**：未捕获异常的 `detail` 可能为对象格式 `{"message": "错误描述", "error_id": "xxx"}`，前端 `getErrorMessage` 已处理此情况。

### 分页参数

多个列表端点支持统一的分页参数：

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| skip | int | 0 | >= 0 | 跳过记录数 |
| limit | int | 50 | 1-200 | 每页记录数 |

---

## 1. 认证模块 /auth

### 1.1 POST /auth/login

用户登录，获取 access_token 和 refresh_token。

- **认证要求**：公开
- **Content-Type**：`application/x-www-form-urlencoded`（OAuth2 标准表单）

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| username | Body (form) | string | 是 | 用户名 |
| password | Body (form) | string | 是 | 密码 |
| captcha | Query | string | 否 | 验证码（多次失败后必填） |

**登录流程**

1. 检查账户是否锁定 -> 锁定则返回 423
2. 检查是否需要验证码 -> 需要但未提供则返回 400
3. 验证用户名是否存在 -> 不存在返回 401（并记录失败次数）
4. 验证密码 -> 错误返回 401（并记录失败次数）
5. 检查账户是否禁用 -> 禁用返回 403
6. 登录成功，重置失败计数，返回令牌

> **审计日志**：登录成功时记录 `login` 操作，登录失败时记录 `login_failed` 操作，均包含客户端 IP 地址。

**成功响应** `200`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 需要验证码：`{"detail": {"message": "Captcha verification is required...", "captcha_required": true}}` |
| 401 | 用户名不存在或密码错误：`{"detail": {"message": "Invalid credentials", "captcha_required": true/false}}` |
| 403 | 账户被禁用 |
| 423 | 账户已锁定：`{"detail": {"message": "Account locked...", "locked": true, "lock_remaining": 900}}` |

**用例**

```bash
# 基本登录
curl -X POST https://<HOST_IP>:8443/api/v1/auth/login \
  -d "username=admin&password=MyPass123"

# 携带验证码登录
curl -X POST "https://<HOST_IP>:8443/api/v1/auth/login?captcha=abc123" \
  -d "username=admin&password=MyPass123"
```

---

### 获取验证码

`GET /auth/captcha`

**认证级别：** 公开

生成服务端算术验证码，答案存入 Redis（5 分钟 TTL）。

**响应示例：**

```json
{
  "captcha_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "3 + 5 = ?"
}
```

> 验证码为一次性使用，验证后自动删除。每次登录失败后应重新获取。

---

### 1.2 POST /auth/register

用户注册。生产环境默认禁用，由 `ALLOW_REGISTRATION` 配置控制。

- **认证要求**：公开

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| username | string | 是 | 3-50字符，仅字母/数字/下划线 | 用户名 |
| email | string | 否 | - | 邮箱（唯一） |
| password | string | 是 | 8-128字符，需含大小写字母和数字 | 密码 |

**成功响应** `201`

```json
{
  "id": 2,
  "username": "newuser",
  "email": "user@example.com",
  "is_active": true,
  "is_superuser": false
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 用户名或邮箱已存在；密码强度不足 |
| 403 | 注册功能已关闭 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "email": "user@example.com",
    "password": "SecurePass123"
  }'
```

---

### 1.3 GET /auth/me

获取当前登录用户信息。

- **认证要求**：需认证

**成功响应** `200`

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "is_active": true,
  "is_superuser": true
}
```

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

### 1.4 POST /auth/refresh

刷新令牌。旧 refresh_token 自动加入黑名单。

- **认证要求**：公开（通过 refresh_token 鉴权）

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| refresh_token | Body | string | 是 | 刷新令牌 |

**成功响应** `200`

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 401 | refresh_token 无效、已撤销或用户不存在/禁用 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<old_refresh_token>"}'
```

---

### 1.5 POST /auth/logout

登出，当前 access_token 加入黑名单。

- **认证要求**：需认证

> **审计日志**：登出成功时记录 `logout` 操作，包含客户端 IP 地址。

**成功响应** `200`

```json
{
  "message": "Successfully logged out",
  "success": true
}
```

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/auth/logout \
  -H "Authorization: Bearer <access_token>"
```

---

### 1.6 PUT /auth/me/profile

更新当前用户个人资料（邮箱）。

- **认证要求**：需认证

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 否 | 新邮箱（需唯一） |

**成功响应** `200`

```json
{
  "id": 1,
  "username": "admin",
  "email": "newemail@example.com",
  "is_active": true,
  "is_superuser": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 邮箱已被其他用户使用 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/auth/me/profile \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "newemail@example.com"}'
```

---

### 1.7 PUT /auth/me/password

修改当前用户密码，需验证旧密码。

- **认证要求**：需认证

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| current_password | string | 是 | - | 当前密码 |
| new_password | string | 是 | 8-128字符，需含大小写字母和数字 | 新密码 |

**成功响应** `200`

```json
{
  "message": "Password changed successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 当前密码错误；新密码强度不足 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/auth/me/password \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "OldPass123",
    "new_password": "NewPass456"
  }'
```

---

## 2. 用户管理 /auth/users

以下端点均为超管专用。

> **审计日志**：用户管理操作均记录审计日志，action 值包括 `create_user`、`update_user`、`delete_user`、`reset_password`、`unlock_user`，details 包含操作对象及变更内容。

### 2.1 GET /auth/users

列出用户，支持搜索和状态过滤。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| search | Query | string | 否 | 按用户名或邮箱模糊搜索 |
| is_active | Query | bool | 否 | 按启用状态过滤 |

**成功响应** `200`

```json
[
  {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "is_active": true,
    "is_superuser": true,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  }
]
```

**用例**

```bash
# 列出所有用户
curl https://<HOST_IP>:8443/api/v1/auth/users \
  -H "Authorization: Bearer <access_token>"

# 搜索用户
curl "https://<HOST_IP>:8443/api/v1/auth/users?search=john&is_active=true" \
  -H "Authorization: Bearer <access_token>"
```

---

### 2.2 POST /auth/users

创建用户。

- **认证要求**：超管专用

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| username | string | 是 | 3-50字符，仅字母/数字/下划线 | 用户名 |
| email | string | 否 | - | 邮箱（唯一） |
| password | string | 是 | 8-128字符，需含大小写字母和数字 | 密码 |
| is_active | bool | 否 | 默认 true | 启用状态 |
| is_superuser | bool | 否 | 默认 false | 超管状态 |

**成功响应** `201`

```json
{
  "id": 3,
  "username": "newadmin",
  "email": "newadmin@example.com",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2025-06-01T12:00:00Z",
  "updated_at": "2025-06-01T12:00:00Z"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 用户名或邮箱已存在；密码强度不足 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/auth/users \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "operator",
    "email": "op@example.com",
    "password": "SecurePass123",
    "is_active": true,
    "is_superuser": false
  }'
```

---

### 2.3 GET /auth/users/{user_id}

获取指定用户详情。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| user_id | Path | int | 是 | 用户 ID |

**成功响应** `200`

```json
{
  "id": 2,
  "username": "operator",
  "email": "op@example.com",
  "is_active": true,
  "is_superuser": false,
  "created_at": "2025-06-01T12:00:00Z",
  "updated_at": "2025-06-01T12:00:00Z"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 用户不存在 |

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/auth/users/2 \
  -H "Authorization: Bearer <access_token>"
```

---

### 2.4 PUT /auth/users/{user_id}

更新用户信息。防止自我降级和自我禁用。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| user_id | Path | int | 是 | 用户 ID |

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 否 | 新邮箱（需唯一） |
| is_active | bool | 否 | 启用状态 |
| is_superuser | bool | 否 | 超管状态 |

**业务规则**

- 不能移除自己的超管权限
- 不能禁用自己的账户

**成功响应** `200`

```json
{
  "id": 2,
  "username": "operator",
  "email": "newop@example.com",
  "is_active": true,
  "is_superuser": true,
  "created_at": "2025-06-01T12:00:00Z",
  "updated_at": "2025-06-08T10:00:00Z"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 不能自我降级/自我禁用；邮箱已被使用 |
| 404 | 用户不存在 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/auth/users/2 \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newop@example.com",
    "is_superuser": true
  }'
```

---

### 2.5 DELETE /auth/users/{user_id}

删除用户。不能删除自己。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| user_id | Path | int | 是 | 用户 ID |

**成功响应** `200`

```json
{
  "message": "User 'operator' deleted successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 不能删除自己 |
| 404 | 用户不存在 |

**用例**

```bash
curl -X DELETE https://<HOST_IP>:8443/api/v1/auth/users/2 \
  -H "Authorization: Bearer <access_token>"
```

---

### 2.6 PUT /auth/users/{user_id}/password

重置用户密码。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| user_id | Path | int | 是 | 用户 ID |

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| new_password | string | 是 | 8-128字符，需含大小写字母和数字 | 新密码 |

**成功响应** `200`

```json
{
  "message": "Password for 'operator' reset successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 用户不存在 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/auth/users/2/password \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"new_password": "ResetPass123"}'
```

---

### 2.7 POST /auth/users/{user_id}/unlock

解锁用户账户，清除 Redis 中的锁定和失败计数。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| user_id | Path | int | 是 | 用户 ID |

**成功响应** `200`

```json
{
  "message": "Account 'operator' unlocked successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 用户不存在 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/auth/users/2/unlock \
  -H "Authorization: Bearer <access_token>"
```

---

## 3. 终端管理 /terminals

### 3.1 GET /terminals/

获取终端列表（分页）。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| skip | Query | int | 0 | 跳过记录数 |
| limit | Query | int | 50 | 每页记录数（1-200） |

**成功响应** `200`

```json
[
  {
    "id": 1,
    "ip_address": "192.168.1.100",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "status": "unblocked",
    "timestamp": "2025-06-01T10:00:00Z",
    "source": "arp",
    "source_tag": "switch-1f",
    "compliance_status": "unknown",
    "wl_match_type": null,
    "comments": null
  }
]
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/terminals/?skip=0&limit=20" \
  -H "Authorization: Bearer <access_token>"
```

---

### 3.2 GET /terminals/search

搜索终端，支持多条件过滤。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| ip | Query | string | 否 | 按 IP 地址模糊搜索（ILIKE） |
| mac | Query | string | 否 | 按 MAC 地址模糊搜索（ILIKE） |
| compliance_status | Query | string | 否 | 按合规状态过滤（compliant/bypass/non_compliant/unknown） |
| status | Query | string | 否 | 按状态过滤（blocked/unblocked） |
| start_date | Query | string | 否 | 起始日期（YYYY-MM-DD） |
| end_date | Query | string | 否 | 截止日期（YYYY-MM-DD） |
| skip | Query | int | 0 | 跳过记录数 |
| limit | Query | int | 50 | 每页记录数（1-200） |
| source_tag | Query | string | 否 | 按数据源标签过滤终端 |
| firewall_tag | Query | string | 否 | 按防火墙标签过滤终端（通过 Blacklist 子查询） |

> IP 和 MAC 参数使用 ILIKE 模糊搜索，同时提供时使用 OR 逻辑（任一匹配即返回）。

**成功响应** `200`

```json
{
  "items": [
    {
      "id": 1,
      "ip_address": "192.168.1.100",
      "mac_address": "AA:BB:CC:DD:EE:FF",
      "status": "unblocked",
      "timestamp": "2025-06-01T10:00:00Z",
      "source": "arp",
      "source_tag": "switch-1f",
      "compliance_status": "unknown",
      "wl_match_type": null,
      "comments": null
    }
  ],
  "total": 150,
  "skip": 0,
  "limit": 50
}
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/terminals/search?ip=192.168.1&compliance_status=non_compliant&start_date=2025-06-01&end_date=2025-06-08" \
  -H "Authorization: Bearer <access_token>"
```

---

### 3.3 POST /terminals/block/{ip_address}

封锁 IP 地址，通过深信服 AF 防火墙 API 执行。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| ip_address | Path | string | 是 | 要封锁的 IP 地址 |
| mac_address | Query | string | 是 | 关联的 MAC 地址 |
| block_time | Query | string | 否 | 封锁时长，默认 `30d`（如 30d/15d/7d/1h） |
| firewall_tag | Query | string | 否 | 防火墙标签，指定路由到哪个防火墙 |
| comments | Query | string | 否 | 封堵备注，写入 Terminal.comments 字段 |

**成功响应** `200`

```json
{
  "message": "IP 192.168.1.100 blocked successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 封锁失败（防火墙不可达等） |

**用例**

```bash
curl -X POST "https://<HOST_IP>:8443/api/v1/terminals/block/192.168.1.100?mac_address=AA:BB:CC:DD:EE:FF&block_time=7d&firewall_tag=sangfor-af1" \
  -H "Authorization: Bearer <access_token>"
```

---

### 3.4 POST /terminals/unblock/{ip_address}

解封 IP 地址。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| ip_address | Path | string | 是 | 要解封的 IP 地址 |
| firewall_tag | Query | string | 否 | 防火墙标签 |
| comments | Query | string | 否 | 解封备注，写入 Terminal.comments 字段 |

**成功响应** `200`

```json
{
  "message": "IP 192.168.1.100 unblocked successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 解封失败 |

**用例**

```bash
curl -X POST "https://<HOST_IP>:8443/api/v1/terminals/unblock/192.168.1.100?firewall_tag=sangfor-af1" \
  -H "Authorization: Bearer <access_token>"
```

---

### 3.5 GET /terminals/{terminal_id}

获取终端详情。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| terminal_id | Path | int | 是 | 终端记录 ID |

**成功响应** `200`

```json
{
  "id": 1,
  "ip_address": "192.168.1.100",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "status": "unfrozen",
  "timestamp": "2025-06-01T10:00:00Z",
  "source": "arp",
  "source_tag": "switch-1f",
  "compliance_status": "compliant",
  "wl_match_type": "mac",
  "comments": null
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 记录不存在 |

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/terminals/1 \
  -H "Authorization: Bearer <access_token>"
```

---

## 4. 白名单管理 /whitelist

### 4.1 GET /whitelist/

获取白名单列表，支持搜索和日期过滤。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| search | Query | string | 否 | 按 MAC、IP 或备注搜索 |
| start_date | Query | string | 否 | 起始日期（YYYY-MM-DD） |
| end_date | Query | string | 否 | 截止日期（YYYY-MM-DD） |
| skip | Query | int | 0 | 跳过记录数 |
| limit | Query | int | 50 | 每页记录数（1-200） |

> **MAC 地址格式无关搜索**：搜索 MAC 地址时，后端使用 `func.replace` 去除分隔符（`:`、`-`、`.`）后进行 ILIKE 匹配，因此输入 `AABBCCDDEEFF`、`AA:BB:CC:DD:EE:FF`、`AA-BB-CC-DD-EE-FF` 均可匹配同一条记录。

**成功响应** `200`

```json
{
  "items": [
    {
      "id": 1,
      "mac_address": "AA:BB:CC:DD:EE:FF",
      "ip_pattern": "192.168.1.0/24",
      "pattern_type": "cidr",
      "comments": "办公网段",
      "added_by": "admin",
      "created_at": "2025-06-01T10:00:00Z"
    }
  ],
  "total": 30,
  "skip": 0,
  "limit": 50
}
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/whitelist/?search=192.168&start_date=2025-06-01" \
  -H "Authorization: Bearer <access_token>"
```

---

### 4.2 POST /whitelist/

添加白名单条目。支持 MAC 地址、单 IP、CIDR 子网、IP 范围。

- **认证要求**：需认证

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mac_address | string | 否 | MAC 地址 |
| ip_address | string | 否 | 单 IP / CIDR / IP 范围（如 `192.168.1.1-192.168.1.50`） |
| comments | string | 否 | 备注 |

> mac_address 和 ip_address 至少提供一个。

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
| 400 | 添加失败（格式错误、重复等） |

**用例**

```bash
# 添加 MAC 地址白名单
curl -X POST https://<HOST_IP>:8443/api/v1/whitelist/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"mac_address": "AA:BB:CC:DD:EE:FF", "comments": "打印机"}'

# 添加 CIDR 白名单
curl -X POST https://<HOST_IP>:8443/api/v1/whitelist/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"ip_address": "192.168.1.0/24", "comments": "办公网段"}'

# 添加 IP 范围白名单
curl -X POST https://<HOST_IP>:8443/api/v1/whitelist/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"ip_address": "192.168.1.100-192.168.1.150", "comments": "DHCP 池"}'
```

---

### 4.3 DELETE /whitelist/{identifier}

删除白名单条目。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| identifier | Path | string | 是 | MAC 地址或 IP 模式 |

**成功响应** `200`

```json
{
  "message": "Successfully removed from whitelist",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 条目不存在 |

**用例**

```bash
curl -X DELETE https://<HOST_IP>:8443/api/v1/whitelist/AA:BB:CC:DD:EE:FF \
  -H "Authorization: Bearer <access_token>"

curl -X DELETE https://<HOST_IP>:8443/api/v1/whitelist/192.168.1.0/24 \
  -H "Authorization: Bearer <access_token>"
```

---

## 5. 黑名单管理 /blacklist

### 5.1 GET /blacklist/

获取黑名单列表，支持搜索和日期过滤。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| search | Query | string | 否 | 按 MAC 或 IP 搜索 |
| start_date | Query | string | 否 | 起始日期（YYYY-MM-DD） |
| end_date | Query | string | 否 | 截止日期（YYYY-MM-DD） |
| skip | Query | int | 0 | 跳过记录数 |
| limit | Query | int | 50 | 每页记录数（1-200） |

> **MAC 地址格式无关搜索**：搜索 MAC 地址时，后端使用 `func.replace` 去除分隔符（`:`、`-`、`.`）后进行 ILIKE 匹配，因此输入 `AABBCCDDEEFF`、`AA:BB:CC:DD:EE:FF`、`AA-BB-CC-DD-EE-FF` 均可匹配同一条记录。

**成功响应** `200`

```json
{
  "items": [
    {
      "id": 1,
      "ip_address": "192.168.1.200",
      "mac_address": "11:22:33:44:55:66",
      "reason": "未合规终端",
      "blocked_at": "2025-06-01T10:00:00Z",
      "expires_at": "2025-07-01T10:00:00Z",
      "blocked_by": "admin",
      "source_tag": "switch-1f",
      "firewall_tag": "sangfor-af1",
      "is_auto_blocked": false,
      "auto_unblocked": false
    }
  ],
  "total": 10,
  "skip": 0,
  "limit": 50
}
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/blacklist/?search=192.168&start_date=2025-06-01" \
  -H "Authorization: Bearer <access_token>"
```

---

### 5.2 POST /blacklist/

添加黑名单条目，同时在深信服 AF 防火墙上执行封锁。IP 和 MAC 至少提供一项。

- **认证要求**：需认证

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ip_address | string | 否 | IP 地址 |
| mac_address | string | 否 | MAC 地址 |
| reason | string | 否 | 封禁原因 |
| block_time | string | 否 | 封锁时长，默认 `30d`（如 15d/7d/1h） |
| firewall_tag | string | 否 | 防火墙标签，指定路由到哪个防火墙 |

> ip_address 和 mac_address 至少提供一个。

**成功响应** `201`

```json
{
  "message": "Added to blacklist and blocked successfully",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | IP 和 MAC 均未提供；添加失败 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/blacklist/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "192.168.1.200",
    "mac_address": "11:22:33:44:55:66",
    "reason": "违规终端",
    "block_time": "15d",
    "firewall_tag": "sangfor-af1"
  }'
```

---

### 5.3 DELETE /blacklist/{identifier}

删除黑名单条目，同时在深信服 AF 防火墙上执行解封。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| identifier | Path | string | 是 | MAC 地址或 IP 地址 |

**成功响应** `200`

```json
{
  "message": "Successfully unblocked terminal",
  "success": true
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 条目不存在 |

**用例**

```bash
curl -X DELETE https://<HOST_IP>:8443/api/v1/blacklist/192.168.1.200 \
  -H "Authorization: Bearer <access_token>"
```

---

## 6. 数据源管理 /data-sources

> **审计日志**：数据源管理操作均记录审计日志，action 值包括 `create_datasource`、`update_datasource`、`delete_datasource`、`test_datasource`、`sync_datasource`，details 包含数据源名称、标签及变更内容。

### 6.1 GET /data-sources/

列出数据源，支持按类型和启用状态过滤。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| type | Query | string | 否 | 数据源类型：arp_ssh / arp_api / sangfor |
| enabled | Query | bool | 否 | 按启用状态过滤 |

**成功响应** `200`

```json
[
  {
    "id": 1,
    "name": "1楼交换机SSH",
    "type": "arp_ssh",
    "tag": "switch-1f",
    "config": {"host": "192.168.1.1", "username": "readonly"},
    "enabled": true,
    "last_sync_at": "2025-06-08T10:00:00Z",
    "last_sync_status": "success",
    "last_sync_error": null,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-06-08T10:00:00Z"
  }
]
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/data-sources/?type=arp_ssh&enabled=true" \
  -H "Authorization: Bearer <access_token>"
```

---

### 6.2 POST /data-sources/

创建数据源。

- **认证要求**：超管专用

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| name | string | 是 | 最长100字符 | 数据源名称（唯一） |
| type | string | 是 | - | 类型：arp_ssh / arp_api / sangfor |
| tag | string | 是 | 最长50字符 | 唯一标签标识符 |
| config | object | 否 | JSON 对象 | 连接配置（见下方 config 参数说明） |
| enabled | bool | 否 | 默认 true | 是否启用 |

**config 参数说明：**

| 参数 | 类型 | 适用类型 | 说明 |
|------|------|---------|------|
| host | string | arp_ssh / arp_api | 主机地址 |
| port | int | arp_ssh / arp_api | 端口号（SSH 默认 22，API 默认 443） |
| username | string | arp_ssh / arp_api | 用户名 |
| password | string | arp_ssh / arp_api | 密码（Fernet 加密存储） |
| base_url | string | sangfor | 防火墙 API 地址 |
| auth_type | string | arp_api | 认证方式：`basic`（默认）/ `header`（Custom Header 认证） |
| header_name | string | arp_api | 自定义认证 Header 名称（`auth_type=header` 时必填，如 `X-API-Key`） |

**成功响应** `201`

```json
{
  "id": 2,
  "name": "深信服AF",
  "type": "sangfor",
  "tag": "sangfor-af1",
  "config": {"base_url": "https://10.0.0.1"},
  "enabled": true,
  "last_sync_at": null,
  "last_sync_status": null,
  "last_sync_error": null,
  "created_at": "2025-06-08T12:00:00Z",
  "updated_at": "2025-06-08T12:00:00Z"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 名称或标签重复；参数无效 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "1楼交换机SSH",
    "type": "arp_ssh",
    "tag": "switch-1f",
    "config": {
      "host": "192.168.1.1",
      "username": "readonly",
      "password": "secret",
      "port": 22
    },
    "enabled": true
  }'
```

---

### 6.3 GET /data-sources/{source_id}

获取数据源详情。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| source_id | Path | int | 是 | 数据源 ID |

**成功响应** `200`

返回格式同 [6.1 GET /data-sources/](#61-get-data-sources) 中的单条记录。

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 数据源不存在 |

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/data-sources/1 \
  -H "Authorization: Bearer <access_token>"
```

---

### 6.4 PUT /data-sources/{source_id}

更新数据源。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| source_id | Path | int | 是 | 数据源 ID |

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 数据源名称 |
| type | string | 否 | 数据源类型 |
| tag | string | 否 | 标签标识符 |
| config | object | 否 | 连接配置 |
| enabled | bool | 否 | 启用状态 |

**成功响应** `200`

返回更新后的完整数据源对象。

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 名称或标签重复；参数无效 |
| 404 | 数据源不存在 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/data-sources/1 \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

### 6.5 DELETE /data-sources/{source_id}

删除数据源。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| source_id | Path | int | 是 | 数据源 ID |

**成功响应** `204`（无内容）

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 数据源不存在 |

**用例**

```bash
curl -X DELETE https://<HOST_IP>:8443/api/v1/data-sources/1 \
  -H "Authorization: Bearer <access_token>"
```

---

### 6.6 POST /data-sources/{source_id}/test

测试数据源连接。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| source_id | Path | int | 是 | 数据源 ID |

**成功响应** `200`

```json
{
  "success": true,
  "message": "Connection successful",
  "details": null
}
```

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/1/test \
  -H "Authorization: Bearer <access_token>"
```

---

### 6.7 POST /data-sources/{source_id}/sync

手动触发数据源同步。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| source_id | Path | int | 是 | 数据源 ID |

**业务规则**

- 数据源必须处于启用状态
- 不同类型数据源的同步行为不同：
  - `arp_ssh`：通过 SSH（netmiko）收集 ARP 表，支持 Huawei/H3C/Cisco 自动设备类型检测
  - `arp_api`：通过 API 收集 ARP 表
  - `sangfor`：不适用。Sangfor 为推送型防火墙，无数据同步语义；前端已隐藏同步按钮，接口返回"Sync is not applicable"提示

**成功响应** `200`

```json
{
  "success": true,
  "message": "Sync completed",
  "entries_processed": 120,
  "entries_added": 5,
  "entries_updated": 3,
  "errors": []
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 数据源已禁用；不支持同步的类型 |
| 404 | 数据源不存在 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/1/sync \
  -H "Authorization: Bearer <access_token>"
```

---

## 7. 数据源绑定 /data-sources/bindings

### 7.1 GET /data-sources/bindings/

列出数据源绑定关系。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| arp_source_tag | Query | string | 否 | 按 ARP 数据源标签过滤 |

**成功响应** `200`

```json
[
  {
    "id": 1,
    "arp_source_tag": "switch-1f",
    "firewall_tag": "sangfor-af1",
    "created_at": "2025-06-01T10:00:00Z"
  }
]
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/data-sources/bindings/?arp_source_tag=switch-1f" \
  -H "Authorization: Bearer <access_token>"
```

---

### 7.2 POST /data-sources/bindings/

创建 ARP 数据源与防火墙的绑定关系。

- **认证要求**：超管专用

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| arp_source_tag | string | 是 | ARP 数据源标签 |
| firewall_tag | string | 是 | 防火墙数据源标签 |

**成功响应** `201`

```json
{
  "id": 2,
  "arp_source_tag": "switch-2f",
  "firewall_tag": "sangfor-af1",
  "created_at": "2025-06-08T12:00:00Z"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 绑定已存在；标签无效 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/bindings/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"arp_source_tag": "switch-2f", "firewall_tag": "sangfor-af1"}'
```

---

### 7.3 DELETE /data-sources/bindings/{binding_id}

删除数据源绑定。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| binding_id | Path | int | 是 | 绑定 ID |

**成功响应** `204`（无内容）

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 绑定不存在 |

**用例**

```bash
curl -X DELETE https://<HOST_IP>:8443/api/v1/data-sources/bindings/1 \
  -H "Authorization: Bearer <access_token>"
```

---

## 8. 合规操作 /data-sources/compliance

以下端点均为超管专用。

### 8.1 POST /data-sources/compliance/check

手动触发合规检查，检查终端是否在合规基准中注册。

- **认证要求**：超管专用

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| arp_source_tag | string | 否 | 仅检查指定 ARP 数据源的终端 |
| force | bool | 否 | 默认 false；为 true 时重新检查已检查过的终端 |

**成功响应** `200`

```json
{
  "total_checked": 50,
  "compliant": 30,
  "bypass": 10,
  "non_compliant": 8,
  "unknown": 2,
  "message": "Compliance check completed",
  "details": {
    "bypass": [{"ip_address": "192.168.1.10", "wl_match_type": "mac"}],
    "compliant": [{"ip_address": "192.168.1.20"}],
    "non_compliant": [{"ip_address": "192.168.1.30"}]
  }
}
```

**用例**

```bash
# 检查所有未检查的终端
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/compliance/check \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{}'

# 强制重新检查指定数据源
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/compliance/check \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"arp_source_tag": "switch-1f", "force": true}'
```

---

### 8.2 POST /data-sources/compliance/auto-block

自动封禁不合规终端。

- **认证要求**：超管专用

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| arp_source_tag | string | 是 | ARP 数据源标签 |
| block_time | string | 否 | 封锁时长，默认 `30d` |
| dry_run | bool | 否 | 默认 false；为 true 时仅预览不实际执行 |

**成功响应** `200`

```json
{
  "total_non_compliant": 8,
  "blocked": 8,
  "skipped": 0,
  "errors": [],
  "details": [
    {"ip_address": "192.168.1.30", "mac_address": "11:22:33:44:55:66", "blocked": true}
  ]
}
```

**用例**

```bash
# 预览模式（不实际封禁）
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/compliance/auto-block \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"arp_source_tag": "switch-1f", "block_time": "7d", "dry_run": true}'

# 实际执行
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/compliance/auto-block \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"arp_source_tag": "switch-1f", "block_time": "7d"}'
```

---

### 8.3 POST /data-sources/compliance/auto-unblock

自动解封已合规的终端（之前被自动封禁且现已合规的终端）。

- **认证要求**：超管专用

**成功响应** `200`

```json
{
  "total_auto_blocked": 8,
  "unblocked": 5,
  "skipped": 3,
  "errors": [],
  "details": [
    {"ip_address": "192.168.1.30", "unblocked": true}
  ]
}
```

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/data-sources/compliance/auto-unblock \
  -H "Authorization: Bearer <access_token>"
```

---

## 9. 合规基准管理 /compliance-baselines

> **审计日志**：合规基准管理操作均记录审计日志，action 值包括 `create_baseline`、`update_baseline`、`delete_baseline`，details 包含基准名称、标签及变更内容。

### 9.1 GET /compliance-baselines/

获取合规基准列表，支持按类型和启用状态过滤。

- **认证要求**：`baseline:read`

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| type | Query | string | 否 | 按类型过滤（ipguard） |
| enabled | Query | bool | 否 | 按启用状态过滤 |

**成功响应** `200`

```json
[
  {
    "id": 1,
    "name": "IPGuard基准",
    "type": "ipguard",
    "tag": "ipguard-01",
    "config": {"db_type": "postgresql", "host": "10.0.0.2", "port": 5432, "username": "readonly", "password": "***", "database": "ipguard"},
    "enabled": true,
    "last_sync_at": "2025-06-08T10:00:00Z",
    "last_sync_status": "success",
    "last_sync_error": null,
    "created_at": "2025-06-01T10:00:00Z",
    "updated_at": "2025-06-01T10:00:00Z"
  }
]
```

**用例**

```bash
# 列出所有合规基准
curl "https://<HOST_IP>:8443/api/v1/compliance-baselines/" \
  -H "Authorization: Bearer <access_token>"

# 按类型和启用状态过滤
curl "https://<HOST_IP>:8443/api/v1/compliance-baselines/?type=ipguard&enabled=true" \
  -H "Authorization: Bearer <access_token>"
```

---

### 9.2 POST /compliance-baselines/

创建合规基准。

- **认证要求**：`baseline:write`

**请求体**

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| name | string | 是 | 最长100字符 | 基准名称（唯一） |
| type | string | 是 | - | 基准类型：ipguard |
| tag | string | 是 | 最长50字符 | 唯一标签标识符 |
| config | object | 否 | JSON 对象 | 连接配置（见下方 config 参数说明） |
| enabled | bool | 否 | 默认 true | 是否启用 |

**config 参数说明（type=ipguard）：**

| 参数 | 类型 | 说明 |
|------|------|------|
| db_type | string | 数据库类型：postgresql / mysql / mssql |
| host | string | 数据库主机地址 |
| port | int | 数据库端口 |
| username | string | 数据库用户名 |
| password | string | 数据库密码（Fernet 加密存储） |
| database | string | 数据库名（默认 ipguard） |

**成功响应** `201`

```json
{
  "id": 2,
  "name": "IPGuard基准-2F",
  "type": "ipguard",
  "tag": "ipguard-2f",
  "config": {"db_type": "postgresql", "host": "10.0.0.3", "port": 5432, "username": "readonly", "password": "***", "database": "ipguard"},
  "enabled": true,
  "last_sync_at": null,
  "last_sync_status": null,
  "last_sync_error": null,
  "created_at": "2025-06-08T12:00:00Z",
  "updated_at": "2025-06-08T12:00:00Z"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 名称或标签重复；参数无效 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/compliance-baselines/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "IPGuard基准",
    "type": "ipguard",
    "tag": "ipguard-01",
    "config": {
      "db_type": "postgresql",
      "host": "10.0.0.2",
      "port": 5432,
      "username": "readonly",
      "password": "secret",
      "database": "ipguard"
    },
    "enabled": true
  }'
```

---

### 9.3 GET /compliance-baselines/{baseline_id}

获取合规基准详情。

- **认证要求**：`baseline:read`

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| baseline_id | Path | int | 是 | 合规基准 ID |

**成功响应** `200`

返回格式同 [9.2 POST /compliance-baselines/](#92-post-compliance-baselines) 中的单条记录。

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 记录不存在 |

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/compliance-baselines/1 \
  -H "Authorization: Bearer <access_token>"
```

---

### 9.4 PUT /compliance-baselines/{baseline_id}

更新合规基准。

- **认证要求**：`baseline:write`

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| baseline_id | Path | int | 是 | 合规基准 ID |

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 否 | 基准名称 |
| type | string | 否 | 基准类型 |
| tag | string | 否 | 标签标识符 |
| config | object | 否 | 连接配置 |
| enabled | bool | 否 | 启用状态 |

**成功响应** `200`

返回更新后的完整合规基准对象。

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 名称或标签重复；参数无效 |
| 404 | 记录不存在 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/compliance-baselines/1 \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

### 9.5 DELETE /compliance-baselines/{baseline_id}

删除合规基准。

- **认证要求**：`baseline:write`

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| baseline_id | Path | int | 是 | 合规基准 ID |

**成功响应** `204`（无内容）

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 记录不存在 |

**用例**

```bash
curl -X DELETE https://<HOST_IP>:8443/api/v1/compliance-baselines/1 \
  -H "Authorization: Bearer <access_token>"
```

---

### 9.6 POST /compliance-baselines/{baseline_id}/test

测试合规基准连接。

- **认证要求**：`baseline:test`

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| baseline_id | Path | int | 是 | 合规基准 ID |

**业务规则**

- 仅 `ipguard` 类型支持连接测试
- 根据 config 中的 `db_type` 选择对应驱动连接（postgresql / mysql / mssql）

**成功响应** `200`

```json
{
  "success": true,
  "message": "Connection successful (postgresql)",
  "details": null
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 404 | 记录不存在 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/compliance-baselines/1/test \
  -H "Authorization: Bearer <access_token>"
```

---

### 9.7 POST /compliance-baselines/{baseline_id}/sync

手动触发合规基准同步。

- **认证要求**：`baseline:sync`

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| baseline_id | Path | int | 是 | 合规基准 ID |

**业务规则**

- 合规基准必须处于启用状态
- 仅 `ipguard` 类型支持同步

**成功响应** `200`

```json
{
  "success": true,
  "message": "Sync completed",
  "entries_processed": 120,
  "entries_added": 0,
  "entries_updated": 0,
  "errors": []
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 合规基准已禁用；不支持同步的类型 |
| 404 | 记录不存在 |

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/compliance-baselines/1/sync \
  -H "Authorization: Bearer <access_token>"
```

---

## 10. 审计日志 /logs

### 10.1 GET /logs/

获取审计日志列表（分页，按时间倒序）。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| skip | Query | int | 0 | 跳过记录数 |
| limit | Query | int | 50 | 每页记录数（1-200） |

**成功响应** `200`

```json
[
  {
    "id": 1,
    "username": "admin",
    "action": "block_terminal",
    "resource_type": "terminal",
    "resource_id": "192.168.1.100",
    "details": "{\"ip\": \"192.168.1.100\", \"mac\": \"AA:BB:CC:DD:EE:FF\", \"block_time\": \"30d\", \"firewall_tag\": \"sangfor-af1\"}",
    "ip_address": "10.0.0.50",
    "timestamp": "2025-06-08T10:00:00Z"
  }
]
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/logs/?skip=0&limit=20" \
  -H "Authorization: Bearer <access_token>"
```

---

### 10.2 GET /logs/search

搜索审计日志，支持多条件过滤。

- **认证要求**：需认证

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| username | Query | string | 否 | 按用户名过滤 |
| action | Query | string | 否 | 按操作类型过滤（见下方 action 值列表） |
| search | Query | string | 否 | 关键词搜索（匹配 IP、用户名、详情） |
| start_date | Query | string | 否 | 起始日期（YYYY-MM-DD） |
| end_date | Query | string | 否 | 截止日期（YYYY-MM-DD） |
| skip | Query | int | 0 | 跳过记录数 |
| limit | Query | int | 50 | 每页记录数（1-200） |

**action 值列表**

| 分类 | action 值 | 说明 |
|------|----------|------|
| 认证 | `login` | 登录成功 |
| 认证 | `login_failed` | 登录失败 |
| 认证 | `logout` | 登出 |
| 认证 | `token_refresh` | 刷新令牌 |
| 认证 | `change_password` | 修改密码 |
| 终端操作 | `block_terminal` | 封锁终端 |
| 终端操作 | `unblock_terminal` | 解封终端 |
| 白名单 | `add_whitelist` | 添加白名单 |
| 白名单 | `remove_whitelist` | 移除白名单 |
| 黑名单 | `block_blacklist` | 添加黑名单 |
| 黑名单 | `unblock_blacklist` | 移除黑名单 |
| 黑名单 | `cleanup_expired` | 清理过期条目 |
| 数据源 | `create_datasource` | 创建数据源 |
| 数据源 | `update_datasource` | 更新数据源 |
| 数据源 | `delete_datasource` | 删除数据源 |
| 数据源 | `test_datasource` | 测试数据源连接 |
| 数据源 | `sync_datasource` | 同步数据源 |
| 数据源 | `bind_datasource` | 绑定数据源 |
| 数据源 | `unbind_datasource` | 解绑数据源 |
| 用户管理 | `create_user` | 创建用户 |
| 用户管理 | `update_user` | 更新用户 |
| 用户管理 | `delete_user` | 删除用户 |
| 用户管理 | `reset_password` | 重置密码 |
| 用户管理 | `unlock_user` | 解锁用户 |
| 用户管理 | `role_change` | 角色变更 |
| 用户管理 | `assign_role` | 分配角色 |
| 角色 | `create_role` | 创建角色 |
| 角色 | `update_role` | 更新角色 |
| 角色 | `delete_role` | 删除角色 |
| 合规 | `create_baseline` | 创建合规基准 |
| 合规 | `update_baseline` | 更新合规基准 |
| 合规 | `delete_baseline` | 删除合规基准 |
| 系统 | `update_config` | 更新系统配置 |
| 系统 | `upload_branding` | 上传品牌资源 |
| 系统 | `export_audit_logs` | 导出审计日志 |

> 后端启动时自动迁移旧版 action 值（如 `block_ip` → `block_terminal`、`add_to_whitelist` → `add_whitelist` 等），确保历史数据与新命名一致。

**成功响应** `200`

```json
{
  "items": [
    {
      "id": 1,
      "username": "admin",
      "action": "block_terminal",
      "resource_type": "terminal",
      "resource_id": "192.168.1.100",
      "details": "{\"ip\": \"192.168.1.100\", \"mac\": \"AA:BB:CC:DD:EE:FF\", \"block_time\": \"30d\", \"firewall_tag\": \"sangfor-af1\"}",
      "ip_address": "10.0.0.50",
      "timestamp": "2025-06-08T10:00:00Z"
    }
  ],
  "total": 200,
  "skip": 0,
  "limit": 50
}
```

> **details 字段**：存储为 JSON 格式字符串，包含操作相关的结构化信息（如 IP 地址、MAC 地址、封锁时长、变更内容等），前端可解析后以格式化方式展示。

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/logs/search?username=admin&action=block_terminal&start_date=2025-06-01&end_date=2025-06-08" \
  -H "Authorization: Bearer <access_token>"
```

---

### 10.3 GET /logs/export

导出审计日志为 CSV 文件。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| username | Query | string | 否 | — | 按用户名过滤 |
| action | Query | string | 否 | — | 按操作类型过滤 |
| search | Query | string | 否 | — | 关键词搜索 |
| start_date | Query | string | 否 | — | 起始日期（YYYY-MM-DD） |
| end_date | Query | string | 否 | — | 截止日期（YYYY-MM-DD） |
| limit | Query | int | 否 | 10000 | 导出记录数上限（最大 50000） |

**成功响应** `200`

- Content-Type: `text/csv`
- Content-Disposition: `attachment; filename=audit_logs.csv`

CSV 列：`ID, Timestamp, Username, Action, Resource Type, Resource ID, IP Address, Details`

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/logs/export?start_date=2025-06-01&end_date=2025-06-08" \
  -H "Authorization: Bearer <access_token>" \
  -o audit_logs.csv
```

---

## 11. 统计 /stats

### 11.1 GET /stats/

获取仪表盘统计数据。

- **认证要求**：需认证

**成功响应** `200`

```json
{
  "total": 500,
  "whitelisted": 120,
  "blocked": 35,
  "unblocked": 465,
  "compliant": 280,
  "bypass": 100,
  "non_compliant": 45,
  "unknown": 75
}
```

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/stats/ \
  -H "Authorization: Bearer <access_token>"
```

---

### 11.2 GET /stats/system-status

获取系统状态，包括深信服 AF 连接状态。

- **认证要求**：需认证

**成功响应** `200`

```json
{
  "backend_api": "connected",
  "database": "connected",
  "sangfor": {
    "connected": true,
    "cpu": 23.5,
    "memory": 45.2,
    "error": null
  },
  "network_scanner": "pending"
}
```

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/stats/system-status \
  -H "Authorization: Bearer <access_token>"
```

---

## 12. 系统设置 /settings

### 12.1 GET /settings/branding

获取品牌配置（登录页使用），无需认证。

- **认证要求**：公开

**成功响应** `200`

```json
{
  "app_name": "Terminal Access Manager",
  "app_short_name": "Terminal Access",
  "app_subtitle": "Manager",
  "login_heading": "Terminal Access Manager",
  "login_subheading": "Sign in to your account",
  "login_footer_text": "Secure authentication · Session-based access control",
  "login_bg_url": "",
  "favicon_url": "",
  "footer_copyright": "© {year} TerminalAccessManager (TAM)",
  "footer_icp_number": "",
  "footer_icp_url": "https://beian.miit.gov.cn/"
}
```

> 以上为系统默认值示例。自定义后的值会覆盖默认值。

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/settings/branding
```

---

### 12.2 GET /settings/

获取所有系统配置，按分类分组。

- **认证要求**：超管专用

**成功响应** `200`

```json
{
  "security": {
    "max_login_attempts": 5,
    "lockout_duration_minutes": 15,
    "captcha_threshold": 3,
    "allow_registration": false,
    "access_token_expire_minutes": 30,
    "refresh_token_expire_days": 7
  },
  "rate_limit": {
    "rate_limit_per_minute": 60,
    "auth_rate_limit_per_minute": 5
  },
  "network": {
    "sangfor_enabled": true,
    "sangfor_base_url": "https://10.0.0.1",
    "switch_enabled": false,
    "switch_host": null,
    "ipguard_enabled": true,
    "ipguard_host": "10.0.0.2"
  },
  "scheduler": {
    "scheduler_arp_collection_interval": 300,
    "scheduler_ipguard_sync_interval": 600,
    "scheduler_firewall_query_interval": 300,
    "scheduler_compliance_check_interval": 300,
    "scheduler_auto_unblock_interval": 600
  },
  "general": {
    "environment": "production",
    "debug": false,
    "log_level": "INFO"
  },
  "branding": {
    "app_name": "Terminal Access Manager",
    "app_short_name": "Terminal Access",
    "app_subtitle": "Manager",
    "login_heading": "Terminal Access Manager",
    "login_subheading": "Sign in to your account",
    "login_footer_text": "Secure authentication · Session-based access control",
    "login_bg_url": "",
    "favicon_url": "",
    "footer_copyright": "© {year} TerminalAccessManager (TAM)",
    "footer_icp_number": "",
    "footer_icp_url": ""
  }
}
```

**用例**

```bash
curl https://<HOST_IP>:8443/api/v1/settings/ \
  -H "Authorization: Bearer <access_token>"
```

---

### 12.3 GET /settings/list

列出配置项列表（含元数据），支持按分类过滤。

- **认证要求**：超管专用

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| category | Query | string | 否 | 按分类过滤（security/rate_limit/auth/network/scheduler/general/logging/branding） |

**成功响应** `200`

```json
[
  {
    "id": 1,
    "key": "max_login_attempts",
    "value": "5",
    "description": "Maximum login attempts before account lockout",
    "category": "security",
    "value_type": "int",
    "is_readonly": false,
    "updated_by": "system",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  }
]
```

**用例**

```bash
curl "https://<HOST_IP>:8443/api/v1/settings/list?category=security" \
  -H "Authorization: Bearer <access_token>"
```

---

### 12.4 PUT /settings/update

批量更新配置项。只读配置不可修改。

- **认证要求**：超管专用

> **审计日志**：配置更新成功时记录 `update_config` 操作，details 包含变更的配置键名、旧值和新值。

**请求体**

```json
[
  {"key": "max_login_attempts", "value": "10"},
  {"key": "captcha_threshold", "value": "5"}
]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| key | string | 是 | 配置键名 |
| value | string | 是 | 新值（字符串形式） |

**成功响应** `200`

```json
[
  {"key": "max_login_attempts", "success": true, "message": null},
  {"key": "captcha_threshold", "success": true, "message": null}
]
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 配置键不存在或为只读 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/settings/update \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '[
    {"key": "max_login_attempts", "value": "10"},
    {"key": "captcha_threshold", "value": "5"}
  ]'
```

---

### 12.5 PUT /settings/{key}

更新单个配置项。

- **认证要求**：超管专用

> **审计日志**：配置更新成功时记录 `update_config` 操作，details 包含变更的配置键名、旧值和新值。

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| key | Path | string | 是 | 配置键名 |

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| key | string | 是 | 配置键名（须与路径一致） |
| value | string | 是 | 新值 |
| description | string | 否 | 新描述 |

**成功响应** `200`

```json
{
  "key": "max_login_attempts",
  "success": true,
  "message": null
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | 配置键不存在或为只读 |

**用例**

```bash
curl -X PUT https://<HOST_IP>:8443/api/v1/settings/max_login_attempts \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"key": "max_login_attempts", "value": "10"}'
```

---

### 12.6 POST /settings/seed

种子默认配置。幂等操作，已存在的键不会覆盖。

- **认证要求**：超管专用

**成功响应** `200`

```json
{
  "message": "Seeded 3 new configs",
  "count": 3
}
```

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/settings/seed \
  -H "Authorization: Bearer <access_token>"
```

---

### 12.7 POST /settings/invalidate-cache

失效所有配置缓存，强制下次读取从数据库加载。

- **认证要求**：超管专用

**成功响应** `200`

```json
{
  "message": "Config cache invalidated"
}
```

**用例**

```bash
curl -X POST https://<HOST_IP>:8443/api/v1/settings/invalidate-cache \
  -H "Authorization: Bearer <access_token>"
```

---

### 12.8 POST /settings/upload

上传品牌资源文件（登录背景图或 Favicon），自动更新对应配置项。

- **认证要求**：超管专用
- **Content-Type**：`multipart/form-data`

**请求参数**

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| file | Body (form) | File | 是 | 图片文件（仅支持 .jpg/.jpeg/.png/.gif/.ico） |
| purpose | Query | string | 是 | 用途：`login_bg` 或 `favicon` |

**限制**

- 文件大小：最大 5MB
- 扩展名白名单：仅支持 .jpg/.jpeg/.png/.gif/.ico
- SVG 不再支持（XSS 风险）
- 双重校验：content_type + 扩展名均须匹配
- 文件名使用 UUID 重命名

**成功响应** `200`

```json
{
  "url": "/uploads/login_bg_abc12345.png",
  "config_key": "login_bg_url",
  "updated": true,
  "message": "File uploaded and login_bg_url updated"
}
```

**错误响应**

| 状态码 | 说明 |
|--------|------|
| 400 | purpose 值无效；文件类型不支持；文件过大 |

**用例**

```bash
# 上传登录背景图
curl -X POST "https://<HOST_IP>:8443/api/v1/settings/upload?purpose=login_bg" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/background.png"

# 上传 Favicon
curl -X POST "https://<HOST_IP>:8443/api/v1/settings/upload?purpose=favicon" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/favicon.ico"
```

---

## 15. 健康检查 /health

### 15.1 GET /health

健康检查，验证数据库和 Redis 连接状态。

- **认证要求**：公开
- **路径**：`/health`（注意：不在 `/api/v1` 前缀下）

**成功响应** `200`

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "environment": "production",
  "db": "ok",
  "redis": "ok"
}
```

**失败响应** `503`

```json
{
  "status": "unhealthy",
  "version": "2.0.0",
  "environment": "production",
  "db": "error: connection refused",
  "redis": "ok"
}
```

**用例**

```bash
curl https://<HOST_IP>:8443/health
```

---

## 13. 角色管理 /roles

### 获取角色列表

```
GET /api/v1/roles/
```

**所需权限**: `role:read`

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| 无 | | | |

**响应**: 角色列表数组

```json
[
  {
    "id": 1,
    "name": "superadmin",
    "description": "超级管理员",
    "is_default": false,
    "permissions": [],
    "created_at": "2026-06-10T00:00:00",
    "updated_at": "2026-06-10T00:00:00"
  }
]
```

#### 获取权限码列表

```
GET /api/v1/roles/permissions
```

**所需权限**: `role:read`

**响应**: 权限码列表数组

```json
[
  {
    "id": 1,
    "code": "terminal:read",
    "name": "查看终端",
    "module": "terminal",
    "description": "查看终端列表和详情"
  }
]
```

#### 获取角色详情

```
GET /api/v1/roles/{role_id}
```

**所需权限**: `role:read`

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| role_id | int | 角色ID |

**业务规则**: 非超管用户查看 superadmin 角色详情返回 403

**响应**:

```json
{
  "id": 2,
  "name": "admin",
  "description": "管理员",
  "is_default": false,
  "permissions": ["datasource:read", "datasource:write", "..."],
  "user_count": 3,
  "created_at": "2026-06-10T00:00:00",
  "updated_at": "2026-06-10T00:00:00"
}
```

#### 创建角色

```
POST /api/v1/roles/
```

**所需权限**: `role:write`

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 角色标识名（2-50字符，小写字母开头，仅含小写字母/数字/下划线） |
| description | string | 否 | 角色描述（最长200字符） |
| permission_ids | int[] | 是 | 权限ID列表 |

**请求示例**:

```json
{
  "name": "custom_operator",
  "description": "自定义操作员角色",
  "permission_ids": [1, 2, 3, 5]
}
```

#### 更新角色

```
PUT /api/v1/roles/{role_id}
```

**所需权限**: `role:write`

**业务规则**: superadmin 角色不可修改

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| description | string | 否 | 角色描述 |
| permission_ids | int[] | 否 | 权限ID列表（替换全部） |

**请求示例**:

```json
{
  "description": "更新后的描述",
  "permission_ids": [1, 2, 3, 5, 7]
}
```

#### 删除角色

```
DELETE /api/v1/roles/{role_id}
```

**所需权限**: `role:delete`

**业务规则**: 内置角色（superadmin/admin/operator/auditor/viewer）不可删除；仍有用户关联的角色不可删除

**响应**: `204 No Content`

#### 分配用户角色

```
PUT /api/v1/roles/users/{user_id}/roles
```

**所需权限**: `user:write`

**业务规则**: superadmin 角色不可分配；分配后自动同步 `is_superuser` 字段；自动失效用户权限缓存

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| role_id | int | 是 | 角色ID（单角色分配） |

**请求示例**:

```json
{
  "role_id": 3
}
```

#### 获取角色用户列表

```
GET /api/v1/roles/{role_id}/users
```

**所需权限**: `role:read`

**业务规则**: 非超管用户查看 superadmin 角色用户返回 403

**响应**:

```json
[
  {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "is_active": true,
    "is_superuser": true
  }
]
```

> **CLI 替代方案**：以上角色管理操作也可通过命令行完成：
> - 查看角色列表：`./manage.sh role list` 或 `python cli.py role list`
> - 查看权限码：`./manage.sh role permissions` 或 `python cli.py role permissions`
> - 重置用户密码：`./manage.sh password reset <username>`
> - 解锁用户：`./manage.sh user unlock <username>`
>
> CLI 操作适用于无法访问 Web UI 的紧急运维场景。

---

## 14. 权限码参考

系统共定义29个权限码，按10个功能模块分组：

| 模块 | 权限码 | 名称 |
|------|--------|------|
| terminal | `terminal:read` | 查看终端 |
| terminal | `terminal:write` | 操作终端 |
| whitelist | `whitelist:read` | 查看白名单 |
| whitelist | `whitelist:write` | 管理白名单 |
| blacklist | `blacklist:read` | 查看封禁列表 |
| blacklist | `blacklist:write` | 管理封禁列表 |
| datasource | `datasource:read` | 查看数据源 |
| datasource | `datasource:write` | 管理数据源 |
| datasource | `datasource:test` | 测试数据源 |
| datasource | `datasource:sync` | 同步数据源 |
| datasource | `datasource:compliance` | 合规检查 |
| baseline | `baseline:read` | 查看合规基线 |
| baseline | `baseline:write` | 管理合规基线 |
| baseline | `baseline:test` | 测试合规基线 |
| baseline | `baseline:sync` | 同步合规基线 |
| user | `user:read` | 查看用户 |
| user | `user:write` | 管理用户 |
| user | `user:delete` | 删除用户 |
| user | `user:password` | 重置密码 |
| user | `user:unlock` | 解锁用户 |
| audit | `audit:read` | 查看审计日志 |
| audit | `audit:export` | 导出审计日志 |
| settings | `settings:read` | 查看系统配置 |
| settings | `settings:write` | 修改系统配置 |
| settings | `settings:upload` | 上传品牌资源 |
| stats | `stats:read` | 查看统计 |
| role | `role:read` | 查看角色 |
| role | `role:write` | 管理角色 |
| role | `role:delete` | 删除角色 |
