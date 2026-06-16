from typing import List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.models.data_source import DataSource, DataSourceBinding
from app.models.blacklist import Blacklist
from app.schemas.data_source import (
    DataSourceCreate,
    DataSourceUpdate,
    DataSourceResponse,
    DataSourceBindingCreate,
    DataSourceBindingResponse,
    ConnectionTestResult,
    SyncResult,
    ComplianceCheckRequest,
    ComplianceCheckResult,
    AutoBlockRequest,
    AutoBlockResult,
    AutoUnblockResult,
    DeletePreviewResponse,
    DeletePreviewAffected,
)
from app.services.data_source_service import DataSourceService
from app.services.arp_collector_service import ArpCollectorService
from app.services.compliance_service import ComplianceService

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/data-sources", tags=["Data Sources"])


# ------------------------------------------------------------------
# DataSource CRUD
# ------------------------------------------------------------------
@router.get("/", response_model=List[DataSourceResponse])
async def list_data_sources(
    type: Optional[str] = Query(None, description="Filter by type (arp_ssh, arp_api, sangfor)"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:read")),
):
    """List all data sources with optional filtering"""
    service = DataSourceService(db)
    sources = await service.list_data_sources(type=type, enabled=enabled)
    return sources


@router.post("/", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    data: DataSourceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Create a new data source (requires datasource:write permission)"""
    service = DataSourceService(db)
    try:
        source = await service.create_data_source(data)

        # Audit log
        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(current_user.username, "create_datasource", "datasource", str(source.id),
                            {"message": "Created datasource", "name": source.name,
                             "type": source.type, "tag": source.tag},
                            ip_address=request.client.host if request.client else None)

        return source
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{source_id}", response_model=DataSourceResponse)
async def get_data_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:read")),
):
    """Get data source details by ID"""
    service = DataSourceService(db)
    source = await service.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )
    return source


@router.put("/{source_id}", response_model=DataSourceResponse)
async def update_data_source(
    source_id: int,
    data: DataSourceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Update a data source (requires datasource:write permission)"""
    service = DataSourceService(db)

    # Check disable impact for Sangfor firewalls with blocked terminals
    if data.enabled is False:
        current_source = await service.get_data_source_by_id(source_id)
        if current_source and current_source.enabled is True and current_source.type == "sangfor":
            blocked_stmt = select(Blacklist).where(Blacklist.firewall_tag == current_source.tag)
            bl_result = await db.execute(blocked_stmt)
            blocked_count = len(bl_result.scalars().all())
            if blocked_count > 0:
                logger.warning(
                    f"Disabling Sangfor firewall '{current_source.tag}' with {blocked_count} blocked entries. "
                    f"Auto-unblock will fail until firewall is re-enabled."
                )

        # Reset compliance status to unknown when disabling ARP source
        if current_source and current_source.enabled is True and current_source.type in ("arp_ssh", "arp_api"):
            from app.models.terminal import Terminal, TerminalStatus
            terminal_stmt = select(Terminal).where(
                Terminal.source_tag == current_source.tag,
                Terminal.compliance_status != "unknown"
            )
            t_result = await db.execute(terminal_stmt)
            affected_terminals = t_result.scalars().all()
            if affected_terminals:
                for terminal in affected_terminals:
                    terminal.compliance_status = "unknown"
                await db.flush()
                logger.info(
                    f"Reset compliance status to 'unknown' for {len(affected_terminals)} terminals "
                    f"under disabled ARP source '{current_source.tag}'"
                )

    try:
        source = await service.update_data_source(source_id, data)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Data source not found",
            )

        # Audit log
        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(current_user.username, "update_datasource", "datasource", str(source.id),
                            {"message": "Updated datasource", "name": source.name, "tag": source.tag},
                            ip_address=request.client.host if request.client else None)

        return source
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{source_id}/delete-preview", response_model=DeletePreviewResponse)
async def preview_delete_data_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Preview the impact of deleting a data source without making any changes"""
    service = DataSourceService(db)
    preview = await service.preview_delete_data_source(source_id)
    return preview


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Safely delete a data source with automatic cleanup (requires datasource:write permission)"""
    service = DataSourceService(db)
    source = await service.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    deleted = await service.safe_delete_data_source(
        source_id,
        username=current_user.username,
        client_ip=request.client.host if request.client else None,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )


@router.post("/{source_id}/test", response_model=ConnectionTestResult)
async def test_data_source_connection(
    source_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:test")),
):
    """Test connection to a data source (requires datasource:test permission)"""
    service = DataSourceService(db)
    source = await service.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    result = await service.test_connection(source_id)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "test_datasource", "datasource", str(source_id),
                        {"message": "Tested datasource connection", "name": source.name,
                         "success": result.success},
                        ip_address=request.client.host if request.client else None)

    return result


@router.post("/{source_id}/sync", response_model=SyncResult)
async def sync_data_source(
    source_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:sync")),
):
    """Manually trigger data sync for a data source (requires datasource:sync permission)"""
    service = DataSourceService(db)
    source = await service.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    if not source.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data source is disabled",
        )

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "sync_datasource", "datasource", str(source_id),
                        {"message": "Synced datasource", "name": source.name},
                        ip_address=request.client.host if request.client else None)

    if source.type == "arp_ssh":
        arp_service = ArpCollectorService(db)
        result = await arp_service.collect_from_ssh(source)
        return result
    elif source.type == "arp_api":
        arp_service = ArpCollectorService(db)
        result = await arp_service.collect_from_api(source)
        return result
    elif source.type == "sangfor":
        # Sangfor is a push-type firewall, not a data collection source.
        # "Sync" has no meaning for Sangfor; use "Test Connection" instead.
        return SyncResult(
            success=True,
            message="Sync is not applicable for Sangfor firewalls. Use 'Test Connection' to verify connectivity.",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sync not supported for data source type: {source.type}",
        )


# ------------------------------------------------------------------
# DataSourceBinding CRUD
# ------------------------------------------------------------------
@router.get("/bindings/", response_model=List[DataSourceBindingResponse])
async def list_bindings(
    arp_source_tag: Optional[str] = Query(None, description="Filter by ARP source tag"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:read")),
):
    """List all data source bindings"""
    service = DataSourceService(db)
    bindings = await service.list_bindings(arp_source_tag=arp_source_tag)
    return bindings


@router.post("/bindings/", response_model=DataSourceBindingResponse, status_code=status.HTTP_201_CREATED)
async def create_binding(
    data: DataSourceBindingCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Create a binding between an ARP source and a firewall (requires datasource:write permission)"""
    service = DataSourceService(db)
    try:
        binding = await service.create_binding(data.arp_source_tag, data.firewall_tag)

        # Audit log
        from app.services.terminal_service import TerminalService
        ts = TerminalService(db)
        await ts.log_action(current_user.username, "bind_datasource", "datasource", str(binding.id),
                            {"message": "Created datasource binding", "arp_source_tag": data.arp_source_tag,
                             "firewall_tag": data.firewall_tag},
                            ip_address=request.client.host if request.client else None)

        return binding
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/bindings/{binding_id}/delete-preview", response_model=DeletePreviewResponse)
async def preview_delete_binding(
    binding_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Preview the impact of deleting a data source binding without making any changes"""
    service = DataSourceService(db)
    preview = await service.preview_delete_binding(binding_id)
    return preview


@router.delete("/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_binding(
    binding_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Safely delete a data source binding with automatic cleanup (requires datasource:write permission)"""
    service = DataSourceService(db)
    deleted = await service.safe_delete_binding(
        binding_id,
        username=current_user.username,
        client_ip=request.client.host if request.client else None,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Binding not found",
        )


# ------------------------------------------------------------------
# Compliance Operations
# ------------------------------------------------------------------
@router.post("/compliance/check", response_model=ComplianceCheckResult)
async def compliance_check(
    request: ComplianceCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:compliance")),
):
    """Manually trigger compliance check (requires datasource:compliance permission)"""
    from sqlalchemy import select, and_
    from app.models.terminal import Terminal

    compliance_service = ComplianceService(db)

    # Build query for entries to check
    conditions = []
    if request.arp_source_tag:
        conditions.append(Terminal.source_tag == request.arp_source_tag)
    if not request.force:
        conditions.append(Terminal.compliance_status == "unknown")

    stmt = select(Terminal)
    if conditions:
        stmt = stmt.where(and_(*conditions))

    result = await db.execute(stmt)
    entries = result.scalars().all()

    if not entries:
        return ComplianceCheckResult(
            total_checked=0,
            compliant=0,
            bypass=0,
            non_compliant=0,
            unknown=0,
            message="No entries to check",
        )

    check_entries = [
        {
            "ip_address": e.ip_address,
            "mac_address": e.mac_address,
            "source_tag": e.source_tag,
        }
        for e in entries
    ]

    check_result = await compliance_service.batch_check_compliance(check_entries)

    # Update compliance_status for each entry
    bypass_ips = set()
    compliant_ips = set()
    non_compliant_ips = set()

    if check_result.details:
        for item in check_result.details.get("bypass", []):
            bypass_ips.add(item.get("ip_address"))
        for item in check_result.details.get("compliant", []):
            compliant_ips.add(item.get("ip_address"))
        for item in check_result.details.get("non_compliant", []):
            non_compliant_ips.add(item.get("ip_address"))

    for entry in entries:
        if entry.ip_address in bypass_ips:
            entry.compliance_status = "bypass"
        elif entry.ip_address in compliant_ips:
            entry.compliance_status = "compliant"
        elif entry.ip_address in non_compliant_ips:
            entry.compliance_status = "non_compliant"

    await db.commit()

    return check_result


@router.post("/compliance/auto-block", response_model=AutoBlockResult)
async def auto_block(
    request: AutoBlockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:compliance")),
):
    """Manually trigger auto-block of non-compliant terminals (requires datasource:compliance permission)"""
    compliance_service = ComplianceService(db)
    result = await compliance_service.auto_block_non_compliant(
        arp_source_tag=request.arp_source_tag,
        block_time=request.block_time,
        dry_run=request.dry_run,
    )
    return result


@router.post("/compliance/auto-unblock", response_model=AutoUnblockResult)
async def auto_unblock(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:compliance")),
):
    """Manually trigger auto-unblock of compliant terminals (requires datasource:compliance permission)"""
    compliance_service = ComplianceService(db)
    result = await compliance_service.auto_unblock_compliant()
    return result
