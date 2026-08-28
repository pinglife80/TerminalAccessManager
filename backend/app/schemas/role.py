from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PermissionResponse(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_default: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    permissions: list[str] = []  # permission codes

    model_config = ConfigDict(from_attributes=True)


class RoleDetailResponse(RoleResponse):
    user_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="Role name")
    description: str | None = Field(None, max_length=200, description="Role description")
    permission_ids: list[int] = Field(default_factory=list, description="Permission IDs to assign")


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=50, description="Role name (only for custom roles)")
    description: str | None = Field(None, max_length=200, description="Role description")
    permission_ids: list[int] | None = Field(None, description="Permission IDs to assign (replaces all)")


class UserRoleUpdate(BaseModel):
    role_id: int = Field(..., description="Role ID to assign to user")


class RoleUserResponse(BaseModel):
    """Schema for user info returned by role users endpoint"""
    id: int
    username: str
    email: str | None = None
    is_active: bool = True
    is_superuser: bool = False

    model_config = ConfigDict(from_attributes=True)
