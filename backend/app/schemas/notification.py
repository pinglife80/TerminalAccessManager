"""
Notification Schemas for TerminalAccessManager.

Pydantic models for notification-related API requests/responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class NotificationChannelBase(BaseModel):
    """Base schema for notification channel"""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="Channel type: email, webhook, feishu, dingtalk, wecom")
    config: Dict[str, Any] = Field(default_factory=dict)
    events: List[str] = Field(default_factory=list, description="Subscribed event types")
    description: Optional[str] = None
    enabled: bool = True


class NotificationChannelCreate(NotificationChannelBase):
    """Schema for creating a notification channel"""

    pass


class NotificationChannelUpdate(BaseModel):
    """Schema for updating a notification channel"""

    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    events: Optional[List[str]] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class NotificationChannelResponse(NotificationChannelBase):
    """Schema for notification channel response"""

    id: int
    created_by: Optional[str]
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
    recipient: Optional[str]
    error_message: Optional[str]
    details: Optional[Dict[str, Any]]
    sent_at: datetime

    class Config:
        from_attributes = True


class NotificationLogListResponse(BaseModel):
    """Schema for paginated notification log list"""

    items: List[NotificationLogResponse]
    total: int
    limit: int
    offset: int


class ChannelTestResultResponse(BaseModel):
    """Schema for channel test result"""

    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class EventMetadata(BaseModel):
    """Event metadata for UI display"""

    type: str
    name: str
    description: str
    severity: str
    category: str


class EventListResponse(BaseModel):
    """Schema for event metadata list"""

    events: List[EventMetadata]


class ChannelMetadata(BaseModel):
    """Channel metadata for UI display"""

    type: str
    name: str
    description: str
    config_fields: List[str]


class ChannelMetadataListResponse(BaseModel):
    """Schema for channel metadata list"""

    channels: List[ChannelMetadata]
