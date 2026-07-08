import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.terminal import PaginatedResponse, ResponseMessage, WhitelistCreate, WhitelistQuery, WhitelistResponse
from app.services.terminal_service import TerminalService

router = APIRouter(prefix="/whitelist", tags=["Whitelist"])


@router.get("/", response_model=PaginatedResponse[WhitelistResponse])
async def get_whitelist(
    search: str = Query(None, description="Search by MAC, IP, or comments"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("whitelist:read"))
):
    """Get all whitelisted MAC addresses with search and date filtering"""
    query = None
    if search or start_date or end_date:
        query = WhitelistQuery(
            search=search,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit
        )

    service = TerminalService(db)
    whitelist = await service.get_whitelist(query=query, skip=skip, limit=limit)
    total = await service.get_whitelist_count(query=query)
    return {"items": whitelist, "total": total, "skip": skip, "limit": limit}


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_to_whitelist(
    whitelist_data: WhitelistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("whitelist:write"))
):
    """Add to whitelist by MAC address, IP address, CIDR subnet, or IP range"""
    service = TerminalService(db)

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


@router.delete("/", response_model=ResponseMessage)
async def delete_from_whitelist(
    identifier: str = Query(..., description="MAC address or IP pattern to remove"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("whitelist:write"))
):
    """Remove a MAC address or IP pattern from whitelist"""
    service = TerminalService(db)

    success = await service.delete_from_whitelist(identifier, current_user.username)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found in whitelist"
        )

    return {"message": "Successfully removed from whitelist", "success": True}


@router.get("/export")
async def export_whitelist(
    search: str = Query(None, description="Search by MAC, IP, or comments"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("whitelist:read"))
):
    """Export whitelist as CSV with filtering support"""
    from sqlalchemy import select, or_, and_, desc
    from app.models.whitelist import Whitelist
    from app.services.terminal_service import _parse_date_range, _escape_like, _normalize_mac

    conditions = []

    if search:
        mac_clean = _normalize_mac(search)
        conditions.append(
            or_(
                Whitelist.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"),
                Whitelist.ip_pattern.ilike(f"%{_escape_like(search)}%"),
                Whitelist.comments.ilike(f"%{_escape_like(search)}%"),
            )
        )

    date_conditions = _parse_date_range(start_date, end_date)
    for dc in date_conditions:
        conditions.append(dc(Whitelist.created_at))

    stmt = (
        select(Whitelist)
        .where(and_(*conditions) if conditions else True)
        .order_by(desc(Whitelist.created_at))
    )

    result = await db.execute(stmt)
    whitelist = result.scalars().all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "MAC Address", "IP Pattern", "Pattern Type", "Comments", "Added By", "Created At"
    ])

    for w in whitelist:
        writer.writerow([
            w.id,
            w.mac_address or "",
            w.ip_pattern or "",
            w.pattern_type or "",
            w.comments or "",
            w.added_by or "",
            w.created_at or ""
        ])

    output.seek(0)

    headers = {
        "Content-Disposition": "attachment; filename=whitelist.csv",
        "Content-Type": "text/csv",
    }

    return Response(content=output.getvalue(), headers=headers)
