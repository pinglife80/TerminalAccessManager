"""
Core business logic tests for TerminalAccessManager.
Tests authentication, encryption, and search functionality.
"""

import os
import subprocess
import sys
from unittest.mock import AsyncMock, patch

import pytest

from app.core.crypto import decrypt_config, decrypt_value, encrypt_config, encrypt_value


class TestFieldEncryption:
    """Test field-level encryption for DataSource passwords"""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting should return original value"""
        original = "my_secret_password"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_ciphertext(self):
        """Each encryption should produce different ciphertext (random IV)"""
        original = "same_password"
        enc1 = encrypt_value(original)
        enc2 = encrypt_value(original)
        assert enc1 != enc2  # Different due to random IV
        assert decrypt_value(enc1) == original
        assert decrypt_value(enc2) == original

    def test_encrypted_value_has_prefix(self):
        """Encrypted values should have ENC: prefix"""
        encrypted = encrypt_value("test")
        assert encrypted.startswith("ENC:")

    def test_decrypt_plaintext_passthrough(self):
        """Decrypting plaintext (non-encrypted) values should return as-is"""
        assert decrypt_value("plain_password") == "plain_password"
        assert decrypt_value("") == ""

    def test_encrypt_config_nested(self):
        """Config encryption should handle nested dicts and only encrypt sensitive fields"""
        config = {
            "host": "10.0.1.1",
            "port": 22,
            "username": "admin",
            "password": "secret123",
            "api_key": "key_abc",
            "options": {"timeout": 30, "token": "tok_xyz"}
        }
        encrypted = encrypt_config(config)

        # Non-sensitive fields should be unchanged
        assert encrypted["host"] == "10.0.1.1"
        assert encrypted["port"] == 22
        assert encrypted["username"] == "admin"

        # Sensitive fields should be encrypted
        assert encrypted["password"].startswith("ENC:")
        assert encrypted["api_key"].startswith("ENC:")
        assert encrypted["options"]["token"].startswith("ENC:")

        # Non-sensitive nested fields should be unchanged
        assert encrypted["options"]["timeout"] == 30

        # Decrypt should restore original
        decrypted = decrypt_config(encrypted)
        assert decrypted["password"] == "secret123"
        assert decrypted["api_key"] == "key_abc"
        assert decrypted["options"]["token"] == "tok_xyz"

    def test_decrypt_config_mixed(self):
        """Should handle configs with mixed encrypted and plaintext values"""
        config = {
            "host": "10.0.1.1",
            "password": encrypt_value("my_pass"),
            "token": "plain_token"  # Not encrypted (legacy)
        }
        decrypted = decrypt_config(config)
        assert decrypted["host"] == "10.0.1.1"
        assert decrypted["password"] == "my_pass"
        assert decrypted["token"] == "plain_token"


class TestSecretKeyValidation:
    """Test SECRET_KEY strength validation (production startup)"""

    def _import_config_in_production(self, secret_key: str) -> subprocess.CompletedProcess:
        """Import app.core.config in a subprocess under production env."""
        code = (
            "import os\n"
            "os.environ.update({\n"
            "    'ENVIRONMENT': 'production',\n"
            f"    'SECRET_KEY': {secret_key!r},\n"
            "    'DATABASE_URL': 'sqlite+aiosqlite:///:memory:',\n"
            "    'VERSION': 'test',\n"
            "})\n"
            "import app.core.config\n"
        )
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    def test_short_key_rejected_in_production(self):
        """Short SECRET_KEY (<32) must abort startup in production."""
        result = self._import_config_in_production("short-key")
        assert result.returncode != 0
        assert "too short" in result.stderr

    def test_insecure_default_key_rejected_in_production(self):
        """Known insecure default SECRET_KEY must abort startup in production."""
        import app.core.config as config_module

        insecure = "change-this-to-a-random-secret-key-in-production"
        assert insecure in config_module._INSECURE_DEFAULTS

        result = self._import_config_in_production(insecure)
        assert result.returncode != 0
        assert "insecure default" in result.stderr

    def test_insecure_defaults_list(self):
        """Known insecure default values should be in the blocklist."""
        import app.core.config as config_module

        for value in (
            "change-this-to-a-random-secret-key-in-production",
            "your-secret-key-change-in-production",
            "password",
        ):
            assert value in config_module._INSECURE_DEFAULTS


class TestLoginSecurity:
    """Test login security measures"""

    @pytest.mark.asyncio
    async def test_login_error_messages_are_uniform(self):
        """Both user-not-found and wrong-password return the same error_message."""
        from app.services.auth_providers.local_provider import LocalProvider

        class _NoUserResult:
            def scalar_one_or_none(self):
                return None

        db1 = AsyncMock()
        db1.execute = AsyncMock(return_value=_NoUserResult())
        not_found = await LocalProvider({"enabled": True}, db1).authenticate("nobody", "pw")
        assert not_found.error_message == "Invalid credentials"

        class _User:
            id = 1
            username = "u"
            email = "u@example.com"
            hashed_password = "x"
            is_active = True

        class _UserResult:
            def scalar_one_or_none(self):
                return _User()

        db2 = AsyncMock()
        db2.execute = AsyncMock(return_value=_UserResult())
        with patch("app.services.auth_providers.local_provider.verify_password", return_value=False):
            wrong_pw = await LocalProvider({"enabled": True}, db2).authenticate("u", "bad")
        assert wrong_pw.error_message == "Invalid credentials"

    def test_like_wildcard_escaping(self):
        """LIKE wildcard characters should be properly escaped"""
        from app.services.terminal_service import _escape_like

        # % and _ should be escaped
        assert _escape_like("test%value") == "test\\%value"
        assert _escape_like("test_value") == "test\\_value"
        assert _escape_like("test\\%value") == "test\\\\\\%value"
        assert _escape_like("100%") == "100\\%"
        assert _escape_like("a_b%c") == "a\\_b\\%c"

    @pytest.mark.asyncio
    async def test_token_version_default(self):
        """get_token_version returns 0 for an unknown user (no cached version)."""
        from app.core.security import get_token_version

        assert await get_token_version(999999) == 0
