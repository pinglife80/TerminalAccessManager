"""
Base Notification Channel Interface for TerminalAccessManager.

Defines the abstract base class for all notification channels.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class NotificationEvent:
    """Notification event data structure"""

    id: str
    type: str  # EventType value
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = "system"  # system / user / scheduler
    severity: str = "info"  # info / warning / error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "source": self.source,
            "severity": self.severity,
        }


@dataclass
class NotificationResult:
    """Result of a notification send operation"""

    success: bool
    message: str
    channel: str
    event_id: Optional[str] = None
    recipient: Optional[str] = None
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "channel": self.channel,
            "event_id": self.event_id,
            "recipient": self.recipient,
            "error_code": self.error_code,
            "details": self.details,
        }


@dataclass
class ChannelTestResult:
    """Result of a channel connection test"""

    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class NotificationChannelBase(ABC):
    """Abstract base class for notification channels

    All notification channels must implement this interface.
    """

    channel_type: str = "base"
    channel_name: str = "Base Channel"

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the channel with configuration.

        Args:
            config: Channel configuration dictionary
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate required configuration fields. Override in subclasses."""
        pass

    @abstractmethod
    async def send(
        self,
        event: NotificationEvent,
        template_data: Optional[Dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send a notification.

        Args:
            event: The notification event to send
            template_data: Optional template data for rendering

        Returns:
            NotificationResult indicating success or failure
        """
        pass

    @abstractmethod
    async def test(self) -> ChannelTestResult:
        """
        Test the channel connection/configuration.

        Returns:
            ChannelTestResult with test outcome
        """
        pass

    def supports_event(self, event_type: str) -> bool:
        """
        Check if this channel supports the given event type.

        Default implementation returns True. Override to filter events.

        Args:
            event_type: The event type to check

        Returns:
            True if the event type is supported
        """
        return True

    def format_message(self, event: NotificationEvent) -> str:
        """
        Format the event as a human-readable message.

        Args:
            event: The notification event

        Returns:
            Formatted message string
        """
        from app.services.notification_channels.event_types import EVENT_METADATA

        metadata = EVENT_METADATA.get(event.type, {})
        name = metadata.get("name", event.type)
        description = metadata.get("description", "")

        message = f"**{name}**\n\n{description}\n\n"
        message += f"时间: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"

        if event.data:
            message += "\n详细信息:\n"
            for key, value in event.data.items():
                message += f"- {key}: {value}\n"

        return message

    def format_data(self, event: NotificationEvent) -> Dict[str, Any]:
        """
        Format the event data for structured notifications.

        Args:
            event: The notification event

        Returns:
            Formatted data dictionary
        """
        from app.services.notification_channels.event_types import EVENT_METADATA

        metadata = EVENT_METADATA.get(event.type, {})

        return {
            "event_id": event.id,
            "event_type": event.type,
            "event_name": metadata.get("name", event.type),
            "severity": event.severity,
            "category": metadata.get("category", "unknown"),
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "data": event.data,
        }

    def get_recipients(self) -> List[str]:
        """
        Get the list of recipients for this channel.

        Override in subclasses that need dynamic recipient resolution.

        Returns:
            List of recipient identifiers
        """
        return self.config.get("recipients", [])


class AsyncNotificationChannelBase(NotificationChannelBase):
    """
    Async notification channel base class.

    Provides async implementations for channels that need async operations.
    """

    async def send(
        self,
        event: NotificationEvent,
        template_data: Optional[Dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send notification asynchronously.

        Override this method in subclasses.
        """
        raise NotImplementedError("Subclasses must implement send()")

    async def test(self) -> ChannelTestResult:
        """
        Test the channel asynchronously.

        Override this method in subclasses.
        """
        raise NotImplementedError("Subclasses must implement test()")
