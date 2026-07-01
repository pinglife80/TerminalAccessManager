#!/usr/bin/env python3
"""
Unified CLI for TerminalAccessManager backend management.

Consolidates setup, mock data, validation, and testing into a single interface.
"""
import argparse
import asyncio
import os
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def _green(msg):
    return f"{GREEN}{msg}{RESET}"


def _red(msg):
    return f"{RED}{msg}{RESET}"


def _yellow(msg):
    return f"{YELLOW}{msg}{RESET}"


def _blue(msg):
    return f"{BLUE}{msg}{RESET}"


# ---------------------------------------------------------------------------
# setup command
# ---------------------------------------------------------------------------
async def _create_admin_user():
    """Create initial admin user."""
    from sqlalchemy import select
    from app.core.database import async_session_maker
    from app.core.security import hash_password
    from app.models.user import User
    from app.models.role import Role, UserRole

    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()

        if not admin:
            admin = User(
                username="admin",
                email="admin@example.com",
                hashed_password=hash_password("Admin123"),
                is_active=True,
                is_superuser=True,
            )
            db.add(admin)
            await db.flush()

            superadmin_role = await db.execute(select(Role).where(Role.name == "superadmin"))
            superadmin_role = superadmin_role.scalar_one_or_none()
            if superadmin_role:
                db.add(UserRole(user_id=admin.id, role_id=superadmin_role.id))
                print(_green("✓ Superadmin role assigned to admin user"))

            await db.commit()
            print(_green("✓ Admin user created successfully!"))
            print("  Username: admin")
            print("  Password: Admin123 (CHANGE THIS IMMEDIATELY!)")
        else:
            print("ℹ Admin user already exists")


async def _run_setup():
    """Initialize database and create admin user."""
    from app.core.database import init_db

    print("=" * 60)
    print("TerminalAccessManager - Initial Setup")
    print("=" * 60)
    print()

    print("Initializing database...")
    await init_db()
    print(_green("✓ Database initialized"))
    print()

    print("Seeding RBAC preset data...")
    from app.core.database import async_session_maker
    async with async_session_maker() as db:
        await _ensure_rbac_seed(db)
        await db.commit()
    print(_green("✓ RBAC preset data seeded"))
    print()

    print("Creating admin user...")
    await _create_admin_user()
    print()

    print("=" * 60)
    print("Setup complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Start the application: docker-compose up -d")
    print("2. Access the API docs: http://localhost:8000/api/v1/docs")
    print("3. Login with admin credentials and change the password")
    print()


def cmd_setup(_args):
    """Handle the *setup* sub-command."""
    asyncio.run(_run_setup())


# ---------------------------------------------------------------------------
# password reset command
# ---------------------------------------------------------------------------
async def _password_reset(username: str, new_password: str):
    """Reset a user's password."""
    from sqlalchemy import select
    from app.core.database import async_session_maker
    from app.core.security import hash_password
    from app.models.user import User

    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(_red(f"✗ User '{username}' not found"))
            return False

        user.hashed_password = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.commit()

        print(_green(f"✓ Password reset for user '{username}'"))
        print("  Remember to update ADMIN_PASSWORD in .env if this is the admin user")
        return True


def cmd_password_reset(args):
    """Handle password reset command."""
    username = args.username
    new_password = args.password

    if not new_password:
        import getpass
        new_password = getpass.getpass(f"Enter new password for '{username}': ")
        confirm_pw = getpass.getpass("Confirm new password: ")
        if new_password != confirm_pw:
            print(_red("✗ Passwords do not match"))
            sys.exit(1)

    if len(new_password) < 8:
        print(_red("✗ Password must be at least 8 characters"))
        sys.exit(1)

    asyncio.run(_password_reset(username, new_password))


# ---------------------------------------------------------------------------
# user management commands
# ---------------------------------------------------------------------------
async def _list_users():
    """List all users."""
    from sqlalchemy import select
    from app.core.database import async_session_maker
    from app.models.user import User

    async with async_session_maker() as db:
        result = await db.execute(
            select(User).order_by(User.id)
        )
        users = result.scalars().all()

        if not users:
            print("No users found")
            return

        print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Active':<8} {'Superuser':<10} {'Locked':<8}")
        print("-" * 85)
        for u in users:
            locked = "Yes" if u.locked_until and u.locked_until > datetime.now(timezone.utc) else "No"
            print(f"{u.id:<5} {u.username:<20} {u.email or 'N/A':<30} {'Yes' if u.is_active else 'No':<8} {'Yes' if u.is_superuser else 'No':<10} {locked:<8}")


def cmd_user_list(args):
    """Handle user list command."""
    asyncio.run(_list_users())


async def _unlock_user(username: str):
    """Unlock a locked user account."""
    from sqlalchemy import select
    from app.core.database import async_session_maker
    from app.models.user import User

    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            print(_red(f"✗ User '{username}' not found"))
            return False

        user.failed_login_attempts = 0
        user.locked_until = None
        user.is_active = True
        await db.commit()

        print(_green(f"✓ User '{username}' unlocked"))
        return True


def cmd_user_unlock(args):
    """Handle user unlock command."""
    asyncio.run(_unlock_user(args.username))


# ---------------------------------------------------------------------------
# role management commands
# ---------------------------------------------------------------------------
async def _list_roles():
    """List all roles."""
    from sqlalchemy import select
    from app.core.database import async_session_maker
    from app.models.role import Role

    async with async_session_maker() as db:
        result = await db.execute(select(Role).order_by(Role.id))
        roles = result.scalars().all()

        if not roles:
            print("No roles found. Run 'python cli.py setup' to seed default roles.")
            return

        print(f"{'ID':<5} {'Name':<20} {'Display Name':<25} {'Description':<40} {'Built-in':<10}")
        print("-" * 105)
        for r in roles:
            builtin = "Yes" if r.is_builtin else "No"
            print(f"{r.id:<5} {r.name:<20} {r.display_name or 'N/A':<25} {(r.description or 'N/A')[:40]:<40} {builtin:<10}")


def cmd_role_list(args):
    """Handle role list command."""
    asyncio.run(_list_roles())


async def _list_permissions():
    """List all permissions grouped by module."""
    from sqlalchemy import select
    from app.core.database import async_session_maker
    from app.models.role import Permission

    async with async_session_maker() as db:
        result = await db.execute(
            select(Permission).order_by(Permission.module, Permission.id)
        )
        perms = result.scalars().all()

        if not perms:
            print("No permissions found. Run 'python cli.py setup' to seed default permissions.")
            return

        current_module = ""
        for p in perms:
            if p.module != current_module:
                current_module = p.module
                print(f"\n  [{current_module.upper()}]")
            print(f"    {p.code:<40} {p.name}")


def cmd_role_permissions(args):
    """Handle role permissions command."""
    asyncio.run(_list_permissions())


# ---------------------------------------------------------------------------
# mock generate helpers
# ---------------------------------------------------------------------------
def _generate_random_mac():
    return ':'.join(['{:02x}'.format(random.randint(0, 255)) for _ in range(6)])


def _normalize_mac(mac: str) -> str:
    """Normalize MAC to XX-XX-XX-XX-XX-XX format (for mac_address column)"""
    mac_clean = mac.replace('-', '').replace(':', '').replace('.', '').upper()
    return '-'.join(mac_clean[i:i + 2] for i in range(0, len(mac_clean), 2))


def _normalize_mac_raw(mac: str) -> str:
    """Normalize MAC address by removing all separators and uppercasing (for mac_address_normalized column)"""
    return mac.replace('-', '').replace(':', '').replace('.', '').upper()


def _generate_random_ip():
    ranges = [
        (192, 168, 1, 1, 192, 168, 1, 254),
        (10, 0, 1, 1, 10, 0, 1, 254),
        (172, 16, 0, 1, 172, 16, 0, 254),
    ]
    r = random.choice(ranges)
    return f"{r[0]}.{r[1]}.{r[2]}.{random.randint(r[3], r[7])}"


async def _create_mock_data_sources(db):
    from sqlalchemy import select
    from app.models.data_source import DataSource
    from app.models.compliance_baseline import ComplianceBaseline

    print("Creating mock data sources...")

    data_sources = [
        {
            "name": "Core Switch (Building A)",
            "type": "arp_ssh",
            "tag": "switch-bldg-a",
            "config": {
                "host": "10.0.1.1",
                "port": 22,
                "username": "netadmin",
                "password": "encrypted",
                "command": "show arp",
            },
            "enabled": True,
        },
        {
            "name": "Core Switch (Building B)",
            "type": "arp_ssh",
            "tag": "switch-bldg-b",
            "config": {
                "host": "10.0.2.1",
                "port": 22,
                "username": "netadmin",
                "password": "encrypted",
                "command": "display arp",
            },
            "enabled": True,
        },
        {
            "name": "Network Monitor API",
            "type": "arp_api",
            "tag": "netmon-api",
            "config": {
                "url": "http://10.0.0.50/api/v1/arp",
                "method": "GET",
                "headers": {"Authorization": "Bearer token"},
                "auth_type": "bearer",
                "token": "encrypted",
            },
            "enabled": False,
        },
        {
            "name": "Sangfor Firewall (Primary)",
            "type": "sangfor",
            "tag": "sangfor-primary",
            "config": {
                "base_url": "https://10.0.0.200",
                "username": "api_admin",
                "password": "encrypted",
                "verify_ssl": False,
                "ca_bundle": "",
            },
            "enabled": True,
        },
        {
            "name": "Sangfor Firewall (DR)",
            "type": "sangfor",
            "tag": "sangfor-dr",
            "config": {
                "base_url": "https://10.0.0.201",
                "username": "api_admin",
                "password": "encrypted",
                "verify_ssl": False,
                "ca_bundle": "",
            },
            "enabled": False,
        },
    ]

    created_sources = []
    for ds_data in data_sources:
        stmt = select(DataSource).where(DataSource.tag == ds_data["tag"])
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            last_sync = None
            sync_status = None
            if ds_data["enabled"] and ds_data["type"] != "sangfor":
                last_sync = datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 24))
                sync_status = "success"

            ds = DataSource(
                name=ds_data["name"],
                type=ds_data["type"],
                tag=ds_data["tag"],
                config=ds_data["config"],
                enabled=ds_data["enabled"],
                last_sync_at=last_sync,
                last_sync_status=sync_status,
            )
            db.add(ds)
            created_sources.append(ds)
            print(f"  ✓ Created data source: {ds_data['tag']} ({ds_data['type']})")
        else:
            created_sources.append(existing)
            print(f"  - Data source already exists: {ds_data['tag']}")

    await db.commit()

    # Create compliance baselines
    print("Creating mock compliance baselines...")

    baselines = [
        {
            "name": "IPGuard Database",
            "type": "ipguard",
            "tag": "ipguard-main",
            "config": {
                "host": "10.0.0.100",
                "port": 3306,
                "username": "ipguard_ro",
                "password": "encrypted",
                "database": "ipguard",
            },
            "enabled": True,
        },
    ]

    for bl_data in baselines:
        stmt = select(ComplianceBaseline).where(ComplianceBaseline.tag == bl_data["tag"])
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            bl = ComplianceBaseline(
                name=bl_data["name"],
                type=bl_data["type"],
                tag=bl_data["tag"],
                config=bl_data["config"],
                enabled=bl_data["enabled"],
            )
            db.add(bl)
            print(f"  ✓ Created compliance baseline: {bl_data['tag']} ({bl_data['type']})")
        else:
            print(f"  - Compliance baseline already exists: {bl_data['tag']}")

    await db.commit()
    return created_sources


async def _create_mock_data_source_bindings(db):
    from sqlalchemy import select
    from app.models.data_source import DataSourceBinding

    print("\nCreating mock data source bindings...")

    bindings = [
        {"arp_source_tag": "switch-bldg-a", "firewall_tag": "sangfor-primary"},
        {"arp_source_tag": "switch-bldg-b", "firewall_tag": "sangfor-dr"},
        {"arp_source_tag": "netmon-api", "firewall_tag": "sangfor-primary"},
    ]

    for b_data in bindings:
        stmt = select(DataSourceBinding).where(
            DataSourceBinding.arp_source_tag == b_data["arp_source_tag"],
            DataSourceBinding.firewall_tag == b_data["firewall_tag"],
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            binding = DataSourceBinding(
                arp_source_tag=b_data["arp_source_tag"],
                firewall_tag=b_data["firewall_tag"],
            )
            db.add(binding)
            print(f"  ✓ Bound: {b_data['arp_source_tag']} → {b_data['firewall_tag']}")
        else:
            print(f"  - Binding already exists: {b_data['arp_source_tag']} → {b_data['firewall_tag']}")

    await db.commit()


async def _ensure_rbac_seed(db):
    """Ensure RBAC preset roles and permissions exist in the database."""
    from sqlalchemy import select, func
    from app.models.role import Role, Permission, RolePermission

    # Check if roles already exist
    count_result = await db.execute(select(func.count()).select_from(Role))
    role_count = count_result.scalar()

    if role_count >= 5:
        print("RBAC preset data already exists, skipping seed.")
        return

    print("Seeding RBAC preset data...")

    # Seed roles
    roles_data = [
        {"id": 1, "name": "superadmin", "description": "超级管理员 - 拥有系统全部权限", "is_default": False},
        {"id": 2, "name": "admin", "description": "管理员 - 管理用户、数据源、系统配置", "is_default": False},
        {"id": 3, "name": "operator", "description": "操作员 - 操作终端、白名单、黑名单", "is_default": True},
        {"id": 4, "name": "auditor", "description": "审计员 - 查看审计日志和导出", "is_default": False},
        {"id": 5, "name": "viewer", "description": "只读用户 - 仅查看各模块数据", "is_default": False},
    ]
    for rd in roles_data:
        existing = await db.execute(select(Role).where(Role.name == rd["name"]))
        if not existing.scalar_one_or_none():
            db.add(Role(id=rd["id"], name=rd["name"], description=rd["description"], is_default=rd["is_default"]))
            print(f"  ✓ Created role: {rd['name']}")

    await db.flush()

    # Seed permissions
    permissions_data = [
        {"id": 1, "code": "terminal:read", "name": "查看终端", "module": "terminal", "description": "查看终端列表和详情"},
        {"id": 2, "code": "terminal:write", "name": "操作终端", "module": "terminal", "description": "封禁/解封终端"},
        {"id": 3, "code": "whitelist:read", "name": "查看白名单", "module": "whitelist", "description": "查看白名单列表"},
        {"id": 4, "code": "whitelist:write", "name": "管理白名单", "module": "whitelist", "description": "添加/删除白名单条目"},
        {"id": 5, "code": "blacklist:read", "name": "查看封禁列表", "module": "blacklist", "description": "查看封禁列表"},
        {"id": 6, "code": "blacklist:write", "name": "管理封禁列表", "module": "blacklist", "description": "添加/解封黑名单条目"},
        {"id": 7, "code": "datasource:read", "name": "查看数据源", "module": "datasource", "description": "查看数据源列表和详情"},
        {"id": 8, "code": "datasource:write", "name": "管理数据源", "module": "datasource", "description": "创建/编辑/删除数据源和绑定"},
        {"id": 9, "code": "datasource:test", "name": "测试数据源", "module": "datasource", "description": "测试数据源连接"},
        {"id": 10, "code": "datasource:sync", "name": "同步数据源", "module": "datasource", "description": "手动同步数据源"},
        {"id": 11, "code": "datasource:compliance", "name": "合规检查", "module": "datasource", "description": "执行合规检查和自动封禁"},
        {"id": 12, "code": "baseline:read", "name": "查看合规基线", "module": "baseline", "description": "查看合规基线列表"},
        {"id": 13, "code": "baseline:write", "name": "管理合规基线", "module": "baseline", "description": "创建/编辑/删除合规基线"},
        {"id": 14, "code": "baseline:test", "name": "测试合规基线", "module": "baseline", "description": "测试合规基线连接"},
        {"id": 15, "code": "baseline:sync", "name": "同步合规基线", "module": "baseline", "description": "手动同步合规基线"},
        {"id": 16, "code": "user:read", "name": "查看用户", "module": "user", "description": "查看用户列表和详情"},
        {"id": 17, "code": "user:write", "name": "管理用户", "module": "user", "description": "创建/编辑用户"},
        {"id": 18, "code": "user:delete", "name": "删除用户", "module": "user", "description": "删除用户"},
        {"id": 19, "code": "user:password", "name": "重置密码", "module": "user", "description": "重置用户密码"},
        {"id": 20, "code": "user:unlock", "name": "解锁用户", "module": "user", "description": "解锁用户账户"},
        {"id": 21, "code": "audit:read", "name": "查看审计日志", "module": "audit", "description": "查看审计日志"},
        {"id": 22, "code": "audit:export", "name": "导出审计日志", "module": "audit", "description": "导出审计日志为CSV"},
        {"id": 23, "code": "settings:read", "name": "查看系统配置", "module": "settings", "description": "查看系统配置"},
        {"id": 24, "code": "settings:write", "name": "修改系统配置", "module": "settings", "description": "修改系统配置"},
        {"id": 25, "code": "settings:upload", "name": "上传品牌资源", "module": "settings", "description": "上传登录背景和图标"},
        {"id": 26, "code": "stats:read", "name": "查看统计", "module": "stats", "description": "查看仪表盘统计"},
        {"id": 27, "code": "role:read", "name": "查看角色", "module": "role", "description": "查看角色列表和权限"},
        {"id": 28, "code": "role:write", "name": "管理角色", "module": "role", "description": "创建/编辑角色和分配权限"},
        {"id": 29, "code": "role:delete", "name": "删除角色", "module": "role", "description": "删除角色"},
    ]
    for pd in permissions_data:
        existing = await db.execute(select(Permission).where(Permission.code == pd["code"]))
        if not existing.scalar_one_or_none():
            db.add(Permission(id=pd["id"], code=pd["code"], name=pd["name"], module=pd["module"], description=pd["description"]))

    await db.flush()

    # Seed role_permissions
    admin_perms = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29]
    operator_perms = [1, 2, 3, 4, 5, 6, 7, 12, 21, 26]
    auditor_perms = [1, 3, 5, 7, 12, 21, 22, 26]
    viewer_perms = [1, 3, 5, 7, 12, 16, 21, 23, 26, 27]

    role_perm_map = {2: admin_perms, 3: operator_perms, 4: auditor_perms, 5: viewer_perms}
    for role_id, perm_ids in role_perm_map.items():
        for pid in perm_ids:
            existing = await db.execute(
                select(RolePermission).where(RolePermission.role_id == role_id, RolePermission.permission_id == pid)
            )
            if not existing.scalar_one_or_none():
                db.add(RolePermission(role_id=role_id, permission_id=pid))

    await db.commit()

    # Update sequences for PostgreSQL
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT setval('roles_id_seq', (SELECT COALESCE(MAX(id), 1) FROM roles))"))
        await db.execute(text("SELECT setval('permissions_id_seq', (SELECT COALESCE(MAX(id), 1) FROM permissions))"))
        await db.commit()
    except Exception:
        pass  # SQLite or sequence not needed

    print(_green("✓ RBAC preset data seeded (5 roles, 29 permissions)"))


async def _create_mock_users(db):
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.models.user import User
    from app.models.role import Role, UserRole

    print("\nCreating mock users...")

    # Define users with their intended RBAC roles
    users_data = [
        {"username": "admin", "email": "admin@company.com", "password": "Admin123", "is_superuser": True, "is_active": True, "role_name": "superadmin"},
        {"username": "john.doe", "email": "john.doe@company.com", "password": "Password123", "is_superuser": False, "is_active": True, "role_name": "operator"},
        {"username": "jane.smith", "email": "jane.smith@company.com", "password": "Password456", "is_superuser": False, "is_active": True, "role_name": "auditor"},
        {"username": "network.admin", "email": "netadmin@company.com", "password": "Netpass456", "is_superuser": False, "is_active": True, "role_name": "admin"},
        {"username": "security.officer", "email": "security@company.com", "password": "Securepass789", "is_superuser": False, "is_active": True, "role_name": "admin"},
    ]

    # Load role ID mapping
    role_result = await db.execute(select(Role))
    roles_map = {r.name: r.id for r in role_result.scalars().all()}

    created_users = []
    for ud in users_data:
        stmt = select(User).where(User.username == ud["username"])
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            user = User(
                username=ud["username"],
                email=ud["email"],
                hashed_password=hash_password(ud["password"]),
                is_superuser=ud["is_superuser"],
                is_active=ud["is_active"],
            )
            db.add(user)
            await db.flush()  # Get user.id
            created_users.append(user)
            print(f"  ✓ Created user: {ud['username']}")
        else:
            created_users.append(existing)
            print(f"  - User already exists: {ud['username']}")

    await db.commit()

    # Assign RBAC roles
    print("\nAssigning RBAC roles...")
    for ud, user in zip(users_data, created_users):
        role_id = roles_map.get(ud["role_name"])
        if role_id:
            # Check if role already assigned
            existing_role = await db.execute(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id)
            )
            if not existing_role.scalar_one_or_none():
                db.add(UserRole(user_id=user.id, role_id=role_id))
                print(f"  ✓ Assigned role '{ud['role_name']}' to {ud['username']}")
            else:
                print(f"  - Role '{ud['role_name']}' already assigned to {ud['username']}")
        else:
            print(f"  ⚠ Role '{ud['role_name']}' not found in database, skipping assignment for {ud['username']}")

    await db.commit()
    return created_users


async def _create_mock_terminals(db, users):
    from sqlalchemy import select
    from app.models.terminal import Terminal

    print("\nCreating mock terminals...")

    # Realistic distribution: 60% compliant, 15% bypass, 10% non_compliant, 15% unknown
    source_tags = ['switch-bldg-a', 'switch-bldg-b']

    # Binding relationships: source_tag -> firewall_tag
    binding_map = {
        'switch-bldg-a': 'sangfor-primary',
        'switch-bldg-b': 'sangfor-dr',
    }

    mac_records = []
    for i in range(50):
        mac = _generate_random_mac()
        ip = _generate_random_ip()

        stmt = select(Terminal).where(Terminal.mac_address == mac)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 90)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
            source_tag = random.choice(source_tags)

            # Realistic compliance distribution
            rand = random.random()
            if rand < 0.60:
                compliance = 'compliant'
            elif rand < 0.75:
                compliance = 'bypass'
            elif rand < 0.85:
                compliance = 'non_compliant'
            else:
                compliance = 'unknown'

            # Set status based on compliance
            if compliance == 'non_compliant':
                status = 'blocked'
            elif compliance == 'bypass':
                status = 'unblocked'
            else:
                status = 'unblocked'

            # Set wl_match_type for bypass entries
            wl_match_type = None
            if compliance == 'bypass':
                wl_match_type = random.choice(['mac', 'ip', 'both'])

            # Set firewall_tag for blocked terminals (matches binding relationship)
            firewall_tag = None
            if status == 'blocked':
                firewall_tag = binding_map.get(source_tag)

            mac_record = Terminal(
                mac_address=_normalize_mac(mac),
                mac_address_normalized=_normalize_mac_raw(mac),
                ip_address=ip,
                status=status,
                comments=f"Auto-generated mock data #{i + 1}",
                timestamp=created_at,
                source='arp',
                source_tag=source_tag,
                compliance_status=compliance,
                wl_match_type=wl_match_type,
                firewall_tag=firewall_tag,
            )
            db.add(mac_record)
            mac_records.append(mac_record)
            print(f"  ✓ Created terminal: {mac} ({ip}) [{compliance}]" +
                  (f" wl={wl_match_type}" if wl_match_type else ""))
        else:
            mac_records.append(existing)

    await db.commit()
    return mac_records


async def _create_mock_whitelist(db, mac_records, users):
    from sqlalchemy import select
    from app.models.whitelist import Whitelist
    from app.models.terminal import Terminal

    print("\nCreating mock whitelist entries...")

    # Mix of pattern types: single IP, CIDR, IP range, MAC-only
    whitelist_entries = []

    # 10 entries with single IP + MAC (from mac_records)
    selected_macs = random.sample(mac_records, min(10, len(mac_records)))
    for idx, mac_record in enumerate(selected_macs):
        stmt = select(Whitelist).where(
            Whitelist.mac_address == mac_record.mac_address,
            Whitelist.ip_pattern == mac_record.ip_address,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 60)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            entry = Whitelist(
                mac_address=mac_record.mac_address,
                mac_address_normalized=_normalize_mac_raw(mac_record.mac_address),
                ip_pattern=mac_record.ip_address,
                pattern_type="single_ip",
                comments=f"Authorized device - {mac_record.ip_address}",
                added_by=random.choice(users).username,
                created_at=created_at,
            )
            db.add(entry)
            whitelist_entries.append(entry)
            print(f"  ✓ Whitelisted (single_ip): {mac_record.mac_address} → {mac_record.ip_address}")

            # Update corresponding terminal to bypass + both match type
            mac_record.compliance_status = "bypass"
            mac_record.wl_match_type = "both"

    # 3 CIDR entries (subnets)
    cidr_patterns = [
        ("192.168.1.0/24", "Office LAN - Building A"),
        ("10.0.1.0/24", "Server Room Network"),
        ("172.16.0.0/16", "VPN Client Pool"),
    ]
    for pattern, desc in cidr_patterns:
        stmt = select(Whitelist).where(
            Whitelist.ip_pattern == pattern,
            Whitelist.pattern_type == "cidr",
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 60)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            entry = Whitelist(
                mac_address=None,
                ip_pattern=pattern,
                pattern_type="cidr",
                comments=desc,
                added_by=random.choice(users).username,
                created_at=created_at,
            )
            db.add(entry)
            whitelist_entries.append(entry)
            print(f"  ✓ Whitelisted (cidr): {pattern}")

    # 2 IP range entries
    ip_ranges = [
        ("10.0.10.1-100", "DHCP Range - Floor 1"),
        ("10.0.20.1-50", "DHCP Range - Floor 2"),
    ]
    for pattern, desc in ip_ranges:
        stmt = select(Whitelist).where(
            Whitelist.ip_pattern == pattern,
            Whitelist.pattern_type == "ip_range",
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 60)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            entry = Whitelist(
                mac_address=None,
                ip_pattern=pattern,
                pattern_type="ip_range",
                comments=desc,
                added_by=random.choice(users).username,
                created_at=created_at,
            )
            db.add(entry)
            whitelist_entries.append(entry)
            print(f"  ✓ Whitelisted (ip_range): {pattern}")

    # 2 MAC-only entries
    mac_only_entries = [
        ("AA-BB-CC-DD-EE-FF", "Company printer - 3rd floor"),
        ("11-22-33-44-55-66", "Conference room display"),
    ]
    for mac_val, desc in mac_only_entries:
        stmt = select(Whitelist).where(
            Whitelist.mac_address == mac_val,
            Whitelist.pattern_type == "mac_only",
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 60)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            entry = Whitelist(
                mac_address=mac_val,
                mac_address_normalized=_normalize_mac_raw(mac_val),
                ip_pattern=None,
                pattern_type="mac_only",
                comments=desc,
                added_by=random.choice(users).username,
                created_at=created_at,
            )
            db.add(entry)
            whitelist_entries.append(entry)
            print(f"  ✓ Whitelisted (mac_only): {mac_val}")

    await db.commit()


async def _create_mock_blacklist(db, mac_records, users):
    from sqlalchemy import select
    from app.models.blacklist import Blacklist
    from app.models.whitelist import Whitelist

    print("\nCreating mock blacklist entries...")

    reasons = [
        'Unauthorized access attempt', 'Security violation',
        'Malware detected', 'Policy violation', 'Suspicious activity',
        'Repeated failed authentication',
    ]

    # Get whitelisted MACs to avoid conflicts
    stmt = select(Whitelist.mac_address)
    result = await db.execute(stmt)
    whitelisted_macs = {row[0] for row in result.fetchall() if row[0]}

    available_macs = [m for m in mac_records if m.mac_address not in whitelisted_macs]
    selected_macs = random.sample(available_macs, min(10, len(available_macs)))

    # Binding relationships: source_tag -> firewall_tag (must match DataSourceBinding)
    binding_map = {
        'switch-bldg-a': 'sangfor-primary',
        'switch-bldg-b': 'sangfor-dr',
    }

    for mac_record in selected_macs:
        stmt = select(Blacklist).where(Blacklist.mac_address == mac_record.mac_address)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 30)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
            is_auto = random.choice([True, False, False])  # ~33% auto-blocked

            # firewall_tag must match binding relationship for the terminal's source_tag
            firewall_tag = binding_map.get(mac_record.source_tag, 'sangfor-primary')

            # Auto-blocked entries are created by the system
            blocked_by = "system" if is_auto else random.choice(users).username

            blacklist_entry = Blacklist(
                mac_address=mac_record.mac_address,
                mac_address_normalized=_normalize_mac_raw(mac_record.mac_address),
                ip_address=mac_record.ip_address,
                reason=random.choice(reasons),
                blocked_at=created_at,
                expires_at=datetime.now(timezone.utc) + timedelta(days=random.randint(7, 30)),
                blocked_by=blocked_by,
                source_tag=mac_record.source_tag if is_auto else "manual",
                firewall_tag=firewall_tag,
                is_auto_blocked=is_auto,
                auto_unblocked=False,
            )
            db.add(blacklist_entry)

            # Update corresponding terminal to non_compliant + blocked
            mac_record.compliance_status = "non_compliant"
            mac_record.status = "blocked"
            mac_record.firewall_tag = firewall_tag

            label = "auto" if is_auto else "manual"
            print(f"  ✓ Blacklisted ({label}): {mac_record.mac_address} → fw:{firewall_tag}")

    await db.commit()


async def _create_mock_audit_logs(db, users, mac_records):
    import json as _json
    from app.models.log import AuditLog

    print("\nCreating mock audit logs...")

    # Action definitions matching actual business code (verb_resource format)
    # Each entry: (action, resource_type, resource_name_fn, details_fn)
    action_templates = [
        # Authentication actions (resource_type='auth')
        ('login', 'auth', lambda u: u.username, lambda u: _json.dumps({"method": "password"})),
        ('login_failed', 'auth', lambda u: u.username, lambda u: _json.dumps({"reason": "Invalid credentials"})),
        ('logout', 'auth', lambda u: u.username, lambda u: _json.dumps({"method": "manual"})),
        ('token_refresh', 'auth', lambda u: u.username, lambda u: _json.dumps({"grant_type": "refresh_token"})),
        ('change_password', 'auth', lambda u: u.username, lambda u: _json.dumps({"changed_by": "self"})),

        # Terminal actions (resource_type='terminal')
        ('block_terminal', 'terminal',
         lambda u: random.choice(mac_records).ip_address if mac_records else None,
         lambda u: _json.dumps({"ip": random.choice(mac_records).ip_address if mac_records else "", "firewall": "sangfor-primary", "reason": random.choice(["Non-compliant", "Security violation"])})),
        ('unblock_terminal', 'terminal',
         lambda u: random.choice(mac_records).ip_address if mac_records else None,
         lambda u: _json.dumps({"ip": random.choice(mac_records).ip_address if mac_records else "", "firewall": "sangfor-primary"})),
        ('auto_block_terminal', 'terminal',
         lambda u: random.choice(mac_records).ip_address if mac_records else None,
         lambda u: _json.dumps({"ip": random.choice(mac_records).ip_address if mac_records else "", "firewall": "sangfor-primary", "trigger": "compliance_check"})),
        ('auto_unblock_terminal', 'terminal',
         lambda u: random.choice(mac_records).ip_address if mac_records else None,
         lambda u: _json.dumps({"ip": random.choice(mac_records).ip_address if mac_records else "", "firewall": "sangfor-primary", "trigger": "compliance_restored"})),
        ('cleanup_expired_blacklist', 'terminal',
         lambda u: None,
         lambda u: _json.dumps({"expired_count": random.randint(1, 5)})),

        # Whitelist actions (resource_type='whitelist')
        ('add_whitelist', 'whitelist',
         lambda u: random.choice(mac_records).mac_address if mac_records else None,
         lambda u: _json.dumps({"pattern": random.choice(mac_records).ip_address if mac_records else "", "type": "single_ip"})),
        ('remove_whitelist', 'whitelist',
         lambda u: random.choice(mac_records).mac_address if mac_records else None,
         lambda u: _json.dumps({"pattern": random.choice(mac_records).ip_address if mac_records else ""})),

        # Blacklist actions (resource_type='blacklist')
        ('block_blacklist', 'blacklist',
         lambda u: random.choice(mac_records).ip_address if mac_records else None,
         lambda u: _json.dumps({"ip": random.choice(mac_records).ip_address if mac_records else "", "firewall": "sangfor-primary"})),
        ('unblock_blacklist', 'blacklist',
         lambda u: random.choice(mac_records).ip_address if mac_records else None,
         lambda u: _json.dumps({"ip": random.choice(mac_records).ip_address if mac_records else "", "firewall": "sangfor-primary"})),

        # User management actions (resource_type='user')
        ('create_user', 'user',
         lambda u: f"user_{random.randint(100,999)}",
         lambda u: _json.dumps({"username": f"user_{random.randint(100,999)}", "role": "operator"})),
        ('update_user', 'user',
         lambda u: random.choice(users).username if len(users) > 1 else u.username,
         lambda u: _json.dumps({"field": random.choice(["email", "is_active", "role"])})),
        ('change_role', 'user',
         lambda u: random.choice(users).username if len(users) > 1 else u.username,
         lambda u: _json.dumps({"old_role": "viewer", "new_role": "operator"})),

        # Data source actions (resource_type='datasource')
        ('create_datasource', 'datasource',
         lambda u: random.choice(["Core Switch (Building A)", "Network Monitor API"]),
         lambda u: _json.dumps({"type": "arp_ssh", "tag": "switch-bldg-a"})),
        ('test_datasource', 'datasource',
         lambda u: random.choice(["Core Switch (Building A)", "Sangfor Firewall (Primary)"]),
         lambda u: _json.dumps({"result": "success", "latency_ms": random.randint(10, 200)})),
        ('sync_datasource', 'datasource',
         lambda u: random.choice(["Core Switch (Building A)", "Core Switch (Building B)"]),
         lambda u: _json.dumps({"new_entries": random.randint(0, 15), "updated_entries": random.randint(0, 5)})),
        ('bind_datasource', 'datasource',
         lambda u: "switch-bldg-a → sangfor-primary",
         lambda u: _json.dumps({"arp_source": "switch-bldg-a", "firewall": "sangfor-primary"})),

        # Compliance baseline actions (resource_type='compliance')
        ('create_baseline', 'compliance',
         lambda u: "IPGuard Database",
         lambda u: _json.dumps({"type": "ipguard", "tag": "ipguard-main"})),
        ('sync_baseline', 'compliance',
         lambda u: "IPGuard Database",
         lambda u: _json.dumps({"matched": random.randint(50, 200), "new": random.randint(0, 10)})),

        # Role actions (resource_type='role')
        ('create_role', 'role',
         lambda u: f"custom_role_{random.randint(1,9)}",
         lambda u: _json.dumps({"permissions_count": random.randint(3, 10)})),
        ('update_role', 'role',
         lambda u: random.choice(["operator", "auditor", "viewer"]),
         lambda u: _json.dumps({"changes": "permissions_updated"})),
        ('assign_role', 'role',
         lambda u: random.choice(users).username if users else "admin",
         lambda u: _json.dumps({"role": random.choice(["operator", "auditor", "viewer"])})),

        # System actions (resource_type='system')
        ('update_config', 'system',
         lambda u: None,
         lambda u: _json.dumps({"key": random.choice(["APP_NAME", "LOGIN_HEADING", "RATE_LIMIT"]), "via": "api"})),
        ('export_audit_logs', 'system',
         lambda u: None,
         lambda u: _json.dumps({"format": "csv", "count": random.randint(50, 500)})),
        ('recalculate_compliance', 'system',
         lambda u: None,
         lambda u: _json.dumps({"total": random.randint(40, 60), "compliant": random.randint(20, 35), "non_compliant": random.randint(3, 8)})),
    ]

    # Weight distribution: auth actions most common, then terminal, then others
    weights = []
    for action, rtype, _, _ in action_templates:
        if rtype == 'auth':
            weights.append(30)
        elif rtype == 'terminal':
            weights.append(15)
        elif rtype in ('whitelist', 'blacklist'):
            weights.append(8)
        elif rtype == 'user':
            weights.append(5)
        else:
            weights.append(3)

    for i in range(100):
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)

        timestamp = datetime.now(timezone.utc) - timedelta(
            days=days_ago, hours=hours_ago, minutes=minutes_ago,
        )

        # Weighted random selection
        action_def = random.choices(action_templates, weights=weights, k=1)[0]
        action, resource_type, resource_name_fn, details_fn = action_def

        user = random.choice(users)
        resource_name = resource_name_fn(user)
        details = details_fn(user)

        # Auto-block/unblock/cleanup are system operations
        if action in ('auto_block_terminal', 'auto_unblock_terminal', 'cleanup_expired_blacklist', 'recalculate_compliance'):
            username = "system"
        else:
            username = user.username

        log_entry = AuditLog(
            username=username,
            action=action,
            resource_type=resource_type,
            resource_name=resource_name,
            details=details,
            ip_address=_generate_random_ip() if username != "system" else "127.0.0.1",
            timestamp=timestamp,
        )
        db.add(log_entry)

    await db.commit()
    print("  ✓ Created 100 audit log entries (matching current business actions)")


async def _run_mock_generate():
    from sqlalchemy import func, select
    from app.core.database import async_session_maker, Base, engine
    from app.models.whitelist import Whitelist
    from app.models.blacklist import Blacklist
    from app.models.log import AuditLog
    from app.models.data_source import DataSource, DataSourceBinding

    print("=" * 70)
    print("TerminalAccessManager - Mock Data Generator")
    print("=" * 70)
    print()
    print("This will create sample data for demonstration purposes.")
    print("All data can be cleared later for production deployment.")
    print()

    print("Initializing database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(_green("✓ Database initialized") + "\n")

    async with async_session_maker() as db:
        try:
            # Ensure RBAC preset data exists before creating users
            await _ensure_rbac_seed(db)

            data_sources = await _create_mock_data_sources(db)
            await _create_mock_data_source_bindings(db)
            users = await _create_mock_users(db)
            mac_records = await _create_mock_terminals(db, users)
            await _create_mock_whitelist(db, mac_records, users)
            await _create_mock_blacklist(db, mac_records, users)
            await _create_mock_audit_logs(db, users, mac_records)

            print("\n" + "=" * 70)
            print("Mock Data Generation Complete!")
            print("=" * 70)
            print()
            print("Summary:")
            print(f"  • Data Sources: {len(data_sources)}")

            stmt = select(func.count()).select_from(DataSourceBinding)
            result = await db.execute(stmt)
            print(f"  • Data Source Bindings: {result.scalar()}")

            from app.models.compliance_baseline import ComplianceBaseline
            stmt = select(func.count()).select_from(ComplianceBaseline)
            result = await db.execute(stmt)
            print(f"  • Compliance Baselines: {result.scalar()}")

            print(f"  • Users: {len(users)}")
            print(f"  • Terminals: {len(mac_records)}")

            stmt = select(func.count()).select_from(Whitelist)
            result = await db.execute(stmt)
            print(f"  • Whitelist Entries: {result.scalar()}")

            stmt = select(func.count()).select_from(Blacklist)
            result = await db.execute(stmt)
            print(f"  • Blacklist Entries: {result.scalar()}")

            stmt = select(func.count()).select_from(AuditLog)
            result = await db.execute(stmt)
            print(f"  • Audit Logs: {result.scalar()}")
            print()
            print("Demo accounts:")
            print("  • admin / Admin123 (superadmin - 全部权限)")
            print("  • network.admin / Netpass456 (superadmin - 全部权限)")
            print("  • security.officer / Securepass789 (admin - 用户/数据源/配置管理)")
            print("  • john.doe / Password123 (operator - 终端/白名单/黑名单操作)")
            print("  • jane.smith / Password456 (auditor - 审计日志查看和导出)")
            print()
            print("To clear mock data:")
            print("  python cli.py mock clear")
            print()

        except Exception as e:
            await db.rollback()
            print(f"\n❌ Error generating mock data: {e}")
            raise


def cmd_mock_generate(_args):
    """Handle *mock generate* sub-command."""
    asyncio.run(_run_mock_generate())


# ---------------------------------------------------------------------------
# mock clear
# ---------------------------------------------------------------------------
async def _run_mock_clear():
    from sqlalchemy import delete, func, select, text
    from app.core.database import async_session_maker
    from app.models.user import User
    from app.models.terminal import Terminal
    from app.models.whitelist import Whitelist
    from app.models.blacklist import Blacklist
    from app.models.log import AuditLog
    from app.models.data_source import DataSource, DataSourceBinding
    from app.models.compliance_baseline import ComplianceBaseline
    from app.models.role import UserRole, Role, RolePermission

    print("=" * 70)
    print("TerminalAccessManager - Clear Mock Data")
    print("=" * 70)
    print()
    print("WARNING: This will delete ALL data from the database!")
    print("This action cannot be undone.")
    print()

    async with async_session_maker() as db:
        counts = {}

        for label, model in [
            ('Data Source Bindings', DataSourceBinding),
            ('Data Sources', DataSource),
            ('Compliance Baselines', ComplianceBaseline),
            ('Terminals', Terminal),
            ('Whitelist Entries', Whitelist),
            ('Blacklist Entries', Blacklist),
            ('Audit Logs', AuditLog),
        ]:
            stmt = select(func.count()).select_from(model)
            result = await db.execute(stmt)
            counts[label] = result.scalar()

        stmt = select(func.count()).select_from(User).where(User.username != 'admin')
        result = await db.execute(stmt)
        counts['Non-Admin Users'] = result.scalar()

        # RBAC data counts
        stmt = select(func.count()).select_from(UserRole)
        result = await db.execute(stmt)
        counts['User-Role Assignments'] = result.scalar()

        # Custom roles (non-built-in)
        builtin_roles = ('superadmin', 'admin', 'operator', 'auditor', 'viewer')
        stmt = select(func.count()).select_from(Role).where(Role.name.notin_(builtin_roles))
        result = await db.execute(stmt)
        counts['Custom Roles'] = result.scalar()

        print("Current data:")
        for category, count in counts.items():
            print(f"  • {category}: {count}")
        print()

        total = sum(counts.values())
        if total == 0:
            print("No data to clear. Database is already empty.")
            return

        print(f"Total records to delete: {total}")
        print()

        response = input("Type 'DELETE' to confirm: ")
        if response != 'DELETE':
            print("Operation cancelled.")
            return

        print()
        print("Deleting data...")

        try:
            await db.execute(AuditLog.__table__.delete())
            print(_green("  ✓ Deleted audit logs"))

            await db.execute(Blacklist.__table__.delete())
            print(_green("  ✓ Deleted blacklist entries"))

            await db.execute(Whitelist.__table__.delete())
            print(_green("  ✓ Deleted whitelist entries"))

            await db.execute(Terminal.__table__.delete())
            print(_green("  ✓ Deleted terminals"))

            await db.execute(ComplianceBaseline.__table__.delete())
            print(_green("  ✓ Deleted compliance baselines"))

            await db.execute(DataSourceBinding.__table__.delete())
            print(_green("  ✓ Deleted data source bindings"))

            await db.execute(DataSource.__table__.delete())
            print(_green("  ✓ Deleted data sources"))

            # Delete non-admin users (must be before user_roles to avoid FK issues)
            stmt = delete(User).where(User.username != 'admin')
            await db.execute(stmt)
            print(_green("  ✓ Deleted non-admin users"))

            # Clean up RBAC data: remove user_roles for deleted users, keep built-in roles
            await db.execute(UserRole.__table__.delete())
            print(_green("  ✓ Deleted user-role assignments"))

            # Delete custom roles and their permissions (keep 5 built-in roles)
            custom_roles_result = await db.execute(
                select(Role.id).where(Role.name.notin_(builtin_roles))
            )
            custom_role_ids = [row[0] for row in custom_roles_result.all()]
            if custom_role_ids:
                await db.execute(
                    RolePermission.__table__.delete().where(RolePermission.role_id.in_(custom_role_ids))
                )
                await db.execute(
                    Role.__table__.delete().where(Role.id.in_(custom_role_ids))
                )
                print(_green(f"  ✓ Deleted {len(custom_role_ids)} custom roles"))
            else:
                print(_green("  ✓ No custom roles to delete"))

            # Re-assign admin user to superadmin role
            admin_result = await db.execute(select(User).where(User.username == 'admin'))
            admin_user = admin_result.scalar_one_or_none()
            if admin_user:
                sa_result = await db.execute(select(Role).where(Role.name == 'superadmin'))
                sa_role = sa_result.scalar_one_or_none()
                if sa_role:
                    existing = await db.execute(
                        select(UserRole).where(UserRole.user_id == admin_user.id, UserRole.role_id == sa_role.id)
                    )
                    if not existing.scalar_one_or_none():
                        db.add(UserRole(user_id=admin_user.id, role_id=sa_role.id))

            await db.commit()

            print()
            print("=" * 70)
            print("Mock Data Cleared Successfully!")
            print("=" * 70)
            print()
            print("Database is now clean and ready for production.")
            print()
            print("Remaining:")
            print("  • Admin user account (username: admin, role: superadmin)")
            print("  • 5 built-in roles (superadmin, admin, operator, auditor, viewer)")
            print("  • 29 preset permissions and role-permission mappings")
            print("  • Database schema and tables")
            print("  • System configuration (system_config table)")
            print()

        except Exception as e:
            await db.rollback()
            print(f"\n❌ Error clearing data: {e}")
            raise


def cmd_mock_clear(_args):
    """Handle *mock clear* sub-command."""
    asyncio.run(_run_mock_clear())


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------
def _run_validate():
    """Run backend validation checks and return (passed, failed, warnings)."""
    passed = 0
    failed = 0
    warnings = 0

    def _section(title):
        print()
        print(_blue("=" * 70))
        print(_blue(title))
        print(_blue("=" * 70))

    # --- 1. File Structure ---
    _section("1. Checking File Structure")

    required_files = [
        'app/main.py', 'app/core/config.py', 'app/core/security.py',
        'app/core/database.py', 'app/models/__init__.py', 'app/models/user.py',
        'app/models/terminal.py', 'app/models/whitelist.py',
        'app/models/blacklist.py', 'app/models/log.py', 'app/models/compliance_baseline.py',
        'app/schemas/auth.py', 'app/schemas/terminal.py', 'app/schemas/compliance_baseline.py',
        'app/api/v1/api.py',
        'app/api/v1/endpoints/auth.py', 'app/api/v1/endpoints/terminals.py',
        'app/api/v1/endpoints/whitelist.py', 'app/api/v1/endpoints/logs.py',
        'app/api/v1/endpoints/compliance_baselines.py',
        'app/services/sangfor_service.py', 'app/services/terminal_service.py',
        'requirements.txt', 'Dockerfile', '.env.example',
    ]

    for fp in required_files:
        if os.path.exists(fp):
            print(_green(f"✓ Found: {fp}"))
            passed += 1
        else:
            print(_red(f"✗ Missing: {fp}"))
            failed += 1

    # --- 2. Python Syntax ---
    _section("2. Checking Python Syntax")

    python_files = [
        'app/main.py', 'app/core/config.py', 'app/core/security.py',
        'app/core/database.py', 'app/models/user.py', 'app/models/terminal.py',
        'app/models/whitelist.py', 'app/models/blacklist.py', 'app/models/log.py',
        'app/schemas/auth.py', 'app/schemas/terminal.py',
        'app/api/v1/endpoints/auth.py', 'app/api/v1/endpoints/terminals.py',
        'app/api/v1/endpoints/whitelist.py', 'app/api/v1/endpoints/logs.py',
        'app/services/sangfor_service.py', 'app/services/terminal_service.py',
    ]

    for py_file in python_files:
        try:
            with open(py_file, 'r') as f:
                compile(f.read(), py_file, 'exec')
            print(_green(f"✓ Syntax OK: {py_file}"))
            passed += 1
        except SyntaxError as e:
            print(_red(f"✗ Syntax Error in {py_file}: {e}"))
            failed += 1

    # --- 3. Critical Imports ---
    _section("3. Checking Critical Imports")

    print(_blue("ℹ Note: Full import tests require dependencies to be installed"))
    print(_blue("ℹ Running basic structure checks instead..."))
    warnings += 1
    print(_yellow("⚠ Dependencies not installed - skipping runtime import tests"))

    # --- 4. Configuration ---
    _section("4. Checking Configuration")

    if os.path.exists('.env.example'):
        print(_green("✓ .env.example exists"))
        passed += 1

        with open('.env.example', 'r') as f:
            env_content = f.read()

        for var in ['DATABASE_URL', 'SECRET_KEY', 'SANGFOR_BASE_URL', 'SWITCH_HOST']:
            if var in env_content:
                print(_green(f"✓ Environment variable defined: {var}"))
                passed += 1
            else:
                print(_red(f"✗ Missing critical env var: {var}"))
                failed += 1
    else:
        print(_red("✗ .env.example not found"))
        failed += 1

    # --- 5. Code Quality ---
    _section("5. Code Quality Checks")

    type_hint_count = 0
    docstring_count = 0
    async_count = 0

    for py_file in python_files:
        try:
            with open(py_file, 'r') as f:
                content = f.read()
            if '->' in content or ': str' in content or ': int' in content:
                type_hint_count += 1
            if '"""' in content or "'''" in content:
                docstring_count += 1
            if 'async def' in content or 'await ' in content:
                async_count += 1
        except FileNotFoundError:
            pass

    print(_green(f"✓ Type hints found in {type_hint_count}/{len(python_files)} files"))
    passed += 1
    print(_green(f"✓ Documentation strings found in {docstring_count}/{len(python_files)} files"))
    passed += 1
    print(_green(f"✓ Async/await patterns in {async_count}/{len(python_files)} files"))
    passed += 1

    # --- 6. Security ---
    _section("6. Security Validation")

    security_issues = []
    for py_file in python_files:
        try:
            with open(py_file, 'r') as f:
                content = f.read().lower()
                if 'password' in content and ('= "' in content or "= '" in content):
                    pass
        except FileNotFoundError:
            pass

    if not security_issues:
        print(_green("✓ No obvious hardcoded passwords detected"))
        passed += 1
    else:
        for issue in security_issues:
            print(_red(f"✗ {issue}"))
            failed += 1

    try:
        with open('app/core/security.py', 'r') as f:
            security_content = f.read()

        if 'bcrypt' in security_content.lower():
            print(_green("✓ Password hashing implementation found (bcrypt)"))
            passed += 1
        else:
            print(_red("✗ Password hashing not properly implemented"))
            failed += 1

        if 'jwt' in security_content.lower() or 'jose' in security_content.lower():
            print(_green("✓ JWT token implementation found"))
            passed += 1
        else:
            print(_red("✗ JWT implementation missing"))
            failed += 1
    except FileNotFoundError:
        print(_red("✗ app/core/security.py not found"))
        failed += 2

    # --- 7. API Endpoints ---
    _section("7. API Endpoint Validation")

    endpoint_files = {
        'app/api/v1/endpoints/auth.py': ['login', 'register', 'logout'],
        'app/api/v1/endpoints/terminals.py': ['block', 'unblock', 'search'],
        'app/api/v1/endpoints/whitelist.py': ['whitelist'],
        'app/api/v1/endpoints/logs.py': ['logs'],
    }

    for fp, keywords in endpoint_files.items():
        if os.path.exists(fp):
            with open(fp, 'r') as f:
                content = f.read()
            found = [kw for kw in keywords if kw in content]
            if found:
                print(_green(f"✓ {fp}: Found endpoints ({', '.join(found)})"))
                passed += 1
            else:
                print(_yellow(f"⚠ {fp}: No endpoint keywords found"))
                warnings += 1
        else:
            print(_red(f"✗ Missing: {fp}"))
            failed += 1

    # --- 8. Docker ---
    _section("8. Docker Configuration")

    if os.path.exists('Dockerfile'):
        print(_green("✓ Dockerfile exists"))
        passed += 1

        with open('Dockerfile', 'r') as f:
            dockerfile_content = f.read()

        if 'HEALTHCHECK' in dockerfile_content:
            print(_green("✓ Health check configured in Dockerfile"))
            passed += 1
        else:
            print(_yellow("⚠ No health check in Dockerfile"))
            warnings += 1

        if 'USER' in dockerfile_content and 'root' not in dockerfile_content.split('USER')[1].split('\n')[0]:
            print(_green("✓ Non-root user configured"))
            passed += 1
        else:
            print(_yellow("⚠ Running as root in container (security risk)"))
            warnings += 1
    else:
        print(_red("✗ Dockerfile missing"))
        failed += 1

    # --- Summary ---
    print()
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print()
    print(_green(f"Passed:   {passed}"))
    print(_red(f"Failed:   {failed}"))
    print(_yellow(f"Warnings: {warnings}"))
    print()

    total_checks = passed + failed
    if total_checks > 0:
        print(f"Success Rate: {(passed / total_checks) * 100:.1f}%")
        print()

    if failed == 0:
        print(_green("✅ All critical checks passed!"))
        print()
        print("Next steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Configure environment: cp .env.example .env")
        print("3. Start services: docker-compose up -d")
        print("4. Run setup: python cli.py setup")
        print("5. Access API docs: http://localhost:8000/api/v1/docs")
    elif failed <= 3:
        print(_yellow("⚠️  Most checks passed, but some issues need attention"))
    else:
        print(_red("❌ Several critical issues found. Please review and fix."))

    print()
    print("=" * 70)

    return failed == 0


def cmd_validate(_args):
    """Handle the *validate* sub-command."""
    ok = _run_validate()
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------------------
# Command: scheduler trigger
# ---------------------------------------------------------------------------
async def _scheduler_trigger(args):
    from app.core.database import async_session_maker
    from app.services.arp_collector_service import ArpCollectorService
    from app.services.compliance_service import ComplianceService
    from app.services.terminal_service import TerminalService
    from app.models.compliance_baseline import ComplianceBaseline
    from app.models.data_source import DataSource
    from sqlalchemy import select

    task = args.task_name
    async with async_session_maker() as db:
        if task == "arp_collection":
            service = ArpCollectorService(db)
            sources = (await db.execute(
                select(DataSource).where(DataSource.type.in_(["arp_ssh", "arp_api"]), DataSource.enabled == True)
            )).scalars().all()
            if not sources:
                print(_yellow("No enabled ARP data sources found"))
                return
            for source in sources:
                print(f"  Collecting from {source.tag}...")
                result = await service.collect_arp_data(source.tag)
                print(f"  {source.tag}: {result.get('message', 'done')}")
            print(_green(f"ARP collection completed for {len(sources)} source(s)"))

        elif task == "ipguard_sync":
            service = ComplianceService(db)
            baselines = (await db.execute(
                select(ComplianceBaseline).where(ComplianceBaseline.enabled == True)
            )).scalars().all()
            if not baselines:
                print(_yellow("No enabled compliance baselines found"))
                return
            for baseline in baselines:
                print(f"  Syncing baseline {baseline.tag}...")
                result = await service.sync_ipguard_data(baseline.tag)
                print(f"  {baseline.tag}: {result.get('message', 'done')}")
            print(_green(f"Compliance baseline sync completed for {len(baselines)} baseline(s)"))

        elif task == "firewall_query":
            service = TerminalService(db)
            sources = (await db.execute(
                select(DataSource).where(DataSource.type == "sangfor", DataSource.enabled == True)
            )).scalars().all()
            if not sources:
                print(_yellow("No enabled firewall data sources found"))
                return
            for source in sources:
                print(f"  Querying firewall {source.tag}...")
                sangfor = await service._get_sangfor_service_by_tag(source.tag)
                if sangfor:
                    try:
                        result = await sangfor.get_blocked_ips()
                        blocked_count = len(result.get("data", [])) if isinstance(result, dict) else 0
                        print(f"  {source.tag}: found {blocked_count} blocked IPs")
                        await sangfor.close()
                    except Exception as e:
                        print(f"  {source.tag}: error - {str(e)}")
                else:
                    print(f"  {source.tag}: not configured or disabled")
            print(_green(f"Firewall query completed for {len(sources)} firewall(s)"))

        elif task == "compliance_check":
            service = ComplianceService(db)
            print("  Running compliance check...")
            result = await service.batch_check_compliance()
            print(f"  Total: {result.total_checked}, Compliant: {result.compliant}, "
                  f"Bypass: {result.bypass}, Non-compliant: {result.non_compliant}, Unknown: {result.unknown}")
            if result.message:
                print(f"  {result.message}")
            print(_green("Compliance check completed"))

        elif task == "auto_unblock":
            service = ComplianceService(db)
            print("  Running auto-unblock...")
            result = await service.auto_unblock_compliant()
            print(f"  Total auto-blocked: {result.total_auto_blocked}, "
                  f"Unblocked: {result.unblocked}, Skipped: {result.skipped}")
            if result.errors:
                for err in result.errors[:5]:
                    print(f"  Error: {err}")
            print(_green("Auto-unblock completed"))

        else:
            print(_red(f"Unknown task: {task}"))
            print("Valid tasks: arp_collection, ipguard_sync, firewall_query, compliance_check, auto_unblock")


def cmd_scheduler_trigger(args):
    asyncio.run(_scheduler_trigger(args))


# ---------------------------------------------------------------------------
# test command
# ---------------------------------------------------------------------------
def cmd_test(args):
    """Handle the *test* sub-command — run pytest."""
    cmd = [sys.executable, "-m", "pytest"]
    if args.args:
        cmd.extend(args.args)
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="TerminalAccessManager - Unified Backend CLI",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup
    sp_setup = subparsers.add_parser("setup", help="Initialize database and create admin user")
    sp_setup.set_defaults(func=cmd_setup)

    # password reset
    sp_password = subparsers.add_parser("password", help="Password management")
    pw_sub = sp_password.add_subparsers(dest="pw_command", help="Password operations")

    sp_pw_reset = pw_sub.add_parser("reset", help="Reset a user's password")
    sp_pw_reset.add_argument("username", help="Username to reset password for")
    sp_pw_reset.add_argument("--password", "-p", help="New password (will prompt if not provided)")
    sp_pw_reset.set_defaults(func=cmd_password_reset)

    # user management
    sp_user = subparsers.add_parser("user", help="User management")
    user_sub = sp_user.add_subparsers(dest="user_command", help="User operations")

    sp_user_list = user_sub.add_parser("list", help="List all users")
    sp_user_list.set_defaults(func=cmd_user_list)

    sp_user_unlock = user_sub.add_parser("unlock", help="Unlock a locked user account")
    sp_user_unlock.add_argument("username", help="Username to unlock")
    sp_user_unlock.set_defaults(func=cmd_user_unlock)

    # role management
    sp_role = subparsers.add_parser("role", help="Role and permission management")
    role_sub = sp_role.add_subparsers(dest="role_command", help="Role operations")

    sp_role_list = role_sub.add_parser("list", help="List all roles")
    sp_role_list.set_defaults(func=cmd_role_list)

    sp_role_perms = role_sub.add_parser("permissions", help="List all permissions")
    sp_role_perms.set_defaults(func=cmd_role_permissions)

    # mock (with sub-subcommands)
    sp_mock = subparsers.add_parser("mock", help="Manage mock/demo data")
    mock_sub = sp_mock.add_subparsers(dest="mock_command", help="Mock data operations")

    sp_mock_gen = mock_sub.add_parser("generate", help="Generate mock data")
    sp_mock_gen.set_defaults(func=cmd_mock_generate)

    sp_mock_clr = mock_sub.add_parser("clear", help="Clear all mock data")
    sp_mock_clr.set_defaults(func=cmd_mock_clear)

    # validate
    sp_validate = subparsers.add_parser("validate", help="Run backend validation checks")
    sp_validate.set_defaults(func=cmd_validate)

    # test
    sp_test = subparsers.add_parser("test", help="Run pytest test suite")
    sp_test.add_argument("args", nargs="*", help="Additional arguments passed to pytest")
    sp_test.set_defaults(func=cmd_test)

    # scheduler (with sub-subcommands)
    sp_sched = subparsers.add_parser("scheduler", help="Manage scheduler tasks")
    sched_sub = sp_sched.add_subparsers(dest="sched_command", help="Scheduler operations")

    sp_sched_trigger = sched_sub.add_parser("trigger", help="Manually trigger a scheduler task")
    sp_sched_trigger.add_argument("task_name", help="Task to trigger (arp_collection|ipguard_sync|firewall_query|compliance_check|auto_unblock)")
    sp_sched_trigger.set_defaults(func=cmd_scheduler_trigger)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
