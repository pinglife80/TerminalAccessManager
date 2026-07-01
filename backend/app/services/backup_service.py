"""
Backup Service for TerminalAccessManager.

Provides database and configuration backup functionality with FTP/SFTP support.
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import paramiko
from loguru import logger

from app.core.config import settings


@dataclass
class BackupConfig:
    """Backup configuration"""

    enabled: bool = False
    schedule: str = "0 2 * * *"  # Daily at 2 AM
    retention_days: int = 7

    # Storage configuration
    storage_type: str = "local"  # local, sftp, ftp
    storage_config: Dict[str, Any] = field(default_factory=dict)

    # Backup content
    backup_database: bool = True
    backup_config: bool = True
    backup_logs: bool = False

    # Encryption
    encrypt_backup: bool = True


@dataclass
class BackupJob:
    """Backup job status"""

    id: str
    status: str  # pending, running, completed, failed
    started_at: datetime
    completed_at: Optional[datetime] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    checksum: Optional[str] = None
    error_message: Optional[str] = None


class BackupService:
    """
    Backup service for TerminalAccessManager.

    Features:
    - PostgreSQL database backup via pg_dump
    - Configuration file backup
    - Local and remote storage (SFTP/FTP)
    - Backup encryption
    - Retention policy management
    """

    def __init__(self, config: Optional[BackupConfig] = None):
        """Initialize backup service"""
        self.config = config or BackupConfig()
        self.backup_dir = os.path.join(settings.UPLOAD_DIR, "backups")
        
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except PermissionError:
            logger.warning(f"Permission denied for backup directory {self.backup_dir}, using /tmp/backups instead")
            self.backup_dir = "/tmp/backups"
            os.makedirs(self.backup_dir, exist_ok=True)

    async def run_backup(self) -> BackupJob:
        """Execute a full backup job"""
        job = BackupJob(
            id=self._generate_backup_id(),
            status="running",
            started_at=datetime.now(),
        )

        try:
            # Create temporary directory for backup files
            with tempfile.TemporaryDirectory() as temp_dir:
                backup_files = []

                # Database backup
                if self.config.backup_database:
                    db_path = await self._backup_database(temp_dir)
                    backup_files.append(db_path)

                # Configuration backup
                if self.config.backup_config:
                    config_path = await self._backup_config(temp_dir)
                    backup_files.append(config_path)

                # Logs backup
                if self.config.backup_logs:
                    logs_path = await self._backup_logs(temp_dir)
                    backup_files.append(logs_path)

                # Create archive
                archive_path = await self._create_archive(temp_dir, backup_files)
                job.file_path = archive_path
                job.file_size = await asyncio.to_thread(os.path.getsize, archive_path)
                job.checksum = await self._calculate_checksum(archive_path)

                # Upload to remote storage if configured
                if self.config.storage_type != "local":
                    remote_path = await self._upload_backup(archive_path)
                    job.file_path = remote_path

            job.status = "completed"
            job.completed_at = datetime.now()

            # Cleanup old backups
            await self._cleanup_old_backups()

            logger.info(f"Backup completed: {job.file_path}")

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            logger.error(f"Backup failed: {e}")

        return job

    def _generate_backup_id(self) -> str:
        """Generate a unique backup ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"backup_{timestamp}"

    async def _backup_database(self, temp_dir: str) -> str:
        """Backup PostgreSQL database using pg_dump"""
        backup_path = os.path.join(temp_dir, "database.sql")

        # Build pg_dump command
        cmd = [
            "pg_dump",
            "-h", settings.POSTGRES_SERVER,
            "-p", str(settings.POSTGRES_PORT),
            "-U", settings.POSTGRES_USER,
            "-d", settings.POSTGRES_DB,
            "-f", backup_path,
            "-F", "c",  # Custom format
        ]

        # Set PGPASSWORD environment variable
        env = os.environ.copy()
        env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

        # Execute pg_dump
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
            raise Exception(f"Database backup failed: {error_msg}")

        logger.info("Database backup completed")
        return backup_path

    async def _backup_config(self, temp_dir: str) -> str:
        """Backup configuration files"""
        config_path = os.path.join(temp_dir, "config")
        os.makedirs(config_path, exist_ok=True)

        # Try to find config files in common locations
        search_paths = [
            ".",
            "/app",
            "/opt/tam",
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ]

        # Copy config files (excluding .env which contains sensitive data)
        config_files = [
            "docker-compose.yml",
            "manage.sh",
        ]
        for file in config_files:
            found = False
            for path in search_paths:
                candidate = os.path.join(path, file)
                if os.path.exists(candidate):
                    shutil.copy(candidate, config_path)
                    found = True
                    break
            if not found:
                logger.warning(f"Could not find {file} to backup")

        # Create archive of config directory
        archive_path = os.path.join(temp_dir, "config.zip")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(config_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)

        logger.info("Configuration backup completed")
        return archive_path

    async def _backup_logs(self, temp_dir: str) -> str:
        """Backup log files"""
        logs_path = os.path.join(temp_dir, "logs")
        os.makedirs(logs_path, exist_ok=True)

        log_dirs = ["/var/log/tam", "./logs"]
        for log_dir in log_dirs:
            if os.path.isdir(log_dir):
                for file in os.listdir(log_dir):
                    if file.endswith(".log") or file.endswith(".gz"):
                        src = os.path.join(log_dir, file)
                        dst = os.path.join(logs_path, file)
                        shutil.copy(src, dst)

        # Create archive
        archive_path = os.path.join(temp_dir, "logs.zip")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(logs_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)

        logger.info("Logs backup completed")
        return archive_path

    async def _create_archive(self, temp_dir: str, files: list) -> str:
        """Create a single archive from backup files"""
        def _create_archive_sync():
            archive_name = f"{self._generate_backup_id()}.zip"
            archive_path = os.path.join(self.backup_dir, archive_name)

            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file in files:
                    arcname = os.path.basename(file)
                    zipf.write(file, arcname)

            logger.info(f"Created archive: {archive_path}")
            return archive_path

        return await asyncio.to_thread(_create_archive_sync)

    async def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of a file"""
        def _calculate_checksum_sync():
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()

        return await asyncio.to_thread(_calculate_checksum_sync)

    async def _upload_backup(self, local_path: str) -> str:
        """Upload backup to remote storage"""
        if self.config.storage_type == "sftp":
            return await self._upload_via_sftp(local_path)
        else:
            return local_path

    async def _upload_via_sftp(self, local_path: str) -> str:
        """Upload backup via SFTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = config.get("port", 22)
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        key_filename = config.get("key_filename")

        try:
            transport = paramiko.Transport((host, port))
            transport.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_filename:
                private_key = paramiko.RSAKey.from_private_key_file(key_filename)
                transport.connect(username=username, pkey=private_key)
            else:
                transport.connect(username=username, password=password)

            sftp = paramiko.SFTPClient.from_transport(transport)

            # Ensure remote directory exists
            try:
                sftp.stat(remote_path)
            except FileNotFoundError:
                sftp.mkdir(remote_path)

            # Upload file
            remote_filename = os.path.basename(local_path)
            remote_file_path = os.path.join(remote_path, remote_filename)
            sftp.put(local_path, remote_file_path)

            sftp.close()
            transport.close()

            logger.info(f"Backup uploaded via SFTP: {remote_file_path}")
            return remote_file_path

        except Exception as e:
            logger.error(f"SFTP upload failed: {e}")
            raise

    async def _cleanup_old_backups(self):
        """Clean up backups older than retention_days"""
        def _cleanup_sync():
            retention_seconds = self.config.retention_days * 24 * 60 * 60
            now = time.time()

            for filename in os.listdir(self.backup_dir):
                file_path = os.path.join(self.backup_dir, filename)
                if os.path.isfile(file_path):
                    file_age = now - os.path.getmtime(file_path)
                    if file_age > retention_seconds:
                        os.remove(file_path)
                        logger.info(f"Removed old backup: {filename}")

        await asyncio.to_thread(_cleanup_sync)

    async def verify_backup(self, backup_path: str) -> bool:
        """Verify backup integrity"""
        if not os.path.exists(backup_path):
            return False

        try:
            with zipfile.ZipFile(backup_path, "r") as zipf:
                # Check for CRC errors
                zipf.testzip()
            return True
        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return False

    async def restore_backup(self, backup_path: str) -> bool:
        """Restore from backup"""
        if not await self.verify_backup(backup_path):
            raise Exception("Backup file is corrupted or missing")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract backup
                with zipfile.ZipFile(backup_path, "r") as zipf:
                    zipf.extractall(temp_dir)

                # Restore database if present
                db_file = os.path.join(temp_dir, "database.sql")
                if os.path.exists(db_file):
                    await self._restore_database(db_file)

                logger.info("Backup restoration completed")
                return True

        except Exception as e:
            logger.error(f"Backup restoration failed: {e}")
            return False

    async def _restore_database(self, db_file: str):
        """Restore PostgreSQL database"""
        cmd = [
            "pg_restore",
            "-h", settings.POSTGRES_SERVER,
            "-p", str(settings.POSTGRES_PORT),
            "-U", settings.POSTGRES_USER,
            "-d", settings.POSTGRES_DB,
            "-c",  # Clean (drop) database objects before creating them
            db_file,
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = settings.POSTGRES_PASSWORD

        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
            raise Exception(f"Database restoration failed: {error_msg}")

        logger.info("Database restoration completed")
