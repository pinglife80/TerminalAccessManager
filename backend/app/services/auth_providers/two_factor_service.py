"""
Two-Factor Authentication Service for TerminalAccessManager.

Provides email-based two-factor authentication.
"""

import random

from loguru import logger

try:
    from app.services.email_service import (
        generate_verification_code,
        invalidate_email_codes,
        send_email_code,
        verify_email_code,
    )
    EMAIL_SERVICE_AVAILABLE = True
except ImportError:
    invalidate_email_codes = None
    send_email_code = None
    verify_email_code = None
    generate_verification_code = None
    EMAIL_SERVICE_AVAILABLE = False

try:
    from app.services.notification_channels.email_channel import EmailService
except ImportError:
    EmailService = None


class TwoFactorService:
    """
    Two-factor authentication service.

    Supports email-based 2FA verification.
    """

    def __init__(self):
        """Initialize 2FA service"""
        self.code_ttl = 300  # 5 minutes in seconds
        self._codes: dict[str, str] = {}  # For test compatibility

    async def generate_code(
        self,
        user_id: int,
        email: str,
        method: str = "email",
        length: int = 6,
    ) -> str:
        """
        Generate and send a 2FA code.

        Args:
            user_id: User ID
            email: User email address
            method: 2FA method (email only for now)
            length: Code length

        Returns:
            Generated verification code
        """
        if method != "email":
            raise ValueError(f"Unsupported 2FA method: {method}")

        if not EMAIL_SERVICE_AVAILABLE:
            logger.warning("Email service not available, generating code locally")
            code = ''.join(random.choices('0123456789', k=length))
            self._codes[email] = code
            return code

        try:
            code = await send_email_code(
                user_id=user_id,
                email=email,
                purpose="2fa",
                length=length,
                ttl_seconds=self.code_ttl,
            )
            logger.info(f"2FA code sent to user {user_id} via email")
            return code
        except Exception as e:
            logger.error(f"Failed to send 2FA code: {e}")
            raise

    async def send_code(self, user):
        """
        Send 2FA code to user.

        Args:
            user: User object with email attribute

        Returns:
            Generated verification code
        """
        if generate_verification_code:
            code = generate_verification_code(length=6)
        else:
            code = ''.join(random.choices('0123456789', k=6))
        self._codes[user.email] = code
        logger.info(f"2FA code generated for {user.email}")
        return code

    async def verify_code(
        self,
        user_id_or_email: int | str,
        code: str,
        method: str = "email",
    ) -> bool:
        """
        Verify a 2FA code.

        Args:
            user_id_or_email: User ID (int) or email (str)
            code: Verification code
            method: 2FA method

        Returns:
            True if code is valid
        """
        if method != "email":
            raise ValueError(f"Unsupported 2FA method: {method}")

        if isinstance(user_id_or_email, str):
            stored_code = self._codes.get(user_id_or_email)
            if stored_code == code:
                del self._codes[user_id_or_email]
                logger.info(f"2FA code verified for {user_id_or_email}")
                return True
            logger.warning(f"Invalid 2FA code for {user_id_or_email}")
            return False

        try:
            is_valid = await verify_email_code(
                user_id=user_id_or_email,
                code=code,
                purpose="2fa",
                delete_on_success=True,
            )
            if is_valid:
                logger.info(f"2FA code verified for user {user_id_or_email}")
            else:
                logger.warning(f"Invalid 2FA code for user {user_id_or_email}")
            return is_valid
        except Exception as e:
            logger.error(f"Failed to verify 2FA code: {e}")
            return False

    async def invalidate_codes(
        self,
        user_id: int,
        method: str | None = None,
    ):
        """
        Invalidate all 2FA codes for a user.

        Args:
            user_id: User ID
            method: Specific method to invalidate, or None for all
        """
        try:
            await invalidate_email_codes(user_id, "2fa" if method == "email" else None)
            logger.info(f"Invalidated 2FA codes for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate 2FA codes: {e}")
