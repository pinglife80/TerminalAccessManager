"""Unit tests for backup service"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-for-testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.services.backup_service import BackupService, BackupJob


class TestBackupService:
    """Test cases for BackupService"""

    @pytest.mark.asyncio
    async def test_run_backup(self):
        """Test running a backup"""
        service = BackupService()
        service.backup_database = AsyncMock(return_value="/tmp/test_backup.sql")
        service.backup_config = AsyncMock(return_value="/tmp/test_config.tar.gz")
        service.create_archive = AsyncMock(return_value="/tmp/test_backup.zip")
        service.upload_backup = AsyncMock(return_value=True)
        service.cleanup_old_backups = AsyncMock()

        job = await service.run_backup()

        assert job.status == "completed"
        assert job.file_path is not None
        service.backup_database.assert_called_once()
        service.backup_config.assert_called_once()
        service.create_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_backup_job_status(self):
        """Test backup job status tracking"""
        job = BackupJob("test-job-id")
        assert job.status == "running"
        assert job.started_at is not None

        job.complete("/tmp/test.zip", 1024, "checksum123")
        assert job.status == "completed"
        assert job.completed_at is not None
        assert job.file_size == 1024

    @pytest.mark.asyncio
    async def test_generate_backup_filename(self):
        """Test backup filename generation"""
        service = BackupService()
        filename = service.generate_backup_filename()
        assert "tam_backup" in filename
        assert filename.endswith(".zip")

    @pytest.mark.asyncio
    async def test_validate_backup_invalid(self):
        """Test backup validation with invalid file"""
        service = BackupService()
        result = await service.validate_backup("/nonexistent/file.zip")
        assert result is False

    @pytest.mark.asyncio
    @patch("paramiko.SSHClient")
    async def test_upload_sftp(self, mock_ssh_client_class):
        """Test SFTP upload"""
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value.__enter__.return_value = mock_sftp
        mock_ssh_client_class.return_value = mock_ssh

        service = BackupService()
        service.config.storage_type = "sftp"
        service.config.storage_config = {
            "host": "backup.example.com",
            "port": 22,
            "username": "backup",
            "password": "secret",
            "path": "/backups"
        }

        result = await service.upload_backup("/tmp/test.zip", "test.zip")
        assert result is True
        mock_ssh.connect.assert_called_once()
        mock_sftp.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_backups(self):
        """Test cleanup of old backups"""
        service = BackupService()
        service.config.retention_days = 1

        # Create mock files
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            service.backup_dir = tmpdir
            # Create a file older than retention period
            old_file = os.path.join(tmpdir, "old_backup.zip")
            with open(old_file, "w") as f:
                f.write("test")
            os.utime(old_file, (0, 0))  # Set old timestamp

            await service.cleanup_old_backups()

            assert not os.path.exists(old_file)