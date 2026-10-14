"""Unit tests for the email notification channel.

Covers ``app/services/notification_channels/email_channel.py``: the shared
HTTP client factory, the ``EmailService`` compatibility wrapper, recipient
parsing, HTML/text content formatting, and the full ``send``/``test`` logic
(legacy SMTP relay path and database-backed global config path). All HTTP and
SMTP boundaries are mocked.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.services.notification_channels.email_channel as email_channel
from app.services.notification_channels.base import (
    ChannelTestResult,
    NotificationEvent,
    NotificationResult,
)
from app.services.notification_channels.email_channel import (
    EmailChannel,
    EmailService,
    _get_email_http_client,
)


def _event(event_type="terminal.blocked", severity="info", data=None, **kwargs):
    return NotificationEvent(
        id="evt-1",
        type=event_type,
        timestamp=kwargs.pop("timestamp", datetime(2026, 1, 1, 12, 0, 0)),
        data=data if data is not None else {},
        severity=severity,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _reset_client():
    email_channel._email_http_client = None
    yield
    email_channel._email_http_client = None


# ===========================================================================
# HTTP client factory
# ===========================================================================

class TestGetEmailHttpClient:
    def test_creates_when_none(self):
        email_channel._email_http_client = None
        with patch.object(email_channel.httpx, "AsyncClient") as mc:
            mc.return_value = sentinel = MagicMock()
            sentinel.is_closed = False
            client = _get_email_http_client()
        assert client is sentinel
        assert email_channel._email_http_client is sentinel

    def test_creates_when_closed(self):
        email_channel._email_http_client = MagicMock()
        email_channel._email_http_client.is_closed = True
        with patch.object(email_channel.httpx, "AsyncClient") as mc:
            mc.return_value = sentinel = MagicMock()
            sentinel.is_closed = False
            client = _get_email_http_client()
        assert client is sentinel

    def test_reuses_open_client(self):
        existing = MagicMock()
        existing.is_closed = False
        email_channel._email_http_client = existing
        assert _get_email_http_client() is existing


# ===========================================================================
# EmailService wrapper
# ===========================================================================

class TestEmailService:
    @pytest.mark.asyncio
    async def test_send_email(self):
        assert await EmailService().send_email("a@b.c", "s", "b") == {"success": True}

    @pytest.mark.asyncio
    async def test_send(self):
        assert await EmailService().send("a@b.c", "s", "b") is True


# ===========================================================================
# Recipient parsing
# ===========================================================================

class TestGetRecipients:
    def test_list_passthrough(self):
        ch = EmailChannel({"recipients": ["a@b.c", "d@e.f"]})
        assert ch.get_recipients() == ["a@b.c", "d@e.f"]

    def test_string_comma_split(self):
        ch = EmailChannel({"recipients": "a@b.c, d@e.f"})
        assert ch.get_recipients() == ["a@b.c", "d@e.f"]

    def test_string_newline_split(self):
        ch = EmailChannel({"recipients": "a@b.c\nd@e.f"})
        assert ch.get_recipients() == ["a@b.c", "d@e.f"]

    def test_filters_empties(self):
        ch = EmailChannel({"recipients": "a@b.c, , d@e.f,"})
        assert ch.get_recipients() == ["a@b.c", "d@e.f"]

    def test_missing_returns_empty(self):
        assert EmailChannel({}).get_recipients() == []


# ===========================================================================
# Content formatting
# ===========================================================================

class TestFormatEmailContent:
    def test_known_event_uses_name_and_description(self):
        ch = EmailChannel({})
        subject, body = ch.format_email_content(_event())
        assert subject == "[TAM] 终端被封锁"
        assert "终端被封锁" in body
        assert "终端已被添加到黑名单" in body

    def test_unknown_event_uses_type(self):
        ch = EmailChannel({})
        subject, body = ch.format_email_content(_event(event_type="custom.thing", data={}))
        assert subject == "[TAM] custom.thing"
        assert "custom.thing" in body

    def test_severity_error_colour(self):
        ch = EmailChannel({})
        _, body = ch.format_email_content(_event(severity="error"))
        assert "#dc2626" in body

    def test_severity_warning_colour(self):
        ch = EmailChannel({})
        _, body = ch.format_email_content(_event(severity="warning"))
        assert "#f59e0b" in body

    def test_severity_info_colour(self):
        ch = EmailChannel({})
        _, body = ch.format_email_content(_event(severity="info"))
        assert "#10b981" in body

    def test_data_renders_details(self):
        ch = EmailChannel({})
        subject, body = ch.format_email_content(_event(data={"ip": "1.2.3.4"}))
        assert "<h3>详细信息</h3>" in body
        assert "ip" in body
        assert "1.2.3.4" in body

    def test_no_data_no_details_heading(self):
        ch = EmailChannel({})
        _, body = ch.format_email_content(_event(data={}))
        assert "<h3>详细信息</h3>" not in body


# ===========================================================================
# send()
# ===========================================================================

class TestSend:
    @pytest.mark.asyncio
    async def test_no_event_and_no_content_raises(self):
        ch = EmailChannel({"recipients": ["a@b.c"]})
        with pytest.raises(ValueError):
            await ch.send()

    @pytest.mark.asyncio
    async def test_no_recipients_returns_error(self):
        ch = EmailChannel({})
        result = await ch.send(event=_event())
        assert result.success is False
        assert result.message == "No recipients configured"

    @pytest.mark.asyncio
    async def test_recipients_override(self):
        ch = EmailChannel({"recipients": ["a@b.c"], "smtp_url": "http://x"})
        with patch.object(email_channel, "_get_email_http_client") as gc:
            client = AsyncMock()
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            client.post = AsyncMock(return_value=resp)
            gc.return_value = client
            result = await ch.send(subject="s", message="m", recipients=["new@b.c"])
        assert result.success is True
        # recipients override was applied before "to" was built
        assert "new@b.c" in str(client.post.await_args)

    @pytest.mark.asyncio
    async def test_subject_message_legacy_success(self):
        ch = EmailChannel({"recipients": "a@b.c", "smtp_url": "http://x"})
        with patch.object(email_channel, "_get_email_http_client") as gc:
            client = AsyncMock()
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            client.post = AsyncMock(return_value=resp)
            gc.return_value = client
            result = await ch.send(subject="Hello", message="World")
        assert result.success is True
        assert result.channel == "email"
        assert result.recipient == "a@b.c"
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_event_legacy_success(self):
        ch = EmailChannel({"recipients": "a@b.c", "smtp_url": "http://x"})
        with patch.object(email_channel, "_get_email_http_client") as gc:
            client = AsyncMock()
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            client.post = AsyncMock(return_value=resp)
            gc.return_value = client
            result = await ch.send(event=_event())
        assert result.success is True
        assert result.event_id == "evt-1"

    @pytest.mark.asyncio
    async def test_legacy_http_error(self):
        ch = EmailChannel({"recipients": "a@b.c", "smtp_url": "http://x"})
        resp = MagicMock()
        resp.status_code = 500
        ex = httpx.HTTPStatusError("err", request=MagicMock(), response=resp)
        with patch.object(email_channel, "_get_email_http_client") as gc:
            client = AsyncMock()
            client.post = AsyncMock(side_effect=ex)
            gc.return_value = client
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "HTTP_ERROR"
        assert "500" in result.message

    @pytest.mark.asyncio
    async def test_legacy_generic_error(self):
        ch = EmailChannel({"recipients": "a@b.c", "smtp_url": "http://x"})
        with patch.object(email_channel, "_get_email_http_client") as gc:
            client = AsyncMock()
            client.post = AsyncMock(side_effect=RuntimeError("boom"))
            gc.return_value = client
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "SEND_ERROR"
        assert "boom" in result.message

    @pytest.mark.asyncio
    async def test_global_config_success(self):
        ch = EmailChannel({"recipients": "a@b.c"})
        with patch("app.services.email_service.send_email", new=AsyncMock(return_value=True)):
            result = await ch.send(event=_event())
        assert result.success is True
        assert "1/1" in result.message

    @pytest.mark.asyncio
    async def test_global_config_partial_success(self):
        ch = EmailChannel({"recipients": "a@b.c,d@e.f"})

        async def _send(to_email, **kwargs):
            if to_email == "a@b.c":
                return True
            raise RuntimeError("fail")

        with patch("app.services.email_service.send_email", side_effect=_send):
            result = await ch.send(event=_event())
        assert result.success is True
        assert "1/2" in result.message

    @pytest.mark.asyncio
    async def test_global_config_all_fail_generic(self):
        ch = EmailChannel({"recipients": "a@b.c"})
        with patch("app.services.email_service.send_email", side_effect=RuntimeError("boom")):
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "SEND_ERROR"

    @pytest.mark.asyncio
    async def test_global_config_all_fail_auth(self):
        ch = EmailChannel({"recipients": "a@b.c"})
        with patch("app.services.email_service.send_email", side_effect=RuntimeError("AUTH_ERROR: bad creds")):
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_global_config_outer_exception(self):
        # An iterable that explodes on iteration raises outside the per-recipient
        # try/except, exercising the outer exception handler.
        class _ExplodingIterable:
            def __iter__(self):
                raise RuntimeError("iterator boom")

        ch = EmailChannel({"recipients": "a@b.c"})
        ch.get_recipients = MagicMock(return_value=_ExplodingIterable())
        result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "SEND_ERROR"


# ===========================================================================
# test()
# ===========================================================================

class TestTest:
    @pytest.mark.asyncio
    async def test_legacy_success(self):
        ch = EmailChannel({"smtp_url": "http://x"})
        with patch.object(email_channel.httpx, "AsyncClient") as mc:
            inner = AsyncMock()
            mc.return_value.__aenter__ = AsyncMock(return_value=inner)
            mc.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = MagicMock()
            resp.status_code = 200
            inner.get = AsyncMock(return_value=resp)
            result = await ch.test()
        assert result.success is True
        assert "legacy relay" in result.message

    @pytest.mark.asyncio
    async def test_legacy_server_error(self):
        ch = EmailChannel({"smtp_url": "http://x"})
        with patch.object(email_channel.httpx, "AsyncClient") as mc:
            inner = AsyncMock()
            mc.return_value.__aenter__ = AsyncMock(return_value=inner)
            mc.return_value.__aexit__ = AsyncMock(return_value=False)
            resp = MagicMock()
            resp.status_code = 500
            inner.get = AsyncMock(return_value=resp)
            result = await ch.test()
        assert result.success is False
        assert "500" in result.message

    @pytest.mark.asyncio
    async def test_legacy_connection_error(self):
        ch = EmailChannel({"smtp_url": "http://x"})
        with patch.object(email_channel.httpx, "AsyncClient") as mc:
            inner = AsyncMock()
            mc.return_value.__aenter__ = AsyncMock(return_value=inner)
            mc.return_value.__aexit__ = AsyncMock(return_value=False)
            inner.get = AsyncMock(side_effect=httpx.ConnectError("conn"))
            result = await ch.test()
        assert result.success is False
        assert "Connection failed" in result.message

    @pytest.mark.asyncio
    async def test_global_config_success(self):
        ch = EmailChannel({})
        with patch("app.services.email_service.get_email_config", new=AsyncMock(
            return_value={"enabled": True, "host": "smtp.x", "port": 465}
        )):
            result = await ch.test()
        assert result.success is True
        assert "smtp.x:465" in result.message

    @pytest.mark.asyncio
    async def test_global_config_disabled(self):
        ch = EmailChannel({})
        with patch("app.services.email_service.get_email_config", new=AsyncMock(
            return_value={"enabled": False, "host": "smtp.x", "port": 465}
        )):
            result = await ch.test()
        assert result.success is False
        assert "disabled" in result.message

    @pytest.mark.asyncio
    async def test_global_config_no_host(self):
        ch = EmailChannel({})
        with patch("app.services.email_service.get_email_config", new=AsyncMock(
            return_value={"enabled": True, "host": "", "port": 465}
        )):
            result = await ch.test()
        assert result.success is False
        assert "host" in result.message

    @pytest.mark.asyncio
    async def test_global_config_exception(self):
        ch = EmailChannel({})
        with patch("app.services.email_service.get_email_config", new=AsyncMock(
            side_effect=RuntimeError("boom")
        )):
            result = await ch.test()
        assert result.success is False
        assert "Failed to read email config" in result.message