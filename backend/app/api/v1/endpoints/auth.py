from datetime import timedelta, datetime, timezone
from fastapi import APIRouter, Body, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from typing import Optional

from app.core.database import get_db
from app.core.security import (
    authenticate_user,
    verify_password,
    create_access_token_async,
    create_refresh_token_async,
    hash_password,
    get_current_user,
    add_token_to_blacklist,
    is_token_blacklisted,
    check_login_attempts,
    check_captcha_required,
    record_failed_login,
    reset_login_attempts,
    generate_captcha,
    verify_captcha,
    require_permission,
    invalidate_user_permissions,
    get_user_permissions,
    get_client_ip,
)
from app.core.config import settings
from app.models.user import User
from app.models.role import Role, UserRole, RolePermission, Permission
from app.schemas.auth import (
    Token, UserCreate, UserResponse, UserDetailResponse,
    UserUpdate, AdminUserCreate, PasswordChange, AdminPasswordReset, ProfileUpdate,
)
from app.schemas.terminal import ResponseMessage

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


async def _get_superadmin_role_id(db: AsyncSession) -> int:
    """Get the superadmin role ID dynamically from the database.
    Falls back to 1 if the superadmin role is not found."""
    result = await db.execute(select(Role.id).where(Role.name == "superadmin"))
    role_id = result.scalar_one_or_none()
    return role_id or 1


async def _build_user_detail_response(db: AsyncSession, user: User) -> UserDetailResponse:
    """Build UserDetailResponse from User ORM object, querying roles from DB
    to avoid DetachedInstanceError when accessing the roles relationship."""
    role_result = await db.execute(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
    )
    role_names = list(role_result.scalars().all())
    return UserDetailResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        roles=role_names,
        permissions=[],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    captcha_id: Optional[str] = None,
    captcha: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Login and get access token"""
    username = form_data.username

    # Check if account is locked
    if await check_login_attempts(username):
        # Get remaining lock time
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        lock_key = f"login_lock:{username}"
        ttl = await redis_client.ttl(lock_key)
        remaining_minutes = max(0, (ttl + 59) // 60) if ttl > 0 else settings.LOCKOUT_DURATION_MINUTES

        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "message": f"Account locked due to too many failed attempts. Try again in {remaining_minutes} minutes.",
                "locked": True,
                "lock_remaining": remaining_minutes * 60,
            },
        )

    # Check if captcha is required
    captcha_required = await check_captcha_required(username)

    # If captcha is required, validate captcha_id + captcha answer via server-side verification
    if captcha_required:
        if not captcha_id or not captcha:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Captcha verification is required. Please solve the captcha and try again.",
                    "captcha_required": True,
                },
            )
        if not await verify_captcha(captcha_id, captcha):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Captcha verification failed. Please try again.",
                    "captcha_required": True,
                },
            )

    # Step 1: Check if user exists
    from sqlalchemy import select
    from app.models.user import User as UserModel
    result = await db.execute(select(UserModel).where(UserModel.username == username))
    user = result.scalar_one_or_none()

    if not user:
        # User does not exist - record failed attempt for anti-enumeration
        await record_failed_login(username)
        captcha_now = await check_captcha_required(username)
        # Audit log for failed login
        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(username, "login_failed", "auth", None,
                            {"message": "Login failed: user not found"},
                            ip_address=get_client_ip(request),
                            resource_name=username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Invalid credentials",
                "captcha_required": captcha_now,
            },
        )

    # Step 2: Verify password
    if not verify_password(form_data.password, user.hashed_password):
        # Password incorrect - record failed attempt
        await record_failed_login(username)
        captcha_now = await check_captcha_required(username)
        locked_now = await check_login_attempts(username)

        # Audit log for failed login (wrong password)
        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(username, "login_failed", "auth", str(user.id),
                            {"message": "Login failed: incorrect password"},
                            ip_address=get_client_ip(request),
                            resource_name=user.username)

        error_detail = {
            "message": "Invalid credentials",
            "captcha_required": captcha_now,
        }
        if locked_now:
            from app.core.security import get_redis_client
            redis_client = await get_redis_client()
            lock_key = f"login_lock:{username}"
            ttl = await redis_client.ttl(lock_key)
            remaining_minutes = max(0, (ttl + 59) // 60) if ttl > 0 else settings.LOCKOUT_DURATION_MINUTES
            error_detail["locked"] = True
            error_detail["lock_remaining"] = remaining_minutes * 60

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail,
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )

    # Reset failed login attempts on successful login
    await reset_login_attempts(username)

    # Audit log for login
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(user.username, "login", "auth", str(user.id),
                        {"message": "User logged in successfully", "ip": get_client_ip(request)},
                        ip_address=get_client_ip(request),
                        resource_name=user.username)

    # Create tokens (uses hot-reloadable config for expiration)
    access_token = await create_access_token_async(data={"sub": user.username}, user_id=user.id)
    refresh_token = await create_refresh_token_async(data={"sub": user.username}, user_id=user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.get("/captcha")
async def get_captcha():
    """Generate a server-side arithmetic captcha.

    Returns captcha_id and question. The answer is stored in Redis
    with a 5-minute TTL and verified on login.
    """
    captcha_id, question = await generate_captcha()
    return {"captcha_id": captcha_id, "question": question}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user (disabled by default in production)"""
    # Check if registration is allowed
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled. Contact an administrator to create an account."
        )

    # Check if username already exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    # Check if email already exists (if provided)
    if user_data.email:
        result = await db.execute(select(User).where(User.email == user_data.email))
        existing_email = result.scalar_one_or_none()

        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    # Create new user
    hashed_pw = hash_password(user_data.password)

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pw,
        is_active=True,
        is_superuser=False
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Assign default role (operator) to newly registered user
    default_role = await db.execute(select(Role).where(Role.is_default == True))
    role = default_role.scalar_one_or_none()
    role_names = []
    if role:
        db.add(UserRole(user_id=new_user.id, role_id=role.id))
        await db.commit()
        role_names = [role.name]

    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        is_active=new_user.is_active,
        is_superuser=new_user.is_superuser,
        roles=role_names,
        permissions=[],
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user information with roles and permissions"""
    import asyncio

    # Parallel: fetch roles and permissions concurrently
    async def _get_roles():
        role_result = await db.execute(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == current_user.id)
        )
        return list(role_result.scalars().all())

    async def _get_permissions():
        if current_user.is_superuser:
            perm_result = await db.execute(select(Permission.code))
            return list(perm_result.scalars().all())
        else:
            return list(await get_user_permissions(db, current_user.id))

    role_names, perm_codes = await asyncio.gather(_get_roles(), _get_permissions())

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        roles=role_names,
        permissions=perm_codes,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    refresh_token: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        token_type: str = payload.get("type")

        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Verify this is actually a refresh token (not an access token)
        # Legacy tokens without 'type' field are accepted for backward compatibility
        if token_type is not None and token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type: expected refresh token"
            )

        # Check if refresh token is blacklisted
        if jti and await is_token_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked"
            )

        # Verify user exists
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user"
            )

        # Verify token version in refresh token
        token_ver = payload.get("ver")
        if token_ver is not None:
            from app.core.security import get_token_version
            current_ver = await get_token_version(user.id)
            if int(token_ver) != current_ver:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been invalidated"
                )

        # Create new tokens (uses hot-reloadable config for expiration)
        access_token = await create_access_token_async(data={"sub": username}, user_id=user.id)
        new_refresh_token = await create_refresh_token_async(data={"sub": username}, user_id=user.id)

        # Blacklist old refresh token
        if jti:
            exp = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)
            await add_token_to_blacklist(jti, exp)

        # Audit log for token refresh
        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(username, "token_refresh", "auth", str(user.id),
                            {"message": "Token refreshed"},
                            ip_address=get_client_ip(request),
                            resource_name=user.username)

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.post("/logout", response_model=ResponseMessage)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Logout and blacklist the current token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        jti = payload.get("jti")
        exp = payload.get("exp")

        if jti and exp:
            exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            await add_token_to_blacklist(jti, exp_dt)
    except Exception:
        pass  # Even if token parsing fails, return success

    # Audit log for logout
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "logout", "auth", str(current_user.id),
                        {"message": "User logged out"},
                        ip_address=get_client_ip(request),
                        resource_name=current_user.username)

    return {"message": "Successfully logged out", "success": True}


# ==================== User Profile APIs ====================

@router.put("/me/profile", response_model=UserResponse)
async def update_profile(
    profile: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile (email)"""
    if profile.email is not None:
        # Check email uniqueness
        if profile.email != current_user.email:
            result = await db.execute(select(User).where(User.email == profile.email))
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = profile.email
        await db.commit()
        await db.refresh(current_user)

    # Query roles to avoid DetachedInstanceError
    role_result = await db.execute(
        select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == current_user.id)
    )
    role_names = list(role_result.scalars().all())

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        roles=role_names,
        permissions=[],
    )


@router.put("/me/password", response_model=ResponseMessage)
async def change_password(
    data: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change current user's password (requires current password verification)"""
    from app.core.security import verify_password
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(data.new_password)
    await db.commit()

    # Invalidate all existing tokens for this user
    from app.core.security import increment_token_version
    await increment_token_version(current_user.id)

    # Audit log for password change
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "change_password", "auth", str(current_user.id),
                        {"message": "User changed their own password"},
                        ip_address=get_client_ip(request),
                        resource_name=current_user.username)

    return {"message": "Password changed successfully", "success": True}


# ==================== Admin User Management APIs ====================


@router.get("/users", response_model=list[UserDetailResponse])
async def list_users(
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(require_permission("user:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all users with optional search and filter (requires user:read permission).
    Non-superadmin users cannot see the superadmin user."""
    from sqlalchemy.orm import selectinload
    stmt = select(User).options(selectinload(User.roles)).order_by(User.id)
    # Non-superadmin users cannot see the superadmin user
    if not current_user.is_superuser:
        stmt = stmt.where(User.is_superuser == False)
    if search:
        escaped_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        stmt = stmt.where(
            (User.username.ilike(f"%{escaped_search}%")) | (User.email.ilike(f"%{escaped_search}%"))
        )
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    result = await db.execute(stmt)
    users = result.scalars().all()
    # Build response with role names
    response = []
    for u in users:
        role_names = [r.name for r in u.roles] if u.roles else []
        response.append(UserDetailResponse(
            id=u.id, username=u.username, email=u.email,
            is_active=u.is_active, is_superuser=u.is_superuser,
            roles=role_names, permissions=[],
            created_at=u.created_at, updated_at=u.updated_at,
        ))
    return response


@router.post("/users", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    user_data: AdminUserCreate,
    request: Request,
    current_user: User = Depends(require_permission("user:write")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (requires user:write permission)"""
    # Check username uniqueness
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    # Check email uniqueness
    if user_data.email:
        result = await db.execute(select(User).where(User.email == user_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        is_active=user_data.is_active,
        is_superuser=user_data.is_superuser,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Assign role if provided
    if user_data.role_id:
        # Prevent assigning superadmin role - it's only for the initial system admin
        superadmin_role_id = await _get_superadmin_role_id(db)
        if user_data.role_id == superadmin_role_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot assign superadmin role. Superadmin is reserved for the initial system administrator."
            )
        db.add(UserRole(user_id=new_user.id, role_id=user_data.role_id))
    elif not user_data.is_superuser:
        # Assign default role (operator) if no role specified and not superuser
        default_role = await db.execute(select(Role).where(Role.is_default == True))
        role = default_role.scalar_one_or_none()
        if role:
            db.add(UserRole(user_id=new_user.id, role_id=role.id))

    # is_superuser is only set internally, not through user creation API
    # New users should never be superuser
    new_user.is_superuser = False

    await db.commit()

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "create_user", "user", str(new_user.id),
                        {"message": "Created user", "username": new_user.username,
                         "email": new_user.email, "is_active": new_user.is_active,
                         "role": "superuser" if new_user.is_superuser else "user"},
                        ip_address=get_client_ip(request),
                        resource_name=new_user.username)

    return await _build_user_detail_response(db, new_user)


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(require_permission("user:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get user details by ID (requires user:read permission).
    Non-superadmin users cannot view the superadmin user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Non-superadmin users cannot see the superadmin user
    if user.is_superuser and not current_user.is_superuser:
        raise HTTPException(status_code=404, detail="User not found")
    return await _build_user_detail_response(db, user)


@router.put("/users/{user_id}", response_model=UserDetailResponse)
async def admin_update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    current_user: User = Depends(require_permission("user:write")),
    db: AsyncSession = Depends(get_db),
):
    """Update user info (requires user:write permission).
    Non-superadmin users cannot modify superadmin users."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Non-superadmin users cannot modify superadmin users
    if user.is_superuser and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Cannot modify superadmin user")

    # Protect the initial system admin (id=1) from demotion or deactivation
    if user.id == 1:
        if user_data.is_superuser is False:
            raise HTTPException(status_code=400, detail="Cannot demote the initial system administrator")
        if user_data.is_active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate the initial system administrator")

    # Prevent self-demotion
    if user.id == current_user.id and user_data.is_superuser is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own superuser status")

    if user_data.email is not None:
        if user_data.email != user.email:
            email_check = await db.execute(select(User).where(User.email == user_data.email))
            if email_check.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Email already in use")
        user.email = user_data.email

    if user_data.is_active is not None:
        # Prevent self-deactivation
        if user.id == current_user.id and not user_data.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
        user.is_active = user_data.is_active

    if user_data.is_superuser is not None and user_data.is_superuser != user.is_superuser:
        old_role = "superuser" if user.is_superuser else "user"
        new_role = "superuser" if user_data.is_superuser else "user"
        user.is_superuser = user_data.is_superuser

        # Sync superadmin role
        superadmin_role_id = await _get_superadmin_role_id(db)
        if user_data.is_superuser:
            existing_sa = await db.execute(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == superadmin_role_id)
            )
            if not existing_sa.scalar_one_or_none():
                db.add(UserRole(user_id=user.id, role_id=superadmin_role_id))
        else:
            await db.execute(
                UserRole.__table__.delete().where(
                    UserRole.user_id == user.id, UserRole.role_id == superadmin_role_id
                )
            )

        # Invalidate permission cache
        await invalidate_user_permissions(user.id)

        # Dedicated audit log for role change
        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(current_user.username, "change_role", "user", str(user.id),
                            {"message": f"User role changed from {old_role} to {new_role}",
                             "target_user": user.username, "old_role": old_role, "new_role": new_role},
                            ip_address=get_client_ip(request),
                            resource_name=user.username)

    await db.commit()
    await db.refresh(user)

    # Handle role assignment
    if user_data.role_id is not None:
        # Superadmin users cannot have their role changed
        if user.is_superuser:
            raise HTTPException(status_code=400, detail="Cannot modify role of a superadmin user")
        # Prevent assigning superadmin role - it's only for the initial system admin
        superadmin_role_id = await _get_superadmin_role_id(db)
        if user_data.role_id == superadmin_role_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot assign superadmin role. Superadmin is reserved for the initial system administrator."
            )
        await db.execute(UserRole.__table__.delete().where(UserRole.user_id == user.id))
        db.add(UserRole(user_id=user.id, role_id=user_data.role_id))
        # Sync is_superuser - only true if user has superadmin role
        user.is_superuser = (user_data.role_id == superadmin_role_id)
        await db.commit()
        await db.refresh(user)
        await invalidate_user_permissions(user.id)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    changes = list(user_data.model_dump(exclude_unset=True).keys())
    await ts.log_action(current_user.username, "update_user", "user", str(user.id),
                        {"message": "Updated user", "username": user.username,
                         "changes": changes},
                        ip_address=get_client_ip(request),
                        resource_name=user.username)

    return await _build_user_detail_response(db, user)


@router.delete("/users/{user_id}", response_model=ResponseMessage)
async def admin_delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_permission("user:delete")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user (requires user:delete permission). Cannot delete self or initial admin.
    Non-superadmin users cannot delete superadmin users."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Non-superadmin users cannot delete superadmin users
    if user.is_superuser and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Cannot delete superadmin user")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Protect the initial system admin (id=1) from deletion
    if user.id == 1:
        raise HTTPException(status_code=400, detail="Cannot delete the initial system administrator")

    deleted_username = user.username
    await db.delete(user)
    await db.commit()

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "delete_user", "user", str(user_id),
                        {"message": "Deleted user", "username": deleted_username},
                        ip_address=get_client_ip(request),
                        resource_name=deleted_username)

    return {"message": f"User '{deleted_username}' deleted successfully", "success": True}


@router.put("/users/{user_id}/password", response_model=ResponseMessage)
async def admin_reset_password(
    user_id: int,
    data: AdminPasswordReset,
    request: Request,
    current_user: User = Depends(require_permission("user:password")),
    db: AsyncSession = Depends(get_db),
):
    """Reset a user's password (requires user:password permission)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    # Invalidate all existing tokens for this user
    from app.core.security import increment_token_version
    await increment_token_version(user.id)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "reset_password", "user", str(user.id),
                        {"message": "Reset password for user", "username": user.username},
                        ip_address=get_client_ip(request),
                        resource_name=user.username)

    return {"message": f"Password for '{user.username}' reset successfully", "success": True}


@router.post("/users/{user_id}/unlock", response_model=ResponseMessage)
async def admin_unlock_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_permission("user:unlock")),
    db: AsyncSession = Depends(get_db),
):
    """Unlock a locked user account (requires user:unlock permission)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Clear Redis lock and attempts
    await reset_login_attempts(user.username)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "unlock_user", "user", str(user.id),
                        {"message": "Unlocked user account", "username": user.username},
                        ip_address=get_client_ip(request),
                        resource_name=user.username)

    return {"message": f"Account '{user.username}' unlocked successfully", "success": True}
