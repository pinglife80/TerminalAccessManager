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


async def emit_user_deleted(
    username: str,
    deleted_by: str,
) -> list[Any]:
    """Emit user deleted event"""
    return await emit_event(
        event_type="security.user_deleted",
        data={
            "username": username,
            "deleted_by": deleted_by,
        },
        source="system",
        severity="warning",
    )


async def emit_user_updated(
    username: str,
    updated_by: str,
    changes: dict,
) -> list[Any]:
    """Emit user updated event"""
    return await emit_event(
        event_type="security.user_updated",
        data={
            "username": username,
            "updated_by": updated_by,
            "changes": changes,
        },
        source="system",
        severity="info",
    )


async def emit_password_changed(
    username: str,
) -> list[Any]:
    """Emit password changed event"""
    return await emit_event(
        event_type="security.password_changed",
        data={
            "username": username,
        },
        source="system",
        severity="info",
    )


async def emit_role_changed(
    username: str,
    changed_by: str,
    old_role: str,
    new_role: str,
) -> list[Any]:
    """Emit role changed event"""
    return await emit_event(
        event_type="admin.role_changed",
        data={
            "username": username,
            "changed_by": changed_by,
            "old_role": old_role,
            "new_role": new_role,
        },
        source="system",
        severity="warning",
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


async def emit_login_locked(
    username: str,
    ip_address: str,
) -> list[Any]:
    """Emit login locked event"""
    return await emit_event(
        event_type="security.login_locked",
        data={
            "username": username,
            "ip_address": ip_address,
        },
        source="system",
        severity="error",
    )


async def emit_password_reset_requested(
    username: str,
    email: str,
) -> list[Any]:
    """Emit password reset requested event"""
    return await emit_event(
        event_type="security.password_reset_requested",
        data={
            "username": username,
            "email": email,
        },
        source="system",
        severity="info",
    )


async def emit_verification_code_sent(
    email: str,
    code_type: str,
) -> list[Any]:
    """Emit verification code sent event"""
    return await emit_event(
        event_type="security.verification_code_sent",
        data={
            "email": email,
            "code_type": code_type,
        },
        source="system",
        severity="info",
    )


async def emit_email_verified(
    username: str,
    email: str,
) -> list[Any]:
    """Emit email verified event"""
    return await emit_event(
        event_type="security.email_verified",
        data={
            "username": username,
            "email": email,
        },
        source="system",
        severity="info",
    )


async def emit_datasource_sync_success(
    source_name: str,
    source_tag: str,
    record_count: int,
) -> list[Any]:
    """Emit datasource sync success event"""
    return await emit_event(
        event_type="system.datasource_sync_success",
        data={
            "source_name": source_name,
            "source_tag": source_tag,
            "record_count": record_count,
        },
        source="scheduler",
        severity="info",
    )


async def emit_firewall_connection_lost(
    firewall_tag: str,
    error: str,
) -> list[Any]:
    """Emit firewall connection lost event"""
    return await emit_event(
        event_type="system.firewall_connection_lost",
        data={
            "firewall_tag": firewall_tag,
            "error": error,
        },
        source="system",
        severity="error",
    )


async def emit_firewall_connection_restored(
    firewall_tag: str,
) -> list[Any]:
    """Emit firewall connection restored event"""
    return await emit_event(
        event_type="system.firewall_connection_restored",
        data={
            "firewall_tag": firewall_tag,
        },
        source="system",
        severity="info",
    )


async def emit_system_error(
    error_type: str,
    message: str,
    details: dict | None = None,
) -> list[Any]:
    """Emit system error event"""
    return await emit_event(
        event_type="system.system_error",
        data={
            "error_type": error_type,
            "message": message,
            **(details or {}),
        },
        source="system",
        severity="error",
    )


async def emit_system_warning(
    warning_type: str,
    message: str,
) -> list[Any]:
    """Emit system warning event"""
    return await emit_event(
        event_type="system.system_warning",
        data={
            "warning_type": warning_type,
            "message": message,
        },
        source="system",
        severity="warning",
    )


async def emit_system_alert(
    alert_type: str,
    message: str,
    details: dict | None = None,
) -> list[Any]:
    """Emit system alert event"""
    return await emit_event(
        event_type="system.system_alert",
        data={
            "alert_type": alert_type,
            "message": message,
            **(details or {}),
        },
        source="system",
        severity="error",
    )


async def emit_config_changed(
    config_key: str,
    changed_by: str,
    old_value: str | None = None,
    new_value: str | None = None,
) -> list[Any]:
    """Emit config changed event"""
    return await emit_event(
        event_type="admin.config_changed",
        data={
            "config_key": config_key,
            "changed_by": changed_by,
            "old_value": old_value,
            "new_value": new_value,
        },
        source="system",
        severity="info",
    )


async def emit_permission_changed(
    username: str,
    changed_by: str,
    permission: str,
    action: str,
) -> list[Any]:
    """Emit permission changed event"""
    return await emit_event(
        event_type="admin.permission_changed",
        data={
            "username": username,
            "changed_by": changed_by,
            "permission": permission,
            "action": action,
        },
        source="system",
        severity="warning",
    )


async def emit_auto_block_triggered(
    ip_address: str,
    mac_address: str,
    reason: str,
) -> list[Any]:
    """Emit auto block triggered event"""
    return await emit_event(
        event_type="alert.auto_block_triggered",
        data={
            "ip_address": ip_address,
            "mac_address": mac_address,
            "reason": reason,
        },
        source="system",
        severity="warning",
    )


async def emit_auto_unblock_triggered(
    ip_address: str,
    mac_address: str,
) -> list[Any]:
    """Emit auto unblock triggered event"""
    return await emit_event(
        event_type="alert.auto_unblock_triggered",
        data={
            "ip_address": ip_address,
            "mac_address": mac_address,
        },
        source="system",
        severity="info",
    )


async def emit_block_threshold_exceeded(
    threshold: int,
    current_count: int,
) -> list[Any]:
    """Emit block threshold exceeded event"""
    return await emit_event(
        event_type="alert.block_threshold",
        data={
            "threshold": threshold,
            "current_count": current_count,
        },
        source="system",
        severity="warning",
    )


async def emit_policy_violation(
    policy_name: str,
    terminal_ip: str,
    details: dict,
) -> list[Any]:
    """Emit policy violation event"""
    return await emit_event(
        event_type="alert.policy_violation",
        data={
            "policy_name": policy_name,
            "terminal_ip": terminal_ip,
            **details,
        },
        source="system",
        severity="error",
    )


async def emit_terminal_compliant(
    ip_address: str,
    mac_address: str,
) -> list[Any]:
    """Emit terminal compliant event"""
    return await emit_event(
        event_type="terminal.compliant",
        data={
            "ip_address": ip_address,
            "mac_address": mac_address,
        },
        source="system",
        severity="info",
    )


async def emit_terminal_non_compliant(
    ip_address: str,
    mac_address: str,
    reasons: list[str],
) -> list[Any]:
    """Emit terminal non-compliant event"""
    return await emit_event(
        event_type="terminal.non_compliant",
        data={
            "ip_address": ip_address,
            "mac_address": mac_address,
            "reasons": reasons,
        },
        source="system",
        severity="warning",
    )


async def emit_terminal_online(
    ip_address: str,
    mac_address: str,
) -> list[Any]:
    """Emit terminal online event"""
    return await emit_event(
        event_type="terminal.online",
        data={
            "ip_address": ip_address,
            "mac_address": mac_address,
        },
        source="system",
        severity="info",
    )


async def emit_terminal_offline(
    ip_address: str,
    mac_address: str,
) -> list[Any]:
    """Emit terminal offline event"""
    return await emit_event(
        event_type="terminal.offline",
        data={
            "ip_address": ip_address,
            "mac_address": mac_address,
        },
        source="system",
        severity="warning",
    )
