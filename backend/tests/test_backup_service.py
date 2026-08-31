"""Unit tests for the backup service (app/services/backup_service.py).

Covers the full backup lifecycle end-to-end without real network or database
I/O: configuration dataclasses, DB config load/save, per-entity backups
(database/config/logs/branding/whitelist), archive/checksum, FTP/SFTP
upload/list/download/delete, retention cleanup, and restore flows. Subprocess
(pg_dump/pg_restore), paramiko, and ftplib boundaries are mocked.
"""

import os
import types
import zipfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services import backup_service as bs
from app.services.backup_service import BackupConfig, BackupJob, BackupService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ns(**kwargs):
    """Build a lightweight attribute object (simulates a DB model row)."""
    return types.SimpleNamespace(**kwargs)


def _make_rows_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _make_scalar_result(scalar):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    return result


def _make_db():
    """Build a mock AsyncSession with the right sync/async method split."""
    from tests.conftest import make_mock_async_session
    db = make_mock_async_session()
    db.begin_nested = AsyncMock(return_value=_savepoint())
    return db


def _savepoint():
    sp = MagicMock()
    sp.commit = AsyncMock()
    sp.rollback = AsyncMock()
    return sp


def _subprocess(returncode=0, stdout=b"", stderr=b""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def _make_backup_config(**overrides):
    cfg = BackupConfig()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ===========================================================================
# Data classes
# ===========================================================================

class TestBackupConfig:
    def test_defaults(self):
        cfg = BackupConfig()
        assert cfg.enabled is False
        assert cfg.schedule == "0 2 * * *"
        assert cfg.retention_days == 7
        assert cfg.storage_type == "local"
        assert cfg.storage_config == {}
        assert cfg.backup_database is True
        assert cfg.backup_config is True
        assert cfg.backup_whitelist is True
        assert cfg.backup_logs is False
        assert cfg.encrypt_backup is True

    def test_storage_config_default_factory_is_independent(self):
        a = BackupConfig()
        b = BackupConfig()
        a.storage_config["x"] = 1
        assert b.storage_config == {}


class TestBackupJob:
    def test_initial_state(self):
        job = BackupJob("job-1")
        assert job.id == "job-1"
        assert job.status == "running"
        assert job.started_at is not None
        assert job.completed_at is None
        assert job.file_path is None
        assert job.checksum is None
        assert job.error_message is None

    def test_complete(self):
        job = BackupJob("job-1")
        job.complete("/tmp/f.zip", 1024, "abc123")
        assert job.status == "completed"
        assert job.completed_at is not None
        assert job.file_path == "/tmp/f.zip"
        assert job.file_size == 1024
        assert job.checksum == "abc123"


# ===========================================================================
# __init__
# ===========================================================================

class TestInit:
    def test_injected_config(self):
        cfg = _make_backup_config(enabled=True)
        svc = BackupService(config=cfg)
        assert svc.config is cfg

    def test_permission_error_falls_back_to_tmp(self):
        with patch.object(os, "makedirs", side_effect=[PermissionError, None]):
            svc = BackupService()
        assert svc.backup_dir == "/tmp/backups"


# ===========================================================================
# load_config / save_config
# ===========================================================================

class TestLoadConfig:
    @pytest.mark.asyncio
    async def test_no_db_returns_current(self):
        svc = BackupService()
        assert await svc.load_config() is svc.config

    @pytest.mark.asyncio
    async def test_existing_model_maps_fields(self):
        db = _make_db()
        model = _ns(
            enabled=True, schedule="0 3 * * *", retention_days=30,
            storage_type="sftp", storage_config={"a": 1},
            backup_database=False, backup_config=True,
            backup_whitelist=True, backup_logs=True, encrypt_backup=False,
        )
        db.execute = AsyncMock(return_value=_make_scalar_result(model))
        svc = BackupService(db=db)

        cfg = await svc.load_config()

        assert cfg.enabled is True
        assert cfg.retention_days == 30
        assert cfg.storage_type == "sftp"
        assert cfg.backup_database is False
        assert cfg.backup_logs is True
        assert cfg.encrypt_backup is False

    @pytest.mark.asyncio
    async def test_missing_model_creates_new(self):
        db = _make_db()
        db.execute = AsyncMock(return_value=_make_scalar_result(None))
        svc = BackupService(db=db)

        cfg = await svc.load_config()

        assert isinstance(cfg, BackupConfig)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_returns_current(self):
        db = _make_db()
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        svc = BackupService(db=db)
        assert await svc.load_config() is svc.config


class TestSaveConfig:
    @pytest.mark.asyncio
    async def test_no_db_assigns_locally(self):
        svc = BackupService()
        cfg = _make_backup_config(enabled=True)
        await svc.save_config(cfg)
        assert svc.config is cfg

    @pytest.mark.asyncio
    async def test_updates_existing_model(self):
        db = _make_db()
        model = MagicMock()
        db.execute = AsyncMock(return_value=_make_scalar_result(model))
        svc = BackupService(db=db)
        cfg = _make_backup_config(enabled=True, retention_days=14)

        await svc.save_config(cfg)

        assert model.enabled is True
        assert model.retention_days == 14
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_new_model(self):
        db = _make_db()
        db.execute = AsyncMock(return_value=_make_scalar_result(None))
        svc = BackupService(db=db)
        await svc.save_config(_make_backup_config(enabled=True))
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_re_raises(self):
        db = _make_db()
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        svc = BackupService(db=db)
        with pytest.raises(RuntimeError):
            await svc.save_config(_make_backup_config())


# ===========================================================================
# _generate_backup_id / generate_backup_filename
# ===========================================================================

class TestNames:
    def test_generate_backup_id(self):
        svc = BackupService()
        bid = svc._generate_backup_id("database")
        assert bid.startswith("backup_database_")

    def test_generate_backup_filename(self):
        svc = BackupService()
        fn = svc.generate_backup_filename()
        assert fn.startswith("tam_backup_")
        assert fn.endswith(".zip")


# ===========================================================================
# _backup_database
# ===========================================================================

class TestBackupDatabase:
    @pytest.mark.asyncio
    async def test_parses_asyncpg_url(self):
        svc = BackupService()
        proc = _subprocess()
        with patch.object(settings, "DATABASE_URL", "postgresql+asyncpg://user:p%40ss@db-host:5433/mydb"), \
             patch.object(bs.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)) as sp:
            path = await svc._backup_database("/tmp")

        assert path == "/tmp/database.sql"
        cmd = sp.call_args.args
        assert cmd[0] == "pg_dump"
        assert cmd[cmd.index("-h") + 1] == "db-host"
        assert cmd[cmd.index("-p") + 1] == "5433"
        assert cmd[cmd.index("-U") + 1] == "user"
        assert cmd[cmd.index("-d") + 1] == "mydb"
        assert sp.call_args.kwargs["env"]["PGPASSWORD"] == "p@ss"

    @pytest.mark.asyncio
    async def test_parses_standard_url(self):
        svc = BackupService()
        proc = _subprocess()
        with patch.object(settings, "DATABASE_URL", "postgresql://u:p@h/9db"), \
             patch.object(bs.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)) as sp:
            await svc._backup_database("/tmp")

        cmd = sp.call_args.args
        assert cmd[cmd.index("-h") + 1] == "h"
        assert cmd[cmd.index("-p") + 1] == "5432"
        assert cmd[cmd.index("-d") + 1] == "9db"

    @pytest.mark.asyncio
    async def test_postgres_fallback(self):
        svc = BackupService()
        proc = _subprocess()
        with patch.object(settings, "DATABASE_URL", ""), \
             patch.object(settings, "DB_HOST", "pg"), \
             patch.object(settings, "DB_USER", "pu"), \
             patch.object(settings, "DB_NAME", "pdb"), \
             patch.object(settings, "DB_PASSWORD", "pp"), \
             patch.object(settings, "DB_PORT", 15432), \
             patch.object(bs.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)) as sp:
            await svc._backup_database("/tmp")

        cmd = sp.call_args.args
        assert cmd[cmd.index("-h") + 1] == "pg"
        assert cmd[cmd.index("-p") + 1] == "15432"
        assert cmd[cmd.index("-U") + 1] == "pu"
        assert cmd[cmd.index("-d") + 1] == "pdb"

    @pytest.mark.asyncio
    async def test_db_fallback(self):
        svc = BackupService()
        proc = _subprocess()
        with patch.object(settings, "DATABASE_URL", ""), \
             patch.object(settings, "DB_HOST", "dbh"), \
             patch.object(settings, "DB_USER", "dbu"), \
             patch.object(settings, "DB_NAME", "dbn"), \
             patch.object(settings, "DB_PASSWORD", "dbp"), \
             patch.object(settings, "DB_PORT", 6432), \
             patch.object(bs.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)) as sp:
            await svc._backup_database("/tmp")

        cmd = sp.call_args.args
        assert cmd[cmd.index("-h") + 1] == "dbh"
        assert cmd[cmd.index("-p") + 1] == "6432"
        assert cmd[cmd.index("-U") + 1] == "dbu"

    @pytest.mark.asyncio
    async def test_no_host_raises(self):
        svc = BackupService()
        with patch.object(settings, "DATABASE_URL", ""), \
             patch.object(settings, "DB_HOST", ""):
            with pytest.raises(Exception, match="not configured"):
                await svc._backup_database("/tmp")

    @pytest.mark.asyncio
    async def test_failure_returncode_raises(self):
        svc = BackupService()
        proc = _subprocess(returncode=1, stderr=b"dump error")
        with patch.object(settings, "DATABASE_URL", "postgresql://u:p@h/db"), \
             patch.object(bs.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)):
            with pytest.raises(Exception, match="dump error"):
                await svc._backup_database("/tmp")


# ===========================================================================
# _backup_config
# ===========================================================================

class TestBackupConfigBackup:
    @pytest.mark.asyncio
    async def test_creates_zip_when_no_files_found(self, tmp_path):
        svc = BackupService()
        with patch.object(os.path, "exists", return_value=False):
            result = await svc._backup_config(str(tmp_path))

        assert result == os.path.join(str(tmp_path), "config.zip")
        assert os.path.exists(result)

    @pytest.mark.asyncio
    async def test_copies_found_file(self, tmp_path):
        # Park a real docker-compose.yml in cwd search path via tmp cwd.
        svc = BackupService()
        real_src = tmp_path / "docker-compose.yml"
        real_src.write_text("version: '3'")

        with patch.object(os.path, "exists", side_effect=lambda p: p == str(real_src)):
            # search_paths includes '.', so symlink cwd is avoided; instead
            # shutil.copy is real but source only exists at tmp_path. Patch the
            # search_paths indirectly by making copy a no-op for zip coverage.
            with patch.object(bs.shutil, "copy", return_value=None):
                result = await svc._backup_config(str(tmp_path))

        assert result == os.path.join(str(tmp_path), "config.zip")


# ===========================================================================
# _backup_logs
# ===========================================================================

class TestBackupLogs:
    @pytest.mark.asyncio
    async def test_creates_empty_archive_when_no_log_dirs(self, tmp_path):
        svc = BackupService()
        with patch.object(os.path, "isdir", return_value=False):
            result = await svc._backup_logs(str(tmp_path))
        assert result == os.path.join(str(tmp_path), "logs.zip")
        assert os.path.exists(result)


# ===========================================================================
# _backup_branding
# ===========================================================================

class TestBackupBranding:
    @pytest.mark.asyncio
    async def test_copies_branding_files(self, tmp_path):
        upload_dir = tmp_path / "uploads"
        brand_dir = upload_dir / "branding"
        brand_dir.mkdir(parents=True)
        (brand_dir / "logo.png").write_bytes(b"png")

        svc = BackupService()
        with patch.object(settings, "UPLOAD_DIR", str(upload_dir)):
            result = await svc._backup_branding(str(tmp_path))

        assert result == os.path.join(str(tmp_path), "branding.zip")
        with zipfile.ZipFile(result) as z:
            names = z.namelist()
        assert any("logo.png" in n for n in names)

    @pytest.mark.asyncio
    async def test_no_branding_dir_still_archives(self, tmp_path):
        svc = BackupService()
        with patch.object(settings, "UPLOAD_DIR", str(tmp_path)):
            result = await svc._backup_branding(str(tmp_path))
        assert os.path.exists(result)


# ===========================================================================
# _backup_system_config_db
# ===========================================================================

class TestBackupSystemConfigDb:
    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, tmp_path):
        svc = BackupService()
        assert await svc._backup_system_config_db(str(tmp_path)) == ""

    @pytest.mark.asyncio
    async def test_backs_up_all_tables(self, tmp_path):
        db = _make_db()
        rows = [
            _ns(key="k1", value="v1", category="c", value_type="int",
                 description="d", is_readonly=False),
        ]
        empty_rows = []
        db.execute = AsyncMock(side_effect=[
            _make_rows_result(rows),            # SystemConfig
            _make_rows_result([]),              # NotificationChannel
            _make_rows_result([]),              # NotificationRule
            _make_rows_result([]),              # NotificationTemplate
            _make_rows_result([]),              # AuthConfig
            _make_rows_result([]),              # DataSource
        ])
        svc = BackupService(db=db)

        result = await svc._backup_system_config_db(str(tmp_path))

        assert result.endswith("system_config.json")
        with open(result) as f:
            import json
            data = json.load(f)
        assert data["system_config"][0]["key"] == "k1"

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self, tmp_path):
        db = _make_db()
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        svc = BackupService(db=db)
        assert await svc._backup_system_config_db(str(tmp_path)) == ""


# ===========================================================================
# backup_whitelist
# ===========================================================================

class TestBackupWhitelist:
    @pytest.mark.asyncio
    async def test_no_db_returns_empty(self, tmp_path):
        svc = BackupService()
        assert await svc.backup_whitelist(str(tmp_path)) == ""

    @pytest.mark.asyncio
    async def test_backs_up_whitelist(self, tmp_path, mock_async_session):
        db = mock_async_session
        row = _ns(
            id=1, mac_address="AA:BB", mac_address_normalized="aa:bb",
            ip_pattern="10.0.0.1", pattern_type="single_ip",
            comments="c", added_by="admin", created_at=datetime(2024, 1, 1),
        )
        db.execute = AsyncMock(return_value=_make_rows_result([row]))
        svc = BackupService(db=db)

        result = await svc.backup_whitelist(str(tmp_path))

        assert result == os.path.join(str(tmp_path), "whitelist.zip")
        with zipfile.ZipFile(result) as z:
            assert "whitelist/whitelist.json" in z.namelist()

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self, tmp_path, mock_async_session):
        db = mock_async_session
        db.execute = AsyncMock(side_effect=RuntimeError("boom"))
        svc = BackupService(db=db)
        assert await svc.backup_whitelist(str(tmp_path)) == ""


# ===========================================================================
# archive / checksum / verify / validate
# ===========================================================================

class TestArchiveAndChecksum:
    @pytest.mark.asyncio
    async def test_create_archive(self, tmp_path):
        src = tmp_path / "a.txt"
        src.write_text("hello")
        svc = BackupService()
        svc.backup_dir = str(tmp_path)
        result = await svc.create_archive(str(tmp_path), [str(src)], "full")
        assert result.endswith(".zip")
        assert os.path.exists(result)

    @pytest.mark.asyncio
    async def test_calculate_checksum(self, tmp_path):
        f = tmp_path / "x.bin"
        f.write_bytes(b"abc")
        svc = BackupService()
        import hashlib
        expected = hashlib.sha256(b"abc").hexdigest()
        assert await svc._calculate_checksum(str(f)) == expected

    @pytest.mark.asyncio
    async def test_verify_backup_missing(self):
        svc = BackupService()
        assert await svc.verify_backup("/nonexistent.zip") is False

    @pytest.mark.asyncio
    async def test_verify_backup_valid(self, tmp_path):
        z = tmp_path / "ok.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("a.txt", "x")
        svc = BackupService()
        assert await svc.verify_backup(str(z)) is True

    @pytest.mark.asyncio
    async def test_verify_backup_corrupt(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_text("not a zip")
        svc = BackupService()
        assert await svc.verify_backup(str(bad)) is False

    @pytest.mark.asyncio
    async def test_validate_backup_valid(self, tmp_path):
        z = tmp_path / "ok.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("a.txt", "x")
        svc = BackupService()
        assert await svc.validate_backup(str(z)) is True


# ===========================================================================
# _upload_backup dispatcher + wrappers
# ===========================================================================

class TestUploadDispatcher:
    @pytest.mark.asyncio
    async def test_local_returns_same_path(self):
        svc = BackupService()
        assert await svc._upload_backup("/tmp/f.zip") == "/tmp/f.zip"

    @pytest.mark.asyncio
    async def test_ftp_dispatch(self):
        svc = BackupService()
        svc.config.storage_type = "ftp"
        with patch.object(svc, "_upload_via_ftp", AsyncMock(return_value="/r/f.zip")) as m:
            assert await svc._upload_backup("/tmp/f.zip") == "/r/f.zip"
        m.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sftp_dispatch(self):
        svc = BackupService()
        svc.config.storage_type = "sftp"
        with patch.object(svc, "_upload_via_sftp", AsyncMock(return_value="/r/f.zip")) as m:
            assert await svc._upload_backup("/tmp/f.zip") == "/r/f.zip"
        m.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_backup_success(self):
        svc = BackupService()
        with patch.object(svc, "_upload_backup", AsyncMock(return_value="/r")):
            assert await svc.upload_backup("/tmp/f.zip") is True

    @pytest.mark.asyncio
    async def test_upload_backup_failure(self):
        svc = BackupService()
        with patch.object(svc, "_upload_backup", AsyncMock(side_effect=RuntimeError("x"))):
            assert await svc.upload_backup("/tmp/f.zip") is False


# ===========================================================================
# _upload_via_ftp
# ===========================================================================

class TestUploadViaFtp:
    @pytest.mark.asyncio
    async def test_success_non_ssl(self, tmp_path):
        f = tmp_path / "b.zip"
        f.write_bytes(b"data")
        svc = BackupService()
        svc.config.storage_config = {"host": "h", "port": 21, "username": "u",
                                     "password": "p", "path": "/backups"}
        ftp = MagicMock()
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            result = await svc._upload_via_ftp(str(f))

        assert result == "/backups/b.zip"
        ftp.connect.assert_called_once_with("h", 21)
        ftp.login.assert_called_once_with("u", "p")
        ftp.storbinary.assert_called_once()

    @pytest.mark.asyncio
    async def test_ssl_and_mkdir_on_missing_dir(self, tmp_path):
        f = tmp_path / "b.zip"
        f.write_bytes(b"data")
        svc = BackupService()
        svc.config.storage_config = {"host": "h", "use_ssl": True, "path": "/bk"}
        ftp = MagicMock()
        ftp.cwd.side_effect = [bs.ftplib.error_perm("no dir"), None]
        with patch.object(bs.ftplib, "FTP_TLS", return_value=ftp):
            result = await svc._upload_via_ftp(str(f))

        assert result == "/bk/b.zip"
        ftp.mkd.assert_called_once_with("/bk")

    @pytest.mark.asyncio
    async def test_error_raises(self, tmp_path):
        f = tmp_path / "b.zip"
        f.write_bytes(b"data")
        svc = BackupService()
        svc.config.storage_config = {"host": "h"}
        ftp = MagicMock()
        ftp.connect.side_effect = RuntimeError("conn")
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            with pytest.raises(RuntimeError):
                await svc._upload_via_ftp(str(f))


# ===========================================================================
# _upload_via_sftp
# ===========================================================================

class TestUploadViaSftp:
    @pytest.mark.asyncio
    async def test_success_password(self, tmp_path):
        f = tmp_path / "b.zip"
        f.write_bytes(b"data")
        svc = BackupService()
        svc.config.storage_config = {"host": "h", "port": 22, "username": "u",
                                     "password": "p", "path": "/backups"}
        ssh = MagicMock()
        sftp = MagicMock()
        ssh.open_sftp.return_value.__enter__.return_value = sftp
        ssh.open_sftp.return_value.__exit__.return_value = False
        with patch.object(bs.paramiko, "SSHClient", return_value=ssh):
            result = await svc._upload_via_sftp(str(f))

        assert result.endswith("b.zip")
        ssh.connect.assert_called_once_with(hostname="h", port=22, username="u", password="p")
        sftp.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_filename_and_mkdir(self, tmp_path):
        f = tmp_path / "b.zip"
        f.write_bytes(b"data")
        svc = BackupService()
        svc.config.storage_config = {"host": "h", "username": "u",
                                     "key_filename": "/k.pem", "path": "/bk"}
        ssh = MagicMock()
        sftp = MagicMock()
        ssh.open_sftp.return_value.__enter__.return_value = sftp
        ssh.open_sftp.return_value.__exit__.return_value = False
        sftp.stat.side_effect = FileNotFoundError
        with patch.object(bs.paramiko, "SSHClient", return_value=ssh):
            await svc._upload_via_sftp(str(f))

        ssh.connect.assert_called_once_with(hostname="h", port=22, username="u",
                                            key_filename="/k.pem")
        sftp.mkdir.assert_called_once_with("/bk")

    @pytest.mark.asyncio
    async def test_error_raises(self, tmp_path):
        f = tmp_path / "b.zip"
        f.write_bytes(b"data")
        svc = BackupService()
        svc.config.storage_config = {"host": "h"}
        ssh = MagicMock()
        ssh.connect.side_effect = RuntimeError("x")
        with patch.object(bs.paramiko, "SSHClient", return_value=ssh):
            with pytest.raises(RuntimeError):
                await svc._upload_via_sftp(str(f))


# ===========================================================================
# _cleanup_old_backups
# ===========================================================================

class TestCleanupOldBackups:
    @pytest.mark.asyncio
    async def test_removes_empty_and_old_files(self, tmp_path):
        svc = BackupService()
        svc.backup_dir = str(tmp_path)
        svc.config.retention_days = 1

        empty = tmp_path / "empty.zip"
        empty.write_bytes(b"")
        old = tmp_path / "old.zip"
        old.write_bytes(b"x")
        os.utime(old, (0, 0))
        fresh = tmp_path / "fresh.zip"
        fresh.write_bytes(b"y")

        await svc._cleanup_old_backups()

        assert not os.path.exists(empty)
        assert not os.path.exists(old)
        assert os.path.exists(fresh)

    @pytest.mark.asyncio
    async def test_remote_cleanup(self, tmp_path):
        svc = BackupService()
        svc.backup_dir = str(tmp_path)
        svc.config.retention_days = 1
        svc.config.storage_type = "sftp"
        old_dt = datetime(2000, 1, 1)
        svc.list_remote_backups = AsyncMock(return_value=[
            {"filename": "old.zip", "created_at": old_dt},
            {"filename": "nofile.zip", "created_at": None},
        ])
        svc.delete_from_remote = AsyncMock(return_value=True)

        await svc._cleanup_old_backups()

        svc.delete_from_remote.assert_awaited_once_with("old.zip")

    @pytest.mark.asyncio
    async def test_remote_cleanup_error_swallowed(self, tmp_path):
        svc = BackupService()
        svc.backup_dir = str(tmp_path)
        svc.config.retention_days = 1
        svc.config.storage_type = "sftp"
        svc.list_remote_backups = AsyncMock(side_effect=RuntimeError("boom"))

        await svc._cleanup_old_backups()  # no raise

    @pytest.mark.asyncio
    async def test_cleanup_old_backups_wrapper(self):
        svc = BackupService()
        with patch.object(svc, "_cleanup_old_backups", AsyncMock()) as m:
            await svc.cleanup_old_backups()
        m.assert_awaited_once()


# ===========================================================================
# list_remote_backups / _list_via_ftp / _list_via_sftp
# ===========================================================================

class TestListRemote:
    @pytest.mark.asyncio
    async def test_local_returns_empty(self):
        svc = BackupService()
        assert await svc.list_remote_backups() == []

    @pytest.mark.asyncio
    async def test_ftp_dispatch(self):
        svc = BackupService()
        svc.config.storage_type = "ftp"
        with patch.object(svc, "_list_via_ftp", AsyncMock(return_value=[{"x": 1}])):
            assert await svc.list_remote_backups() == [{"x": 1}]

    @pytest.mark.asyncio
    async def test_ftp_success_with_mdtm(self):
        svc = BackupService()
        svc.config.storage_config = {"host": "h", "path": "/bk"}
        ftp = MagicMock()
        ftp.nlst.return_value = ["a.zip"]
        ftp.size.return_value = 123
        ftp.voidcmd.return_value = "213 20260101000000"
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            result = await svc._list_via_ftp()

        assert len(result) == 1
        assert result[0]["filename"] == "a.zip"
        assert result[0]["file_size"] == 123

    @pytest.mark.asyncio
    async def test_ftp_entry_fallback_on_error(self):
        svc = BackupService()
        svc.config.storage_config = {"host": "h", "path": "/bk"}
        ftp = MagicMock()
        ftp.nlst.return_value = ["a.zip"]
        ftp.size.side_effect = RuntimeError("no size")
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            result = await svc._list_via_ftp()

        assert result[0]["file_size"] is None
        assert result[0]["created_at"] is None

    @pytest.mark.asyncio
    async def test_ftp_connect_error_returns_empty(self):
        svc = BackupService()
        svc.config.storage_config = {"host": "h"}
        ftp = MagicMock()
        ftp.connect.side_effect = RuntimeError("x")
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            assert await svc._list_via_ftp() == []

    @pytest.mark.asyncio
    async def test_sftp_success(self):
        svc = BackupService()
        svc.config.storage_config = {"host": "h", "username": "u", "path": "/bk"}
        ssh = MagicMock()
        sftp = MagicMock()
        ssh.open_sftp.return_value.__enter__.return_value = sftp
        ssh.open_sftp.return_value.__exit__.return_value = False
        entry = MagicMock()
        entry.filename = "a.zip"
        entry.st_size = 10
        entry.st_mtime = 0
        sftp.listdir_attr.return_value = [entry]
        with patch.object(bs.paramiko, "SSHClient", return_value=ssh):
            result = await svc._list_via_sftp()

        assert result[0]["filename"] == "a.zip"
        assert result[0]["file_size"] == 10


# ===========================================================================
# download_from_remote / _download_via_ftp / _download_via_sftp
# ===========================================================================

class TestDownload:
    @pytest.mark.asyncio
    async def test_local_dispatch_raises(self):
        svc = BackupService()
        with pytest.raises(Exception, match="remote"):
            await svc.download_from_remote("a.zip")

    @pytest.mark.asyncio
    async def test_ftp_download(self, tmp_path):
        svc = BackupService()
        svc.backup_dir = str(tmp_path)
        svc.config.storage_config = {"host": "h", "path": "/bk"}
        ftp = MagicMock()
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            result = await svc._download_via_ftp("a.zip")

        assert result == os.path.join(str(tmp_path), "a.zip")
        ftp.retrbinary.assert_called_once()

    @pytest.mark.asyncio
    async def test_sftp_download(self, tmp_path):
        svc = BackupService()
        svc.backup_dir = str(tmp_path)
        svc.config.storage_config = {"host": "h", "username": "u", "path": "/bk"}
        ssh = MagicMock()
        sftp = MagicMock()
        ssh.open_sftp.return_value.__enter__.return_value = sftp
        ssh.open_sftp.return_value.__exit__.return_value = False
        with patch.object(bs.paramiko, "SSHClient", return_value=ssh):
            result = await svc._download_via_sftp("a.zip")

        assert result == os.path.join(str(tmp_path), "a.zip")
        sftp.get.assert_called_once()


# ===========================================================================
# delete_from_remote / _delete_via_ftp / _delete_via_sftp
# ===========================================================================

class TestDelete:
    @pytest.mark.asyncio
    async def test_local_returns_false(self):
        svc = BackupService()
        assert await svc.delete_from_remote("a.zip") is False

    @pytest.mark.asyncio
    async def test_ftp_delete_success(self):
        svc = BackupService()
        svc.config.storage_type = "ftp"
        svc.config.storage_config = {"host": "h", "path": "/bk"}
        ftp = MagicMock()
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            assert await svc._delete_via_ftp("a.zip") is True
        ftp.delete.assert_called_once_with("a.zip")

    @pytest.mark.asyncio
    async def test_ftp_delete_failure(self):
        svc = BackupService()
        svc.config.storage_config = {"host": "h"}
        ftp = MagicMock()
        ftp.connect.side_effect = RuntimeError("x")
        with patch.object(bs.ftplib, "FTP", return_value=ftp):
            assert await svc._delete_via_ftp("a.zip") is False

    @pytest.mark.asyncio
    async def test_sftp_delete_success(self):
        svc = BackupService()
        svc.config.storage_type = "sftp"
        svc.config.storage_config = {"host": "h", "username": "u", "path": "/bk"}
        ssh = MagicMock()
        sftp = MagicMock()
        ssh.open_sftp.return_value.__enter__.return_value = sftp
        ssh.open_sftp.return_value.__exit__.return_value = False
        with patch.object(bs.paramiko, "SSHClient", return_value=ssh):
            assert await svc._delete_via_sftp("a.zip") is True
        sftp.remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_sftp_delete_failure(self):
        svc = BackupService()
        svc.config.storage_config = {"host": "h"}
        ssh = MagicMock()
        ssh.connect.side_effect = RuntimeError("x")
        with patch.object(bs.paramiko, "SSHClient", return_value=ssh):
            assert await svc._delete_via_sftp("a.zip") is False


# ===========================================================================
# run_backup
# ===========================================================================

class TestRunBackup:
    @pytest.mark.asyncio
    async def test_full_backup_local_success(self):
        svc = BackupService()
        svc.backup_database = AsyncMock(return_value="/tmp/db.sql")
        svc.backup_config = AsyncMock(return_value="/tmp/cfg.zip")
        svc._backup_system_config_db = AsyncMock(return_value="/tmp/sys.json")
        svc._backup_branding = AsyncMock(return_value="/tmp/brand.zip")
        svc.backup_whitelist = AsyncMock(return_value="/tmp/wl.zip")
        svc._backup_logs = AsyncMock(return_value="/tmp/logs.zip")
        svc.create_archive = AsyncMock(return_value="/tmp/full.zip")
        svc._calculate_checksum = AsyncMock(return_value="abc123")
        svc._upload_backup = AsyncMock(return_value="/tmp/full.zip")
        svc.cleanup_old_backups = AsyncMock()

        with patch("app.services.event_emitter.emit_backup_completed", AsyncMock()) as emit_ok, \
             patch("app.services.event_emitter.emit_backup_failed", AsyncMock()) as emit_fail:
            job = await svc.run_backup("full")

        assert job.status == "completed"
        assert job.file_path == "/tmp/full.zip"
        svc.cleanup_old_backups.assert_awaited_once()
        emit_ok.assert_awaited_once()
        emit_fail.assert_not_called()

    @pytest.mark.asyncio
    async def test_database_only_backup(self):
        svc = BackupService()
        svc.backup_database = AsyncMock(return_value="/tmp/db.sql")
        svc.backup_config = AsyncMock()
        svc.backup_whitelist = AsyncMock()
        svc._backup_logs = AsyncMock()
        svc.create_archive = AsyncMock(return_value="/tmp/db.zip")
        svc.cleanup_old_backups = AsyncMock()

        with patch("app.services.event_emitter.emit_backup_completed", AsyncMock()):
            job = await svc.run_backup("database")

        svc.backup_database.assert_awaited_once()
        svc.backup_config.assert_not_called()
        svc.backup_whitelist.assert_not_called()
        svc._backup_logs.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_emits_failed(self):
        svc = BackupService()
        svc.backup_database = AsyncMock(side_effect=RuntimeError("dump fail"))
        svc.backup_config = AsyncMock(return_value="/tmp/cfg.zip")
        svc._backup_system_config_db = AsyncMock(return_value="")
        svc._backup_branding = AsyncMock(return_value="")
        svc.backup_whitelist = AsyncMock(return_value="")
        svc._backup_logs = AsyncMock(return_value="")
        svc.create_archive = AsyncMock(return_value="/tmp/full.zip")
        svc.cleanup_old_backups = AsyncMock()

        with patch("app.services.event_emitter.emit_backup_completed", AsyncMock()) as emit_ok, \
             patch("app.services.event_emitter.emit_backup_failed", AsyncMock()) as emit_fail:
            job = await svc.run_backup("full")

        assert job.status == "failed"
        assert "dump fail" in job.error_message
        emit_fail.assert_awaited_once()
        emit_ok.assert_not_called()


# ===========================================================================
# restore flows
# ===========================================================================

class TestRestoreSystemConfigDb:
    @pytest.mark.asyncio
    async def test_missing_file_returns_false(self, tmp_path):
        svc = BackupService(db=_make_db())
        assert await svc._restore_system_config_db(str(tmp_path)) is False

    @pytest.mark.asyncio
    async def test_no_db_returns_false(self, tmp_path):
        os.makedirs(os.path.join(str(tmp_path), "config"), exist_ok=True)
        with open(os.path.join(str(tmp_path), "config", "system_config.json"), "w") as f:
            f.write("{}")
        svc = BackupService()
        assert await svc._restore_system_config_db(str(tmp_path)) is False

    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        os.makedirs(os.path.join(str(tmp_path), "config"), exist_ok=True)
        data = {"system_config": [{}]}
        with open(os.path.join(str(tmp_path), "config", "system_config.json"), "w") as f:
            import json
            json.dump(data, f)

        db = _make_db()
        db.execute = AsyncMock()
        svc = BackupService(db=db)

        assert await svc._restore_system_config_db(str(tmp_path)) is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure_rolls_back(self, tmp_path):
        os.makedirs(os.path.join(str(tmp_path), "config"), exist_ok=True)
        with open(os.path.join(str(tmp_path), "config", "system_config.json"), "w") as f:
            f.write("{bad json")

        db = _make_db()
        svc = BackupService(db=db)
        assert await svc._restore_system_config_db(str(tmp_path)) is False
        db.rollback.assert_awaited_once()


class TestRestoreBranding:
    @pytest.mark.asyncio
    async def test_missing_zip_returns_false(self, tmp_path, tmp_path_factory):
        svc = BackupService()
        assert await svc._restore_branding(str(tmp_path)) is False

    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        # Branding zip with a single file.
        brand_src = tmp_path / "src"
        brand_src.mkdir()
        (brand_src / "logo.png").write_bytes(b"png")
        brand_zip = tmp_path / "branding.zip"
        with zipfile.ZipFile(brand_zip, "w") as zf:
            zf.write(str(brand_src / "logo.png"), "branding/logo.png")

        upload = tmp_path / "upload"
        svc = BackupService()
        with patch.object(settings, "UPLOAD_DIR", str(upload)):
            assert await svc._restore_branding(str(tmp_path)) is True
        assert (upload / "branding" / "logo.png").exists()


class TestRestoreLogsFromZip:
    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        logs_zip = tmp_path / "logs.zip"
        with zipfile.ZipFile(logs_zip, "w") as zf:
            zf.writestr("app.log", "hello")

        svc = BackupService()
        real_isdir = os.path.isdir
        with patch.object(
            os.path,
            "isdir",
            side_effect=lambda p: False if p == "/var/log/tam" else real_isdir(p),
        ):
            result = await svc._restore_logs_from_zip(str(logs_zip))
        assert result is True

    @pytest.mark.asyncio
    async def test_error_returns_false(self):
        svc = BackupService()
        assert await svc._restore_logs_from_zip("/nonexistent.zip") is False


class TestRestoreWhitelist:
    @pytest.mark.asyncio
    async def test_corrupt_backup_raises(self):
        svc = BackupService()
        with patch.object(svc, "verify_backup", AsyncMock(return_value=False)):
            with pytest.raises(Exception, match="corrupted"):
                await svc.restore_whitelist("/bad.zip")

    @pytest.mark.asyncio
    async def test_no_db_returns_false(self):
        svc = BackupService()
        with patch.object(svc, "verify_backup", AsyncMock(return_value=True)):
            assert await svc.restore_whitelist("/ok.zip") is False

    @pytest.mark.asyncio
    async def test_success_nested_json(self, tmp_path, mock_async_session):
        # Build a whitelist.zip with nested whitelist/whitelist.json
        wl_dir = tmp_path / "wl"
        wl_dir.mkdir()
        (wl_dir / "whitelist.json").write_text(
            '[{"mac_address": "AA", "pattern_type": "single_ip"}]'
        )
        wl_zip = tmp_path / "whitelist.zip"
        with zipfile.ZipFile(wl_zip, "w") as zf:
            zf.write(str(wl_dir / "whitelist.json"), "whitelist/whitelist.json")

        db = mock_async_session
        db.execute = AsyncMock()
        svc = BackupService(db=db)
        with patch.object(svc, "verify_backup", AsyncMock(return_value=True)), \
             patch("app.services.compliance_service.ComplianceService.recalculate_all_compliance", AsyncMock()):
            assert await svc.restore_whitelist(str(wl_zip)) is True
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_restore_from_json_success(self, tmp_path, mock_async_session):
        json_file = tmp_path / "whitelist.json"
        json_file.write_text('[{"mac_address": "BB", "pattern_type": "single_ip"}]')

        db = mock_async_session
        db.execute = AsyncMock()
        svc = BackupService(db=db)
        with patch("app.services.compliance_service.ComplianceService.recalculate_all_compliance", AsyncMock()):
            assert await svc._restore_whitelist_from_json(str(json_file)) is True
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_restore_from_json_no_db(self, tmp_path):
        json_file = tmp_path / "whitelist.json"
        json_file.write_text("[]")
        svc = BackupService()
        assert await svc._restore_whitelist_from_json(str(json_file)) is False

    @pytest.mark.asyncio
    async def test_restore_from_json_error(self, tmp_path, mock_async_session):
        json_file = tmp_path / "whitelist.json"
        json_file.write_text("{bad json")
        db = mock_async_session
        svc = BackupService(db=db)
        assert await svc._restore_whitelist_from_json(str(json_file)) is False
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restore_from_zip_no_db(self, tmp_path):
        wl_zip = tmp_path / "w.zip"
        with zipfile.ZipFile(wl_zip, "w") as zf:
            zf.writestr("whitelist/whitelist.json", "[]")
        svc = BackupService()
        assert await svc._restore_whitelist_from_zip(str(wl_zip)) is False

    @pytest.mark.asyncio
    async def test_restore_from_zip_missing_json(self, tmp_path, mock_async_session):
        wl_zip = tmp_path / "w.zip"
        with zipfile.ZipFile(wl_zip, "w") as zf:
            zf.writestr("other.txt", "x")
        svc = BackupService(db=mock_async_session)
        assert await svc._restore_whitelist_from_zip(str(wl_zip)) is False


class TestRestoreBackup:
    @pytest.mark.asyncio
    async def test_corrupt_raises(self):
        svc = BackupService()
        with patch.object(svc, "verify_backup", AsyncMock(return_value=False)):
            with pytest.raises(Exception, match="corrupted"):
                await svc.restore_backup("/bad.zip")

    @pytest.mark.asyncio
    async def test_full_restore_success(self, tmp_path):
        # Build a valid archive containing database.sql + config + whitelist + logs.
        db_sql = tmp_path / "database.sql"
        db_sql.write_text("-- sql")
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir()
        (cfg_dir / "system_config.json").write_text("{}")
        wl_dir = tmp_path / "wl"
        wl_dir.mkdir()
        (wl_dir / "whitelist.json").write_text("[]")

        z = tmp_path / "full.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.write(str(db_sql), "database.sql")
            zf.write(str(cfg_dir / "system_config.json"), "config/system_config.json")
            zf.write(str(wl_dir / "whitelist.json"), "whitelist/whitelist.json")

        svc = BackupService(db=_make_db())
        svc._restore_database = AsyncMock()
        svc._restore_system_config_db = AsyncMock(return_value=True)
        svc._restore_branding = AsyncMock(return_value=True)
        svc._restore_whitelist_from_zip = AsyncMock(return_value=True)
        svc._restore_logs_from_zip = AsyncMock(return_value=True)

        assert await svc.restore_backup(str(z)) is True
        svc._restore_database.assert_awaited_once()
        svc._restore_system_config_db.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_restore_error_returns_false(self, tmp_path):
        z = tmp_path / "full.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("database.sql", "-- sql")

        svc = BackupService(db=_make_db())
        svc._restore_database = AsyncMock(side_effect=RuntimeError("boom"))
        assert await svc.restore_backup(str(z)) is False


class TestRestoreDatabase:
    @pytest.mark.asyncio
    async def test_success(self):
        svc = BackupService()
        proc = _subprocess()
        with patch.object(bs.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)):
            await svc._restore_database("/tmp/db.sql")

    @pytest.mark.asyncio
    async def test_failure_raises(self):
        svc = BackupService()
        proc = _subprocess(returncode=1, stderr=b"restore error")
        with patch.object(bs.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)):
            with pytest.raises(Exception, match="restore error"):
                await svc._restore_database("/tmp/db.sql")