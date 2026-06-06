from typing import List
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import csv
from io import StringIO

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.log import AuditLog
from app.schemas.mac_address import AuditLogResponse

router = APIRouter(prefix="/logs", tags=["Audit Logs"])


@router.get("/export")
async def export_audit_logs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export audit logs as CSV"""
    stmt = select(AuditLog).order_by(desc(AuditLog.timestamp))
    
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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search audit logs by criteria"""
    conditions = []
    
    if username:
        conditions.append(AuditLog.username == username)
    
    if action:
        conditions.append(AuditLog.action == action)
    
    from sqlalchemy import and_
    
    stmt = (
        select(AuditLog)
        .where(and_(*conditions) if conditions else True)
        .order_by(desc(AuditLog.timestamp))
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    return logs
