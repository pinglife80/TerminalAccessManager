"""Request-ID middleware for distributed tracing across log lines.

Each incoming request is assigned a unique request_id (12-char hex).
If the client sends an X-Request-ID header, that value is reused
(so upstream proxies / load balancers can propagate a trace ID).

The request_id is stored in a ContextVar so that any log line emitted
during request processing automatically includes it via the loguru patcher
configured in logging_config.py.
"""
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ContextVar shared with logging_config.py patcher
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a request_id to every HTTP request and expose it in
    the response header X-Request-ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Prefer client-supplied X-Request-ID (e.g. from a gateway)
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request_id_ctx.set(req_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
