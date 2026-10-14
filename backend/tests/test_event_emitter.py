"""Unit tests for event_emitter utility (app/services/event_emitter.py)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import event_emitter


class TestEmitEvent:
    @pytest.mark.asyncio
    async def test_returns_empty_when_service_not_set(self):
        with patch.object(event_emitter, "get_notification_service", return_value=None):
            result = await event_emitter.emit_event("terminal.blocked")
        assert result == []

    @pytest.mark.asyncio
    async def test_emits_via_service(self):
        service = MagicMock()
        service.emit = AsyncMock(return_value=["r1"])
        with patch.object(event_emitter, "get_notification_service", return_value=service):
            result = await event_emitter.emit_event(
                "terminal.blocked",
                data={"ip": "1.2.3.4"},
                source="scheduler",
                severity="warning",
            )
        assert result == ["r1"]
        service.emit.assert_awaited_once_with(
            event_type="terminal.blocked",
            data={"ip": "1.2.3.4"},
            source="scheduler",
            severity="warning",
        )

    @pytest.mark.asyncio
    async def test_returns_empty_when_service_has_no_emit(self):
        service = object()  # no emit attribute
        with patch.object(event_emitter, "get_notification_service", return_value=service):
            result = await event_emitter.emit_event("terminal.blocked")
        assert result == []

    @pytest.mark.asyncio
    async def test_swallows_emit_exception(self):
        service = MagicMock()
        service.emit = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(event_emitter, "get_notification_service", return_value=service):
            result = await event_emitter.emit_event("terminal.blocked")
        assert result == []


class TestEmitEventSync:
    def test_no_running_loop_runs_via_asyncio_run(self):
        with patch("app.services.event_emitter.asyncio.get_running_loop", side_effect=RuntimeError), \
             patch("app.services.event_emitter.asyncio.run") as m_run, \
             patch.object(event_emitter, "emit_event", new=MagicMock()):
            event_emitter.emit_event_sync("terminal.blocked")
        m_run.assert_called_once()

    def test_running_loop_schedules_task(self):
        loop = MagicMock()
        with patch("app.services.event_emitter.asyncio.get_running_loop", return_value=loop), \
             patch.object(event_emitter, "emit_event", new=MagicMock()) as m_emit:
            event_emitter.emit_event_sync("terminal.blocked")
        loop.create_task.assert_called_once()
        m_emit.assert_called_once_with("terminal.blocked", None, "system", "info")


class TestSetGetService:
    def test_set_and_get_notification_service(self):
        sentinel = object()
        event_emitter.set_notification_service(sentinel)
        assert event_emitter.get_notification_service() is sentinel
        event_emitter.set_notification_service(None)


# (func, args, event_type, source, severity, expected_data)
_CONVENIENCE_EMITTERS = [
    (event_emitter.emit_terminal_blocked, ("1.2.3.4", "aa:bb:cc", "reason", "system"),
     "terminal.blocked", "system", "warning",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc", "reason": "reason", "blocked_by": "system"}),
    (event_emitter.emit_terminal_unblocked, ("1.2.3.4", "aa:bb:cc", "admin"),
     "terminal.unblocked", "system", "info",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc", "unblocked_by": "admin"}),
    (event_emitter.emit_login_failed, ("alice", "1.2.3.4", "bad password"),
     "security.login_failed", "system", "warning",
     {"username": "alice", "ip_address": "1.2.3.4", "reason": "bad password"}),
    (event_emitter.emit_login_success, ("alice", "1.2.3.4"),
     "security.login_success", "system", "info",
     {"username": "alice", "ip_address": "1.2.3.4"}),
    (event_emitter.emit_user_created, ("alice", "admin"),
     "security.user_created", "system", "info",
     {"username": "alice", "created_by": "admin"}),
    (event_emitter.emit_user_deleted, ("alice", "admin"),
     "security.user_deleted", "system", "warning",
     {"username": "alice", "deleted_by": "admin"}),
    (event_emitter.emit_user_updated, ("alice", "admin", {"role": "x"}),
     "security.user_updated", "system", "info",
     {"username": "alice", "updated_by": "admin", "changes": {"role": "x"}}),
    (event_emitter.emit_password_changed, ("alice",),
     "security.password_changed", "system", "info", {"username": "alice"}),
    (event_emitter.emit_role_changed, ("alice", "admin", "assigned", {"old_role": "viewer", "new_role": "admin"}),
     "admin.role_changed", "system", "warning",
     {"subject": "alice", "changed_by": "admin", "action": "assigned", "old_role": "viewer", "new_role": "admin"}),
    (event_emitter.emit_datasource_sync_failed, ("src", "arp_ssh", "err"),
     "system.datasource_sync_failed", "scheduler", "error",
     {"source_name": "src", "source_tag": "arp_ssh", "error": "err"}),
    (event_emitter.emit_backup_completed, ("/backups/x.zip", 2 * 1024 * 1024),
     "system.backup_completed", "scheduler", "info",
     {"backup_path": "/backups/x.zip", "file_size_mb": 2.0}),
    (event_emitter.emit_backup_failed, ("err",),
     "system.backup_failed", "scheduler", "error", {"error": "err"}),
    (event_emitter.emit_login_locked, ("alice", "1.2.3.4"),
     "security.login_locked", "system", "error",
     {"username": "alice", "ip_address": "1.2.3.4"}),
    (event_emitter.emit_password_reset_requested, ("alice", "a@x.com"),
     "security.password_reset_requested", "system", "info",
     {"username": "alice", "email": "a@x.com"}),
    (event_emitter.emit_password_reset, ("alice",),
     "security.password_reset", "system", "info", {"username": "alice"}),
    (event_emitter.emit_verification_code_sent, ("a@x.com", "reset"),
     "security.verification_code_sent", "system", "info",
     {"email": "a@x.com", "code_type": "reset"}),
    (event_emitter.emit_email_verified, ("alice", "a@x.com"),
     "security.email_verified", "system", "info",
     {"username": "alice", "email": "a@x.com"}),
    (event_emitter.emit_datasource_sync_success, ("src", "arp_ssh", 10),
     "system.datasource_sync_success", "scheduler", "info",
     {"source_name": "src", "source_tag": "arp_ssh", "record_count": 10}),
    (event_emitter.emit_firewall_connection_lost, ("fw1", "timeout"),
     "system.firewall_connection_lost", "system", "error",
     {"firewall_tag": "fw1", "error": "timeout"}),
    (event_emitter.emit_firewall_connection_restored, ("fw1",),
     "system.firewall_connection_restored", "system", "info", {"firewall_tag": "fw1"}),
    (event_emitter.emit_system_error, ("TypeX", "boom", {"extra": "v"}),
     "system.error", "system", "error",
     {"error_type": "TypeX", "message": "boom", "extra": "v"}),
    (event_emitter.emit_system_warning, ("WarnX", "msg"),
     "system.warning", "system", "warning", {"warning_type": "WarnX", "message": "msg"}),
    (event_emitter.emit_system_alert, ("AlertX", "msg", {"k": "v"}),
     "system.alert", "system", "error", {"alert_type": "AlertX", "message": "msg", "k": "v"}),
    (event_emitter.emit_config_changed, ("some.key", "admin", None, "x"),
     "admin.config_changed", "system", "info",
     {"config_key": "some.key", "changed_by": "admin", "old_value": None, "new_value": "x"}),
    (event_emitter.emit_permission_changed, ("alice", "admin", "perm:read", "grant"),
     "admin.permission_changed", "system", "warning",
     {"username": "alice", "changed_by": "admin", "permission": "perm:read", "action": "grant"}),
    (event_emitter.emit_auto_block_triggered, ("1.2.3.4", "aa:bb:cc", "reason"),
     "alert.auto_block_triggered", "system", "warning",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc", "reason": "reason"}),
    (event_emitter.emit_auto_unblock_triggered, ("1.2.3.4", "aa:bb:cc"),
     "alert.auto_unblock_triggered", "system", "info",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc"}),
    (event_emitter.emit_block_threshold_exceeded, (100, 90),
     "alert.block_threshold", "system", "warning",
     {"threshold": 100, "current_count": 90}),
    (event_emitter.emit_policy_violation, ("pol", "1.2.3.4", {"rule": "r1"}),
     "alert.policy_violation", "system", "error",
     {"policy_name": "pol", "terminal_ip": "1.2.3.4", "rule": "r1"}),
    (event_emitter.emit_terminal_compliant, ("1.2.3.4", "aa:bb:cc"),
     "terminal.compliant", "system", "info",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc"}),
    (event_emitter.emit_terminal_non_compliant, ("1.2.3.4", "aa:bb:cc", ["r1", "r2"]),
     "terminal.non_compliant", "system", "warning",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc", "reasons": ["r1", "r2"]}),
    (event_emitter.emit_terminal_online, ("1.2.3.4", "aa:bb:cc"),
     "terminal.online", "system", "info",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc"}),
    (event_emitter.emit_terminal_offline, ("1.2.3.4", "aa:bb:cc"),
     "terminal.offline", "system", "warning",
     {"ip_address": "1.2.3.4", "mac_address": "aa:bb:cc"}),
]


class TestConvenienceEmitters:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "func,args,event_type,source,severity,expected_data",
        _CONVENIENCE_EMITTERS,
        ids=lambda val: val if isinstance(val, str) else "",
    )
    async def test_forward_to_emit_event(self, func, args, event_type, source, severity, expected_data):
        with patch.object(event_emitter, "emit_event", new=AsyncMock(return_value=[])) as m:
            await func(*args)
        m.assert_awaited_once()
        assert m.await_args.kwargs["event_type"] == event_type
        assert m.await_args.kwargs["source"] == source
        assert m.await_args.kwargs["severity"] == severity
        assert m.await_args.kwargs["data"] == expected_data


class TestEmitComplianceAlert:
    @pytest.mark.asyncio
    async def test_no_emit_when_rate_above_threshold(self):
        with patch("app.services.config_service.get_config_value", new=AsyncMock(return_value="50")), \
             patch.object(event_emitter, "emit_event", new=AsyncMock()) as m:
            result = await event_emitter.emit_compliance_alert(
                compliance_rate=90, non_compliant_count=1, threshold=80
            )
        assert result == []
        m.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_when_not_critical(self):
        with patch("app.services.config_service.get_config_value", new=AsyncMock(return_value="50")), \
             patch.object(event_emitter, "emit_event", new=AsyncMock(return_value=["ok"])) as m:
            await event_emitter.emit_compliance_alert(
                compliance_rate=60, non_compliant_count=5, threshold=80
            )
        # 60 >= 80*50/100 = 40 -> not critical -> low
        assert m.await_args.kwargs["event_type"] == "alert.compliance_rate_low"
        assert m.await_args.kwargs["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_critical_when_below_critical_ratio(self):
        with patch("app.services.config_service.get_config_value", new=AsyncMock(return_value="50")), \
             patch.object(event_emitter, "emit_event", new=AsyncMock(return_value=["ok"])) as m:
            await event_emitter.emit_compliance_alert(
                compliance_rate=30, non_compliant_count=5, threshold=80
            )
        # 30 < 40 -> critical
        assert m.await_args.kwargs["event_type"] == "alert.compliance_rate_critical"
        assert m.await_args.kwargs["severity"] == "error"

    @pytest.mark.asyncio
    async def test_data_includes_counts_when_provided(self):
        with patch("app.services.config_service.get_config_value", new=AsyncMock(return_value="50")), \
             patch.object(event_emitter, "emit_event", new=AsyncMock(return_value=["ok"])) as m:
            await event_emitter.emit_compliance_alert(
                compliance_rate=60,
                non_compliant_count=5,
                threshold=80,
                compliant_count=40,
                bypass_count=10,
                total_checked=100,
            )
        data = m.await_args.kwargs["data"]
        assert data["total_checked"] == 100
        assert data["compliant_count"] == 40
        assert data["bypass_count"] == 10