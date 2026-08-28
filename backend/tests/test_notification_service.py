"""Unit tests for notification service"""
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-for-testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.services.notification_channels.event_types import ChannelType, EventType
from app.services.notification_service import NotificationService
from app.services.notification_channels.base import (
    ChannelTestResult,
    NotificationEvent,
    NotificationResult,
)

import types
from datetime import datetime

from tests.conftest import make_mock_async_session


@pytest.fixture
def mock_db(mock_async_session):
    """Mock AsyncSession with correct sync/async method split."""
    return mock_async_session


class TestNotificationService:
    """Test cases for NotificationService"""

    @pytest.mark.asyncio
    async def test_publish_event(self, mock_db):
        """Test publishing an event"""
        mock_email_channel = AsyncMock()
        mock_email_channel.send = AsyncMock(return_value={"success": True})

        service = NotificationService(mock_db)
        service._channels = {
            ChannelType.EMAIL: mock_email_channel
        }

        await service.publish_event(EventType.TERMINAL_BLOCKED, {
            "terminal_id": "term123",
            "ip_address": "192.168.1.1"
        })

        mock_email_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification(self, mock_db):
        """Test sending a notification"""
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock(return_value={"success": True})

        service = NotificationService(mock_db)
        service._channels = {
            "test": mock_channel
        }

        result = await service.send_notification(
            channel_type="test",
            recipients=["user@example.com"],
            subject="Test Subject",
            message="Test Message"
        )

        assert result["success"] is True
        mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_notification(self, mock_db):
        """Test logging a notification"""
        service = NotificationService(mock_db)
        await service.log_notification(
            channel_type="email",
            recipient="test@example.com",
            success=True,
            event_type="TEST_EVENT",
            message_id="msg123"
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_metadata(self, mock_db):
        """Test getting channel metadata"""
        service = NotificationService(mock_db)

        metadata = service.get_channel_metadata()
        assert isinstance(metadata, dict)
        assert ChannelType.EMAIL.value in metadata

    @pytest.mark.asyncio
    async def test_get_event_types(self, mock_db):
        """Test getting event types"""
        service = NotificationService(mock_db)

        events = service.get_event_types()
        assert isinstance(events, list)
        assert len(events) > 0


class TestEmailChannel:
    """Test cases for EmailChannel"""

    @pytest.mark.asyncio
    @patch("app.services.notification_channels.email_channel.httpx.AsyncClient")
    async def test_send_email(self, mock_client_class):
        """Test sending email notification"""
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        from app.services.notification_channels.email_channel import EmailChannel

        channel = EmailChannel({"enabled": True, "smtp_url": "http://localhost:8080/smtp"})
        result = await channel.send(
            recipients=["test@example.com"],
            subject="Test",
            message="Test message"
        )

        assert result.success is True
        mock_client.post.assert_called_once()


class TestWebhookChannel:
    """Test cases for WebhookChannel"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_webhook(self, mock_client_class):
        """Test sending webhook notification"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        from app.services.notification_channels.webhook_channel import WebhookChannel

        channel = WebhookChannel({
            "url": "https://webhook.example.com",
            "secret": "secret123"
        })
        result = await channel.send(
            recipients=["test"],
            subject="Test",
            message="Test message"
        )

        assert result["success"] is True
        mock_client.post.assert_called_once()


class TestFeishuChannel:
    """Test cases for FeishuChannel"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_feishu(self, mock_client_class):
        """Test sending Feishu notification"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={"code": 0})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        from app.services.notification_channels.feishu_channel import FeishuChannel

        channel = FeishuChannel({
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test"
        })
        result = await channel.send(
            recipients=["test"],
            subject="Test",
            message="Test message"
        )

        assert result["success"] is True
        mock_client.post.assert_called_once()


class TestDingTalkChannel:
    """Test cases for DingTalkChannel"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_dingtalk(self, mock_client_class):
        """Test sending DingTalk notification"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={"errcode": 0})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        from app.services.notification_channels.dingtalk_channel import DingTalkChannel

        channel = DingTalkChannel({
            "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=test"
        })
        result = await channel.send(
            recipients=["test"],
            subject="Test",
            message="Test message"
        )

        assert result["success"] is True
        mock_client.post.assert_called_once()


class TestWeComChannel:
    """Test cases for WeComChannel"""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_send_wecom(self, mock_client_class):
        """Test sending WeCom notification"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={"errcode": 0})
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        from app.services.notification_channels.wecom_channel import WeComChannel

        channel = WeComChannel({
            "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        })
        result = await channel.send(
            recipients=["test"],
            subject="Test",
            message="Test message"
        )

        assert result["success"] is True
        mock_client.post.assert_called_once()


# ===========================================================================
# Helpers
# ===========================================================================

def _ns(**kwargs):
    return types.SimpleNamespace(**kwargs)


def _scalar_result(scalar):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    return result


def _scalars_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _channel_row(**kwargs):
    defaults = dict(
        id=1, name="ch", type="email", config={}, enabled=True,
        events=[], description=None, created_by=None,
    )
    defaults.update(kwargs)
    return _ns(**defaults)


# ===========================================================================
# Session scope and lazy accessors
# ===========================================================================

class TestSessionScope:
    @pytest.mark.asyncio
    async def test_injected_db_yields_self(self, mock_db):
        service = NotificationService(mock_db)
        async with service._session_scope() as session:
            assert session is mock_db

    @pytest.mark.asyncio
    async def test_singleton_opens_factory_session(self):
        fake_session = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=fake_session)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.database.async_session_factory", return_value=cm):
            service = NotificationService()
            async with service._session_scope() as session:
                assert session is fake_session


class TestLazyAccessors:
    def test_get_workers_lazy_and_cached(self):
        with patch("app.services.notification_workers.NotificationWorkers") as mock_cls:
            service = NotificationService()
            w1 = service._get_workers()
            w2 = service._get_workers()
        assert w1 is w2
        mock_cls.assert_called_once_with(service._channels, service._channel_configs)

    def test_get_logger(self):
        with patch("app.services.notification_logging.NotificationLogger") as mock_cls:
            service = NotificationService(MagicMock())
            logger_inst = service._get_logger()
        assert logger_inst is mock_cls.return_value
        mock_cls.assert_called_once_with(service.db)


# ===========================================================================
# initialize_channels
# ===========================================================================

class TestInitializeChannels:
    @pytest.mark.asyncio
    async def test_empty_channels_clears_cache(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalars_result([]))
        service = NotificationService(mock_db)
        service._channels = {"stale": MagicMock()}

        with patch("app.services.notification_service.get_channel") as gc:
            await service.initialize_channels()

        assert service._channels == {}
        gc.assert_not_called()

    @pytest.mark.asyncio
    async def test_loads_enabled_channel(self, mock_db):
        channel = _channel_row(name="email1", type="webhook", config={"url": "x"})
        mock_db.execute = AsyncMock(return_value=_scalars_result([channel]))
        fake = MagicMock()
        service = NotificationService(mock_db)
        service._channels = {}
        service._channel_configs = {}

        with patch("app.services.notification_service.get_channel", return_value=fake) as gc, \
             patch("app.services.notification_service.has_encrypted_config", return_value=False):
            await service.initialize_channels()

        assert service._channels["email1"] is fake
        assert service._channel_configs["email1"]["type"] == "webhook"
        gc.assert_called_once_with("webhook", {"url": "x"})

    @pytest.mark.asyncio
    async def test_decrypts_encrypted_config(self, mock_db):
        channel = _channel_row(config={"encrypted": True})
        mock_db.execute = AsyncMock(return_value=_scalars_result([channel]))
        fake = MagicMock()
        service = NotificationService(mock_db)

        with patch("app.services.notification_service.get_channel", return_value=fake) as gc, \
             patch("app.services.notification_service.has_encrypted_config", return_value=True), \
             patch("app.services.notification_service.decrypt_config", return_value={"url": "dec"}) as dc:
            await service.initialize_channels()

        dc.assert_called_once_with({"encrypted": True})
        gc.assert_called_once_with("email", {"url": "dec"})

    @pytest.mark.asyncio
    async def test_channel_load_error_is_swallowed(self, mock_db):
        channel = _channel_row(name="bad")
        mock_db.execute = AsyncMock(return_value=_scalars_result([channel]))
        service = NotificationService(mock_db)

        with patch("app.services.notification_service.get_channel", side_effect=Exception("boom")):
            await service.initialize_channels()

        assert service._channels == {}

    @pytest.mark.asyncio
    async def test_refreshes_existing_workers(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalars_result([]))
        service = NotificationService(mock_db)
        service._workers = MagicMock()

        await service.initialize_channels()

        assert service._workers._channels == {}
        assert service._workers._channel_configs == {}


# ===========================================================================
# Channel queries and CRUD
# ===========================================================================

class TestChannelQueries:
    @pytest.mark.asyncio
    async def test_get_channels(self, mock_db):
        row = _channel_row()
        mock_db.execute = AsyncMock(return_value=_scalars_result([row]))
        service = NotificationService(mock_db)
        assert await service.get_channels() == [row]

    @pytest.mark.asyncio
    async def test_get_channel_by_id(self, mock_db):
        row = _channel_row()
        mock_db.execute = AsyncMock(return_value=_scalar_result(row))
        service = NotificationService(mock_db)
        assert await service.get_channel_by_id(1) is row


class TestChannelCRUD:
    @pytest.mark.asyncio
    async def test_create_channel(self, mock_db):
        service = NotificationService(mock_db)
        service.initialize_channels = AsyncMock()
        service._refresh_global_channels = AsyncMock()

        result = await service.create_channel(
            name="n", channel_type="email", config={}, events=["terminal.blocked"]
        )

        assert result.name == "n"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()
        service.initialize_channels.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_channel_not_found(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(None))
        service = NotificationService(mock_db)
        service.initialize_channels = AsyncMock()
        service._refresh_global_channels = AsyncMock()

        assert await service.update_channel(99, name="x") is None
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_channel_found(self, mock_db):
        channel = MagicMock()
        mock_db.execute = AsyncMock(return_value=_scalar_result(channel))
        service = NotificationService(mock_db)
        service.initialize_channels = AsyncMock()
        service._refresh_global_channels = AsyncMock()

        result = await service.update_channel(1, name="new", enabled=False)

        assert result is channel
        assert channel.name == "new"
        assert channel.enabled is False
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_channel_not_found(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(None))
        service = NotificationService(mock_db)
        service.initialize_channels = AsyncMock()
        service._refresh_global_channels = AsyncMock()

        assert await service.delete_channel(99) is False
        mock_db.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_channel_found(self, mock_db):
        channel = MagicMock()
        mock_db.execute = AsyncMock(return_value=_scalar_result(channel))
        service = NotificationService(mock_db)
        service.initialize_channels = AsyncMock()
        service._refresh_global_channels = AsyncMock()

        assert await service.delete_channel(1) is True
        mock_db.delete.assert_awaited_once_with(channel)
        mock_db.commit.assert_awaited_once()


# ===========================================================================
# _refresh_global_channels
# ===========================================================================

class TestRefreshGlobalChannels:
    @pytest.mark.asyncio
    async def test_no_global_service(self):
        service = NotificationService()
        with patch("app.services.event_emitter.get_notification_service", return_value=None):
            await service._refresh_global_channels()

    @pytest.mark.asyncio
    async def test_global_is_self_skips(self):
        service = NotificationService()
        with patch("app.services.event_emitter.get_notification_service", return_value=service):
            await service._refresh_global_channels()

    @pytest.mark.asyncio
    async def test_refreshes_other_global(self):
        service = NotificationService()
        other = MagicMock()
        other.initialize_channels = AsyncMock()
        with patch("app.services.event_emitter.get_notification_service", return_value=other):
            await service._refresh_global_channels()
        other.initialize_channels.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_error_swallowed(self):
        service = NotificationService()
        other = MagicMock()
        other.initialize_channels = AsyncMock(side_effect=Exception("boom"))
        with patch("app.services.event_emitter.get_notification_service", return_value=other):
            await service._refresh_global_channels()


# ===========================================================================
# test_channel
# ===========================================================================

class TestTestChannel:
    @pytest.mark.asyncio
    async def test_not_found(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalar_result(None))
        service = NotificationService(mock_db)
        result = await service.test_channel(99)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_found_success(self, mock_db):
        row = _channel_row(type="webhook", config={"url": "x"})
        mock_db.execute = AsyncMock(return_value=_scalar_result(row))
        fake = MagicMock()
        fake.test = AsyncMock(return_value=ChannelTestResult(True, "ok", {"a": 1}))
        service = NotificationService(mock_db)

        with patch("app.services.notification_service.get_channel", return_value=fake), \
             patch("app.services.notification_service.has_encrypted_config", return_value=False):
            result = await service.test_channel(1)

        assert result == {"success": True, "message": "ok", "details": {"a": 1}}

    @pytest.mark.asyncio
    async def test_found_exception(self, mock_db):
        row = _channel_row()
        mock_db.execute = AsyncMock(return_value=_scalar_result(row))
        service = NotificationService(mock_db)

        with patch("app.services.notification_service.get_channel", side_effect=Exception("nope")):
            result = await service.test_channel(1)

        assert result["success"] is False
        assert "Test failed" in result["message"]


# ===========================================================================
# Worker delegation
# ===========================================================================

class TestWorkerDelegation:
    @pytest.mark.asyncio
    async def test_start_workers(self):
        service = NotificationService()
        service._workers = MagicMock()
        service._workers.start_workers = AsyncMock()
        await service.start_workers()
        service._workers.start_workers.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_workers(self):
        service = NotificationService()
        service._workers = MagicMock()
        service._workers.stop_workers = AsyncMock()
        await service.stop_workers()
        service._workers.stop_workers.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_emit(self):
        service = NotificationService()
        service._workers = MagicMock()
        service._workers.emit = AsyncMock(return_value=[1, 2])
        result = await service.emit("terminal.blocked", {"a": 1})
        assert result == [1, 2]
        service._workers.emit.assert_awaited_once()


# ===========================================================================
# Log delegation wrappers
# ===========================================================================

class TestLogDelegation:
    def _service_with_logger(self):
        service = NotificationService()
        logger_inst = MagicMock()
        logger_inst.log_suppressed = AsyncMock()
        logger_inst.log_sent = AsyncMock()
        logger_inst.log_retrying = AsyncMock()
        logger_inst.log_failed = AsyncMock()
        logger_inst.log_notification = AsyncMock()
        logger_inst.render_template = AsyncMock()
        logger_inst.get_notification_logs = AsyncMock()
        service._get_logger = MagicMock(return_value=logger_inst)
        return service, logger_inst

    @pytest.mark.asyncio
    async def test_log_suppressed(self):
        service, logger_inst = self._service_with_logger()
        event = NotificationEvent(id="e", type="t", timestamp=datetime.now())
        await service._log_suppressed(event, "email", 300)
        logger_inst.log_suppressed.assert_awaited_once_with(event, "email", 300)

    @pytest.mark.asyncio
    async def test_log_sent(self):
        service, logger_inst = self._service_with_logger()
        event = NotificationEvent(id="e", type="t", timestamp=datetime.now())
        result = NotificationResult(True, "ok", "email")
        await service._log_sent(event, "email", result)
        logger_inst.log_sent.assert_awaited_once_with(event, "email", result)

    @pytest.mark.asyncio
    async def test_log_retrying(self):
        service, logger_inst = self._service_with_logger()
        event = NotificationEvent(id="e", type="t", timestamp=datetime.now())
        result = NotificationResult(False, "again", "email")
        await service._log_retrying(event, "email", result, 1, datetime(2026, 1, 1))
        logger_inst.log_retrying.assert_awaited_once_with(event, "email", result, 1, datetime(2026, 1, 1))

    @pytest.mark.asyncio
    async def test_log_failed(self):
        service, logger_inst = self._service_with_logger()
        event = NotificationEvent(id="e", type="t", timestamp=datetime.now())
        result = NotificationResult(False, "boom", "email")
        await service._log_failed(event, "email", result, 3)
        logger_inst.log_failed.assert_awaited_once_with(event, "email", result, 3)

    @pytest.mark.asyncio
    async def test_log_notification(self):
        service, logger_inst = self._service_with_logger()
        event = NotificationEvent(id="e", type="t", timestamp=datetime.now())
        result = NotificationResult(True, "", "email")
        await service._log_notification(event, "email", result)
        logger_inst.log_notification.assert_awaited_once_with(event, "email", result, service.db)

    @pytest.mark.asyncio
    async def test_render_template(self):
        service, logger_inst = self._service_with_logger()
        event = NotificationEvent(id="e", type="t", timestamp=datetime.now())
        await service._render_template(event, "email")
        logger_inst.render_template.assert_awaited_once_with(event, "email")

    @pytest.mark.asyncio
    async def test_get_notification_logs(self):
        service, logger_inst = self._service_with_logger()
        service.db = MagicMock()
        await service.get_notification_logs()
        logger_inst.get_notification_logs.assert_awaited_once()


# ===========================================================================
# send_notification branches
# ===========================================================================

class TestSendNotificationExtended:
    @pytest.mark.asyncio
    async def test_channel_not_found(self, mock_db):
        service = NotificationService(mock_db)
        service._channels = {}
        result = await service.send_notification("email", ["a@b.c"], "s", "m")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_dict_result_passthrough(self, mock_db):
        channel = MagicMock()
        channel.send = AsyncMock(return_value={"success": True, "extra": "x"})
        service = NotificationService(mock_db)
        service._channels = {"email": channel}
        result = await service.send_notification("email", ["a@b.c"], "s", "m")
        assert result == {"success": True, "extra": "x"}

    @pytest.mark.asyncio
    async def test_notification_result_wrapped(self, mock_db):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=NotificationResult(True, "sent", "email"))
        service = NotificationService(mock_db)
        service._channels = {"email": channel}
        result = await service.send_notification("email", ["a@b.c"], "s", "m")
        assert result == {"success": True, "message": "sent"}


# ===========================================================================
# get_statistics
# ===========================================================================

class TestGetStatistics:
    def _status_rows(self):
        return [("sent", 5), ("failed", 2), ("pending", 1), ("retrying", 1), ("suppressed", 1)]

    def _setup_db(self, mock_db, status_rows=None, lat_scalar=125.0,
                  ch_rows=None, ev_rows=None):
        status_result = MagicMock()
        status_result.all.return_value = status_rows if status_rows is not None else self._status_rows()
        lat_result = MagicMock()
        lat_result.scalar.return_value = lat_scalar
        ch_result = MagicMock()
        ch_result.all.return_value = ch_rows if ch_rows is not None else [("email", 6, 5, 1)]
        ev_result = MagicMock()
        ev_result.all.return_value = ev_rows if ev_rows is not None else [("terminal.blocked", 5, 4, 1)]
        mock_db.execute = AsyncMock(side_effect=[status_result, lat_result, ch_result, ev_result])

    @pytest.mark.asyncio
    async def test_full_success(self, mock_db):
        self._setup_db(mock_db)
        redis = MagicMock()
        redis.llen = AsyncMock(return_value=3)
        redis.zcard = AsyncMock(return_value=1)

        service = NotificationService(mock_db)
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            stats = await service.get_statistics()

        assert stats["overview"]["total"] == 10
        assert stats["overview"]["sent"] == 5
        assert stats["overview"]["success_rate"] == 71.43
        assert stats["overview"]["avg_latency_ms"] == 125.0
        assert stats["overview"]["queue_size"] == 3
        assert stats["overview"]["retry_queue_size"] == 1
        assert stats["by_channel"][0]["channel_name"] == "email"
        assert stats["by_event"][0]["event_type"] == "terminal.blocked"

    @pytest.mark.asyncio
    async def test_latency_exception(self, mock_db):
        status_result = MagicMock()
        status_result.all.return_value = self._status_rows()
        ch_result = MagicMock()
        ch_result.all.return_value = [("email", 6, 5, 1)]
        ev_result = MagicMock()
        ev_result.all.return_value = [("terminal.blocked", 5, 4, 1)]
        mock_db.execute = AsyncMock(
            side_effect=[status_result, Exception("lat"), ch_result, ev_result]
        )
        redis = MagicMock()
        redis.llen = AsyncMock(return_value=0)
        redis.zcard = AsyncMock(return_value=0)

        service = NotificationService(mock_db)
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            stats = await service.get_statistics()

        assert stats["overview"]["avg_latency_ms"] is None

    @pytest.mark.asyncio
    async def test_channel_exception(self, mock_db):
        status_result = MagicMock()
        status_result.all.return_value = self._status_rows()
        lat_result = MagicMock()
        lat_result.scalar.return_value = 10.0
        ev_result = MagicMock()
        ev_result.all.return_value = [("terminal.blocked", 5, 4, 1)]
        mock_db.execute = AsyncMock(
            side_effect=[status_result, lat_result, Exception("ch"), ev_result]
        )
        redis = MagicMock()
        redis.llen = AsyncMock(return_value=0)
        redis.zcard = AsyncMock(return_value=0)

        service = NotificationService(mock_db)
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            stats = await service.get_statistics()

        assert stats["by_channel"] == []

    @pytest.mark.asyncio
    async def test_event_exception(self, mock_db):
        status_result = MagicMock()
        status_result.all.return_value = self._status_rows()
        lat_result = MagicMock()
        lat_result.scalar.return_value = 10.0
        ch_result = MagicMock()
        ch_result.all.return_value = [("email", 6, 5, 1)]
        mock_db.execute = AsyncMock(
            side_effect=[status_result, lat_result, ch_result, Exception("ev")]
        )
        redis = MagicMock()
        redis.llen = AsyncMock(return_value=0)
        redis.zcard = AsyncMock(return_value=0)

        service = NotificationService(mock_db)
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            stats = await service.get_statistics()

        assert stats["by_event"] == []

    @pytest.mark.asyncio
    async def test_redis_exception(self, mock_db):
        self._setup_db(mock_db)
        service = NotificationService(mock_db)
        with patch("app.core.security.get_redis_client", new=AsyncMock(side_effect=Exception("redis"))):
            stats = await service.get_statistics()

        assert stats["overview"]["queue_size"] == 0
        assert stats["overview"]["retry_queue_size"] == 0


# ===========================================================================
# retry_failed_notification / retry_all_failed
# ===========================================================================

class TestRetryFailedNotification:
    @pytest.mark.asyncio
    async def test_log_not_found(self, mock_db):
        mock_db.get = AsyncMock(return_value=None)
        service = NotificationService(mock_db)
        assert await service.retry_failed_notification(99) is False

    @pytest.mark.asyncio
    async def test_wrong_status(self, mock_db):
        mock_db.get = AsyncMock(return_value=_ns(status="sent"))
        service = NotificationService(mock_db)
        assert await service.retry_failed_notification(1) is False

    @pytest.mark.asyncio
    async def test_success(self, mock_db):
        log = _ns(
            status="failed", event_id="e1", event_type="terminal.blocked",
            details={"event_data": {"ip": "1.2.3.4"}}, sent_at=datetime(2026, 1, 1),
            error_message="old", next_retry_at=datetime(2026, 1, 2), retry_count=2,
        )
        mock_db.get = AsyncMock(return_value=log)
        redis = MagicMock()
        redis.lpush = AsyncMock()
        service = NotificationService(mock_db)

        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=redis)):
            assert await service.retry_failed_notification(1) is True

        assert log.status == "pending"
        assert log.error_message is None
        assert log.next_retry_at is None
        assert log.retry_count == 0
        redis.lpush.assert_awaited_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_exception(self, mock_db):
        mock_db.get = AsyncMock(return_value=_ns(
            status="failed", event_id="e1", event_type="t", details={},
            sent_at=datetime(2026, 1, 1),
        ))
        service = NotificationService(mock_db)
        with patch("app.core.security.get_redis_client", new=AsyncMock(side_effect=Exception("boom"))):
            assert await service.retry_failed_notification(1) is False


class TestRetryAllFailed:
    @pytest.mark.asyncio
    async def test_no_logs(self, mock_db):
        mock_db.execute = AsyncMock(return_value=_scalars_result([]))
        service = NotificationService(mock_db)
        assert await service.retry_all_failed() == 0

    @pytest.mark.asyncio
    async def test_counts_successes(self, mock_db):
        logs = [_ns(id=1), _ns(id=2)]
        mock_db.execute = AsyncMock(return_value=_scalars_result(logs))
        service = NotificationService(mock_db)
        service.retry_failed_notification = AsyncMock(side_effect=[True, False])
        assert await service.retry_all_failed() == 1


# ===========================================================================
# _get_event_coverage
# ===========================================================================

class TestEventCoverage:
    @pytest.mark.asyncio
    async def test_empty_emitted(self):
        service = NotificationService()
        result = await service._get_event_coverage([])
        assert result["total_emitted"] == 0
        assert result["coverage_rate"] == 0.0
        assert len(result["never_emitted"]) == result["total_defined"]

    @pytest.mark.asyncio
    async def test_partial(self):
        service = NotificationService()
        by_event = [{"event_type": "terminal.blocked"}]
        result = await service._get_event_coverage(by_event)
        assert result["total_emitted"] == 1
