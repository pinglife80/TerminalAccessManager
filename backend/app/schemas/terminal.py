from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# Terminal schemas
class TerminalBase(BaseModel):
    """Base terminal schema"""
    ip_address: str = Field(..., description="IP address")
    mac_address: str = Field(..., description="MAC address")
    comments: Optional[str] = None


class TerminalCreate(TerminalBase):
    """Schema for creating terminal record"""
    source: Optional[str] = "arp"


class TerminalUpdate(BaseModel):
    """Schema for updating terminal"""
    status: Optional[str] = None
    comments: Optional[str] = None


class TerminalResponse(TerminalBase):
    """Terminal response schema"""
    id: int
    status: str
    timestamp: datetime
    source: str
    source_tag: Optional[str] = None
    compliance_status: str = Field("unknown", description="Compliance status: compliant/bypass/non_compliant/unknown")
    wl_match_type: Optional[str] = Field(None, description="Whitelist match type: mac/ip/both/null")

    class Config:
        from_attributes = True


class TerminalQuery(BaseModel):
    """Query parameters for terminal search"""
    ip: Optional[str] = None
    mac: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[str] = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="Filter by end date (YYYY-MM-DD)")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


# Whitelist schemas
class WhitelistBase(BaseModel):
    """Base whitelist schema"""
    mac_address: Optional[str] = Field(None, description="MAC address")
    comments: Optional[str] = None


class WhitelistCreate(BaseModel):
    """Schema for adding to whitelist"""
    mac_address: Optional[str] = None
    ip_address: Optional[str] = None  # Accepts single IP, CIDR, or IP range (stored as ip_pattern)
    comments: Optional[str] = None


class WhitelistResponse(WhitelistBase):
    """Whitelist response schema"""
    id: int
    ip_pattern: Optional[str] = None
    pattern_type: str = "single_ip"
    added_by: str
    created_at: datetime

    class Config:
        from_attributes = True


class WhitelistQuery(BaseModel):
    """Query parameters for whitelist search"""
    search: Optional[str] = Field(None, description="Search by MAC, IP, or comments")
    start_date: Optional[str] = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="Filter by end date (YYYY-MM-DD)")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


# Blacklist schemas
class BlacklistBase(BaseModel):
    """Base blacklist schema"""
    ip_address: Optional[str] = Field(None, description="IP address")
    mac_address: Optional[str] = Field(None, description="MAC address")
    reason: Optional[str] = None


class BlacklistCreate(BlacklistBase):
    """Schema for adding to blacklist"""
    block_time: Optional[str] = Field("30d", description="Block duration (e.g. 15d, 7d, 1h)")
    firewall_tag: Optional[str] = Field(None, description="Firewall tag to route block operation")


class BlacklistResponse(BlacklistBase):
    """Blacklist response schema"""
    id: int
    blocked_at: datetime
    expires_at: Optional[datetime] = None
    blocked_by: str
    source_tag: Optional[str] = None
    firewall_tag: Optional[str] = None
    is_auto_blocked: bool = False
    auto_unblocked: bool = False

    class Config:
        from_attributes = True


class BlacklistQuery(BaseModel):
    """Query parameters for blacklist search"""
    search: Optional[str] = Field(None, description="Search by MAC or IP")
    start_date: Optional[str] = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="Filter by end date (YYYY-MM-DD)")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


# Audit Log schemas
class AuditLogBase(BaseModel):
    """Base audit log schema"""
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None


class AuditLogResponse(AuditLogBase):
    """Audit log response schema"""
    id: int
    username: str
    ip_address: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditLogQuery(BaseModel):
    """Query parameters for audit log search"""
    username: Optional[str] = None
    action: Optional[str] = None
    search: Optional[str] = Field(None, description="Search by IP, username, or details")
    start_date: Optional[str] = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="Filter by end date (YYYY-MM-DD)")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


# Stats schemas
class DashboardStats(BaseModel):
    """Dashboard statistics response"""
    total: int = Field(0, description="Total terminals count")
    whitelisted: int = Field(0, description="Whitelisted terminals count")
    blocked: int = Field(0, description="Blocked terminals count")
    active: int = Field(0, description="Active terminals count")
    inactive: int = Field(0, description="Inactive terminals count")
    pending: int = Field(0, description="Pending terminals count")
    compliant: int = Field(0, description="Compliant terminals count")
    bypass: int = Field(0, description="Bypass (whitelisted) terminals count")
    non_compliant: int = Field(0, description="Non-compliant terminals count")
    unknown: int = Field(0, description="Unknown compliance status count")


class SangforStatus(BaseModel):
    """Sangfor AF system status"""
    connected: bool = False
    cpu: Optional[float] = None
    memory: Optional[float] = None
    error: Optional[str] = None


class SystemStatus(BaseModel):
    """System status response"""
    backend_api: str = "connected"
    database: str = "connected"
    sangfor: Optional[SangforStatus] = None
    network_scanner: str = "pending"


# Generic response schema
class ResponseMessage(BaseModel):
    """Generic response message"""
    message: str
    success: bool = True
