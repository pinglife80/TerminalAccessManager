"""Global exception handler middleware for consistent error responses"""
import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTPException — preserve existing detail format (pass-through).

    Business endpoints return structured detail like:
        {"detail": {"message": "...", "captcha_required": True}}
    This handler preserves that format without modification.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers or {},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle RequestValidationError — keep FastAPI's default 422 format.

    Frontend relies on the standard validation error structure for form fields.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all uncaught exceptions — return unified format with error_id for tracing.

    This ensures that unexpected errors (bugs, external service failures, etc.)
    return a consistent JSON response instead of Starlette's plain text.
    The error_id links the response to the server log for debugging.
    """
    error_id = str(uuid.uuid4())[:8]
    logger.error(
        f"Unhandled exception [{error_id}]: {type(exc).__name__}: {exc} "
        f"| {request.method} {request.url.path}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "message": "Internal server error",
                "error_id": error_id,
            }
        },
    )
