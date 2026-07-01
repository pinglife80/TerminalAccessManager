"""
Notification Schemas for TerminalAccessManager.

Pydantic models for notification-related API requests/responses.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NotificationChannelBase(BaseModel):
    """Base schema for notification channel"""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="Channel type: email, webhook, feishu, dingtalk, wecom")
    config: dict[str, Any] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list, description="Subscribed event types")
    description: str | None = None
    enabled: bool = True


class NotificationChannelCreate(NotificationChannelBase):
    """Schema for creating a notification channel"""

    pass


class NotificationChannelUpdate(BaseModel):
    """Schema for updating a notification channel"""

    name: str | None = None
    config: dict[str, Any] | None = None
    events: list[str] | None = None
    description: str | None = None
    enabled: bool | None = None


class NotificationChannelResponse(NotificationChannelBase):
    """Schema for notification channel response"""

    id: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationLogResponse(BaseModel):
    """Schema for notification log response"""

    id: int
    event_id: str
    channel_name: str
    event_type: str
    status: str
    recipient: str | None
    error_message: str | None
    details: dict[str, Any] | None
    sent_at: datetime

    class Config:
        from_attributes = True


class NotificationLogListResponse(BaseModel):
    """Schema for paginated notification log list"""

    items: list[NotificationLogResponse]
    total: int
    limit: int
    offset: int


class ChannelTestResultResponse(BaseModel):
    """Schema for channel test result"""

    success: bool
    message: str
    details: dict[str, Any] | None = None


class EventMetadata(BaseModel):
    """Event metadata for UI display"""

    type: str
    name: str
    description: str
    severity: str
    category: str


class EventListResponse(BaseModel):
    """Schema for event metadata list"""

    events: list[EventMetadata]


class ChannelMetadata(BaseModel):
    """Channel metadata for UI display"""

    type: str
    name: str
    description: str
    config_fields: list[str]


class ChannelMetadataListResponse(BaseModel):
    """Schema for channel metadata list"""

    channels: list[ChannelMetadata]
