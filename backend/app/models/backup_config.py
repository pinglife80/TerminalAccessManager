from sqlalchemy import Boolean, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BackupConfigModel(Base):
    __tablename__ = "backup_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule: Mapped[str] = mapped_column(String(100), default="0 2 * * *")
    retention_days: Mapped[int] = mapped_column(Integer, default=7)
    storage_type: Mapped[str] = mapped_column(String(50), default="local")
    storage_config: Mapped[dict] = mapped_column(JSON, default=dict)
    backup_database: Mapped[bool] = mapped_column(Boolean, default=True)
    backup_config: Mapped[bool] = mapped_column(Boolean, default=True)
    backup_whitelist: Mapped[bool] = mapped_column(Boolean, default=True)
    backup_logs: Mapped[bool] = mapped_column(Boolean, default=False)
    encrypt_backup: Mapped[bool] = mapped_column(Boolean, default=True)