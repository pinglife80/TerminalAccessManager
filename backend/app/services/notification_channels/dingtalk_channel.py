"""
DingTalk (钉钉) Notification Channel for TerminalAccessManager.

Supports two modes:
  1. Webhook robot mode (legacy): sends markdown to a group via webhook_url
     with optional secret signature.
  2. App mode: sends work notifications to specified users/departments via
     DingTalk Open Platform API using app_key + app_secret + agent_id.

App mode config fields:
  - app_key: DingTalk app key
  - app_secret: DingTalk app secret
  - agent_id: DingTalk agent ID
  - userid_list: comma-separated user IDs (optional)
  - dept_id_list: comma-separated department IDs (optional)
  - to_all_user: send to all users (optional, boolean)
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

DINGTALK_TOKEN_URL = "https://oapi.dingtalk.com/gettoken"
DINGTALK_WORK_NOTIFICATION_URL = "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2"
DINGTALK_TOKEN_CACHE_KEY = "dingtalk:access_token:{app_key}"
DINGTALK_TOKEN_TTL = 7000  # DingTalk tokens expire in 7200s


class DingTalkChannel(NotificationChannelBase):
    """
    DingTalk notification channel.

    Supports webhook robot mode and app work notification mode.
    """

    channel_type = "dingtalk"
    channel_name = "钉钉通知"

    def _validate_config(self) -> None:
        """Validate DingTalk channel configuration.

        Accepts either webhook_url (webhook mode) or app_key+app_secret
        (app mode). At least one mode must be configured.
        """
        webhook_url = self.config.get("webhook_url", "")
        app_key = self.config.get("app_key", "")
        app_secret = self.config.get("app_secret", "")

        if not webhook_url and not (app_key and app_secret):
            raise ValueError(
                "DingTalk channel requires either 'webhook_url' or "
                "'app_key'+'app_secret' configuration"
            )

        # When app mode is configured, agent_id is required
        if app_key and app_secret:
            agent_id = self.config.get("agent_id", "")
            if not agent_id:
                raise ValueError("DingTalk app mode requires 'agent_id'")
            # At least one target must be specified
            userid_list = self.config.get("userid_list", "")
            dept_id_list = self.config.get("dept_id_list", "")
            to_all_user = self.config.get("to_all_user", False)
            if not userid_list and not dept_id_list and not to_all_user:
                raise ValueError(
                    "DingTalk app mode requires at least one of "
                    "'userid_list', 'dept_id_list', or 'to_all_user'"
                )

    def _is_app_mode(self) -> bool:
        """Check if this channel is configured in app mode."""
        return bool(self.config.get("app_key") and self.config.get("app_secret"))

    async def _get_access_token(self) -> str:
        """Get DingTalk access_token, cached in Redis."""
        app_key = self.config["app_key"]
        app_secret = self.config["app_secret"]
        cache_key = DINGTALK_TOKEN_CACHE_KEY.format(app_key=app_key)

        from app.core.security import get_redis_client

        redis = await get_redis_client()
        cached_token = await redis.get(cache_key)
        if cached_token:
            return cached_token

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                DINGTALK_TOKEN_URL,
                params={"appkey": app_key, "appsecret": app_secret},
            )
            result = response.json()

        if result.get("errcode") != 0:
            raise RuntimeError(
                f"DingTalk token request failed: {result.get('errmsg', 'Unknown error')}"
            )

        token = result["access_token"]
        await redis.setex(cache_key, DINGTALK_TOKEN_TTL, token)
        return token

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
        """Send DingTalk notification via webhook or app mode"""
        if subject and message:
            text_content = f"{subject}\n{message}"
            if self._is_app_mode():
                return await self._send_app_message(subject, text_content, event)
            return await self._send_webhook_text(text_content)

        if event is None:
            raise ValueError("Either event or subject is required")

        if self._is_app_mode():
            return await self._send_app_event(event)
        return await self._send_webhook_event(event)

    async def _send_webhook_text(self, text: str) -> dict:
        """Send text via webhook (legacy mode)"""
        webhook_url = self._get_webhook_url()
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
        webhook_url = self._get_webhook_url()
        payload = self._build_message(event)
        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"DingTalk notification sent (webhook): {event.type}")
                    return NotificationResult(
                        success=True, message="Notification sent successfully",
                        channel=self.channel_type, event_id=event.id,
                        recipient=webhook_url[:50] + "...",
                    )
                error_msg = result.get("errmsg", "Unknown error")
                logger.warning(f"DingTalk send failed: {error_msg}")
                return NotificationResult(
                    success=False, message=f"DingTalk API error: {error_msg}",
                    channel=self.channel_type, event_id=event.id, error_code=str(result.get("errcode")),
                )
        except httpx.TimeoutException:
            logger.error("DingTalk timeout")
            return NotificationResult(
                success=False, message="Request timeout",
                channel=self.channel_type, event_id=event.id, error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"DingTalk send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False, message=f"Send failed: {str(e)}",
                channel=self.channel_type, event_id=event.id, error_code="SEND_ERROR",
            )

    async def _send_app_message(self, title: str, text: str, event: NotificationEvent | None) -> dict:
        """Send work notification via DingTalk Open Platform API (app mode)"""
        try:
            token = await self._get_access_token()
            agent_id = self.config["agent_id"]
            payload: dict[str, Any] = {
                "agent_id": agent_id,
                "msg": {
                    "msgtype": "markdown",
                    "markdown": {"title": title, "text": text},
                },
            }
            # Add optional target fields
            userid_list = self.config.get("userid_list", "")
            if userid_list:
                payload["userid_list"] = userid_list
            dept_id_list = self.config.get("dept_id_list", "")
            if dept_id_list:
                payload["dept_id_list"] = dept_id_list
            if self.config.get("to_all_user"):
                payload["to_all_user"] = True

            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    DINGTALK_WORK_NOTIFICATION_URL,
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
        """Send event notification via DingTalk Open Platform API (app mode)"""
        try:
            token = await self._get_access_token()
            agent_id = self.config["agent_id"]
            msg_payload = self._build_message(event)
            payload: dict[str, Any] = {
                "agent_id": agent_id,
                "msg": msg_payload,
            }
            userid_list = self.config.get("userid_list", "")
            if userid_list:
                payload["userid_list"] = userid_list
            dept_id_list = self.config.get("dept_id_list", "")
            if dept_id_list:
                payload["dept_id_list"] = dept_id_list
            if self.config.get("to_all_user"):
                payload["to_all_user"] = True

            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                response = await client.post(
                    DINGTALK_WORK_NOTIFICATION_URL,
                    params={"access_token": token},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("errcode") == 0:
                    logger.info(f"DingTalk notification sent (app): {event.type}")
                    targets = []
                    if userid_list:
                        targets.append(f"users:{userid_list}")
                    if dept_id_list:
                        targets.append(f"depts:{dept_id_list}")
                    if self.config.get("to_all_user"):
                        targets.append("all")
                    return NotificationResult(
                        success=True, message="Notification sent successfully",
                        channel=self.channel_type, event_id=event.id,
                        recipient=", ".join(targets) or "app",
                    )
                error_msg = result.get("errmsg", "Unknown error")
                logger.warning(f"DingTalk app send failed: {error_msg}")
                return NotificationResult(
                    success=False, message=f"DingTalk API error: {error_msg}",
                    channel=self.channel_type, event_id=event.id, error_code=str(result.get("errcode")),
                )
        except httpx.TimeoutException:
            logger.error("DingTalk app timeout")
            return NotificationResult(
                success=False, message="Request timeout",
                channel=self.channel_type, event_id=event.id, error_code="TIMEOUT",
            )
        except Exception as e:
            logger.error(f"DingTalk app send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False, message=f"Send failed: {str(e)}",
                channel=self.channel_type, event_id=event.id, error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test DingTalk connection (webhook or app mode)"""
        if self._is_app_mode():
            return await self._test_app()
        return await self._test_webhook()

    async def _test_webhook(self) -> ChannelTestResult:
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

    async def _test_app(self) -> ChannelTestResult:
        """Test DingTalk app mode by sending a test message"""
        try:
            token = await self._get_access_token()
            agent_id = self.config["agent_id"]
            test_text = "## 🔧 连接测试\n\n这是一条测试消息，用于验证钉钉应用配置是否正确。\n\n> 如果收到此消息，说明配置成功"
            payload: dict[str, Any] = {
                "agent_id": agent_id,
                "msg": {
                    "msgtype": "markdown",
                    "markdown": {"title": "[TAM] 连接测试", "text": test_text},
                },
            }
            userid_list = self.config.get("userid_list", "")
            if userid_list:
                payload["userid_list"] = userid_list
            dept_id_list = self.config.get("dept_id_list", "")
            if dept_id_list:
                payload["dept_id_list"] = dept_id_list
            if self.config.get("to_all_user"):
                payload["to_all_user"] = True

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    DINGTALK_WORK_NOTIFICATION_URL,
                    params={"access_token": token},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                if result.get("errcode") == 0:
                    return ChannelTestResult(
                        success=True,
                        message="DingTalk app test successful",
                    )
                return ChannelTestResult(
                    success=False,
                    message=f"DingTalk API error: {result.get('errmsg', 'Unknown')}",
                )
        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"App connection failed: {str(e)}",
            )
