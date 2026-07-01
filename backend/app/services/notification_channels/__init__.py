"""
Notification Channels Package for TerminalAccessManager.

Provides various notification channel implementations for sending alerts.
"""

from app.services.notification_channels.base import (
    ChannelTestResult,
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
)
from app.services.notification_channels.dingtalk_channel import DingTalkChannel
from app.services.notification_channels.email_channel import EmailChannel
from app.services.notification_channels.event_types import (
    CHANNEL_METADATA,
    EVENT_METADATA,
    ChannelType,
    EventType,
)
from app.services.notification_channels.feishu_channel import FeishuChannel
from app.services.notification_channels.webhook_channel import WebhookChannel
from app.services.notification_channels.wecom_channel import WeComChannel

# Channel registry for factory pattern
CHANNEL_REGISTRY = {
    "email": EmailChannel,
    "webhook": WebhookChannel,
    "feishu": FeishuChannel,
    "dingtalk": DingTalkChannel,
    "wecom": WeComChannel,
}


def get_channel(channel_type: str, config: dict) -> NotificationChannelBase:
    """
    Factory function to get a notification channel instance.

    Args:
        channel_type: Type of channel (email, webhook, feishu, dingtalk, wecom)
        config: Channel configuration dictionary

    Returns:
        NotificationChannelBase instance

    Raises:
        ValueError: If channel type is not supported
    """
    channel_class = CHANNEL_REGISTRY.get(channel_type.lower())
    if not channel_class:
        raise ValueError(f"Unsupported channel type: {channel_type}")
    return channel_class(config)


__all__ = [
    "NotificationChannelBase",
    "NotificationEvent",
    "NotificationResult",
    "ChannelTestResult",
    "EventType",
    "ChannelType",
    "EVENT_METADATA",
    "CHANNEL_METADATA",
    "EmailChannel",
    "WebhookChannel",
    "FeishuChannel",
    "DingTalkChannel",
    "WeComChannel",
    "get_channel",
    "CHANNEL_REGISTRY",
]
