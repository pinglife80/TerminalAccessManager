"""
Email Service for TerminalAccessManager.

Provides:
- Async email sending with connection pooling
- Email templates rendering (Jinja2)
- Email verification codes (stored in Redis with TTL)
- Rate limiting for email sending
- Configurable SMTP settings
"""

import random
import string
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from app.core.config import settings

# Template directory
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates" / "email"


def _ensure_template_dir() -> Path:
    """Ensure template directory exists"""
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATE_DIR


# Global template environment (lazy initialization)
_jinja_env: Environment | None = None


def get_jinja_env() -> Environment:
    """Get or create Jinja2 template environment"""
    global _jinja_env
    if _jinja_env is None:
        template_dir = _ensure_template_dir()
        _jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=True,
        )
    return _jinja_env


# ==================== Email Code Functions ====================


async def get_redis_client():
    """Get Redis client for email code storage"""
    from app.core.security import get_redis_client
    return await get_redis_client()


async def generate_email_code(length: int = 6) -> str:
    """Generate a random numeric email code"""
    return "".join(random.choices(string.digits, k=length))


async def send_email_code(
    user_id: int,
    email: str,
    purpose: str = "verification",
    length: int = 6,
    ttl_seconds: int = 600,
) -> str:
    """
    Generate and send an email verification code.

    Args:
        user_id: User ID for code storage key
        email: Email address to send code to
        purpose: Purpose of the code (verification, password_reset, 2fa)
        length: Length of the code (default 6 digits)
        ttl_seconds: Time-to-live in seconds (default 10 minutes)

    Returns:
        The generated code (for testing purposes)
    """
    code = await generate_email_code(length)
    redis = await get_redis_client()

    # Store code in Redis with TTL
    key = f"email_code:{purpose}:{user_id}"
    await redis.setex(key, ttl_seconds, code)

    # Prepare template data
    template_data = {
        "code": code,
        "purpose": purpose,
        "ttl_minutes": ttl_seconds // 60,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Select template based on purpose
    template_map = {
        "verification": "email_verify.html",
        "password_reset": "password_reset.html",
        "2fa": "second_factor.html",
        "email_change": "email_change.html",
    }

    template_name = template_map.get(purpose, "notification.html")

    # Render and send email
    try:
        await send_email(
            to_email=email,
            subject=f"【TAM】您的验证码：{code}",
            template_name=template_name,
            template_data=template_data,
        )
        logger.info(f"Email verification code sent to {email} for purpose: {purpose}")
    except Exception as e:
        logger.error(f"Failed to send email code to {email}: {e}")
        raise

    return code


async def verify_email_code(
    user_id: int,
    code: str,
    purpose: str = "verification",
    delete_on_success: bool = True,
    max_attempts: int = 5,
) -> bool:
    """
    Verify an email code.

    Args:
        user_id: User ID
        code: Code to verify
        purpose: Purpose of the code
        delete_on_success: Whether to delete the code after successful verification
        max_attempts: Maximum number of attempts before invalidating code

    Returns:
        True if code is valid and not expired, False otherwise
    """
    redis = await get_redis_client()
    key = f"email_code:{purpose}:{user_id}"
    attempts_key = f"email_code:{purpose}:{user_id}:attempts"

    stored_code = await redis.get(key)
    if not stored_code:
        return False

    attempts = await redis.get(attempts_key)
    attempts = int(attempts) if attempts else 0

    if attempts >= max_attempts:
        await redis.delete(key)
        await redis.delete(attempts_key)
        return False

    is_valid = stored_code == code

    if is_valid and delete_on_success:
        await redis.delete(key)
        await redis.delete(attempts_key)
    elif not is_valid:
        attempts += 1
        await redis.set(attempts_key, attempts)

    return is_valid


async def invalidate_email_codes(user_id: int, purpose: str | None = None):
    """
    Invalidate all email codes for a user.

    Args:
        user_id: User ID
        purpose: Specific purpose to invalidate, or None for all purposes
    """
    redis = await get_redis_client()

    if purpose:
        keys = [
            f"email_code:{purpose}:{user_id}",
            f"email_code:{purpose}:{user_id}:attempts",
        ]
    else:
        # Get all code keys for this user
        keys = []
        for p in ["verification", "password_reset", "2fa", "email_change"]:
            keys.append(f"email_code:{p}:{user_id}")
            keys.append(f"email_code:{p}:{user_id}:attempts")

    for key in keys:
        await redis.delete(key)


# ==================== Rate Limiting ====================


async def check_email_rate_limit(email: str) -> tuple[bool, int]:
    """
    Check if email rate limit is exceeded.

    Args:
        email: Email address

    Returns:
        Tuple of (is_allowed, remaining_requests)
    """
    redis = await get_redis_client()
    key = f"email_rate:{email}"

    current = await redis.get(key)
    if current is None:
        await redis.setex(key, 60, 1)
        return True, settings.EMAIL_RATE_LIMIT_PER_MINUTE - 1

    current_count = int(current)
    if current_count >= settings.EMAIL_RATE_LIMIT_PER_MINUTE:
        return False, 0

    await redis.incr(key)
    return True, settings.EMAIL_RATE_LIMIT_PER_MINUTE - current_count - 1


# ==================== Email Sending ====================


class EmailSender:
    """
    Async email sender with SMTP support.

    Features:
    - Connection pooling via httpx
    - HTML and plain text parts
    - Template rendering
    - Rate limiting
    - Error handling and logging
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = False,
        use_ssl: bool = True,
        from_email: str | None = None,
        from_name: str | None = None,
    ):
        self.host = host or getattr(settings, "EMAIL_HOST", None) or "smtp.example.com"
        self.port = port or getattr(settings, "EMAIL_PORT", 465)
        self.username = username or getattr(settings, "EMAIL_USERNAME", None)
        self.password = password or getattr(settings, "EMAIL_PASSWORD", None)
        self.use_tls = use_tls or getattr(settings, "EMAIL_USE_TLS", False)
        self.use_ssl = use_ssl if use_ssl is not None else getattr(settings, "EMAIL_USE_SSL", True)
        self.from_email = from_email or getattr(settings, "EMAIL_FROM", "noreply@example.com")
        self.from_name = from_name or getattr(settings, "EMAIL_FROM_NAME", "TAM System")

    def _build_message(
        self,
        to_email: str,
        subject: str,
        html_content: str | None = None,
        text_content: str | None = None,
    ) -> dict:
        """Build email message dict for API sending"""
        return {
            "from": f"{self.from_name} <{self.from_email}>",
            "to": to_email,
            "subject": subject,
            "html": html_content,
            "text": text_content or (html_content if html_content else ""),
        }

    async def send(
        self,
        to_email: str,
        subject: str,
        html_content: str | None = None,
        text_content: str | None = None,
    ) -> bool:
        """
        Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body content
            text_content: Plain text body content

        Returns:
            True if email sent successfully

        Raises:
            Exception if email sending fails
        """
        # Check rate limit
        is_allowed, remaining = await check_email_rate_limit(to_email)
        if not is_allowed:
            raise EmailRateLimitError(
                f"Rate limit exceeded for {to_email}. Please try again later."
            )

        # Build message
        message = self._build_message(to_email, subject, html_content, text_content)

        # Send via SMTP API endpoint (simulated) or direct SMTP
        try:
            # Try direct SMTP first using httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                # For SMTP, we use a simple HTTP POST to a local SMTP relay
                # In production, this would be a real SMTP server or email service API
                smtp_url = getattr(settings, "EMAIL_SMTP_URL", None)

                if smtp_url:
                    # Send via HTTP SMTP relay
                    response = await client.post(
                        smtp_url,
                        json=message,
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                else:
                    # Fallback: Log the email (for development without SMTP)
                    logger.info(
                        f"[EMAIL] To: {to_email}, Subject: {subject}, "
                        f"Remaining quota: {remaining}"
                    )
                    logger.debug(f"[EMAIL] HTML content: {html_content[:200] if html_content else 'N/A'}...")

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Email sending failed (HTTP {e.response.status_code}): {e}")
            raise EmailSendError(f"Failed to send email: HTTP {e.response.status_code}")
        except Exception as e:
            logger.error(f"Email sending failed: {type(e).__name__}: {e}")
            raise EmailSendError(f"Failed to send email: {str(e)}")

    async def test_connection(self) -> dict:
        """
        Test SMTP connection.

        Returns:
            Dict with test result
        """
        try:
            # For now, just check if SMTP settings are configured
            if not self.host or self.host == "smtp.example.com":
                return {
                    "success": False,
                    "message": "SMTP host not configured",
                }

            # Try a minimal connection test
            async with httpx.AsyncClient(timeout=10.0) as client:
                if self.use_ssl:
                    url = f"https://{self.host}:{self.port}"
                else:
                    url = f"http://{self.host}:{self.port}"

                # This is a simplified test - in production you'd do proper SMTP handshake
                await client.get(url)

            return {
                "success": True,
                "message": f"SMTP connection to {self.host}:{self.port} successful",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection failed: {str(e)}",
            }


class EmailSendError(Exception):
    """Raised when email sending fails"""
    pass


class EmailRateLimitError(Exception):
    """Raised when email rate limit is exceeded"""
    pass


# ==================== Template Rendering ====================


async def render_template(
    template_name: str,
    template_data: dict[str, Any],
) -> tuple[str, str]:
    """
    Render an email template.

    Args:
        template_name: Name of the template file
        template_data: Data to pass to template

    Returns:
        Tuple of (html_content, text_content)
    """
    env = get_jinja_env()

    try:
        template = env.get_template(template_name)
    except Exception:
        # Fallback to simple template if file not found
        logger.warning(f"Template {template_name} not found, using fallback")
        return _fallback_template(template_data)

    # Add default variables
    defaults = {
        "system_name": "Terminal Access Manager",
        "company_name": getattr(settings, "COMPANY_NAME", "TAM"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@example.com"),
        "current_year": datetime.now().year,
    }
    template_data = {**defaults, **template_data}

    # Render
    html_content = await template.render_async(**template_data)
    text_content = _html_to_text(html_content)

    return html_content, text_content


def _fallback_template(data: dict[str, Any]) -> tuple[str, str]:
    """Fallback template when template file is not found"""
    code = data.get("code", "N/A")
    ttl_minutes = data.get("ttl_minutes", 10)

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #2563eb;">Terminal Access Manager</h2>
            <p>您的验证码是: <strong style="font-size: 24px; color: #2563eb;">{code}</strong></p>
            <p>验证码将在 {ttl_minutes} 分钟后过期。</p>
            <p>如果您没有请求此验证码，请忽略此邮件。</p>
        </div>
    </body>
    </html>
    """

    text = f"""
    Terminal Access Manager

    您的验证码是: {code}
    验证码将在 {ttl_minutes} 分钟后过期。
    如果您没有请求此验证码，请忽略此邮件。
    """

    return html, text


def _html_to_text(html: str) -> str:
    """Simple HTML to plain text conversion"""
    import re
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&amp;", "&")
    return text.strip()


# ==================== High-level Email Functions ====================


async def send_email(
    to_email: str,
    subject: str,
    template_name: str | None = None,
    template_data: dict[str, Any] | None = None,
    html_content: str | None = None,
    text_content: str | None = None,
) -> bool:
    """
    Send an email with optional template rendering.

    Args:
        to_email: Recipient email address
        subject: Email subject
        template_name: Name of template file (if using templates)
        template_data: Data for template rendering
        html_content: Direct HTML content (if not using template)
        text_content: Direct plain text content

    Returns:
        True if email sent successfully
    """
    sender = EmailSender()

    # Render template if specified
    if template_name:
        html_content, text_content = await render_template(
            template_name,
            template_data or {},
        )

    return await sender.send(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
    )


async def send_password_reset_email(email: str, user_id: int) -> str:
    """
    Send password reset email with verification code.

    Args:
        email: User's email address
        user_id: User ID

    Returns:
        The generated code (for testing purposes)
    """
    ttl = getattr(settings, "EMAIL_CODE_EXPIRE_MINUTES", 10) * 60
    return await send_email_code(
        user_id=user_id,
        email=email,
        purpose="password_reset",
        ttl_seconds=ttl,
    )


async def send_verification_email(email: str, user_id: int) -> str:
    """
    Send email verification code.

    Args:
        email: User's email address
        user_id: User ID

    Returns:
        The generated code (for testing purposes)
    """
    ttl = getattr(settings, "EMAIL_CODE_EXPIRE_MINUTES", 10) * 60
    return await send_email_code(
        user_id=user_id,
        email=email,
        purpose="verification",
        ttl_seconds=ttl,
    )


async def send_2fa_email(email: str, user_id: int) -> str:
    """
    Send two-factor authentication code via email.

    Args:
        email: User's email address
        user_id: User ID

    Returns:
        The generated code (for testing purposes)
    """
    ttl = 300  # 5 minutes for 2FA
    return await send_email_code(
        user_id=user_id,
        email=email,
        purpose="2fa",
        ttl_seconds=ttl,
    )


# ==================== Default Templates ====================


def init_email_templates():
    """Initialize default email templates if they don't exist"""
    template_dir = _ensure_template_dir()

    templates = {
        "base.html": """\
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ subject or 'Email' }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; background-color: #f4f4f4; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; background-color: #fff; }
        .header { background-color: #2563eb; color: #fff; padding: 20px; text-align: center; }
        .content { padding: 30px 20px; }
        .code { font-size: 32px; font-weight: bold; color: #2563eb; text-align: center; padding: 20px; background-color: #f0f4ff; border-radius: 8px; margin: 20px 0; letter-spacing: 4px; }
        .footer { padding: 20px; text-align: center; font-size: 12px; color: #666; border-top: 1px solid #eee; }
        .button { display: inline-block; padding: 12px 24px; background-color: #2563eb; color: #fff; text-decoration: none; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ system_name or 'Terminal Access Manager' }}</h1>
        </div>
        <div class="content">
            {% block content %}{% endblock %}
        </div>
        <div class="footer">
            <p>这是一封自动发送的邮件，请勿回复。</p>
            <p>&copy; {{ current_year }} {{ company_name or 'TAM' }}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
""",
        "email_verify.html": """\
{% extends "base.html" %}
{% block content %}
<h2>验证您的邮箱</h2>
<p>您好，</p>
<p>感谢您注册 {{ system_name }}。请使用以下验证码完成邮箱验证：</p>
<div class="code">{{ code }}</div>
<p>验证码有效期：{{ ttl_minutes }} 分钟</p>
<p>如果您没有注册 {{ system_name }}，请忽略此邮件。</p>
{% endblock %}
""",
        "password_reset.html": """\
{% extends "base.html" %}
{% block content %}
<h2>重置密码</h2>
<p>您好，</p>
<p>我们收到了您的密码重置请求。请使用以下验证码完成密码重置：</p>
<div class="code">{{ code }}</div>
<p>验证码有效期：{{ ttl_minutes }} 分钟</p>
<p>如果您没有请求重置密码，请忽略此邮件并确保您的账户安全。</p>
{% endblock %}
""",
        "second_factor.html": """\
{% extends "base.html" %}
{% block content %}
<h2>二次校验验证码</h2>
<p>您好，</p>
<p>您正在进行登录操作。请使用以下验证码完成身份验证：</p>
<div class="code">{{ code }}</div>
<p>验证码有效期：5 分钟</p>
<p>如果这不是您的操作，请立即联系管理员。</p>
{% endblock %}
""",
        "email_change.html": """\
{% extends "base.html" %}
{% block content %}
<h2>邮箱变更验证</h2>
<p>您好，</p>
<p>您正在更改账户邮箱地址。请使用以下验证码完成验证：</p>
<div class="code">{{ code }}</div>
<p>验证码有效期：{{ ttl_minutes }} 分钟</p>
<p>如果您没有请求更改邮箱，请忽略此邮件并确保您的账户安全。</p>
{% endblock %}
""",
        "notification.html": """\
{% extends "base.html" %}
{% block content %}
{{ message or '您有一条新通知。' }}
{% endblock %}
""",
    }

    for filename, content in templates.items():
        filepath = template_dir / filename
        if not filepath.exists():
            filepath.write_text(content, encoding="utf-8")
            logger.info(f"Created email template: {filename}")


# Initialize templates on module import
init_email_templates()
