"""
Backup API Endpoints for TerminalAccessManager.

Provides REST API for managing backups.
"""

import os
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_client_ip, get_current_user, require_permission
from app.core.database import get_db
from app.models.user import User
from app.services.terminal_service import TerminalService
from app.schemas.backup import (
    BackupConfigResponse,
    BackupConfigUpdate,
    BackupContentsResponse,
    BackupJobResponse,
    BackupListResponse,
    BackupRestoreResponse,
    BackupTestResult,
)
from app.services.backup_service import BackupService

router = APIRouter(prefix="/backup", tags=["Backup"])


def get_backup_service(db: AsyncSession = Depends(get_db)) -> BackupService:
    """Dependency to get BackupService instance with database"""
    return BackupService(db=db)


@router.get("/config", response_model=BackupConfigResponse)
async def get_backup_config(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(get_current_user),
):
    """Get current backup configuration"""
    config = await backup_service.load_config()
    return BackupConfigResponse(
        enabled=config.enabled,
        schedule=config.schedule,
        retention_days=config.retention_days,
        storage_type=config.storage_type,
        storage_config=config.storage_config,
        backup_database=config.backup_database,
        backup_config=config.backup_config,
        backup_whitelist=config.backup_whitelist,
        backup_logs=config.backup_logs,
        encrypt_backup=config.encrypt_backup,
    )


@router.put("/config", response_model=BackupConfigResponse)
async def update_backup_config(
    config_data: BackupConfigUpdate,
    request: Request,
    backup_service: BackupService = Depends(get_backup_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup:write")),
):
    """Update backup configuration"""
    from app.services.backup_service import BackupConfig

    config = BackupConfig(
        enabled=config_data.enabled,
        schedule=config_data.schedule,
        retention_days=config_data.retention_days,
        storage_type=config_data.storage_type,
        storage_config=config_data.storage_config,
        backup_database=config_data.backup_database,
        backup_config=config_data.backup_config,
        backup_whitelist=config_data.backup_whitelist,
        backup_logs=config_data.backup_logs,
        encrypt_backup=config_data.encrypt_backup,
    )
    await backup_service.save_config(config)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "update_backup_config", "backup",
        None,
        {"enabled": config.enabled, "schedule": config.schedule, "storage_type": config.storage_type},
        ip_address=get_client_ip(request),
    )
    return BackupConfigResponse(**config_data.model_dump())


@router.post("/run", response_model=BackupJobResponse)
async def run_backup(
    request: Request,
    backup_type: str = "full",
    backup_service: BackupService = Depends(get_backup_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup:write")),
):
    """Run a manual backup"""
    job = await backup_service.run_backup(backup_type=backup_type)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "run_backup", "backup",
        str(job.id),
        {"status": job.status, "file_path": job.file_path, "file_size": job.file_size, "backup_type": backup_type},
        ip_address=get_client_ip(request),
        resource_name=job.file_path,
    )
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


@router.post("/whitelist", response_model=BackupJobResponse)
async def create_whitelist_backup(
    request: Request,
    backup_service: BackupService = Depends(get_backup_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup:write")),
):
    """Create a whitelist-only backup"""
    job = await backup_service.run_backup(backup_type="whitelist")
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "create_whitelist_backup", "backup",
        str(job.id),
        {"status": job.status, "file_path": job.file_path, "file_size": job.file_size},
        ip_address=get_client_ip(request),
        resource_name=job.file_path,
    )
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


@router.get("/whitelist/list", response_model=BackupListResponse)
async def get_whitelist_backups(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(get_current_user),
):
    """List all whitelist backups"""
    backups = []
    backup_dir = backup_service.backup_dir
    if os.path.isdir(backup_dir):
        for filename in sorted(os.listdir(backup_dir), reverse=True):
            if filename.endswith(".zip") and "whitelist" in filename.lower():
                file_path = os.path.join(backup_dir, filename)
                stats = os.stat(file_path)
                backups.append({
                    "filename": filename,
                    "file_path": file_path,
                    "file_size": stats.st_size,
                    "created_at": datetime.fromtimestamp(stats.st_mtime),
                    "storage": "local",
                })

    backups.sort(key=lambda x: (x.get("created_at") or datetime.min).replace(tzinfo=None) if hasattr(x.get("created_at") or datetime.min, 'replace') else datetime.min, reverse=True)
    return BackupListResponse(backups=backups)


@router.post("/whitelist/restore/{filename}", response_model=BackupRestoreResponse)
async def restore_whitelist_backup(
    filename: str,
    request: Request,
    backup_service: BackupService = Depends(get_backup_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup:write")),
):
    """Restore from a whitelist backup"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    success = await backup_service.restore_whitelist(file_path)

    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "restore_whitelist_backup", "backup",
        safe_filename,
        {"filename": safe_filename, "success": success},
        ip_address=get_client_ip(request),
        resource_name=safe_filename,
    )

    return BackupRestoreResponse(
        success=success,
        message="Whitelist restored successfully" if success else "Whitelist restoration failed",
        backup_file=safe_filename,
    )


@router.get("/{filename}/contents", response_model=BackupContentsResponse)
async def get_backup_contents(
    filename: str,
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(get_current_user),
):
    """Get contents/metadata of a backup file"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        contents = []
        with zipfile.ZipFile(file_path, "r") as zipf:
            for info in zipf.infolist():
                contents.append({
                    "filename": info.filename,
                    "file_size": info.file_size,
                    "compress_size": info.compress_size,
                })

        stats = os.stat(file_path)
        return BackupContentsResponse(
            filename=safe_filename,
            file_size=stats.st_size,
            created_at=datetime.fromtimestamp(stats.st_mtime),
            contents=contents,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read backup contents: {str(e)}")


@router.get("/list", response_model=BackupListResponse)
async def list_backups(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(get_current_user),
):
    """List all available backups (local + remote)"""
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
                    "storage": "local",
                })

    config = await backup_service.load_config()
    if config.storage_type != "local":
        remote_backups = await backup_service.list_remote_backups()
        backups.extend(remote_backups)

    backups.sort(key=lambda x: (x.get("created_at") or datetime.min).replace(tzinfo=None) if hasattr(x.get("created_at") or datetime.min, 'replace') else datetime.min, reverse=True)

    return BackupListResponse(backups=backups)


@router.get("/download/{filename}")
async def download_backup(
    filename: str,
    request: Request,
    backup_service: BackupService = Depends(get_backup_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup:write")),
):
    """Download a backup file (from local or remote)"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    if not os.path.exists(file_path):
        config = await backup_service.load_config()
        if config.storage_type != "local":
            try:
                file_path = await backup_service.download_from_remote(safe_filename)
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Backup file not found: {str(e)}")
        else:
            raise HTTPException(status_code=404, detail="Backup file not found")

    ts = TerminalService(db)
    file_size = os.path.getsize(file_path)
    await ts.log_action(
        current_user.username, "download_backup", "backup",
        safe_filename,
        {"filename": safe_filename, "file_size": file_size},
        ip_address=get_client_ip(request),
        resource_name=safe_filename,
    )

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/zip",
    )


@router.post("/restore/{filename}", response_model=BackupRestoreResponse)
async def restore_backup(
    filename: str,
    request: Request,
    backup_service: BackupService = Depends(get_backup_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup:write")),
):
    """Restore from a backup file"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Backup file not found")

    success = await backup_service.restore_backup(file_path)

    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "restore_backup", "backup",
        safe_filename,
        {"filename": safe_filename, "success": success},
        ip_address=get_client_ip(request),
        resource_name=safe_filename,
    )

    return BackupRestoreResponse(
        success=success,
        message="Backup restored successfully" if success else "Backup restoration failed",
        backup_file=safe_filename,
    )


@router.delete("/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    filename: str,
    request: Request,
    backup_service: BackupService = Depends(get_backup_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("backup:write")),
):
    """Delete a backup file (from local and/or remote)"""
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        raise HTTPException(status_code=400, detail="Invalid filename")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(backup_service.backup_dir, safe_filename)

    file_size = 0
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        os.remove(file_path)

    config = await backup_service.load_config()
    if config.storage_type != "local":
        await backup_service.delete_from_remote(safe_filename)

    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "delete_backup", "backup",
        safe_filename,
        {"filename": safe_filename, "file_size": file_size},
        ip_address=get_client_ip(request),
        resource_name=safe_filename,
    )


@router.post("/test", response_model=BackupTestResult)
async def test_backup_config(
    backup_service: BackupService = Depends(get_backup_service),
    current_user: User = Depends(require_permission("backup:write")),
    db: AsyncSession = Depends(get_db),
):
    """Test backup configuration"""
    results = {"database": "pending", "storage": "pending"}

    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
        results["database"] = "connected"
    except Exception as e:
        return BackupTestResult(
            success=False,
            message=f"Database connection failed: {str(e)}",
            details=results,
        )

    config = await backup_service.load_config()
    if config.storage_type == "sftp":
        try:
            import paramiko

            sftp_config = config.storage_config
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if sftp_config.get("key_filename"):
                ssh.connect(
                    hostname=sftp_config.get("host", ""),
                    port=int(sftp_config.get("port", 22)),
                    username=sftp_config.get("username", ""),
                    key_filename=sftp_config.get("key_filename"),
                    timeout=10,
                )
            else:
                ssh.connect(
                    hostname=sftp_config.get("host", ""),
                    port=int(sftp_config.get("port", 22)),
                    username=sftp_config.get("username", ""),
                    password=sftp_config.get("password", ""),
                    timeout=10,
                )
            ssh.close()
            results["storage"] = "connected"
        except Exception as e:
            return BackupTestResult(
                success=False,
                message=f"SFTP connection failed: {str(e)}",
                details=results,
            )
    elif config.storage_type == "ftp":
        try:
            import ftplib

            ftp_config = config.storage_config
            host = ftp_config.get("host", "localhost")
            port = int(ftp_config.get("port", 21))
            username = ftp_config.get("username", "")
            password = ftp_config.get("password", "")
            use_ssl = ftp_config.get("use_ssl", False)

            if use_ssl:
                ftp = ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()

            ftp.connect(host, port)
            ftp.login(username, password)
            ftp.quit()
            results["storage"] = "connected"
        except Exception as e:
            return BackupTestResult(
                success=False,
                message=f"FTP connection failed: {str(e)}",
                details=results,
            )
    else:
        results["storage"] = "local (no test needed)"

    return BackupTestResult(
        success=True,
        message="Backup configuration test successful",
        details=results,
    )
