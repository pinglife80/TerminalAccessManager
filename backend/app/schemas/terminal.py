from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# Terminal schemas
class TerminalBase(BaseModel):
    """Base terminal schema"""
    ip_address: str = Field(..., description="IP address")
    mac_address: str = Field(..., description="MAC address")
    comments: str | None = None


class TerminalCreate(TerminalBase):
    """Schema for creating terminal record"""
    source: str | None = "arp"


class TerminalUpdate(BaseModel):
    """Schema for updating terminal"""
    status: str | None = None
    comments: str | None = None


class TerminalResponse(TerminalBase):
    """Terminal response schema"""
    id: int
    status: str
    timestamp: datetime
    source: str
    source_tag: str | None = None
    compliance_status: str = Field("unknown", description="Compliance status: compliant/bypass/non_compliant/unknown")
    wl_match_type: str | None = Field(None, description="Whitelist match type: mac/ip/both/null")
    firewall_tag: str | None = Field(None, description="Firewall tag from block operation")
    block_state: str | None = Field(None, description="Blockable state: null/no_firewall/block_failed")

    model_config = ConfigDict(from_attributes=True)


class TerminalQuery(BaseModel):
    """Query parameters for terminal search"""
    ip: str | None = None
    mac: str | None = None
    status: str | None = None
    compliance_status: str | None = Field(None, description="Filter by compliance status")
    source_tag: str | None = Field(None, description="Filter by source tag")
    firewall_tag: str | None = Field(None, description="Filter by firewall tag (via blacklist)")
    block_state: str | None = Field(None, description="Filter by block_state (no_firewall/block_failed)")
    arp_enabled_only: bool = Field(False, description="Restrict to enabled ARP data sources")
    start_date: str | None = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="Filter by end date (YYYY-MM-DD)")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


# Whitelist schemas
class WhitelistBase(BaseModel):
    """Base whitelist schema"""
    mac_address: str | None = Field(None, description="MAC address")
    comments: str | None = None


class WhitelistCreate(BaseModel):
    """Schema for adding to whitelist"""
    mac_address: str | None = None
    ip_address: str | None = None  # Accepts single IP, CIDR, or IP range (stored as ip_pattern)
    comments: str = Field(..., description="Comment for the whitelist entry")


class WhitelistResponse(WhitelistBase):
    """Whitelist response schema"""
    id: int
    ip_pattern: str | None = None
    pattern_type: str = "single_ip"
    added_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhitelistQuery(BaseModel):
    """Query parameters for whitelist search"""
    search: str | None = Field(None, description="Search by MAC, IP, or comments")
    start_date: str | None = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="Filter by end date (YYYY-MM-DD)")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


class WhitelistImportError(BaseModel):
    """Single import error detail"""
    row: int = Field(..., description="CSV row number (1-based)")
    reason: str = Field(..., description="Error description")
    data: dict = Field(default_factory=dict, description="Row data that caused the error")


class WhitelistImportResult(BaseModel):
    """Result of whitelist CSV import"""
    success_count: int = Field(0, description="Number of successfully imported entries")
    skipped_count: int = Field(0, description="Number of skipped (duplicate) entries")
    failed_count: int = Field(0, description="Number of failed entries")
    errors: list[WhitelistImportError] = Field(default_factory=list, description="List of import errors")
    mode: str = Field("skip", description="Conflict handling mode used")
    total_processed: int = Field(0, description="Total rows processed (excluding header)")


# Blacklist schemas
class BlacklistBase(BaseModel):
    """Base blacklist schema"""
    ip_address: str | None = Field(None, description="IP address")
    mac_address: str | None = Field(None, description="MAC address")
    reason: str | None = None


class BlacklistCreate(BlacklistBase):
    """Schema for adding to blacklist"""
    block_time: str | None = Field("30d", description="Block duration (e.g. 15d, 7d, 1h)")
    firewall_tag: str | None = Field(None, description="Firewall tag to route block operation")


class BlacklistResponse(BlacklistBase):
    """Blacklist response schema"""
    id: int
    blocked_at: datetime | None = None
    expires_at: datetime | None = None
    blocked_by: str
    source_tag: str | None = None
    firewall_tag: str | None = None
    is_auto_blocked: bool = False
    auto_unblocked: bool = False
    unblocked_at: datetime | None = None
    unblocked_by: str | None = None
    last_operation_type: str | None = None
    last_operation_status: str | None = None
    last_operation_error: str | None = None
    last_operation_at: datetime | None = None
    retry_count: int = 0
    terminal_compliance_status: str | None = Field(
        None, description="Associated terminal's compliance_status (compliant/bypass/non_compliant/unknown), null if no terminal"
    )

    model_config = ConfigDict(from_attributes=True)


class BlacklistQuery(BaseModel):
    """Query parameters for blacklist search"""
    search: str | None = Field(None, description="Search by MAC or IP")
    start_date: str | None = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="Filter by end date (YYYY-MM-DD)")
    status: str | None = Field(None, description="Filter by status: active/unblocked/all")
    category: str | None = Field(None, description="Filter by category: success_blocked/success_unblocked/pending_retry_unblock")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


class BlacklistCheckRequest(BaseModel):
    """Request body for batch blacklist check"""
    mac_addresses: list[str] = Field(default_factory=list, description="MAC addresses to check")
    ip_addresses: list[str] = Field(default_factory=list, description="IP addresses to check")


class BlacklistCheckItem(BaseModel):
    """A single blacklist match result for batch check"""
    mac_address: str | None = None
    ip_address: str | None = None
    firewall_tag: str | None = None


# Audit Log schemas
class AuditLogBase(BaseModel):
    """Base audit log schema"""
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    resource_name: str | None = None
    details: str | None = None


class AuditLogResponse(AuditLogBase):
    """Audit log response schema"""
    id: int
    username: str
    ip_address: str | None = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogQuery(BaseModel):
    """Query parameters for audit log search"""
    username: str | None = None
    action: str | None = None
    search: str | None = Field(None, description="Search by IP, username, or details")
    start_date: str | None = Field(None, description="Filter by start date (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="Filter by end date (YYYY-MM-DD)")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)
    cursor: str | None = Field(None, description="Keyset pagination cursor (base64-encoded timestamp/id)")


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
    error: str | None = None


class SystemStatus(BaseModel):
    """System status response"""
    backend_api: str = "connected"
    database: str = "connected"
    sangfor: SangforStatus | None = None
    network_scanner: str = "pending"
    uptime: str | None = None
    version: str | None = None
    environment: str | None = None


# Generic response schema
class ResponseMessage(BaseModel):
    """Generic response message"""
    message: str
    success: bool = True


# Paginated response wrapper
T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""
    items: list[T]
    total: int
    skip: int
    limit: int


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """Cursor-based paginated response wrapper for efficient deep pagination"""
    items: list[T]
    total: int
    limit: int
    next_cursor: str | None = None
