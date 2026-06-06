from fastapi import APIRouter

from app.api.v1.endpoints import auth, mac_addresses, whitelist, logs, blacklist

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(mac_addresses.router)
api_router.include_router(whitelist.router)
api_router.include_router(blacklist.router)
api_router.include_router(logs.router)
