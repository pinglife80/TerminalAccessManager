"""
System Configuration Service

Provides a cached, hot-reloadable configuration layer on top of the database.
- Configs are cached in Redis with a short TTL for fast reads
- Updates invalidate the cache immediately (write-through)
- Business logic reads from this service instead of raw settings
- Supports graceful fallback: DB -> Redis cache -> .env defaults
"""

import json
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.system_config import SystemConfig
from app.schemas.system_config import (
    AllConfigsResponse,
    AlertConfigResponse,
    BrandingConfigResponse,
    CacheConfigResponse,
    ComplianceConfigResponse,
    ConfigUpdateResult,
    ConfigValueType,
    EmailConfigResponse,
    GeneralConfigResponse,
    NetworkConfigResponse,
    RateLimitConfigResponse,
    SchedulerConfigResponse,
    SecurityConfigResponse,
    SystemConfigResponse,
    SystemConfigUpdate,
)

# Redis cache key prefix and TTL
CONFIG_CACHE_PREFIX = "sys_config:"
CONFIG_CACHE_TTL = 300  # 5 minutes


async def _get_redis():
    from app.core.security import get_redis_client
    return await get_redis_client()


def _cache_key(key: str) -> str:
    return f"{CONFIG_CACHE_PREFIX}{key}"


def _parse_value(raw: str, value_type: str) -> Any:
    """Parse a string value into its typed representation"""
    if value_type == ConfigValueType.INT:
        return int(raw)
    elif value_type == ConfigValueType.BOOL:
        return raw.lower() in ("true", "1", "yes")
    elif value_type == ConfigValueType.JSON:
        return json.loads(raw)
    return raw


class ConfigService:
    """Service for managing system configuration with Redis caching"""

    # Default configs that are seeded on first startup
    DEFAULT_CONFIGS: list[dict[str, Any]] = [
        # Security
        {"key": "max_login_attempts", "value": "5", "category": "security",
         "value_type": "int", "description": "Maximum failed login attempts before account lockout",
         "is_readonly": False},
        {"key": "lockout_duration_minutes", "value": "15", "category": "security",
         "value_type": "int", "description": "Account lockout duration in minutes",
         "is_readonly": False},
        {"key": "captcha_threshold", "value": "3", "category": "security",
         "value_type": "int", "description": "Failed login attempts before captcha is required",
         "is_readonly": False},
        {"key": "allow_registration", "value": "false", "category": "security",
         "value_type": "bool", "description": "Allow public user registration",
         "is_readonly": False},
        {"key": "access_token_expire_minutes", "value": "30", "category": "security",
         "value_type": "int", "description": "Access token expiration in minutes",
         "is_readonly": False},
        {"key": "refresh_token_expire_days", "value": "7", "category": "security",
         "value_type": "int", "description": "Refresh token expiration in days",
         "is_readonly": False},
        # Rate Limit
        {"key": "rate_limit_per_minute", "value": "60", "category": "rate_limit",
         "value_type": "int", "description": "General API rate limit per minute per IP",
         "is_readonly": False},
        {"key": "auth_rate_limit_per_minute", "value": "5", "category": "rate_limit",
         "value_type": "int", "description": "Authentication API rate limit per minute per IP",
         "is_readonly": False},
        # Network
        {"key": "sangfor_enabled", "value": "false", "category": "network",
         "value_type": "bool", "description": "Enable Sangfor AF firewall integration",
         "is_readonly": False},
        {"key": "sangfor_base_url", "value": "", "category": "network",
         "value_type": "string", "description": "Sangfor AF API base URL",
         "is_readonly": False},
        {"key": "switch_enabled", "value": "false", "category": "network",
         "value_type": "bool", "description": "Enable switch integration",
         "is_readonly": False},
        {"key": "switch_host", "value": "", "category": "network",
         "value_type": "string", "description": "Switch management host address",
         "is_readonly": False},
        {"key": "ipguard_enabled", "value": "false", "category": "network",
         "value_type": "bool", "description": "Enable IPGuard integration",
         "is_readonly": False},
        {"key": "ipguard_host", "value": "", "category": "network",
         "value_type": "string", "description": "IPGuard database host address",
         "is_readonly": False},
        # General
        {"key": "environment", "value": "development", "category": "general",
         "value_type": "string", "description": "Application environment (development/production)",
         "is_readonly": True},
        {"key": "debug", "value": "false", "category": "general",
         "value_type": "bool", "description": "Enable debug mode",
         "is_readonly": True},
        {"key": "log_level", "value": "INFO", "category": "general",
         "value_type": "string", "description": "Application log level (DEBUG/INFO/WARNING/ERROR)",
         "is_readonly": False},
        # Scheduler
        {"key": "scheduler_arp_collection_interval", "value": "300", "category": "scheduler",
         "value_type": "int", "description": "ARP data collection interval in seconds (30-86400)",
         "is_readonly": False},
        {"key": "scheduler_ipguard_sync_interval", "value": "600", "category": "scheduler",
         "value_type": "int", "description": "IPGuard data sync interval in seconds (30-86400)",
         "is_readonly": False},
        {"key": "scheduler_firewall_query_interval", "value": "300", "category": "scheduler",
         "value_type": "int", "description": "Firewall blacklist query interval in seconds (30-86400)",
         "is_readonly": False},
        {"key": "scheduler_compliance_check_interval", "value": "300", "category": "scheduler",
         "value_type": "int", "description": "Compliance check interval in seconds (30-86400)",
         "is_readonly": False},
        {"key": "scheduler_auto_unblock_interval", "value": "600", "category": "scheduler",
         "value_type": "int", "description": "Auto-unblock check interval in seconds (30-86400)",
         "is_readonly": False},
        {"key": "scheduler_backup_interval", "value": "3600", "category": "scheduler",
         "value_type": "int", "description": "Backup execution interval in seconds (30-86400)",
         "is_readonly": False},
        # Compliance
        {"key": "compliance_confirm_threshold", "value": "2", "category": "compliance",
         "value_type": "int", "description": "Consecutive non-compliant detections before status flips (1-10)",
         "is_readonly": False},
        {"key": "block_time", "value": "30d", "category": "compliance",
         "value_type": "string", "description": "Default blacklist block duration (e.g. 1h/6h/12h/1d/3d/7d/15d/30d)",
         "is_readonly": False},
        {"key": "ipguard_stale_threshold_minutes", "value": "12", "category": "compliance",
         "value_type": "int", "description": "IPGuard cache stale threshold in minutes (5-60)",
         "is_readonly": False},
        # Cache
        {"key": "cache_ipguard_ttl", "value": "900", "category": "cache",
         "value_type": "int", "description": "IPGuard data cache TTL in seconds (60-7200)",
         "is_readonly": False},
        {"key": "cache_whitelist_ttl", "value": "300", "category": "cache",
         "value_type": "int", "description": "Whitelist data cache TTL in seconds (60-3600)",
         "is_readonly": False},
        # Branding
        {"key": "app_name", "value": "Terminal Access Manager", "category": "branding",
         "value_type": "string", "description": "Application display name",
         "is_readonly": False},
        {"key": "app_short_name", "value": "Terminal Access", "category": "branding",
         "value_type": "string", "description": "Short name for sidebar",
         "is_readonly": False},
        {"key": "app_subtitle", "value": "Manager", "category": "branding",
         "value_type": "string", "description": "Subtitle below app name in sidebar",
         "is_readonly": False},
        {"key": "login_heading", "value": "Terminal Access Manager", "category": "branding",
         "value_type": "string", "description": "Login page heading text",
         "is_readonly": False},
        {"key": "login_subheading", "value": "Sign in to your account", "category": "branding",
         "value_type": "string", "description": "Login page subheading text",
         "is_readonly": False},
        {"key": "login_footer_text", "value": "Secure authentication · Session-based access control", "category": "branding",
         "value_type": "string", "description": "Login page footer text",
         "is_readonly": False},
        {"key": "footer_copyright", "value": "© {year} TerminalAccessManager (TAM)", "category": "branding",
         "value_type": "string", "description": "Footer copyright text ({year} replaced dynamically)",
         "is_readonly": False},
        {"key": "footer_icp_number", "value": "", "category": "branding",
         "value_type": "string", "description": "ICP filing number (leave empty to hide)",
         "is_readonly": False},
        {"key": "footer_icp_url", "value": "https://beian.miit.gov.cn/", "category": "branding",
         "value_type": "string", "description": "ICP filing URL",
         "is_readonly": False},
        {"key": "login_bg_url", "value": "", "category": "branding",
         "value_type": "string", "description": "Login page background image URL (leave empty for gradient)",
         "is_readonly": False},
        {"key": "favicon_url", "value": "", "category": "branding",
         "value_type": "string", "description": "Custom favicon URL (leave empty for default)",
         "is_readonly": False},
        # Email Configuration
        {"key": "email_enabled", "value": "false", "category": "email",
         "value_type": "bool", "description": "Enable email service for notifications and verification codes",
         "is_readonly": False},
        {"key": "email_host", "value": "", "category": "email",
         "value_type": "string", "description": "SMTP server host (e.g. smtp.gmail.com)",
         "is_readonly": False},
        {"key": "email_port", "value": "465", "category": "email",
         "value_type": "int", "description": "SMTP server port (465 for SSL, 587 for TLS)",
         "is_readonly": False},
        {"key": "email_use_tls", "value": "false", "category": "email",
         "value_type": "bool", "description": "Use STARTTLS encryption",
         "is_readonly": False},
        {"key": "email_use_ssl", "value": "true", "category": "email",
         "value_type": "bool", "description": "Use SSL encryption (mutually exclusive with TLS)",
         "is_readonly": False},
        {"key": "email_username", "value": "", "category": "email",
         "value_type": "string", "description": "SMTP authentication username",
         "is_readonly": False},
        {"key": "email_password", "value": "", "category": "email",
         "value_type": "string", "description": "SMTP authentication password (use authorization code/授权码 for QQ/163)",
         "is_readonly": False},
        {"key": "email_from", "value": "", "category": "email",
         "value_type": "string", "description": "Sender email address",
         "is_readonly": False},
        {"key": "email_from_name", "value": "TAM System", "category": "email",
         "value_type": "string", "description": "Sender display name",
         "is_readonly": False},
        {"key": "email_rate_limit", "value": "10", "category": "email",
         "value_type": "int", "description": "Maximum emails sent per minute",
         "is_readonly": False},
        # Alert thresholds
        {"key": "alert_compliance_rate_threshold", "value": "80", "category": "alert",
         "value_type": "int", "description": "Compliance rate alert threshold in percent (trigger when below)",
         "is_readonly": False},
        {"key": "alert_compliance_critical_ratio", "value": "50", "category": "alert",
         "value_type": "int", "description": "Critical ratio in percent of threshold (trigger severe alert when compliance rate below threshold x ratio)",
         "is_readonly": False},
        {"key": "alert_block_count_threshold", "value": "50", "category": "alert",
         "value_type": "int", "description": "Block count alert threshold (trigger when single auto-block exceeds this count)",
         "is_readonly": False},
        {"key": "alert_offline_threshold_multiplier", "value": "3", "category": "alert",
         "value_type": "int", "description": "Offline detection multiplier (ARP interval x this = offline threshold seconds)",
         "is_readonly": False},
    ]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def seed_defaults(self) -> int:
        """Seed default configs into the database. Idempotent - skips existing keys."""
        count = 0
        for cfg in self.DEFAULT_CONFIGS:
            stmt = select(SystemConfig).where(SystemConfig.key == cfg["key"])
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if not existing:
                # For keys that have .env values, use those as initial value
                env_value = self._get_env_default(cfg["key"])
                if env_value is not None:
                    cfg = {**cfg, "value": str(env_value)}

                entry = SystemConfig(**cfg)
                self.db.add(entry)
                count += 1
                logger.info(f"Seeded config: {cfg['key']} = {cfg['value']}")

        if count > 0:
            await self.db.commit()
            logger.info(f"Seeded {count} default configs")
        return count

    def _get_env_default(self, key: str) -> str | None:
        """Get the current .env value for a config key, if it exists"""
        env_mapping = {
            "max_login_attempts": settings.MAX_LOGIN_ATTEMPTS,
            "lockout_duration_minutes": settings.LOCKOUT_DURATION_MINUTES,
            "captcha_threshold": settings.CAPTCHA_THRESHOLD,
            "allow_registration": settings.ALLOW_REGISTRATION,
            "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
            "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
            "auth_rate_limit_per_minute": settings.AUTH_RATE_LIMIT_PER_MINUTE,
            "sangfor_enabled": bool(settings.SANGFOR_BASE_URL),
            "sangfor_base_url": settings.SANGFOR_BASE_URL or "",
            "switch_enabled": bool(settings.SWITCH_HOST),
            "switch_host": settings.SWITCH_HOST or "",
            "ipguard_enabled": bool(settings.IPGUARD_HOST),
            "ipguard_host": settings.IPGUARD_HOST or "",
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
            "log_level": settings.LOG_LEVEL,
            "email_enabled": bool(settings.EMAIL_HOST),
            "email_host": settings.EMAIL_HOST or "",
            "email_port": settings.EMAIL_PORT,
            "email_use_tls": settings.EMAIL_USE_TLS,
            "email_use_ssl": settings.EMAIL_USE_SSL,
            "email_username": settings.EMAIL_USERNAME or "",
            "email_password": settings.EMAIL_PASSWORD or "",
            "email_from": settings.EMAIL_FROM or "",
            "email_from_name": settings.EMAIL_FROM_NAME,
            "email_rate_limit": settings.EMAIL_RATE_LIMIT_PER_MINUTE,
        }
        return env_mapping.get(key)

    async def get(self, key: str) -> str | None:
        """Get a config value. Reads from Redis cache first, then DB, then .env fallback."""
        # Try Redis cache first
        try:
            redis = await _get_redis()
            cached = await redis.get(_cache_key(key))
            if cached is not None:
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception:
            pass  # Redis unavailable, fall through to DB

        # Try database
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()

        if config:
            # Cache it
            try:
                redis = await _get_redis()
                await redis.setex(_cache_key(key), CONFIG_CACHE_TTL, config.value)
            except Exception:
                pass
            return config.value

        # Fallback to .env
        env_value = self._get_env_default(key)
        if env_value is not None:
            return str(env_value)

        return None

    async def get_typed(self, key: str, default: Any = None) -> Any:
        """Get a typed config value (auto-parses based on DB value_type or falls back to type of default)"""
        raw = await self.get(key)
        if raw is None:
            return default

        # Get value_type from DB for proper parsing
        stmt = select(SystemConfig.value_type).where(SystemConfig.key == key)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        value_type = row if row else ConfigValueType.STRING

        try:
            return _parse_value(raw, value_type)
        except (ValueError, json.JSONDecodeError):
            return default

    async def get_value(self, key: str) -> str | None:
        """Get a config value by key"""
        stmt = select(SystemConfig.value).where(SystemConfig.key == key)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return str(row) if row is not None else None

    async def set(self, key: str, value: str, updated_by: str = "system") -> ConfigUpdateResult:
        """Set a config value. Validates, persists, invalidates cache."""
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            return ConfigUpdateResult(key=key, success=False, message="Config key not found")

        if config.is_readonly:
            return ConfigUpdateResult(key=key, success=False, message="Config is read-only")

        # Validate value against value_type
        validation_error = self._validate_value(value, config.value_type)
        if validation_error:
            return ConfigUpdateResult(key=key, success=False, message=validation_error)

        # Update database
        config.value = value
        config.updated_by = updated_by
        config.updated_at = datetime.now(UTC)
        await self.db.commit()

        # Invalidate Redis cache
        await self._invalidate_cache(key)

        logger.info(f"Config updated: {key} = {value} (by {updated_by})")
        return ConfigUpdateResult(key=key, success=True)

    async def batch_update(self, updates: list[SystemConfigUpdate], updated_by: str = "system") -> list[ConfigUpdateResult]:
        """Update multiple configs at once. All-or-nothing: if any validation fails, none are applied."""
        results = []

        # Pre-validate all updates
        for upd in updates:
            stmt = select(SystemConfig).where(SystemConfig.key == upd.key)
            result = await self.db.execute(stmt)
            config = result.scalar_one_or_none()

            if not config:
                results.append(ConfigUpdateResult(key=upd.key, success=False, message="Config key not found"))
                continue
            if config.is_readonly:
                results.append(ConfigUpdateResult(key=upd.key, success=False, message="Config is read-only"))
                continue

            validation_error = self._validate_value(upd.value, config.value_type)
            if validation_error:
                results.append(ConfigUpdateResult(key=upd.key, success=False, message=validation_error))
                continue

        # If any validation failed, return without applying
        if any(not r.success for r in results):
            return results

        # Apply all updates
        for upd in updates:
            r = await self.set(upd.key, upd.value, updated_by)
            results.append(r)

        return results

    def _validate_value(self, value: str, value_type: str) -> str | None:
        """Validate a value against its declared type. Returns error message or None."""
        try:
            if value_type == ConfigValueType.INT:
                int(value)
                if int(value) < 0:
                    return "Value must be a non-negative integer"
            elif value_type == ConfigValueType.BOOL:
                if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                    return "Value must be true/false"
            elif value_type == ConfigValueType.JSON:
                json.loads(value)
        except ValueError:
            return f"Invalid value for type {value_type}"
        except json.JSONDecodeError:
            return "Invalid JSON format"
        return None

    async def _invalidate_cache(self, key: str):
        """Remove a config key from Redis cache"""
        try:
            redis = await _get_redis()
            await redis.delete(_cache_key(key))
        except Exception:
            pass

    async def _invalidate_all_cache(self):
        """Remove all config keys from Redis cache"""
        try:
            redis = await _get_redis()
            async for key in redis.scan_iter(match=f"{CONFIG_CACHE_PREFIX}*"):
                await redis.delete(key)
        except Exception:
            pass

    async def list_all(self, category: str | None = None) -> list[SystemConfigResponse]:
        """List all configs, optionally filtered by category"""
        stmt = select(SystemConfig).order_by(SystemConfig.category, SystemConfig.key)
        if category:
            stmt = stmt.where(SystemConfig.category == category)
        result = await self.db.execute(stmt)
        configs = result.scalars().all()
        return [SystemConfigResponse.model_validate(c) for c in configs]

    async def get_all_grouped(self) -> AllConfigsResponse:
        """Get all configs grouped by category, with typed values"""
        all_configs = await self.list_all()
        config_map = {c.key: c for c in all_configs}

        def _val(key: str, default: Any = None) -> Any:
            c = config_map.get(key)
            if c:
                try:
                    return _parse_value(c.value, c.value_type)
                except (ValueError, json.JSONDecodeError):
                    pass
            return default

        return AllConfigsResponse(
            security=SecurityConfigResponse(
                max_login_attempts=_val("max_login_attempts", 5),
                lockout_duration_minutes=_val("lockout_duration_minutes", 15),
                captcha_threshold=_val("captcha_threshold", 3),
                allow_registration=_val("allow_registration", False),
                access_token_expire_minutes=_val("access_token_expire_minutes", 30),
                refresh_token_expire_days=_val("refresh_token_expire_days", 7),
            ),
            rate_limit=RateLimitConfigResponse(
                rate_limit_per_minute=_val("rate_limit_per_minute", 60),
                auth_rate_limit_per_minute=_val("auth_rate_limit_per_minute", 5),
            ),
            network=NetworkConfigResponse(
                sangfor_enabled=_val("sangfor_enabled", False),
                sangfor_base_url=_val("sangfor_base_url", ""),
                switch_enabled=_val("switch_enabled", False),
                switch_host=_val("switch_host", ""),
                ipguard_enabled=_val("ipguard_enabled", False),
                ipguard_host=_val("ipguard_host", ""),
            ),
            scheduler=SchedulerConfigResponse(
                scheduler_arp_collection_interval=_val("scheduler_arp_collection_interval", 300),
                scheduler_ipguard_sync_interval=_val("scheduler_ipguard_sync_interval", 600),
                scheduler_firewall_query_interval=_val("scheduler_firewall_query_interval", 300),
                scheduler_compliance_check_interval=_val("scheduler_compliance_check_interval", 300),
                scheduler_auto_unblock_interval=_val("scheduler_auto_unblock_interval", 600),
                scheduler_backup_interval=_val("scheduler_backup_interval", 3600),
            ),
            general=GeneralConfigResponse(
                environment=_val("environment", "development"),
                debug=_val("debug", False),
                log_level=_val("log_level", "INFO"),
            ),
            branding=BrandingConfigResponse(
                app_name=_val("app_name", "Terminal Access Manager"),
                app_short_name=_val("app_short_name", "Terminal Access"),
                app_subtitle=_val("app_subtitle", "Manager"),
                login_heading=_val("login_heading", "Terminal Access Manager"),
                login_subheading=_val("login_subheading", "Sign in to your account"),
                login_footer_text=_val("login_footer_text", "Secure authentication · Session-based access control"),
                login_bg_url=_val("login_bg_url", ""),
                favicon_url=_val("favicon_url", ""),
                footer_copyright=_val("footer_copyright", "© {year} TerminalAccessManager (TAM)"),
                footer_icp_number=_val("footer_icp_number", ""),
                footer_icp_url=_val("footer_icp_url", "https://beian.miit.gov.cn/"),
            ),
            email=EmailConfigResponse(
                email_enabled=_val("email_enabled", False),
                email_host=_val("email_host", ""),
                email_port=_val("email_port", 465),
                email_use_tls=_val("email_use_tls", False),
                email_use_ssl=_val("email_use_ssl", True),
                email_username=_val("email_username", ""),
                email_password=_val("email_password", ""),
                email_from=_val("email_from", ""),
                email_from_name=_val("email_from_name", "TAM System"),
                email_rate_limit=_val("email_rate_limit", 10),
            ),
            compliance=ComplianceConfigResponse(
                compliance_confirm_threshold=_val("compliance_confirm_threshold", 2),
                block_time=_val("block_time", "30d"),
                ipguard_stale_threshold_minutes=_val("ipguard_stale_threshold_minutes", 12),
            ),
            cache=CacheConfigResponse(
                cache_ipguard_ttl=_val("cache_ipguard_ttl", 900),
                cache_whitelist_ttl=_val("cache_whitelist_ttl", 300),
            ),
            alert=AlertConfigResponse(
                alert_compliance_rate_threshold=_val("alert_compliance_rate_threshold", 80),
                alert_compliance_critical_ratio=_val("alert_compliance_critical_ratio", 50),
                alert_block_count_threshold=_val("alert_block_count_threshold", 50),
                alert_offline_threshold_multiplier=_val("alert_offline_threshold_multiplier", 3),
            ),
        )


# Module-level convenience functions for business logic to call directly
# These use the Redis cache and avoid needing a DB session for reads

async def get_config_value(key: str, default: Any = None) -> Any:
    """Get a typed config value without needing a DB session.
    Uses Redis cache first, falls back to DB, then .env settings."""
    # Try Redis cache first
    try:
        redis = await _get_redis()
        cached = await redis.get(_cache_key(key))
        if cached is not None:
            raw = cached.decode() if isinstance(cached, bytes) else cached
            # Infer type from default
            if isinstance(default, bool):
                return raw.lower() in ("true", "1", "yes")
            elif isinstance(default, int):
                return int(raw)
            return raw
    except Exception:
        pass

    # Try database
    from app.core.database import get_db
    try:
        async for db in get_db():
            stmt = select(SystemConfig).where(SystemConfig.key == key)
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()
            if config:
                # Cache it
                try:
                    redis = await _get_redis()
                    await redis.setex(_cache_key(key), CONFIG_CACHE_TTL, config.value)
                except Exception:
                    pass
                # Parse type
                raw = config.value
                if isinstance(default, bool):
                    return raw.lower() in ("true", "1", "yes")
                elif isinstance(default, int):
                    return int(raw)
                return raw
    except Exception:
        pass

    # Fallback to .env settings
    env_mapping = {
        "max_login_attempts": settings.MAX_LOGIN_ATTEMPTS,
        "lockout_duration_minutes": settings.LOCKOUT_DURATION_MINUTES,
        "captcha_threshold": settings.CAPTCHA_THRESHOLD,
        "allow_registration": settings.ALLOW_REGISTRATION,
        "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
        "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
        "auth_rate_limit_per_minute": settings.AUTH_RATE_LIMIT_PER_MINUTE,
        "sangfor_enabled": bool(settings.SANGFOR_BASE_URL),
        "sangfor_base_url": settings.SANGFOR_BASE_URL or "",
        "switch_enabled": bool(settings.SWITCH_HOST),
        "switch_host": settings.SWITCH_HOST or "",
        "ipguard_enabled": bool(settings.IPGUARD_HOST),
        "ipguard_host": settings.IPGUARD_HOST or "",
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "email_enabled": bool(settings.EMAIL_HOST),
        "email_host": settings.EMAIL_HOST or "",
        "email_port": settings.EMAIL_PORT,
        "email_use_tls": settings.EMAIL_USE_TLS,
        "email_use_ssl": settings.EMAIL_USE_SSL,
        "email_username": settings.EMAIL_USERNAME or "",
        "email_password": settings.EMAIL_PASSWORD or "",
        "email_from": settings.EMAIL_FROM or "",
        "email_from_name": settings.EMAIL_FROM_NAME,
        "email_rate_limit": settings.EMAIL_RATE_LIMIT_PER_MINUTE,
    }
    return env_mapping.get(key, default)
