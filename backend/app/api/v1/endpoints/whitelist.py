from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.mac_address import (
    WhitelistCreate,
    WhitelistResponse,
    ResponseMessage
)
from app.services.mac_service import MacService

router = APIRouter(prefix="/whitelist", tags=["Whitelist"])


@router.get("/", response_model=List[WhitelistResponse])
async def get_whitelist(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all whitelisted MAC addresses"""
    service = MacService(db)
    whitelist = await service.get_whitelist(skip=skip, limit=limit)
    return whitelist


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_to_whitelist(
    whitelist_data: WhitelistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add to whitelist by MAC address, IP address, CIDR subnet, or IP range"""
    service = MacService(db)
    
    try:
        result = await service.add_to_whitelist(
            mac_address=whitelist_data.mac_address,
            ip_address=whitelist_data.ip_address,
            comments=whitelist_data.comments or "",
            username=current_user.username
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{mac_address}", response_model=ResponseMessage)
async def delete_from_whitelist(
    mac_address: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove a MAC address from whitelist"""
    service = MacService(db)
    
    success = await service.delete_from_whitelist(mac_address, current_user.username)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MAC address not found in whitelist"
        )
    
    return {"message": "Successfully removed from whitelist", "success": True}
