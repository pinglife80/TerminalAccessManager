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
    retry_count: int
    next_retry_at: datetime | None
    sent_at: datetime
    completed_at: datetime | None

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


# ==================== Notification Templates ====================


class NotificationTemplateCreate(BaseModel):
    """Schema for creating a notification template"""

    name: str = Field(..., min_length=1, max_length=100, description="Unique template name")
    event_type: str = Field(..., description="Event type this template applies to")
    channel_type: str = Field(..., description="Channel type: email, webhook, feishu, dingtalk, wecom")
    subject_template: str | None = Field(None, description="Jinja2 subject template (optional for non-email channels)")
    body_template: str = Field(..., description="Jinja2 body template")
    is_default: bool = False


class NotificationTemplateUpdate(BaseModel):
    """Schema for updating a notification template"""

    name: str | None = None
    event_type: str | None = None
    channel_type: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    is_default: bool | None = None


class NotificationTemplateResponse(BaseModel):
    """Schema for notification template response"""

    id: int
    name: str
    event_type: str
    channel_type: str
    subject_template: str | None
    body_template: str
    is_default: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationTemplatePreviewRequest(BaseModel):
    """Schema for previewing a template with sample data"""

    event_type: str = Field(..., description="Event type to preview")
    channel_type: str = Field(..., description="Channel type to preview")
    subject_template: str | None = Field(None, description="Subject template to preview")
    body_template: str = Field(..., description="Body template to preview")
    sample_data: dict[str, Any] = Field(default_factory=dict, description="Sample event data for rendering")


class NotificationTemplatePreviewResponse(BaseModel):
    """Schema for template preview result"""

    subject: str
    body: str


# ==================== Notification Rules ====================


class NotificationRuleBase(BaseModel):
    """Base schema for notification rule"""

    name: str = Field(..., min_length=1, max_length=100)
    event_type: str = Field(..., description="Event type this rule applies to")
    channel_name: str | None = Field(None, description="Specific channel name, or None for all channels")
    enabled: bool = True
    description: str | None = None
    suppress_enabled: bool = False
    suppress_window: int = Field(300, ge=1, le=86400, description="Suppression window in seconds (1-86400)")
    escalate_enabled: bool = False
    escalate_threshold: int = Field(5, ge=1, le=1000, description="Event count to trigger escalation")
    escalate_window: int = Field(3600, ge=60, le=604800, description="Escalation counting window in seconds")
    escalate_severity: str = Field("error", description="Severity to escalate to: info, warning, error, critical")


class NotificationRuleCreate(NotificationRuleBase):
    """Schema for creating a notification rule"""

    pass


class NotificationRuleUpdate(BaseModel):
    """Schema for updating a notification rule"""

    name: str | None = None
    event_type: str | None = None
    channel_name: str | None = None
    enabled: bool | None = None
    description: str | None = None
    suppress_enabled: bool | None = None
    suppress_window: int | None = Field(None, ge=1, le=86400)
    escalate_enabled: bool | None = None
    escalate_threshold: int | None = Field(None, ge=1, le=1000)
    escalate_window: int | None = Field(None, ge=60, le=604800)
    escalate_severity: str | None = None


class NotificationRuleResponse(NotificationRuleBase):
    """Schema for notification rule response"""

    id: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Notification Statistics ====================


class NotificationStatsOverview(BaseModel):
    """Overall notification statistics"""

    total: int
    sent: int
    failed: int
    pending: int
    retrying: int
    suppressed: int
    success_rate: float
    avg_latency_ms: float | None = None
    queue_size: int
    retry_queue_size: int


class ChannelStat(BaseModel):
    """Per-channel statistics"""

    channel_name: str
    total: int
    sent: int
    failed: int
    success_rate: float


class EventStat(BaseModel):
    """Per-event-type statistics"""

    event_type: str
    total: int
    sent: int
    failed: int
    success_rate: float


class NotificationStatsResponse(BaseModel):
    """Statistics response with breakdowns"""

    overview: NotificationStatsOverview
    by_channel: list[ChannelStat]
    by_event: list[EventStat]
