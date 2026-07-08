import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.terminal import BlacklistCheckItem, BlacklistCheckRequest, BlacklistCreate, BlacklistQuery, BlacklistResponse, PaginatedResponse, ResponseMessage
from app.services.terminal_service import TerminalService

router = APIRouter(prefix="/blacklist", tags=["Blacklist"])


@router.get("/stats")
async def get_blacklist_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:read"))
):
    """Get blacklist statistics (server-side global counts for active entries)."""
    service = TerminalService(db)
    stats = await service.get_blacklist_stats()
    return stats


@router.get("/", response_model=PaginatedResponse[BlacklistResponse])
async def get_blacklist(
    search: str = Query(None, description="Search by MAC or IP"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    status: str = Query(None, description="Filter by status: active/unblocked/all"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:read"))
):
    """Get blacklisted terminals with search and date filtering.
    Default shows only active (auto_unblocked=False) records.
    Use status='unblocked' for unblocked history, 'all' for all records."""
    query = None
    if search or start_date or end_date or status:
        query = BlacklistQuery(
            search=search,
            start_date=start_date,
            end_date=end_date,
            status=status,
            skip=skip,
            limit=limit
        )

    service = TerminalService(db)
    blacklist = await service.get_blacklist(query=query, skip=skip, limit=limit)
    total = await service.get_blacklist_count(query=query)
    return {"items": blacklist, "total": total, "skip": skip, "limit": limit}


@router.post("/check", response_model=list[BlacklistCheckItem])
async def check_blacklist(
    request: BlacklistCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:read"))
):
    """Batch-check which MAC/IP addresses are currently active in the blacklist.
    Returns only matching entries (mac_address, ip_address, firewall_tag).
    Uses indexed IN() query for efficient bulk lookup."""
    service = TerminalService(db)
    results = await service.check_blacklist(
        mac_addresses=request.mac_addresses,
        ip_addresses=request.ip_addresses,
    )
    return results


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_to_blacklist(
    blacklist_data: BlacklistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:write"))
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
    current_user: User = Depends(require_permission("blacklist:write"))
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


@router.get("/export")
async def export_blacklist(
    search: str = Query(None, description="Search by MAC or IP"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    status: str = Query(None, description="Filter by status: active/unblocked/all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:read"))
):
    """Export blacklist as CSV with filtering support"""
    from sqlalchemy import select, or_, and_, desc
    from app.models.blacklist import Blacklist
    from app.services.terminal_service import _parse_date_range, _escape_like, _normalize_mac

    conditions = []

    _active_filter = and_(
        Blacklist.auto_unblocked == False,
        Blacklist.unblocked_at.is_(None)
    )
    _unblocked_filter = or_(
        Blacklist.auto_unblocked == True,
        Blacklist.unblocked_at.is_not(None)
    )
    if status:
        if status == 'active':
            conditions.append(_active_filter)
        elif status == 'unblocked':
            conditions.append(_unblocked_filter)
    else:
        conditions.append(_active_filter)

    if search:
        mac_clean = _normalize_mac(search)
        conditions.append(
            or_(
                Blacklist.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"),
                Blacklist.ip_address.ilike(f"%{_escape_like(search)}%"),
            )
        )

    date_conditions = _parse_date_range(start_date, end_date)
    for dc in date_conditions:
        conditions.append(dc(Blacklist.blocked_at))

    stmt = (
        select(Blacklist)
        .where(and_(*conditions) if conditions else True)
        .order_by(desc(Blacklist.blocked_at))
    )

    result = await db.execute(stmt)
    blacklist = result.scalars().all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "MAC Address", "IP Address", "Status", "Firewall Tag",
        "Reason", "Block Time", "Added By", "Created At", "Auto Unblocked"
    ])

    for b in blacklist:
        writer.writerow([
            b.id,
            b.mac_address or "",
            b.ip_address or "",
            b.status or "",
            b.firewall_tag or "",
            b.reason or "",
            b.block_time or "",
            b.added_by or "",
            b.created_at or "",
            b.auto_unblocked or ""
        ])

    output.seek(0)

    headers = {
        "Content-Disposition": "attachment; filename=blacklist.csv",
        "Content-Type": "text/csv",
    }

    return Response(content=output.getvalue(), headers=headers)
