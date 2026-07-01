"""
Authentication Provider Factory for TerminalAccessManager.

Factory class to create and manage authentication providers.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_providers.base import AuthProviderBase, AuthProviderType
from app.services.auth_providers.local_provider import LocalProvider

try:
    from app.services.auth_providers.ldap_provider import LDAPProvider
    LDAP_AVAILABLE = True
except ImportError:
    LDAPProvider = None
    LDAP_AVAILABLE = False


class AuthProviderFactory:
    """
    Factory class for creating authentication providers.

    Supports:
    - Local authentication
    - LDAP authentication
    """

    _providers: dict[str, type[AuthProviderBase]] = {
        AuthProviderType.LOCAL.value: LocalProvider,
    }

    if LDAP_AVAILABLE:
        _providers[AuthProviderType.LDAP.value] = LDAPProvider

    @classmethod
    def register_provider(cls, provider_type: str, provider_class: type[AuthProviderBase]) -> None:
        """
        Register a new authentication provider.

        Args:
            provider_type: Provider type identifier
            provider_class: Provider class to register
        """
        cls._providers[provider_type] = provider_class

    @classmethod
    def get_provider_class(cls, provider_type: str) -> type[AuthProviderBase] | None:
        """
        Get provider class by type.

        Args:
            provider_type: Provider type identifier

        Returns:
            Provider class if found, None otherwise
        """
        return cls._providers.get(provider_type.lower())

    @classmethod
    async def create_provider(
        cls,
        provider_type: str,
        config: dict[str, Any],
        db: AsyncSession | None = None,
    ) -> AuthProviderBase:
        """
        Create an authentication provider instance.

        Args:
            provider_type: Provider type identifier
            config: Provider configuration
            db: Database session (required for local provider)

        Returns:
            AuthProviderBase instance

        Raises:
            ValueError: If provider type is not supported
        """
        provider_class = cls.get_provider_class(provider_type)
        if not provider_class:
            raise ValueError(f"Unsupported authentication provider: {provider_type}")

        # Local provider requires database session
        if provider_type.lower() == AuthProviderType.LOCAL.value and db:
            return provider_class(config, db)

        return provider_class(config)

    @classmethod
    async def get_enabled_providers(
        cls,
        db: AsyncSession,
    ) -> dict[str, AuthProviderBase]:
        """
        Get all enabled authentication providers from database.

        Args:
            db: Database session

        Returns:
            Dictionary of provider instances keyed by type
        """
        from app.models.auth_config import AuthConfig

        providers = {}

        # Always include local provider
        local_config = {
            "require_2fa": False,
        }
        providers[AuthProviderType.LOCAL.value] = LocalProvider(local_config, db)

        # Get other providers from database
        stmt = select(AuthConfig).where(AuthConfig.enabled == True)
        result = await db.execute(stmt)
        configs = result.scalars().all()

        for config in configs:
            try:
                provider = await cls.create_provider(config.provider_type, config.config, db)
                providers[config.provider_type] = provider
            except Exception as e:
                # Log error but don't fail
                from loguru import logger
                logger.error(f"Failed to create provider {config.provider_type}: {e}")

        return providers

    @classmethod
    async def authenticate(
        cls,
        provider_type: str,
        credentials: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Authenticate using the specified provider.

        Args:
            provider_type: Provider type to use
            credentials: User credentials
            db: Database session

        Returns:
            Authentication result dictionary
        """
        provider = await cls.create_provider(provider_type, {}, db)
        auth_result = await provider.authenticate(
            credentials.get("username", ""),
            credentials.get("password", ""),
        )

        return {
            "success": auth_result.success,
            "user_id": auth_result.user_id,
            "username": auth_result.username,
            "email": auth_result.email,
            "provider": auth_result.provider,
            "requires_2fa": auth_result.requires_2fa,
            "error_message": auth_result.error_message,
        }
