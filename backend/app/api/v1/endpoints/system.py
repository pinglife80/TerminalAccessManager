"""
System API Endpoints for TerminalAccessManager.

Provides system status and configuration management endpoints.
"""

import platform
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import engine, get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User

router = APIRouter(prefix="/system", tags=["System"])

start_time = time.time()


@router.get("/status", response_model=dict)
async def get_system_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get system status and health information"""
    uptime_seconds = time.time() - start_time

    days = int(uptime_seconds // (24 * 3600))
    hours = int((uptime_seconds % (24 * 3600)) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    seconds = int(uptime_seconds % 60)

    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    return {
        "uptime": uptime_str,
        "database": db_status,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }


@router.get("/config", response_model=dict)
async def get_system_config(
    current_user: User = Depends(get_current_user),
):
    """Get current system configuration (safe values only)"""
    # email_enabled is DB-backed (system_config) with .env fallback, kept
    # consistent with auth.py's allow_registration to avoid dual-source drift.
    from app.services.config_service import get_config_value
    email_enabled = await get_config_value("email_enabled", bool(settings.EMAIL_HOST))
    return {
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "email_enabled": email_enabled,
        "metrics_enabled": settings.PROMETHEUS_ENABLED,
    }


@router.get("/health", response_model=dict)
async def health_check():
    """Health check endpoint with dependency verification"""
    import redis.asyncio as aioredis

    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "db": "ok",
        "redis": "ok"
    }

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        if settings.ENVIRONMENT == "production":
            health_status["db"] = "error"
        else:
            health_status["db"] = f"error: {str(e)}"

    try:
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis_client.ping()
        await redis_client.close()
    except Exception as e:
        if settings.ENVIRONMENT == "production":
            health_status["redis"] = "error"
        else:
            health_status["redis"] = f"error: {str(e)}"

    if health_status["db"] != "ok" or health_status["redis"] != "ok":
        health_status["status"] = "unhealthy"

    return health_status


@router.post("/firewall-reconciliation", response_model=dict)
async def trigger_firewall_reconciliation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("system:manage")),
):
    """Trigger manual firewall reconciliation to sync firewall blocked IPs with database"""
    from app.services.firewall_reconciliation_service import FirewallReconciliationService
    
    recon_svc = FirewallReconciliationService(db)
    results = await recon_svc.reconcile()

    # Cache latest reconciliation result for firewall stats display
    from app.main import _cache_reconcile_result
    await _cache_reconcile_result(results)

    return {
        "success": True,
        "message": "Firewall reconciliation completed",
        **results,
    }


@router.get("/scheduler/tasks", response_model=dict)
async def get_scheduler_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the authoritative scheduler task list with real-time status."""
    from app.core.scheduler_registry import SCHEDULER_TASKS
    from app.core.security import get_redis_client
    from app.services.config_service import ConfigService

    redis_client = None
    try:
        redis_client = await get_redis_client()
    except Exception:
        redis_client = None

    config_service = ConfigService(db)

    tasks = []
    for task in SCHEDULER_TASKS:
        name = task["name"]
        interval_key = task["interval_key"]
        default_interval = task["default_interval"]

        # Resolve interval (configurable tasks clamp to 30-86400s, fixed otherwise)
        interval_seconds = default_interval
        if interval_key is not None:
            try:
                value = await config_service.get_value(interval_key)
                if value is not None:
                    interval_seconds = max(30, min(86400, int(value)))
            except Exception:
                interval_seconds = default_interval

        paused = False
        executing = False
        alive = False
        last_heartbeat_at = None
        if redis_client is not None:
            try:
                ctrl_val = await redis_client.get(f"scheduler:ctrl:{name}")
                paused = ctrl_val == b"paused" or ctrl_val == "paused"
                lock_val = await redis_client.get(f"scheduler:lock:{name}")
                executing = lock_val is not None
                hb_val = await redis_client.get(f"scheduler:heartbeat:{name}")
                if hb_val is not None:
                    alive = True
                    last_heartbeat_at = hb_val.decode() if isinstance(hb_val, bytes) else str(hb_val)
            except Exception:
                pass

        tasks.append({
            "name": name,
            "display_name": task["display_name"],
            "interval_seconds": interval_seconds,
            "interval_key": interval_key,
            "paused": paused,
            "executing": executing,
            "alive": alive,
            "last_heartbeat_at": last_heartbeat_at,
        })

    return {"tasks": tasks}
