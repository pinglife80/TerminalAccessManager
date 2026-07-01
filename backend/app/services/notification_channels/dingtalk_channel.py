"""
DingTalk (钉钉) Notification Channel for TerminalAccessManager.

Sends notifications via DingTalk webhook robot with signature verification.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Any

import httpx
from loguru import logger

from app.services.notification_channels.base import (
    ChannelTestResult,
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
)


class DingTalkChannel(NotificationChannelBase):
    """
    DingTalk webhook robot notification channel.

    Sends markdown messages to DingTalk groups via webhook with optional secret signature.
    """

    channel_type = "dingtalk"
    channel_name = "钉钉通知"

    def _validate_config(self) -> None:
        """Validate DingTalk channel configuration"""
        if "webhook_url" not in self.config or not self.config["webhook_url"]:
            raise ValueError("DingTalk channel requires 'webhook_url' configuration")

    def _generate_signature(self) -> str | None:
        """Generate timestamp + signature for secret-based webhook"""
        secret = self.config.get("secret", "")
        if not secret:
            return None

        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{secret}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(
            secret_enc,
            string_to_sign_enc,
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        return f"&timestamp={timestamp}&sign={sign}"

    def _get_webhook_url(self) -> str:
        """Get webhook URL with signature if secret is configured"""
        webhook_url = self.config["webhook_url"]
        signature = self._generate_signature()

        if signature:
            webhook_url = f"{webhook_url}{signature}"

        return webhook_url

    def _build_message(self, event: NotificationEvent) -> dict[str, Any]:
        """Build DingTalk markdown message"""
        from app.services.notification_channels.event_types import EVENT_METADATA

        metadata = EVENT_METADATA.get(event.type, {})
        event_name = metadata.get("name", event.type)

        # Emoji based on severity
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
        }
        emoji = emoji_map.get(event.severity, "ℹ️")

        # Build markdown content
        content = f"## {emoji} {event_name}\n\n"
        content += f"{metadata.get('description', '')}\n\n"
        content += "---\n\n"
        content += f"**严重级别**: {event.severity.upper()}\n\n"
        content += f"**时间**: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        content += f"**来源**: {event.source}\n\n"

        if event.data:
            content += "---\n\n"
            content += "**详细信息**:\n\n"
            for key, value in event.data.items():
                content += f"- **{key}**: {value}\n"

        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"[TAM] {event_name}",
                "text": content,
            },
        }

    async def send(
        self,
        event: NotificationEvent | None = None,
        template_data: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
        subject: str | None = None,
        message: str | None = None,
    ) -> dict | NotificationResult:
        """Send DingTalk notification"""
        if subject and message:
            webhook_url = self._get_webhook_url()

            payload = {
                "msgtype": "text",
                "text": {
                    "content": f"{subject}\n{message}",
                },
            }

            try:
                async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                    response = await client.post(
                        webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                    try:
                        result = await response.json()
                    except TypeError:
                        result = response.json()

                    if result.get("errcode") == 0:
                        return {"success": True}
                    else:
                        return {"success": False, "message": result.get("errmsg", "Unknown error")}
            except Exception as e:
                return {"success": False, "message": str(e)}

        if event is None:
            raise ValueError("Either event or subject is required")

        webhook_url = self._get_webhook_url()
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
                    logger.info(f"DingTalk notification sent: {event.type}")
                    return NotificationResult(
                        success=True,
                        message="Notification sent successfully",
                        channel=self.channel_type,
                        event_id=event.id,
                        recipient=webhook_url[:50] + "...",  # Truncate for logging
                    )
                else:
                    error_msg = result.get("errmsg", "Unknown error")
                    logger.warning(f"DingTalk send failed: {error_msg}")
                    return NotificationResult(
                        success=False,
                        message=f"DingTalk API error: {error_msg}",
                        channel=self.channel_type,
                        event_id=event.id,
                        error_code=str(result.get("errcode")),
                    )

        except httpx.TimeoutException:
            logger.error("DingTalk timeout")
            return NotificationResult(
                success=False,
                message="Request timeout",
                channel=self.channel_type,
                event_id=event.id,
                error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"DingTalk send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False,
                message=f"Send failed: {str(e)}",
                channel=self.channel_type,
                event_id=event.id,
                error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test DingTalk webhook connection"""
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
                "title": "[TAM] 连接测试",
                "text": "## 🔧 连接测试\n\n这是一条测试消息，用于验证钉钉机器人配置是否正确。\n\n> 如果收到此消息，说明配置成功",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._get_webhook_url(),
                    json=test_message,
                    headers={"Content-Type": "application/json"},
                )

                result = response.json()

                if result.get("errcode") == 0:
                    return ChannelTestResult(
                        success=True,
                        message="DingTalk webhook test successful",
                    )
                else:
                    return ChannelTestResult(
                        success=False,
                        message=f"DingTalk API error: {result.get('errmsg', 'Unknown')}",
                    )

        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
            )
