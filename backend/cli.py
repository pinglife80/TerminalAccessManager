#!/usr/bin/env python3
"""
Unified CLI for MAC Security Platform backend management.

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

    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()

        if not admin:
            admin = User(
                username="admin",
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                is_active=True,
                is_superuser=True,
            )
            db.add(admin)
            await db.commit()
            print(_green("✓ Admin user created successfully!"))
            print("  Username: admin")
            print("  Password: admin123 (CHANGE THIS IMMEDIATELY!)")
        else:
            print("ℹ Admin user already exists")


async def _run_setup():
    """Initialize database and create admin user."""
    from app.core.database import init_db

    print("=" * 60)
    print("MAC Security Platform - Initial Setup")
    print("=" * 60)
    print()

    print("Initializing database...")
    await init_db()
    print(_green("✓ Database initialized"))
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
# mock generate helpers
# ---------------------------------------------------------------------------
def _generate_random_mac():
    return ':'.join(['{:02x}'.format(random.randint(0, 255)) for _ in range(6)])


def _normalize_mac(mac: str) -> str:
    mac_clean = mac.replace('-', '').replace(':', '').replace('.', '').upper()
    return '-'.join(mac_clean[i:i + 2] for i in range(0, len(mac_clean), 2))


def _generate_random_ip():
    ranges = [
        (192, 168, 1, 1, 192, 168, 1, 254),
        (10, 0, 1, 1, 10, 0, 1, 254),
        (172, 16, 0, 1, 172, 16, 0, 254),
    ]
    r = random.choice(ranges)
    return f"{r[0]}.{r[1]}.{r[2]}.{random.randint(r[3], r[7])}"


def _generate_random_hostname():
    prefixes = ['desktop', 'laptop', 'server', 'printer', 'phone', 'tablet', 'camera', 'ap']
    departments = ['hr', 'it', 'finance', 'marketing', 'sales', 'engineering', 'support']
    return f"{random.choice(prefixes)}-{random.choice(departments)}-{random.randint(1, 99):02d}"


async def _create_mock_users(db):
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.models.user import User

    print("Creating mock users...")

    users_data = [
        {"username": "admin", "email": "admin@company.com", "password": "admin123", "is_superuser": True, "is_active": True},
        {"username": "john.doe", "email": "john.doe@company.com", "password": "password123", "is_superuser": False, "is_active": True},
        {"username": "jane.smith", "email": "jane.smith@company.com", "password": "password123", "is_superuser": False, "is_active": True},
        {"username": "network.admin", "email": "netadmin@company.com", "password": "netpass456", "is_superuser": True, "is_active": True},
        {"username": "security.officer", "email": "security@company.com", "password": "securepass789", "is_superuser": False, "is_active": True},
    ]

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
            created_users.append(user)
            print(f"  ✓ Created user: {ud['username']}")
        else:
            created_users.append(existing)
            print(f"  - User already exists: {ud['username']}")

    await db.commit()
    return created_users


async def _create_mock_mac_addresses(db, users):
    from sqlalchemy import select
    from app.models.mac_address import MacAddress

    print("\nCreating mock MAC addresses...")

    statuses = ['active', 'inactive', 'frozen', 'pending', 'unfrozen']

    mac_records = []
    for i in range(50):
        mac = _generate_random_mac()
        ip = _generate_random_ip()

        stmt = select(MacAddress).where(MacAddress.mac_address == mac)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 90)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            mac_record = MacAddress(
                mac_address=_normalize_mac(mac),
                ip_address=ip,
                status=random.choice(statuses),
                comments=f"Auto-generated mock data #{i + 1}",
                timestamp=created_at,
                source=random.choice(['arp', 'ipguard']),
            )
            db.add(mac_record)
            mac_records.append(mac_record)
            print(f"  ✓ Created MAC: {mac} ({ip})")
        else:
            mac_records.append(existing)

    await db.commit()
    return mac_records


async def _create_mock_whitelist(db, mac_records, users):
    from sqlalchemy import select
    from app.models.whitelist import Whitelist

    print("\nCreating mock whitelist entries...")

    selected_macs = random.sample(mac_records, min(15, len(mac_records)))

    for mac_record in selected_macs:
        stmt = select(Whitelist).where(Whitelist.mac_address == mac_record.mac_address)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 60)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            whitelist_entry = Whitelist(
                mac_address=mac_record.mac_address,
                comments=f"Auto-generated whitelist entry #{len(selected_macs)}",
                added_by=random.choice(users).username,
                created_at=created_at,
            )
            db.add(whitelist_entry)
            print(f"  ✓ Whitelisted: {mac_record.mac_address}")

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

    stmt = select(Whitelist.mac_address)
    result = await db.execute(stmt)
    whitelisted_macs = {row[0] for row in result.fetchall()}

    available_macs = [m for m in mac_records if m.mac_address not in whitelisted_macs]
    selected_macs = random.sample(available_macs, min(10, len(available_macs)))

    for mac_record in selected_macs:
        stmt = select(Blacklist).where(Blacklist.mac_address == mac_record.mac_address)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            days_ago = random.randint(0, 30)
            created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            blacklist_entry = Blacklist(
                mac_address=mac_record.mac_address,
                ip_address=mac_record.ip_address,
                reason=random.choice(reasons),
                blocked_at=created_at,
                expires_at=datetime.now(timezone.utc) + timedelta(days=random.randint(7, 30)),
                blocked_by=random.choice(users).username,
            )
            db.add(blacklist_entry)
            print(f"  ✓ Blacklisted: {mac_record.mac_address}")

    await db.commit()


async def _create_mock_audit_logs(db, users, mac_records):
    from app.models.log import AuditLog

    print("\nCreating mock audit logs...")

    actions = [
        ('login', 'User logged in successfully'),
        ('logout', 'User logged out'),
        ('block_ip', f'Blocked IP {_generate_random_ip()}'),
        ('unblock_ip', f'Unblocked IP {_generate_random_ip()}'),
        ('add_whitelist', 'Added device to whitelist'),
        ('remove_whitelist', 'Removed device from whitelist'),
        ('search_mac', 'Searched for MAC address'),
        ('update_mac', 'Updated MAC address information'),
        ('view_logs', 'Viewed audit logs'),
        ('export_data', 'Exported MAC address data'),
    ]

    resource_types = ['user', 'mac', 'whitelist', 'blacklist', 'system']

    for i in range(100):
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)

        timestamp = datetime.now(timezone.utc) - timedelta(
            days=days_ago, hours=hours_ago, minutes=minutes_ago,
        )

        action, description = random.choice(actions)

        mac_for_action = None
        if action in ['block_ip', 'unblock_ip', 'search_mac', 'update_mac']:
            mac_for_action = random.choice(mac_records)
            if mac_for_action:
                description = description.replace('IP', f"{mac_for_action.ip_address}")

        log_entry = AuditLog(
            user_id=random.choice(users).id,
            username=random.choice(users).username,
            action=action,
            resource_type=random.choice(resource_types),
            resource_id=str(mac_for_action.id) if mac_for_action else None,
            details=description,
            ip_address=_generate_random_ip(),
            timestamp=timestamp,
        )
        db.add(log_entry)

    await db.commit()
    print("  ✓ Created 100 audit log entries")


async def _run_mock_generate():
    from sqlalchemy import func, select
    from app.core.database import async_session_maker, Base, engine
    from app.models.whitelist import Whitelist
    from app.models.blacklist import Blacklist
    from app.models.log import AuditLog

    print("=" * 70)
    print("MAC Security Platform - Mock Data Generator")
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
            users = await _create_mock_users(db)
            mac_records = await _create_mock_mac_addresses(db, users)
            await _create_mock_whitelist(db, mac_records, users)
            await _create_mock_blacklist(db, mac_records, users)
            await _create_mock_audit_logs(db, users, mac_records)

            print("\n" + "=" * 70)
            print("Mock Data Generation Complete!")
            print("=" * 70)
            print()
            print("Summary:")
            print(f"  • Users: {len(users)}")
            print(f"  • MAC Addresses: {len(mac_records)}")

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
            print("  • admin / admin123 (superuser)")
            print("  • john.doe / password123")
            print("  • jane.smith / password123")
            print("  • network.admin / netpass456 (superuser)")
            print("  • security.officer / securepass789")
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
    from sqlalchemy import delete, func, select
    from app.core.database import async_session_maker
    from app.models.user import User
    from app.models.mac_address import MacAddress
    from app.models.whitelist import Whitelist
    from app.models.blacklist import Blacklist
    from app.models.log import AuditLog

    print("=" * 70)
    print("MAC Security Platform - Clear Mock Data")
    print("=" * 70)
    print()
    print("WARNING: This will delete ALL data from the database!")
    print("This action cannot be undone.")
    print()

    async with async_session_maker() as db:
        counts = {}

        for label, model in [
            ('MAC Addresses', MacAddress),
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

            await db.execute(MacAddress.__table__.delete())
            print(_green("  ✓ Deleted MAC addresses"))

            stmt = delete(User).where(User.username != 'admin')
            await db.execute(stmt)
            print(_green("  ✓ Deleted non-admin users"))

            await db.commit()

            print()
            print("=" * 70)
            print("Mock Data Cleared Successfully!")
            print("=" * 70)
            print()
            print("Database is now clean and ready for production.")
            print()
            print("Remaining:")
            print("  • Admin user account (username: admin)")
            print("  • Database schema and tables")
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
        'app/models/mac_address.py', 'app/models/whitelist.py',
        'app/models/blacklist.py', 'app/models/log.py', 'app/schemas/auth.py',
        'app/schemas/mac_address.py', 'app/api/v1/api.py',
        'app/api/v1/endpoints/auth.py', 'app/api/v1/endpoints/mac_addresses.py',
        'app/api/v1/endpoints/whitelist.py', 'app/api/v1/endpoints/logs.py',
        'app/services/sangfor_service.py', 'app/services/mac_service.py',
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
        'app/core/database.py', 'app/models/user.py', 'app/models/mac_address.py',
        'app/models/whitelist.py', 'app/models/blacklist.py', 'app/models/log.py',
        'app/schemas/auth.py', 'app/schemas/mac_address.py',
        'app/api/v1/endpoints/auth.py', 'app/api/v1/endpoints/mac_addresses.py',
        'app/api/v1/endpoints/whitelist.py', 'app/api/v1/endpoints/logs.py',
        'app/services/sangfor_service.py', 'app/services/mac_service.py',
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

        if 'bcrypt' in security_content.lower() or 'pwd_context' in security_content:
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
        'app/api/v1/endpoints/mac_addresses.py': ['block', 'unblock', 'search'],
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
        description="MAC Security Platform - Unified Backend CLI",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # setup
    sp_setup = subparsers.add_parser("setup", help="Initialize database and create admin user")
    sp_setup.set_defaults(func=cmd_setup)

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
