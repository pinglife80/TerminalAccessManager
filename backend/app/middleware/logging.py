"""Request logging middleware"""
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests"""

    # Paths to exclude from logging
    EXCLUDED_PATHS = {"/health", "/metrics"}

    async def dispatch(self, request: Request, call_next):
        """Log request details and response time"""
        # Skip logging for excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Log request details
        logger.info(
            f"{request.method} {request.url.path} "
            f"- {response.status_code} - {duration_ms}ms"
        )

        # Add timing header
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response
