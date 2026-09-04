"""
Feishu (飞书) Notification Channel for TerminalAccessManager.

Supports two modes:
  1. Webhook robot mode (legacy): sends card messages to a group via webhook_url.
  2. App mode: sends messages to specified users/groups/departments via Feishu
     Open Platform API using app_id + app_secret.

App mode config fields:
  - app_id: Feishu app ID
  - app_secret: Feishu app secret
  - receive_id_type: open_id | user_id | chat_id | department_id | email
  - receive_id: the target ID corresponding to receive_id_type
"""

from typing import Any

import httpx
from loguru import logger

from .base import format_timestamp
from app.services.notification_channels.base import (
    ChannelTestResult,
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
)

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
FEISHU_TOKEN_CACHE_KEY = "feishu:tenant_access_token:{app_id}"
FEISHU_TOKEN_TTL = 7000  # Feishu tokens expire in 7200s; refresh slightly early


class FeishuChannel(NotificationChannelBase):
    """
    Feishu notification channel.

    Supports webhook robot mode and app message mode.
    """

    channel_type = "feishu"
    channel_name = "飞书通知"

    def _validate_config(self) -> None:
        """Validate Feishu channel configuration.

        Accepts either webhook_url (webhook mode) or app_id+app_secret
        (app mode). At least one mode must be configured.
        """
        webhook_url = self.config.get("webhook_url", "")
        app_id = self.config.get("app_id", "")
        app_secret = self.config.get("app_secret", "")

        if not webhook_url and not (app_id and app_secret):
            raise ValueError(
                "Feishu channel requires either 'webhook_url' or "
                "'app_id'+'app_secret' configuration"
            )

        # When app mode is configured, receive_id_type and receive_id are required
        if app_id and app_secret:
            receive_id_type = self.config.get("receive_id_type", "")
            receive_id = self.config.get("receive_id", "")
            if not receive_id_type or not receive_id:
                raise ValueError(
                    "Feishu app mode requires 'receive_id_type' and 'receive_id'"
                )

    def _is_app_mode(self) -> bool:
        """Check if this channel is configured in app mode."""
        return bool(self.config.get("app_id") and self.config.get("app_secret"))

    async def _get_tenant_access_token(self) -> str:
        """Get Feishu tenant_access_token, cached in Redis.

        Feishu tokens are valid for 2 hours. We cache them in Redis with
        a slightly shorter TTL to avoid edge-case expiry failures.
        """
        app_id = self.config["app_id"]
        app_secret = self.config["app_secret"]
        cache_key = FEISHU_TOKEN_CACHE_KEY.format(app_id=app_id)

        from app.core.security import get_redis_client

        redis = await get_redis_client()
        cached_token = await redis.get(cache_key)
        if cached_token:
            return cached_token

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                FEISHU_TOKEN_URL,
                json={"app_id": app_id, "app_secret": app_secret},
                headers={"Content-Type": "application/json"},
            )
            result = response.json()

        if result.get("code") != 0:
            raise RuntimeError(
                f"Feishu token request failed: {result.get('msg', 'Unknown error')}"
            )

        token = result["tenant_access_token"]
        await redis.setex(cache_key, FEISHU_TOKEN_TTL, token)
        return token

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
                                "content": f"**时间**\n{format_timestamp(event.timestamp)}",
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
        event: NotificationEvent | None = None,
        template_data: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
        subject: str | None = None,
        message: str | None = None,
    ) -> dict | NotificationResult:
        """Send Feishu notification via webhook or app mode"""
        if subject and message:
            text_content = f"{subject}\n{message}"
            if self._is_app_mode():
                res = await self._send_app_text(text_content, event)
            else:
                res = await self._send_webhook_text(text_content, event)
            return NotificationResult(
                success=bool(res.get("success")),
                message=res.get("message", ""),
                channel=self.channel_type,
                event_id=event.id if event else None,
            )

        if event is None:
            raise ValueError("Either event or subject is required")

        if self._is_app_mode():
            return await self._send_app_card(event)
        return await self._send_webhook_card(event)

    async def _send_webhook_text(self, text: str, event: NotificationEvent | None) -> dict:
        """Send text via webhook (legacy mode)"""
        webhook_url = self.config["webhook_url"]
        payload = {"msg_type": "text", "content": {"text": text}}
        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})
                try:
                    result = await response.json()
                except TypeError:
                    result = response.json()
                if result.get("code") == 0 or response.status_code == 200:
                    return {"success": True}
                return {"success": False, "message": result.get("msg", "Unknown error")}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def _send_webhook_card(self, event: NotificationEvent) -> NotificationResult:
        """Send card via webhook (legacy mode)"""
        webhook_url = self.config["webhook_url"]
        payload = self._build_card(event)
        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})
                result = response.json()
                if result.get("code") == 0 or response.status_code == 200:
                    logger.info(f"Feishu notification sent (webhook): {event.type}")
                    return NotificationResult(
                        success=True, message="Notification sent successfully",
                        channel=self.channel_type, event_id=event.id, recipient=webhook_url,
                    )
                error_msg = result.get("msg", "Unknown error")
                logger.warning(f"Feishu send failed: {error_msg}")
                return NotificationResult(
                    success=False, message=f"Feishu API error: {error_msg}",
                    channel=self.channel_type, event_id=event.id, error_code=str(result.get("code")),
                )
        except httpx.TimeoutException:
            logger.error(f"Feishu timeout: {webhook_url}")
            return NotificationResult(
                success=False, message="Request timeout",
                channel=self.channel_type, event_id=event.id, error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"Feishu send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False, message=f"Send failed: {str(e)}",
                channel=self.channel_type, event_id=event.id, error_code="SEND_ERROR",
            )

    async def _send_app_text(self, text: str, event: NotificationEvent | None) -> dict:
        """Send text message via Feishu Open Platform API (app mode)"""
        try:
            token = await self._get_tenant_access_token()
            receive_id_type = self.config["receive_id_type"]
            receive_id = self.config["receive_id"]
            import json
            payload = {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            }
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    FEISHU_MESSAGE_URL,
                    params={"receive_id_type": receive_id_type},
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("code") == 0:
                    return {"success": True}
                return {"success": False, "message": result.get("msg", "Unknown error")}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def _send_app_card(self, event: NotificationEvent) -> NotificationResult:
        """Send interactive card via Feishu Open Platform API (app mode)"""
        try:
            token = await self._get_tenant_access_token()
            receive_id_type = self.config["receive_id_type"]
            receive_id = self.config["receive_id"]
            card_payload = self._build_card(event)
            # The card payload for app API is slightly different: wrap in "content"
            import json
            card_content = card_payload.get("card", card_payload)
            payload = {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card_content),
            }
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    FEISHU_MESSAGE_URL,
                    params={"receive_id_type": receive_id_type},
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("code") == 0:
                    logger.info(f"Feishu notification sent (app): {event.type}")
                    return NotificationResult(
                        success=True, message="Notification sent successfully",
                        channel=self.channel_type, event_id=event.id,
                        recipient=f"{receive_id_type}:{receive_id}",
                    )
                error_msg = result.get("msg", "Unknown error")
                logger.warning(f"Feishu app send failed: {error_msg}")
                return NotificationResult(
                    success=False, message=f"Feishu API error: {error_msg}",
                    channel=self.channel_type, event_id=event.id, error_code=str(result.get("code")),
                )
        except httpx.TimeoutException:
            logger.error("Feishu app timeout")
            return NotificationResult(
                success=False, message="Request timeout",
                channel=self.channel_type, event_id=event.id, error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"Feishu app send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False, message=f"Send failed: {str(e)}",
                channel=self.channel_type, event_id=event.id, error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test Feishu connection (webhook or app mode)"""
        if self._is_app_mode():
            return await self._test_app()
        return await self._test_webhook()

    async def _test_webhook(self) -> ChannelTestResult:
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

    async def _test_app(self) -> ChannelTestResult:
        """Test Feishu app mode by sending a test message"""
        try:
            token = await self._get_tenant_access_token()
            receive_id_type = self.config["receive_id_type"]
            receive_id = self.config["receive_id"]
            import json
            test_text = "[TAM] 连接测试\n这是一条测试消息，用于验证飞书应用配置是否正确。\n如果收到此消息，说明配置成功"
            payload = {
                "receive_id_type": receive_id_type,
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": test_text}),
            }
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    FEISHU_MESSAGE_URL,
                    params={"receive_id_type": receive_id_type},
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("code") == 0:
                    return ChannelTestResult(
                        success=True,
                        message="Feishu app test successful",
                    )
                return ChannelTestResult(
                    success=False,
                    message=f"Feishu API error: {result.get('msg', 'Unknown')}",
                )
        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"App connection failed: {str(e)}",
            )
