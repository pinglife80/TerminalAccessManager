"""
Notification Service for TerminalAccessManager.

Central service for managing notifications and event publishing.

Architecture (P3 async/retry):
    emit() → enqueues to Redis List (notify:queue:main) → fire-and-forget
    main_worker_task → pops from queue, applies rules, attempts delivery
        → success: log as sent
        → failure: schedule retry in Redis ZSet (notify:queue:retry) with
                   exponential backoff; log as retrying
    retry_worker_task → scans ZSet for due items, re-attempts delivery
        → success: log as sent, clear retry
        → failure + retries left: reschedule with longer backoff
        → failure + retries exhausted: log as failed (terminal)
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

from loguru import logger
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_config, has_encrypted_config
from app.core.timezone import now
from app.models.notification import (
    NotificationChannel,
    NotificationLog,
)
from app.services.notification_channels import (
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
    get_channel,
)
from app.services.notification_channels.event_types import CHANNEL_METADATA, EVENT_METADATA, EventType


class NotificationService:
    """
    Central notification service.

    Manages notification channels, event publishing, and notification logs.

    Two usage modes:
    1. Request-scoped: pass an AsyncSession (API endpoints). All operations
       share the request's session and transaction.
    2. Global singleton: omit the session (lifespan initialization). Each
       DB-touching operation opens a short-lived session via
       async_session_factory. Channel instances and config cache are kept
       in-memory across operations.
    """

    def __init__(self, db: AsyncSession | None = None):
        """
        Initialize notification service.

        Args:
            db: Optional database session. When provided, all DB operations
                reuse this session (request-scoped usage). When omitted,
                each DB operation opens its own short-lived session
                (global singleton usage).
        """
        self.db = db
        self._channels: dict[str, NotificationChannelBase] = {}
        self._channel_configs: dict[str, dict] = {}
        self._workers = None

    @asynccontextmanager
    async def _session_scope(self) -> AsyncIterator[AsyncSession]:
        """Yield a DB session.

        Uses the injected session when available (request-scoped mode),
        otherwise opens a fresh short-lived session from the factory
        (singleton mode) and closes it when the block exits.
        """
        if self.db is not None:
            yield self.db
        else:
            from app.core.database import async_session_factory

            async with async_session_factory() as session:
                yield session

    def _get_workers(self):
        if self._workers is None:
            from app.services.notification_workers import NotificationWorkers
            self._workers = NotificationWorkers(self._channels, self._channel_configs)
        return self._workers

    def _get_logger(self):
        from app.services.notification_logging import NotificationLogger
        return NotificationLogger(self.db)

    async def initialize_channels(self) -> None:
        """
        Load and initialize all enabled notification channels from database.

        Clears the in-memory cache before reloading so that deleted or
        disabled channels are removed. Without the clear, a channel that
        was deleted from the database would still be present in the cache
        and continue to receive events until the process restarts.
        """
        async with self._session_scope() as db:
            self._channels.clear()
            self._channel_configs.clear()

            stmt = select(NotificationChannel).where(NotificationChannel.enabled == True)
            result = await db.execute(stmt)
            channels = result.scalars().all()

            for channel_config in channels:
                try:
                    config = channel_config.config
                    if isinstance(config, dict) and has_encrypted_config(config):
                        config = decrypt_config(config)

                    channel = get_channel(channel_config.type, config)
                    self._channels[channel_config.name] = channel
                    self._channel_configs[channel_config.name] = {
                        "id": channel_config.id,
                        "type": channel_config.type,
                        "events": channel_config.events,
                    }

                    logger.info(f"Loaded notification channel: {channel_config.name} ({channel_config.type})")
                except Exception as e:
                    logger.error(f"Failed to load channel {channel_config.name}: {e}")

            if self._workers is not None:
                self._workers._channels = self._channels
                self._workers._channel_configs = self._channel_configs

    async def get_channels(self) -> list[NotificationChannel]:
        """Get all notification channels from database"""
        stmt = select(NotificationChannel).order_by(NotificationChannel.id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_channel_by_id(self, channel_id: int) -> NotificationChannel | None:
        """Get a notification channel by ID"""
        stmt = select(NotificationChannel).where(NotificationChannel.id == channel_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_channel(
        self,
        name: str,
        channel_type: str,
        config: dict,
        events: list[str],
        description: str | None = None,
        created_by: str | None = None,
        enabled: bool = True,
    ) -> NotificationChannel:
        """Create a new notification channel"""
        channel = NotificationChannel(
            name=name,
            type=channel_type,
            config=config,
            events=events,
            description=description,
            created_by=created_by,
            enabled=enabled,
        )
        self.db.add(channel)
        await self.db.commit()
        await self.db.refresh(channel)

        try:
            await self.initialize_channels()
            await self._refresh_global_channels()
        except Exception as e:
            logger.error(f"Failed to refresh channel cache after creation: {e}")

        logger.info(f"Created notification channel: {name}")
        return channel

    async def update_channel(
        self,
        channel_id: int,
        name: str | None = None,
        config: dict | None = None,
        events: list[str] | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> NotificationChannel | None:
        """Update a notification channel"""
        channel = await self.get_channel_by_id(channel_id)
        if not channel:
            return None

        if name is not None:
            channel.name = name
        if config is not None:
            channel.config = config
        if events is not None:
            channel.events = events
        if description is not None:
            channel.description = description
        if enabled is not None:
            channel.enabled = enabled

        await self.db.commit()
        await self.db.refresh(channel)

        try:
            await self.initialize_channels()
            await self._refresh_global_channels()
        except Exception as e:
            logger.error(f"Failed to refresh channel cache after update: {e}")

        logger.info(f"Updated notification channel: {channel.name}")
        return channel

    async def delete_channel(self, channel_id: int) -> bool:
        """Delete a notification channel"""
        channel = await self.get_channel_by_id(channel_id)
        if not channel:
            return False

        await self.db.delete(channel)
        await self.db.commit()

        try:
            await self.initialize_channels()
            await self._refresh_global_channels()
        except Exception as e:
            logger.error(f"Failed to refresh channel cache after deletion: {e}")

        logger.info(f"Deleted notification channel: {channel.name}")
        return True

    async def _refresh_global_channels(self) -> None:
        """Refresh the global notification service singleton's channel cache."""
        from app.services.event_emitter import get_notification_service

        global_service = get_notification_service()
        if global_service is not None and global_service is not self:
            try:
                await global_service.initialize_channels()
                logger.info("Global notification service channels refreshed")
            except Exception as e:
                logger.error(f"Failed to refresh global notification service: {e}")

    async def test_channel(self, channel_id: int) -> dict:
        """Test a notification channel connection"""
        channel_config = await self.get_channel_by_id(channel_id)
        if not channel_config:
            return {"success": False, "message": "Channel not found"}

        try:
            config = channel_config.config
            if isinstance(config, dict) and has_encrypted_config(config):
                config = decrypt_config(config)

            channel = get_channel(channel_config.type, config)

            test_result = await channel.test()

            return {
                "success": test_result.success,
                "message": test_result.message,
                "details": test_result.details,
            }
        except Exception as e:
            logger.error(f"Channel test failed: {e}")
            return {"success": False, "message": f"Test failed: {str(e)}"}

    async def start_workers(self) -> None:
        """Start the background worker coroutines."""
        workers = self._get_workers()
        await workers.start_workers()

    async def stop_workers(self) -> None:
        """Stop the background worker coroutines gracefully."""
        workers = self._get_workers()
        await workers.stop_workers()

    async def emit(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        source: str = "system",
        severity: str = "info",
    ) -> list[NotificationResult]:
        """
        Emit an event — enqueues for async delivery.
        """
        workers = self._get_workers()
        return await workers.emit(event_type, data, source, severity)

    async def _log_suppressed(self, event: NotificationEvent, channel_name: str, window: int) -> None:
        """Log a suppressed notification"""
        logger_inst = self._get_logger()
        await logger_inst.log_suppressed(event, channel_name, window)

    async def _log_sent(self, event: NotificationEvent, channel_name: str, result: NotificationResult) -> None:
        """Log a successfully sent notification"""
        logger_inst = self._get_logger()
        await logger_inst.log_sent(event, channel_name, result)

    async def _log_retrying(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
        retry_count: int,
        next_retry_at: datetime,
    ) -> None:
        """Log a notification that will be retried"""
        logger_inst = self._get_logger()
        await logger_inst.log_retrying(event, channel_name, result, retry_count, next_retry_at)

    async def _log_failed(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
        retry_count: int,
    ) -> None:
        """Log a permanently failed notification"""
        logger_inst = self._get_logger()
        await logger_inst.log_failed(event, channel_name, result, retry_count)

    async def _log_notification(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
    ) -> None:
        """Backward-compatible log wrapper."""
        logger_inst = self._get_logger()
        await logger_inst.log_notification(event, channel_name, result)

    async def _render_template(
        self,
        event: NotificationEvent,
        channel_type: str,
    ) -> dict[str, str] | None:
        """Look up and render a message template for the given event+channel."""
        logger_inst = self._get_logger()
        return await logger_inst.render_template(event, channel_type)

    async def get_notification_logs(
        self,
        channel_name: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        archived: bool | None = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[NotificationLog], int]:
        """Get notification logs with filtering and pagination."""
        logger_inst = self._get_logger()
        return await logger_inst.get_notification_logs(self.db, channel_name, event_type, status, archived, limit, offset)

    async def publish_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> list:
        """Publish an event"""
        results = []
        for channel in self._channels.values():
            result = await channel.send(
                recipients=[],
                subject=f"Event: {event_type}",
                message=str(data),
            )
            results.append(result)
        return results

    async def send_notification(
        self,
        channel_type: str,
        recipients: list[str],
        subject: str,
        message: str,
    ) -> dict:
        """Send a notification directly"""
        channel = self._channels.get(channel_type)
        if not channel:
            return {"success": False, "message": f"Channel {channel_type} not found"}

        event = NotificationEvent(
            id=str(__import__('uuid').uuid4()),
            type="custom",
            timestamp=now(),
            data={"subject": subject, "message": message},
            source="user",
            severity="info",
        )

        result = await channel.send(event)
        if isinstance(result, dict):
            return result
        return {"success": result.success, "message": result.message}

    async def log_notification(
        self,
        channel_type: str,
        recipient: str,
        success: bool,
        event_type: str,
        message_id: str,
    ) -> None:
        """Log a notification (public alias)"""
        event = NotificationEvent(
            id=message_id,
            type=event_type,
            timestamp=now(),
            data={},
            source="system",
            severity="info",
        )
        result = NotificationResult(
            success=success,
            message="",
            channel=channel_type,
            event_id=message_id,
            recipient=recipient,
        )
        await self._log_notification(event, channel_type, result)

    def get_channel_metadata(self) -> dict:
        """Get channel metadata"""
        return {
            "channels": list(self._channels.keys()),
            "configs": self._channel_configs,
            **CHANNEL_METADATA,
        }

    def get_event_types(self) -> list[str]:
        """Get all event types"""
        return list(EVENT_METADATA.keys())

    async def get_statistics(self) -> dict[str, Any]:
        """Get notification statistics overview with breakdowns."""
        async with self._session_scope() as db:
            stmt = select(
                NotificationLog.status,
                func.count(NotificationLog.id).label("cnt"),
            ).group_by(NotificationLog.status)
            result = await db.execute(stmt)
            rows = result.all()
            status_counts = {row[0]: row[1] for row in rows}

            total = sum(status_counts.values())
            sent = status_counts.get("sent", 0)
            failed = status_counts.get("failed", 0)
            pending = status_counts.get("pending", 0)
            retrying = status_counts.get("retrying", 0)
            suppressed = status_counts.get("suppressed", 0)
            deliverable = sent + failed
            success_rate = (sent / deliverable * 100) if deliverable > 0 else 100.0

            avg_latency_ms = None
            try:
                from sqlalchemy import extract

                latency_stmt = select(
                    func.avg(
                        (func.extract("epoch", NotificationLog.completed_at) -
                         func.extract("epoch", NotificationLog.sent_at)) * 1000
                    )
                ).where(
                    NotificationLog.status == "sent",
                    NotificationLog.completed_at.isnot(None),
                )
                lat_result = await db.execute(latency_stmt)
                avg_latency_ms = lat_result.scalar()
            except Exception as e:
                logger.warning(f"Failed to calculate average latency: {e}")

            try:
                from sqlalchemy import case
                ch_stmt = select(
                    NotificationLog.channel_name,
                    func.count(NotificationLog.id).label("total"),
                    func.sum(case((NotificationLog.status == "sent", 1), else_=0)).label("sent"),
                    func.sum(case((NotificationLog.status == "failed", 1), else_=0)).label("failed"),
                ).group_by(NotificationLog.channel_name).order_by(func.count(NotificationLog.id).desc())
                ch_result = await db.execute(ch_stmt)
                by_channel = []
                for row in ch_result.all():
                    ch_total = row[1]
                    ch_sent = row[2] or 0
                    ch_failed = row[3] or 0
                    ch_deliverable = ch_sent + ch_failed
                    ch_rate = (ch_sent / ch_deliverable * 100) if ch_deliverable > 0 else 100.0
                    by_channel.append({
                        "channel_name": row[0],
                        "total": ch_total,
                        "sent": ch_sent,
                        "failed": ch_failed,
                        "success_rate": round(ch_rate, 2),
                    })
            except Exception as e:
                logger.error(f"Failed to get channel statistics: {e}")
                by_channel = []

            try:
                from sqlalchemy import case
                ev_stmt = select(
                    NotificationLog.event_type,
                    func.count(NotificationLog.id).label("total"),
                    func.sum(case((NotificationLog.status == "sent", 1), else_=0)).label("sent"),
                    func.sum(case((NotificationLog.status == "failed", 1), else_=0)).label("failed"),
                ).group_by(NotificationLog.event_type).order_by(func.count(NotificationLog.id).desc())
                ev_result = await db.execute(ev_stmt)
                by_event = []
                for row in ev_result.all():
                    ev_total = row[1]
                    ev_sent = row[2] or 0
                    ev_failed = row[3] or 0
                    ev_deliverable = ev_sent + ev_failed
                    ev_rate = (ev_sent / ev_deliverable * 100) if ev_deliverable > 0 else 100.0
                    by_event.append({
                        "event_type": row[0],
                        "total": ev_total,
                        "sent": ev_sent,
                        "failed": ev_failed,
                        "success_rate": round(ev_rate, 2),
                    })
            except Exception as e:
                logger.error(f"Failed to get event statistics: {e}")
                by_event = []

        queue_size = 0
        retry_queue_size = 0
        try:
            from app.core.security import get_redis_client
            redis = await get_redis_client()
            queue_size = await redis.llen("notify:queue:main")
            retry_queue_size = await redis.zcard("notify:queue:retry")
        except Exception as e:
            logger.warning(f"Failed to get queue sizes: {e}")

        return {
            "overview": {
                "total": total,
                "sent": sent,
                "failed": failed,
                "pending": pending,
                "retrying": retrying,
                "suppressed": suppressed,
                "success_rate": round(success_rate, 2),
                "avg_latency_ms": round(avg_latency_ms, 2) if avg_latency_ms is not None else None,
                "queue_size": queue_size,
                "retry_queue_size": retry_queue_size,
            },
            "by_channel": by_channel,
            "by_event": by_event,
            "event_coverage": await self._get_event_coverage(by_event),
        }

    async def retry_failed_notification(self, log_id: int) -> bool:
        """Manually retry a failed notification by log ID."""
        async with self._session_scope() as db:
            log = await db.get(NotificationLog, log_id)
            if not log:
                return False
            if log.status not in ("failed", "retrying"):
                return False

            try:
                from app.core.security import get_redis_client
                redis = await get_redis_client()
                payload = json.dumps({
                    "event_id": log.event_id,
                    "event_type": log.event_type,
                    "data": (log.details or {}).get("event_data", {}),
                    "source": "manual_retry",
                    "severity": "warning",
                    "timestamp": log.sent_at.isoformat(),
                    "retry_count": 0,
                    "queued_at": datetime.utcnow().isoformat(),
                    "_manual_retry": True,
                    "_log_id": log_id,
                })
                await redis.lpush("notify:queue:main", payload)
                log.status = "pending"
                log.error_message = None
                log.next_retry_at = None
                log.retry_count = 0
                await db.commit()
                logger.info(f"Manual retry queued for log {log_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to queue manual retry for log {log_id}: {e}")
                return False

    async def _get_event_coverage(self, by_event: list[dict]) -> dict:
        """Compare defined event types vs actually emitted event types."""
        from app.services.notification_channels.event_types import EVENT_METADATA

        emitted_types = {item["event_type"] for item in by_event}
        defined_types = set(EVENT_METADATA.keys())

        never_emitted = []
        for et in sorted(defined_types):
            if et not in emitted_types:
                meta = EVENT_METADATA.get(et, {})
                never_emitted.append({
                    "event_type": et,
                    "name": meta.get("name", et),
                    "category": meta.get("category", "unknown"),
                    "severity": meta.get("severity", "info"),
                })

        return {
            "total_defined": len(defined_types),
            "total_emitted": len(emitted_types & defined_types),
            "coverage_rate": round(len(emitted_types & defined_types) / len(defined_types) * 100, 1) if defined_types else 0.0,
            "never_emitted": never_emitted,
        }

    async def retry_all_failed(self) -> int:
        """Retry all currently failed notifications. Returns count retried."""
        async with self._session_scope() as db:
            stmt = select(NotificationLog).where(NotificationLog.status == "failed")
            result = await db.execute(stmt)
            logs = result.scalars().all()
            count = 0
            for log in logs:
                if await self.retry_failed_notification(log.id):
                    count += 1
            return count

    