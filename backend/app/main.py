from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys

from app.core.config import settings
from app.core.database import init_db
from app.api.v1.api import api_router
from app.core.security import close_redis_client
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.logging import RequestLoggingMiddleware


# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.LOG_LEVEL
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Terminal Network Access Manager...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down Terminal Network Access Manager...")

    # Close Redis connections
    await close_redis_client()
    logger.info("Redis connections closed")


# Determine API docs visibility based on environment
docs_url = f"{settings.API_V1_STR}/docs" if settings.ENVIRONMENT != "production" else None
redoc_url = f"{settings.API_V1_STR}/redoc" if settings.ENVIRONMENT != "production" else None

# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A secure platform for managing network terminals and access control",
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.ENVIRONMENT != "production" else None,
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Configure CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
async def health_check():
    """Health check endpoint with dependency verification"""
    from sqlalchemy import text
    from app.core.database import engine
    import redis.asyncio as aioredis

    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "db": "ok",
        "redis": "ok"
    }

    # Check database connection
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        health_status["db"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Redis connection
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    status_code = 200 if health_status["status"] == "healthy" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=health_status, status_code=status_code)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION
    }


# Prometheus monitoring (optional)
if settings.ENVIRONMENT != "production" or True:  # Enable in all environments
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app)
        logger.info("Prometheus metrics enabled at /metrics")
    except ImportError:
        logger.warning("prometheus-fastapi-instrumentator not installed, metrics disabled")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
