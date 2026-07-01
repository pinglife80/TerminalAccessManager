"""
Authentication Provider Base Interface for TerminalAccessManager.

Defines the abstract base class for all authentication providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AuthProviderType(StrEnum):
    """Authentication provider type enumeration"""
    LOCAL = "local"
    LDAP = "ldap"
    OAUTH_FEISHU = "oauth_feishu"
    OAUTH_DINGTALK = "oauth_dingtalk"
    OAUTH_WECOM = "oauth_wecom"


@dataclass
class AuthResult:
    """Authentication result data structure"""
    success: bool
    user_id: int | None = None
    username: str | None = None
    email: str | None = None
    provider: str | None = None
    provider_user_id: str | None = None
    error_message: str | None = None
    requires_2fa: bool = False
    user: Any | None = None
    message: str = ""
    mfa_required: bool = False


@dataclass
class AuthCredentials:
    """Authentication credentials data structure"""
    username: str
    password: str | None = None
    code: str | None = None              # 2FA code
    provider: str | None = None          # Provider type
    remember_me: bool = False


@dataclass
class OAuthToken:
    """OAuth token information"""
    access_token: str
    refresh_token: str | None = None
    expires_in: int = 0
    token_type: str = "Bearer"
    scope: str | None = None


@dataclass
class ProviderConfig:
    """Authentication provider configuration"""
    id: int | None = None
    name: str = "Default"
    provider_type: AuthProviderType = AuthProviderType.LOCAL
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100                    # Lower number = higher priority


class AuthProviderBase(ABC):
    """Abstract base class for authentication providers"""

    provider_type: AuthProviderType = AuthProviderType.LOCAL
    provider_name: str = "Base Provider"

    def __init__(self, config: dict[str, Any], db: Any | None = None):
        """
        Initialize the provider with configuration.

        Args:
            config: Provider configuration dictionary
            db: Database session
        """
        self.config = config
        self.db = db
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """Validate required configuration fields. Override in subclasses."""
        pass

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> AuthResult:
        """
        Authenticate user with provided credentials.

        Args:
            username: Username
            password: Password

        Returns:
            AuthResult indicating success or failure
        """
        pass

    @abstractmethod
    async def get_user_info(self, user_id: str) -> dict[str, Any]:
        """
        Get user information from the provider.

        Args:
            user_id: User identifier in the provider

        Returns:
            Dictionary of user information
        """
        pass

    @abstractmethod
    async def test_connection(self) -> dict:
        """
        Test the provider connection/configuration.

        Returns:
            Dict with test result (success, message, details)
        """
        pass

    @property
    def requires_password(self) -> bool:
        """Whether this provider requires password authentication"""
        return True

    @property
    def supports_2fa(self) -> bool:
        """Whether this provider supports two-factor authentication"""
        return True

    def build_auth_result(
        self,
        success: bool,
        username: str | None = None,
        email: str | None = None,
        user_id: int | None = None,
        provider_user_id: str | None = None,
        error_message: str | None = None,
        requires_2fa: bool = False,
        user: Any | None = None,
        message: str = "",
    ) -> AuthResult:
        """
        Build an AuthResult instance.

        Args:
            success: Whether authentication succeeded
            username: Username
            email: User email
            user_id: Local user ID
            provider_user_id: Provider-specific user ID
            error_message: Error message if failed
            requires_2fa: Whether 2FA is required
            user: User object
            message: Result message

        Returns:
            AuthResult instance
        """
        return AuthResult(
            success=success,
            user_id=user_id,
            username=username,
            email=email,
            provider=self.provider_type.value,
            provider_user_id=provider_user_id,
            error_message=error_message,
            requires_2fa=requires_2fa,
            user=user,
            message=message,
        )


class TwoFactorProviderBase(ABC):
    """Abstract base class for two-factor authentication providers"""

    @abstractmethod
    async def generate_code(self, user_id: int, method: str = "email") -> str:
        """
        Generate a 2FA code for the user.

        Args:
            user_id: User ID
            method: 2FA method (email, sms, authenticator)

        Returns:
            Generated verification code
        """
        pass

    @abstractmethod
    async def verify_code(self, user_id: int, code: str, method: str = "email") -> bool:
        """
        Verify a 2FA code.

        Args:
            user_id: User ID
            code: Verification code
            method: 2FA method

        Returns:
            True if code is valid
        """
        pass

    @abstractmethod
    async def invalidate_codes(self, user_id: int, method: str | None = None):
        """
        Invalidate all 2FA codes for a user.

        Args:
            user_id: User ID
            method: Specific method to invalidate, or None for all
        """
        pass
