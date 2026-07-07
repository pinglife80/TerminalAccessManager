"""
Backup Schemas for TerminalAccessManager.

Pydantic models for backup-related API requests/responses.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BackupConfigResponse(BaseModel):
    """Schema for backup configuration response"""

    enabled: bool = False
    schedule: str = "0 2 * * *"
    retention_days: int = 7
    storage_type: str = "local"
    storage_config: dict[str, Any] = Field(default_factory=dict)
    backup_database: bool = True
    backup_config: bool = True
    backup_logs: bool = False
    encrypt_backup: bool = True


class BackupConfigUpdate(BaseModel):
    """Schema for backup configuration update request"""

    enabled: bool = False
    schedule: str = "0 2 * * *"
    retention_days: int = 7
    storage_type: str = "local"
    storage_config: dict[str, Any] = Field(default_factory=dict)
    backup_database: bool = True
    backup_config: bool = True
    backup_logs: bool = False
    encrypt_backup: bool = True


class BackupJobResponse(BaseModel):
    """Schema for backup job response"""

    id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    file_path: str | None = None
    file_size: int | None = None
    checksum: str | None = None
    error_message: str | None = None


class BackupInfo(BaseModel):
    """Schema for backup file information"""

    filename: str
    file_path: str | None = None
    file_size: int | None = None
    created_at: datetime | None = None
    storage: str = "local"


class BackupListResponse(BaseModel):
    """Schema for backup list response"""

    backups: list[BackupInfo]


class BackupRestoreResponse(BaseModel):
    """Schema for backup restore response"""

    success: bool
    message: str
    backup_file: str


class BackupTestResult(BaseModel):
    """Schema for backup test result"""

    success: bool
    message: str
    details: dict[str, Any] | None = None
