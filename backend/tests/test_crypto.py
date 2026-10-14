"""Unit tests for field-level encryption utilities (app/core/crypto.py)."""
import pytest

from app.core import crypto


class TestEncryptValue:
    def test_encrypt_returns_enc_prefixed_ciphertext(self):
        result = crypto.encrypt_value("s3cret")
        assert result.startswith("ENC:")
        assert result != "s3cret"

    def test_roundtrip(self):
        plaintext = "my-password-123"
        assert crypto.decrypt_value(crypto.encrypt_value(plaintext)) == plaintext

    def test_decrypt_plaintext_passthrough(self):
        # Legacy plaintext values (no ENC: prefix) should be returned as-is
        assert crypto.decrypt_value("plaintext") == "plaintext"


class TestConfigEncryption:
    def test_encrypt_sensitive_fields(self):
        config = {
            "username": "admin",
            "password": "p@ss",
            "api_token": "t0ken",
        }
        enc = crypto.encrypt_config(config)
        assert enc["username"] == "admin"
        assert enc["password"].startswith("ENC:")
        assert enc["api_token"].startswith("ENC:")

    def test_encrypt_is_case_insensitive_on_key(self):
        enc = crypto.encrypt_config({"API_KEY": "abc"})
        assert enc["API_KEY"].startswith("ENC:")

    def test_encrypt_skips_non_string_values(self):
        enc = crypto.encrypt_config({"port": 443, "enabled": True})
        assert enc["port"] == 443
        assert enc["enabled"] is True

    def test_encrypt_nested_dict(self):
        enc = crypto.encrypt_config({"outer": {"password": "x"}})
        assert enc["outer"]["password"].startswith("ENC:")

    def test_decrypt_config_roundtrip(self):
        original = {"password": "p@ss", "username": "admin", "nested": {"secret": "s"}}
        enc = crypto.encrypt_config(original)
        assert crypto.decrypt_config(enc) == original

    def test_decrypt_config_passthrough_non_encrypted(self):
        assert crypto.decrypt_config({"a": "b", "n": {"c": "d"}}) == {"a": "b", "n": {"c": "d"}}


class TestHasEncryptedConfig:
    def test_true_when_encrypted(self):
        assert crypto.has_encrypted_config({"password": "ENC:xyz"}) is True

    def test_true_when_nested_encrypted(self):
        assert crypto.has_encrypted_config({"nested": {"api_key": "ENC:xyz"}}) is True

    def test_false_when_none(self):
        assert crypto.has_encrypted_config({"password": "plain", "n": {"a": "b"}}) is False


class TestFernetFallback:
    def test_falls_back_to_secret_key_when_encryption_key_missing(self, monkeypatch):
        monkeypatch.setattr(crypto.settings, "ENCRYPTION_KEY", None)
        # Should not raise and should still roundtrip using SECRET_KEY fallback
        assert crypto.decrypt_value(crypto.encrypt_value("s3cret")) == "s3cret"