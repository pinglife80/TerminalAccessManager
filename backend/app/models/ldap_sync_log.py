"""
LDAP Sync Log Models for TerminalAccessManager.

Database models for storing LDAP synchronization history and status.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LDAPSyncLog(Base):
    """LDAP synchronization log"""

    __tablename__ = "ldap_sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running, completed, failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=True)  # manual or scheduler
    sync_type: Mapped[str] = mapped_column(String(20), default="full")  # full, incremental

    def __repr__(self) -> str:
        return f"<LDAPSyncLog(id={self.id}, status='{self.status}', started_at={self.started_at})>"