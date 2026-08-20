from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ScopeType = Literal["ip_cidr", "ip_range", "mac_prefix"]


class ComplianceScopeBase(BaseModel):
    scope_type: ScopeType = Field(..., description="Scope type: ip_cidr, ip_range, or mac_prefix")
    scope_value: str = Field(..., description="Scope value: e.g., 192.168.0.0/16, 192.168.1.1-255, AA:BB:CC")
    description: str | None = Field(default=None, description="Description")


class ComplianceScopeCreate(ComplianceScopeBase):
    pass


class ComplianceScopeUpdate(BaseModel):
    scope_type: ScopeType | None = None
    scope_value: str | None = None
    description: str | None = None
    is_active: bool | None = None


class ComplianceScopeResponse(ComplianceScopeBase):
    id: int
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ComplianceScopeListResponse(BaseModel):
    items: list[ComplianceScopeResponse]
    total: int
