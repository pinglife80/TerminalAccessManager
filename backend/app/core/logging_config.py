"""
Centralized logging configuration for TerminalAccessManager.

- Uses loguru as the primary logging library
- Intercepts standard library logging to unify output format
- Configures stdout + file output with rotation
- Unified timestamp format with timezone info
- Request-ID auto-injection via format function + ContextVar
- Timezone controlled by TZ config / environment variable
"""
import os
import sys
import logging
from loguru import logger

from app.core.config import settings
from app.middleware.request_id import request_id_ctx


class InterceptHandler(logging.Handler):
    """Intercept standard library logging and forward to loguru.

    This ensures that modules using `logging.getLogger(__name__)`
    (e.g. security.py, crypto.py) produce output through loguru
    with consistent formatting and level control.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller frame to skip InterceptHandler in loguru output
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _log_format(record) -> str:
    """Dynamic format function that injects request_id from ContextVar.

    Using a function (instead of a static format string) allows us to
    read the ContextVar at log-emission time, so every log line within
    a request automatically carries the correct request_id.
    """
    record["extra"].setdefault("request_id", request_id_ctx.get("-"))
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS ZZ}</green> | "
        "<level>{level:<8}</level> | "
        "<blue>{extra[request_id]}</blue> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n"
    )


def setup_logging() -> None:
    """Initialize logging configuration.

    - Set system timezone from TZ config / environment variable
    - Remove default loguru handler
    - Add stdout handler with configured log level
    - Add file handler with rotation (10MB, 30 days retention, gz compression)
    - Intercept standard library logging
    """
    # Set system timezone so loguru ZZ shows the correct offset
    tz = settings.TZ
    os.environ.setdefault("TZ", tz)
    try:
        import time
        time.tzset()
    except AttributeError:
        pass  # Windows doesn't have tzset

    # Remove default loguru handler
    logger.remove()

    # Stdout handler — always enabled
    logger.add(
        sys.stdout,
        format=_log_format,
        level=settings.LOG_LEVEL,
    )

    # File handler — with rotation and retention
    try:
        logger.add(
            "/var/log/tam/app.log",
            format=_log_format,
            level=settings.LOG_LEVEL,
            rotation="10 MB",
            retention="30 days",
            compression="gz",
            backtrace=True,
            diagnose=settings.DEBUG,
        )
    except Exception:
        # If /var/log/tam/ is not writable (e.g. local dev without volume),
        # skip file logging silently
        logger.warning("Log directory /var/log/tam/ not available, file logging disabled")

    # Intercept standard library logging
    # This makes `logging.getLogger(__name__)` output go through loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Reduce noise from third-party libraries
    for noisy_logger in [
        "uvicorn.access",
        "uvicorn.error",
        "sqlalchemy.engine",
        "asyncio",
        "httpx",
        "httpcore",
    ]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    logger.info(f"Logging initialized [level={settings.LOG_LEVEL}]")
