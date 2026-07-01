"""
Authentication Provider Base Interface for TerminalAccessManager.

Defines the abstract base class for all authentication providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class AuthProviderType(str, Enum):
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
    user_id: Optional[int] = None
    username: Optional[str] = None
    email: Optional[str] = None
    provider: Optional[str] = None
    provider_user_id: Optional[str] = None  # Third-party user ID
    error_message: Optional[str] = None
    requires_2fa: bool = False              # Whether 2FA is required


@dataclass
class AuthCredentials:
    """Authentication credentials data structure"""
    username: str
    password: Optional[str] = None
    code: Optional[str] = None              # 2FA code
    provider: Optional[str] = None          # Provider type
    remember_me: bool = False


@dataclass
class OAuthToken:
    """OAuth token information"""
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int = 0
    token_type: str = "Bearer"
    scope: Optional[str] = None


@dataclass
class ProviderConfig:
    """Authentication provider configuration"""
    id: Optional[int] = None
    name: str = "Default"
    provider_type: AuthProviderType = AuthProviderType.LOCAL
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 100                    # Lower number = higher priority


class AuthProviderBase(ABC):
    """Abstract base class for authentication providers"""

    provider_type: AuthProviderType = AuthProviderType.LOCAL
    provider_name: str = "Base Provider"

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the provider with configuration.

        Args:
            config: Provider configuration dictionary
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate required configuration fields. Override in subclasses."""
        pass

    @abstractmethod
    async def authenticate(self, credentials: AuthCredentials) -> AuthResult:
        """
        Authenticate user with provided credentials.

        Args:
            credentials: User credentials

        Returns:
            AuthResult indicating success or failure
        """
        pass

    @abstractmethod
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
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
        username: Optional[str] = None,
        email: Optional[str] = None,
        user_id: Optional[int] = None,
        provider_user_id: Optional[str] = None,
        error_message: Optional[str] = None,
        requires_2fa: bool = False,
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
    async def invalidate_codes(self, user_id: int, method: Optional[str] = None):
        """
        Invalidate all 2FA codes for a user.

        Args:
            user_id: User ID
            method: Specific method to invalidate, or None for all
        """
        pass
