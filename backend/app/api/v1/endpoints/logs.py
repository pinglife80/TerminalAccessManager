from typing import List
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_
import csv
from io import StringIO

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.log import AuditLog
from app.schemas.terminal import AuditLogResponse, AuditLogQuery
from app.services.terminal_service import TerminalService, _parse_date_range

router = APIRouter(prefix="/logs", tags=["Audit Logs"])


@router.get("/export")
async def export_audit_logs(
    username: str = Query(None, description="Filter by username"),
    action: str = Query(None, description="Filter by action type"),
    search: str = Query(None, description="Search by IP, username, or details"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export audit logs as CSV with filtering support"""
    conditions = []

    if username:
        conditions.append(AuditLog.username == username)
    if action:
        conditions.append(AuditLog.action == action)
    if search:
        search_term = f"%{search}%"
        conditions.append(
            or_(
                AuditLog.ip_address.ilike(search_term),
                AuditLog.username.ilike(search_term),
                AuditLog.details.ilike(search_term),
            )
        )

    date_conditions = _parse_date_range(start_date, end_date)
    for dc in date_conditions:
        conditions.append(dc(AuditLog.timestamp))

    stmt = select(AuditLog)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(AuditLog.timestamp))

    result = await db.execute(stmt)
    logs = result.scalars().all()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Timestamp", "Username", "Action",
        "Resource Type", "Resource ID", "IP Address", "Details"
    ])

    for log in logs:
        writer.writerow([
            log.id,
            log.timestamp,
            log.username,
            log.action,
            log.resource_type or "",
            log.resource_id or "",
            log.ip_address or "",
            log.details or ""
        ])

    output.seek(0)

    headers = {
        "Content-Disposition": "attachment; filename=audit_logs.csv",
        "Content-Type": "text/csv",
    }

    return Response(content=output.getvalue(), headers=headers)


@router.get("/", response_model=List[AuditLogResponse])
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get audit logs with pagination"""
    stmt = (
        select(AuditLog)
        .order_by(desc(AuditLog.timestamp))
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(stmt)
    logs = result.scalars().all()

    return logs


@router.get("/search", response_model=List[AuditLogResponse])
async def search_audit_logs(
    username: str = Query(None, description="Filter by username"),
    action: str = Query(None, description="Filter by action type"),
    search: str = Query(None, description="Search by IP, username, or details"),
    start_date: str = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search audit logs by various criteria with date range and keyword filtering"""
    query = AuditLogQuery(
        username=username,
        action=action,
        search=search,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )

    service = TerminalService(db)
    logs = await service.search_audit_logs(query)
    return logs
