"""
WeCom (企业微信) Notification Channel for TerminalAccessManager.

Sends notifications via WeCom webhook robot.
"""

from typing import Any

import httpx
from loguru import logger

from app.services.notification_channels.base import (
    ChannelTestResult,
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
)


class WecomChannel(NotificationChannelBase):
    """
    WeCom (企业微信) webhook robot notification channel.

    Sends rich messages to WeCom groups via webhook.
    """

    channel_type = "wecom"
    channel_name = "企业微信通知"

    def _validate_config(self) -> None:
        """Validate WeCom channel configuration"""
        if "webhook_url" not in self.config or not self.config["webhook_url"]:
            raise ValueError("WeCom channel requires 'webhook_url' configuration")

    def _build_message(self, event: NotificationEvent) -> dict[str, Any]:
        """Build WeCom markdown message"""
        from app.services.notification_channels.event_types import EVENT_METADATA

        metadata = EVENT_METADATA.get(event.type, {})
        event_name = metadata.get("name", event.type)

        # Build markdown content (WeCom supports a subset of markdown)
        content = f"### {event_name}\n\n"
        content += f"{metadata.get('description', '')}\n\n"
        content += "> 时间: {}\n\n".format(event.timestamp.strftime('%Y-%m-%d %H:%M:%S'))
        content += f"> 严重级别: **{event.severity.upper()}**\n\n"
        content += f"> 来源: {event.source}\n\n"

        if event.data:
            content += "---\n\n"
            for key, value in event.data.items():
                content += f"**{key}**: {value}\n\n"

        return {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
            },
        }

    async def send(
        self,
        event: NotificationEvent,
        template_data: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Send WeCom notification"""
        webhook_url = self.config["webhook_url"]
        payload = self._build_message(event)

        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                result = response.json()

                if result.get("errcode") == 0:
                    logger.info(f"WeCom notification sent: {event.type}")
                    return NotificationResult(
                        success=True,
                        message="Notification sent successfully",
                        channel=self.channel_type,
                        event_id=event.id,
                        recipient=webhook_url[:50] + "...",
                    )
                else:
                    error_msg = result.get("errmsg", "Unknown error")
                    logger.warning(f"WeCom send failed: {error_msg}")
                    return NotificationResult(
                        success=False,
                        message=f"WeCom API error: {error_msg}",
                        channel=self.channel_type,
                        event_id=event.id,
                        error_code=str(result.get("errcode")),
                    )

        except httpx.TimeoutException:
            logger.error("WeCom timeout")
            return NotificationResult(
                success=False,
                message="Request timeout",
                channel=self.channel_type,
                event_id=event.id,
                error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"WeCom send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False,
                message=f"Send failed: {str(e)}",
                channel=self.channel_type,
                event_id=event.id,
                error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test WeCom webhook connection"""
        webhook_url = self.config.get("webhook_url")

        if not webhook_url:
            return ChannelTestResult(
                success=False,
                message="Webhook URL not configured",
            )

        # Send a test message
        test_message = {
            "msgtype": "markdown",
            "markdown": {
                "content": "### 🔧 连接测试\n\n这是一条测试消息，用于验证企业微信机器人配置是否正确。\n\n> 如果收到此消息，说明配置成功",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    webhook_url,
                    json=test_message,
                    headers={"Content-Type": "application/json"},
                )

                result = response.json()

                if result.get("errcode") == 0:
                    return ChannelTestResult(
                        success=True,
                        message="WeCom webhook test successful",
                    )
                else:
                    return ChannelTestResult(
                        success=False,
                        message=f"WeCom API error: {result.get('errmsg', 'Unknown')}",
                    )

        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
            )
