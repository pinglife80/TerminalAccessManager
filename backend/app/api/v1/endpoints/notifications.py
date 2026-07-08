"""
Notification API Endpoints for TerminalAccessManager.

Provides REST API for managing notification channels and viewing notification logs.
"""


from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_client_ip, get_current_user, require_permission
from app.services.terminal_service import TerminalService
from app.models.notification import NotificationRule, NotificationTemplate
from app.models.user import User
from app.schemas.notification import (
    ChannelMetadata,
    ChannelMetadataListResponse,
    ChannelStat,
    ChannelTestResultResponse,
    EventListResponse,
    EventMetadata,
    EventStat,
    NotificationChannelCreate,
    NotificationChannelResponse,
    NotificationChannelUpdate,
    NotificationLogListResponse,
    NotificationLogResponse,
    NotificationRuleCreate,
    NotificationRuleResponse,
    NotificationRuleUpdate,
    NotificationStatsOverview,
    NotificationStatsResponse,
    NotificationTemplateCreate,
    NotificationTemplatePreviewRequest,
    NotificationTemplatePreviewResponse,
    NotificationTemplateResponse,
    NotificationTemplateUpdate,
)
from app.services.notification_channels.event_types import CHANNEL_METADATA, EVENT_METADATA
from app.services.notification_service import NotificationService

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
    request: Request,
    notification_service: NotificationService = Depends(get_notification_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
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
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "create_notification_channel", "notification_channel",
        str(channel.id),
        {"name": channel.name, "type": channel.type, "enabled": channel.enabled},
        ip_address=get_client_ip(request),
        resource_name=channel.name,
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
    request: Request,
    notification_service: NotificationService = Depends(get_notification_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
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
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "update_notification_channel", "notification_channel",
        str(channel.id),
        {"name": channel.name, "enabled": channel.enabled},
        ip_address=get_client_ip(request),
        resource_name=channel.name,
    )
    return channel


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    request: Request,
    notification_service: NotificationService = Depends(get_notification_service),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Delete a notification channel"""
    channel = await notification_service.get_channel_by_id(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel_name = channel.name
    deleted = await notification_service.delete_channel(channel_id)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "delete_notification_channel", "notification_channel",
        str(channel_id),
        {"name": channel_name},
        ip_address=get_client_ip(request),
        resource_name=channel_name,
    )


@router.post("/channels/{channel_id}/test", response_model=ChannelTestResultResponse)
async def test_channel(
    channel_id: int,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Test a notification channel connection"""
    result = await notification_service.test_channel(channel_id)
    return ChannelTestResultResponse(**result)


@router.get("/logs", response_model=NotificationLogListResponse)
async def list_notification_logs(
    channel_name: str | None = Query(None, description="Filter by channel name"),
    event_type: str | None = Query(None, description="Filter by event type"),
    status: str | None = Query(None, description="Filter by status (sent, failed)"),
    archived: bool | None = Query(False, description="Include archived logs"),
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
        archived=archived,
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


# ==================== Notification Templates ====================


@router.get("/templates", response_model=list[NotificationTemplateResponse])
async def list_templates(
    event_type: str | None = Query(None, description="Filter by event type"),
    channel_type: str | None = Query(None, description="Filter by channel type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:read")),
):
    """List all notification templates with optional filtering"""
    stmt = select(NotificationTemplate).order_by(NotificationTemplate.created_at.desc())
    if event_type:
        stmt = stmt.where(NotificationTemplate.event_type == event_type)
    if channel_type:
        stmt = stmt.where(NotificationTemplate.channel_type == channel_type)
    result = await db.execute(stmt)
    templates = result.scalars().all()
    return [NotificationTemplateResponse.model_validate(t) for t in templates]


@router.post("/templates", response_model=NotificationTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: NotificationTemplateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Create a new notification template"""
    if template_data.event_type not in EVENT_METADATA:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {template_data.event_type}")
    valid_channels = {ct.value for ct in CHANNEL_METADATA}
    if template_data.channel_type not in valid_channels:
        raise HTTPException(status_code=400, detail=f"Invalid channel_type: {template_data.channel_type}")

    template = NotificationTemplate(
        name=template_data.name,
        event_type=template_data.event_type,
        channel_type=template_data.channel_type,
        subject_template=template_data.subject_template,
        body_template=template_data.body_template,
        is_default=template_data.is_default,
        created_by=current_user.username,
    )
    db.add(template)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Template name or event+channel combination already exists")
    await db.refresh(template)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "create_notification_template", "notification_template",
        str(template.id),
        {"name": template.name, "event_type": template.event_type, "channel_type": template.channel_type},
        ip_address=get_client_ip(request),
        resource_name=template.name,
    )
    return NotificationTemplateResponse.model_validate(template)


@router.get("/templates/{template_id}", response_model=NotificationTemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:read")),
):
    """Get a specific notification template by ID"""
    result = await db.execute(
        select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return NotificationTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=NotificationTemplateResponse)
async def update_template(
    template_id: int,
    template_data: NotificationTemplateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Update a notification template"""
    result = await db.execute(
        select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    update_fields = template_data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(template, key, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Template name or event+channel combination already exists")
    await db.refresh(template)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "update_notification_template", "notification_template",
        str(template.id),
        {"name": template.name, "event_type": template.event_type, "channel_type": template.channel_type},
        ip_address=get_client_ip(request),
        resource_name=template.name,
    )
    return NotificationTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Delete a notification template"""
    result = await db.execute(
        select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    template_name = template.name
    await db.delete(template)
    await db.commit()
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "delete_notification_template", "notification_template",
        str(template_id),
        {"name": template_name},
        ip_address=get_client_ip(request),
        resource_name=template_name,
    )


@router.post("/templates/preview", response_model=NotificationTemplatePreviewResponse)
async def preview_template(
    preview_data: NotificationTemplatePreviewRequest,
    current_user: User = Depends(require_permission("notification:read")),
):
    """Preview a template rendering with sample data.

    Renders the provided Jinja2 templates with sample event data so the
    admin can see what the final message will look like before saving.
    """
    import jinja2

    # Validate event_type
    if preview_data.event_type not in EVENT_METADATA:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {preview_data.event_type}")

    metadata = EVENT_METADATA[preview_data.event_type]
    from datetime import datetime

    context = {
        "event_type": preview_data.event_type,
        "event_name": metadata.get("name", preview_data.event_type),
        "description": metadata.get("description", ""),
        "severity": metadata.get("severity", "info"),
        "source": "preview",
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "data": preview_data.sample_data,
    }

    env = jinja2.Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)

    try:
        subject = ""
        if preview_data.subject_template:
            subject = env.from_string(preview_data.subject_template).render(**context)
        body = env.from_string(preview_data.body_template).render(**context)
    except jinja2.TemplateSyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Template syntax error: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template render error: {e}")

    return NotificationTemplatePreviewResponse(subject=subject, body=body)


# ==================== Notification Rules ====================


@router.get("/rules", response_model=list[NotificationRuleResponse])
async def list_rules(
    event_type: str | None = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:read")),
):
    """List all notification rules with optional filtering"""
    stmt = select(NotificationRule).order_by(NotificationRule.created_at.desc())
    if event_type:
        stmt = stmt.where(NotificationRule.event_type == event_type)
    result = await db.execute(stmt)
    rules = result.scalars().all()
    return [NotificationRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=NotificationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    rule_data: NotificationRuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Create a new notification rule"""
    if rule_data.event_type not in EVENT_METADATA:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {rule_data.event_type}")

    valid_severities = {"info", "warning", "error", "critical"}
    if rule_data.escalate_severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid escalate_severity: {rule_data.escalate_severity}. Must be one of: {', '.join(sorted(valid_severities))}",
        )

    rule = NotificationRule(
        name=rule_data.name,
        event_type=rule_data.event_type,
        channel_name=rule_data.channel_name,
        enabled=rule_data.enabled,
        description=rule_data.description,
        suppress_enabled=rule_data.suppress_enabled,
        suppress_window=rule_data.suppress_window,
        escalate_enabled=rule_data.escalate_enabled,
        escalate_threshold=rule_data.escalate_threshold,
        escalate_window=rule_data.escalate_window,
        escalate_severity=rule_data.escalate_severity,
        created_by=current_user.username,
    )
    db.add(rule)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Rule name already exists, or a rule for this event+channel combination already exists",
        )
    await db.refresh(rule)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "create_notification_rule", "notification_rule",
        str(rule.id),
        {"name": rule.name, "event_type": rule.event_type, "channel_name": rule.channel_name, "enabled": rule.enabled},
        ip_address=get_client_ip(request),
        resource_name=rule.name,
    )
    return NotificationRuleResponse.model_validate(rule)


@router.get("/rules/{rule_id}", response_model=NotificationRuleResponse)
async def get_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:read")),
):
    """Get a specific notification rule by ID"""
    result = await db.execute(
        select(NotificationRule).where(NotificationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return NotificationRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=NotificationRuleResponse)
async def update_rule(
    rule_id: int,
    rule_data: NotificationRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Update a notification rule"""
    result = await db.execute(
        select(NotificationRule).where(NotificationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    new_event_type = rule_data.event_type or rule.event_type
    if new_event_type not in EVENT_METADATA:
        raise HTTPException(status_code=400, detail=f"Invalid event_type: {new_event_type}")

    new_severity = rule_data.escalate_severity or rule.escalate_severity
    valid_severities = {"info", "warning", "error", "critical"}
    if new_severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid escalate_severity: {new_severity}. Must be one of: {', '.join(sorted(valid_severities))}",
        )

    update_fields = rule_data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(rule, key, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Rule name already exists, or a rule for this event+channel combination already exists",
        )
    await db.refresh(rule)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "update_notification_rule", "notification_rule",
        str(rule.id),
        {"name": rule.name, "event_type": rule.event_type, "channel_name": rule.channel_name, "enabled": rule.enabled},
        ip_address=get_client_ip(request),
        resource_name=rule.name,
    )
    return NotificationRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Delete a notification rule"""
    result = await db.execute(
        select(NotificationRule).where(NotificationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule_name = rule.name
    await db.delete(rule)
    await db.commit()
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "delete_notification_rule", "notification_rule",
        str(rule_id),
        {"name": rule_name},
        ip_address=get_client_ip(request),
        resource_name=rule_name,
    )


# ==================== Statistics & Monitoring ====================


@router.get("/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:read")),
):
    """Get notification statistics overview with breakdowns"""
    stats = await notification_service.get_statistics()
    return NotificationStatsResponse(
        overview=NotificationStatsOverview(**stats["overview"]),
        by_channel=[ChannelStat(**c) for c in stats["by_channel"]],
        by_event=[EventStat(**e) for e in stats["by_event"]],
    )


@router.post("/logs/{log_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_notification(
    log_id: int,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Manually retry a failed notification by log ID"""
    success = await notification_service.retry_failed_notification(log_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Notification log not found or not in retryable state (failed/retrying)",
        )
    return {"message": "Notification queued for retry", "log_id": log_id}


@router.post("/logs/retry-all", status_code=status.HTTP_202_ACCEPTED)
async def retry_all_failed_notifications(
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Retry all currently failed notifications"""
    count = await notification_service.retry_all_failed()
    return {"message": f"Queued {count} notification(s) for retry", "count": count}


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Delete a notification log by ID"""
    result = await db.execute(
        select(NotificationLog).where(NotificationLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Notification log not found")
    await db.delete(log)
    await db.commit()


@router.post("/logs/{log_id}/archive", response_model=dict)
async def archive_notification_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Archive a notification log by ID"""
    result = await db.execute(
        select(NotificationLog).where(NotificationLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Notification log not found")
    log.archived = True
    await db.commit()
    await db.refresh(log)
    return {"message": "Notification log archived", "log_id": log_id}


@router.post("/logs/archive-all", response_model=dict)
async def archive_all_notification_logs(
    days: int = Query(30, description="Archive logs older than this number of days"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Archive all notification logs older than specified days"""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = select(NotificationLog).where(
        NotificationLog.sent_at < cutoff,
        NotificationLog.archived == False,
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    count = 0
    for log in logs:
        log.archived = True
        count += 1
    if count > 0:
        await db.commit()
    return {"message": f"Archived {count} notification log(s)", "count": count}


@router.delete("/logs/cleanup", response_model=dict)
async def cleanup_notification_logs(
    days: int = Query(90, description="Delete archived logs older than this number of days"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("notification:write")),
):
    """Clean up (permanently delete) archived notification logs older than specified days"""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = select(NotificationLog).where(
        NotificationLog.sent_at < cutoff,
        NotificationLog.archived == True,
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    count = 0
    for log in logs:
        await db.delete(log)
        count += 1
    if count > 0:
        await db.commit()
    return {"message": f"Cleaned up {count} archived notification log(s)", "count": count}
