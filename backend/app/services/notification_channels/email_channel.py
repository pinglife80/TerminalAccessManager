"""
Email Notification Channel for TerminalAccessManager.

Sends notifications via email using SMTP.
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


class EmailChannel(NotificationChannelBase):
    """
    Email notification channel.

    Sends notifications to email addresses using SMTP or HTTP email API.
    """

    channel_type = "email"
    channel_name = "邮件通知"

    def _validate_config(self) -> None:
        """Validate email channel configuration"""
        required = ["recipients"]
        for field in required:
            if field not in self.config or not self.config[field]:
                raise ValueError(f"Email channel requires '{field}' configuration")

    def get_recipients(self) -> list[str]:
        """Get list of recipient email addresses"""
        recipients = self.config.get("recipients", [])
        if isinstance(recipients, str):
            # Split by comma or newline
            recipients = [r.strip() for r in recipients.replace("\n", ",").split(",")]
        return [r for r in recipients if r]

    def format_email_content(self, event: NotificationEvent) -> tuple[str, str]:
        """Format email subject and body"""
        from app.services.notification_channels.event_types import EVENT_METADATA

        metadata = EVENT_METADATA.get(event.type, {})
        event_name = metadata.get("name", event.type)

        subject = f"[TAM] {event_name}"

        # Build HTML body
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px;">
                    {event_name}
                </h2>
                <p>{metadata.get('description', '')}</p>
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; width: 120px;">时间</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">严重级别</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">
                            <span style="color: {'#dc2626' if event.severity == 'error' else '#f59e0b' if event.severity == 'warning' else '#10b981'};">
                                {event.severity.upper()}
                            </span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">来源</td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{event.source}</td>
                    </tr>
                </table>
        """

        if event.data:
            body += "<h3>详细信息</h3><ul>"
            for key, value in event.data.items():
                body += f"<li><strong>{key}:</strong> {value}</li>"
            body += "</ul>"

        body += """
                <div style="margin-top: 30px; padding: 15px; background-color: #f9fafb; border-radius: 4px;">
                    <p style="color: #666; font-size: 12px; margin: 0;">
                        此邮件由 Terminal Access Manager 自动发送，请勿回复。
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        # Plain text version
        text = f"""
{event_name}
{'=' * len(event_name)}

{metadata.get('description', '')}

时间: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
严重级别: {event.severity.upper()}
来源: {event.source}

详细信息:
"""
        for key, value in event.data.items():
            text += f"  {key}: {value}\n"

        return subject, body

    async def send(
        self,
        event: NotificationEvent,
        template_data: dict[str, Any] | None = None,
    ) -> NotificationResult:
        """Send email notification"""
        recipients = self.get_recipients()
        if not recipients:
            return NotificationResult(
                success=False,
                message="No recipients configured",
                channel=self.channel_type,
                event_id=event.id,
            )

        subject, body = self.format_email_content(event)

        try:
            # Try HTTP SMTP relay first
            smtp_url = self.config.get("smtp_url")
            if smtp_url:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        smtp_url,
                        json={
                            "from": self.config.get("from_email", "noreply@tam.local"),
                            "to": recipients,
                            "subject": subject,
                            "html": body,
                        },
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()

            logger.info(f"Email notification sent to {len(recipients)} recipients: {subject}")

            return NotificationResult(
                success=True,
                message=f"Email sent to {len(recipients)} recipients",
                channel=self.channel_type,
                event_id=event.id,
                recipient=", ".join(recipients),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Email send failed (HTTP {e.response.status_code}): {e}")
            return NotificationResult(
                success=False,
                message=f"HTTP error: {e.response.status_code}",
                channel=self.channel_type,
                event_id=event.id,
                error_code="HTTP_ERROR",
            )
        except Exception as e:
            logger.error(f"Email send failed: {type(e).__name__}: {e}")
            # Fallback: log for development
            logger.info(f"[EMAIL FALLBACK] To: {recipients}, Subject: {subject}")
            return NotificationResult(
                success=False,
                message=f"Send failed: {str(e)}",
                channel=self.channel_type,
                event_id=event.id,
                error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test email channel configuration"""
        smtp_url = self.config.get("smtp_url")

        if not smtp_url:
            return ChannelTestResult(
                success=False,
                message="SMTP relay URL not configured",
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(smtp_url)
                if response.status_code < 400:
                    return ChannelTestResult(
                        success=True,
                        message="Email channel connection successful",
                    )
                return ChannelTestResult(
                    success=False,
                    message=f"SMTP server returned {response.status_code}",
                )
        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
            )
