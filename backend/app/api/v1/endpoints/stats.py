from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.terminal import DashboardStats, SystemStatus
from app.services.terminal_service import TerminalService

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("/", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dashboard statistics (total, whitelisted, blocked, active, inactive, pending)"""
    service = TerminalService(db)
    stats = await service.get_stats()
    return stats


@router.get("/system-status", response_model=SystemStatus)
async def get_system_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get system status including Sangfor AF connectivity"""
    service = TerminalService(db)
    status = await service.get_system_status()
    return status
