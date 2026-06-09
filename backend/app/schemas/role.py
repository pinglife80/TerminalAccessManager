from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PermissionResponse(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    permissions: list[str] = []  # permission codes

    class Config:
        from_attributes = True


class RoleDetailResponse(RoleResponse):
    user_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="Role name")
    description: Optional[str] = Field(None, max_length=200, description="Role description")
    permission_ids: list[int] = Field(default_factory=list, description="Permission IDs to assign")


class RoleUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=200, description="Role description")
    permission_ids: Optional[list[int]] = Field(None, description="Permission IDs to assign (replaces all)")


class UserRoleUpdate(BaseModel):
    role_ids: list[int] = Field(..., description="Role IDs to assign to user")
