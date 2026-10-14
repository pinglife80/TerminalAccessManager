"""Unit tests for the email service (app/services/email_service.py).

Redis is mocked via conftest's autouse ``get_redis_client`` patch (in-memory
dict). ``get_email_config`` reads DB-backed config via
``config_service.get_config_value``, which is patched directly for the config
tests. SMTP/HTTP paths are exercised with httpx / smtplib mocks so no real
network I/O occurs.
"""

import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.services import email_service
from app.services.email_service import (
    EmailRateLimitError,
    EmailSendError,
    EmailSender,
    check_email_rate_limit,
    generate_email_code,
    get_email_config,
    invalidate_email_codes,
    render_template,
    send_2fa_email,
    send_email,
    send_email_code,
    send_password_reset_email,
    send_verification_email,
    verify_email_code,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_config(overrides):
    """Patch config_service.get_config_value to return per-key values."""

    async def _ctx(key, default=None):
        return overrides.get(key, default)

    return patch("app.services.config_service.get_config_value", side_effect=_ctx)


def _http_client(**kwargs):
    """Build a mock httpx.AsyncClient usable in ``async with``."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = kwargs.get("post", AsyncMock(return_value=MagicMock()))
    client.get = kwargs.get("get", AsyncMock(return_value=MagicMock()))
    return client


# ===========================================================================
# generate_email_code
# ===========================================================================

class TestGenerateEmailCode:
    @pytest.mark.asyncio
    async def test_default_length_is_six_digits(self):
        code = await generate_email_code()
        assert len(code) == 6
        assert code.isdigit()

    @pytest.mark.asyncio
    async def test_custom_length(self):
        code = await generate_email_code(length=4)
        assert len(code) == 4
        assert code.isdigit()


# ===========================================================================
# send_email_code
# ===========================================================================

class TestSendEmailCode:
    @pytest.mark.asyncio
    async def test_success_stores_and_sends(self, mock_redis):
        with patch.object(email_service, "generate_email_code", AsyncMock(return_value="123456")), \
             patch.object(email_service, "send_email", AsyncMock(return_value=True)) as mock_send:
            code = await send_email_code(
                1, "user@example.com", purpose="password_reset", ttl_seconds=300
            )

        assert code == "123456"
        assert mock_redis._data["email_code:password_reset:1"] == "123456"
        mock_send.assert_awaited_once()
        kwargs = mock_send.call_args.kwargs
        assert kwargs["to_email"] == "user@example.com"
        assert kwargs["template_name"] == "password_reset.html"
        assert kwargs["template_data"]["code"] == "123456"
        assert kwargs["template_data"]["ttl_minutes"] == 5

    @pytest.mark.asyncio
    async def test_unknown_purpose_falls_back_to_notification_template(self):
        with patch.object(email_service, "generate_email_code", AsyncMock(return_value="000000")), \
             patch.object(email_service, "send_email", AsyncMock(return_value=True)) as mock_send:
            await send_email_code(1, "user@example.com", purpose="weird")

        assert mock_send.call_args.kwargs["template_name"] == "notification.html"

    @pytest.mark.asyncio
    async def test_send_failure_is_re_raised(self, mock_redis):
        with patch.object(email_service, "generate_email_code", AsyncMock(return_value="123456")), \
             patch.object(email_service, "send_email", AsyncMock(side_effect=RuntimeError("send fail"))):
            with pytest.raises(RuntimeError):
                await send_email_code(1, "user@example.com")

        # Code is still stored before the send attempt.
        assert mock_redis._data["email_code:verification:1"] == "123456"


# ===========================================================================
# verify_email_code
# ===========================================================================

class TestVerifyEmailCode:
    @pytest.mark.asyncio
    async def test_valid_code_deletes_on_success(self, mock_redis):
        mock_redis._data["email_code:verification:1"] = "123456"
        assert await verify_email_code(1, "123456") is True
        assert "email_code:verification:1" not in mock_redis._data

    @pytest.mark.asyncio
    async def test_valid_code_keeps_when_delete_disabled(self, mock_redis):
        mock_redis._data["email_code:verification:1"] = "123456"
        assert await verify_email_code(1, "123456", delete_on_success=False) is True
        assert mock_redis._data["email_code:verification:1"] == "123456"

    @pytest.mark.asyncio
    async def test_missing_code_returns_false(self, mock_redis):
        assert await verify_email_code(1, "123456") is False

    @pytest.mark.asyncio
    async def test_invalid_code_increments_attempts(self, mock_redis):
        mock_redis._data["email_code:verification:1"] = "111111"
        assert await verify_email_code(1, "222222") is False
        assert mock_redis._data["email_code:verification:1:attempts"] == 1
        # Code still present (not deleted on failure).
        assert mock_redis._data["email_code:verification:1"] == "111111"

    @pytest.mark.asyncio
    async def test_max_attempts_invalidates_code(self, mock_redis):
        mock_redis._data["email_code:verification:1"] = "111111"
        mock_redis._data["email_code:verification:1:attempts"] = "5"
        assert await verify_email_code(1, "222222") is False
        assert "email_code:verification:1" not in mock_redis._data
        assert "email_code:verification:1:attempts" not in mock_redis._data

    @pytest.mark.asyncio
    async def test_custom_max_attempts_boundary(self, mock_redis):
        mock_redis._data["email_code:verification:1"] = "111111"
        # attempts (2) < max_attempts (3) -> still checks against code.
        mock_redis._data["email_code:verification:1:attempts"] = "2"
        assert await verify_email_code(1, "wrong", max_attempts=3) is False
        assert mock_redis._data["email_code:verification:1:attempts"] == 3


# ===========================================================================
# invalidate_email_codes
# ===========================================================================

class TestInvalidateEmailCodes:
    @pytest.mark.asyncio
    async def test_specific_purpose(self, mock_redis):
        mock_redis._data["email_code:verification:1"] = "1"
        mock_redis._data["email_code:verification:1:attempts"] = "1"
        mock_redis._data["email_code:password_reset:1"] = "2"
        await invalidate_email_codes(1, purpose="verification")

        assert "email_code:verification:1" not in mock_redis._data
        assert "email_code:verification:1:attempts" not in mock_redis._data
        assert "email_code:password_reset:1" in mock_redis._data

    @pytest.mark.asyncio
    async def test_all_purposes(self, mock_redis):
        for p in ["verification", "password_reset", "2fa", "email_change"]:
            mock_redis._data[f"email_code:{p}:1"] = "1"
            mock_redis._data[f"email_code:{p}:1:attempts"] = "1"

        await invalidate_email_codes(1)

        for p in ["verification", "password_reset", "2fa", "email_change"]:
            assert f"email_code:{p}:1" not in mock_redis._data
            assert f"email_code:{p}:1:attempts" not in mock_redis._data


# ===========================================================================
# get_email_config
# ===========================================================================

class TestGetEmailConfig:
    @pytest.mark.asyncio
    async def test_defaults_from_env(self):
        with _patch_config({}):
            config = await get_email_config()

        assert config["host"] == "" or config["host"] == settings.EMAIL_HOST
        assert config["port"] == 465
        assert config["use_tls"] is False
        assert config["use_ssl"] is True
        assert config["from_name"] == "TAM System"
        assert config["rate_limit"] == settings.EMAIL_RATE_LIMIT_PER_MINUTE
        assert config["enabled"] is False

    @pytest.mark.asyncio
    async def test_db_values_override(self):
        values = {
            "email_host": "smtp.gmail.com",
            "email_port": 587,
            "email_use_tls": True,
            "email_use_ssl": False,
            "email_username": "u",
            "email_password": "p",
            "email_from": "f@x.com",
            "email_from_name": "Name",
            "email_rate_limit": 20,
            "email_enabled": True,
        }
        with _patch_config(values):
            config = await get_email_config()

        assert config["host"] == "smtp.gmail.com"
        assert config["port"] == 587
        assert config["use_tls"] is True
        assert config["use_ssl"] is False
        assert config["username"] == "u"
        assert config["password"] == "p"
        assert config["from_email"] == "f@x.com"
        assert config["from_name"] == "Name"
        assert config["rate_limit"] == 20
        assert config["enabled"] is True

    @pytest.mark.asyncio
    async def test_host_configured_forces_enabled_even_if_disabled(self):
        values = {"email_host": "smtp.real.com", "email_enabled": False}
        with _patch_config(values):
            config = await get_email_config()
        assert config["enabled"] is True

    @pytest.mark.asyncio
    async def test_default_host_does_not_force_enabled(self):
        values = {"email_host": "smtp.example.com", "email_enabled": False}
        with _patch_config(values):
            config = await get_email_config()
        assert config["enabled"] is False

    @pytest.mark.asyncio
    async def test_port_falls_back_to_env_when_zero(self):
        values = {"email_port": 0}
        with _patch_config(values):
            config = await get_email_config()
        assert config["port"] == settings.EMAIL_PORT


# ===========================================================================
# check_email_rate_limit
# ===========================================================================

class TestCheckEmailRateLimit:
    @pytest.mark.asyncio
    async def test_first_request_allowed(self, mock_redis):
        allowed, remaining = await check_email_rate_limit("a@b.com", rate_limit=10)
        assert allowed is True
        assert remaining == 9
        assert mock_redis._data["email_rate:a@b.com"] == 1

    @pytest.mark.asyncio
    async def test_under_limit_increments(self, mock_redis):
        mock_redis._data["email_rate:a@b.com"] = "3"
        allowed, remaining = await check_email_rate_limit("a@b.com", rate_limit=10)
        assert allowed is True
        assert remaining == 6
        assert mock_redis._data["email_rate:a@b.com"] == "4"

    @pytest.mark.asyncio
    async def test_at_limit_denied(self, mock_redis):
        mock_redis._data["email_rate:a@b.com"] = "10"
        allowed, remaining = await check_email_rate_limit("a@b.com", rate_limit=10)
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_over_limit_denied(self, mock_redis):
        mock_redis._data["email_rate:a@b.com"] = "11"
        allowed, remaining = await check_email_rate_limit("a@b.com", rate_limit=10)
        assert allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_none_rate_limit_falls_back_to_settings(self, mock_redis):
        allowed, _ = await check_email_rate_limit("a@b.com")
        assert allowed is True
        # First request returns rate_limit - 1 using settings default.
        assert mock_redis._data["email_rate:a@b.com"] == 1


# ===========================================================================
# EmailSender.__init__ / _build_message
# ===========================================================================

class TestEmailSenderInit:
    def test_explicit_values_override_settings(self):
        sender = EmailSender(
            host="h", port=587, username="u", password="p",
            use_tls=True, use_ssl=False, from_email="f@x.com", from_name="F",
        )
        assert sender.host == "h"
        assert sender.port == 587
        assert sender.username == "u"
        assert sender.password == "p"
        assert sender.use_tls is True
        assert sender.use_ssl is False
        assert sender.from_email == "f@x.com"
        assert sender.from_name == "F"

    def test_defaults_from_settings(self):
        sender = EmailSender()
        assert sender.host == "smtp.example.com"
        assert sender.port == 465
        assert sender.use_ssl is True
        assert sender.from_email == "noreply@example.com"
        assert sender.from_name == "TAM System"


class TestBuildMessage:
    def test_from_header_and_text_fallback(self):
        sender = EmailSender(host="h", from_email="f@x.com", from_name="Name")
        msg = sender._build_message("to@x.com", "subj", html_content="<p>h</p>")
        assert msg["from"] == "Name <f@x.com>"
        assert msg["to"] == "to@x.com"
        assert msg["subject"] == "subj"
        assert msg["html"] == "<p>h</p>"
        assert msg["text"] == "<p>h</p>"

    def test_explicit_text_wins(self):
        sender = EmailSender(host="h")
        msg = sender._build_message("to@x.com", "subj", html_content="<p>h</p>", text_content="plain")
        assert msg["text"] == "plain"

    def test_no_content_has_empty_text(self):
        sender = EmailSender(host="h")
        msg = sender._build_message("to@x.com", "subj")
        assert msg["text"] == ""


# ===========================================================================
# EmailSender.send
# ===========================================================================

class TestEmailSenderSend:
    def _sender(self):
        return EmailSender(
            host="smtp.test.com", port=587, username="u", password="p",
            use_tls=True, use_ssl=False, from_email="f@t.com", from_name="F",
        )

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises(self):
        sender = self._sender()
        with patch.object(email_service, "check_email_rate_limit", AsyncMock(return_value=(False, 0))):
            with pytest.raises(EmailRateLimitError):
                await sender.send("x@y.com", "subject")

    @pytest.mark.asyncio
    async def test_send_via_http_relay(self):
        sender = self._sender()
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        client = _http_client(post=AsyncMock(return_value=resp))

        with patch.object(settings, "EMAIL_SMTP_URL", "http://relay.example.com/send"), \
             patch.object(email_service.httpx, "AsyncClient", return_value=client):
            result = await sender.send("x@y.com", "hi", html_content="<p>x</p>")

        assert result is True
        client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_via_direct_smtp_when_no_relay(self):
        sender = self._sender()
        with patch.object(settings, "EMAIL_SMTP_URL", None), \
             patch.object(sender, "_send_via_smtp", AsyncMock(return_value=None)) as mock_smtp:
            result = await sender.send("x@y.com", "hi", html_content="<p>x</p>")

        assert result is True
        mock_smtp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_http_status_error_wrapped(self):
        sender = self._sender()
        req = MagicMock()
        resp = MagicMock()
        resp.status_code = 500
        err = httpx.HTTPStatusError("err", request=req, response=resp)
        client = _http_client(post=AsyncMock(side_effect=err))

        with patch.object(settings, "EMAIL_SMTP_URL", "http://relay.example.com/send"), \
             patch.object(email_service.httpx, "AsyncClient", return_value=client):
            with pytest.raises(EmailSendError) as ei:
                await sender.send("x@y.com", "hi")

        assert "HTTP 500" in str(ei.value)

    @pytest.mark.asyncio
    async def test_smtp_auth_error_wrapped(self):
        sender = self._sender()
        with patch.object(settings, "EMAIL_SMTP_URL", None), \
             patch.object(sender, "_send_via_smtp",
                          AsyncMock(side_effect=smtplib.SMTPAuthenticationError(535, b"auth failed"))):
            with pytest.raises(EmailSendError) as ei:
                await sender.send("x@y.com", "hi")

        assert "AUTH_ERROR" in str(ei.value)

    @pytest.mark.asyncio
    async def test_generic_error_wrapped(self):
        sender = self._sender()
        with patch.object(settings, "EMAIL_SMTP_URL", None), \
             patch.object(sender, "_send_via_smtp", AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(EmailSendError) as ei:
                await sender.send("x@y.com", "hi")

        assert "boom" in str(ei.value)


# ===========================================================================
# EmailSender._send_via_smtp
# ===========================================================================

class TestSendViaSmtp:
    async def _run(self, sender, to_email="to@x.com", subject="subj",
                   html_content="<p>h</p>", text_content=None):
        async def fake_to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with patch("asyncio.to_thread", new=fake_to_thread):
            await sender._send_via_smtp(to_email, subject, html_content, text_content)

    @pytest.mark.asyncio
    async def test_ssl_with_username_and_password(self):
        sender = EmailSender(host="h", port=465, username="u", password="p", use_ssl=True)
        mock_ssl = MagicMock()
        server = MagicMock()
        mock_ssl.return_value.__enter__.return_value = server
        mock_ssl.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP_SSL", mock_ssl):
            await self._run(sender)

        mock_ssl.assert_called_once_with("h", 465, timeout=30)
        server.login.assert_called_once_with("u", "p")
        server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_tls_starttls_called(self):
        sender = EmailSender(host="h", port=587, username="u", password="p", use_ssl=False)
        mock_smtp = MagicMock()
        server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = server
        mock_smtp.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP", mock_smtp):
            await self._run(sender)

        server.starttls.assert_called_once()
        server.login.assert_called_once_with("u", "p")

    @pytest.mark.asyncio
    async def test_username_with_empty_password(self):
        sender = EmailSender(host="h", port=465, username="u", password="", use_ssl=True)
        mock_ssl = MagicMock()
        server = MagicMock()
        mock_ssl.return_value.__enter__.return_value = server
        mock_ssl.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP_SSL", mock_ssl):
            await self._run(sender)

        server.login.assert_called_once_with("u", "")

    @pytest.mark.asyncio
    async def test_tls_username_with_empty_password(self):
        sender = EmailSender(host="h", port=587, username="u", password="", use_ssl=False)
        mock_smtp = MagicMock()
        server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = server
        mock_smtp.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP", mock_smtp):
            await self._run(sender)

        server.login.assert_called_once_with("u", "")

    @pytest.mark.asyncio
    async def test_text_content_is_attached(self):
        sender = EmailSender(host="h", port=465, use_ssl=True)
        mock_ssl = MagicMock()
        server = MagicMock()
        mock_ssl.return_value.__enter__.return_value = server
        mock_ssl.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP_SSL", mock_ssl):
            await self._run(sender, html_content="<p>h</p>", text_content="plain text")

        server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_username_skips_login(self):
        sender = EmailSender(host="h", port=465, use_ssl=True)
        mock_ssl = MagicMock()
        server = MagicMock()
        mock_ssl.return_value.__enter__.return_value = server
        mock_ssl.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP_SSL", mock_ssl):
            await self._run(sender)

        server.login.assert_not_called()
        server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_tls_no_username_skips_login(self):
        sender = EmailSender(host="h", port=587, username="", password="", use_ssl=False)
        mock_smtp = MagicMock()
        server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = server
        mock_smtp.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP", mock_smtp):
            await self._run(sender)

        server.starttls.assert_called_once()
        server.login.assert_not_called()
        server.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_html_no_text_uses_subject(self):
        sender = EmailSender(host="h", port=465, use_ssl=True)
        mock_ssl = MagicMock()
        server = MagicMock()
        mock_ssl.return_value.__enter__.return_value = server
        mock_ssl.return_value.__exit__.return_value = False

        with patch.object(email_service.smtplib, "SMTP_SSL", mock_ssl):
            await self._run(sender, html_content=None, text_content=None)

        server.send_message.assert_called_once()


# ===========================================================================
# EmailSender.test_connection
# ===========================================================================

class TestConnection:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        sender = EmailSender(host="smtp.example.com")
        result = await sender.test_connection()
        assert result["success"] is False
        assert "not configured" in result["message"]

    @pytest.mark.asyncio
    async def test_ssl_uses_https(self):
        sender = EmailSender(host="smtp.real.com", port=465, use_ssl=True)
        client = _http_client()
        with patch.object(email_service.httpx, "AsyncClient", return_value=client):
            result = await sender.test_connection()
        assert result["success"] is True
        client.get.assert_awaited_once_with("https://smtp.real.com:465")

    @pytest.mark.asyncio
    async def test_non_ssl_uses_http(self):
        sender = EmailSender(host="smtp.real.com", port=587, use_ssl=False)
        client = _http_client()
        with patch.object(email_service.httpx, "AsyncClient", return_value=client):
            result = await sender.test_connection()
        client.get.assert_awaited_once_with("http://smtp.real.com:587")

    @pytest.mark.asyncio
    async def test_connection_error_returns_failure(self):
        sender = EmailSender(host="smtp.real.com", port=465, use_ssl=True)
        client = _http_client(get=AsyncMock(side_effect=RuntimeError("conn reset")))
        with patch.object(email_service.httpx, "AsyncClient", return_value=client):
            result = await sender.test_connection()
        assert result["success"] is False
        assert "conn reset" in result["message"]


# ===========================================================================
# render_template / _fallback_template / _html_to_text
# ===========================================================================

class TestRenderTemplate:
    @pytest.mark.asyncio
    async def test_renders_template_and_converts_to_text(self):
        template = MagicMock()
        template.render_async = AsyncMock(return_value="<p>hello world</p>")
        env = MagicMock()
        env.get_template.return_value = template

        with patch.object(email_service, "get_jinja_env", return_value=env):
            html, text = await render_template("email_verify.html", {"code": "123"})

        assert html == "<p>hello world</p>"
        assert text == "hello world"
        template.render_async.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_template_uses_fallback(self):
        env = MagicMock()
        env.get_template.side_effect = Exception("not found")
        with patch.object(email_service, "get_jinja_env", return_value=env):
            html, text = await render_template("missing.html", {"code": "654321", "ttl_minutes": 7})

        assert "654321" in html
        assert "654321" in text

    def test_fallback_template_defaults(self):
        html, text = email_service._fallback_template({})
        assert "N/A" in html
        assert "N/A" in text

    def test_html_to_text_strips_tags_and_whitespace(self):
        assert email_service._html_to_text("<p>Hello <b>World</b></p>") == "Hello World"

    def test_html_to_text_decodes_entities(self):
        assert email_service._html_to_text("a &amp; b &lt;tag&gt;") == "a & b <tag>"

    def test_get_jinja_env_caches(self):
        email_service._jinja_env = None
        env1 = email_service.get_jinja_env()
        env2 = email_service.get_jinja_env()
        assert env1 is env2
        assert email_service._jinja_env is env1


# ===========================================================================
# send_email
# ===========================================================================

class TestSendEmail:
    def _config(self):
        return {
            "host": "smtp.test.com",
            "port": 587,
            "use_tls": True,
            "use_ssl": False,
            "username": "u",
            "password": "p",
            "from_email": "f@x.com",
            "from_name": "F",
            "rate_limit": 20,
        }

    @pytest.mark.asyncio
    async def test_with_template(self):
        mock_sender = MagicMock()
        mock_sender.send = AsyncMock(return_value=True)
        with patch.object(email_service, "get_email_config", AsyncMock(return_value=self._config())), \
             patch.object(email_service, "EmailSender", return_value=mock_sender) as mock_ctor, \
             patch.object(email_service, "render_template", AsyncMock(return_value=("<p>h</p>", "text"))) as mock_render:
            result = await send_email(
                "to@x.com", "subj",
                template_name="email_verify.html", template_data={"code": "1"},
            )

        assert result is True
        mock_ctor.assert_called_once_with(
            host="smtp.test.com", port=587, username="u", password="p",
            use_tls=True, use_ssl=False, from_email="f@x.com", from_name="F",
        )
        mock_render.assert_awaited_once_with("email_verify.html", {"code": "1"})
        mock_sender.send.assert_awaited_once_with(
            to_email="to@x.com", subject="subj", html_content="<p>h</p>",
            text_content="text", rate_limit=20,
        )

    @pytest.mark.asyncio
    async def test_without_template_direct_content(self):
        mock_sender = MagicMock()
        mock_sender.send = AsyncMock(return_value=True)
        with patch.object(email_service, "get_email_config", AsyncMock(return_value=self._config())), \
             patch.object(email_service, "EmailSender", return_value=mock_sender), \
             patch.object(email_service, "render_template") as mock_render:
            await send_email("to@x.com", "subj", html_content="<p>h</p>", text_content="t")

        mock_render.assert_not_called()
        mock_sender.send.assert_awaited_once_with(
            to_email="to@x.com", subject="subj", html_content="<p>h</p>",
            text_content="t", rate_limit=20,
        )


# ===========================================================================
# High-level wrapper functions
# ===========================================================================

class TestHighLevelWrappers:
    @pytest.mark.asyncio
    async def test_send_password_reset_email(self):
        with patch.object(email_service, "send_email_code", AsyncMock(return_value="code")) as mock:
            result = await send_password_reset_email("u@x.com", 1)

        assert result == "code"
        kwargs = mock.call_args.kwargs
        assert kwargs["purpose"] == "password_reset"
        assert kwargs["ttl_seconds"] == settings.EMAIL_CODE_EXPIRE_MINUTES * 60

    @pytest.mark.asyncio
    async def test_send_verification_email(self):
        with patch.object(email_service, "send_email_code", AsyncMock(return_value="code")) as mock:
            await send_verification_email("u@x.com", 1)

        kwargs = mock.call_args.kwargs
        assert kwargs["purpose"] == "verification"
        assert kwargs["ttl_seconds"] == settings.EMAIL_CODE_EXPIRE_MINUTES * 60

    @pytest.mark.asyncio
    async def test_send_2fa_email_fixed_ttl(self):
        with patch.object(email_service, "send_email_code", AsyncMock(return_value="code")) as mock:
            await send_2fa_email("u@x.com", 1)

        kwargs = mock.call_args.kwargs
        assert kwargs["purpose"] == "2fa"
        assert kwargs["ttl_seconds"] == 300

    def test_init_email_templates_idempotent(self):
        # Runs at import; calling again must not raise and must be repeatable.
        email_service.init_email_templates()

    def test_init_email_templates_creates_missing_files(self, tmp_path):
        with patch.object(email_service, "_ensure_template_dir", return_value=tmp_path):
            email_service.init_email_templates()

        # Every default template must now exist on disk.
        for name in ["base.html", "email_verify.html", "password_reset.html",
                     "second_factor.html", "email_change.html", "notification.html"]:
            assert (tmp_path / name).exists()