from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis
import uuid
import json
import random
from loguru import logger

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import TokenData

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

# Redis client for token blacklist
_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """Get or create Redis client for token blacklist"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
    return _redis_client


async def close_redis_client():
    """Close Redis client connection"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def add_token_to_blacklist(jti: str, exp: datetime) -> None:
    """Add a JWT token to the blacklist in Redis"""
    try:
        redis_client = await get_redis_client()
        now = datetime.now(timezone.utc)
        ttl = int((exp - now).total_seconds())

        if ttl > 0:
            await redis_client.setex(
                f"token_blacklist:{jti}",
                ttl,
                "1"
            )
            logger.debug(f"Token blacklisted: jti={jti}, ttl={ttl}s")
    except Exception as e:
        logger.warning(f"Redis unavailable, skipping token blacklist: {e}")


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a JWT token is in the blacklist"""
    try:
        redis_client = await get_redis_client()
        return await redis_client.exists(f"token_blacklist:{jti}") > 0
    except Exception as e:
        logger.warning(f"Redis unavailable, treating token as blacklisted (fail-closed): {e}")
        return True


# ==================== Token Version Functions ====================

async def get_token_version(user_id: int) -> int:
    """Get the current token version for a user from Redis.

    Returns 0 if no version is set (default for new users).
    """
    try:
        redis_client = await get_redis_client()
        version = await redis_client.get(f"token_version:{user_id}")
        return int(version) if version else 0
    except Exception as e:
        logger.warning(f"Redis unavailable, returning token version 0 (fail-open): {e}")
        return 0


async def increment_token_version(user_id: int) -> int:
    """Increment the token version for a user, invalidating all existing tokens.

    Returns the new version number.
    """
    try:
        redis_client = await get_redis_client()
        new_version = await redis_client.incr(f"token_version:{user_id}")
        logger.info(f"Token version incremented for user_id={user_id}: now at {new_version}")
        return new_version
    except Exception as e:
        logger.warning(f"Redis unavailable, returning token version 0 (fail-open): {e}")
        return 0


async def check_login_attempts(username: str) -> bool:
    """Check if account is locked due to too many failed login attempts.
    Returns True if account is locked."""
    try:
        redis_client = await get_redis_client()
        lock_key = f"login_lock:{username}"

        # Check if account is locked
        if await redis_client.exists(lock_key):
            return True

        return False
    except Exception as e:
        logger.warning(f"Redis unavailable, allowing login (fail-open): {e}")
        return False


async def check_captcha_required(username: str) -> bool:
    """Check if captcha verification is required for this username.
    Returns True if failed attempts >= CAPTCHA_THRESHOLD.
    Reads threshold from ConfigService (hot-reloadable)."""
    try:
        redis_client = await get_redis_client()
        attempts_key = f"login_attempts:{username}"
        attempts = await redis_client.get(attempts_key)
        if attempts:
            from app.services.config_service import get_config_value
            threshold = await get_config_value("captcha_threshold", settings.CAPTCHA_THRESHOLD)
            if int(attempts) >= threshold:
                return True
        return False
    except Exception as e:
        logger.warning(f"Redis unavailable, skipping captcha check (fail-open): {e}")
        return False


async def record_failed_login(username: str) -> None:
    """Record a failed login attempt and lock account if threshold exceeded.
    Reads thresholds from ConfigService (hot-reloadable)."""
    try:
        redis_client = await get_redis_client()
        attempts_key = f"login_attempts:{username}"
        lock_key = f"login_lock:{username}"

        # Increment failed attempts
        attempts = await redis_client.incr(attempts_key)
        if attempts == 1:
            from app.services.config_service import get_config_value
            lockout_minutes = await get_config_value("lockout_duration_minutes", settings.LOCKOUT_DURATION_MINUTES)
            await redis_client.expire(attempts_key, lockout_minutes * 60)

        # Lock account if threshold exceeded
        from app.services.config_service import get_config_value
        max_attempts = await get_config_value("max_login_attempts", settings.MAX_LOGIN_ATTEMPTS)
        lockout_minutes = await get_config_value("lockout_duration_minutes", settings.LOCKOUT_DURATION_MINUTES)
        if attempts >= max_attempts:
            await redis_client.setex(
                lock_key,
                lockout_minutes * 60,
                str(attempts)
            )
    except Exception as e:
        logger.warning(f"Redis unavailable, skipping failed login record: {e}")


async def reset_login_attempts(username: str) -> None:
    """Reset failed login attempts after successful login"""
    try:
        redis_client = await get_redis_client()
        attempts_key = f"login_attempts:{username}"
        lock_key = f"login_lock:{username}"

        await redis_client.delete(attempts_key, lock_key)
    except Exception as e:
        logger.warning(f"Redis unavailable, skipping login attempts reset: {e}")


# ==================== Captcha Functions ====================

CAPTCHA_TTL_SECONDS = 300  # 5 minutes


async def generate_captcha() -> Tuple[str, str]:
    """Generate a server-side arithmetic captcha.

    Returns:
        Tuple of (captcha_id, question_string)
    """
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    if random.random() > 0.5:
        question = f"{a} + {b}"
        answer = a + b
    else:
        x, y = max(a, b), min(a, b)
        question = f"{x} - {y}"
        answer = x - y

    captcha_id = str(uuid.uuid4())
    try:
        redis_client = await get_redis_client()
        await redis_client.setex(f"captcha:{captcha_id}", CAPTCHA_TTL_SECONDS, str(answer))
    except Exception as e:
        logger.error(f"Redis unavailable, cannot generate captcha: {e}")
        raise

    return captcha_id, question


async def verify_captcha(captcha_id: str, user_answer: str) -> bool:
    """Verify a captcha answer against the stored value in Redis.

    Args:
        captcha_id: The captcha UUID returned by generate_captcha
        user_answer: The user's answer string

    Returns:
        True if the answer is correct, False otherwise.
        Also returns False if the captcha_id is not found or expired.
        The captcha is always deleted after verification (one-time use).
    """
    try:
        redis_client = await get_redis_client()
        captcha_key = f"captcha:{captcha_id}"

        # Get and delete in a pipeline for atomicity
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.get(captcha_key)
            pipe.delete(captcha_key)
            results = await pipe.execute()

        stored_answer = results[0]
        if stored_answer is None:
            # Captcha not found or expired
            return False

        try:
            return int(user_answer) == int(stored_answer)
        except (ValueError, TypeError):
            return False
    except Exception as e:
        logger.warning(f"Redis unavailable, captcha verification failed (fail-closed): {e}")
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def create_access_token_async(data: dict, expires_delta: Optional[timedelta] = None, user_id: Optional[int] = None) -> str:
    """Create a JWT access token with hot-reloadable expiration.
    Reads access_token_expire_minutes from ConfigService.
    Includes token version (ver) for invalidation on password change."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        from app.services.config_service import get_config_value
        expire_minutes = await get_config_value("access_token_expire_minutes", settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti, "type": "access"})

    # Include token version for password-change invalidation
    if user_id is not None:
        to_encode["ver"] = await get_token_version(user_id)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return encoded_jwt


async def create_refresh_token_async(data: dict, user_id: Optional[int] = None) -> str:
    """Create a JWT refresh token with hot-reloadable expiration.
    Reads refresh_token_expire_days from ConfigService.
    Includes token version (ver) for invalidation on password change."""
    to_encode = data.copy()
    from app.services.config_service import get_config_value
    expire_days = await get_config_value("refresh_token_expire_days", settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti, "type": "refresh"})

    # Include token version for password-change invalidation
    if user_id is not None:
        to_encode["ver"] = await get_token_version(user_id)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return encoded_jwt


async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    """Authenticate a user by username and password"""
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """Get the current authenticated user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")

        if username is None:
            raise credentials_exception

        # Check if token is blacklisted
        if jti and await is_token_blacklisted(jti):
            raise credentials_exception

        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.username == token_data.username))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    # Verify token version — reject tokens issued before password change
    token_ver = payload.get("ver")
    if token_ver is not None:
        current_ver = await get_token_version(user.id)
        if int(token_ver) != current_ver:
            raise credentials_exception
    # Tokens without 'ver' field (legacy) are accepted if user version is still 0

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current user and verify they are a superuser"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )

    return current_user


async def get_user_permissions(db: AsyncSession, user_id: int) -> set[str]:
    """Get all permission codes for a user via their roles (with Redis cache)"""
    try:
        redis_client = await get_redis_client()
        cache_key = f"user_perms:{user_id}"
        cached = await redis_client.get(cache_key)
        if cached:
            return set(json.loads(cached))
    except Exception as e:
        logger.warning(f"Redis unavailable for permission cache: {e}")

    from sqlalchemy import select
    from app.models.role import Permission, RolePermission, UserRole

    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    perms = set(result.scalars().all())

    try:
        redis_client = await get_redis_client()
        await redis_client.setex(f"user_perms:{user_id}", 300, json.dumps(list(perms)))
    except Exception as e:
        logger.warning(f"Redis unavailable for permission cache write: {e}")

    return perms


async def invalidate_user_permissions(user_id: int) -> None:
    """Invalidate cached permissions for a user"""
    try:
        redis_client = await get_redis_client()
        await redis_client.delete(f"user_perms:{user_id}")
    except Exception as e:
        logger.warning(f"Redis unavailable for permission cache invalidation: {e}")


def require_permission(permission_code: str):
    """Dependency factory for permission-based access control.
    Superusers always pass. Other users must have the specified permission."""
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        if current_user.is_superuser:
            return current_user
        perms = await get_user_permissions(db, current_user.id)
        if permission_code not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission_code}"
            )
        return current_user
    return permission_checker
