import csv
from io import StringIO
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.terminal import BlacklistCheckItem, BlacklistCheckRequest, BlacklistQuery, BlacklistResponse, PaginatedResponse
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


@router.post("/{entry_id}/retry")
async def retry_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:write"))
):
    """Manually retry unblocking a single blacklist entry on its firewall."""
    service = TerminalService(db)
    result = await service.retry_unblock(entry_id, username=current_user.username)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "重试失败"))
    return {"success": True, "message": "解封成功"}


@router.get("/", response_model=PaginatedResponse[BlacklistResponse])
async def get_blacklist(
    search: str = Query(None, description="Search by MAC or IP"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    status: str = Query(None, description="Filter by status: active/unblocked/all"),
    category: str = Query(None, description="Filter by category: success_blocked/success_unblocked/pending_retry_unblock"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("blacklist:read"))
):
    """Get blacklisted terminals with search and date filtering.
    Default shows only active (auto_unblocked=False) records.
    Use status='unblocked' for unblocked history, 'all' for all records."""
    query = None
    if search or start_date or end_date or status or category:
        query = BlacklistQuery(
            search=search,
            start_date=start_date,
            end_date=end_date,
            status=status,
            category=category,
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
        Blacklist.unblocked_at.is_(None),
        or_(
            Blacklist.expires_at >= datetime.now(UTC),
            Blacklist.expires_at.is_(None),
        )
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
        "Reason", "Block Time", "Blocked By", "Source Tag", "Block Type", "Auto Unblocked"
    ])

    for b in blacklist:
        is_blocked = not (b.auto_unblocked or b.unblocked_at)
        status_label = "Blocked" if is_blocked else "Unblocked"
        block_type = "Auto" if b.is_auto_blocked else "Manual"
        unblock_label = "Yes" if b.auto_unblocked or b.unblocked_at else "No"
        writer.writerow([
            b.id,
            b.mac_address or "",
            b.ip_address or "",
            status_label,
            b.firewall_tag or "",
            b.reason or "",
            b.blocked_at or "",
            b.blocked_by or "",
            b.source_tag or "",
            block_type,
            unblock_label,
        ])

    output.seek(0)

    headers = {
        "Content-Disposition": "attachment; filename=blacklist.csv",
        "Content-Type": "text/csv",
    }

    return Response(content=output.getvalue(), headers=headers)
