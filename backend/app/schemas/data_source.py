from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# DataSource schemas
# ------------------------------------------------------------------
class DataSourceBase(BaseModel):
    """Base data source schema"""
    name: str = Field(..., max_length=100, description="Data source name")
    type: str = Field(..., description="Data source type: arp_ssh / arp_api / sangfor")
    tag: str = Field(..., max_length=50, description="Unique tag identifier")
    config: dict[str, Any] = Field(default={}, description="Connection configuration")
    enabled: bool = Field(default=True, description="Whether the data source is enabled")


class DataSourceCreate(DataSourceBase):
    """Schema for creating a data source"""
    pass


class DataSourceUpdate(BaseModel):
    """Schema for updating a data source"""
    name: str | None = Field(None, max_length=100)
    type: str | None = None
    tag: str | None = Field(None, max_length=50)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class DataSourceResponse(DataSourceBase):
    """Data source response schema"""
    id: int
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    warnings: list[str] | None = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# DataSourceBinding schemas
# ------------------------------------------------------------------
class DataSourceBindingCreate(BaseModel):
    """Schema for creating a data source binding"""
    arp_source_tag: str = Field(..., max_length=50, description="ARP data source tag")
    firewall_tag: str = Field(..., max_length=50, description="Firewall data source tag")


class DataSourceBindingResponse(BaseModel):
    """Data source binding response schema"""
    id: int
    arp_source_tag: str
    firewall_tag: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# Connection test result
# ------------------------------------------------------------------
class ConnectionTestResult(BaseModel):
    """Result of testing a data source connection"""
    success: bool
    message: str
    details: dict[str, Any] | None = None


# ------------------------------------------------------------------
# Sync result
# ------------------------------------------------------------------
class SyncResult(BaseModel):
    """Result of a data source sync operation"""
    success: bool
    message: str
    entries_processed: int = 0
    entries_added: int = 0
    entries_updated: int = 0
    errors: list[str] = []


# ------------------------------------------------------------------
# Compliance schemas
# ------------------------------------------------------------------
class ComplianceCheckRequest(BaseModel):
    """Request for compliance check"""
    arp_source_tag: str | None = Field(None, description="Check only entries from this ARP source")
    force: bool = Field(default=False, description="Force re-check even if already checked")


class ComplianceCheckResult(BaseModel):
    """Result of a compliance check"""
    total_checked: int = 0
    compliant: int = 0
    bypass: int = 0
    non_compliant: int = 0
    unknown: int = 0
    message: str | None = None
    details: dict[str, list[dict[str, Any]]] | None = None


class AutoBlockRequest(BaseModel):
    """Request for auto-blocking non-compliant terminals"""
    arp_source_tag: str = Field(..., description="ARP source tag to process")
    block_time: str = Field(default="30d", description="Block duration")
    dry_run: bool = Field(default=False, description="Preview only, do not actually block")


class AutoBlockResult(BaseModel):
    """Result of auto-blocking operation"""
    total_non_compliant: int = 0
    blocked: int = 0
    skipped: int = 0
    errors: list[str] = []
    details: list[dict[str, Any]] | None = None
    message: str | None = None


class AutoUnblockResult(BaseModel):
    """Result of auto-unblocking operation"""
    total_auto_blocked: int = 0
    unblocked: int = 0
    skipped: int = 0
    errors: list[str] = []
    details: list[dict[str, Any]] | None = None
    message: str | None = None


# ------------------------------------------------------------------
# Delete Preview schemas
# ------------------------------------------------------------------
class DeletePreviewAffected(BaseModel):
    """Affected resources count for delete preview"""
    terminals: int = 0
    blocked_terminals: int = 0
    blacklist_entries: int = 0
    bindings: int = 0
    compliant_terminals: int = 0


class DeletePreviewResponse(BaseModel):
    """Response for delete preview - shows impact before actual deletion"""
    can_delete: bool
    warnings: list[str] = []
    actions: list[str] = []
    affected: DeletePreviewAffected = DeletePreviewAffected()
    reason: str | None = None
