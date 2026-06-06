from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.mac_address import (
    BlacklistCreate,
    BlacklistResponse,
    ResponseMessage
)
from app.services.mac_service import MacService

router = APIRouter(prefix="/blacklist", tags=["Blacklist"])


@router.get("/", response_model=List[BlacklistResponse])
async def get_blacklist(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all blacklisted terminals"""
    service = MacService(db)
    blacklist = await service.get_blacklist(skip=skip, limit=limit)
    return blacklist


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_to_blacklist(
    blacklist_data: BlacklistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add to blacklist by IP address, MAC address, or both"""
    service = MacService(db)
    
    if not blacklist_data.ip_address and not blacklist_data.mac_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of IP address or MAC address is required"
        )
    
    try:
        result = await service.add_to_blacklist(
            ip_address=blacklist_data.ip_address or "",
            mac_address=blacklist_data.mac_address,
            reason=blacklist_data.reason or "",
            username=current_user.username
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
    """Remove from blacklist by MAC address or IP address"""
    service = MacService(db)
    
    success = await service.delete_from_blacklist(identifier, current_user.username)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Terminal not found in blacklist"
        )
    
    return {"message": "Successfully unblocked terminal", "success": True}