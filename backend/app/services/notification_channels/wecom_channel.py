"""
WeCom (企业微信) Notification Channel for TerminalAccessManager.

Supports two modes:
  1. Webhook robot mode (legacy): sends markdown to a group via webhook_url.
  2. App mode: sends application messages to specified users/departments/tags
     via WeCom Open Platform API using corp_id + agent_id + secret.

App mode config fields:
  - corp_id: WeCom corporation ID
  - agent_id: WeCom application agent ID
  - secret: WeCom application secret
  - touser: user IDs, pipe-separated (optional)
  - toparty: department IDs, pipe-separated (optional)
  - totag: tag IDs, pipe-separated (optional)
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

WECOM_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_MESSAGE_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
WECOM_TOKEN_CACHE_KEY = "wecom:access_token:{corp_id}:{agent_id}"
WECOM_TOKEN_TTL = 7000  # WeCom tokens expire in 7200s


class WeComChannel(NotificationChannelBase):
    """
    WeCom (企业微信) notification channel.

    Supports webhook robot mode and app message mode.
    """

    channel_type = "wecom"
    channel_name = "企业微信通知"

    def _validate_config(self) -> None:
        """Validate WeCom channel configuration.

        Accepts either webhook_url (webhook mode) or corp_id+secret+agent_id
        (app mode). At least one mode must be configured.
        """
        webhook_url = self.config.get("webhook_url", "")
        corp_id = self.config.get("corp_id", "")
        secret = self.config.get("secret", "")
        agent_id = self.config.get("agent_id", "")

        if not webhook_url and not (corp_id and secret and agent_id):
            raise ValueError(
                "WeCom channel requires either 'webhook_url' or "
                "'corp_id'+'secret'+'agent_id' configuration"
            )

        # When app mode is configured, at least one target is required
        if corp_id and secret and agent_id:
            touser = self.config.get("touser", "")
            toparty = self.config.get("toparty", "")
            totag = self.config.get("totag", "")
            if not touser and not toparty and not totag:
                raise ValueError(
                    "WeCom app mode requires at least one of "
                    "'touser', 'toparty', or 'totag'"
                )

    def _is_app_mode(self) -> bool:
        """Check if this channel is configured in app mode."""
        return bool(
            self.config.get("corp_id")
            and self.config.get("secret")
            and self.config.get("agent_id")
        )

    async def _get_access_token(self) -> str:
        """Get WeCom access_token, cached in Redis.

        WeCom tokens are valid for 2 hours. We cache them in Redis with
        a slightly shorter TTL to avoid edge-case expiry failures.
        """
        corp_id = self.config["corp_id"]
        secret = self.config["secret"]
        agent_id = self.config["agent_id"]
        cache_key = WECOM_TOKEN_CACHE_KEY.format(corp_id=corp_id, agent_id=agent_id)

        from app.core.security import get_redis_client

        redis = await get_redis_client()
        cached_token = await redis.get(cache_key)
        if cached_token:
            return cached_token

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                WECOM_TOKEN_URL,
                params={"corpid": corp_id, "corpsecret": secret},
            )
            result = response.json()

        if result.get("errcode") != 0:
            raise RuntimeError(
                f"WeCom token request failed: {result.get('errmsg', 'Unknown error')}"
            )

        token = result["access_token"]
        await redis.setex(cache_key, WECOM_TOKEN_TTL, token)
        return token

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
        event: NotificationEvent | None = None,
        template_data: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
        subject: str | None = None,
        message: str | None = None,
    ) -> dict | NotificationResult:
        """Send WeCom notification via webhook or app mode"""
        if subject and message:
            text_content = f"{subject}\n{message}"
            if self._is_app_mode():
                return await self._send_app_text(text_content, event)
            return await self._send_webhook_text(text_content)

        if event is None:
            raise ValueError("Either event or subject is required")

        if self._is_app_mode():
            return await self._send_app_event(event)
        return await self._send_webhook_event(event)

    async def _send_webhook_text(self, text: str) -> dict:
        """Send text via webhook (legacy mode)"""
        webhook_url = self.config["webhook_url"]
        payload = {"msgtype": "text", "text": {"content": text}}
        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})
                try:
                    result = await response.json()
                except TypeError:
                    result = response.json()
                if result.get("errcode") == 0:
                    return {"success": True}
                return {"success": False, "message": result.get("errmsg", "Unknown error")}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def _send_webhook_event(self, event: NotificationEvent) -> NotificationResult:
        """Send markdown via webhook (legacy mode)"""
        webhook_url = self.config["webhook_url"]
        payload = self._build_message(event)
        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"WeCom notification sent (webhook): {event.type}")
                    return NotificationResult(
                        success=True, message="Notification sent successfully",
                        channel=self.channel_type, event_id=event.id,
                        recipient=webhook_url[:50] + "...",
                    )
                error_msg = result.get("errmsg", "Unknown error")
                logger.warning(f"WeCom send failed: {error_msg}")
                return NotificationResult(
                    success=False, message=f"WeCom API error: {error_msg}",
                    channel=self.channel_type, event_id=event.id, error_code=str(result.get("errcode")),
                )
        except httpx.TimeoutException:
            logger.error("WeCom timeout")
            return NotificationResult(
                success=False, message="Request timeout",
                channel=self.channel_type, event_id=event.id, error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"WeCom send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False, message=f"Send failed: {str(e)}",
                channel=self.channel_type, event_id=event.id, error_code="SEND_ERROR",
            )

    def _build_app_payload(self, msg_content: dict[str, Any]) -> dict[str, Any]:
        """Build WeCom app message payload with target fields."""
        payload: dict[str, Any] = {
            "msgtype": msg_content.get("msgtype", "markdown"),
            "agentid": self.config["agent_id"],
        }
        # Add message body based on msgtype
        if payload["msgtype"] == "markdown":
            payload["markdown"] = msg_content.get("markdown", {"content": ""})
        elif payload["msgtype"] == "text":
            payload["text"] = msg_content.get("text", {"content": ""})

        # Add target fields (at least one required)
        touser = self.config.get("touser", "")
        if touser:
            payload["touser"] = touser
        toparty = self.config.get("toparty", "")
        if toparty:
            payload["toparty"] = toparty
        totag = self.config.get("totag", "")
        if totag:
            payload["totag"] = totag
        return payload

    async def _send_app_text(self, text: str, event: NotificationEvent | None) -> dict:
        """Send text message via WeCom Open Platform API (app mode)"""
        try:
            token = await self._get_access_token()
            msg_content = {"msgtype": "text", "text": {"content": text}}
            payload = self._build_app_payload(msg_content)
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    WECOM_MESSAGE_URL,
                    params={"access_token": token},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("errcode") == 0:
                    return {"success": True}
                return {"success": False, "message": result.get("errmsg", "Unknown error")}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def _send_app_event(self, event: NotificationEvent) -> NotificationResult:
        """Send event notification via WeCom Open Platform API (app mode)"""
        try:
            token = await self._get_access_token()
            msg_content = self._build_message(event)
            payload = self._build_app_payload(msg_content)
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    WECOM_MESSAGE_URL,
                    params={"access_token": token},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"WeCom notification sent (app): {event.type}")
                    targets = []
                    if self.config.get("touser"):
                        targets.append(f"users:{self.config['touser']}")
                    if self.config.get("toparty"):
                        targets.append(f"depts:{self.config['toparty']}")
                    if self.config.get("totag"):
                        targets.append(f"tags:{self.config['totag']}")
                    return NotificationResult(
                        success=True, message="Notification sent successfully",
                        channel=self.channel_type, event_id=event.id,
                        recipient=", ".join(targets) or "app",
                    )
                error_msg = result.get("errmsg", "Unknown error")
                logger.warning(f"WeCom app send failed: {error_msg}")
                return NotificationResult(
                    success=False, message=f"WeCom API error: {error_msg}",
                    channel=self.channel_type, event_id=event.id, error_code=str(result.get("errcode")),
                )
        except httpx.TimeoutException:
            logger.error("WeCom app timeout")
            return NotificationResult(
                success=False, message="Request timeout",
                channel=self.channel_type, event_id=event.id, error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"WeCom app send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False, message=f"Send failed: {str(e)}",
                channel=self.channel_type, event_id=event.id, error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test WeCom connection (webhook or app mode)"""
        if self._is_app_mode():
            return await self._test_app()
        return await self._test_webhook()

    async def _test_webhook(self) -> ChannelTestResult:
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

    async def _test_app(self) -> ChannelTestResult:
        """Test WeCom app mode by sending a test message"""
        try:
            token = await self._get_access_token()
            test_text = "### 🔧 连接测试\n\n这是一条测试消息，用于验证企业微信应用配置是否正确。\n\n> 如果收到此消息，说明配置成功"
            msg_content = {"msgtype": "markdown", "markdown": {"content": test_text}}
            payload = self._build_app_payload(msg_content)
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    WECOM_MESSAGE_URL,
                    params={"access_token": token},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("errcode") == 0:
                    return ChannelTestResult(
                        success=True,
                        message="WeCom app test successful",
                    )
                return ChannelTestResult(
                    success=False,
                    message=f"WeCom API error: {result.get('errmsg', 'Unknown')}",
                )
        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"App connection failed: {str(e)}",
            )
