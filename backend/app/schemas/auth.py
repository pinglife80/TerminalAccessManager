from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


class UserCreate(BaseModel):
    """Schema for user registration with password validation matching frontend rules"""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: Optional[str] = Field(None, description="Email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password")

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        """Validate password meets complexity requirements:
        - At least 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        """
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    roles: list[str] = []  # role names
    permissions: list[str] = []  # permission codes

    class Config:
        from_attributes = True


class UserDetailResponse(UserResponse):
    """Extended user response with timestamps"""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Schema for updating user info (by admin)"""
    email: Optional[str] = Field(None, description="Email address")
    is_active: Optional[bool] = Field(None, description="Active status")
    is_superuser: Optional[bool] = Field(None, description="Superuser status")
    role_ids: Optional[list[int]] = Field(None, description="Role IDs to assign")


class AdminUserCreate(BaseModel):
    """Schema for admin creating a new user"""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: Optional[str] = Field(None, description="Email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password")
    is_active: bool = Field(True, description="Active status")
    is_superuser: bool = Field(False, description="Superuser status")
    role_ids: list[int] = Field(default_factory=list, description="Role IDs to assign")

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v


class PasswordChange(BaseModel):
    """Schema for changing own password"""
    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v


class AdminPasswordReset(BaseModel):
    """Schema for admin resetting a user's password"""
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v


class ProfileUpdate(BaseModel):
    """Schema for updating own profile"""
    email: Optional[str] = Field(None, description="Email address")


class LoginResponse(BaseModel):
    """Schema for login response with captcha info"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    captcha_required: bool = False
