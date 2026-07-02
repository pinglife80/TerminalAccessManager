from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings


def get_timezone() -> ZoneInfo:
    """Get the configured timezone from settings."""
    return ZoneInfo(settings.TZ)


def now() -> datetime:
    """Get current datetime in the configured timezone with timezone info."""
    return datetime.now(get_timezone()).astimezone()


def now_utc() -> datetime:
    """Get current datetime in UTC timezone."""
    return datetime.now(timezone.utc)