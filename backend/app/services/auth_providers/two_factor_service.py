"""
Two-Factor Authentication Service for TerminalAccessManager.

Provides email-based two-factor authentication.
"""

from typing import Optional

from loguru import logger

from app.services.email_service import send_email_code, verify_email_code, invalidate_email_codes


class TwoFactorService:
    """
    Two-factor authentication service.

    Supports email-based 2FA verification.
    """

    def __init__(self):
        """Initialize 2FA service"""
        self.code_ttl = 300  # 5 minutes in seconds

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

    async def verify_code(
        self,
        user_id: int,
        code: str,
        method: str = "email",
    ) -> bool:
        """
        Verify a 2FA code.

        Args:
            user_id: User ID
            code: Verification code
            method: 2FA method

        Returns:
            True if code is valid
        """
        if method != "email":
            raise ValueError(f"Unsupported 2FA method: {method}")

        try:
            is_valid = await verify_email_code(
                user_id=user_id,
                code=code,
                purpose="2fa",
                delete_on_success=True,
            )
            if is_valid:
                logger.info(f"2FA code verified for user {user_id}")
            else:
                logger.warning(f"Invalid 2FA code for user {user_id}")
            return is_valid
        except Exception as e:
            logger.error(f"Failed to verify 2FA code: {e}")
            return False

    async def invalidate_codes(
        self,
        user_id: int,
        method: Optional[str] = None,
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
