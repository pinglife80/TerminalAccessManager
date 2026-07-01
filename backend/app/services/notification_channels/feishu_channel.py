"""
Feishu (飞书) Notification Channel for TerminalAccessManager.

Sends notifications via Feishu webhook robot.
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


class FeishuChannel(NotificationChannelBase):
    """
    Feishu webhook robot notification channel.

    Sends rich card messages to Feishu groups or users via webhook.
    """

    channel_type = "feishu"
    channel_name = "飞书通知"

    def _validate_config(self) -> None:
        """Validate Feishu channel configuration"""
        if "webhook_url" not in self.config or not self.config["webhook_url"]:
            raise ValueError("Feishu channel requires 'webhook_url' configuration")

    def _build_card(self, event: NotificationEvent) -> dict[str, Any]:
        """Build Feishu interactive card payload"""
        from app.services.notification_channels.event_types import EVENT_METADATA

        metadata = EVENT_METADATA.get(event.type, {})
        event_name = metadata.get("name", event.type)

        # Color based on severity
        color_map = {
            "info": "#1890FF",
            "warning": "#FAAD14",
            "error": "#F5222D",
        }
        color = color_map.get(event.severity, "#1890FF")

        # Build card elements
        elements = [
            {
                "tag": "markdown",
                "content": f"**{event_name}**\n{metadata.get('description', '')}",
            },
            {
                "tag": "hr",
            },
            {
                "tag": "column_set",
                "flex_mode": "none",
                "horizontal_spacing": "default",
                "children": [
                    {
                        "tag": "column",
                        "width": "auto",
                        "widgets": [
                            {
                                "tag": "markdown",
                                "content": f"**严重级别**\n{event.severity.upper()}",
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "auto",
                        "widgets": [
                            {
                                "tag": "markdown",
                                "content": f"**来源**\n{event.source}",
                            }
                        ],
                    },
                    {
                        "tag": "column",
                        "width": "strech",
                        "widgets": [
                            {
                                "tag": "markdown",
                                "content": f"**时间**\n{event.timestamp.strftime('%H:%M:%S')}",
                            }
                        ],
                    },
                ],
            },
        ]

        # Add data fields if present
        if event.data:
            data_lines = []
            for key, value in event.data.items():
                data_lines.append(f"**{key}**: {value}")
            elements.append({
                "tag": "markdown",
                "content": "\n".join(data_lines),
            })

        # Build the card
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"[TAM] {event_name}",
                    },
                    "template": color.replace("#", "").lower(),
                },
                "elements": elements,
            },
        }

        return card

    async def send(
        self,
        event: NotificationEvent,
        template_data: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Send Feishu notification"""
        webhook_url = self.config["webhook_url"]

        payload = self._build_card(event)

        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                result = response.json()

                if result.get("code") == 0 or response.status_code == 200:
                    logger.info(f"Feishu notification sent: {event.type}")
                    return NotificationResult(
                        success=True,
                        message="Notification sent successfully",
                        channel=self.channel_type,
                        event_id=event.id,
                        recipient=webhook_url,
                    )
                else:
                    error_msg = result.get("msg", "Unknown error")
                    logger.warning(f"Feishu send failed: {error_msg}")
                    return NotificationResult(
                        success=False,
                        message=f"Feishu API error: {error_msg}",
                        channel=self.channel_type,
                        event_id=event.id,
                        error_code=str(result.get("code")),
                    )

        except httpx.TimeoutException:
            logger.error(f"Feishu timeout: {webhook_url}")
            return NotificationResult(
                success=False,
                message="Request timeout",
                channel=self.channel_type,
                event_id=event.id,
                error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"Feishu send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False,
                message=f"Send failed: {str(e)}",
                channel=self.channel_type,
                event_id=event.id,
                error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test Feishu webhook connection"""
        webhook_url = self.config.get("webhook_url")

        if not webhook_url:
            return ChannelTestResult(
                success=False,
                message="Webhook URL not configured",
            )

        # Send a test card
        test_card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "[TAM] 连接测试",
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": "这是一条测试消息，用于验证飞书机器人配置是否正确。",
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": "如果收到此消息，说明配置成功",
                            }
                        ],
                    },
                ],
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    webhook_url,
                    json=test_card,
                    headers={"Content-Type": "application/json"},
                )

                result = response.json()

                if result.get("code") == 0:
                    return ChannelTestResult(
                        success=True,
                        message="Feishu webhook test successful",
                    )
                else:
                    return ChannelTestResult(
                        success=False,
                        message=f"Feishu API error: {result.get('msg', 'Unknown')}",
                    )

        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
            )
