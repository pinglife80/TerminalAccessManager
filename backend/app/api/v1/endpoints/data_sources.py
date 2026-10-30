import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_client_ip, require_permission
from app.models.blacklist import Blacklist
from app.models.data_source import DataSourceBinding
from app.models.user import User
from app.schemas.data_source import (
    AutoBlockRequest,
    AutoBlockResult,
    AutoUnblockResult,
    ComplianceCheckRequest,
    ComplianceCheckResult,
    ConnectionTestResult,
    DataSourceBindingCreate,
    DataSourceBindingResponse,
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    DeletePreviewResponse,
    DeleteTaskResponse,
    DeleteTaskStatusResponse,
    SyncResult,
)
from app.services.arp_collector_service import ArpCollectorService
from app.services.compliance_service import ComplianceService
from app.services.data_source_service import DataSourceService
from app.services.data_source_tasks import (
    run_delete_binding_task,
    run_delete_data_source_task,
)
from app.services.task_state import get_task_state, now_iso, set_task_state

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/data-sources", tags=["Data Sources"])

# Keep strong references to running background tasks so they are not garbage
# collected before completion (asyncio only holds weak references).
_running_tasks: set[asyncio.Task] = set()


def _submit_delete_task(coro) -> str:
    """Schedule a background deletion coroutine and return its task id."""
    task_id = uuid.uuid4().hex
    task = asyncio.create_task(coro(task_id))
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)
    return task_id


# ------------------------------------------------------------------
# DataSource CRUD
# ------------------------------------------------------------------
@router.get("/", response_model=list[DataSourceResponse])
async def list_data_sources(
    type: str | None = Query(None, description="Filter by type (arp_ssh, arp_api, sangfor)"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
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
                            ip_address=get_client_ip(request),
                            resource_name=source.name,
                            user_id=current_user.id)

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


@router.post("/{source_id}/disable-preview")
async def disable_preview_data_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:read")),
):
    """Preview the impact of disabling a data source (read-only, no modifications).

    Returns warnings and affected resource counts to help the user make an
    informed decision before disabling.
    """
    service = DataSourceService(db)
    source = await service.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    if not source.enabled:
        return {"can_disable": True, "warnings": [], "affected_terminals": 0, "actions": []}

    warnings = []
    actions = []
    affected_terminals = 0

    if source.type == "sangfor":
        blocked_stmt = select(Blacklist).where(Blacklist.firewall_tag == source.tag)
        bl_result = await db.execute(blocked_stmt)
        blocked_entries = bl_result.scalars().all()
        if blocked_entries:
            warnings.append(
                f"该防火墙下有 {len(blocked_entries)} 条封堵记录，禁用后自动解封将失败，"
                f"直到防火墙重新启用。已封堵终端将保持封堵状态但无法通过系统解封。"
            )
            actions.append({
                "action": "block_retained",
                "description": f"{len(blocked_entries)} 条封堵记录将保留但无法自动解封",
                "firewall_tag": source.tag,
                "count": len(blocked_entries),
            })

    elif source.type in ("arp_ssh", "arp_api"):
        from app.models.terminal import Terminal
        terminal_stmt = select(Terminal).where(
            Terminal.source_tag == source.tag,
            Terminal.compliance_status != "unknown"
        )
        t_result = await db.execute(terminal_stmt)
        affected = t_result.scalars().all()
        affected_terminals = len(affected)

        if affected:
            compliant_count = sum(1 for t in affected if t.compliance_status == "compliant")
            bypass_count = sum(1 for t in affected if t.compliance_status == "bypass")
            non_compliant_count = sum(1 for t in affected if t.compliance_status == "non_compliant")
            warnings.append(
                f"禁用后该数据源下 {affected_terminals} 个终端的合规状态将重置为「待判定」："
                f"合规 {compliant_count} 个、白名单旁路 {bypass_count} 个、不合规 {non_compliant_count} 个。"
                f"重新启用后需手动触发合规检查恢复状态。"
            )
            actions.append({
                "action": "compliance_reset",
                "description": f"{affected_terminals} 个终端合规状态将重置为「待判定」",
                "count": affected_terminals,
            })

        # Check for bound firewalls with blocked terminals
        binding_stmt = select(DataSourceBinding).where(DataSourceBinding.arp_source_tag == source.tag)
        b_result = await db.execute(binding_stmt)
        bindings = b_result.scalars().all()
        if bindings:
            for binding in bindings:
                bl_stmt = select(Blacklist).where(
                    Blacklist.firewall_tag == binding.firewall_tag,
                    Blacklist.source_tag == source.tag
                )
                bl_result = await db.execute(bl_stmt)
                bl_entries = bl_result.scalars().all()
                if bl_entries:
                    warnings.append(
                        f"该数据源下有 {len(bl_entries)} 个终端在防火墙 [{binding.firewall_tag}] 上被封堵，"
                        f"禁用后过期自动解封仍可执行，但合规状态变更不会触发自动封堵/解封。"
                    )
                    actions.append({
                        "action": "block_retained",
                        "description": f"{len(bl_entries)} 个终端在防火墙 [{binding.firewall_tag}] 上保持封堵",
                        "firewall_tag": binding.firewall_tag,
                        "count": len(bl_entries),
                    })

    return {
        "can_disable": True,
        "warnings": warnings,
        "affected_terminals": affected_terminals,
        "actions": actions,
    }


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
    warnings = []

    # Check disable impact and collect warnings
    if data.enabled is False:
        current_source = await service.get_data_source_by_id(source_id)
        if current_source and current_source.enabled is True:
            if current_source.type == "sangfor":
                blocked_stmt = select(Blacklist).where(Blacklist.firewall_tag == current_source.tag)
                bl_result = await db.execute(blocked_stmt)
                blocked_count = len(bl_result.scalars().all())
                if blocked_count > 0:
                    warn_msg = (
                        f"该防火墙下有 {blocked_count} 条封堵记录，禁用后自动解封将失败，"
                        f"直到防火墙重新启用。已封堵终端将保持封堵状态但无法通过系统解封。"
                    )
                    warnings.append(warn_msg)
                    logger.warning(
                        f"Disabling Sangfor firewall '{current_source.tag}' with {blocked_count} blocked entries. "
                        f"Auto-unblock will fail until firewall is re-enabled."
                    )

            elif current_source.type in ("arp_ssh", "arp_api"):
                from app.models.terminal import Terminal
                # Count affected terminals before reset
                terminal_stmt = select(Terminal).where(
                    Terminal.source_tag == current_source.tag,
                    Terminal.compliance_status != "unknown",
                    Terminal.status != "blocked",
                )
                t_result = await db.execute(terminal_stmt)
                affected_terminals = t_result.scalars().all()
                if affected_terminals:
                    compliant_count = sum(1 for t in affected_terminals if t.compliance_status == "compliant")
                    bypass_count = sum(1 for t in affected_terminals if t.compliance_status == "bypass")
                    non_compliant_count = sum(1 for t in affected_terminals if t.compliance_status == "non_compliant")
                    warn_msg = (
                        f"禁用后该数据源下 {len(affected_terminals)} 个终端的合规状态将重置为「待判定」："
                        f"合规 {compliant_count} 个、白名单旁路 {bypass_count} 个、不合规 {non_compliant_count} 个。"
                        f"重新启用后需手动触发合规检查恢复状态。"
                    )
                    warnings.append(warn_msg)

                    for terminal in affected_terminals:
                        terminal.compliance_status = "unknown"
                    await db.flush()
                    logger.info(
                        f"Reset compliance status to 'unknown' for {len(affected_terminals)} terminals "
                        f"under disabled ARP source '{current_source.tag}'"
                    )

                # Check for bound firewalls with blocked terminals
                binding_stmt = select(DataSourceBinding).where(DataSourceBinding.arp_source_tag == current_source.tag)
                b_result = await db.execute(binding_stmt)
                bindings = b_result.scalars().all()
                if bindings:
                    for binding in bindings:
                        bl_stmt = select(Blacklist).where(Blacklist.firewall_tag == binding.firewall_tag,
                                                          Blacklist.source_tag == current_source.tag)
                        bl_result = await db.execute(bl_stmt)
                        bl_count = len(bl_result.scalars().all())
                        if bl_count > 0:
                            warnings.append(
                                f"该数据源下有 {bl_count} 个终端在防火墙 [{binding.firewall_tag}] 上被封堵，"
                                f"禁用后过期自动解封仍可执行，但合规状态变更不会触发自动封堵/解封。"
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
        audit_details = {"message": "Updated datasource", "name": source.name, "tag": source.tag}
        if data.enabled is not None:
            audit_details["enabled"] = data.enabled
        if warnings:
            audit_details["warnings"] = warnings
        await ts.log_action(current_user.username, "update_datasource", "datasource", str(source.id),
                            audit_details, ip_address=get_client_ip(request),
                            resource_name=source.name,
                            user_id=current_user.id)

        # When enabling an ARP source, trigger compliance recalculation for its terminals
        if data.enabled is True and source.type in ("arp_ssh", "arp_api"):
            try:
                from app.services.compliance_service import ComplianceService
                compliance_svc = ComplianceService(db)
                await compliance_svc.invalidate_whitelist_cache()
                recalc_result = await compliance_svc.recalculate_all_compliance()
                logger.info(f"ARP source '{source.tag}' enabled, compliance recalculation: {recalc_result}")
            except Exception as e:
                logger.warning(f"Failed to recalculate compliance after enabling ARP source '{source.tag}': {e}")

        # Attach warnings to response
        source_dict = DataSourceResponse.model_validate(source)
        if warnings:
            source_dict.warnings = warnings
        return source_dict
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


@router.delete("/{source_id}", response_model=DeleteTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def delete_data_source(
    source_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Submit a background task to safely delete a data source (requires datasource:write permission)"""
    service = DataSourceService(db)
    source = await service.get_data_source_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    username = current_user.username
    client_ip = get_client_ip(request)

    task_id = _submit_delete_task(
        lambda tid: run_delete_data_source_task(tid, source_id, username, client_ip)
    )
    await set_task_state(task_id, {
        "status": "pending",
        "kind": "source",
        "submitted_at": now_iso(),
    })

    return DeleteTaskResponse(task_id=task_id, status="pending", kind="source")


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
                         "tag": source.tag, "success": result.success},
                        ip_address=get_client_ip(request),
                        resource_name=source.name,
                        user_id=current_user.id)

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
                        {"message": "Synced datasource", "name": source.name, "type": source.type},
                        ip_address=get_client_ip(request),
                        resource_name=source.name,
                        user_id=current_user.id)

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
@router.get("/bindings/", response_model=list[DataSourceBindingResponse])
async def list_bindings(
    arp_source_tag: str | None = Query(None, description="Filter by ARP source tag"),
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
                            ip_address=get_client_ip(request),
                            resource_name=f"{data.arp_source_tag} -> {data.firewall_tag}",
                            user_id=current_user.id)

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


@router.delete("/bindings/{binding_id}", response_model=DeleteTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def delete_binding(
    binding_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("datasource:write")),
):
    """Submit a background task to safely delete a data source binding (requires datasource:write permission)"""
    binding = await db.get(DataSourceBinding, binding_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Binding not found",
        )

    username = current_user.username
    client_ip = get_client_ip(request)

    task_id = _submit_delete_task(
        lambda tid: run_delete_binding_task(tid, binding_id, username, client_ip)
    )
    await set_task_state(task_id, {
        "status": "pending",
        "kind": "binding",
        "submitted_at": now_iso(),
    })

    return DeleteTaskResponse(task_id=task_id, status="pending", kind="binding")


@router.get("/delete-tasks/{task_id}", response_model=DeleteTaskStatusResponse)
async def get_delete_task_status(
    task_id: str,
    current_user: User = Depends(require_permission("datasource:read")),
):
    """Poll the status of a submitted background deletion task."""
    state = await get_task_state(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return DeleteTaskStatusResponse(
        task_id=task_id,
        status=state.get("status", "unknown"),
        kind=state.get("kind", "source"),
        message=state.get("message"),
        error=state.get("error"),
        submitted_at=state.get("submitted_at"),
        finished_at=state.get("finished_at"),
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
    from sqlalchemy import and_, select

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

    # Map each classified result back to its Terminal by (ip, mac), then apply it
    # through the standard first-discovery path so that threshold-based
    # de-duplication, audit logging, and blocking all apply consistently.
    # This replaces the previous direct `entry.compliance_status = ...` write,
    # which bypassed the confirm threshold, produced no audit log, and never
    # actually blocked the terminal.
    decision_by_terminal = {}
    if check_result.details:
        for status_key in ("bypass", "compliant", "non_compliant"):
            for item in check_result.details.get(status_key, []):
                key = (item.get("ip_address"), item.get("mac_address"))
                if key not in decision_by_terminal:
                    decision_by_terminal[key] = item

    pending_audits = []
    for entry in entries:
        item = decision_by_terminal.get((entry.ip_address, entry.mac_address))
        if not item:
            continue
        apply_result = await compliance_service.apply_initial_compliance_result(
            entry,
            item.get("compliance_status"),
            item.get("wl_match_type"),
            item.get("wl_comments"),
            entry.ip_address or "",
            entry.mac_address or "",
            ip_found=item.get("ip_found", False),
            mac_found=item.get("mac_found", False),
            use_ip_only=item.get("use_ip_only", False),
        )
        if apply_result and apply_result.get("audit"):
            pending_audits.append(apply_result["audit"])

    await db.commit()
    for audit in pending_audits:
        await compliance_service.log_action(
            audit["username"], audit["action"], audit["resource_type"],
            audit["resource_id"], audit["details"],
            ip_address=audit.get("ip_address"),
        )

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
