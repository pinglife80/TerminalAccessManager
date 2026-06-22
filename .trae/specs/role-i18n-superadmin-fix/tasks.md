# 角色权限 i18n 与超管角色初始化修复 - 实施计划

## [x] Task 1: 修复 i18n 翻译键命名冲突（权限列表头）
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 将 i18n 翻译文件中 `roles.permissions` 表头键重命名为 `roles.permissionsColumn`，避免与权限翻译对象命名冲突
  - 同步更新前端 Roles.tsx 中对该表头翻译键的引用
  - 需同时修改 en.ts、zh.ts、ja.ts 三个语言文件
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `human-judgment` TR-1.1: 角色列表 "权限" 列表头在中英文下均正确显示文本，无 "returned an object instead of string" 错误
  - `human-judgment` TR-1.2: 角色权限详情弹窗和编辑弹窗中的权限翻译仍正常使用 `roles.permissions.xxx` 路径
- **Notes**: 修改量小但需仔细检查所有引用点

## [x] Task 2: 修复权限代码冒号与 i18next nsSeparator 冲突
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - 权限代码格式为 `terminal:read`，其中冒号 `:` 是 i18next 默认的命名空间分隔符，导致翻译键查找失败
  - 修复方案：在 i18n 配置中设置 `nsSeparator: false`（因项目仅使用单一 translation 命名空间，禁用命名空间分隔符无副作用）
  - 验证所有权限翻译键（共 29 个权限）在英文、中文、日文下均正确显示
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `human-judgment` TR-2.1: 角色权限详情弹窗中所有权限项显示翻译后的名称（英文环境显示英文，中文环境显示中文）
  - `human-judgment` TR-2.2: 角色编辑弹窗中权限列表显示翻译后的名称
  - `human-judgment` TR-2.3: 日文环境下权限翻译也正常显示
- **Notes**: 需确保禁用 nsSeparator 不影响其他翻译键的使用

## [x] Task 3: 修复初始化 admin 用户未分配 superadmin 角色
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 修改 `backend/cli.py` 中的 `_create_admin_user()` 函数
  - 在创建 admin 用户后，查询 superadmin 角色并创建 UserRole 关联
  - 保证幂等性：若 admin 用户已存在且已有关联，则不重复创建
  - 同时确保 `_ensure_rbac_seed` 或相关迁移中也有同样的逻辑（如有其他初始化入口）
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 干净数据库执行 `python cli.py setup` 后，查询 user_roles 表，admin 用户有且仅有一条关联 superadmin 角色的记录
  - `programmatic` TR-3.2: 重复执行 `python cli.py setup` 后，user_roles 表中记录数不增加，无报错
- **Notes**: 注意使用事务和正确的异常处理

## [x] Task 4: 修复 `_ensure_rbac_seed` 中 admin 用户角色重分配逻辑
- **Priority**: P1
- **Depends On**: Task 3
- **Description**:
  - 检查 `_ensure_rbac_seed` 函数（cli.py 约 1307 行附近）中的 admin 用户角色重分配逻辑
  - 确保该逻辑能正确将 admin 用户重新分配到 superadmin 角色
  - 该逻辑在每次 seed 时执行，用于修复旧数据
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-4.1: admin 用户无 superadmin 角色时，执行 seed 后获得该角色
  - `programmatic` TR-4.2: admin 用户已有 superadmin 角色时，执行 seed 不产生重复记录
- **Notes**: 这是对 Task 3 的补充，确保已部署环境也能修复

## [x] Task 5: 前端验证与集成测试
- **Priority**: P1
- **Depends On**: Task 1, Task 2, Task 3
- **Description**:
  - 验证角色管理页面各项显示正常
  - 验证用户管理页面 admin 用户角色显示为 Super Admin
  - 中英文切换验证
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-4
- **Test Requirements**:
  - `human-judgment` TR-5.1: 角色列表各列标题正确翻译
  - `human-judgment` TR-5.2: 5 个内置角色名称和描述正确翻译
  - `human-judgment` TR-5.3: 权限名称全部正确翻译
  - `human-judgment` TR-5.4: 用户管理页面 admin 用户显示 "Super Admin" 紫色标签
- **Notes**: 综合验收测试
