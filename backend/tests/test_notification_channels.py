"""Unit tests for notification channel implementations.

Covers the base interface, the ``get_channel`` factory, and the concrete
webhook / wecom / feishu / dingtalk channels. HTTP and Redis boundaries are
mocked so no network or external service is contacted.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.notification_channels.base import (
    AsyncNotificationChannelBase,
    ChannelTestResult,
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
    format_timestamp,
)
from app.services.notification_channels import (
    DingTalkChannel,
    FeishuChannel,
    NotificationChannelBase as FactoryBase,
    WebhookChannel,
    WeComChannel,
    get_channel,
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


def _http(status_code=200, json_data=None, text="body"):
    """Build an httpx-like response object.

    ``Response.json()`` in httpx is a synchronous method, so it is mocked as a
    plain ``MagicMock`` returning the parsed dict (not an AsyncMock). Channels
    that ``await response.json()`` rely on a ``TypeError`` fallback in the
    production code, which the sync mock correctly exercises.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    else:
        resp.json = MagicMock(side_effect=ValueError("no json"))
    return resp


def _client(mock_client_class, responses):
    """Wire an httpx.AsyncClient mock to return responses in order.

    ``responses`` is a function (verb, url, **kwargs) -> response, or a list
    used round-robin. Returns the inner async client mock.
    """
    inner = AsyncMock()
    mock_client_class.return_value.__aenter__ = AsyncMock(return_value=inner)
    mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

    def _respond(*args, **kwargs):
        if callable(responses):
            return responses(*args, **kwargs)
        return responses.pop(0) if responses else MagicMock()

    inner.post = AsyncMock(side_effect=_respond)
    inner.put = AsyncMock(side_effect=_respond)
    inner.patch = AsyncMock(side_effect=_respond)
    inner.get = AsyncMock(side_effect=_respond)
    inner.head = AsyncMock(side_effect=_respond)
    return inner


# ===========================================================================
# Base dataclasses / helpers
# ===========================================================================

class TestFormatTimestamp:
    def test_naive_assumes_utc(self):
        out = format_timestamp(datetime(2026, 1, 1, 0, 0, 0))
        assert out == "2026-01-01 08:00:00"

    def test_aware_converts_to_shanghai(self):
        from zoneinfo import ZoneInfo
        out = format_timestamp(datetime(2026, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
        assert out == "2026-01-01 08:00:00"


class TestNotificationEvent:
    def test_to_dict(self):
        evt = _event(data={"ip": "1.2.3.4"})
        d = evt.to_dict()
        assert d["id"] == "evt-1"
        assert d["type"] == "terminal.blocked"
        assert d["data"] == {"ip": "1.2.3.4"}


class TestNotificationResult:
    def test_to_dict(self):
        r = NotificationResult(True, "ok", "email", event_id="e", error_code="X")
        d = r.to_dict()
        assert d["success"] is True
        assert d["channel"] == "email"
        assert d["error_code"] == "X"


class _ConcreteChannel(NotificationChannelBase):
    def _validate_config(self):
        pass

    async def send(self, event=None, **kwargs):
        return NotificationResult(True, "ok", self.channel_type)

    async def test(self):
        return ChannelTestResult(True, "ok")


class TestBaseChannel:
    def test_get_recipients_default(self):
        ch = _ConcreteChannel({"recipients": ["a"]})
        assert ch.get_recipients() == ["a"]

    def test_supports_event_default_true(self):
        ch = _ConcreteChannel({})
        assert ch.supports_event("anything") is True

    def test_format_message_with_data(self):
        ch = _ConcreteChannel({})
        msg = ch.format_message(_event(data={"ip": "1.2.3.4"}))
        assert "终端被封锁" in msg
        assert "ip: 1.2.3.4" in msg
        assert "时间:" in msg

    def test_format_message_unknown_event_no_data(self):
        ch = _ConcreteChannel({})
        msg = ch.format_message(_event(event_type="custom.thing", data={}))
        assert "custom.thing" in msg

    def test_format_data(self):
        ch = _ConcreteChannel({})
        d = ch.format_data(_event(data={"x": 1}))
        assert d["event_id"] == "evt-1"
        assert d["event_type"] == "terminal.blocked"
        assert d["data"] == {"x": 1}


class _ConcreteAsyncBase(AsyncNotificationChannelBase):
    """Minimal concrete subclass that does NOT override send()/test()."""

    def _validate_config(self) -> None:
        pass


class TestAsyncBase:
    @pytest.mark.asyncio
    async def test_send_raises_not_implemented(self):
        ch = _ConcreteAsyncBase({})
        with pytest.raises(NotImplementedError):
            await ch.send(_event())

    @pytest.mark.asyncio
    async def test_test_raises_not_implemented(self):
        ch = _ConcreteAsyncBase({})
        with pytest.raises(NotImplementedError):
            await ch.test()


# ===========================================================================
# Factory
# ===========================================================================

class TestGetChannel:
    _VALID_CONFIGS = {
        "email": {},
        "webhook": {"url": "http://x"},
        "feishu": {"webhook_url": "http://x"},
        "dingtalk": {"webhook_url": "http://x"},
        "wecom": {"webhook_url": "http://x"},
    }

    @pytest.mark.parametrize("ctype", ["email", "webhook", "feishu", "dingtalk", "wecom"])
    def test_returns_channel(self, ctype):
        ch = get_channel(ctype, self._VALID_CONFIGS[ctype])
        assert isinstance(ch, FactoryBase)

    def test_case_insensitive(self):
        assert isinstance(get_channel("EMAIL", {}), FactoryBase)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError):
            get_channel("slack", {})


# ===========================================================================
# Webhook channel
# ===========================================================================

class TestWebhookValidate:
    def test_missing_url_raises(self):
        with pytest.raises(ValueError):
            WebhookChannel({})

    def test_url_ok(self):
        assert WebhookChannel({"url": "http://x"}).config["url"] == "http://x"


class TestWebhookSignature:
    def test_no_secret_returns_empty(self):
        ch = WebhookChannel({"url": "http://x"})
        assert ch._generate_signature("payload") == ""

    def test_with_secret(self):
        ch = WebhookChannel({"url": "http://x", "secret": "s3cret"})
        sig = ch._generate_signature("payload")
        assert sig.startswith("sha256=")
        assert len(sig) > len("sha256=")

    def test_prepare_headers_no_secret(self):
        ch = WebhookChannel({"url": "http://x"})
        h = ch._prepare_headers("payload")
        assert "X-TAM-Signature" not in h

    def test_prepare_headers_with_secret_and_custom(self):
        ch = WebhookChannel({"url": "http://x", "secret": "s", "headers": {"X-Custom": "1"}})
        h = ch._prepare_headers("payload")
        assert h["X-TAM-Signature"].startswith("sha256=")
        assert h["X-Custom"] == "1"


class TestWebhookBuildPayload:
    def test_build_payload(self):
        ch = WebhookChannel({"url": "http://x"})
        p = ch._build_payload(_event(data={"ip": "1.2.3.4"}))
        assert p["event_id"] == "evt-1"
        assert p["message"]


class TestWebhookSend:
    @pytest.mark.asyncio
    async def test_subject_message_post_success(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: _http(200))
            result = await ch.send(subject="s", message="m")
        assert result.success is True
        inner.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subject_message_unsupported_method(self):
        ch = WebhookChannel({"url": "http://x", "method": "DELETE"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient"):
            result = await ch.send(subject="s", message="m")
        assert result.success is False
        assert result.message == "Unsupported HTTP method: DELETE"

    @pytest.mark.asyncio
    async def test_subject_message_http_error(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(500))
            result = await ch.send(subject="s", message="m")
        assert result.success is False
        assert result.message == "HTTP 500"

    @pytest.mark.asyncio
    async def test_event_none_raises(self):
        ch = WebhookChannel({"url": "http://x"})
        with pytest.raises(ValueError):
            await ch.send()

    @pytest.mark.asyncio
    async def test_event_post_success(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200))
            result = await ch.send(event=_event())
        assert result.success is True
        assert result.details["status_code"] == 200

    @pytest.mark.asyncio
    async def test_event_http_error(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(404, text="not found"))
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "HTTP_ERROR"

    @pytest.mark.asyncio
    async def test_event_unsupported_method(self):
        ch = WebhookChannel({"url": "http://x", "method": "DELETE"})
        result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "INVALID_METHOD"

    @pytest.mark.asyncio
    async def test_event_timeout(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = httpx.TimeoutException("timeout")
            result = await ch.send(event=_event())
        assert result.error_code == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_event_connect_error(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = httpx.ConnectError("conn")
            result = await ch.send(event=_event())
        assert result.error_code == "CONNECTION_ERROR"

    @pytest.mark.asyncio
    async def test_event_generic_error(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = RuntimeError("boom")
            result = await ch.send(event=_event())
        assert result.error_code == "SEND_ERROR"


class TestWebhookTest:
    @pytest.mark.asyncio
    async def test_head_success(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200))
            result = await ch.test()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_head_fallback_to_post_success(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: _http(200))
            inner.head = AsyncMock(return_value=_http(405))
            result = await ch.test()
        assert result.success is True
        inner.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_post_server_error(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: _http(500))
            inner.head = AsyncMock(return_value=_http(405))
            result = await ch.test()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_timeout(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.head.side_effect = httpx.TimeoutException("timeout")
            result = await ch.test()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_connect_error(self):
        ch = WebhookChannel({"url": "http://x"})
        with patch("app.services.notification_channels.webhook_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.head.side_effect = httpx.ConnectError("conn")
            result = await ch.test()
        assert result.success is False


# ===========================================================================
# WeCom channel
# ===========================================================================

class TestWeComValidate:
    def test_webhook_mode_ok(self):
        assert WeComChannel({"webhook_url": "http://x"})._is_app_mode() is False

    def test_app_mode_ok(self):
        ch = WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a", "touser": "u"})
        assert ch._is_app_mode() is True

    def test_no_config_raises(self):
        with pytest.raises(ValueError):
            WeComChannel({})

    def test_app_mode_requires_target(self):
        with pytest.raises(ValueError):
            WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a"})


class TestWeComToken:
    @pytest.mark.asyncio
    async def test_cached_token(self):
        ch = WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a", "touser": "u"})
        redis = MagicMock()
        redis.get = AsyncMock(return_value="cached-token")
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            assert await ch._get_access_token() == "cached-token"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        ch = WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a", "touser": "u"})
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)), \
             patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0, "access_token": "tok"}))
            assert await ch._get_access_token() == "tok"
        redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_error(self):
        ch = WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a", "touser": "u"})
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)), \
             patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 40001, "errmsg": "bad"}))
            with pytest.raises(RuntimeError):
                await ch._get_access_token()


class TestWeComSend:
    @pytest.mark.asyncio
    async def test_subject_message_webhook_success(self):
        ch = WeComChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(subject="s", message="m")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_webhook_event_success(self):
        ch = WeComChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(event=_event())
        assert result.success is True

    @pytest.mark.asyncio
    async def test_webhook_event_error(self):
        ch = WeComChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 1, "errmsg": "bad"}))
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "1"

    @pytest.mark.asyncio
    async def test_app_event_success(self):
        ch = WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a", "touser": "u"})
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(event=_event())
        assert result.success is True
        assert "users:u" in result.recipient

    @pytest.mark.asyncio
    async def test_app_event_error(self):
        ch = WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a", "touser": "u"})
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 9, "errmsg": "bad"}))
            result = await ch.send(event=_event())
        assert result.success is False

    @pytest.mark.asyncio
    async def test_timeout(self):
        ch = WeComChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = httpx.TimeoutException("timeout")
            result = await ch.send(event=_event())
        assert result.error_code == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_generic_error(self):
        ch = WeComChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = RuntimeError("boom")
            result = await ch.send(event=_event())
        assert result.error_code == "SEND_ERROR"


class TestWeComTest:
    @pytest.mark.asyncio
    async def test_webhook_no_url(self):
        ch = WeComChannel({"webhook_url": "http://x"})
        ch.config = {"webhook_url": ""}
        result = await ch._test_webhook()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_webhook_success(self):
        ch = WeComChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.test()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_app_success(self):
        ch = WeComChannel({"corp_id": "c", "secret": "s", "agent_id": "a", "touser": "u"})
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.wecom_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.test()
        assert result.success is True


# ===========================================================================
# Feishu channel
# ===========================================================================

class TestFeishuValidate:
    def test_webhook_mode_ok(self):
        assert FeishuChannel({"webhook_url": "http://x"})._is_app_mode() is False

    def test_app_mode_ok(self):
        ch = FeishuChannel({"app_id": "a", "app_secret": "s", "receive_id_type": "open_id", "receive_id": "r"})
        assert ch._is_app_mode() is True

    def test_no_config_raises(self):
        with pytest.raises(ValueError):
            FeishuChannel({})

    def test_app_mode_requires_receive(self):
        with pytest.raises(ValueError):
            FeishuChannel({"app_id": "a", "app_secret": "s"})


class TestFeishuBuildCard:
    def test_build_card_no_data(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        card = ch._build_card(_event(data={}))
        assert card["msg_type"] == "interactive"
        assert card["card"]["header"]["title"]["content"] == "[TAM] 终端被封锁"

    def test_build_card_with_data_and_severity(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        card = ch._build_card(_event(severity="error", data={"ip": "1.2.3.4"}))
        assert card["card"]["header"]["template"] == "f5222d"


class TestFeishuSend:
    @pytest.mark.asyncio
    async def test_subject_message_webhook_success(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 0}))
            result = await ch.send(subject="s", message="m")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_webhook_card_success(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 0}))
            result = await ch.send(event=_event())
        assert result.success is True

    @pytest.mark.asyncio
    async def test_webhook_card_error(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(500, json_data={"code": 1, "msg": "bad"}))
            result = await ch.send(event=_event())
        assert result.success is False

    @pytest.mark.asyncio
    async def test_app_card_success(self):
        ch = FeishuChannel({"app_id": "a", "app_secret": "s", "receive_id_type": "open_id", "receive_id": "r"})
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 0}))
            result = await ch.send(event=_event())
        assert result.success is True
        assert result.recipient == "open_id:r"

    @pytest.mark.asyncio
    async def test_timeout(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = httpx.TimeoutException("timeout")
            result = await ch.send(event=_event())
        assert result.error_code == "TIMEOUT"


class TestFeishuTest:
    @pytest.mark.asyncio
    async def test_webhook_success(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 0}))
            result = await ch.test()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_app_success(self):
        ch = FeishuChannel({"app_id": "a", "app_secret": "s", "receive_id_type": "open_id", "receive_id": "r"})
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 0}))
            result = await ch.test()
        assert result.success is True


class TestFeishuToken:
    def _app_channel(self):
        return FeishuChannel(
            {"app_id": "a", "app_secret": "s", "receive_id_type": "open_id", "receive_id": "r"}
        )

    @pytest.mark.asyncio
    async def test_cached_token(self):
        ch = self._app_channel()
        redis = MagicMock()
        redis.get = AsyncMock(return_value="cached-token")
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            assert await ch._get_tenant_access_token() == "cached-token"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        ch = self._app_channel()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)), \
             patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 0, "tenant_access_token": "tok"}))
            assert await ch._get_tenant_access_token() == "tok"
        redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_error(self):
        ch = self._app_channel()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)), \
             patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 1, "msg": "bad"}))
            with pytest.raises(RuntimeError):
                await ch._get_tenant_access_token()


class TestFeishuAppText:
    def _app_channel(self):
        return FeishuChannel(
            {"app_id": "a", "app_secret": "s", "receive_id_type": "open_id", "receive_id": "r"}
        )

    @pytest.mark.asyncio
    async def test_subject_message_app_success(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 0}))
            result = await ch.send(subject="s", message="m")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_app_text_error(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 1, "msg": "bad"}))
            result = await ch._send_app_text("text", None)
        assert result == {"success": False, "message": "bad"}

    @pytest.mark.asyncio
    async def test_app_text_exception(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(side_effect=RuntimeError("boom"))
        result = await ch._send_app_text("text", None)
        assert result == {"success": False, "message": "boom"}


class TestFeishuAppCard:
    def _app_channel(self):
        return FeishuChannel(
            {"app_id": "a", "app_secret": "s", "receive_id_type": "open_id", "receive_id": "r"}
        )

    @pytest.mark.asyncio
    async def test_app_card_error(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 1, "msg": "bad"}))
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "1"

    @pytest.mark.asyncio
    async def test_app_card_timeout(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = httpx.TimeoutException("timeout")
            result = await ch.send(event=_event())
        assert result.error_code == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_app_card_generic_error(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = RuntimeError("boom")
            result = await ch.send(event=_event())
        assert result.error_code == "SEND_ERROR"


class TestFeishuNoArgsAndTest:
    def _app_channel(self):
        return FeishuChannel(
            {"app_id": "a", "app_secret": "s", "receive_id_type": "open_id", "receive_id": "r"}
        )

    @pytest.mark.asyncio
    async def test_no_event_or_subject_raises(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        with pytest.raises(ValueError):
            await ch.send()

    @pytest.mark.asyncio
    async def test_test_app_error(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"code": 1, "msg": "bad"}))
            result = await ch.test()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_test_app_exception(self):
        ch = self._app_channel()
        ch._get_tenant_access_token = AsyncMock(side_effect=RuntimeError("boom"))
        result = await ch.test()
        assert result.success is False
        assert "boom" in result.message

    @pytest.mark.asyncio
    async def test_test_webhook_no_url(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        ch.config = {"webhook_url": ""}
        result = await ch._test_webhook()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_test_webhook_exception(self):
        ch = FeishuChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.feishu_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = RuntimeError("boom")
            result = await ch._test_webhook()
        assert result.success is False


# ===========================================================================
# DingTalk channel
# ===========================================================================

class TestDingTalkValidate:
    def test_webhook_mode_ok(self):
        assert DingTalkChannel({"webhook_url": "http://x"})._is_app_mode() is False

    def test_app_mode_ok(self):
        ch = DingTalkChannel({"app_key": "k", "app_secret": "s", "agent_id": "a", "userid_list": "u"})
        assert ch._is_app_mode() is True

    def test_no_config_raises(self):
        with pytest.raises(ValueError):
            DingTalkChannel({})

    def test_app_mode_requires_agent(self):
        with pytest.raises(ValueError):
            DingTalkChannel({"app_key": "k", "app_secret": "s"})

    def test_app_mode_requires_target(self):
        with pytest.raises(ValueError):
            DingTalkChannel({"app_key": "k", "app_secret": "s", "agent_id": "a"})


class TestDingTalkSignature:
    def test_no_secret_returns_none(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        assert ch._generate_signature() is None

    def test_with_secret(self):
        ch = DingTalkChannel({"webhook_url": "http://x", "secret": "s"})
        sig = ch._generate_signature()
        assert sig.startswith("&timestamp=")
        assert "&sign=" in sig

    def test_get_webhook_url_no_secret(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        assert ch._get_webhook_url() == "http://x"

    def test_get_webhook_url_with_secret(self):
        ch = DingTalkChannel({"webhook_url": "http://x", "secret": "s"})
        assert ch._get_webhook_url().startswith("http://x&timestamp=")


class TestDingTalkSend:
    @pytest.mark.asyncio
    async def test_subject_message_webhook_success(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(subject="s", message="m")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_webhook_event_success(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(event=_event())
        assert result.success is True

    @pytest.mark.asyncio
    async def test_app_event_success(self):
        ch = DingTalkChannel({"app_key": "k", "app_secret": "s", "agent_id": "a", "userid_list": "u"})
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(event=_event())
        assert result.success is True
        assert "users:u" in result.recipient

    @pytest.mark.asyncio
    async def test_timeout(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = httpx.TimeoutException("timeout")
            result = await ch.send(event=_event())
        assert result.error_code == "TIMEOUT"


class TestDingTalkTest:
    @pytest.mark.asyncio
    async def test_webhook_success(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.test()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_app_success(self):
        ch = DingTalkChannel({"app_key": "k", "app_secret": "s", "agent_id": "a", "userid_list": "u"})
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.test()
        assert result.success is True


class TestDingTalkToken:
    def _app_channel(self):
        return DingTalkChannel({"app_key": "k", "app_secret": "s", "agent_id": "a", "userid_list": "u"})

    @pytest.mark.asyncio
    async def test_cached_token(self):
        ch = self._app_channel()
        redis = MagicMock()
        redis.get = AsyncMock(return_value="cached-token")
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            assert await ch._get_access_token() == "cached-token"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        ch = self._app_channel()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)), \
             patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0, "access_token": "tok"}))
            assert await ch._get_access_token() == "tok"
        redis.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_error(self):
        ch = self._app_channel()
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)), \
             patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 40001, "errmsg": "bad"}))
            with pytest.raises(RuntimeError):
                await ch._get_access_token()


class TestDingTalkAppMessage:
    def _app_channel(self):
        return DingTalkChannel({"app_key": "k", "app_secret": "s", "agent_id": "a", "userid_list": "u"})

    @pytest.mark.asyncio
    async def test_subject_message_app_success(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(subject="s", message="m")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_app_message_error(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 1, "errmsg": "bad"}))
            result = await ch._send_app_message("t", "txt", None)
        assert result == {"success": False, "message": "bad"}

    @pytest.mark.asyncio
    async def test_app_message_exception(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(side_effect=RuntimeError("boom"))
        result = await ch._send_app_message("t", "txt", None)
        assert result == {"success": False, "message": "boom"}

    @pytest.mark.asyncio
    async def test_app_message_full_targets(self):
        ch = DingTalkChannel(
            {"app_key": "k", "app_secret": "s", "agent_id": "a", "dept_id_list": "d", "to_all_user": True}
        )
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch._send_app_message("t", "txt", None)
        assert result == {"success": True}


class TestDingTalkAppEvent:
    def _app_channel(self, **extra):
        cfg = {"app_key": "k", "app_secret": "s", "agent_id": "a", "userid_list": "u"}
        cfg.update(extra)
        return DingTalkChannel(cfg)

    @pytest.mark.asyncio
    async def test_full_targets(self):
        ch = self._app_channel(dept_id_list="d", to_all_user=True)
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.send(event=_event())
        assert result.success is True
        assert result.recipient == "users:u, depts:d, all"

    @pytest.mark.asyncio
    async def test_app_event_error(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 1, "errmsg": "bad"}))
            result = await ch.send(event=_event())
        assert result.success is False
        assert result.error_code == "1"

    @pytest.mark.asyncio
    async def test_app_event_timeout(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = httpx.TimeoutException("timeout")
            result = await ch.send(event=_event())
        assert result.error_code == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_app_event_generic_error(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            inner = _client(mc, lambda *a, **k: None)
            inner.post.side_effect = RuntimeError("boom")
            result = await ch.send(event=_event())
        assert result.error_code == "SEND_ERROR"


class TestDingTalkBuildMessage:
    def test_build_message_with_data(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        msg = ch._build_message(_event(data={"ip": "1.2.3.4"}))
        assert "- **ip**: 1.2.3.4" in msg["markdown"]["text"]

    def test_build_message_no_data(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        msg = ch._build_message(_event())
        assert "**详细信息**" not in msg["markdown"]["text"]


class TestDingTalkNoArgsAndTest:
    def _app_channel(self):
        return DingTalkChannel({"app_key": "k", "app_secret": "s", "agent_id": "a", "userid_list": "u"})

    @pytest.mark.asyncio
    async def test_no_event_or_subject_raises(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        with pytest.raises(ValueError):
            await ch.send()

    @pytest.mark.asyncio
    async def test_test_app_error(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 1, "errmsg": "bad"}))
            result = await ch.test()
        assert result.success is False

    @pytest.mark.asyncio
    async def test_test_app_exception(self):
        ch = self._app_channel()
        ch._get_access_token = AsyncMock(side_effect=RuntimeError("boom"))
        result = await ch.test()
        assert result.success is False
        assert "boom" in result.message

    @pytest.mark.asyncio
    async def test_test_app_full_targets(self):
        ch = DingTalkChannel(
            {"app_key": "k", "app_secret": "s", "agent_id": "a", "dept_id_list": "d", "to_all_user": True}
        )
        ch._get_access_token = AsyncMock(return_value="tok")
        with patch("app.services.notification_channels.dingtalk_channel.httpx.AsyncClient") as mc:
            _client(mc, lambda *a, **k: _http(200, json_data={"errcode": 0}))
            result = await ch.test()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_test_webhook_no_url(self):
        ch = DingTalkChannel({"webhook_url": "http://x"})
        ch.config = {"webhook_url": ""}
        result = await ch._test_webhook()
        assert result.success is False