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
)
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import (
    Token, UserCreate, UserResponse, UserDetailResponse,
    UserUpdate, AdminUserCreate, PasswordChange, AdminPasswordReset, ProfileUpdate,
)
from app.schemas.terminal import ResponseMessage

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    captcha: str = None,
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
            detail=f"Account locked due to too many failed attempts. Try again in {remaining_minutes} minutes.",
            headers={"X-Account-Locked": "true", "X-Lock-Remaining": str(remaining_minutes * 60)},
        )

    # Check if captcha is required
    captcha_required = await check_captcha_required(username)

    # If captcha is required but not provided, reject
    if captcha_required and not captcha:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Captcha verification is required. Please solve the captcha and try again.",
            headers={"X-Captcha-Required": "true"},
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
        headers = {"X-Captcha-Required": "true" if captcha_now else "false"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers=headers,
        )

    # Step 2: Verify password
    if not verify_password(form_data.password, user.hashed_password):
        # Password incorrect - record failed attempt
        await record_failed_login(username)
        captcha_now = await check_captcha_required(username)
        locked_now = await check_login_attempts(username)

        headers = {
            "X-Captcha-Required": "true" if captcha_now else "false",
        }
        if locked_now:
            from app.core.security import get_redis_client
            redis_client = await get_redis_client()
            lock_key = f"login_lock:{username}"
            ttl = await redis_client.ttl(lock_key)
            remaining_minutes = max(0, (ttl + 59) // 60) if ttl > 0 else settings.LOCKOUT_DURATION_MINUTES
            headers["X-Account-Locked"] = "true"
            headers["X-Lock-Remaining"] = str(remaining_minutes * 60)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers=headers,
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
                        {"message": "User logged in successfully"},
                        ip_address=request.client.host if request.client else None)

    # Create tokens (uses hot-reloadable config for expiration)
    access_token = await create_access_token_async(data={"sub": user.username})
    refresh_token = await create_refresh_token_async(data={"sub": user.username})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.get("/login-status")
async def get_login_status(username: str):
    """Get login status for a username (captcha required, account locked)"""
    captcha_required = await check_captcha_required(username)
    locked = await check_login_attempts(username)

    result = {
        "captcha_required": captcha_required,
        "locked": locked,
    }

    if locked:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        lock_key = f"login_lock:{username}"
        ttl = await redis_client.ttl(lock_key)
        remaining_seconds = max(0, ttl) if ttl > 0 else settings.LOCKOUT_DURATION_MINUTES * 60
        result["lock_remaining_seconds"] = remaining_seconds

    return result


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

    return new_user


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    return current_user


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")

        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
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

        # Create new tokens (uses hot-reloadable config for expiration)
        access_token = await create_access_token_async(data={"sub": username})
        new_refresh_token = await create_refresh_token_async(data={"sub": username})

        # Blacklist old refresh token
        if jti:
            exp = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)
            await add_token_to_blacklist(jti, exp)

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
                        ip_address=request.client.host if request.client else None)

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
    return current_user


@router.put("/me/password", response_model=ResponseMessage)
async def change_password(
    data: PasswordChange,
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
    return {"message": "Password changed successfully", "success": True}


# ==================== Admin User Management APIs ====================

async def get_current_active_superuser(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: ensure current user is a superuser"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


@router.get("/users", response_model=list[UserDetailResponse])
async def list_users(
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
):
    """List all users with optional search and filter (superuser only)"""
    stmt = select(User).order_by(User.id)
    if search:
        stmt = stmt.where(
            (User.username.ilike(f"%{search}%")) | (User.email.ilike(f"%{search}%"))
        )
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/users", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    user_data: AdminUserCreate,
    request: Request,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (superuser only)"""
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

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "create_user", "user", str(new_user.id),
                        {"message": "Created user", "username": new_user.username,
                         "role": "superuser" if new_user.is_superuser else "user"},
                        ip_address=request.client.host if request.client else None)

    return new_user


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Get user details by ID (superuser only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/{user_id}", response_model=UserDetailResponse)
async def admin_update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Update user info (superuser only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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

    if user_data.is_superuser is not None:
        user.is_superuser = user_data.is_superuser

    await db.commit()
    await db.refresh(user)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "update_user", "user", str(user.id),
                        {"message": "Updated user", "username": user.username},
                        ip_address=request.client.host if request.client else None)

    return user


@router.delete("/users/{user_id}", response_model=ResponseMessage)
async def admin_delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user (superuser only). Cannot delete self."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    deleted_username = user.username
    await db.delete(user)
    await db.commit()

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "delete_user", "user", str(user_id),
                        {"message": "Deleted user", "username": deleted_username},
                        ip_address=request.client.host if request.client else None)

    return {"message": f"User '{deleted_username}' deleted successfully", "success": True}


@router.put("/users/{user_id}/password", response_model=ResponseMessage)
async def admin_reset_password(
    user_id: int,
    data: AdminPasswordReset,
    request: Request,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Reset a user's password (superuser only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    await db.commit()

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "reset_password", "user", str(user.id),
                        {"message": "Reset password for user", "username": user.username},
                        ip_address=request.client.host if request.client else None)

    return {"message": f"Password for '{user.username}' reset successfully", "success": True}


@router.post("/users/{user_id}/unlock", response_model=ResponseMessage)
async def admin_unlock_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_active_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Unlock a locked user account (superuser only)"""
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
                        ip_address=request.client.host if request.client else None)

    return {"message": f"Account '{user.username}' unlocked successfully", "success": True}
