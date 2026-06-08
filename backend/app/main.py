from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import sys
import asyncio

from app.core.config import settings
from app.core.database import init_db, async_session_factory
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


async def _is_task_paused(task_name: str) -> bool:
    """Check if a scheduler task is paused via Redis control key"""
    try:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        ctrl_key = f"scheduler:ctrl:{task_name}"
        val = await redis_client.get(ctrl_key)
        return val == b"paused" or val == "paused"
    except Exception:
        return False


async def _get_scheduler_interval(key: str, default: int) -> int:
    """Get scheduler interval from config, clamped to 30-86400 seconds"""
    try:
        async with async_session_factory() as db:
            from app.services.config_service import ConfigService
            config_service = ConfigService(db)
            value = await config_service.get_value(key)
            if value is not None:
                interval = int(value)
                return max(30, min(86400, interval))
    except Exception:
        pass
    return default


async def cleanup_expired_blacklist():
    """Background task to periodically clean up expired blacklist entries"""
    while True:
        interval = await _get_scheduler_interval("scheduler_firewall_query_interval", 3600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("firewall_query"):
                continue
            async with async_session_factory() as db:
                from app.services.terminal_service import TerminalService
                service = TerminalService(db)
                count = await service.cleanup_expired_blacklist()
                if count > 0:
                    logger.info(f"Cleaned up {count} expired blacklist entries")
        except Exception as e:
            logger.error(f"Error in blacklist cleanup task: {str(e)}")


async def scheduled_arp_collection():
    """Background task to periodically collect ARP data from all enabled sources"""
    while True:
        interval = await _get_scheduler_interval("scheduler_arp_collection_interval", 300)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("arp_collection"):
                continue
            async with async_session_factory() as db:
                from app.services.arp_collector_service import ArpCollectorService
                service = ArpCollectorService(db)
                await service.run_scheduled_collection()
        except Exception as e:
            logger.error(f"Error in scheduled ARP collection task: {str(e)}")


async def scheduled_ipguard_sync():
    """Background task to periodically sync IPGuard baseline data"""
    while True:
        interval = await _get_scheduler_interval("scheduler_ipguard_sync_interval", 600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("ipguard_sync"):
                continue
            async with async_session_factory() as db:
                from sqlalchemy import select
                from app.models.compliance_baseline import ComplianceBaseline
                from app.services.compliance_service import ComplianceService
                service = ComplianceService(db)
                stmt = select(ComplianceBaseline).where(ComplianceBaseline.enabled == True)
                result = await db.execute(stmt)
                baselines = result.scalars().all()
                for baseline in baselines:
                    try:
                        await service.sync_ipguard_data(baseline.tag)
                        logger.info(f"Synced IPGuard data for baseline: {baseline.tag}")
                    except Exception as e:
                        logger.error(f"Error syncing IPGuard data for {baseline.tag}: {str(e)}")
        except Exception as e:
            logger.error(f"Error in scheduled IPGuard sync task: {str(e)}")


async def scheduled_compliance_check():
    """Background task to periodically run compliance checks"""
    while True:
        interval = await _get_scheduler_interval("scheduler_compliance_check_interval", 300)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("compliance_check"):
                continue
            async with async_session_factory() as db:
                from app.services.compliance_service import ComplianceService
                service = ComplianceService(db)
                from app.services.data_source_service import DataSourceService
                ds_service = DataSourceService(db)
                sources = await ds_service.list_data_sources(type="arp_ssh", enabled=True)
                sources2 = await ds_service.list_data_sources(type="arp_api", enabled=True)
                all_arp_sources = sources + sources2
                for source in all_arp_sources:
                    try:
                        from sqlalchemy import select as sa_select
                        from app.models.terminal import Terminal
                        stmt = sa_select(Terminal).where(
                            (Terminal.source_tag == source.tag) &
                            (Terminal.compliance_status == "unknown")
                        )
                        r = await db.execute(stmt)
                        unchecked = r.scalars().all()
                        if unchecked:
                            check_entries = [
                                {"ip_address": e.ip_address, "mac_address": e.mac_address, "source_tag": e.source_tag}
                                for e in unchecked
                            ]
                            result = await service.batch_check_compliance(check_entries)
                            # Update compliance_status for each entry
                            bypass_data = {}  # ip -> wl_match_type
                            compliant_ips = set()
                            non_compliant_ips = set()
                            if result.details:
                                for item in result.details.get("bypass", []):
                                    bypass_data[item.get("ip_address")] = item.get("wl_match_type")
                                for item in result.details.get("compliant", []):
                                    compliant_ips.add(item.get("ip_address"))
                                for item in result.details.get("non_compliant", []):
                                    non_compliant_ips.add(item.get("ip_address"))
                            for entry in unchecked:
                                if entry.ip_address in bypass_data:
                                    entry.compliance_status = "bypass"
                                    entry.wl_match_type = bypass_data[entry.ip_address]
                                elif entry.ip_address in compliant_ips:
                                    entry.compliance_status = "compliant"
                                    entry.wl_match_type = None
                                elif entry.ip_address in non_compliant_ips:
                                    entry.compliance_status = "non_compliant"
                                    entry.wl_match_type = None
                            await db.commit()
                            if result.non_compliant > 0 or result.bypass > 0:
                                logger.info(f"Compliance check for {source.tag}: {result.compliant} compliant, {result.bypass} bypass, {result.non_compliant} non-compliant")
                    except Exception as e:
                        logger.error(f"Error in compliance check for {source.tag}: {str(e)}")
        except Exception as e:
            logger.error(f"Error in scheduled compliance check task: {str(e)}")


async def scheduled_auto_unblock():
    """Background task to periodically auto-unblock compliant terminals"""
    while True:
        interval = await _get_scheduler_interval("scheduler_auto_unblock_interval", 600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("auto_unblock"):
                continue
            async with async_session_factory() as db:
                from app.services.compliance_service import ComplianceService
                service = ComplianceService(db)
                result = await service.auto_unblock_compliant()
                if result.unblocked > 0:
                    logger.info(f"Auto-unblocked {result.unblocked} compliant terminals")
        except Exception as e:
            logger.error(f"Error in scheduled auto-unblock task: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Terminal Network Access Manager...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Seed default system configs (idempotent)
    async with async_session_factory() as db:
        from app.services.config_service import ConfigService
        config_service = ConfigService(db)
        count = await config_service.seed_defaults()
        if count > 0:
            logger.info(f"Seeded {count} default system configs")
        else:
            logger.info("System configs already initialized")

    # Start background tasks
    cleanup_task = asyncio.create_task(cleanup_expired_blacklist())
    arp_collection_task = asyncio.create_task(scheduled_arp_collection())
    ipguard_sync_task = asyncio.create_task(scheduled_ipguard_sync())
    compliance_check_task = asyncio.create_task(scheduled_compliance_check())
    auto_unblock_task = asyncio.create_task(scheduled_auto_unblock())
    logger.info("All background scheduler tasks started")

    yield

    # Shutdown
    cleanup_task.cancel()
    arp_collection_task.cancel()
    ipguard_sync_task.cancel()
    compliance_check_task.cancel()
    auto_unblock_task.cancel()
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

# Serve uploaded branding assets
import os
UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


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
