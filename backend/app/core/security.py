from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as aioredis
import uuid

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.auth import TokenData

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
            decode_responses=True
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
    redis_client = await get_redis_client()
    now = datetime.now(timezone.utc)
    ttl = int((exp - now).total_seconds())

    if ttl > 0:
        await redis_client.setex(
            f"token_blacklist:{jti}",
            ttl,
            "1"
        )


async def is_token_blacklisted(jti: str) -> bool:
    """Check if a JWT token is in the blacklist"""
    redis_client = await get_redis_client()
    return await redis_client.exists(f"token_blacklist:{jti}") > 0


async def check_login_attempts(username: str) -> bool:
    """Check if account is locked due to too many failed login attempts.
    Returns True if account is locked."""
    redis_client = await get_redis_client()
    lock_key = f"login_lock:{username}"
    attempts_key = f"login_attempts:{username}"

    # Check if account is locked
    if await redis_client.exists(lock_key):
        return True

    return False


async def record_failed_login(username: str) -> None:
    """Record a failed login attempt and lock account if threshold exceeded"""
    redis_client = await get_redis_client()
    attempts_key = f"login_attempts:{username}"
    lock_key = f"login_lock:{username}"

    # Increment failed attempts
    attempts = await redis_client.incr(attempts_key)
    if attempts == 1:
        await redis_client.expire(attempts_key, settings.LOCKOUT_DURATION_MINUTES * 60)

    # Lock account if threshold exceeded
    if attempts >= settings.MAX_LOGIN_ATTEMPTS:
        await redis_client.setex(
            lock_key,
            settings.LOCKOUT_DURATION_MINUTES * 60,
            str(attempts)
        )


async def reset_login_attempts(username: str) -> None:
    """Reset failed login attempts after successful login"""
    redis_client = await get_redis_client()
    attempts_key = f"login_attempts:{username}"
    lock_key = f"login_lock:{username}"

    await redis_client.delete(attempts_key, lock_key)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti})
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
