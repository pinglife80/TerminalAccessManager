from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    add_token_to_blacklist,
    check_captcha_required,
    check_login_attempts,
    create_access_token_async,
    create_refresh_token_async,
    generate_captcha,
    get_client_ip,
    get_current_user,
    get_user_permissions,
    hash_password,
    invalidate_user_permissions,
    is_token_blacklisted,
    record_failed_login,
    require_permission,
    reset_login_attempts,
    verify_captcha,
    verify_password,
)
from app.models.role import Permission, Role, UserRole
from app.models.user import User
from app.schemas.auth import (
    AdminPasswordReset,
    AdminUserCreate,
    PasswordChange,
    ProfileUpdate,
    Token,
    UserCreate,
    UserDetailResponse,
    UserResponse,
    UserUpdate,
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
    captcha_id: str | None = None,
    captcha: str | None = None,
    provider: str = "local",
    db: AsyncSession = Depends(get_db)
):
    """Login and get access token"""
    username = form_data.username

    # Check if account is locked
    if await check_login_attempts(username):
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

    # Authenticate via AuthProviderFactory
    from app.services.auth_providers.provider_factory import AuthProviderFactory

    auth_result = await AuthProviderFactory.authenticate(
        provider_type=provider,
        credentials={"username": username, "password": form_data.password},
        db=db,
    )

    if not auth_result["success"]:
        await record_failed_login(username)
        captcha_now = await check_captcha_required(username)
        locked_now = await check_login_attempts(username)

        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(username, "login_failed", "auth", None,
                            {"message": "Login failed: invalid credentials", "provider": provider},
                            ip_address=get_client_ip(request),
                            resource_name=username)

        # Emit security.login_failed event for notification dispatch.
        # fire-and-forget: emit_event logs errors internally and never raises.
        from app.services.event_emitter import emit_login_failed
        await emit_login_failed(
            username=username,
            ip_address=get_client_ip(request),
            reason="invalid credentials",
        )

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

            from app.services.event_emitter import emit_login_locked
            await emit_login_locked(username, get_client_ip(request))

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail,
        )

    user = auth_result["user"]
    if not user:
        await record_failed_login(username)
        captcha_now = await check_captcha_required(username)
        locked_now = await check_login_attempts(username)

        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(username, "login_failed", "auth", None,
                            {"message": "Login failed: user not found", "provider": provider},
                            ip_address=get_client_ip(request),
                            resource_name=username)

        # Emit security.login_failed event for notification dispatch.
        from app.services.event_emitter import emit_login_failed
        await emit_login_failed(
            username=username,
            ip_address=get_client_ip(request),
            reason="user not found",
        )

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

            from app.services.event_emitter import emit_login_locked
            await emit_login_locked(username, get_client_ip(request))

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail,
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Your account has been locked. Please contact your administrator.",
                "locked": True,
            }
        )

    await reset_login_attempts(username)

    # Emit login success event for notification
    from app.services.event_emitter import emit_login_success
    await emit_login_success(user.username, get_client_ip(request))

    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(user.username, "login", "auth", str(user.id),
                        {"message": "User logged in successfully", "ip": get_client_ip(request), "provider": provider},
                        ip_address=get_client_ip(request),
                        resource_name=user.username)

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
        provider=current_user.provider,
        provider_user_id=current_user.provider_user_id,
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
            exp = datetime.fromtimestamp(payload.get("exp", 0), tz=UTC)
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
            exp_dt = datetime.fromtimestamp(exp, tz=UTC)
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
    if current_user.provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Profile management is not supported for {current_user.provider} users. Please contact your {current_user.provider} administrator.",
        )
    if profile.email is not None:
        if profile.email != current_user.email:
            if current_user.provider == "local" and not profile.force_email:
                result = await db.execute(select(User).where(User.email == profile.email, User.provider == "local"))
                if result.scalar_one_or_none():
                    raise HTTPException(status_code=400, detail="Email already in use by another local user")
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
        provider=current_user.provider,
        provider_user_id=current_user.provider_user_id,
    )


@router.put("/me/password", response_model=ResponseMessage)
async def change_password(
    data: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change current user's password (requires current password verification)"""
    if current_user.provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Password management is not supported for {current_user.provider} users. Please contact your {current_user.provider} administrator.",
        )
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

    # Emit password changed event for notification
    from app.services.event_emitter import emit_password_changed
    await emit_password_changed(current_user.username)

    # Audit log for password change
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "change_password", "auth", str(current_user.id),
                        {"message": "User changed their own password"},
                        ip_address=get_client_ip(request),
                        resource_name=current_user.username)

    return {"message": "Password changed successfully", "success": True}


# ==================== Admin User Management APIs ====================


@router.get("/users/email-available", response_model=dict)
async def check_email_available(
    email: str = Query(..., description="Email address to check"),
    exclude_user_id: int | None = Query(None, description="User ID to exclude (for update)"),
    db: AsyncSession = Depends(get_db),
):
    """Check if an email is available for use by a local user"""
    if not email:
        return {"available": True, "used_by": None}

    query = select(User).where(User.email == email, User.provider == "local")
    if exclude_user_id:
        query = query.where(User.id != exclude_user_id)

    result = await db.execute(query)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        return {
            "available": False,
            "used_by": {
                "id": existing_user.id,
                "username": existing_user.username,
            },
        }
    return {"available": True, "used_by": None}


@router.get("/users", response_model=list[UserDetailResponse])
async def list_users(
    search: str | None = None,
    is_active: bool | None = None,
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

    from app.core.security import get_redis_client
    try:
        redis_client = await get_redis_client()
        lock_info = {}
        for u in users:
            lock_key = f"login_lock:{u.username}"
            ttl = await redis_client.ttl(lock_key)
            lock_info[u.username] = {
                "is_locked": ttl > 0,
                "lock_remaining_seconds": ttl if ttl > 0 else None,
            }
    except Exception as e:
        from loguru import logger
        logger.warning(f"Redis unavailable, skipping lock status check: {e}")
        lock_info = {}

    response = []
    for u in users:
        role_names = [r.name for r in u.roles] if u.roles else []
        lock_data = lock_info.get(u.username, {"is_locked": False, "lock_remaining_seconds": None})
        response.append(UserDetailResponse(
            id=u.id, username=u.username, email=u.email,
            is_active=u.is_active, is_superuser=u.is_superuser,
            roles=role_names, permissions=[],
            provider=u.provider, provider_user_id=u.provider_user_id,
            created_at=u.created_at, updated_at=u.updated_at,
            is_locked=lock_data["is_locked"],
            lock_remaining_seconds=lock_data["lock_remaining_seconds"],
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

    # Check email uniqueness for local users (unless force_email is true)
    if user_data.email and not user_data.force_email:
        result = await db.execute(select(User).where(User.email == user_data.email, User.provider == "local"))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use by another local user")

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

    # Emit user created event for notification
    from app.services.event_emitter import emit_user_created
    await emit_user_created(new_user.username, current_user.username)

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
            if not user_data.force_email:
                email_check = await db.execute(select(User).where(User.email == user_data.email, User.provider == "local"))
                if email_check.scalar_one_or_none():
                    raise HTTPException(status_code=400, detail="Email already in use by another local user")
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

        # Emit role changed event for notification
        from app.services.event_emitter import emit_role_changed
        await emit_role_changed(user.username, current_user.username, old_role, new_role)

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

    # Emit user updated event for notification
    from app.services.event_emitter import emit_user_updated
    changes = list(user_data.model_dump(exclude_unset=True).keys())
    await emit_user_updated(user.username, current_user.username, changes)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
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

    # Emit user deleted event for notification
    from app.services.event_emitter import emit_user_deleted
    await emit_user_deleted(deleted_username, current_user.username)

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

    if user.provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Password reset is not supported for {user.provider} users. Please contact your {user.provider} administrator.",
        )

    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    # Invalidate all existing tokens for this user
    from app.core.security import increment_token_version
    await increment_token_version(user.id)

    # Emit password changed event for notification
    from app.services.event_emitter import emit_password_changed
    await emit_password_changed(user.username)

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


@router.post("/users/{user_id}/lock", response_model=ResponseMessage)
async def admin_lock_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_permission("user:lock")),
    db: AsyncSession = Depends(get_db),
):
    """Lock a user account (requires user:lock permission)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="User is already locked")

    user.is_active = False
    await db.commit()

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "lock_user", "user", str(user.id),
                        {"message": "Locked user account", "username": user.username},
                        ip_address=get_client_ip(request),
                        resource_name=user.username)

    return {"message": f"Account '{user.username}' locked successfully", "success": True}


# ==================== Password Reset with Verification Code ====================

class PasswordResetRequest(BaseModel):
    """Request body for password reset initiation"""
    username: str | None = None
    email: str | None = None


class PasswordResetVerify(BaseModel):
    """Request body for password reset verification and completion"""
    email: str | None = None
    username: str | None = None
    code: str
    new_password: str


@router.post("/password-reset/request", response_model=ResponseMessage)
async def request_password_reset(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request password reset - sends verification code to user's email"""
    user = None
    if data.username:
        result = await db.execute(select(User).where(User.username == data.username))
        user = result.scalar_one_or_none()
    elif data.email:
        result = await db.execute(select(User).where(User.email == data.email))
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please check your username.",
        )

    if user.provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Password reset is not supported for {user.provider} users. Please contact your {user.provider} administrator.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact your administrator.",
        )

    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your account does not have an email address configured. Please contact your administrator.",
        )

    from app.services.email_service import send_password_reset_email
    await send_password_reset_email(email=user.email, user_id=user.id)

    from app.services.event_emitter import emit_password_reset_requested
    await emit_password_reset_requested(user.username, user.email)

    return {
        "message": "Verification code sent successfully. Please check your email.",
        "success": True,
        "email": user.email,
    }


@router.post("/password-reset/verify", response_model=ResponseMessage)
async def verify_and_reset_password(
    data: PasswordResetVerify,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Verify verification code and reset password"""
    user = None
    if data.username:
        result = await db.execute(select(User).where(User.username == data.username))
        user = result.scalar_one_or_none()
    elif data.email:
        result = await db.execute(select(User).where(User.email == data.email))
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.provider != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Password reset is not supported for {user.provider} users.",
        )

    from app.services.email_service import verify_email_code
    is_valid = await verify_email_code(user_id=user.id, code=data.code, purpose="password_reset")

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code.",
        )

    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    from app.core.security import increment_token_version
    await increment_token_version(user.id)

    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(user.username, "password_reset", "auth", str(user.id),
                        {"message": "User reset password via verification code",
                         "ip": get_client_ip(request)},
                        ip_address=get_client_ip(request),
                        resource_name=user.username)

    return {
        "message": "Password reset successfully. Please log in with your new password.",
        "success": True,
    }
