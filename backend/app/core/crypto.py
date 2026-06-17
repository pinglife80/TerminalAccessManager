"""
Field-level encryption utility using Fernet (AES-128-CBC).

Encrypts sensitive fields in DataSource config (passwords, API keys, etc.)
before storing to database, and decrypts on read.

ENCRYPTION_KEY must be set in environment variables for production.
If ENCRYPTION_KEY is not set, SECRET_KEY is used as fallback (development only).
"""

from cryptography.fernet import Fernet
import base64
import os
import hashlib
from loguru import logger
from typing import Any

from app.core.config import settings


def _get_fernet() -> Fernet:
    """Get Fernet cipher from ENCRYPTION_KEY or derive from SECRET_KEY"""
    key_source = getattr(settings, 'ENCRYPTION_KEY', None) or settings.SECRET_KEY
    if not getattr(settings, 'ENCRYPTION_KEY', None):
        logger.warning(
            "ENCRYPTION_KEY is not set. Falling back to SECRET_KEY for field encryption. "
            "This is insecure for production — set ENCRYPTION_KEY to a separate strong key."
        )
    # Derive a valid 32-byte Fernet key from the source
    key_bytes = hashlib.sha256(key_source.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value, returns encrypted string with prefix"""
    f = _get_fernet()
    encrypted = f.encrypt(plaintext.encode())
    return f"ENC:{encrypted.decode()}"


def decrypt_value(ciphertext: str) -> str:
    """Decrypt an encrypted string value"""
    if not ciphertext.startswith("ENC:"):
        # Not encrypted (legacy plaintext), return as-is
        return ciphertext
    f = _get_fernet()
    encrypted = ciphertext[4:]  # Remove "ENC:" prefix
    return f.decrypt(encrypted.encode()).decode()


# Sensitive field names that should be encrypted
SENSITIVE_FIELDS = {"password", "secret", "api_key", "token", "passphrase"}


def encrypt_config(config: dict[str, Any]) -> dict[str, Any]:
    """Encrypt sensitive fields in a config dict"""
    encrypted = {}
    for key, value in config.items():
        if isinstance(value, str) and any(s in key.lower() for s in SENSITIVE_FIELDS):
            encrypted[key] = encrypt_value(value)
        elif isinstance(value, dict):
            encrypted[key] = encrypt_config(value)  # Recurse for nested dicts
        else:
            encrypted[key] = value
    return encrypted


def decrypt_config(config: dict[str, Any]) -> dict[str, Any]:
    """Decrypt sensitive fields in a config dict"""
    decrypted = {}
    for key, value in config.items():
        if isinstance(value, str) and value.startswith("ENC:"):
            decrypted[key] = decrypt_value(value)
        elif isinstance(value, dict):
            decrypted[key] = decrypt_config(value)  # Recurse for nested dicts
        else:
            decrypted[key] = value
    return decrypted
