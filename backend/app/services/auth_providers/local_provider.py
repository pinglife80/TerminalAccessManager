"""
Local Authentication Provider for TerminalAccessManager.

Authenticates users against local database.
"""

from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.user import User
from app.services.auth_providers.base import AuthCredentials, AuthProviderBase, AuthProviderType, AuthResult


class LocalProvider(AuthProviderBase):
    """
    Local authentication provider.

    Authenticates users against the local database.
    """

    provider_type = AuthProviderType.LOCAL
    provider_name = "Local"

    def __init__(self, config: Dict[str, Any], db: AsyncSession):
        """
        Initialize local provider.

        Args:
            config: Provider configuration
            db: Database session
        """
        super().__init__(config)
        self.db = db

    async def authenticate(self, credentials: AuthCredentials) -> AuthResult:
        """Authenticate user against local database"""
        username = credentials.username
        password = credentials.password

        if not username or not password:
            return self.build_auth_result(
                success=False,
                error_message="Username and password are required",
            )

        try:
            # Find user by username or email
            result = await self.db.execute(
                select(User).where(
                    (User.username == username) | (User.email == username)
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                return self.build_auth_result(
                    success=False,
                    error_message="Invalid credentials",
                )

            if not user.is_active:
                return self.build_auth_result(
                    success=False,
                    error_message="Account is disabled",
                )

            if not verify_password(password, user.hashed_password):
                return self.build_auth_result(
                    success=False,
                    error_message="Invalid credentials",
                )

            # Check if 2FA is required
            requires_2fa = self.config.get("require_2fa", False)

            return self.build_auth_result(
                success=True,
                user_id=user.id,
                username=user.username,
                email=user.email,
                provider_user_id=str(user.id),
                requires_2fa=requires_2fa,
            )

        except Exception as e:
            return self.build_auth_result(
                success=False,
                error_message=f"Authentication failed: {str(e)}",
            )

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information from local database"""
        try:
            result = await self.db.execute(
                select(User).where(User.id == int(user_id))
            )
            user = result.scalar_one_or_none()

            if user:
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_superuser": user.is_superuser,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                }
            return {"error": "User not found"}
        except Exception as e:
            return {"error": str(e)}

    async def test_connection(self) -> dict:
        """Test local database connection"""
        try:
            # Test by executing a simple query
            await self.db.execute(select(1))
            return {
                "success": True,
                "message": "Local database connection successful",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Database connection failed: {str(e)}",
            }
