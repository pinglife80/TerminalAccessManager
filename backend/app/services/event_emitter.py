"""
Event Emitter Utility for TerminalAccessManager.

Provides a simple interface for emitting events from anywhere in the application.
"""

import asyncio
from typing import Any

from loguru import logger

# Global notification service reference (set during app startup).
# Module-level singleton instead of ContextVar: ContextVar does not propagate
# across uvicorn request tasks nor asyncio scheduler tasks spawned in lifespan,
# which would silently drop events. A module-level singleton is shared by all
# coroutines in the same process and is safe because NotificationService uses
# short-lived AsyncSession scopes per operation.
_notification_service_instance: Any | None = None


def set_notification_service(service: Any) -> None:
    """Set the global notification service instance"""
    global _notification_service_instance
    _notification_service_instance = service


def get_notification_service() -> Any | None:
    """Get the global notification service instance"""
    return _notification_service_instance


async def emit_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    source: str = "system",
    severity: str = "info",
) -> list[Any]:
    """
    Emit an event to all subscribed notification channels.

    This is a fire-and-forget operation - errors are logged but not raised.

    Args:
        event_type: Event type (e.g., "terminal.blocked")
        data: Event data payload
        source: Event source (system, user, scheduler)
        severity: Severity level (info, warning, error)

    Returns:
        List of notification results (may be empty if service not initialized)
    """
    service = get_notification_service()
    if not service:
        logger.debug(f"Notification service not initialized, skipping event: {event_type}")
        return []

    try:
        # Check if emit method exists
        if hasattr(service, "emit"):
            results = await service.emit(
                event_type=event_type,
                data=data,
                source=source,
                severity=severity,
            )
            return results
        else:
            logger.warning("Notification service has no emit method")
            return []
    except Exception as e:
        logger.error(f"Failed to emit event {event_type}: {e}")
        return []


def emit_event_sync(
    event_type: str,
    data: dict[str, Any] | None = None,
    source: str = "system",
    severity: str = "info",
) -> None:
    """
    Synchronous wrapper for emit_event.

    Uses asyncio.run() for non-async contexts (use with caution in async code).
    """
    try:
        loop = asyncio.get_running_loop()
        # If already in async context, schedule the task
        loop.create_task(emit_event(event_type, data, source, severity))
    except RuntimeError:
        # No running loop, create new one
        asyncio.run(emit_event(event_type, data, source, severity))


# ==================== Convenience Functions ====================


async def emit_terminal_blocked(
    ip_address: str,
    mac_address: str,
    reason: str,
    blocked_by: str,
) -> list[Any]:
    """Emit terminal blocked event"""
    return await emit_event(
        event_type="terminal.blocked",
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
    ip_address: str,
    mac_address: str,
    unblocked_by: str,
) -> list[Any]:
    """Emit terminal unblocked event"""
    return await emit_event(
        event_type="terminal.unblocked",
        data={
            "ip_address": ip_address,
            "mac_address": mac_address,
            "unblocked_by": unblocked_by,
        },
        source="system",
        severity="info",
    )


async def emit_login_failed(
    username: str,
    ip_address: str,
    reason: str,
) -> list[Any]:
    """Emit login failed event"""
    return await emit_event(
        event_type="security.login_failed",
        data={
            "username": username,
            "ip_address": ip_address,
            "reason": reason,
        },
        source="system",
        severity="warning",
    )


async def emit_login_success(
    username: str,
    ip_address: str,
) -> list[Any]:
    """Emit login success event"""
    return await emit_event(
        event_type="security.login_success",
        data={
            "username": username,
            "ip_address": ip_address,
        },
        source="system",
        severity="info",
    )


async def emit_user_created(
    username: str,
    created_by: str,
) -> list[Any]:
    """Emit user created event"""
    return await emit_event(
        event_type="security.user_created",
        data={
            "username": username,
            "created_by": created_by,
        },
        source="system",
        severity="info",
    )


async def emit_datasource_sync_failed(
    source_name: str,
    source_tag: str,
    error: str,
) -> list[Any]:
    """Emit datasource sync failed event"""
    return await emit_event(
        event_type="system.datasource_sync_failed",
        data={
            "source_name": source_name,
            "source_tag": source_tag,
            "error": error,
        },
        source="scheduler",
        severity="error",
    )


async def emit_compliance_alert(
    compliance_rate: float,
    non_compliant_count: int,
    threshold: float,
) -> list[Any]:
    """Emit compliance alert event"""
    is_critical = compliance_rate < threshold * 0.5
    event_type = (
        "alert.compliance_rate_critical" if is_critical else "alert.compliance_rate_low"
    )
    severity = "error" if is_critical else "warning"

    return await emit_event(
        event_type=event_type,
        data={
            "compliance_rate": f"{compliance_rate:.1f}%",
            "non_compliant_count": non_compliant_count,
            "threshold": f"{threshold * 100:.0f}%",
        },
        source="scheduler",
        severity=severity,
    )


async def emit_backup_completed(
    backup_path: str,
    file_size: int,
) -> list[Any]:
    """Emit backup completed event"""
    return await emit_event(
        event_type="system.backup_completed",
        data={
            "backup_path": backup_path,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
        },
        source="scheduler",
        severity="info",
    )


async def emit_backup_failed(
    error: str,
) -> list[Any]:
    """Emit backup failed event"""
    return await emit_event(
        event_type="system.backup_failed",
        data={
            "error": error,
        },
        source="scheduler",
        severity="error",
    )
