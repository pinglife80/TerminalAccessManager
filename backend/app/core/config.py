import sys

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    PROJECT_NAME: str = "Terminal Access Manager"
    VERSION: str = "3.6.0"
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
    ENCRYPTION_KEY: str | None = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Sangfor API (optional)
    SANGFOR_BASE_URL: str | None = None
    SANGFOR_USERNAME: str | None = None
    SANGFOR_PASSWORD: str | None = None
    SANGFOR_CA_BUNDLE: str | None = None

    # Switch Configuration (optional)
    SWITCH_HOST: str | None = None
    SWITCH_USERNAME: str | None = None
    SWITCH_PASSWORD: str | None = None
    SWITCH_PORT: int = 23

    # IpGuard Database (optional)
    IPGUARD_HOST: str | None = None
    IPGUARD_USER: str | None = None
    IPGUARD_PASSWORD: str | None = None
    IPGUARD_DATABASE: str = "OCULAR3"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str | None = None

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:80"]

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 120
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # Account Lockout
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    CAPTCHA_THRESHOLD: int = 3

    # Registration Control
    ALLOW_REGISTRATION: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"
    TZ: str = "Asia/Shanghai"

    # Metrics
    PROMETHEUS_ENABLED: bool = False

    # Upload
    UPLOAD_DIR: str = "./uploads"

    # Email Configuration
    EMAIL_HOST: str | None = None
    EMAIL_PORT: int = 465
    EMAIL_USE_TLS: bool = False
    EMAIL_USE_SSL: bool = True
    EMAIL_USERNAME: str | None = None
    EMAIL_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    EMAIL_FROM_NAME: str = "TAM System"
    EMAIL_SMTP_URL: str | None = None  # HTTP SMTP relay URL (optional)

    # Email Rate Limiting
    EMAIL_RATE_LIMIT_PER_MINUTE: int = 10
    EMAIL_CODE_EXPIRE_MINUTES: int = 10

    # Company Info (for email templates)
    COMPANY_NAME: str = "TAM"
    SUPPORT_EMAIL: str | None = None

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
        print("ERROR: SECRET_KEY is set to an insecure default value. "
              "Generate a strong key with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"",
              file=sys.stderr)
        sys.exit(1)

    if len(settings.SECRET_KEY) < 32:
        print(f"ERROR: SECRET_KEY is too short ({len(settings.SECRET_KEY)} chars). "
              f"Minimum 32 characters required for production. "
              f"Generate a strong key with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"",
              file=sys.stderr)
        sys.exit(1)

    if not settings.ENCRYPTION_KEY:
        print("ERROR: ENCRYPTION_KEY is not set in production environment. "
              "ENCRYPTION_KEY must be set separately from SECRET_KEY for field-level encryption. "
              "Generate a strong key with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"",
              file=sys.stderr)
        sys.exit(1)

    if settings.ENCRYPTION_KEY == settings.SECRET_KEY:
        print("ERROR: ENCRYPTION_KEY must be different from SECRET_KEY in production. "
              "Using the same key for both JWT signing and field encryption violates key separation principle.",
              file=sys.stderr)
        sys.exit(1)

    if not settings.DATABASE_URL or "password" in settings.DATABASE_URL.lower() and settings.DATABASE_URL.count("password") > 0:
        # Check if using default password in DATABASE_URL
        pass  # DATABASE_URL is validated by pydantic as required field

    if settings.DEBUG:
        print("WARNING: DEBUG mode is enabled in production environment!", file=sys.stderr)
