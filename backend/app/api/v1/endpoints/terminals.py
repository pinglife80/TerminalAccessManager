import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.models.terminal import Terminal
from app.models.user import User
from app.schemas.terminal import PaginatedResponse, ResponseMessage, TerminalQuery, TerminalResponse
from app.services.terminal_service import TerminalService

router = APIRouter(prefix="/terminals", tags=["Terminals"])


@router.get("/", response_model=list[TerminalResponse])
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
    block_state: str = Query(None, description="Filter by block_state (no_firewall/block_failed)"),
    arp_enabled_only: bool = Query(False, description="Restrict to enabled ARP data sources"),
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
        block_state=block_state,
        arp_enabled_only=arp_enabled_only,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )

    service = TerminalService(db)
    results = await service.search_macs(query)
    total = await service.search_macs_count(query)
    return {"items": results, "total": total, "skip": skip, "limit": limit}


@router.get("/export")
async def export_terminals(
    ip: str = Query(None, description="Filter by IP address"),
    mac: str = Query(None, description="Filter by MAC address"),
    status_filter: str = Query(None, alias="status", description="Filter by status"),
    compliance_status: str = Query(None, description="Filter by compliance status"),
    source_tag: str = Query(None, description="Filter by source tag"),
    firewall_tag: str = Query(None, description="Filter by firewall tag (via blacklist)"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("terminal:read"))
):
    """Export terminals as CSV with filtering support"""
    from sqlalchemy import select, or_, and_, desc, func
    from app.models.blacklist import Blacklist
    from app.services.terminal_service import _parse_date_range, _escape_like, _normalize_mac

    conditions = []

    ip_mac_conditions = []
    if ip:
        ip_mac_conditions.append(Terminal.ip_address.ilike(f"%{_escape_like(ip)}%"))
    if mac:
        mac_clean = _normalize_mac(mac)
        ip_mac_conditions.append(Terminal.mac_address_normalized.ilike(f"%{_escape_like(mac_clean)}%"))

    if ip_mac_conditions:
        conditions.append(or_(*ip_mac_conditions))

    if status_filter:
        conditions.append(Terminal.status == status_filter)

    if compliance_status:
        conditions.append(Terminal.compliance_status == compliance_status)

    if source_tag:
        conditions.append(Terminal.source_tag == source_tag)

    if firewall_tag:
        fw_subquery = (
            select(Blacklist.ip_address)
            .where(Blacklist.firewall_tag == firewall_tag)
            .correlate(Terminal)
        )
        conditions.append(Terminal.ip_address.in_(fw_subquery))

    date_conditions = _parse_date_range(start_date, end_date)
    for dc in date_conditions:
        conditions.append(dc(Terminal.timestamp))

    stmt = (
        select(Terminal)
        .where(and_(*conditions) if conditions else True)
        .order_by(desc(Terminal.timestamp))
    )

    result = await db.execute(stmt)
    terminals = result.scalars().all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "MAC Address", "IP Address", "Status", "Source", "Source Tag",
        "Compliance Status", "Whitelist Match", "Firewall Tag", "Added", "Comments"
    ])

    for t in terminals:
        writer.writerow([
            t.mac_address or "",
            t.ip_address or "",
            t.status or "",
            t.source or "",
            t.source_tag or "",
            t.compliance_status or "",
            t.wl_match_type or "",
            t.firewall_tag or "",
            t.timestamp or "",
            t.comments or ""
        ])

    output.seek(0)

    headers = {
        "Content-Disposition": "attachment; filename=terminals.csv",
        "Content-Type": "text/csv",
    }

    return Response(content=output.getvalue(), headers=headers)


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
