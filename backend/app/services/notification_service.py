"""
Notification Service for TerminalAccessManager.

Central service for managing notifications and event publishing.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_config
from app.models.notification import NotificationChannel, NotificationLog
from app.services.notification_channels import (
    CHANNEL_REGISTRY,
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
    get_channel,
)
from app.services.notification_channels.event_types import EventType


class NotificationService:
    """
    Central notification service.

    Manages notification channels, event publishing, and notification logs.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize notification service.

        Args:
            db: Database session
        """
        self.db = db
        self._channels: Dict[str, NotificationChannelBase] = {}
        self._channel_configs: Dict[str, dict] = {}

    async def initialize_channels(self) -> None:
        """
        Load and initialize all enabled notification channels from database.
        """
        stmt = select(NotificationChannel).where(NotificationChannel.enabled == True)
        result = await self.db.execute(stmt)
        channels = result.scalars().all()

        for channel_config in channels:
            try:
                # Decrypt config if needed
                config = channel_config.config
                if isinstance(config, dict) and any(
                    v.startswith("ENC:") if isinstance(v, str) else False
                    for v in config.values()
                ):
                    config = decrypt_config(config)

                # Create channel instance
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

    async def get_channels(self) -> List[NotificationChannel]:
        """Get all notification channels from database"""
        stmt = select(NotificationChannel).order_by(NotificationChannel.id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_channel_by_id(self, channel_id: int) -> Optional[NotificationChannel]:
        """Get a notification channel by ID"""
        stmt = select(NotificationChannel).where(NotificationChannel.id == channel_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_channel(
        self,
        name: str,
        channel_type: str,
        config: dict,
        events: List[str],
        description: Optional[str] = None,
        created_by: Optional[str] = None,
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

        # Initialize the channel
        await self.initialize_channels()

        logger.info(f"Created notification channel: {name}")
        return channel

    async def update_channel(
        self,
        channel_id: int,
        name: Optional[str] = None,
        config: Optional[dict] = None,
        events: Optional[List[str]] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[NotificationChannel]:
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

        # Reload channels
        await self.initialize_channels()

        logger.info(f"Updated notification channel: {channel.name}")
        return channel

    async def delete_channel(self, channel_id: int) -> bool:
        """Delete a notification channel"""
        channel = await self.get_channel_by_id(channel_id)
        if not channel:
            return False

        await self.db.delete(channel)
        await self.db.commit()

        # Reload channels
        await self.initialize_channels()

        logger.info(f"Deleted notification channel: {channel.name}")
        return True

    async def test_channel(self, channel_id: int) -> dict:
        """Test a notification channel connection"""
        channel_config = await self.get_channel_by_id(channel_id)
        if not channel_config:
            return {"success": False, "message": "Channel not found"}

        try:
            # Decrypt config if needed
            config = channel_config.config
            if isinstance(config, dict) and any(
                v.startswith("ENC:") if isinstance(v, str) else False
                for v in config.values()
            ):
                config = decrypt_config(config)

            # Create channel instance
            channel = get_channel(channel_config.type, config)

            # Test connection
            test_result = await channel.test()

            return {
                "success": test_result.success,
                "message": test_result.message,
                "details": test_result.details,
            }
        except Exception as e:
            logger.error(f"Channel test failed: {e}")
            return {"success": False, "message": f"Test failed: {str(e)}"}

    def _get_subscribed_channels(self, event_type: str) -> List[str]:
        """Get list of channel names that are subscribed to the given event type"""
        subscribed = []
        for channel_name, channel_info in self._channel_configs.items():
            if event_type in channel_info.get("events", []):
                subscribed.append(channel_name)
        return subscribed

    async def emit(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        source: str = "system",
        severity: str = "info",
    ) -> List[NotificationResult]:
        """
        Emit an event and send notifications to subscribed channels.

        Args:
            event_type: Type of event to emit
            data: Event data payload
            source: Source of the event (system, user, scheduler)
            severity: Severity level (info, warning, error)

        Returns:
            List of notification results for each channel
        """
        # Create event
        event = NotificationEvent(
            id=str(uuid.uuid4()),
            type=event_type,
            timestamp=datetime.utcnow(),
            data=data or {},
            source=source,
            severity=severity,
        )

        # Get subscribed channels
        subscribed_channels = self._get_subscribed_channels(event_type)

        if not subscribed_channels:
            logger.debug(f"No channels subscribed to event: {event_type}")
            return []

        # Send to all subscribed channels
        results = []
        for channel_name in subscribed_channels:
            channel = self._channels.get(channel_name)
            if not channel:
                continue

            try:
                result = await channel.send(event)
                results.append(result)

                # Log the notification
                await self._log_notification(event, channel_name, result)

            except Exception as e:
                logger.error(f"Failed to send notification to {channel_name}: {e}")
                results.append(
                    NotificationResult(
                        success=False,
                        message=f"Send failed: {str(e)}",
                        channel=channel.channel_type,
                        event_id=event.id,
                        error_code="SEND_ERROR",
                    )
                )

        return results

    async def _log_notification(
        self,
        event: NotificationEvent,
        channel_name: str,
        result: NotificationResult,
    ) -> None:
        """Log a notification to the database"""
        try:
            log = NotificationLog(
                event_id=event.id,
                channel_name=channel_name,
                event_type=event.type,
                status="sent" if result.success else "failed",
                recipient=result.recipient,
                error_message=result.message if not result.success else None,
                details=result.details,
            )
            self.db.add(log)
            await self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")

    async def get_notification_logs(
        self,
        channel_name: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[NotificationLog], int]:
        """
        Get notification logs with filtering and pagination.

        Returns:
            Tuple of (logs, total_count)
        """
        stmt = select(NotificationLog).order_by(NotificationLog.sent_at.desc())

        if channel_name:
            stmt = stmt.where(NotificationLog.channel_name == channel_name)
        if event_type:
            stmt = stmt.where(NotificationLog.event_type == event_type)
        if status:
            stmt = stmt.where(NotificationLog.status == status)

        # Get total count
        from sqlalchemy import func

        count_stmt = select(func.count()).select_from(NotificationLog)
        if channel_name:
            count_stmt = count_stmt.where(NotificationLog.channel_name == channel_name)
        if event_type:
            count_stmt = count_stmt.where(NotificationLog.event_type == event_type)
        if status:
            count_stmt = count_stmt.where(NotificationLog.status == status)

        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar()

        # Get paginated results
        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        logs = result.scalars().all()

        return list(logs), total

    # ==================== Convenience Methods ====================

    async def emit_terminal_blocked(
        self,
        ip_address: str,
        mac_address: str,
        reason: str,
        blocked_by: str,
    ) -> List[NotificationResult]:
        """Emit terminal blocked event"""
        return await self.emit(
            event_type=EventType.TERMINAL_BLOCKED,
            data={
                "ip_address": ip_address,
                "mac_address": mac_address,
                "reason": reason,
                "blocked_by": blocked_by,
            },
            source="system",
            severity="warning",
        )

    async def emit_terminal_unblocked(
        self,
        ip_address: str,
        mac_address: str,
        unblocked_by: str,
    ) -> List[NotificationResult]:
        """Emit terminal unblocked event"""
        return await self.emit(
            event_type=EventType.TERMINAL_UNBLOCKED,
            data={
                "ip_address": ip_address,
                "mac_address": mac_address,
                "unblocked_by": unblocked_by,
            },
            source="system",
            severity="info",
        )

    async def emit_login_failed(
        self,
        username: str,
        ip_address: str,
        reason: str,
    ) -> List[NotificationResult]:
        """Emit login failed event"""
        return await self.emit(
            event_type=EventType.LOGIN_FAILED,
            data={
                "username": username,
                "ip_address": ip_address,
                "reason": reason,
            },
            source="system",
            severity="warning",
        )

    async def emit_login_locked(
        self,
        username: str,
        ip_address: str,
        lock_duration: int,
    ) -> List[NotificationResult]:
        """Emit account locked event"""
        return await self.emit(
            event_type=EventType.LOGIN_LOCKED,
            data={
                "username": username,
                "ip_address": ip_address,
                "lock_duration_minutes": lock_duration,
            },
            source="system",
            severity="error",
        )

    async def emit_datasource_sync_failed(
        self,
        source_name: str,
        source_tag: str,
        error: str,
    ) -> List[NotificationResult]:
        """Emit datasource sync failed event"""
        return await self.emit(
            event_type=EventType.DATASOURCE_SYNC_FAILED,
            data={
                "source_name": source_name,
                "source_tag": source_tag,
                "error": error,
            },
            source="scheduler",
            severity="error",
        )

    async def emit_compliance_alert(
        self,
        compliance_rate: float,
        non_compliant_count: int,
        threshold: float,
    ) -> List[NotificationResult]:
        """Emit compliance rate alert event"""
        event_type = (
            EventType.COMPLIANCE_RATE_CRITICAL
            if compliance_rate < threshold * 0.5
            else EventType.COMPLIANCE_RATE_LOW
        )
        severity = "error" if compliance_rate < threshold * 0.5 else "warning"

        return await self.emit(
            event_type=event_type,
            data={
                "compliance_rate": f"{compliance_rate:.1f}%",
                "non_compliant_count": non_compliant_count,
                "threshold": f"{threshold * 100:.0f}%",
            },
            source="scheduler",
            severity=severity,
        )
