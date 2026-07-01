"""
Backup Schemas for TerminalAccessManager.

Pydantic models for backup-related API requests/responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BackupConfigResponse(BaseModel):
    """Schema for backup configuration response"""

    enabled: bool = False
    schedule: str = "0 2 * * *"
    retention_days: int = 7
    storage_type: str = "local"
    storage_config: Dict[str, Any] = Field(default_factory=dict)
    backup_database: bool = True
    backup_config: bool = True
    backup_logs: bool = False
    encrypt_backup: bool = True


class BackupJobResponse(BaseModel):
    """Schema for backup job response"""

    id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    checksum: Optional[str] = None
    error_message: Optional[str] = None


class BackupInfo(BaseModel):
    """Schema for backup file information"""

    filename: str
    file_path: str
    file_size: int
    created_at: datetime


class BackupListResponse(BaseModel):
    """Schema for backup list response"""

    backups: List[BackupInfo]


class BackupRestoreResponse(BaseModel):
    """Schema for backup restore response"""

    success: bool
    message: str
    backup_file: str


class BackupTestResult(BaseModel):
    """Schema for backup test result"""

    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
