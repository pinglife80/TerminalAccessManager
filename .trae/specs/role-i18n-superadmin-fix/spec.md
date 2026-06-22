# 角色权限 i18n 与超管角色初始化修复 - 产品需求文档

## Overview
- **Summary**: 修复角色管理页面中 5 个内置角色权限菜单的国际化翻译问题、权限列表头显示错误，以及初始化创建的 admin 用户未分配 superadmin 角色导致显示为 "User" 的问题。
- **Purpose**: 解决角色管理相关的两个功能性缺陷：i18n 翻译失效与初始化用户角色错误，确保系统正确展示角色权限信息且初始管理员拥有正确角色。
- **Target Users**: 系统管理员、运维人员

## Goals
- 修复角色列表 "权限" 列表头显示错误 "key 'roles.permissions (en)' returned an object instead of string."
- 修复 5 个内置角色权限菜单项的 i18n 翻译不生效问题
- 确保初始化创建的 admin 用户正确分配 superadmin 角色
- 保持与现有代码风格和架构一致

## Non-Goals (Out of Scope)
- 不新增角色或权限类型
- 不重构整个 RBAC 系统
- 不改动角色管理页面的 UI 布局
- 不添加新的 i18n 语言

## Background & Context
### 问题 1：角色权限 i18n 失效
当前 `roles.permissions` 在 i18n 文件中存在命名冲突：
- 作为字符串：`permissions: 'Permissions'`（列表头翻译）
- 作为对象：`permissions: { ... }`（各权限代码的翻译集合）

对象定义会覆盖字符串定义，导致调用 `t('roles.permissions')` 时返回对象而非字符串，触发错误提示。

此外，权限代码（如 `terminal:read`）中包含冒号 `:`，而 i18next 默认将冒号视为命名空间分隔符（`nsSeparator`），导致 `t('roles.permissions.terminal:read')` 被错误解析为命名空间 `roles.permissions.terminal` + 键 `read`，翻译查找失败。

### 问题 2：初始化 admin 用户角色为 "User"
`_create_admin_user()` 函数（位于 cli.py）创建 admin 用户时仅设置了 `is_superuser=True`，但未在 `user_roles` 关联表中分配任何角色。前端用户管理页面在用户无角色时显示默认文本 "User"，导致管理员角色显示错误。

虽然 `is_superuser=True` 在后端可能绕过权限检查，但前端角色显示和基于角色的权限判断依赖 `user_roles` 关联表。

## Functional Requirements
- **FR-1**: 角色列表 "权限" 列表头正确显示翻译后的文本（英文 "Permissions"，中文 "权限"）
- **FR-2**: 角色权限详情弹窗和编辑弹窗中的权限名称正确显示翻译文本
- **FR-3**: 5 个内置角色的名称、描述的 i18n 翻译保持可用
- **FR-4**: `python cli.py setup` 初始化命令创建的 admin 用户自动关联 superadmin 角色
- **FR-5**: 用户管理页面中 admin 用户正确显示 "Super Admin" 角色标签

## Non-Functional Requirements
- **NFR-1**: 修复不影响现有 i18n 翻译键的使用（除了需要调整的表头键）
- **NFR-2**: 修复向后兼容，不破坏已有自定义角色的权限展示
- **NFR-3**: 初始化脚本幂等性：重复执行 setup 不会创建重复角色关联

## Constraints
- **技术**: 前端使用 React + react-i18next，后端使用 Python + FastAPI + SQLAlchemy
- **依赖**: i18next 配置保持单命名空间（translation）
- **数据**: 必须保证数据库迁移和种子数据的一致性

## Assumptions
- `is_superuser=True` 的用户在后端权限检查中拥有全部权限
- 前端权限判断依赖后端返回的 `roles` 数组
- 初始化脚本 `cli.py setup` 是创建初始 admin 用户的标准方式

## Acceptance Criteria

### AC-1: 角色权限列表头正确显示
- **Given**: 用户访问角色管理页面且语言设置为英文
- **When**: 查看角色列表的表头
- **Then**: "权限" 列正确显示 "Permissions" 文本，无错误提示
- **Verification**: `human-judgment`
- **Notes**: 需验证中英文切换均正常

### AC-2: 权限名称 i18n 翻译生效
- **Given**: 用户查看角色权限详情弹窗且语言设置为英文
- **When**: 展开任意权限模块
- **Then**: 各权限项（如 "terminal:read"）显示英文翻译而非原始 code 或中文名称
- **Verification**: `human-judgment`
- **Notes**: 需验证 5 个内置角色的权限翻译全部正确显示

### AC-3: 初始化 admin 用户拥有 superadmin 角色
- **Given**: 干净的数据库环境
- **When**: 执行 `python cli.py setup` 初始化命令
- **Then**: admin 用户在 `user_roles` 表中关联 superadmin 角色（role_id=1）
- **Verification**: `programmatic`
- **Notes**: 可通过数据库查询或 API 验证

### AC-4: 用户管理页正确显示 admin 角色
- **Given**: admin 用户已分配 superadmin 角色
- **When**: 管理员在用户管理页面查看用户列表
- **Then**: admin 用户的角色列显示 "Super Admin" 标签（紫色样式），而非 "User"
- **Verification**: `human-judgment`

### AC-5: 初始化脚本幂等
- **Given**: admin 用户已存在且已分配 superadmin 角色
- **When**: 再次执行 `python cli.py setup`
- **Then**: 不会创建重复的角色关联，无错误发生
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要为已部署的旧数据提供迁移脚本，将已有 admin 用户补分配 superadmin 角色？
