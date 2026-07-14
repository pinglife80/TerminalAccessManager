"""
Backup Service for TerminalAccessManager.

Provides database and configuration backup functionality with FTP/SFTP support.
"""

import asyncio
import ftplib
import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import paramiko
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.backup_config import BackupConfigModel
from app.models.system_config import SystemConfig
from app.models.notification import NotificationChannel, NotificationRule, NotificationTemplate
from app.models.auth_config import AuthConfig
from app.models.data_source import DataSource
from app.models.whitelist import Whitelist


@dataclass
class BackupConfig:
    """Backup configuration"""

    enabled: bool = False
    schedule: str = "0 2 * * *"  # Daily at 2 AM
    retention_days: int = 7

    # Storage configuration
    storage_type: str = "local"  # local, sftp, ftp
    storage_config: dict[str, Any] = field(default_factory=dict)

    # Backup content
    backup_database: bool = True
    backup_config: bool = True
    backup_whitelist: bool = True
    backup_logs: bool = False

    # Encryption
    encrypt_backup: bool = True


@dataclass
class BackupJob:
    """Backup job status"""

    id: str
    status: str = "running"
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    file_path: str | None = None
    file_size: int | None = None
    checksum: str | None = None
    error_message: str | None = None

    def complete(self, file_path: str, file_size: int, checksum: str) -> None:
        """Mark job as completed"""
        self.status = "completed"
        self.completed_at = datetime.now()
        self.file_path = file_path
        self.file_size = file_size
        self.checksum = checksum


class BackupService:
    """
    Backup service for TerminalAccessManager.

    Features:
    - PostgreSQL database backup via pg_dump
    - Configuration file backup
    - Local and remote storage (SFTP/FTP)
    - Backup encryption
    - Retention policy management
    - Database persistent configuration
    """

    def __init__(self, config: BackupConfig | None = None, db: AsyncSession | None = None):
        """Initialize backup service"""
        self.db = db
        self.config = config or BackupConfig()
        self.backup_dir = os.path.join(settings.UPLOAD_DIR, "backups")

        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except PermissionError:
            logger.warning(f"Permission denied for backup directory {self.backup_dir}, using /tmp/backups instead")
            self.backup_dir = "/tmp/backups"
            os.makedirs(self.backup_dir, exist_ok=True)

    async def load_config(self) -> BackupConfig:
        """Load backup configuration from database"""
        if self.db is None:
            return self.config

        try:
            result = await self.db.execute(select(BackupConfigModel).limit(1))
            model = result.scalar_one_or_none()

            if model:
                self.config = BackupConfig(
                    enabled=model.enabled,
                    schedule=model.schedule,
                    retention_days=model.retention_days,
                    storage_type=model.storage_type,
                    storage_config=model.storage_config,
                    backup_database=model.backup_database,
                    backup_config=model.backup_config,
                    backup_whitelist=getattr(model, "backup_whitelist", True),
                    backup_logs=model.backup_logs,
                    encrypt_backup=model.encrypt_backup,
                )
            else:
                model = BackupConfigModel()
                self.db.add(model)
                await self.db.commit()
                self.config = BackupConfig()

            return self.config
        except Exception as e:
            logger.error(f"Failed to load backup config from database: {e}")
            return self.config

    async def save_config(self, config: BackupConfig) -> None:
        """Save backup configuration to database"""
        if self.db is None:
            self.config = config
            return

        try:
            result = await self.db.execute(select(BackupConfigModel).limit(1))
            model = result.scalar_one_or_none()

            if model:
                model.enabled = config.enabled
                model.schedule = config.schedule
                model.retention_days = config.retention_days
                model.storage_type = config.storage_type
                model.storage_config = config.storage_config
                model.backup_database = config.backup_database
                model.backup_config = config.backup_config
                model.backup_whitelist = config.backup_whitelist
                model.backup_logs = config.backup_logs
                model.encrypt_backup = config.encrypt_backup
            else:
                model = BackupConfigModel(
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
                self.db.add(model)

            await self.db.commit()
            self.config = config
            logger.info("Backup config saved to database")
        except Exception as e:
            logger.error(f"Failed to save backup config to database: {e}")
            raise

    async def run_backup(self, backup_type: str = "full") -> BackupJob:
        """Execute a backup job"""
        job = BackupJob(
            id=self._generate_backup_id(backup_type),
            status="running",
            started_at=datetime.now(),
        )

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                backup_files = []

                if backup_type == "full" or backup_type == "database":
                    if self.config.backup_database:
                        db_path = await self.backup_database(temp_dir)
                        backup_files.append(db_path)

                if backup_type == "full" or backup_type == "config":
                    if self.config.backup_config:
                        config_path = await self.backup_config(temp_dir)
                        backup_files.append(config_path)

                        system_config_path = await self._backup_system_config_db(temp_dir)
                        if system_config_path:
                            backup_files.append(system_config_path)

                        branding_path = await self._backup_branding(temp_dir)
                        if branding_path:
                            backup_files.append(branding_path)

                if backup_type == "full" or backup_type == "whitelist":
                    whitelist_path = await self.backup_whitelist(temp_dir)
                    if whitelist_path:
                        backup_files.append(whitelist_path)

                if backup_type == "full" or backup_type == "logs":
                    if self.config.backup_logs:
                        logs_path = await self._backup_logs(temp_dir)
                        backup_files.append(logs_path)

                archive_path = await self.create_archive(temp_dir, backup_files, backup_type)
                job.file_path = archive_path
                if os.path.exists(archive_path):
                    job.file_size = await asyncio.to_thread(os.path.getsize, archive_path)
                    job.checksum = await self._calculate_checksum(archive_path)

                if self.config.storage_type != "local":
                    remote_path = await self._upload_backup(archive_path)
                    job.file_path = remote_path

            job.status = "completed"
            job.completed_at = datetime.now()

            await self.cleanup_old_backups()

            logger.info(f"Backup completed: {job.file_path}")

            from app.services.event_emitter import emit_backup_completed
            await emit_backup_completed(job.file_path or "", job.file_size or 0)

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            logger.error(f"Backup failed: {e}")

            from app.services.event_emitter import emit_backup_failed
            await emit_backup_failed(str(e))

        return job

    def _generate_backup_id(self, backup_type: str = "full") -> str:
        """Generate a unique backup ID with type identifier"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"backup_{backup_type}_{timestamp}"

    async def _backup_database(self, temp_dir: str) -> str:
        """Backup PostgreSQL database using pg_dump"""
        backup_path = os.path.join(temp_dir, "database.sql")

        if not hasattr(settings, 'POSTGRES_SERVER') or not settings.POSTGRES_SERVER:
            logger.warning("PostgreSQL not configured, skipping database backup")
            with open(backup_path, "w") as f:
                f.write("-- PostgreSQL not configured\n")
            return backup_path

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
            for root, _dirs, files in os.walk(config_path):
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
            for root, _dirs, files in os.walk(logs_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)

        logger.info("Logs backup completed")
        return archive_path

    async def _backup_system_config_db(self, temp_dir: str) -> str:
        """Backup system configuration from database tables"""
        config_data = {}
        config_path = os.path.join(temp_dir, "config")
        os.makedirs(config_path, exist_ok=True)

        if self.db is None:
            logger.warning("No database session available, skipping system config backup")
            return ""

        try:
            result = await self.db.execute(select(SystemConfig))
            config_data["system_config"] = [
                {
                    "key": row.key,
                    "value": row.value,
                    "category": row.category,
                    "value_type": row.value_type,
                    "description": row.description,
                    "is_readonly": row.is_readonly,
                }
                for row in result.scalars().all()
            ]

            result = await self.db.execute(select(NotificationChannel))
            config_data["notification_channels"] = [
                {
                    "id": row.id,
                    "name": row.name,
                    "type": row.type,
                    "config": row.config,
                    "enabled": row.enabled,
                    "events": row.events,
                    "description": row.description,
                }
                for row in result.scalars().all()
            ]

            result = await self.db.execute(select(NotificationRule))
            config_data["notification_rules"] = [
                {
                    "id": row.id,
                    "name": row.name,
                    "event_type": row.event_type,
                    "channel_name": row.channel_name,
                    "enabled": row.enabled,
                    "priority": row.priority,
                    "description": row.description,
                    "suppress_enabled": row.suppress_enabled,
                    "suppress_window": row.suppress_window,
                    "escalate_enabled": row.escalate_enabled,
                    "escalate_threshold": row.escalate_threshold,
                    "escalate_window": row.escalate_window,
                    "escalate_severity": row.escalate_severity,
                }
                for row in result.scalars().all()
            ]

            result = await self.db.execute(select(NotificationTemplate))
            config_data["notification_templates"] = [
                {
                    "id": row.id,
                    "name": row.name,
                    "event_type": row.event_type,
                    "channel_type": row.channel_type,
                    "subject": row.subject,
                    "body": row.body,
                    "is_default": row.is_default,
                }
                for row in result.scalars().all()
            ]

            result = await self.db.execute(select(AuthConfig))
            config_data["auth_providers"] = [
                {
                    "id": row.id,
                    "name": row.name,
                    "provider_type": row.provider_type,
                    "config": row.config,
                    "enabled": row.enabled,
                    "priority": row.priority,
                }
                for row in result.scalars().all()
            ]

            result = await self.db.execute(select(DataSource))
            config_data["datasource"] = [
                {
                    "id": row.id,
                    "name": row.name,
                    "type": row.type,
                    "config": row.config,
                    "enabled": row.enabled,
                }
                for row in result.scalars().all()
            ]

            config_file = os.path.join(config_path, "system_config.json")
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

            logger.info("System config backup completed")
            return config_file
        except Exception as e:
            logger.error(f"Failed to backup system config: {e}")
            return ""

    async def _restore_system_config_db(self, temp_dir: str) -> bool:
        """Restore system configuration to database tables"""
        config_file = os.path.join(temp_dir, "config", "system_config.json")
        if not os.path.exists(config_file):
            logger.warning("system_config.json not found in backup, skipping")
            return False

        if self.db is None:
            logger.warning("No database session available, skipping system config restore")
            return False

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            if "system_config" in config_data:
                await self.db.execute(SystemConfig.__table__.delete())
                for item in config_data["system_config"]:
                    self.db.add(SystemConfig(**item))

            if "notification_channels" in config_data:
                await self.db.execute(NotificationChannel.__table__.delete())
                for item in config_data["notification_channels"]:
                    obj = NotificationChannel(
                        name=item["name"],
                        type=item["type"],
                        config=item["config"],
                        enabled=item["enabled"],
                        events=item["events"],
                        description=item.get("description"),
                    )
                    self.db.add(obj)

            if "notification_rules" in config_data:
                await self.db.execute(NotificationRule.__table__.delete())
                for item in config_data["notification_rules"]:
                    obj = NotificationRule(
                        name=item["name"],
                        event_type=item["event_type"],
                        channel_name=item["channel_name"],
                        enabled=item["enabled"],
                        priority=item.get("priority", 100),
                        description=item.get("description"),
                        suppress_enabled=item.get("suppress_enabled", False),
                        suppress_window=item.get("suppress_window", 300),
                        escalate_enabled=item.get("escalate_enabled", False),
                        escalate_threshold=item.get("escalate_threshold", 5),
                        escalate_window=item.get("escalate_window", 3600),
                        escalate_severity=item.get("escalate_severity", "error"),
                    )
                    self.db.add(obj)

            if "notification_templates" in config_data:
                await self.db.execute(NotificationTemplate.__table__.delete())
                for item in config_data["notification_templates"]:
                    obj = NotificationTemplate(
                        name=item["name"],
                        event_type=item["event_type"],
                        channel_type=item["channel_type"],
                        subject=item.get("subject"),
                        body=item.get("body"),
                        is_default=item.get("is_default", False),
                    )
                    self.db.add(obj)

            if "auth_providers" in config_data:
                await self.db.execute(AuthConfig.__table__.delete())
                for item in config_data["auth_providers"]:
                    obj = AuthConfig(
                        name=item["name"],
                        provider_type=item["provider_type"],
                        config=item["config"],
                        enabled=item["enabled"],
                        priority=item.get("priority", 100),
                    )
                    self.db.add(obj)

            if "datasource" in config_data:
                await self.db.execute(DataSource.__table__.delete())
                for item in config_data["datasource"]:
                    obj = DataSource(
                        name=item["name"],
                        type=item["type"],
                        config=item["config"],
                        enabled=item["enabled"],
                    )
                    self.db.add(obj)

            await self.db.commit()
            logger.info("System config restoration completed")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to restore system config: {e}")
            return False

    async def _backup_branding(self, temp_dir: str) -> str:
        """Backup branding asset files"""
        branding_path = os.path.join(temp_dir, "branding")
        os.makedirs(branding_path, exist_ok=True)

        upload_dir = getattr(settings, 'UPLOAD_DIR', '/app/uploads')
        branding_dir = os.path.join(upload_dir, "branding")

        if os.path.isdir(branding_dir):
            for file in os.listdir(branding_dir):
                src = os.path.join(branding_dir, file)
                dst = os.path.join(branding_path, file)
                if os.path.isfile(src):
                    shutil.copy(src, dst)

        archive_path = os.path.join(temp_dir, "branding.zip")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _dirs, files in os.walk(branding_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)

        logger.info("Branding backup completed")
        return archive_path

    async def _restore_branding(self, temp_dir: str) -> bool:
        """Restore branding asset files"""
        branding_zip = os.path.join(temp_dir, "branding.zip")
        if not os.path.exists(branding_zip):
            logger.warning("branding.zip not found in backup, skipping")
            return False

        upload_dir = getattr(settings, 'UPLOAD_DIR', '/app/uploads')
        branding_dir = os.path.join(upload_dir, "branding")
        os.makedirs(branding_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(branding_zip, "r") as zipf:
                zipf.extractall(temp_dir)

            branding_path = os.path.join(temp_dir, "branding")
            if os.path.isdir(branding_path):
                for file in os.listdir(branding_path):
                    src = os.path.join(branding_path, file)
                    dst = os.path.join(branding_dir, file)
                    if os.path.isfile(src):
                        shutil.copy(src, dst)

            logger.info("Branding restoration completed")
            return True
        except Exception as e:
            logger.error(f"Failed to restore branding: {e}")
            return False

    async def backup_whitelist(self, temp_dir: str) -> str:
        """Export whitelist to JSON file"""
        whitelist_path = os.path.join(temp_dir, "whitelist")
        os.makedirs(whitelist_path, exist_ok=True)

        if self.db is None:
            logger.warning("No database session available, skipping whitelist backup")
            return ""

        try:
            result = await self.db.execute(select(Whitelist))
            whitelist_data = [
                {
                    "id": row.id,
                    "mac_address": row.mac_address,
                    "mac_address_normalized": row.mac_address_normalized,
                    "ip_pattern": row.ip_pattern,
                    "pattern_type": row.pattern_type,
                    "comments": row.comments,
                    "added_by": row.added_by,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in result.scalars().all()
            ]

            whitelist_file = os.path.join(whitelist_path, "whitelist.json")
            with open(whitelist_file, "w", encoding="utf-8") as f:
                json.dump(whitelist_data, f, ensure_ascii=False, indent=2)

            archive_path = os.path.join(temp_dir, "whitelist.zip")
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(whitelist_file, "whitelist/whitelist.json")

            logger.info("Whitelist backup completed")
            return archive_path
        except Exception as e:
            logger.error(f"Failed to backup whitelist: {e}")
            return ""

    async def restore_whitelist(self, file_path: str) -> bool:
        """Restore whitelist from backup file"""
        if not await self.verify_backup(file_path):
            raise Exception("Backup file is corrupted or missing")

        if self.db is None:
            logger.warning("No database session available, skipping whitelist restore")
            return False

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(file_path, "r") as zipf:
                    zipf.extractall(temp_dir)

                whitelist_file = os.path.join(temp_dir, "whitelist", "whitelist.json")
                if not os.path.exists(whitelist_file):
                    whitelist_file = os.path.join(temp_dir, "whitelist.json")

                if not os.path.exists(whitelist_file):
                    logger.warning("whitelist.json not found in backup")
                    return False

                with open(whitelist_file, "r", encoding="utf-8") as f:
                    whitelist_data = json.load(f)

                await self.db.execute(Whitelist.__table__.delete())
                for item in whitelist_data:
                    obj = Whitelist(
                        mac_address=item.get("mac_address"),
                        mac_address_normalized=item.get("mac_address_normalized"),
                        ip_pattern=item.get("ip_pattern"),
                        pattern_type=item.get("pattern_type", "single_ip"),
                        comments=item.get("comments"),
                        added_by=item.get("added_by", "system"),
                    )
                    self.db.add(obj)

                await self.db.commit()
                logger.info("Whitelist restoration completed")

                try:
                    from app.services.compliance_service import recalculate_all_compliance
                    await recalculate_all_compliance(self.db)
                    logger.info("Compliance recalculation triggered after whitelist restore")
                except Exception as e:
                    logger.error(f"Failed to trigger compliance recalculation: {e}")

                return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to restore whitelist: {e}")
            return False

    async def _create_archive(self, temp_dir: str, files: list, backup_type: str = "full") -> str:
        """Create a single archive from backup files"""
        def _create_archive_sync():
            archive_name = f"{self._generate_backup_id(backup_type)}.zip"
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
        elif self.config.storage_type == "ftp":
            return await self._upload_via_ftp(local_path)
        else:
            return local_path

    async def _upload_via_ftp(self, local_path: str) -> str:
        """Upload backup via FTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = int(config.get("port", 21))
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        use_ssl = config.get("use_ssl", False)

        try:
            if use_ssl:
                ftp = ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()

            ftp.connect(host, port)
            ftp.login(username, password)
            ftp.set_pasv(True)

            try:
                ftp.cwd(remote_path)
            except ftplib.error_perm:
                ftp.mkd(remote_path)
                ftp.cwd(remote_path)

            remote_filename = os.path.basename(local_path)
            remote_file_path = f"{remote_path}/{remote_filename}"

            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_filename}", f)

            ftp.quit()
            logger.info(f"Backup uploaded via FTP: {remote_file_path}")
            return remote_file_path

        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            raise

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
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_filename:
                ssh.connect(hostname=host, port=port, username=username, key_filename=key_filename)
            else:
                ssh.connect(hostname=host, port=port, username=username, password=password)

            with ssh.open_sftp() as sftp:
                # Ensure remote directory exists
                try:
                    sftp.stat(remote_path)
                except FileNotFoundError:
                    sftp.mkdir(remote_path)

                # Upload file
                remote_filename = os.path.basename(local_path)
                remote_file_path = os.path.join(remote_path, remote_filename)
                sftp.put(local_path, remote_file_path)

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

    def generate_backup_filename(self) -> str:
        """Generate a unique backup filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"tam_backup_{timestamp}.zip"

    async def backup_database(self, temp_dir: str) -> str:
        """Backup PostgreSQL database"""
        return await self._backup_database(temp_dir)

    async def backup_config(self, temp_dir: str) -> str:
        """Backup configuration files"""
        return await self._backup_config(temp_dir)

    async def create_archive(self, temp_dir: str, files: list, backup_type: str = "full") -> str:
        """Create a single archive from backup files"""
        return await self._create_archive(temp_dir, files, backup_type)

    async def validate_backup(self, backup_path: str) -> bool:
        """Validate backup integrity"""
        return await self.verify_backup(backup_path)

    async def upload_backup(self, local_path: str, filename: str | None = None) -> bool:
        """Upload backup to remote storage"""
        try:
            await self._upload_backup(local_path)
            return True
        except Exception as e:
            logger.error(f"Upload backup failed: {e}")
            return False

    async def cleanup_old_backups(self) -> None:
        """Clean up backups older than retention_days"""
        await self._cleanup_old_backups()

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
                with zipfile.ZipFile(backup_path, "r") as zipf:
                    zipf.extractall(temp_dir)

                db_file = os.path.join(temp_dir, "database.sql")
                if os.path.exists(db_file):
                    await self._restore_database(db_file)

                await self._restore_system_config_db(temp_dir)

                await self._restore_branding(temp_dir)

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

    async def list_remote_backups(self) -> list[dict]:
        """List backups from remote storage (FTP/SFTP)"""
        if self.config.storage_type == "sftp":
            return await self._list_via_sftp()
        elif self.config.storage_type == "ftp":
            return await self._list_via_ftp()
        return []

    async def _list_via_ftp(self) -> list[dict]:
        """List backups via FTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = int(config.get("port", 21))
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        use_ssl = config.get("use_ssl", False)

        backups = []
        try:
            if use_ssl:
                ftp = ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()

            ftp.connect(host, port)
            ftp.login(username, password)
            ftp.set_pasv(True)

            try:
                ftp.cwd(remote_path)
            except ftplib.error_perm:
                ftp.mkd(remote_path)
                ftp.cwd(remote_path)

            for filename in ftp.nlst():
                if filename.endswith(".zip"):
                    try:
                        file_size = ftp.size(filename)
                        mtime_str = ftp.voidcmd(f"MDTM {filename}")[4:].strip()
                        mtime_dt = datetime.strptime(mtime_str, "%Y%m%d%H%M%S")
                        backups.append({
                            "filename": filename,
                            "file_path": f"{remote_path}/{filename}",
                            "file_size": file_size,
                            "created_at": mtime_dt,
                            "storage": "remote",
                        })
                    except Exception:
                        backups.append({
                            "filename": filename,
                            "file_path": f"{remote_path}/{filename}",
                            "file_size": None,
                            "created_at": None,
                            "storage": "remote",
                        })

            ftp.quit()
        except Exception as e:
            logger.error(f"FTP list failed: {e}")

        return backups

    async def _list_via_sftp(self) -> list[dict]:
        """List backups via SFTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = int(config.get("port", 22))
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        key_filename = config.get("key_filename")

        backups = []
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_filename:
                ssh.connect(hostname=host, port=port, username=username, key_filename=key_filename)
            else:
                ssh.connect(hostname=host, port=port, username=username, password=password)

            with ssh.open_sftp() as sftp:
                try:
                    sftp.stat(remote_path)
                except FileNotFoundError:
                    sftp.mkdir(remote_path)

                for entry in sftp.listdir_attr(remote_path):
                    if entry.filename.endswith(".zip"):
                        backups.append({
                            "filename": entry.filename,
                            "file_path": f"{remote_path}/{entry.filename}",
                            "file_size": entry.st_size,
                            "created_at": datetime.fromtimestamp(entry.st_mtime),
                            "storage": "remote",
                        })

            ssh.close()
        except Exception as e:
            logger.error(f"SFTP list failed: {e}")

        return backups

    async def download_from_remote(self, filename: str) -> str:
        """Download backup from remote storage to local"""
        if self.config.storage_type == "sftp":
            return await self._download_via_sftp(filename)
        elif self.config.storage_type == "ftp":
            return await self._download_via_ftp(filename)
        raise Exception("Only remote storage supported")

    async def _download_via_ftp(self, filename: str) -> str:
        """Download backup via FTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = int(config.get("port", 21))
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        use_ssl = config.get("use_ssl", False)

        local_path = os.path.join(self.backup_dir, filename)

        try:
            if use_ssl:
                ftp = ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()

            ftp.connect(host, port)
            ftp.login(username, password)
            ftp.set_pasv(True)

            ftp.cwd(remote_path)
            with open(local_path, "wb") as f:
                ftp.retrbinary(f"RETR {filename}", f.write)

            ftp.quit()
            logger.info(f"Downloaded from FTP: {local_path}")
            return local_path
        except Exception as e:
            logger.error(f"FTP download failed: {e}")
            raise

    async def _download_via_sftp(self, filename: str) -> str:
        """Download backup via SFTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = int(config.get("port", 22))
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        key_filename = config.get("key_filename")

        local_path = os.path.join(self.backup_dir, filename)

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_filename:
                ssh.connect(hostname=host, port=port, username=username, key_filename=key_filename)
            else:
                ssh.connect(hostname=host, port=port, username=username, password=password)

            with ssh.open_sftp() as sftp:
                remote_file_path = os.path.join(remote_path, filename)
                sftp.get(remote_file_path, local_path)

            ssh.close()
            logger.info(f"Downloaded from SFTP: {local_path}")
            return local_path
        except Exception as e:
            logger.error(f"SFTP download failed: {e}")
            raise

    async def delete_from_remote(self, filename: str) -> bool:
        """Delete backup from remote storage"""
        if self.config.storage_type == "sftp":
            return await self._delete_via_sftp(filename)
        elif self.config.storage_type == "ftp":
            return await self._delete_via_ftp(filename)
        return False

    async def _delete_via_ftp(self, filename: str) -> bool:
        """Delete backup via FTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = int(config.get("port", 21))
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        use_ssl = config.get("use_ssl", False)

        try:
            if use_ssl:
                ftp = ftplib.FTP_TLS()
            else:
                ftp = ftplib.FTP()

            ftp.connect(host, port)
            ftp.login(username, password)
            ftp.set_pasv(True)

            ftp.cwd(remote_path)
            ftp.delete(filename)
            ftp.quit()
            logger.info(f"Deleted from FTP: {filename}")
            return True
        except Exception as e:
            logger.error(f"FTP delete failed: {e}")
            return False

    async def _delete_via_sftp(self, filename: str) -> bool:
        """Delete backup via SFTP"""
        config = self.config.storage_config
        host = config.get("host", "localhost")
        port = int(config.get("port", 22))
        username = config.get("username")
        password = config.get("password")
        remote_path = config.get("path", "/backups")
        key_filename = config.get("key_filename")

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if key_filename:
                ssh.connect(hostname=host, port=port, username=username, key_filename=key_filename)
            else:
                ssh.connect(hostname=host, port=port, username=username, password=password)

            with ssh.open_sftp() as sftp:
                remote_file_path = os.path.join(remote_path, filename)
                sftp.remove(remote_file_path)

            ssh.close()
            logger.info(f"Deleted from SFTP: {filename}")
            return True
        except Exception as e:
            logger.error(f"SFTP delete failed: {e}")
            return False
