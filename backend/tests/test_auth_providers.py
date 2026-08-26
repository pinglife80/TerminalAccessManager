"""Unit tests for authentication providers"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Test imports must come after setting environment
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-for-testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from app.models.user import User
from app.services.auth_providers.base import AuthResult
from app.services.auth_providers.ldap_provider import LDAPProvider
from app.services.auth_providers.local_provider import LocalProvider
from app.services.auth_providers.provider_factory import AuthProviderFactory
from app.services.auth_providers.two_factor_service import TwoFactorService


class TestAuthProviderBase:
    """Test cases for AuthProviderBase abstract class"""

    def test_auth_result_success(self):
        """Test AuthResult success case"""
        user = User(id=1, username="test", email="test@example.com")
        result = AuthResult(success=True, user=user, message="Success")
        assert result.success is True
        assert result.user == user
        assert result.message == "Success"
        assert result.mfa_required is False

    def test_auth_result_failure(self):
        """Test AuthResult failure case"""
        result = AuthResult(success=False, message="Failed")
        assert result.success is False
        assert result.user is None
        assert result.message == "Failed"


class TestLocalProvider:
    """Test cases for LocalProvider"""

    @pytest.mark.asyncio
    @patch("app.services.auth_providers.local_provider.verify_password")
    async def test_authenticate_success(self, mock_verify_password):
        """Test successful local authentication"""
        mock_verify_password.return_value = True

        mock_db = AsyncMock()

        class MockUser:
            def __init__(self):
                self.id = 1
                self.username = "testuser"
                self.email = "test@example.com"
                self.hashed_password = "hashed_password"
                self.is_active = True

        mock_user = MockUser()

        async def mock_execute(*args, **kwargs):
            class MockResult:
                def scalar_one_or_none(self):
                    return mock_user
            return MockResult()

        mock_db.execute = mock_execute

        provider = LocalProvider({"enabled": True}, mock_db)
        result = await provider.authenticate("testuser", "correct_password")

        assert result.success is True
        assert result.user == mock_user

    @pytest.mark.asyncio
    @patch("app.services.auth_providers.local_provider.verify_password")
    async def test_authenticate_invalid_password(self, mock_verify_password):
        """Test authentication with invalid password"""
        mock_verify_password.return_value = False

        mock_db = AsyncMock()

        class MockUser:
            def __init__(self):
                self.id = 1
                self.username = "testuser"
                self.email = "test@example.com"
                self.hashed_password = "hashed_password"
                self.is_active = True

        mock_user = MockUser()

        async def mock_execute(*args, **kwargs):
            class MockResult:
                def scalar_one_or_none(self):
                    return mock_user
            return MockResult()

        mock_db.execute = mock_execute

        provider = LocalProvider({"enabled": True}, mock_db)
        result = await provider.authenticate("testuser", "wrong_password")

        assert result.success is False
        assert result.message == "Invalid username or password"

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        """Test authentication when user not found"""
        mock_db = AsyncMock()

        async def mock_execute(*args, **kwargs):
            class MockResult:
                def scalar_one_or_none(self):
                    return None
            return MockResult()

        mock_db.execute = mock_execute

        provider = LocalProvider({"enabled": True}, mock_db)
        result = await provider.authenticate("nonexistent", "password")

        assert result.success is False


class TestLDAPProvider:
    """Test cases for LDAPProvider"""

    @pytest.mark.asyncio
    async def test_authenticate_ldap_not_available(self):
        """Test LDAP authentication when ldap3 module is not available"""
        try:
            import ldap3
            pytest.skip("ldap3 module is available")
        except ImportError:
            pass

        config = {"server": "ldap.example.com", "port": 389, "use_ssl": False}
        provider = LDAPProvider(config, AsyncMock())

        result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert "LDAP module not available" in result.error_message

    @pytest.mark.asyncio
    async def test_test_connection_ldap_not_available(self):
        """Test LDAP connection test when ldap3 module is not available"""
        try:
            import ldap3
            pytest.skip("ldap3 module is available")
        except ImportError:
            pass

        config = {"server": "ldap.example.com", "port": 389, "use_ssl": False}
        provider = LDAPProvider(config, AsyncMock())

        result = await provider.test_connection()
        assert result["success"] is False


class TestTwoFactorService:
    """Test cases for TwoFactorService"""

    @pytest.mark.asyncio
    @patch("app.services.auth_providers.two_factor_service.EmailService")
    async def test_generate_and_verify_code(self, mock_email_service_class):
        """Test generating and verifying a 2FA code"""
        mock_email_service = AsyncMock()
        mock_email_service_class.return_value = mock_email_service

        service = TwoFactorService()
        user = MagicMock()
        user.email = "test@example.com"

        await service.send_code(user)

        code = service._codes.get(user.email)
        assert code is not None
        assert len(code) == 6

        result = await service.verify_code(user.email, code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_invalid_code(self):
        """Test verifying an invalid code"""
        service = TwoFactorService()
        result = await service.verify_code("test@example.com", "123456")
        assert result is False


class TestAuthProviderFactory:
    """Test cases for AuthProviderFactory"""

    def test_get_provider_class_local(self):
        """Test getting local provider class"""
        provider_class = AuthProviderFactory.get_provider_class("local")
        assert provider_class == LocalProvider

    def test_get_provider_class_ldap(self):
        """Test getting LDAP provider class"""
        provider_class = AuthProviderFactory.get_provider_class("ldap")
        assert provider_class == LDAPProvider

    def test_get_provider_class_invalid(self):
        """Test getting invalid provider class"""
        provider_class = AuthProviderFactory.get_provider_class("invalid")
        assert provider_class is None

    @pytest.mark.asyncio
    async def test_create_provider(self):
        """Test creating a provider instance"""
        mock_db = AsyncMock()
        provider = await AuthProviderFactory.create_provider("local", {"enabled": True}, mock_db)
        assert isinstance(provider, LocalProvider)
