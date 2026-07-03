"""
Notification Models for TerminalAccessManager.

Database models for notification channels and notification logs.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationChannel(Base):
    """Notification channel configuration"""

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, webhook, feishu, dingtalk, wecom
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)  # Encrypted storage
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # Subscribed event types
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<NotificationChannel(id={self.id}, name='{self.name}', type='{self.type}', enabled={self.enabled})>"


class NotificationLog(Base):
    """Notification log for audit trail.

    Status lifecycle:
        pending   → queued for async delivery, not yet attempted
        retrying  → delivery failed, scheduled for retry
        sent      → successfully delivered (terminal)
        failed    → all retries exhausted or permanent failure (terminal)
        suppressed → skipped by suppression rule (terminal, counted separately)
    """

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<NotificationLog(id={self.id}, event_type='{self.event_type}', status='{self.status}')>"


class NotificationTemplate(Base):
    """Notification message template.

    Stores Jinja2-renderable subject and body templates keyed by
    (event_type, channel_type). When a notification is emitted, the
    service looks up a matching template; if none exists, the channel's
    built-in default formatting is used (backward compatible).
    """

    __tablename__ = "notification_templates"
    __table_args__ = (
        UniqueConstraint("event_type", "channel_type", name="uq_template_event_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subject_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<NotificationTemplate(id={self.id}, name='{self.name}', event='{self.event_type}', channel='{self.channel_type}')>"


class NotificationRule(Base):
    """Notification processing rule for suppression, aggregation, and escalation.

    Rules are matched by event_type (required) and optionally channel_name.
    When channel_name is NULL, the rule applies to all channels subscribed to
    that event type. When a specific channel_name is set, it takes precedence
    over the catch-all (NULL) rule for the same event_type.

    Suppression: within ``suppress_window`` seconds after a notification is
    sent, subsequent events of the same type to the same channel are skipped
    and counted. The count is included in the next notification's event data
    as ``suppressed_count``, providing natural aggregation.

    Escalation: tracks total occurrences of an event type within
    ``escalate_window`` seconds. When the count reaches
    ``escalate_threshold``, the event severity is upgraded to
    ``escalate_severity`` for this emission.
    """

    __tablename__ = "notification_rules"
    # Note: uniqueness on (event_type, channel_name) is enforced via partial
    # indexes created in migration 018 — PostgreSQL treats NULL as distinct in
    # a regular UNIQUE constraint, so we need partial indexes to guarantee
    # only one catch-all (NULL channel_name) rule per event_type.

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # NULL means "all channels"; a specific name scopes the rule to that channel
    channel_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Suppression / Aggregation
    suppress_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    suppress_window: Mapped[int] = mapped_column(Integer, default=300)  # seconds

    # Escalation
    escalate_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    escalate_threshold: Mapped[int] = mapped_column(Integer, default=5)  # event count
    escalate_window: Mapped[int] = mapped_column(Integer, default=3600)  # seconds
    escalate_severity: Mapped[str] = mapped_column(String(20), default="error")  # info, warning, error, critical

    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<NotificationRule(id={self.id}, name='{self.name}', event='{self.event_type}', channel='{self.channel_name}')>"
