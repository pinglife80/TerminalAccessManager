from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.mac_address import MacAddress
from app.schemas.mac_address import (
    MacAddressResponse,
    MacAddressQuery,
    ResponseMessage
)
from app.services.mac_service import MacService

router = APIRouter(prefix="/mac", tags=["MAC Addresses"])


@router.get("/", response_model=List[MacAddressResponse])
async def get_invalid_mac_addresses(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get invalid (unfrozen) MAC addresses with pagination"""
    service = MacService(db)
    macs = await service.get_invalid_macs(skip=skip, limit=limit)
    return macs


@router.get("/search", response_model=List[MacAddressResponse])
async def search_mac_addresses(
    ip: str = Query(None, description="Filter by IP address"),
    mac: str = Query(None, description="Filter by MAC address"),
    status_filter: str = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search MAC addresses by various criteria"""
    query = MacAddressQuery(
        ip=ip,
        mac=mac,
        status=status_filter,
        skip=skip,
        limit=limit
    )
    
    service = MacService(db)
    results = await service.search_macs(query)
    return results


@router.post("/block/{ip_address}", response_model=ResponseMessage)
async def block_ip_address(
    ip_address: str,
    mac_address: str = Query(..., description="MAC address associated with IP"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Block an IP address via Sangfor API"""
    service = MacService(db)
    result = await service.block_ip(ip_address, mac_address, current_user.username)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
    
    return result


@router.post("/unblock/{ip_address}", response_model=ResponseMessage)
async def unblock_ip_address(
    ip_address: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unblock an IP address via Sangfor API"""
    service = MacService(db)
    result = await service.unblock_ip(ip_address, current_user.username)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
    
    return result


@router.get("/{mac_id}", response_model=MacAddressResponse)
async def get_mac_address_by_id(
    mac_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific MAC address record by ID"""
    from sqlalchemy import select
    
    stmt = select(MacAddress).where(MacAddress.id == mac_id)
    result = await db.execute(stmt)
    mac_record = result.scalar_one_or_none()
    
    if not mac_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MAC address record not found"
        )
    
    return mac_record
