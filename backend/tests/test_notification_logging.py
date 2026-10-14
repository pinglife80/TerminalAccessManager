"""Unit tests for NotificationLogger (app/services/notification_logging.py)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.notification import NotificationLog, NotificationTemplate
from app.services.notification_channels.base import NotificationEvent, NotificationResult
from app.services.notification_logging import NotificationLogger


def _event():
    return NotificationEvent(
        id="evt1",
        type="terminal.blocked",
        timestamp=datetime(2026, 1, 1, 12, 0, 0),
        data={"ip_address": "1.2.3.4"},
        source="system",
        severity="warning",
    )


def _result(success=True, channel="email"):
    return NotificationResult(
        success=success,
        message="ok" if success else "boom",
        channel=channel,
        recipient="r@example.com",
        details={"k": "v"},
    )


def _patch_factory(fake_session):
    """Patch async_session_factory to return a context manager yielding fake_session."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch("app.core.database.async_session_factory", return_value=cm)


class TestRenderTemplate:
    def _template(self):
        return NotificationTemplate(
            name="t",
            event_type="terminal.blocked",
            channel_type="email",
            subject_template="Hello {{event_name}}",
            body_template="{{description}} / {{severity}}",
        )

    @pytest.mark.asyncio
    async def test_renders_subject_and_body(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._template()
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        rendered = await logger.render_template(_event(), "email", mock_async_session)

        assert rendered["subject"] == "Hello 终端被封锁"
        assert rendered["body"].startswith("终端已被添加到黑名单")

    @pytest.mark.asyncio
    async def test_empty_subject_when_template_has_none(self, mock_async_session):
        tmpl = self._template()
        tmpl.subject_template = None
        result = MagicMock()
        result.scalar_one_or_none.return_value = tmpl
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        rendered = await logger.render_template(_event(), "email", mock_async_session)

        assert rendered["subject"] == ""
        assert rendered["body"] != ""

    @pytest.mark.asyncio
    async def test_none_when_no_template(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        rendered = await logger.render_template(_event(), "email", mock_async_session)

        assert rendered is None

    @pytest.mark.asyncio
    async def test_none_on_render_error(self, mock_async_session):
        tmpl = self._template()
        tmpl.body_template = "{% invalid_jinja %}"
        result = MagicMock()
        result.scalar_one_or_none.return_value = tmpl
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        rendered = await logger.render_template(_event(), "email", mock_async_session)

        assert rendered is None

    @pytest.mark.asyncio
    async def test_uses_factory_when_no_db(self):
        fake_session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._template()
        fake_session.execute = AsyncMock(return_value=result)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=fake_session)
        cm.__aexit__ = AsyncMock(return_value=False)

        logger = NotificationLogger()
        with patch("app.core.database.async_session_factory", return_value=cm):
            rendered = await logger.render_template(_event(), "email", None)

        assert rendered["subject"] == "Hello 终端被封锁"


class TestLogSuppressed:
    @pytest.mark.asyncio
    async def test_logs_suppressed(self, mock_async_session):
        logger = NotificationLogger(mock_async_session)
        await logger.log_suppressed(_event(), "email", 300, mock_async_session)

        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_called_once()
        added = mock_async_session.add.call_args[0][0]
        assert added.status == "suppressed"
        assert added.details == {"suppression_window": 300}

    @pytest.mark.asyncio
    async def test_uses_factory_when_no_db(self, mock_async_session):
        logger = NotificationLogger()
        with _patch_factory(mock_async_session):
            await logger.log_suppressed(_event(), "email", 300, None)
        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_called_once()
        assert mock_async_session.add.call_args[0][0].status == "suppressed"


class TestLogSent:
    @pytest.mark.asyncio
    async def test_logs_sent(self, mock_async_session):
        logger = NotificationLogger(mock_async_session)
        await logger.log_sent(_event(), "email", _result(success=True), mock_async_session)

        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_called_once()
        added = mock_async_session.add.call_args[0][0]
        assert added.status == "sent"
        assert added.recipient == "r@example.com"
        assert added.details == {"k": "v"}

    @pytest.mark.asyncio
    async def test_uses_factory_when_no_db(self, mock_async_session):
        logger = NotificationLogger()
        with _patch_factory(mock_async_session):
            await logger.log_sent(_event(), "email", _result(success=True), None)
        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_called_once()
        assert mock_async_session.add.call_args[0][0].status == "sent"


class TestLogRetrying:
    @pytest.mark.asyncio
    async def test_updates_existing_log(self, mock_async_session):
        existing = NotificationLog(
            event_id="evt1", channel_name="email", event_type="terminal.blocked", status="failed"
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        next_retry = datetime(2026, 1, 1, 13, 0, 0)
        await logger.log_retrying(_event(), "email", _result(success=False), 2, next_retry, mock_async_session)

        mock_async_session.add.assert_not_called()
        mock_async_session.commit.assert_called_once()
        assert existing.status == "retrying"
        assert existing.error_message == "boom"
        assert existing.retry_count == 2
        assert existing.next_retry_at == next_retry

    @pytest.mark.asyncio
    async def test_creates_new_log_when_none(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        next_retry = datetime(2026, 1, 1, 13, 0, 0)
        await logger.log_retrying(_event(), "email", _result(success=False), 2, next_retry, mock_async_session)

        mock_async_session.add.assert_called_once()
        added = mock_async_session.add.call_args[0][0]
        assert added.status == "retrying"
        assert added.retry_count == 2

    @pytest.mark.asyncio
    async def test_uses_factory_when_no_db(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger()
        next_retry = datetime(2026, 1, 2, 0, 0)
        with _patch_factory(mock_async_session):
            await logger.log_retrying(_event(), "email", _result(success=False), 2, next_retry, None)
        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_called_once()
        assert mock_async_session.add.call_args[0][0].status == "retrying"


class TestLogFailed:
    @pytest.mark.asyncio
    async def test_updates_existing_log(self, mock_async_session):
        existing = NotificationLog(
            event_id="evt1", channel_name="email", event_type="terminal.blocked", status="retrying"
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        await logger.log_failed(_event(), "email", _result(success=False), 3, mock_async_session)

        mock_async_session.add.assert_not_called()
        assert existing.status == "failed"
        assert existing.retry_count == 3
        assert existing.next_retry_at is None

    @pytest.mark.asyncio
    async def test_creates_new_log_when_none(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger(mock_async_session)
        await logger.log_failed(_event(), "email", _result(success=False), 3, mock_async_session)

        mock_async_session.add.assert_called_once()
        added = mock_async_session.add.call_args[0][0]
        assert added.status == "failed"
        assert added.retry_count == 3

    @pytest.mark.asyncio
    async def test_uses_factory_when_no_db(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute = AsyncMock(return_value=result)

        logger = NotificationLogger()
        with _patch_factory(mock_async_session):
            await logger.log_failed(_event(), "email", _result(success=False), 3, None)
        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_called_once()
        assert mock_async_session.add.call_args[0][0].status == "failed"


class TestLogNotification:
    @pytest.mark.asyncio
    async def test_delegates_to_log_sent_on_success(self):
        logger = NotificationLogger(MagicMock())
        with patch.object(logger, "log_sent", new=AsyncMock()) as m_sent, \
             patch.object(logger, "log_failed", new=AsyncMock()) as m_failed:
            await logger.log_notification(_event(), "email", _result(success=True), None)
        m_sent.assert_awaited_once()
        m_failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delegates_to_log_failed_on_failure(self):
        logger = NotificationLogger(MagicMock())
        with patch.object(logger, "log_sent", new=AsyncMock()) as m_sent, \
             patch.object(logger, "log_failed", new=AsyncMock()) as m_failed:
            await logger.log_notification(_event(), "email", _result(success=False), None)
        m_failed.assert_awaited_once()
        m_sent.assert_not_awaited()


class TestGetNotificationLogs:
    @pytest.mark.asyncio
    async def test_returns_logs_and_total(self, mock_async_session):
        log1 = NotificationLog(event_id="e1", channel_name="email", event_type="x", status="sent")
        log2 = NotificationLog(event_id="e2", channel_name="email", event_type="x", status="sent")
        count_res = MagicMock()
        count_res.scalar.return_value = 2
        res = MagicMock()
        res.scalars.return_value.all.return_value = [log1, log2]
        mock_async_session.execute = AsyncMock(side_effect=[count_res, res])

        logger = NotificationLogger(mock_async_session)
        logs, total = await logger.get_notification_logs(
            mock_async_session, channel_name="email", event_type="x", status="sent"
        )

        assert total == 2
        assert logs == [log1, log2]

    @pytest.mark.asyncio
    async def test_archived_none_skips_filter(self, mock_async_session):
        count_res = MagicMock()
        count_res.scalar.return_value = 0
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        mock_async_session.execute = AsyncMock(side_effect=[count_res, res])

        logger = NotificationLogger(mock_async_session)
        logs, total = await logger.get_notification_logs(mock_async_session, archived=None)

        assert total == 0
        assert logs == []


class TestExceptionSwallowing:
    @pytest.mark.asyncio
    async def test_log_suppressed_swallows_commit_error(self, mock_async_session):
        mock_async_session.commit = AsyncMock(side_effect=Exception("boom"))
        logger = NotificationLogger(mock_async_session)
        await logger.log_suppressed(_event(), "email", 300, mock_async_session)  # no raise

    @pytest.mark.asyncio
    async def test_log_sent_swallows_commit_error(self, mock_async_session):
        mock_async_session.commit = AsyncMock(side_effect=Exception("boom"))
        logger = NotificationLogger(mock_async_session)
        await logger.log_sent(_event(), "email", _result(True), mock_async_session)  # no raise

    @pytest.mark.asyncio
    async def test_log_retrying_swallows_commit_error(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute = AsyncMock(return_value=result)
        mock_async_session.commit = AsyncMock(side_effect=Exception("boom"))
        logger = NotificationLogger(mock_async_session)
        await logger.log_retrying(
            _event(), "email", _result(False), 1, datetime(2026, 1, 2, 0, 0), mock_async_session
        )  # no raise

    @pytest.mark.asyncio
    async def test_log_failed_swallows_commit_error(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute = AsyncMock(return_value=result)
        mock_async_session.commit = AsyncMock(side_effect=Exception("boom"))
        logger = NotificationLogger(mock_async_session)
        await logger.log_failed(_event(), "email", _result(False), 1, mock_async_session)  # no raise