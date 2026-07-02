
# 实施计划：认证体系与消息通知完善

> 文档版本：v1.0  更新日期：2026-07-02

## 需求概述

基于系统当前实现情况，需要完善以下两大功能：

| 需求 | 描述 | 优先级 |
|------|------|--------|
| **多认证方式支持** | 系统支持本地用户和LDAP两种认证方式，两种用户都支持角色关联 | P0 |
| **消息通知管理** | 1) 密码重置时发送验证码验证；2) 系统事件通过不同渠道灵活通知 | P0 |

---

## 阶段一：后端模型与认证流程重构

### 1.1 User 模型增强

**目标**：添加认证提供者标识字段，支持区分本地用户和LDAP用户

**修改文件**：`backend/app/models/user.py`

**变更内容**：
```python
# 新增字段
provider = Column(String(50), default="local")  # 认证提供者类型：local/ldap
provider_user_id = Column(String(255), nullable=True)  # 提供者中的用户ID(如LDAP DN)
```

**迁移脚本**：生成 Alembic 迁移文件，为现有用户设置默认值
```bash
alembic revision --autogenerate -m "add provider fields to users"
```

### 1.2 重构登录 API

**目标**：集成 AuthProviderFactory，支持选择认证方式，实现 LDAP 用户 JIT 自动创建

**修改文件**：`backend/app/api/v1/endpoints/auth.py`

**变更内容**：
1. 在登录接口中添加 `provider` 查询参数（默认值：`local`）
2. 通过 `AuthProviderFactory` 执行认证
3. 实现 `_get_or_create_user()` 函数处理 LDAP 用户首次登录
4. 确保无密码的 LDAP 用户不能通过本地密码方式登录

**关键逻辑**：
- 本地用户：查询本地数据库验证密码
- LDAP 用户：调用 LDAPProvider 验证，验证成功后创建/获取本地用户记录
- 所有用户统一通过本地 `users` 表获取角色权限

### 1.3 密码修改/重置安全增强

**目标**：确保 LDAP 用户无法修改本地密码（密码由 LDAP 服务器管理）

**修改文件**：`backend/app/api/v1/endpoints/auth.py`

**变更内容**：
- 修改 `/auth/me/password`：检查用户 provider，LDAP 用户禁止修改密码
- 修改 `/auth/users/{user_id}/password`：同上，管理员也不能为 LDAP 用户重置密码

### 1.4 新增认证提供者选择 API

**目标**：前端获取可用的认证提供者列表

**修改文件**：`backend/app/api/v1/endpoints/auth_providers.py`

**新增接口**：
```
GET /auth/providers/available
```

返回已启用的认证提供者列表，供前端登录页面选择。

---

## 阶段二：前端认证 UI 适配

### 2.1 登录页面 Provider 选择

**目标**：在登录表单中添加认证方式选择

**修改文件**：`frontend/src/pages/Login.tsx`

**变更内容**：
1. 调用 `/auth/providers/available` 获取可用提供者列表
2. 添加下拉选择框（本地 / LDAP）
3. 根据选择的 provider 调整登录请求参数
4. 处理 LDAP 用户首次登录的提示信息

### 2.2 用户管理页面增强

**目标**：展示用户的认证来源信息

**修改文件**：`frontend/src/pages/Users.tsx`

**变更内容**：
1. 在用户列表中显示 provider 类型标签
2. LDAP 用户禁用密码修改/重置按钮
3. 用户详情中显示 provider_user_id

---

## 阶段三：消息通知功能完善

### 3.1 新增验证码发送事件类型

**目标**：支持密码重置时的验证码发送与验证

**修改文件**：`backend/app/services/notification_channels/event_types.py`

**新增事件**：
```python
PASSWORD_RESET_CODE = "security.password_reset_code"  # 发送密码重置验证码
VERIFICATION_CODE = "security.verification_code"       # 通用验证码发送
```

### 3.2 NotificationService 增加验证方法

**目标**：支持验证码的发送与验证

**修改文件**：`backend/app/services/notification_service.py`

**新增方法**：
```python
async def send_verification_code(self, channel_type, recipient, code, purpose):
    """发送验证码"""
    ...

async def verify_verification_code(self, recipient, code, purpose):
    """验证验证码"""
    ...
```

### 3.3 密码重置 API 集成验证码

**目标**：实现密码重置流程中的验证码验证

**修改文件**：`backend/app/api/v1/endpoints/auth.py`

**新增接口**：
```
POST /auth/password/reset/request    # 请求密码重置（发送验证码）
POST /auth/password/reset/verify     # 验证验证码并重置密码
```

**流程**：
1. 用户输入邮箱 → 后端生成验证码 → 通过邮件通道发送
2. 用户输入验证码 → 后端验证 → 通过后重置密码

### 3.4 前端事件订阅选择 UI

**目标**：在消息通道管理中添加事件订阅选择功能

**修改文件**：`frontend/src/pages/Notifications.tsx`

**变更内容**：
1. 在通道表单中添加事件多选区域
2. 按类别分组显示事件（terminal/security/system/alert/admin）
3. 支持全选/反选功能
4. 编辑时回显已订阅的事件列表
5. 提交时传递 `events` 字段

### 3.5 前端密码重置页面

**目标**：实现密码重置验证码流程

**修改文件**：`frontend/src/pages/PasswordReset.tsx`（新建或修改）

**变更内容**：
1. 第一步：输入邮箱，请求验证码
2. 第二步：输入验证码，设置新密码
3. 第三步：完成重置，跳转登录

---

## 文件变更清单

### 后端修改

| 文件路径 | 修改类型 | 说明 |
|----------|----------|------|
| `backend/app/models/user.py` | 修改 | 新增 provider, provider_user_id 字段 |
| `backend/app/api/v1/endpoints/auth.py` | 修改 | 重构登录流程，支持 provider 参数 |
| `backend/app/api/v1/endpoints/auth_providers.py` | 修改 | 新增 available 接口 |
| `backend/app/services/auth_providers/provider_factory.py` | 修改 | 完善 authenticate 方法 |
| `backend/app/services/notification_channels/event_types.py` | 修改 | 新增验证码事件类型 |
| `backend/app/services/notification_service.py` | 修改 | 新增验证码发送/验证方法 |
| `backend/alembic/versions/xxx_add_provider_fields.py` | 新建 | 数据库迁移脚本 |

### 前端修改

| 文件路径 | 修改类型 | 说明 |
|----------|----------|------|
| `frontend/src/pages/Login.tsx` | 修改 | 添加 provider 选择 |
| `frontend/src/pages/Notifications.tsx` | 修改 | 添加事件订阅选择 UI |
| `frontend/src/pages/Users.tsx` | 修改 | 显示 provider 信息 |
| `frontend/src/pages/PasswordReset.tsx` | 新建 | 密码重置页面 |

---

## 风险评估与处理

### 数据库变更风险
- **风险**：修改 User 模型需要数据库迁移
- **处理**：使用 Alembic 自动生成迁移脚本，在测试环境验证后再部署生产

### 认证兼容性风险
- **风险**：修改登录 API 可能影响现有前端
- **处理**：`provider` 参数设置默认值 `local`，保持向后兼容

### 安全风险
- **风险**：LDAP 用户无本地密码，可能被恶意利用
- **处理**：代码中明确检查 provider，禁止 LDAP 用户使用密码修改功能

### 通知功能风险
- **风险**：事件订阅可能导致通知泛滥
- **处理**：按类别分组显示，支持全选/反选，用户可精细控制

---

## 验证计划

### 阶段一验证
1. **数据库迁移**：执行迁移脚本，验证字段添加成功
2. **本地用户登录**：现有本地用户仍可正常登录
3. **LDAP 用户登录**：LDAP 用户首次登录自动创建本地记录
4. **角色关联**：LDAP 用户登录后能获取分配的角色权限

### 阶段二验证
1. **登录页面**：Provider 选择下拉框正常显示和切换
2. **用户管理**：显示 provider 标签，LDAP 用户密码按钮禁用

### 阶段三验证
1. **密码重置**：邮箱接收验证码，验证后密码重置成功
2. **事件订阅**：创建通道时可选择事件，事件触发时通知发送到正确通道
3. **通知日志**：查看通知发送记录，确认订阅生效

---

## 实施顺序建议

```
阶段一（后端）          阶段二（前端认证）    阶段三（通知）
├─ 用户模型修改        ├─ 登录页面 Provider  ├─ 验证码事件类型
├─ 登录 API 重构       │   选择              ├─ NotificationService
├─ 密码安全增强        ├─ 用户管理页面       │   验证方法
├─ 提供者列表 API      │   provider 展示     ├─ 密码重置 API
└─ 数据库迁移          └─ LDAP 用户禁用     ├─ 事件订阅 UI
                                            └─ 密码重置页面
```

**建议节奏**：每个阶段完成后进行验证，确保功能正常后再进入下一阶段。
