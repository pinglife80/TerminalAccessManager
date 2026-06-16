from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.models.terminal import Terminal
from app.schemas.terminal import (
    TerminalResponse,
    TerminalQuery,
    PaginatedResponse,
    ResponseMessage
)
from app.services.terminal_service import TerminalService

router = APIRouter(prefix="/terminals", tags=["Terminals"])


@router.get("/", response_model=List[TerminalResponse])
async def get_invalid_mac_addresses(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("terminal:read"))
):
    """Get unblocked MAC addresses with pagination"""
    service = TerminalService(db)
    macs = await service.get_invalid_macs(skip=skip, limit=limit)
    return macs


@router.get("/search", response_model=PaginatedResponse[TerminalResponse])
async def search_mac_addresses(
    ip: str = Query(None, description="Filter by IP address"),
    mac: str = Query(None, description="Filter by MAC address"),
    status_filter: str = Query(None, alias="status", description="Filter by status"),
    compliance_status: str = Query(None, description="Filter by compliance status"),
    source_tag: str = Query(None, description="Filter by source tag"),
    firewall_tag: str = Query(None, description="Filter by firewall tag (via blacklist)"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("terminal:read"))
):
    """Search MAC addresses by various criteria with date range filtering"""
    query = TerminalQuery(
        ip=ip,
        mac=mac,
        status=status_filter,
        compliance_status=compliance_status,
        source_tag=source_tag,
        firewall_tag=firewall_tag,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )

    service = TerminalService(db)
    results = await service.search_macs(query)
    total = await service.search_macs_count(query)
    return {"items": results, "total": total, "skip": skip, "limit": limit}


@router.post("/block/{ip_address}", response_model=ResponseMessage)
async def block_ip_address(
    ip_address: str,
    mac_address: str = Query(..., description="MAC address associated with IP"),
    block_time: str = Query("30d", description="Block duration (e.g. 30d, 15d, 7d, 1h)"),
    firewall_tag: Optional[str] = Query(None, description="Firewall tag to route block operation"),
    comments: Optional[str] = Query(None, description="Comment for the block action"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("terminal:write")),
    request: Request = None
):
    """Block an IP address via Sangfor API"""
    client_ip = request.client.host if request else None
    service = TerminalService(db)
    result = await service.block_ip(ip_address, mac_address, current_user.username,
                                     block_time=block_time, firewall_tag=firewall_tag,
                                     comments=comments, client_ip=client_ip)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )

    return result


@router.post("/unblock/{ip_address}", response_model=ResponseMessage)
async def unblock_ip_address(
    ip_address: str,
    mac_address: Optional[str] = Query(None, description="MAC address to unblock (if omitted, unblocks all MACs for this IP)"),
    firewall_tag: Optional[str] = Query(None, description="Firewall tag to route unblock operation"),
    comments: Optional[str] = Query(None, description="Comment for the unblock action"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("terminal:write")),
    request: Request = None
):
    """Unblock an IP address via Sangfor API"""
    client_ip = request.client.host if request else None
    service = TerminalService(db)
    result = await service.unblock_ip(ip_address, current_user.username,
                                       mac_address=mac_address,
                                       firewall_tag=firewall_tag, comments=comments,
                                       client_ip=client_ip)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )

    return result


@router.get("/{mac_id}", response_model=TerminalResponse)
async def get_mac_address_by_id(
    mac_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("terminal:read"))
):
    """Get a specific terminal record by ID"""
    from sqlalchemy import select

    stmt = select(Terminal).where(Terminal.id == mac_id)
    result = await db.execute(stmt)
    mac_record = result.scalar_one_or_none()

    if not mac_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Terminal record not found"
        )

    return mac_record
