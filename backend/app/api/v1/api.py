from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    blacklist,
    compliance_baselines,
    data_sources,
    logs,
    roles,
    settings,
    stats,
    terminals,
    whitelist,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(terminals.router)
api_router.include_router(whitelist.router)
api_router.include_router(blacklist.router)
api_router.include_router(logs.router)
api_router.include_router(stats.router)
api_router.include_router(settings.router)
api_router.include_router(data_sources.router)
api_router.include_router(compliance_baselines.router)
api_router.include_router(roles.router)
