"""
Notification Logging and Template Rendering.

Handles notification logging to database and Jinja2 template rendering.
"""

import json
from datetime import datetime
from typing import Any

import jinja2
from loguru import logger
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now
from app.models.notification import NotificationLog, NotificationTemplate
from app.services.notification_channels import NotificationEvent, NotificationResult

_jinja_env = jinja2.Environment(
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


class NotificationLogger:
    """Handles notification logging and template rendering."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def render_template(
        self,
        event: NotificationEvent,
        channel_type: str,
        db: AsyncSession | None = None,
    ) -> dict[str, str] | None:
        try:
            from app.core.database import async_session_factory
            
            if db is not None:
                session = db
                own_session = False
            else:
                session_factory = async_session_factory()
                session = await session_factory.__aenter__()
                own_session = True

            try:
                stmt = select(NotificationTemplate).where(
                    NotificationTemplate.channel_type == channel_type,
                    (NotificationTemplate.event_type == event.type) | 
                    (NotificationTemplate.event_type == "*"),
                ).order_by(
                    (NotificationTemplate.event_type == event.type).desc(),
                    NotificationTemplate.priority.asc(),
                ).limit(1)
                result = await session.execute(stmt)
                template = result.scalar_one_or_none()

                if not template:
                    return None

                from app.services.notification_channels.event_types import EVENT_METADATA

                metadata = EVENT_METADATA.get(event.type, {})
                context = {
                    "event_type": event.type,
                    "event_name": metadata.get("name", event.type),
                    "description": metadata.get("description", ""),
                    "severity": event.severity,
                    "source": event.source,
                    "timestamp": event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "data": event.data,
                }

                subject = ""
                if template.subject_template:
                    subject = _jinja_env.from_string(template.subject_template).render(**context)

                body = _jinja_env.from_string(template.body_template).render(**context)

                return {"subject": subject, "body": body}
            finally:
                if own_session:
                    await session_factory.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Template render failed for {event.type}/{channel_type}: {e}")
            return None

    async def log_suppressed(
        self,
        event: NotificationEvent,
        channel_name: str,
        window: int,
        db: AsyncSession | None = None,
    ) -> None:
        try:
            from app.core.database import async_session_factory
            
            if db is not None:
                session = db
                own_session = False
            else:
                session_factory = async_session_factory()
                session = await session_factory.__aenter__()
                own_session = True

            try:
                log = NotificationLog(
                    event_id=event.id,
                    channel_name=channel_name,
                    event_type=event.type,
                    status="suppressed",
                    details={"suppression_window": window},
                    completed_at=now().replace(tzinfo=None),
                )
                session.add(log)
                await session.commit()
            finally:
                if own_session:
                    await session_factory.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Failed to log suppressed notification: {e}")

    async def log_sent(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
        db: AsyncSession | None = None,
    ) -> None:
        try:
            from app.core.database import async_session_factory
            
            if db is not None:
                session = db
                own_session = False
            else:
                session_factory = async_session_factory()
                session = await session_factory.__aenter__()
                own_session = True

            try:
                log = NotificationLog(
                    event_id=event.id,
                    channel_name=channel_name,
                    event_type=event.type,
                    status="sent",
                    recipient=result.recipient,
                    details=result.details,
                    completed_at=now().replace(tzinfo=None),
                )
                session.add(log)
                await session.commit()
            finally:
                if own_session:
                    await session_factory.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Failed to log sent notification: {e}")

    async def log_retrying(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
        retry_count: int,
        next_retry_at: datetime,
        db: AsyncSession | None = None,
    ) -> None:
        try:
            from app.core.database import async_session_factory
            
            if db is not None:
                session = db
                own_session = False
            else:
                session_factory = async_session_factory()
                session = await session_factory.__aenter__()
                own_session = True

            try:
                stmt = select(NotificationLog).where(
                    NotificationLog.event_id == event.id,
                    NotificationLog.channel_name == channel_name,
                )
                res = await session.execute(stmt)
                log = res.scalar_one_or_none()
                if log is None:
                    log = NotificationLog(
                        event_id=event.id,
                        channel_name=channel_name,
                        event_type=event.type,
                        status="retrying",
                        error_message=result.message,
                        details=result.details,
                        retry_count=retry_count,
                        next_retry_at=next_retry_at,
                    )
                    session.add(log)
                else:
                    log.status = "retrying"
                    log.error_message = result.message
                    log.details = result.details
                    log.retry_count = retry_count
                    log.next_retry_at = next_retry_at
                await session.commit()
            finally:
                if own_session:
                    await session_factory.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Failed to log retrying notification: {e}")

    async def log_failed(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
        retry_count: int,
        db: AsyncSession | None = None,
    ) -> None:
        try:
            from app.core.database import async_session_factory
            
            if db is not None:
                session = db
                own_session = False
            else:
                session_factory = async_session_factory()
                session = await session_factory.__aenter__()
                own_session = True

            try:
                stmt = select(NotificationLog).where(
                    NotificationLog.event_id == event.id,
                    NotificationLog.channel_name == channel_name,
                )
                res = await session.execute(stmt)
                log = res.scalar_one_or_none()
                if log is None:
                    log = NotificationLog(
                        event_id=event.id,
                        channel_name=channel_name,
                        event_type=event.type,
                        status="failed",
                        error_message=result.message,
                        details=result.details,
                        retry_count=retry_count,
                        completed_at=now().replace(tzinfo=None),
                    )
                    session.add(log)
                else:
                    log.status = "failed"
                    log.error_message = result.message
                    log.details = result.details
                    log.retry_count = retry_count
                    log.next_retry_at = None
                    log.completed_at = datetime.utcnow()
                await session.commit()
            finally:
                if own_session:
                    await session_factory.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"Failed to log failed notification: {e}")

    async def log_notification(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
        db: AsyncSession | None = None,
    ) -> None:
        if result.success:
            await self.log_sent(event, channel_name, result, db)
        else:
            await self.log_failed(event, channel_name, result, 0, db)

    async def get_notification_logs(
        self,
        db: AsyncSession,
        channel_name: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        archived: bool | None = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[NotificationLog], int]:
        stmt = select(NotificationLog).order_by(NotificationLog.sent_at.desc())

        if channel_name:
            stmt = stmt.where(NotificationLog.channel_name == channel_name)
        if event_type:
            stmt = stmt.where(NotificationLog.event_type == event_type)
        if status:
            stmt = stmt.where(NotificationLog.status == status)
        if archived is not None:
            stmt = stmt.where(NotificationLog.archived == archived)

        count_stmt = select(func.count()).select_from(NotificationLog)
        if channel_name:
            count_stmt = count_stmt.where(NotificationLog.channel_name == channel_name)
        if event_type:
            count_stmt = count_stmt.where(NotificationLog.event_type == event_type)
        if status:
            count_stmt = count_stmt.where(NotificationLog.status == status)
        if archived is not None:
            count_stmt = count_stmt.where(NotificationLog.archived == archived)

        count_result = await db.execute(count_stmt)
        total = count_result.scalar()

        stmt = stmt.limit(limit).offset(offset)
        result = await db.execute(stmt)
        logs = result.scalars().all()

        return list(logs), total