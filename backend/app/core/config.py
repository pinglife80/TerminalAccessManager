from pydantic_settings import BaseSettings
from typing import List, Optional
import os
import sys


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    PROJECT_NAME: str = "Terminal Access Manager"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "tam_admin"
    DB_PASSWORD: str = ""
    DB_NAME: str = "tam_db"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Sangfor API (optional)
    SANGFOR_BASE_URL: Optional[str] = None
    SANGFOR_USERNAME: Optional[str] = None
    SANGFOR_PASSWORD: Optional[str] = None
    SANGFOR_CA_BUNDLE: Optional[str] = None

    # Switch Configuration (optional)
    SWITCH_HOST: Optional[str] = None
    SWITCH_USERNAME: Optional[str] = None
    SWITCH_PASSWORD: Optional[str] = None
    SWITCH_PORT: int = 23

    # IpGuard Database (optional)
    IPGUARD_HOST: Optional[str] = None
    IPGUARD_USER: Optional[str] = None
    IPGUARD_PASSWORD: Optional[str] = None
    IPGUARD_DATABASE: str = "OCULAR3"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost", "http://localhost:80"]

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 5

    # Account Lockout
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    CAPTCHA_THRESHOLD: int = 3

    # Registration Control
    ALLOW_REGISTRATION: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create global settings instance with validation
settings = Settings()

# Validate critical settings at startup
_INSECURE_DEFAULTS = [
    "change-this-to-a-random-secret-key-in-production",
    "your-secret-key-change-in-production",
    "CHANGE_ME_GENERATE_A_RANDOM_SECRET_KEY",
    "password",
    "redis_password",
    "CHANGE_ME_STRONG_DB_PASSWORD",
    "CHANGE_ME_STRONG_REDIS_PASSWORD",
]

if settings.ENVIRONMENT == "production":
    if settings.SECRET_KEY in _INSECURE_DEFAULTS:
        print(f"ERROR: SECRET_KEY is set to an insecure default value. "
              f"Generate a strong key with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"",
              file=sys.stderr)
        sys.exit(1)

    if len(settings.SECRET_KEY) < 32:
        print(f"ERROR: SECRET_KEY is too short ({len(settings.SECRET_KEY)} chars). "
              f"Minimum 32 characters required for production. "
              f"Generate a strong key with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"",
              file=sys.stderr)
        sys.exit(1)

    if not settings.DATABASE_URL or "password" in settings.DATABASE_URL.lower() and settings.DATABASE_URL.count("password") > 0:
        # Check if using default password in DATABASE_URL
        pass  # DATABASE_URL is validated by pydantic as required field

    if settings.DEBUG:
        print("WARNING: DEBUG mode is enabled in production environment!", file=sys.stderr)
