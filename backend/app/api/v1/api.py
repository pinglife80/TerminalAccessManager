from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    auth_providers,
    backup,
    blacklist,
    compliance_baselines,
    compliance_scope,
    data_sources,
    ldap,
    logs,
    notifications,
    roles,
    settings,
    stats,
    system,
    terminals,
    whitelist,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(auth_providers.router)
api_router.include_router(ldap.router)
api_router.include_router(backup.router)
api_router.include_router(terminals.router)
api_router.include_router(whitelist.router)
api_router.include_router(blacklist.router)
api_router.include_router(logs.router)
api_router.include_router(stats.router)
api_router.include_router(settings.router)
api_router.include_router(data_sources.router)
api_router.include_router(compliance_baselines.router)
api_router.include_router(compliance_scope.router)
api_router.include_router(roles.router)
api_router.include_router(notifications.router)
api_router.include_router(system.router)


@api_router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint with dependency verification"""
    import redis.asyncio as aioredis
    from sqlalchemy import text

    from app.core.config import settings
    from app.core.database import engine

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
