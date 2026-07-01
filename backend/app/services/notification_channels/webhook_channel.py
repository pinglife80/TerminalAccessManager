"""
Webhook Notification Channel for TerminalAccessManager.

Sends notifications to HTTP endpoints with optional signature verification.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from app.services.notification_channels.base import (
    ChannelTestResult,
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
)


class WebhookChannel(NotificationChannelBase):
    """
    Webhook notification channel.

    Sends notifications to HTTP/HTTPS endpoints with configurable
    headers and optional HMAC signature for verification.
    """

    channel_type = "webhook"
    channel_name = "Webhook通知"

    def _validate_config(self) -> None:
        """Validate webhook channel configuration"""
        if "url" not in self.config or not self.config["url"]:
            raise ValueError("Webhook channel requires 'url' configuration")

    def _generate_signature(self, payload: str) -> str:
        """Generate HMAC-SHA256 signature for payload verification"""
        secret = self.config.get("secret", "")
        if not secret:
            return ""

        signature = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return f"sha256={signature}"

    def _prepare_headers(self, payload: str) -> dict[str, str]:
        """Prepare HTTP headers including signature"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "TAM-Notification/1.0",
            "X-TAM-Event": "notification",
        }

        # Add signature if secret is configured
        if self.config.get("secret"):
            signature = self._generate_signature(payload)
            headers["X-TAM-Signature"] = signature

        # Add custom headers
        custom_headers = self.config.get("headers", {})
        if isinstance(custom_headers, dict):
            headers.update(custom_headers)

        return headers

    def _build_payload(self, event: NotificationEvent) -> dict[str, Any]:
        """Build webhook payload"""
        return {
            "event_id": event.id,
            "event_type": event.type,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "severity": event.severity,
            "data": event.data,
            "message": self.format_message(event),
        }

    async def send(
        self,
        event: NotificationEvent | None = None,
        template_data: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
        subject: str | None = None,
        message: str | None = None,
    ) -> dict | NotificationResult:
        """Send webhook notification"""
        if subject and message:
            url = self.config["url"]
            method = self.config.get("method", "POST").upper()

            payload = {
                "event_id": "test",
                "event_type": "custom",
                "timestamp": datetime.utcnow().isoformat(),
                "source": "test",
                "severity": "info",
                "data": {"subject": subject, "message": message},
                "message": message,
            }
            payload_json = json.dumps(payload, ensure_ascii=False)
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "TAM-Notification/1.0",
                "X-TAM-Event": "notification",
            }

            try:
                async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                    if method == "POST":
                        response = await client.post(url, content=payload_json, headers=headers)
                    elif method == "PUT":
                        response = await client.put(url, content=payload_json, headers=headers)
                    else:
                        return {"success": False, "message": f"Unsupported HTTP method: {method}"}

                    if response.status_code < 400:
                        return {"success": True}
                    else:
                        return {"success": False, "message": f"HTTP {response.status_code}"}
            except Exception as e:
                return {"success": False, "message": str(e)}

        if event is None:
            raise ValueError("Either event or subject is required")

        url = self.config["url"]
        method = self.config.get("method", "POST").upper()

        payload = self._build_payload(event)
        payload_json = json.dumps(payload, ensure_ascii=False)
        headers = self._prepare_headers(payload_json)

        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 30)) as client:
                if method == "POST":
                    response = await client.post(url, content=payload_json, headers=headers)
                elif method == "PUT":
                    response = await client.put(url, content=payload_json, headers=headers)
                elif method == "PATCH":
                    response = await client.patch(url, content=payload_json, headers=headers)
                else:
                    return NotificationResult(
                        success=False,
                        message=f"Unsupported HTTP method: {method}",
                        channel=self.channel_type,
                        event_id=event.id,
                        error_code="INVALID_METHOD",
                    )

                if response.status_code < 400:
                    logger.info(f"Webhook sent successfully to {url}: {event.type}")
                    return NotificationResult(
                        success=True,
                        message=f"Webhook sent (HTTP {response.status_code})",
                        channel=self.channel_type,
                        event_id=event.id,
                        recipient=url,
                        details={"status_code": response.status_code},
                    )
                else:
                    logger.warning(f"Webhook returned error {response.status_code}: {response.text[:200]}")
                    return NotificationResult(
                        success=False,
                        message=f"Webhook returned HTTP {response.status_code}",
                        channel=self.channel_type,
                        event_id=event.id,
                        error_code="HTTP_ERROR",
                        details={"status_code": response.status_code, "response": response.text[:200]},
                    )

        except httpx.TimeoutException:
            logger.error(f"Webhook timeout: {url}")
            return NotificationResult(
                success=False,
                message="Request timeout",
                channel=self.channel_type,
                event_id=event.id,
                error_code="TIMEOUT",
            )
        except httpx.ConnectError as e:
            logger.error(f"Webhook connection error: {url} - {e}")
            return NotificationResult(
                success=False,
                message=f"Connection failed: {str(e)}",
                channel=self.channel_type,
                event_id=event.id,
                error_code="CONNECTION_ERROR",
            )
        except Exception as e:
            logger.error(f"Webhook send error: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False,
                message=f"Send failed: {str(e)}",
                channel=self.channel_type,
                event_id=event.id,
                error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test webhook connection with a test payload"""
        url = self.config["url"]

        # We'll just test the connection, not send the full test
        try:
            async with httpx.AsyncClient(timeout=self.config.get("timeout", 10)) as client:
                # Try a HEAD request first to check connectivity
                try:
                    response = await client.head(url)
                    return ChannelTestResult(
                        success=True,
                        message=f"Connection to {url} successful (HTTP {response.status_code})",
                    )
                except httpx.MethodNotAllowed:
                    # HEAD might not be allowed, try a minimal POST
                    pass

                # Send a test POST with minimal payload
                payload = {"test": True, "timestamp": time.time()}
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json", "X-TAM-Test": "true"},
                )

                if response.status_code < 500:
                    return ChannelTestResult(
                        success=True,
                        message=f"Webhook test successful (HTTP {response.status_code})",
                        details={"response": response.text[:100]},
                    )
                else:
                    return ChannelTestResult(
                        success=False,
                        message=f"Webhook returned server error (HTTP {response.status_code})",
                        details={"response": response.text[:100]},
                    )

        except httpx.TimeoutException:
            return ChannelTestResult(
                success=False,
                message=f"Connection timeout to {url}",
            )
        except httpx.ConnectError as e:
            return ChannelTestResult(
                success=False,
                message=f"Cannot connect to {url}: {str(e)}",
            )
        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"Test failed: {str(e)}",
            )
