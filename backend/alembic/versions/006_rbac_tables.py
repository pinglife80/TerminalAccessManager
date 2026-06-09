"""Add RBAC tables: roles, permissions, user_roles, role_permissions

Revision ID: 006_rbac_tables
Revises: 005_mac_normalized_column
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String, Integer, Boolean

# revision identifiers
revision = '006_rbac_tables'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('description', sa.String(200), nullable=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_roles_id', 'roles', ['id'])
    op.create_index('ix_roles_name', 'roles', ['name'])

    # Create permissions table
    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(100), unique=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('description', sa.String(200), nullable=True),
    )
    op.create_index('ix_permissions_id', 'permissions', ['id'])
    op.create_index('ix_permissions_code', 'permissions', ['code'])
    op.create_index('ix_permissions_module', 'permissions', ['module'])

    # Create user_roles association table
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    )

    # Create role_permissions association table
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_id', sa.Integer(), sa.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    )

    # Seed preset roles
    roles_table = table('roles',
        column('id', Integer),
        column('name', String),
        column('description', String),
        column('is_default', Boolean),
    )
    op.bulk_insert(roles_table, [
        {'id': 1, 'name': 'superadmin', 'description': '超级管理员 - 拥有系统全部权限', 'is_default': False},
        {'id': 2, 'name': 'admin', 'description': '管理员 - 管理用户、数据源、系统配置', 'is_default': False},
        {'id': 3, 'name': 'operator', 'description': '操作员 - 操作终端、白名单、黑名单', 'is_default': True},
        {'id': 4, 'name': 'auditor', 'description': '审计员 - 查看审计日志和导出', 'is_default': False},
        {'id': 5, 'name': 'viewer', 'description': '只读用户 - 仅查看各模块数据', 'is_default': False},
    ])

    # Seed preset permissions
    permissions_table = table('permissions',
        column('id', Integer),
        column('code', String),
        column('name', String),
        column('module', String),
        column('description', String),
    )
    op.bulk_insert(permissions_table, [
        # Terminal
        {'id': 1, 'code': 'terminal:read', 'name': '查看终端', 'module': 'terminal', 'description': '查看终端列表和详情'},
        {'id': 2, 'code': 'terminal:write', 'name': '操作终端', 'module': 'terminal', 'description': '封禁/解封终端'},
        # Whitelist
        {'id': 3, 'code': 'whitelist:read', 'name': '查看白名单', 'module': 'whitelist', 'description': '查看白名单列表'},
        {'id': 4, 'code': 'whitelist:write', 'name': '管理白名单', 'module': 'whitelist', 'description': '添加/删除白名单条目'},
        # Blacklist
        {'id': 5, 'code': 'blacklist:read', 'name': '查看封禁列表', 'module': 'blacklist', 'description': '查看封禁列表'},
        {'id': 6, 'code': 'blacklist:write', 'name': '管理封禁列表', 'module': 'blacklist', 'description': '添加/解封黑名单条目'},
        # Data Source
        {'id': 7, 'code': 'datasource:read', 'name': '查看数据源', 'module': 'datasource', 'description': '查看数据源列表和详情'},
        {'id': 8, 'code': 'datasource:write', 'name': '管理数据源', 'module': 'datasource', 'description': '创建/编辑/删除数据源和绑定'},
        {'id': 9, 'code': 'datasource:test', 'name': '测试数据源', 'module': 'datasource', 'description': '测试数据源连接'},
        {'id': 10, 'code': 'datasource:sync', 'name': '同步数据源', 'module': 'datasource', 'description': '手动同步数据源'},
        {'id': 11, 'code': 'datasource:compliance', 'name': '合规检查', 'module': 'datasource', 'description': '执行合规检查和自动封禁'},
        # Compliance Baseline
        {'id': 12, 'code': 'baseline:read', 'name': '查看合规基线', 'module': 'baseline', 'description': '查看合规基线列表'},
        {'id': 13, 'code': 'baseline:write', 'name': '管理合规基线', 'module': 'baseline', 'description': '创建/编辑/删除合规基线'},
        {'id': 14, 'code': 'baseline:test', 'name': '测试合规基线', 'module': 'baseline', 'description': '测试合规基线连接'},
        {'id': 15, 'code': 'baseline:sync', 'name': '同步合规基线', 'module': 'baseline', 'description': '手动同步合规基线'},
        # User management
        {'id': 16, 'code': 'user:read', 'name': '查看用户', 'module': 'user', 'description': '查看用户列表和详情'},
        {'id': 17, 'code': 'user:write', 'name': '管理用户', 'module': 'user', 'description': '创建/编辑用户'},
        {'id': 18, 'code': 'user:delete', 'name': '删除用户', 'module': 'user', 'description': '删除用户'},
        {'id': 19, 'code': 'user:password', 'name': '重置密码', 'module': 'user', 'description': '重置用户密码'},
        {'id': 20, 'code': 'user:unlock', 'name': '解锁用户', 'module': 'user', 'description': '解锁用户账户'},
        # Audit
        {'id': 21, 'code': 'audit:read', 'name': '查看审计日志', 'module': 'audit', 'description': '查看审计日志'},
        {'id': 22, 'code': 'audit:export', 'name': '导出审计日志', 'module': 'audit', 'description': '导出审计日志为CSV'},
        # Settings
        {'id': 23, 'code': 'settings:read', 'name': '查看系统配置', 'module': 'settings', 'description': '查看系统配置'},
        {'id': 24, 'code': 'settings:write', 'name': '修改系统配置', 'module': 'settings', 'description': '修改系统配置'},
        {'id': 25, 'code': 'settings:upload', 'name': '上传品牌资源', 'module': 'settings', 'description': '上传登录背景和图标'},
        # Stats
        {'id': 26, 'code': 'stats:read', 'name': '查看统计', 'module': 'stats', 'description': '查看仪表盘统计'},
        # Role management
        {'id': 27, 'code': 'role:read', 'name': '查看角色', 'module': 'role', 'description': '查看角色列表和权限'},
        {'id': 28, 'code': 'role:write', 'name': '管理角色', 'module': 'role', 'description': '创建/编辑角色和分配权限'},
        {'id': 29, 'code': 'role:delete', 'name': '删除角色', 'module': 'role', 'description': '删除角色'},
    ])

    # Seed role_permissions
    role_permissions_table = table('role_permissions',
        column('role_id', Integer),
        column('permission_id', Integer),
    )

    # admin: user, datasource, baseline, settings, audit, role (all read+write), stats
    admin_perms = [7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29]
    # operator: terminal, whitelist, blacklist, datasource/baseline read, stats, audit read
    operator_perms = [1,2,3,4,5,6,7,12,21,26]
    # auditor: audit read+export, stats, terminal/whitelist/blacklist/datasource/baseline read
    auditor_perms = [1,3,5,7,12,21,22,26]
    # viewer: all read permissions + stats
    viewer_perms = [1,3,5,7,12,16,21,23,26,27]

    admin_rp = [{'role_id': 2, 'permission_id': pid} for pid in admin_perms]
    operator_rp = [{'role_id': 3, 'permission_id': pid} for pid in operator_perms]
    auditor_rp = [{'role_id': 4, 'permission_id': pid} for pid in auditor_perms]
    viewer_rp = [{'role_id': 5, 'permission_id': pid} for pid in viewer_perms]

    op.bulk_insert(role_permissions_table, admin_rp + operator_rp + auditor_rp + viewer_rp)
    # Note: superadmin (id=1) skips permission checks in code, no role_permissions needed

    # Migrate existing users: is_superuser=True -> superadmin, is_superuser=False -> viewer
    # NOTE: Non-superuser users are mapped to viewer (not operator) to avoid privilege escalation.
    # Operator role has terminal block/unblock and whitelist/blacklist write permissions.
    op.execute("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, 1 FROM users u WHERE u.is_superuser = True
        ON CONFLICT (user_id, role_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, 5 FROM users u WHERE u.is_superuser = False
        ON CONFLICT (user_id, role_id) DO NOTHING
    """)

    # Update PostgreSQL sequences to match seeded data IDs
    op.execute("SELECT setval('roles_id_seq', (SELECT COALESCE(MAX(id), 1) FROM roles))")
    op.execute("SELECT setval('permissions_id_seq', (SELECT COALESCE(MAX(id), 1) FROM permissions))")


def downgrade() -> None:
    """WARNING: This will permanently delete all RBAC data (roles, permissions, user-role mappings).
    User-role assignments will be lost. The is_superuser field on users table is preserved,
    but any role changes made after migration will NOT be reflected back to is_superuser.
    Consider backing up user_roles before running downgrade."""
    # Restore is_superuser from roles before dropping tables
    op.execute("""
        UPDATE users SET is_superuser = True
        WHERE id IN (SELECT user_id FROM user_roles WHERE role_id = 1)
    """)
    op.execute("""
        UPDATE users SET is_superuser = False
        WHERE id NOT IN (SELECT user_id FROM user_roles WHERE role_id = 1)
    """)
    op.drop_table('role_permissions')
    op.drop_table('user_roles')
    op.drop_table('permissions')
    op.drop_table('roles')
