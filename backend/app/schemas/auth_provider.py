"""
Authentication Provider Schemas for TerminalAccessManager.

Pydantic models for authentication provider configuration.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuthProviderBase(BaseModel):
    """Base schema for authentication provider"""

    name: str = Field(..., min_length=1, max_length=100)
    provider_type: str = Field(..., description="Provider type: local, ldap")
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = Field(100, ge=1, le=1000, description="Lower number = higher priority")
    description: str | None = None


class AuthProviderCreate(AuthProviderBase):
    """Schema for creating an authentication provider"""

    pass


class AuthProviderUpdate(BaseModel):
    """Schema for updating an authentication provider"""

    name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    priority: int | None = None
    description: str | None = None


class AuthProviderResponse(AuthProviderBase):
    """Schema for authentication provider response"""

    id: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthProviderListResponse(BaseModel):
    """Schema for authentication provider list"""

    providers: list[AuthProviderResponse]


class AuthTestResult(BaseModel):
    """Schema for authentication test result"""

    success: bool
    message: str
    details: dict[str, Any] | None = None


class LoginRequest(BaseModel):
    """Schema for login request"""

    username: str
    password: str
    provider: str | None = Field("local", description="Authentication provider type")
    remember_me: bool = False


class LoginResponse(BaseModel):
    """Schema for login response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict[str, Any]
    requires_2fa: bool = False


class TwoFactorRequest(BaseModel):
    """Schema for 2FA verification request"""

    user_id: int
    code: str
    method: str = "email"


class TwoFactorResponse(BaseModel):
    """Schema for 2FA verification response"""

    success: bool
    message: str
    access_token: str | None = None
    refresh_token: str | None = None
