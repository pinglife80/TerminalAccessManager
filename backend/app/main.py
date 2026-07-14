import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.core.logging_config import setup_logging
from app.core.security import close_redis_client
from app.middleware.error_handler import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware

# Configure logging (centralized: loguru + intercept stdlib logging)
setup_logging()


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


async def _acquire_task_lock(task_name: str, ttl: int = 300) -> bool:
    """Acquire a distributed lock for a scheduler task via Redis.
    Returns True if lock acquired, False if another instance holds it."""
    try:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        lock_key = f"scheduler:lock:{task_name}"
        # SET with NX (only if not exists) and EX (expire)
        acquired = await redis_client.set(lock_key, "locked", nx=True, ex=ttl)
        return acquired is not None
    except Exception:
        # If Redis is unavailable, allow task to run (fail-open)
        return True


async def _release_task_lock(task_name: str) -> None:
    """Release a distributed lock for a scheduler task"""
    try:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        lock_key = f"scheduler:lock:{task_name}"
        await redis_client.delete(lock_key)
    except Exception:
        pass


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
            if not await _acquire_task_lock("firewall_query"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.terminal_service import TerminalService
                    service = TerminalService(db)
                    count = await service.cleanup_expired_blacklist()
                    if count > 0:
                        logger.info(f"Cleaned up {count} expired blacklist entries [source=scheduler]")
            finally:
                await _release_task_lock("firewall_query")
        except Exception as e:
            logger.error(f"Error in blacklist cleanup task: {type(e).__name__}: {e} [source=scheduler]")


async def cleanup_expired_logs():
    """Background task to periodically clean up expired audit and notification logs"""
    while True:
        try:
            await asyncio.sleep(86400)
            if await _is_task_paused("log_cleanup"):
                continue
            if not await _acquire_task_lock("log_cleanup", 7200):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.config_service import ConfigService
                    config_service = ConfigService(db)
                    
                    retention_days = await config_service.get_value("audit_log_retention_days")
                    if retention_days is None:
                        retention_days = 90
                    else:
                        retention_days = int(retention_days)

                    from datetime import datetime, timedelta, UTC
                    cutoff_time = datetime.now(UTC) - timedelta(days=retention_days)

                    from sqlalchemy import delete, select, func
                    from app.models.log import AuditLog
                    from app.models.notification import NotificationLog

                    audit_stmt = delete(AuditLog).where(AuditLog.timestamp < cutoff_time)
                    audit_result = await db.execute(audit_stmt)
                    audit_deleted = audit_result.rowcount or 0

                    notif_stmt = delete(NotificationLog).where(
                        NotificationLog.sent_at < cutoff_time,
                        NotificationLog.archived == True
                    )
                    notif_result = await db.execute(notif_stmt)
                    notif_deleted = notif_result.rowcount or 0

                    await db.commit()

                    if audit_deleted > 0 or notif_deleted > 0:
                        logger.info(f"Cleaned up {audit_deleted} audit logs and {notif_deleted} notification logs older than {retention_days} days [source=scheduler]")
            finally:
                await _release_task_lock("log_cleanup")
        except Exception as e:
            logger.error(f"Error in log cleanup task: {type(e).__name__}: {e} [source=scheduler]")


async def firewall_reconciliation():
    """Background task to periodically reconcile firewall blocked IPs with database blacklist"""
    while True:
        try:
            await asyncio.sleep(300)
            if await _is_task_paused("firewall_reconciliation"):
                continue
            if not await _acquire_task_lock("firewall_reconciliation", 600):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.firewall_reconciliation_service import FirewallReconciliationService
                    recon_svc = FirewallReconciliationService(db)
                    results = await recon_svc.reconcile()

                    if results["missing_in_db"] or results["missing_in_firewall"]:
                        logger.warning(f"Firewall reconciliation found {len(results['missing_in_db'])} IPs missing in DB and {len(results['missing_in_firewall'])} IPs missing in firewall")
                        logger.info(f"Reconciliation results: created_in_db={results['created_in_db']}, marked_unblocked={results['marked_unblocked']}, unblocked_on_firewall={results['unblocked_on_firewall']}")
            finally:
                await _release_task_lock("firewall_reconciliation")
        except Exception as e:
            logger.error(f"Error in firewall reconciliation task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_arp_collection():
    """Background task to periodically collect ARP data from all enabled sources"""
    while True:
        interval = await _get_scheduler_interval("scheduler_arp_collection_interval", 300)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("arp_collection"):
                continue
            if not await _acquire_task_lock("arp_collection"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.arp_collector_service import ArpCollectorService
                    service = ArpCollectorService(db)
                    await service.run_scheduled_collection()
            finally:
                await _release_task_lock("arp_collection")
        except Exception as e:
            logger.error(f"Error in scheduled ARP collection task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_ipguard_sync():
    """Background task to periodically sync IPGuard baseline data"""
    while True:
        interval = await _get_scheduler_interval("scheduler_ipguard_sync_interval", 600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("ipguard_sync"):
                continue
            if not await _acquire_task_lock("ipguard_sync"):
                continue
            try:
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
                            logger.info(f"Synced IPGuard data for baseline: {baseline.tag} [source=scheduler]")
                            # Trigger compliance re-evaluation after IPGuard data update
                            try:
                                result = await service.recalculate_all_compliance()
                                if result.get("non_compliant", 0) > 0 or result.get("bypass", 0) > 0 or result.get("compliant", 0) > 0:
                                    logger.info(f"Compliance re-evaluated after IPGuard sync: {result} [source=scheduler]")
                            except Exception as re:
                                logger.error(f"Error re-evaluating compliance after IPGuard sync: {type(re).__name__}: {re} [source=scheduler]")
                        except Exception as e:
                            logger.error(f"Error syncing IPGuard data for {baseline.tag}: {type(e).__name__}: {e} [source=scheduler]")
                            # Emit datasource sync failed event for notification dispatch.
                            # fire-and-forget: emit_event logs errors internally and never raises.
                            from app.services.event_emitter import emit_datasource_sync_failed
                            await emit_datasource_sync_failed(
                                source_name=baseline.tag,
                                source_tag=baseline.tag,
                                error=f"{type(e).__name__}: {e}",
                            )
            finally:
                await _release_task_lock("ipguard_sync")
        except Exception as e:
            logger.error(f"Error in scheduled IPGuard sync task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_compliance_check():
    """Background task to periodically run compliance checks"""
    while True:
        interval = await _get_scheduler_interval("scheduler_compliance_check_interval", 300)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("compliance_check"):
                continue
            if not await _acquire_task_lock("compliance_check"):
                continue
            try:
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

                                # Build lookup maps for compliance results
                                result_lookup = {}
                                if result.details:
                                    for item in result.details.get("bypass", []):
                                        result_lookup[item.get("ip_address")] = {
                                            "compliance_status": "bypass",
                                            "wl_match_type": item.get("wl_match_type"),
                                            "wl_comments": item.get("wl_comments"),
                                        }
                                    for item in result.details.get("compliant", []):
                                        result_lookup[item.get("ip_address")] = {
                                            "compliance_status": "compliant",
                                            "wl_match_type": None,
                                            "wl_comments": None,
                                        }
                                    for item in result.details.get("non_compliant", []):
                                        result_lookup[item.get("ip_address")] = {
                                            "compliance_status": "non_compliant",
                                            "wl_match_type": None,
                                            "wl_comments": None,
                                        }

                                # Apply compliance results using shared method
                                for entry in unchecked:
                                    r = result_lookup.get(entry.ip_address)
                                    if r:
                                        await service._apply_compliance_result(
                                            entry,
                                            r["compliance_status"],
                                            r["wl_match_type"],
                                            r["wl_comments"],
                                            entry.ip_address or "",
                                            entry.mac_address or "",
                                        )

                                await db.commit()
                                if result.non_compliant > 0 or result.bypass > 0:
                                    logger.info(f"Compliance check for {source.tag}: {result.compliant} compliant, {result.bypass} bypass, {result.non_compliant} non-compliant")
                                    # Trigger auto-block for non-compliant terminals
                                    if result.non_compliant > 0:
                                        try:
                                            block_result = await service.auto_block_non_compliant(source.tag)
                                            if block_result.blocked > 0:
                                                logger.info(f"Auto-blocked {block_result.blocked} non-compliant terminals from {source.tag} [source=scheduler]")
                                        except Exception as be:
                                            logger.error(f"Error auto-blocking for {source.tag}: {type(be).__name__}: {be} [source=scheduler]")

                                        # Emit compliance rate alert when non-compliant terminals are found.
                                        # fire-and-forget: emit_event logs errors internally and never raises.
                                        from app.services.event_emitter import emit_compliance_alert
                                        total_checked = result.compliant + result.bypass + result.non_compliant
                                        rate = (result.compliant / total_checked * 100) if total_checked > 0 else 100.0
                                        await emit_compliance_alert(
                                            compliance_rate=rate,
                                            non_compliant_count=result.non_compliant,
                                            threshold=0.8,
                                        )
                        except Exception as e:
                            logger.error(f"Error in compliance check for {source.tag}: {type(e).__name__}: {e} [source=scheduler]")
            finally:
                await _release_task_lock("compliance_check")
        except Exception as e:
            logger.error(f"Error in scheduled compliance check task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_auto_unblock():
    """Background task to periodically auto-unblock compliant terminals"""
    while True:
        interval = await _get_scheduler_interval("scheduler_auto_unblock_interval", 600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("auto_unblock"):
                continue
            if not await _acquire_task_lock("auto_unblock"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.compliance_service import ComplianceService
                    service = ComplianceService(db)
                    result = await service.auto_unblock_compliant()
                    if result.unblocked > 0:
                        logger.info(f"Auto-unblocked {result.unblocked} compliant terminals")
            finally:
                await _release_task_lock("auto_unblock")
        except Exception as e:
            logger.error(f"Error in scheduled auto-unblock task: {type(e).__name__}: {e} [source=scheduler]")


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

        # Migrate legacy "Terminal Access Platform" → "Terminal Access Manager"
        from sqlalchemy import text
        legacy_rows = await db.execute(
            text("SELECT id, value FROM system_config WHERE value LIKE '%Terminal Access Platform%'")
        )
        for row in legacy_rows:
            new_value = row[1].replace("Terminal Access Platform", "Terminal Access Manager")
            await db.execute(
                text("UPDATE system_config SET value = :val WHERE id = :id"),
                {"val": new_value, "id": row[0]}
            )
            logger.info(f"Migrated config id={row[0]}: '{row[1]}' → '{new_value}'")
        await db.commit()

        # Migrate legacy action names in audit_logs
        action_migrations = {
            "block_ip": "block_terminal",
            "unblock_ip": "unblock_terminal",
            "block": "block_blacklist",
            "unblock": "unblock_blacklist",
        }
        for old_action, new_action in action_migrations.items():
            result = await db.execute(
                text("UPDATE audit_logs SET action = :new WHERE action = :old"),
                {"new": new_action, "old": old_action}
            )
            if result.rowcount > 0:
                logger.info(f"Migrated {result.rowcount} audit log action(s): '{old_action}' → '{new_action}'")
        await db.commit()

    # Initialize global notification service (singleton).
    # Module-level singleton instead of ContextVar: scheduler tasks spawned here
    # run in the same event loop but separate task contexts, and ContextVar
    # values do not propagate into them — which previously caused
    # emit_event() to silently no-op with "Notification service not initialized".
    from app.services.event_emitter import set_notification_service
    from app.services.notification_service import NotificationService

    notification_service = NotificationService(db=None)
    await notification_service.initialize_channels()
    await notification_service.start_workers()
    set_notification_service(notification_service)
    logger.info(
        f"Notification service initialized with {len(notification_service._channels)} channel(s)"
    )

    cleanup_task = asyncio.create_task(cleanup_expired_blacklist())
    arp_collection_task = asyncio.create_task(scheduled_arp_collection())
    ipguard_sync_task = asyncio.create_task(scheduled_ipguard_sync())
    compliance_check_task = asyncio.create_task(scheduled_compliance_check())
    auto_unblock_task = asyncio.create_task(scheduled_auto_unblock())
    log_cleanup_task = asyncio.create_task(cleanup_expired_logs())
    firewall_reconciliation_task = asyncio.create_task(firewall_reconciliation())
    logger.info("All background scheduler tasks started")

    yield

    # Shutdown
    logger.info("Shutting down Terminal Network Access Manager...")

    # Stop notification workers
    await notification_service.stop_workers()
    logger.info("Notification workers stopped")

    # Cancel background tasks and wait for them to finish
    for task in [cleanup_task, arp_collection_task, ipguard_sync_task, compliance_check_task, auto_unblock_task, log_cleanup_task, firewall_reconciliation_task]:
        task.cancel()
    await asyncio.gather(*[cleanup_task, arp_collection_task, ipguard_sync_task, compliance_check_task, auto_unblock_task, log_cleanup_task, firewall_reconciliation_task], return_exceptions=True)
    logger.info("Background tasks cancelled")

    # Close Redis connections
    await close_redis_client()
    logger.info("Redis connections closed")

    # Dispose database engine
    from app.core.database import engine
    await engine.dispose()
    logger.info("Database engine disposed")

    # Close email HTTP client
    try:
        from app.services.notification_channels.email_channel import _email_http_client
        if _email_http_client is not None and not _email_http_client.is_closed:
            await _email_http_client.aclose()
            logger.info("Email HTTP client closed")
    except Exception as e:
        logger.warning(f"Error closing email HTTP client: {e}")


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

# Register global exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Add request-id middleware (registered last so it runs first)
app.add_middleware(RequestIDMiddleware)

# Add request logging middleware (registered second so it runs second, after request_id is set)
app.add_middleware(RequestLoggingMiddleware)

# Add rate limiting middleware (registered first so it runs last)
app.add_middleware(RateLimitMiddleware)

# Configure CORS
if settings.BACKEND_CORS_ORIGINS:
    origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]

    # Security check: allow_credentials=True with wildcard origin is invalid per CORS spec
    # and would allow any site to make authenticated requests
    if "*" in origins and len(origins) == 1:
        logger.warning(
            "CORS: allow_origins='*' with allow_credentials=True is insecure. "
            "Falling back to allow_credentials=False."
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Serve uploaded branding assets

UPLOAD_DIR = settings.UPLOAD_DIR


def _ensure_upload_dir():
    """Ensure upload directory exists (safe to call multiple times)"""
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        return True
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot create upload directory {UPLOAD_DIR}: {e}")
        return False


if _ensure_upload_dir():
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health_check():
    """Health check endpoint with dependency verification"""
    import redis.asyncio as aioredis
    from sqlalchemy import text

    from app.core.database import engine

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
        if settings.ENVIRONMENT == "production":
            health_status["db"] = "error"
        else:
            health_status["db"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Redis connection
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
    except Exception as e:
        if settings.ENVIRONMENT == "production":
            health_status["redis"] = "error"
        else:
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


# Prometheus monitoring (enabled in all environments for observability)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)

    # Expose custom business metrics at /metrics/custom
    from fastapi.responses import Response

    from app.services.metrics_service import get_metrics

    @app.get("/metrics/custom", include_in_schema=False)
    async def custom_metrics():
        """Custom business metrics for Prometheus"""
        return Response(content=get_metrics(), media_type="text/plain")

    logger.info("Prometheus metrics enabled at /metrics and /metrics/custom")
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator not installed, metrics disabled")


# Enhanced health check endpoints
@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness check - verifies all dependencies are available.
    Used by Kubernetes readinessProbe.
    """
    import redis.asyncio as aioredis
    from sqlalchemy import text

    from app.core.database import engine

    checks = {
        "database": "unknown",
        "redis": "unknown",
    }

    # Check database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:50]}"

    # Check Redis
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:50]}"

    # Determine overall status
    all_ok = all(v == "ok" for v in checks.values())

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """
    Liveness check - verifies the application is running.
    Used by Kubernetes livenessProbe.
    """
    return {
        "status": "alive",
        "version": settings.VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
