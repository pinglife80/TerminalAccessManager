from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class ComplianceBaselineBase(BaseModel):
    """Base compliance baseline schema"""
    name: str = Field(..., max_length=100, description="Baseline name")
    type: str = Field(..., description="Baseline type: ipguard")
    tag: str = Field(..., max_length=50, description="Unique tag identifier")
    config: Dict[str, Any] = Field(default={}, description="Connection configuration")
    enabled: bool = Field(default=True, description="Whether the baseline is enabled")


class ComplianceBaselineCreate(ComplianceBaselineBase):
    """Schema for creating a compliance baseline"""
    pass


class ComplianceBaselineUpdate(BaseModel):
    """Schema for updating a compliance baseline"""
    name: Optional[str] = Field(None, max_length=100)
    type: Optional[str] = None
    tag: Optional[str] = Field(None, max_length=50)
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class ComplianceBaselineResponse(ComplianceBaselineBase):
    """Compliance baseline response schema"""
    id: int
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
