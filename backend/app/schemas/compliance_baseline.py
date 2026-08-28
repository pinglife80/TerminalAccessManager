from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComplianceBaselineBase(BaseModel):
    """Base compliance baseline schema"""
    name: str = Field(..., max_length=100, description="Baseline name")
    type: str = Field(..., description="Baseline type: ipguard")
    tag: str = Field(..., max_length=50, description="Unique tag identifier")
    config: dict[str, Any] = Field(default={}, description="Connection configuration")
    enabled: bool = Field(default=True, description="Whether the baseline is enabled")


class ComplianceBaselineCreate(ComplianceBaselineBase):
    """Schema for creating a compliance baseline"""
    pass


class ComplianceBaselineUpdate(BaseModel):
    """Schema for updating a compliance baseline"""
    name: str | None = Field(None, max_length=100)
    type: str | None = None
    tag: str | None = Field(None, max_length=50)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class ComplianceBaselineResponse(ComplianceBaselineBase):
    """Compliance baseline response schema"""
    id: int
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
