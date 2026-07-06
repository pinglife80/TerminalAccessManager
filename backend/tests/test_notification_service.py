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


class TestNotificationService:
    """Test cases for NotificationService"""

    @pytest.mark.asyncio
    async def test_publish_event(self):
        """Test publishing an event"""
        mock_db = AsyncMock()
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
    async def test_send_notification(self):
        """Test sending a notification"""
        mock_db = AsyncMock()
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
    async def test_log_notification(self):
        """Test logging a notification"""
        mock_db = AsyncMock()

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
    async def test_get_channel_metadata(self):
        """Test getting channel metadata"""
        mock_db = AsyncMock()
        service = NotificationService(mock_db)

        metadata = service.get_channel_metadata()
        assert isinstance(metadata, dict)
        assert ChannelType.EMAIL.value in metadata

    @pytest.mark.asyncio
    async def test_get_event_types(self):
        """Test getting event types"""
        mock_db = AsyncMock()
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
