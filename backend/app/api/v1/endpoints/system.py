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
from app.core.security import get_current_user
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
        await db.execute("SELECT 1")
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
    return {
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "email_enabled": settings.EMAIL_HOST is not None,
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
    current_user: User = Depends(get_current_user),
):
    """Trigger manual firewall reconciliation to sync firewall blocked IPs with database"""
    from app.services.firewall_reconciliation_service import FirewallReconciliationService
    
    recon_svc = FirewallReconciliationService(db)
    results = await recon_svc.reconcile()
    
    return {
        "success": True,
        "message": "Firewall reconciliation completed",
        **results,
    }
