"""
Notification API Endpoints for TerminalAccessManager.

Provides REST API for managing notification channels and viewing notification logs.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.notification import (
    ChannelMetadataListResponse,
    ChannelMetadata,
    ChannelTestResultResponse,
    EventListResponse,
    EventMetadata,
    NotificationChannelCreate,
    NotificationChannelResponse,
    NotificationChannelUpdate,
    NotificationLogListResponse,
    NotificationLogResponse,
)
from app.services.notification_service import NotificationService
from app.services.notification_channels.event_types import CHANNEL_METADATA, EVENT_METADATA

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_notification_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    """Dependency to get NotificationService instance"""
    return NotificationService(db)


@router.get("/channels", response_model=list[NotificationChannelResponse])
async def list_channels(
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:read")),
):
    """List all notification channels"""
    channels = await notification_service.get_channels()
    return channels


@router.post("/channels", response_model=NotificationChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    channel_data: NotificationChannelCreate,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:manage")),
):
    """Create a new notification channel"""
    channel = await notification_service.create_channel(
        name=channel_data.name,
        channel_type=channel_data.type,
        config=channel_data.config,
        events=channel_data.events,
        description=channel_data.description,
        created_by=current_user.username,
        enabled=channel_data.enabled,
    )
    return channel


@router.get("/channels/{channel_id}", response_model=NotificationChannelResponse)
async def get_channel(
    channel_id: int,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:read")),
):
    """Get a notification channel by ID"""
    channel = await notification_service.get_channel_by_id(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.put("/channels/{channel_id}", response_model=NotificationChannelResponse)
async def update_channel(
    channel_id: int,
    channel_data: NotificationChannelUpdate,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:manage")),
):
    """Update a notification channel"""
    channel = await notification_service.update_channel(
        channel_id=channel_id,
        name=channel_data.name,
        config=channel_data.config,
        events=channel_data.events,
        description=channel_data.description,
        enabled=channel_data.enabled,
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:manage")),
):
    """Delete a notification channel"""
    deleted = await notification_service.delete_channel(channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found")


@router.post("/channels/{channel_id}/test", response_model=ChannelTestResultResponse)
async def test_channel(
    channel_id: int,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:manage")),
):
    """Test a notification channel connection"""
    result = await notification_service.test_channel(channel_id)
    return ChannelTestResultResponse(**result)


@router.get("/logs", response_model=NotificationLogListResponse)
async def list_notification_logs(
    channel_name: Optional[str] = Query(None, description="Filter by channel name"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status: Optional[str] = Query(None, description="Filter by status (sent, failed)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:read")),
):
    """List notification logs with optional filtering"""
    logs, total = await notification_service.get_notification_logs(
        channel_name=channel_name,
        event_type=event_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    return NotificationLogListResponse(
        items=[NotificationLogResponse.model_validate(log) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/events", response_model=EventListResponse)
async def list_events(
    current_user: User = Depends(get_current_user),
):
    """List all available event types with metadata"""
    events = [
        EventMetadata(
            type=event_type.value,
            name=metadata["name"],
            description=metadata["description"],
            severity=metadata["severity"],
            category=metadata["category"],
        )
        for event_type, metadata in EVENT_METADATA.items()
    ]
    return EventListResponse(events=events)


@router.get("/channel-types", response_model=ChannelMetadataListResponse)
async def list_channel_types(
    current_user: User = Depends(get_current_user),
):
    """List all available channel types with metadata"""
    channels = [
        ChannelMetadata(
            type=channel_type.value,
            name=metadata["name"],
            description=metadata["description"],
            config_fields=metadata["config_fields"],
        )
        for channel_type, metadata in CHANNEL_METADATA.items()
    ]
    return ChannelMetadataListResponse(channels=channels)
