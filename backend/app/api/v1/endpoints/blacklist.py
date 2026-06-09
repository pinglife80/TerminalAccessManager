from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.terminal import (
    BlacklistCreate,
    BlacklistResponse,
    BlacklistQuery,
    PaginatedResponse,
    ResponseMessage
)
from app.services.terminal_service import TerminalService

router = APIRouter(prefix="/blacklist", tags=["Blacklist"])


@router.get("/", response_model=PaginatedResponse[BlacklistResponse])
async def get_blacklist(
    search: str = Query(None, description="Search by MAC or IP"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all blacklisted terminals with search and date filtering"""
    query = None
    if search or start_date or end_date:
        query = BlacklistQuery(
            search=search,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit
        )

    service = TerminalService(db)
    blacklist = await service.get_blacklist(query=query, skip=skip, limit=limit)
    total = await service.get_blacklist_count(query=query)
    return {"items": blacklist, "total": total, "skip": skip, "limit": limit}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_to_blacklist(
    blacklist_data: BlacklistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add to blacklist by IP address, MAC address, or both.
    Also blocks the IP on Sangfor AF firewall if configured."""
    if not blacklist_data.ip_address and not blacklist_data.mac_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of IP address or MAC address is required"
        )

    service = TerminalService(db)

    try:
        result = await service.add_to_blacklist(
            ip_address=blacklist_data.ip_address or "",
            mac_address=blacklist_data.mac_address,
            reason=blacklist_data.reason or "",
            username=current_user.username,
            block_time=blacklist_data.block_time or "30d",
            firewall_tag=blacklist_data.firewall_tag,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{identifier}", response_model=ResponseMessage)
async def delete_from_blacklist(
    identifier: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove from blacklist by MAC address or IP address.
    Also unblocks the IP on Sangfor AF firewall if configured."""
    service = TerminalService(db)

    success = await service.delete_from_blacklist(identifier, current_user.username)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Terminal not found in blacklist"
        )

    return {"message": "Successfully unblocked terminal", "success": True}
