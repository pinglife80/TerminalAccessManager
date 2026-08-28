"""Unit tests for authentication providers"""
import os
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Test imports must come after setting environment
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-for-testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
from app.models.user import User
from app.services.auth_providers import ldap_provider as ldap_mod
from app.services.auth_providers.base import AuthResult
from app.services.auth_providers.ldap_provider import (
    LDAPBindError,
    LDAPException,
    LDAPProvider,
    escape_ldap_special_chars,
    validate_username,
)
from app.services.auth_providers.local_provider import LocalProvider
from app.services.auth_providers.provider_factory import AuthProviderFactory
from app.services.auth_providers.two_factor_service import TwoFactorService

LDAP_CONNECTION = "app.services.auth_providers.ldap_provider.Connection"


def _ldap_entry(dn, attrs):
    """Build a mock ldap3 entry."""
    entry = MagicMock()
    entry.entry_dn = dn
    entry.entry_attributes_as_dict = attrs
    return entry


def _ldap_conn(entries):
    """Build a mock ldap3 Connection with the given entries."""
    conn = MagicMock()
    conn.entries = entries
    return conn


def _db_result(scalar=None):
    """Build a mock SQLAlchemy result exposing scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    return result


def _scalars_result(items):
    """Build a mock SQLAlchemy result exposing scalars().all()."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _factory_db(execute=None):
    """Build a mock AsyncSession with sync add + async execute/commit/refresh."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    if isinstance(execute, list):
        db.execute.side_effect = execute
    elif execute is not None:
        db.execute.return_value = execute
    return db


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

    @staticmethod
    def _db(scalar=None):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = scalar
        db.execute = AsyncMock(return_value=result)
        return db

    @staticmethod
    def _user(**overrides):
        user = MagicMock()
        user.id = overrides.get("id", 1)
        user.username = overrides.get("username", "testuser")
        user.email = overrides.get("email", "test@example.com")
        user.hashed_password = overrides.get("hashed_password", "hashed_password")
        user.is_active = overrides.get("is_active", True)
        user.is_superuser = overrides.get("is_superuser", False)
        user.created_at = overrides.get("created_at")
        return user

    @pytest.mark.asyncio
    @patch("app.services.auth_providers.local_provider.verify_password")
    async def test_authenticate_success(self, mock_verify_password):
        """Test successful local authentication"""
        mock_verify_password.return_value = True
        user = self._user()
        provider = LocalProvider({"enabled": True}, self._db(scalar=user))
        result = await provider.authenticate("testuser", "correct_password")

        assert result.success is True
        assert result.user is user
        assert result.requires_2fa is False
        assert result.provider_user_id == str(user.id)

    @pytest.mark.asyncio
    @patch("app.services.auth_providers.local_provider.verify_password")
    async def test_authenticate_success_require_2fa(self, mock_verify_password):
        """Test successful authentication with 2FA required"""
        mock_verify_password.return_value = True
        user = self._user()
        provider = LocalProvider({"require_2fa": True}, self._db(scalar=user))
        result = await provider.authenticate("testuser", "correct_password")

        assert result.success is True
        assert result.requires_2fa is True

    @pytest.mark.asyncio
    async def test_authenticate_empty_username(self):
        """Test authentication with empty username"""
        provider = LocalProvider({}, AsyncMock())
        result = await provider.authenticate("", "password")
        assert result.success is False
        assert result.error_message == "Username and password are required"

    @pytest.mark.asyncio
    async def test_authenticate_empty_password(self):
        """Test authentication with empty password"""
        provider = LocalProvider({}, AsyncMock())
        result = await provider.authenticate("testuser", "")
        assert result.success is False
        assert result.error_message == "Username and password are required"

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        """Test authentication when user not found"""
        provider = LocalProvider({"enabled": True}, self._db(scalar=None))
        result = await provider.authenticate("nonexistent", "password")
        assert result.success is False
        assert result.error_message == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_authenticate_disabled(self):
        """Test authentication disabled account"""
        user = self._user(is_active=False)
        provider = LocalProvider({"enabled": True}, self._db(scalar=user))
        result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert result.error_message == "Account is disabled"

    @pytest.mark.asyncio
    @patch("app.services.auth_providers.local_provider.verify_password")
    async def test_authenticate_invalid_password(self, mock_verify_password):
        """Test authentication with invalid password"""
        mock_verify_password.return_value = False
        user = self._user()
        provider = LocalProvider({"enabled": True}, self._db(scalar=user))
        result = await provider.authenticate("testuser", "wrong_password")

        assert result.success is False
        assert result.error_message == "Invalid credentials"
        assert result.message == "Invalid username or password"

    @pytest.mark.asyncio
    async def test_authenticate_exception(self):
        """Test authentication database exception"""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        provider = LocalProvider({"enabled": True}, db)
        result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert result.error_message == "Authentication failed: boom"

    @pytest.mark.asyncio
    async def test_get_user_info_success(self):
        """Test get_user_info with found user"""
        user = self._user()
        user.created_at = MagicMock()
        user.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        provider = LocalProvider({"enabled": True}, self._db(scalar=user))
        info = await provider.get_user_info("1")

        assert info["id"] == 1
        assert info["username"] == "testuser"
        assert info["email"] == "test@example.com"
        assert info["is_active"] is True
        assert info["is_superuser"] is False
        assert info["created_at"] == "2024-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_get_user_info_no_created_at(self):
        """Test get_user_info with missing created_at"""
        user = self._user(created_at=None)
        provider = LocalProvider({"enabled": True}, self._db(scalar=user))
        info = await provider.get_user_info("1")
        assert info["created_at"] is None

    @pytest.mark.asyncio
    async def test_get_user_info_not_found(self):
        """Test get_user_info when user not found"""
        provider = LocalProvider({"enabled": True}, self._db(scalar=None))
        info = await provider.get_user_info("999")
        assert info == {"error": "User not found"}

    @pytest.mark.asyncio
    async def test_get_user_info_invalid_id(self):
        """Test get_user_info with non-integer user id"""
        provider = LocalProvider({"enabled": True}, self._db(scalar=None))
        info = await provider.get_user_info("not-an-int")
        assert "error" in info

    @pytest.mark.asyncio
    async def test_get_user_info_exception(self):
        """Test get_user_info database exception"""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        provider = LocalProvider({"enabled": True}, db)
        info = await provider.get_user_info("1")
        assert info == {"error": "boom"}

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """Test test_connection success"""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        provider = LocalProvider({"enabled": True}, db)
        result = await provider.test_connection()
        assert result["success"] is True
        assert "successful" in result["message"]

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """Test test_connection failure"""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        provider = LocalProvider({"enabled": True}, db)
        result = await provider.test_connection()
        assert result["success"] is False
        assert "Database connection failed" in result["message"]


class TestLDAPUtils:
    """Test cases for module-level LDAP utility functions"""

    def test_escape_empty(self):
        assert escape_ldap_special_chars("") == ""

    def test_escape_plain(self):
        assert escape_ldap_special_chars("john") == "john"

    def test_escape_special_chars(self):
        assert escape_ldap_special_chars("*") == "\\2a"
        assert escape_ldap_special_chars("(") == "\\28"
        assert escape_ldap_special_chars(")") == "\\29"
        assert escape_ldap_special_chars("\\") == "\\5c"
        assert escape_ldap_special_chars("a*b(c)") == "a\\2ab\\28c\\29"

    def test_escape_control_and_non_ascii(self):
        assert escape_ldap_special_chars("a\x01b") == "a\\01b"
        assert escape_ldap_special_chars("é") == "\\e9"

    def test_validate_username_valid(self):
        assert validate_username("john") is True
        assert validate_username("john.doe") is True
        assert validate_username("test_user-1") is True
        assert validate_username("a@b.com") is True

    def test_validate_username_invalid(self):
        assert validate_username("") is False
        assert validate_username("john doe") is False
        assert validate_username("john*") is False
        assert validate_username("(x)") is False
        assert validate_username("x/y") is False
        assert validate_username("中文") is False


class TestLDAPProviderConfig:
    """Test cases for LDAP provider configuration validation"""

    def test_validate_config_missing_server(self):
        with pytest.raises(ValueError, match="requires 'server'"):
            LDAPProvider({}, None)

    def test_validate_config_empty_server(self):
        with pytest.raises(ValueError, match="requires 'server'"):
            LDAPProvider({"server": ""}, None)

    def test_validate_config_ok(self):
        provider = LDAPProvider({"server": "ldap.example.com"}, None)
        assert provider.config["server"] == "ldap.example.com"

    def test_build_server_basic(self):
        provider = LDAPProvider({"server": "ldap.example.com", "port": 389})
        with patch("app.services.auth_providers.ldap_provider.Server") as mock_server, \
             patch("app.services.auth_providers.ldap_provider.Tls") as mock_tls:
            provider._build_server()
            mock_tls.assert_not_called()
            kwargs = mock_server.call_args.kwargs
            assert kwargs["use_ssl"] is False
            assert kwargs["tls"] is None
            assert kwargs["get_info"] == ldap_mod.ldap3.ALL

    def test_build_server_no_get_info(self):
        provider = LDAPProvider({"server": "ldap.example.com"})
        with patch("app.services.auth_providers.ldap_provider.Server") as mock_server:
            provider._build_server(get_info=False)
            assert mock_server.call_args.kwargs["get_info"] == ldap_mod.ldap3.NONE

    def test_build_server_ssl_skip_verify(self):
        provider = LDAPProvider(
            {"server": "ldap.example.com", "use_ssl": True, "skip_cert_verify": True}
        )
        with patch("app.services.auth_providers.ldap_provider.Server"), \
             patch("app.services.auth_providers.ldap_provider.Tls") as mock_tls:
            provider._build_server()
            kwargs = mock_tls.call_args.kwargs
            assert kwargs["validate"] == ssl.CERT_NONE
            assert kwargs["version"] == ssl.PROTOCOL_TLS

    def test_build_server_starttls_verify(self):
        provider = LDAPProvider({"server": "ldap.example.com", "use_starttls": True})
        with patch("app.services.auth_providers.ldap_provider.Server"), \
             patch("app.services.auth_providers.ldap_provider.Tls") as mock_tls:
            provider._build_server()
            assert mock_tls.call_args.kwargs["validate"] == ssl.CERT_REQUIRED


class TestLDAPProviderAuthenticate:
    """Test cases for LDAPProvider.authenticate"""

    def _provider(self, **cfg):
        cfg.setdefault("server", "ldap.example.com")
        return LDAPProvider(cfg, AsyncMock())

    @pytest.mark.asyncio
    async def test_authenticate_ldap_not_available(self):
        provider = self._provider()
        with patch("app.services.auth_providers.ldap_provider.LDAP_AVAILABLE", False):
            result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert result.error_message == "LDAP module not available"

    @pytest.mark.asyncio
    async def test_authenticate_empty_username(self):
        provider = self._provider()
        result = await provider.authenticate("", "password")
        assert result.success is False
        assert result.error_message == "Username and password are required"

    @pytest.mark.asyncio
    async def test_authenticate_empty_password(self):
        provider = self._provider()
        result = await provider.authenticate("testuser", "")
        assert result.success is False
        assert result.error_message == "Username and password are required"

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch.object(provider, "_search_user_dn", return_value="cn=test,dc=example,dc=com") as mock_search, \
             patch.object(provider, "_get_user_info_from_ldap", return_value={"email": "test@example.com", "raw": {}}), \
             patch.object(provider, "_is_user_active", return_value=True), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            result = await provider.authenticate("testuser", "password")

        assert result.success is True
        assert result.username == "testuser"
        assert result.email == "test@example.com"
        assert result.provider_user_id == "cn=test,dc=example,dc=com"
        assert result.message == "Success"
        mock_search.assert_called_once_with("testuser")
        mock_conn_cls.return_value.unbind.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_disabled_user(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch.object(provider, "_search_user_dn", return_value="cn=test"), \
             patch.object(provider, "_get_user_info_from_ldap", return_value={"email": "test@example.com"}), \
             patch.object(provider, "_is_user_active", return_value=False), \
             patch(LDAP_CONNECTION):
            result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert result.error_message == "User account is disabled"

    @pytest.mark.asyncio
    async def test_authenticate_bind_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch.object(provider, "_search_user_dn", side_effect=LDAPBindError("bad creds")), \
             patch(LDAP_CONNECTION):
            result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert result.error_message == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_authenticate_ldap_exception(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch.object(provider, "_search_user_dn", side_effect=LDAPException("boom")), \
             patch(LDAP_CONNECTION):
            result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert result.error_message == "LDAP error: boom"

    @pytest.mark.asyncio
    async def test_authenticate_value_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch.object(provider, "_search_user_dn", side_effect=ValueError("Invalid username format")), \
             patch(LDAP_CONNECTION):
            result = await provider.authenticate("bad*user", "password")
        assert result.success is False
        assert result.error_message == "Invalid username format"

    @pytest.mark.asyncio
    async def test_authenticate_unexpected_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch.object(provider, "_search_user_dn", side_effect=RuntimeError("boom")), \
             patch(LDAP_CONNECTION):
            result = await provider.authenticate("testuser", "password")
        assert result.success is False
        assert result.error_message == "Authentication failed: boom"


class TestLDAPProviderSearchDN:
    """Test cases for LDAPProvider._search_user_dn"""

    def _provider(self, **cfg):
        cfg.setdefault("server", "ldap.example.com")
        return LDAPProvider(cfg, AsyncMock())

    def test_search_invalid_username(self):
        provider = self._provider()
        with pytest.raises(ValueError, match="Invalid username format"):
            provider._search_user_dn("bad*name")

    def test_search_direct_dn_pattern(self):
        provider = self._provider(user_dn_pattern="uid={username},dc=example,dc=com")
        result = provider._search_user_dn("john")
        assert result == "uid=john,dc=example,dc=com"

    def test_search_anonymous_with_bind(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            anonymous_search=True,
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        entry = _ldap_entry("cn=john,dc=example,dc=com", {})
        conn = _ldap_conn([entry])
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider._search_user_dn("john")
        assert result == "cn=john,dc=example,dc=com"
        assert mock_conn_cls.call_args.kwargs["user"] == "cn=admin,dc=example,dc=com"

    def test_search_anonymous_without_bind(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com", anonymous_search=True
        )
        entry = _ldap_entry("cn=john,dc=example,dc=com", {})
        conn = _ldap_conn([entry])
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider._search_user_dn("john")
        assert result == "cn=john,dc=example,dc=com"
        assert mock_conn_cls.call_args.kwargs["authentication"] == ldap_mod.ldap3.ANONYMOUS

    def test_search_bind_dn_without_password(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com", bind_dn="cn=admin,dc=example,dc=com"
        )
        with patch.object(provider, "_build_server", return_value=MagicMock()):
            with pytest.raises(ValueError, match="bind_password is missing"):
                provider._search_user_dn("john")

    def test_search_no_bind_dn_anonymous(self):
        provider = self._provider(user_search_base="dc=example,dc=com")
        entry = _ldap_entry("cn=john,dc=example,dc=com", {})
        conn = _ldap_conn([entry])
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider._search_user_dn("john")
        assert result == "cn=john,dc=example,dc=com"
        assert mock_conn_cls.call_args.kwargs["user"] is None

    def test_search_with_bind(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        entry = _ldap_entry("cn=john,dc=example,dc=com", {})
        conn = _ldap_conn([entry])
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider._search_user_dn("john")
        assert result == "cn=john,dc=example,dc=com"
        assert mock_conn_cls.call_args.kwargs["user"] == "cn=admin,dc=example,dc=com"

    def test_search_user_not_found(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        conn = _ldap_conn([])
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            with pytest.raises(ValueError, match="User not found"):
                provider._search_user_dn("john")


class TestLDAPProviderHelpers:
    """Test cases for LDAP provider helper methods"""

    def _provider(self, **cfg):
        cfg.setdefault("server", "ldap.example.com")
        return LDAPProvider(cfg, AsyncMock())

    def test_get_user_info_empty(self):
        provider = self._provider()
        conn = _ldap_conn([])
        assert provider._get_user_info_from_ldap(conn, "cn=test") == {}

    def test_get_user_info_with_attrs(self):
        provider = self._provider()
        entry = _ldap_entry(
            "cn=test,dc=example,dc=com",
            {"mail": ["test@example.com"], "sAMAccountName": ["testuser"]},
        )
        conn = _ldap_conn([entry])
        info = provider._get_user_info_from_ldap(conn, "cn=test,dc=example,dc=com")
        assert info["email"] == "test@example.com"
        assert info["username"] == "testuser"
        assert info["dn"] == "cn=test,dc=example,dc=com"

    def test_get_user_info_custom_attrs(self):
        provider = self._provider(email_attribute="email", username_attribute="uid")
        entry = _ldap_entry("cn=test", {"email": ["a@b.c"], "uid": ["abc"]})
        conn = _ldap_conn([entry])
        info = provider._get_user_info_from_ldap(conn, "cn=test")
        assert info["email"] == "a@b.c"
        assert info["username"] == "abc"

    def test_get_user_info_missing_attrs(self):
        provider = self._provider()
        entry = _ldap_entry("cn=test", {})
        conn = _ldap_conn([entry])
        info = provider._get_user_info_from_ldap(conn, "cn=test")
        assert info["email"] is None
        assert info["username"] is None

    def test_is_user_active_default(self):
        provider = self._provider()
        assert provider._is_user_active({"raw": {}}) is True
        assert provider._is_user_active({"raw": {"userAccountControl": [512]}}) is True

    def test_is_user_active_disabled(self):
        provider = self._provider()
        # ACCOUNTDISABLE flag (2) combined with NORMAL_ACCOUNT (512) = 514
        assert provider._is_user_active({"raw": {"userAccountControl": [514]}}) is False


class TestLDAPProviderConnectionMethods:
    """Test cases for get_user_info / test_connection / get_user_info_by_dn / get_ous"""

    def _provider(self, **cfg):
        cfg.setdefault("server", "ldap.example.com")
        return LDAPProvider(cfg, AsyncMock())

    @pytest.mark.asyncio
    async def test_get_user_info_bind_no_password(self):
        provider = self._provider(bind_dn="cn=admin,dc=example,dc=com")
        with patch.object(provider, "_build_server", return_value=MagicMock()):
            result = await provider.get_user_info("cn=test")
        assert result == {"error": "bind_dn is set but bind_password is missing"}

    @pytest.mark.asyncio
    async def test_get_user_info_success(self):
        provider = self._provider(
            bind_dn="cn=admin,dc=example,dc=com", bind_password="secret"
        )
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls, \
             patch.object(provider, "_get_user_info_from_ldap", return_value={"email": "a@b.c"}):
            result = await provider.get_user_info("cn=test")
        assert result == {"email": "a@b.c"}
        assert mock_conn_cls.call_args.kwargs["user"] == "cn=admin,dc=example,dc=com"

    @pytest.mark.asyncio
    async def test_get_user_info_exception(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", side_effect=RuntimeError("boom")):
            result = await provider.get_user_info("cn=test")
        assert result == {"error": "boom"}

    @pytest.mark.asyncio
    async def test_get_user_info_anonymous(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls, \
             patch.object(provider, "_get_user_info_from_ldap", return_value={"email": "a@b.c"}):
            result = await provider.get_user_info("cn=test")
        assert result == {"email": "a@b.c"}
        assert mock_conn_cls.call_args.kwargs["authentication"] == ldap_mod.ldap3.ANONYMOUS

    @pytest.mark.asyncio
    async def test_test_connection_success_anonymous(self):
        provider = self._provider(anonymous_search=True)
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            result = await provider.test_connection()
        assert result["success"] is True
        assert "ldap.example.com" in result["message"]
        mock_conn_cls.return_value.unbind.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_bind_no_password(self):
        provider = self._provider(bind_dn="cn=admin,dc=example,dc=com")
        with patch.object(provider, "_build_server", return_value=MagicMock()):
            result = await provider.test_connection()
        assert result["success"] is False
        assert "bind_password" in result["message"]

    @pytest.mark.asyncio
    async def test_test_connection_success_with_bind(self):
        provider = self._provider(
            bind_dn="cn=admin,dc=example,dc=com", bind_password="secret"
        )
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            result = await provider.test_connection()
        assert result["success"] is True
        assert mock_conn_cls.call_args.kwargs["user"] == "cn=admin,dc=example,dc=com"

    @pytest.mark.asyncio
    async def test_test_connection_anonymous_no_bind(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            result = await provider.test_connection()
        assert result["success"] is True
        assert mock_conn_cls.call_args.kwargs["authentication"] == ldap_mod.ldap3.ANONYMOUS

    @pytest.mark.asyncio
    async def test_test_connection_bind_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", side_effect=LDAPBindError("boom")):
            result = await provider.test_connection()
        assert result["success"] is False
        assert "bind" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_test_connection_ldap_exception(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", side_effect=LDAPException("boom")):
            result = await provider.test_connection()
        assert result["success"] is False
        assert "LDAP connection failed" in result["message"]

    @pytest.mark.asyncio
    async def test_test_connection_generic_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", side_effect=RuntimeError("boom")):
            result = await provider.test_connection()
        assert result["success"] is False
        assert "Connection test failed" in result["message"]

    def test_get_user_info_by_dn_bind_no_password(self):
        provider = self._provider(bind_dn="cn=admin,dc=example,dc=com")
        with patch.object(provider, "_build_server", return_value=MagicMock()):
            result = provider.get_user_info_by_dn("cn=test")
        assert result == {"error": "bind_dn is set but bind_password is missing"}

    def test_get_user_info_by_dn_success(self):
        provider = self._provider(
            bind_dn="cn=admin,dc=example,dc=com", bind_password="secret"
        )
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION), \
             patch.object(provider, "_get_user_info_from_ldap", return_value={"email": "a@b.c"}):
            result = provider.get_user_info_by_dn("cn=test")
        assert result == {"email": "a@b.c"}

    def test_get_user_info_by_dn_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", side_effect=RuntimeError("boom")):
            result = provider.get_user_info_by_dn("cn=test")
        assert result == {}

    def test_get_user_info_by_dn_anonymous(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls, \
             patch.object(provider, "_get_user_info_from_ldap", return_value={"email": "a@b.c"}):
            result = provider.get_user_info_by_dn("cn=test")
        assert result == {"email": "a@b.c"}
        assert mock_conn_cls.call_args.kwargs["authentication"] == ldap_mod.ldap3.ANONYMOUS

    def test_get_ous_no_base(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION):
            assert provider.get_ous() == []

    def test_get_ous_bind_no_password(self):
        provider = self._provider(bind_dn="cn=admin,dc=example,dc=com")
        with patch.object(provider, "_build_server", return_value=MagicMock()):
            assert provider.get_ous() == []

    def test_get_ous_success(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        entry = _ldap_entry("ou=Sales,dc=example,dc=com", {"ou": ["Sales"], "description": ["Sales OU"]})
        conn = _ldap_conn([entry])
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider.get_ous()
        assert len(result) == 1
        assert result[0]["name"] == "Sales"
        assert result[0]["dn"] == "ou=Sales,dc=example,dc=com"

    def test_get_ous_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", side_effect=RuntimeError("boom")):
            assert provider.get_ous() == []


class TestLDAPProviderSearchUsers:
    """Test cases for LDAPProvider.search_users"""

    def _provider(self, **cfg):
        cfg.setdefault("server", "ldap.example.com")
        return LDAPProvider(cfg, AsyncMock())

    def test_search_no_base(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION):
            result = provider.search_users()
        assert result == {"users": [], "total": 0}

    def test_search_bind_no_password(self):
        provider = self._provider(bind_dn="cn=admin,dc=example,dc=com")
        with patch.object(provider, "_build_server", return_value=MagicMock()):
            result = provider.search_users()
        assert result == {"error": "bind_dn is set but bind_password is missing"}

    def test_search_anonymous_with_bind(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            anonymous_search=True,
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        conn = _ldap_conn(self._make_entries(1))
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider.search_users()
        assert result["total"] == 1
        assert mock_conn_cls.call_args.kwargs["user"] == "cn=admin,dc=example,dc=com"

    def test_search_anonymous_without_bind(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com", anonymous_search=True
        )
        conn = _ldap_conn(self._make_entries(1))
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider.search_users()
        assert result["total"] == 1
        assert mock_conn_cls.call_args.kwargs["authentication"] == ldap_mod.ldap3.ANONYMOUS

    def _make_entries(self, count):
        entries = []
        for i in range(count):
            entries.append(
                _ldap_entry(
                    f"cn=user{i},dc=example,dc=com",
                    {
                        "cn": [f"User {i}"],
                        "sAMAccountName": [f"user{i}"],
                        "mail": [f"user{i}@example.com"],
                        "givenName": ["Given"],
                        "sn": ["Sn"],
                    },
                )
            )
        return entries

    def test_search_with_results(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        conn = _ldap_conn(self._make_entries(3))
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider.search_users()
        assert result["total"] == 3
        assert len(result["users"]) == 3
        assert result["users"][0]["username"] == "user0"
        assert result["users"][0]["email"] == "user0@example.com"

    def test_search_with_username(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        conn = _ldap_conn(self._make_entries(2))
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider.search_users(username="user")
        assert result["total"] == 2
        search_filter = mock_conn_cls.return_value.search.call_args.kwargs["search_filter"]
        assert "sAMAccountName" in search_filter
        assert "*user*" in search_filter

    def test_search_with_custom_filter(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        conn = _ldap_conn(self._make_entries(1))
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider.search_users(search_base="dc=example,dc=com", search_filter="(objectClass=person)")
        assert result["total"] == 1
        search_filter = mock_conn_cls.return_value.search.call_args.kwargs["search_filter"]
        assert "(objectClass=person)" in search_filter

    def test_search_pagination(self):
        provider = self._provider(
            user_search_base="dc=example,dc=com",
            bind_dn="cn=admin,dc=example,dc=com",
            bind_password="secret",
        )
        conn = _ldap_conn(self._make_entries(5))
        with patch.object(provider, "_build_server", return_value=MagicMock()), \
             patch(LDAP_CONNECTION) as mock_conn_cls:
            mock_conn_cls.return_value = conn
            result = provider.search_users(page_size=2, page_number=2)
        assert result["total"] == 5
        assert len(result["users"]) == 2
        assert result["users"][0]["username"] == "user2"

    def test_search_error(self):
        provider = self._provider()
        with patch.object(provider, "_build_server", side_effect=RuntimeError("boom")):
            result = provider.search_users()
        assert result == {"error": "boom"}


class TestTwoFactorService:
    """Test cases for TwoFactorService"""

    def setup_method(self):
        self.service = TwoFactorService()

    @pytest.mark.asyncio
    async def test_generate_code_unsupported_method(self):
        with pytest.raises(ValueError, match="Unsupported 2FA method"):
            await self.service.generate_code(1, "a@b.c", method="sms")

    @pytest.mark.asyncio
    async def test_generate_code_email_unavailable(self):
        with patch("app.services.auth_providers.two_factor_service.EMAIL_SERVICE_AVAILABLE", False):
            code = await self.service.generate_code(1, "a@b.c")
        assert len(code) == 6
        assert code.isdigit()
        assert self.service._codes["a@b.c"] == code

    @pytest.mark.asyncio
    async def test_generate_code_email_available(self):
        with patch("app.services.auth_providers.two_factor_service.send_email_code", new=AsyncMock(return_value="123456")) as mock_send, \
             patch("app.services.event_emitter.emit_verification_code_sent", new=AsyncMock(return_value=[])) as mock_emit:
            code = await self.service.generate_code(1, "a@b.c")
        assert code == "123456"
        mock_send.assert_awaited_once_with(
            user_id=1, email="a@b.c", purpose="2fa", length=6, ttl_seconds=300
        )
        mock_emit.assert_awaited_once_with("a@b.c", "2fa")

    @pytest.mark.asyncio
    async def test_generate_code_email_raises(self):
        with patch("app.services.auth_providers.two_factor_service.send_email_code", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(RuntimeError, match="boom"):
                await self.service.generate_code(1, "a@b.c")

    @pytest.mark.asyncio
    async def test_send_code(self):
        with patch("app.services.auth_providers.two_factor_service.generate_email_code", new=AsyncMock(return_value="654321")) as mock_gen, \
             patch("app.services.event_emitter.emit_verification_code_sent", new=AsyncMock(return_value=[])):
            user = MagicMock()
            user.email = "a@b.c"
            code = await self.service.send_code(user)
        assert code == "654321"
        assert self.service._codes["a@b.c"] == "654321"
        mock_gen.assert_awaited_once_with(length=6)

    @pytest.mark.asyncio
    async def test_send_code_fallback(self):
        with patch("app.services.auth_providers.two_factor_service.generate_email_code", None), \
             patch("app.services.event_emitter.emit_verification_code_sent", new=AsyncMock(return_value=[])):
            user = MagicMock()
            user.email = "a@b.c"
            code = await self.service.send_code(user)
        assert len(code) == 6
        assert self.service._codes["a@b.c"] == code

    @pytest.mark.asyncio
    async def test_verify_code_unsupported_method(self):
        with pytest.raises(ValueError, match="Unsupported 2FA method"):
            await self.service.verify_code("a@b.c", "123456", method="sms")

    @pytest.mark.asyncio
    async def test_verify_code_str_success(self):
        self.service._codes["a@b.c"] = "123456"
        result = await self.service.verify_code("a@b.c", "123456")
        assert result is True
        assert "a@b.c" not in self.service._codes

    @pytest.mark.asyncio
    async def test_verify_code_str_wrong(self):
        self.service._codes["a@b.c"] = "999999"
        result = await self.service.verify_code("a@b.c", "123456")
        assert result is False
        assert self.service._codes["a@b.c"] == "999999"

    @pytest.mark.asyncio
    async def test_verify_code_int_success(self):
        with patch("app.services.auth_providers.two_factor_service.verify_email_code", new=AsyncMock(return_value=True)) as mock_verify:
            result = await self.service.verify_code(1, "123456")
        assert result is True
        mock_verify.assert_awaited_once_with(
            user_id=1, code="123456", purpose="2fa", delete_on_success=True
        )

    @pytest.mark.asyncio
    async def test_verify_code_int_failure(self):
        with patch("app.services.auth_providers.two_factor_service.verify_email_code", new=AsyncMock(return_value=False)):
            result = await self.service.verify_code(1, "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_code_int_exception(self):
        with patch("app.services.auth_providers.two_factor_service.verify_email_code", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await self.service.verify_code(1, "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_codes_email(self):
        with patch("app.services.auth_providers.two_factor_service.invalidate_email_codes", new=AsyncMock()) as mock_invalidate:
            await self.service.invalidate_codes(1, method="email")
        mock_invalidate.assert_awaited_once_with(1, "2fa")

    @pytest.mark.asyncio
    async def test_invalidate_codes_none(self):
        with patch("app.services.auth_providers.two_factor_service.invalidate_email_codes", new=AsyncMock()) as mock_invalidate:
            await self.service.invalidate_codes(1)
        mock_invalidate.assert_awaited_once_with(1, None)

    @pytest.mark.asyncio
    async def test_invalidate_codes_exception(self):
        with patch("app.services.auth_providers.two_factor_service.invalidate_email_codes", new=AsyncMock(side_effect=RuntimeError("boom"))):
            await self.service.invalidate_codes(1)


class TestAuthProviderFactory:
    """Test cases for AuthProviderFactory"""

    def test_get_provider_class_local(self):
        """Test getting local provider class"""
        assert AuthProviderFactory.get_provider_class("local") == LocalProvider

    def test_get_provider_class_ldap(self):
        """Test getting LDAP provider class"""
        assert AuthProviderFactory.get_provider_class("ldap") == LDAPProvider

    def test_get_provider_class_case_insensitive(self):
        """Test provider class lookup is case insensitive"""
        assert AuthProviderFactory.get_provider_class("LOCAL") == LocalProvider

    def test_get_provider_class_invalid(self):
        """Test getting invalid provider class"""
        assert AuthProviderFactory.get_provider_class("invalid") is None

    def test_register_provider(self):
        """Test registering a new provider"""
        class DummyProvider:
            pass

        AuthProviderFactory.register_provider("dummy", DummyProvider)
        try:
            assert AuthProviderFactory.get_provider_class("dummy") == DummyProvider
        finally:
            del AuthProviderFactory._providers["dummy"]

    @pytest.mark.asyncio
    async def test_create_provider_unsupported(self):
        """Test creating an unsupported provider raises"""
        with pytest.raises(ValueError, match="Unsupported authentication provider"):
            await AuthProviderFactory.create_provider("invalid", {}, AsyncMock())

    @pytest.mark.asyncio
    async def test_create_provider_local_with_db(self):
        """Test creating local provider with db session"""
        mock_db = AsyncMock()
        mock_cls = MagicMock()
        with patch.object(AuthProviderFactory, "get_provider_class", return_value=mock_cls):
            provider = await AuthProviderFactory.create_provider("local", {"a": 1}, mock_db)
        mock_cls.assert_called_once_with({"a": 1}, mock_db)
        assert provider == mock_cls.return_value

    @pytest.mark.asyncio
    async def test_create_provider_local_without_db(self):
        """Test creating local provider without db session"""
        mock_cls = MagicMock()
        with patch.object(AuthProviderFactory, "get_provider_class", return_value=mock_cls):
            provider = await AuthProviderFactory.create_provider("local", {"a": 1}, None)
        mock_cls.assert_called_once_with({"a": 1})
        assert provider == mock_cls.return_value

    @pytest.mark.asyncio
    async def test_create_provider_non_local(self):
        """Test creating non-local provider without db session"""
        mock_cls = MagicMock()
        with patch.object(AuthProviderFactory, "get_provider_class", return_value=mock_cls):
            provider = await AuthProviderFactory.create_provider("ldap", {"a": 1}, AsyncMock())
        mock_cls.assert_called_once_with({"a": 1})
        assert provider == mock_cls.return_value

    @pytest.mark.asyncio
    async def test_get_enabled_providers(self):
        """Test getting enabled providers from database"""
        db = _factory_db(execute=_scalars_result([
            MagicMock(provider_type="ldap", config={"server": "ldap.example.com"}),
            MagicMock(provider_type="oauth", config={"client_id": "x"}),
        ]))
        with patch.object(
            AuthProviderFactory, "create_provider",
            new=AsyncMock(side_effect=lambda pt, cfg, d: MagicMock()),
        ) as mock_create:
            providers = await AuthProviderFactory.get_enabled_providers(db)

        assert "local" in providers
        assert isinstance(providers["local"], LocalProvider)
        assert "ldap" in providers
        assert "oauth" in providers
        assert mock_create.await_count == 2

    @pytest.mark.asyncio
    async def test_get_enabled_providers_create_fails(self):
        """Test get_enabled_providers skips failed providers"""
        db = _factory_db(execute=_scalars_result([
            MagicMock(provider_type="bad", config={}),
        ]))
        with patch.object(
            AuthProviderFactory, "create_provider",
            new=AsyncMock(side_effect=ValueError("boom")),
        ):
            providers = await AuthProviderFactory.get_enabled_providers(db)

        assert "local" in providers
        assert "bad" not in providers

    @pytest.mark.asyncio
    async def test_authenticate_failure(self):
        """Test authenticate returns failure result"""
        auth_result = AuthResult(success=False, error_message="Invalid credentials")
        provider = AsyncMock()
        provider.authenticate = AsyncMock(return_value=auth_result)
        with patch.object(AuthProviderFactory, "create_provider", new=AsyncMock(return_value=provider)):
            result = await AuthProviderFactory.authenticate(
                "local", {"username": "u", "password": "p"}, _factory_db()
            )
        assert result == {"success": False, "error_message": "Invalid credentials"}

    @pytest.mark.asyncio
    async def test_authenticate_local_with_user(self):
        """Test authenticate local with auth_result user present"""
        user = MagicMock()
        user.id = 7
        user.username = "u"
        user.email = "u@example.com"
        auth_result = AuthResult(
            success=True, username="u", email="u@example.com",
            user=user, requires_2fa=True,
        )
        provider = AsyncMock()
        provider.authenticate = AsyncMock(return_value=auth_result)
        with patch.object(AuthProviderFactory, "create_provider", new=AsyncMock(return_value=provider)):
            result = await AuthProviderFactory.authenticate(
                "local", {"username": "u", "password": "p"}, _factory_db()
            )
        assert result["success"] is True
        assert result["user"] is user
        assert result["user_id"] == 7
        assert result["requires_2fa"] is True

    @pytest.mark.asyncio
    async def test_authenticate_local_without_user(self):
        """Test authenticate local resolves user by username"""
        existing = MagicMock()
        existing.id = 3
        existing.username = "u"
        existing.email = "u@example.com"
        auth_result = AuthResult(success=True, username="u", user=None)
        provider = AsyncMock()
        provider.authenticate = AsyncMock(return_value=auth_result)
        db = _factory_db(execute=_db_result(existing))
        with patch.object(AuthProviderFactory, "create_provider", new=AsyncMock(return_value=provider)):
            result = await AuthProviderFactory.authenticate(
                "local", {"username": "u", "password": "p"}, db
            )
        assert result["success"] is True
        assert result["user"] is existing
        assert result["user_id"] == 3

    @pytest.mark.asyncio
    async def test_authenticate_non_local_no_config(self):
        """Test authenticate non-local with no stored auth config"""
        user = MagicMock()
        user.id = 9
        auth_result = AuthResult(
            success=True, username="u", provider_user_id="dn", user=user,
        )
        provider = AsyncMock()
        provider.authenticate = AsyncMock(return_value=auth_result)
        db = _factory_db(execute=_db_result(None))
        with patch.object(
            AuthProviderFactory, "create_provider",
            new=AsyncMock(return_value=provider),
        ) as mock_create:
            result = await AuthProviderFactory.authenticate(
                "ldap", {"username": "u", "password": "p"}, db
            )
        mock_create.assert_awaited_once_with("ldap", {}, db)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_authenticate_non_local_existing_user(self):
        """Test authenticate non-local with existing provider user"""
        auth_config = MagicMock()
        auth_config.config = {"server": "ldap"}
        existing = MagicMock()
        existing.id = 11
        existing.username = "u"
        existing.email = "u@example.com"
        auth_result = AuthResult(
            success=True, username="u", provider_user_id="dn", user=None,
        )
        provider = AsyncMock()
        provider.authenticate = AsyncMock(return_value=auth_result)
        db = _factory_db(execute=[_db_result(auth_config), _db_result(existing)])
        with patch.object(AuthProviderFactory, "create_provider", new=AsyncMock(return_value=provider)):
            result = await AuthProviderFactory.authenticate(
                "ldap", {"username": "u", "password": "p"}, db
            )
        assert result["success"] is True
        assert result["user"] is existing
        assert result["user_id"] == 11

    @pytest.mark.asyncio
    async def test_authenticate_non_local_creates_user_with_role(self):
        """Test authenticate non-local auto-creates user and default role"""
        auth_config = MagicMock()
        auth_config.config = {"server": "ldap"}
        default_role = MagicMock()
        default_role.id = 5
        auth_result = AuthResult(
            success=True, username="u", email="u@example.com",
            provider_user_id="dn", user=None,
        )
        provider = AsyncMock()
        provider.authenticate = AsyncMock(return_value=auth_result)
        db = _factory_db(execute=[
            _db_result(auth_config),
            _db_result(None),
            _db_result(default_role),
        ])
        with patch.object(AuthProviderFactory, "create_provider", new=AsyncMock(return_value=provider)):
            result = await AuthProviderFactory.authenticate(
                "ldap", {"username": "u", "password": "p"}, db
            )
        assert result["success"] is True
        assert result["username"] == "u"
        assert result["email"] == "u@example.com"
        assert db.add.call_count == 2  # User + UserRole
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_authenticate_non_local_creates_user_no_role(self):
        """Test authenticate non-local creates user without default role"""
        auth_config = MagicMock()
        auth_config.config = {"server": "ldap"}
        auth_result = AuthResult(
            success=True, username="u", email="u@example.com",
            provider_user_id="dn", user=None,
        )
        provider = AsyncMock()
        provider.authenticate = AsyncMock(return_value=auth_result)
        db = _factory_db(execute=[
            _db_result(auth_config),
            _db_result(None),
            _db_result(None),
        ])
        with patch.object(AuthProviderFactory, "create_provider", new=AsyncMock(return_value=provider)):
            result = await AuthProviderFactory.authenticate(
                "ldap", {"username": "u", "password": "p"}, db
            )
        assert result["success"] is True
        assert db.add.call_count == 1  # User only