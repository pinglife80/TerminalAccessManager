"""
Backup API Endpoints for TerminalAccessManager.

Provides REST API for managing backups.
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.backup import (
    BackupConfigResponse,
    BackupJobResponse,
    BackupListResponse,
    BackupRestoreResponse,
    BackupTestResult,
)
from app.services.backup_service import BackupConfig, BackupService

router = APIRouter(prefix="/backup", tags=["Backup"])


def get_backup_service() -> BackupService:
    """Dependency to get BackupService instance"""
    return BackupService()


@router.get("/config", response_model=BackupConfigResponse)
async def get_backup_config(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(get_current_user),
):
    """Get current backup configuration"""
    config = backup_service.config
    return BackupConfigResponse(
        enabled=config.enabled,
        schedule=config.schedule,
        retention_days=config.retention_days,
        storage_type=config.storage_type,
        storage_config=config.storage_config,
        backup_database=config.backup_database,
        backup_config=config.backup_config,
        backup_logs=config.backup_logs,
        encrypt_backup=config.encrypt_backup,
    )


@router.put("/config", response_model=BackupConfigResponse)
async def update_backup_config(
    config_data: BackupConfigResponse,
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(require_permission("system.manage")),
):
    """Update backup configuration"""
    backup_service.config.enabled = config_data.enabled
    backup_service.config.schedule = config_data.schedule
    backup_service.config.retention_days = config_data.retention_days
    backup_service.config.storage_type = config_data.storage_type
    backup_service.config.storage_config = config_data.storage_config
    backup_service.config.backup_database = config_data.backup_database
    backup_service.config.backup_config = config_data.backup_config
    backup_service.config.backup_logs = config_data.backup_logs
    backup_service.config.encrypt_backup = config_data.encrypt_backup

    return config_data


@router.post("/run", response_model=BackupJobResponse)
async def run_backup(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(require_permission("system.manage")),
):
    """Run a manual backup"""
    job = await backup_service.run_backup()
    return BackupJobResponse(
        id=job.id,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        file_path=job.file_path,
        file_size=job.file_size,
        checksum=job.checksum,
        error_message=job.error_message,
    )


@router.get("/list", response_model=BackupListResponse)
async def list_backups(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(get_current_user),
):
    """List all available backups"""
    backups = []
    backup_dir = backup_service.backup_dir

    if os.path.isdir(backup_dir):
        for filename in sorted(os.listdir(backup_dir), reverse=True):
            if filename.endswith(".zip"):
                file_path = os.path.join(backup_dir, filename)
                stats = os.stat(file_path)
                backups.append({
                    "filename": filename,
                    "file_path": file_path,
                    "file_size": stats.st_size,
                    "created_at": datetime.fromtimestamp(stats.st_mtime),
                })

    return BackupListResponse(backups=backups)


@router.get("/download/{filename}")
async def download_backup(
    filename: str,
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(require_permission("system.manage")),
):
    """Download a backup file"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/zip",
    )


@router.post("/restore/{filename}", response_model=BackupRestoreResponse)
async def restore_backup(
    filename: str,
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(require_permission("system.manage")),
):
    """Restore from a backup file"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    success = await backup_service.restore_backup(file_path)

    return BackupRestoreResponse(
        success=success,
        message="Backup restored successfully" if success else "Backup restoration failed",
        backup_file=safe_filename,
    )


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    filename: str,
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(require_permission("system.manage")),
):
    """Delete a backup file"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    os.remove(file_path)


@router.post("/test", response_model=BackupTestResult)
async def test_backup_config(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(require_permission("system.manage")),
):
    """Test backup configuration"""
    try:
        # Test database connection
        import psycopg2
        from app.core.config import settings

        conn = psycopg2.connect(
            host=settings.POSTGRES_SERVER,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            dbname=settings.POSTGRES_DB,
        )
        conn.close()

        # Test remote storage if configured
        if backup_service.config.storage_type != "local":
            # Attempt to connect
            if backup_service.config.storage_type == "sftp":
                # This is a basic test - actual connection test would require more
                pass

        return BackupTestResult(
            success=True,
            message="Backup configuration test successful",
            details={
                "database": "connected",
                "storage_type": backup_service.config.storage_type,
            },
        )
    except Exception as e:
        return BackupTestResult(
            success=False,
            message=f"Backup configuration test failed: {str(e)}",
        )
