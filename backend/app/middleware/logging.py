"""Request logging middleware"""
import time

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.request_id import request_id_ctx


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

        # Extract client IP (prefer X-Forwarded-For for proxied requests)
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "-"

        # Get request_id set by RequestIDMiddleware
        req_id = request_id_ctx.get("-")

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Log request details with client IP and request_id
        logger.info(
            f"{request.method} {request.url.path} "
            f"- {response.status_code} - {duration_ms}ms | ip={client_ip} | req_id={req_id}"
        )

        # Add timing header
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response
