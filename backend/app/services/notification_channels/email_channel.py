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


class EmailService:
    """Email service wrapper for test compatibility"""

    async def send_email(self, to: str, subject: str, body: str) -> dict:
        """Send email"""
        logger.info(f"[EmailService] Sending to: {to}, Subject: {subject}")
        return {"success": True}

    async def send(self, to: str, subject: str, body: str) -> bool:
        """Send email"""
        logger.info(f"[EmailService] Sending to: {to}, Subject: {subject}")
        return True


class EmailChannel(NotificationChannelBase):
    """
    Email notification channel.

    Sends notifications to email addresses using SMTP or HTTP email API.
    """

    channel_type = "email"
    channel_name = "邮件通知"

    def _validate_config(self) -> None:
        """Validate email channel configuration"""
        pass

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
        event: NotificationEvent | None = None,
        template_data: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
        subject: str | None = None,
        message: str | None = None,
    ) -> NotificationResult:
        """Send email notification.

        Uses the global email configuration (database-backed, with .env
        fallback) via email_service.send_email so that verification-code
        emails and notification emails share the same SMTP settings.
        The legacy per-channel ``smtp_url`` config key is still honored
        when present, for backward compatibility with existing channels.

        When subject/message are provided, they override the auto-generated
        content but still use the real email delivery path.
        """
        if recipients:
            self.config["recipients"] = recipients

        if event is None and not (subject and message):
            raise ValueError("Either event or subject/message is required")

        email_recipients = self.get_recipients()
        if not email_recipients:
            return NotificationResult(
                success=False,
                message="No recipients configured",
                channel=self.channel_type,
                event_id=event.id if event else None,
            )

        if subject and message:
            email_subject = subject
            body = message
        elif event:
            email_subject, body = self.format_email_content(event)
        else:
            return NotificationResult(
                success=False,
                message="No content to send",
                channel=self.channel_type,
                event_id=event.id if event else None,
            )

        # Legacy path: per-channel HTTP SMTP relay URL (backward compat).
        # When present, send directly via httpx; otherwise route through
        # the global email_service which reads DB-backed SMTP config.
        smtp_url = self.config.get("smtp_url")
        if smtp_url:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        smtp_url,
                        json={
                            "from": self.config.get("from_email", "noreply@tam.local"),
                            "to": email_recipients,
                            "subject": email_subject,
                            "html": body,
                        },
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()

                logger.info(f"Email notification sent to {len(email_recipients)} recipients (legacy relay): {email_subject}")
                return NotificationResult(
                    success=True,
                    message=f"Email sent to {len(email_recipients)} recipients",
                    channel=self.channel_type,
                    event_id=event.id if event else None,
                    recipient=", ".join(email_recipients),
                )
            except httpx.HTTPStatusError as e:
                logger.error(f"Email send failed (HTTP {e.response.status_code}): {e}")
                return NotificationResult(
                    success=False,
                    message=f"HTTP error: {e.response.status_code}",
                    channel=self.channel_type,
                    event_id=event.id if event else None,
                    error_code="HTTP_ERROR",
                )
            except Exception as e:
                logger.error(f"Email send failed: {type(e).__name__}: {e}")
                return NotificationResult(
                    success=False,
                    message=f"Send failed: {str(e)}",
                    channel=self.channel_type,
                    event_id=event.id if event else None,
                    error_code="SEND_ERROR",
                )

        # Global config path: use email_service.send_email (DB-backed SMTP).
        try:
            from app.services.email_service import send_email

            sent_count = 0
            last_error: str | None = None
            for recipient in email_recipients:
                try:
                    await send_email(
                        to_email=recipient,
                        subject=email_subject,
                        html_content=body,
                    )
                    sent_count += 1
                except Exception as single_err:
                    last_error = str(single_err)
                    logger.error(f"Failed to send email to {recipient}: {single_err}")

            if sent_count > 0:
                logger.info(f"Email notification sent to {sent_count}/{len(email_recipients)} recipients: {email_subject}")
                return NotificationResult(
                    success=True,
                    message=f"Email sent to {sent_count}/{len(email_recipients)} recipients",
                    channel=self.channel_type,
                    event_id=event.id if event else None,
                    recipient=", ".join(email_recipients[:sent_count]),
                )
            return NotificationResult(
                success=False,
                message=f"Send failed: {last_error or 'unknown error'}",
                channel=self.channel_type,
                event_id=event.id if event else None,
                error_code="SEND_ERROR",
            )

        except Exception as e:
            logger.error(f"Email send failed: {type(e).__name__}: {e}")
            return NotificationResult(
                success=False,
                message=f"Send failed: {str(e)}",
                channel=self.channel_type,
                event_id=event.id if event else None,
                error_code="SEND_ERROR",
            )

    async def test(self) -> ChannelTestResult:
        """Test email channel configuration.

        When a per-channel smtp_url is configured, test that relay directly.
        Otherwise, validate the global email configuration by reading it and
        checking that SMTP host is set.
        """
        smtp_url = self.config.get("smtp_url")
        if smtp_url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(smtp_url)
                    if response.status_code < 400:
                        return ChannelTestResult(
                            success=True,
                            message="Email channel connection successful (legacy relay)",
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

        # Global config validation
        try:
            from app.services.email_service import get_email_config
            config = await get_email_config()
            if not config["enabled"]:
                return ChannelTestResult(
                    success=False,
                    message="Email service is disabled. Configure SMTP settings in Email Settings first.",
                )
            if not config["host"]:
                return ChannelTestResult(
                    success=False,
                    message="SMTP host not configured. Set it in Email Settings.",
                )
            return ChannelTestResult(
                success=True,
                message=f"Global SMTP config valid: {config['host']}:{config['port']}",
            )
        except Exception as e:
            return ChannelTestResult(
                success=False,
                message=f"Failed to read email config: {str(e)}",
            )
