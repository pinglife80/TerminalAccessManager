from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_permission, get_client_ip
from app.models.user import User
from app.models.compliance_baseline import ComplianceBaseline
from app.schemas.compliance_baseline import (
    ComplianceBaselineCreate,
    ComplianceBaselineUpdate,
    ComplianceBaselineResponse,
)
from app.schemas.data_source import ConnectionTestResult, SyncResult, DeletePreviewResponse, DeletePreviewAffected
from app.services.compliance_service import ComplianceService
from sqlalchemy import func


router = APIRouter(prefix="/compliance-baselines", tags=["Compliance Baselines"])


@router.get("/", response_model=List[ComplianceBaselineResponse])
async def list_baselines(
    type: Optional[str] = Query(None, description="Filter by type (ipguard)"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:read")),
):
    """List all compliance baselines"""
    from sqlalchemy import select
    stmt = select(ComplianceBaseline)
    if type:
        stmt = stmt.where(ComplianceBaseline.type == type)
    if enabled is not None:
        stmt = stmt.where(ComplianceBaseline.enabled == enabled)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=ComplianceBaselineResponse, status_code=status.HTTP_201_CREATED)
async def create_baseline(
    data: ComplianceBaselineCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:write")),
):
    """Create a new compliance baseline (requires baseline:write permission)"""
    # Check unique constraints
    from sqlalchemy import select
    if await db.execute(select(ComplianceBaseline).where(ComplianceBaseline.name == data.name)):
        existing = (await db.execute(select(ComplianceBaseline).where(ComplianceBaseline.name == data.name))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail=f"Baseline with name '{data.name}' already exists")
    existing_tag = (await db.execute(select(ComplianceBaseline).where(ComplianceBaseline.tag == data.tag))).scalar_one_or_none()
    if existing_tag:
        raise HTTPException(status_code=400, detail=f"Baseline with tag '{data.tag}' already exists")

    baseline = ComplianceBaseline(**data.model_dump())
    db.add(baseline)
    await db.commit()
    await db.refresh(baseline)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "create_baseline", "compliance", str(baseline.id),
                        {"message": "Created compliance baseline", "name": baseline.name,
                         "type": baseline.type, "tag": baseline.tag},
                        ip_address=get_client_ip(request))

    return baseline


@router.get("/{baseline_id}", response_model=ComplianceBaselineResponse)
async def get_baseline(
    baseline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:read")),
):
    """Get compliance baseline details by ID"""
    from sqlalchemy import select
    stmt = select(ComplianceBaseline).where(ComplianceBaseline.id == baseline_id)
    result = await db.execute(stmt)
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Compliance baseline not found")
    return baseline


@router.put("/{baseline_id}", response_model=ComplianceBaselineResponse)
async def update_baseline(
    baseline_id: int,
    data: ComplianceBaselineUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:write")),
):
    """Update a compliance baseline (requires baseline:write permission)"""
    from sqlalchemy import select
    stmt = select(ComplianceBaseline).where(ComplianceBaseline.id == baseline_id)
    result = await db.execute(stmt)
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Compliance baseline not found")

    update_data = data.model_dump(exclude_unset=True)

    # Prevent tag modification - tag is a system-wide identifier
    if "tag" in update_data and update_data["tag"] != baseline.tag:
        raise HTTPException(
            status_code=400,
            detail=f"Baseline tag cannot be changed. Tag '{baseline.tag}' is referenced by IPGuard cache and compliance checks. "
                   f"Please create a new baseline with the desired tag and delete the old one."
        )

    for key, value in update_data.items():
        setattr(baseline, key, value)
    await db.commit()
    await db.refresh(baseline)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "update_baseline", "compliance", str(baseline.id),
                        {"message": "Updated compliance baseline", "name": baseline.name, "tag": baseline.tag,
                         "changes": list(update_data.keys())},
                        ip_address=get_client_ip(request))

    return baseline


@router.post("/{baseline_id}/delete-preview", response_model=DeletePreviewResponse)
async def preview_delete_baseline(
    baseline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:write")),
):
    """Preview the impact of deleting a compliance baseline without making any changes"""
    from sqlalchemy import select
    stmt = select(ComplianceBaseline).where(ComplianceBaseline.id == baseline_id)
    result = await db.execute(stmt)
    baseline = result.scalar_one_or_none()
    if not baseline:
        return DeletePreviewResponse(
            can_delete=False,
            warnings=[],
            actions=[],
            affected=DeletePreviewAffected(),
            reason="Compliance baseline not found",
        )

    tag = baseline.tag
    name = baseline.name

    # Count terminals with compliance_status determined by this baseline
    from app.models.terminal import Terminal
    from app.models.data_source import DataSourceBinding

    # Count terminals with non-unknown compliance status
    terminal_stmt = select(Terminal).where(Terminal.compliance_status.in_(["compliant", "non_compliant"]))
    terminal_result = await db.execute(terminal_stmt)
    all_compliant_terminals = terminal_result.scalars().all()

    compliant_count = sum(1 for t in all_compliant_terminals if t.compliance_status == "compliant")
    non_compliant_count = sum(1 for t in all_compliant_terminals if t.compliance_status == "non_compliant")

    warnings = []
    actions = []

    if compliant_count > 0:
        warnings.append(f"该基准当前覆盖 {compliant_count} 个合规终端")
    if non_compliant_count > 0:
        warnings.append(f"该基准关联 {non_compliant_count} 个不合规终端")

    actions.append(f"清理 Redis 缓存 (ipguard:{tag})")
    actions.append(f"删除合规基准 [{name}]")
    actions.append("触发全量合规重算（不合规终端将被自动封堵）")

    return DeletePreviewResponse(
        can_delete=True,
        warnings=warnings,
        actions=actions,
        affected=DeletePreviewAffected(
            compliant_terminals=compliant_count + non_compliant_count,
        ),
    )


@router.delete("/{baseline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_baseline(
    baseline_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:write")),
):
    """Safely delete a compliance baseline with automatic cleanup (requires baseline:write permission)"""
    from sqlalchemy import select
    stmt = select(ComplianceBaseline).where(ComplianceBaseline.id == baseline_id)
    result = await db.execute(stmt)
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Compliance baseline not found")

    deleted_name = baseline.name
    deleted_tag = baseline.tag

    # Step 1: Delete the baseline
    await db.delete(baseline)
    await db.commit()

    # Step 2: Clean up Redis cache
    try:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        if redis_client:
            cache_key = f"ipguard:{deleted_tag}"
            await redis_client.delete(cache_key)
    except Exception as e:
        from loguru import logger
        logger.warning(f"Failed to clean Redis cache for baseline {deleted_tag}: {e}")

    # Step 3: Trigger compliance recalculation
    try:
        from app.services.compliance_service import ComplianceService
        cs = ComplianceService(db)
        await cs.recalculate_all_compliance()
    except Exception as e:
        from loguru import logger
        logger.warning(f"Failed to trigger compliance recalculation after baseline deletion: {e}")

    # Step 4: Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "delete_baseline", "compliance", str(baseline_id),
                        {"message": "Safely deleted compliance baseline with cleanup", "name": deleted_name, "tag": deleted_tag},
                        ip_address=get_client_ip(request))


@router.post("/{baseline_id}/test", response_model=ConnectionTestResult)
async def test_baseline_connection(
    baseline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:test")),
):
    """Test connection to a compliance baseline (requires baseline:test permission)"""
    from sqlalchemy import select
    stmt = select(ComplianceBaseline).where(ComplianceBaseline.id == baseline_id)
    result = await db.execute(stmt)
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Compliance baseline not found")

    if baseline.type == "ipguard":
        try:
            from app.core.crypto import decrypt_config
            config = baseline.config
            if config:
                config = decrypt_config(config)
            db_type = config.get("db_type", "postgresql")
            host = config.get("host", "")
            port = config.get("port", 3306)
            username = config.get("username", "")
            password = config.get("password", "")
            database = config.get("database", "ipguard")

            if db_type == "mssql":
                import pyodbc
                conn_str = (
                    f"DRIVER={{FreeTDS}};"
                    f"SERVER={host};"
                    f"PORT={port};"
                    f"DATABASE={database};"
                    f"UID={username};"
                    f"PWD={password};"
                    f"TDS_Version=7.3;"
                )
                conn = pyodbc.connect(conn_str, timeout=10)
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                conn.close()
            elif db_type == "mysql":
                import aiomysql
                conn = await aiomysql.connect(
                    host=host, port=int(port),
                    user=username, password=password,
                    db=database, connect_timeout=10,
                )
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                conn.close()
            else:
                import asyncpg
                conn = await asyncpg.connect(
                    host=host, port=int(port),
                    user=username, password=password,
                    database=database, timeout=10,
                )
                await conn.execute("SELECT 1")
                await conn.close()
            return ConnectionTestResult(success=True, message=f"Connection successful ({db_type})")
        except Exception as e:
            return ConnectionTestResult(success=False, message=f"Connection failed: {str(e)}")
    else:
        return ConnectionTestResult(success=False, message=f"Test not supported for type: {baseline.type}")


@router.post("/{baseline_id}/sync", response_model=SyncResult)
async def sync_baseline(
    baseline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("baseline:sync")),
):
    """Manually trigger sync for a compliance baseline (requires baseline:sync permission)"""
    from sqlalchemy import select
    stmt = select(ComplianceBaseline).where(ComplianceBaseline.id == baseline_id)
    result = await db.execute(stmt)
    baseline = result.scalar_one_or_none()
    if not baseline:
        raise HTTPException(status_code=404, detail="Compliance baseline not found")

    if not baseline.enabled:
        raise HTTPException(status_code=400, detail="Compliance baseline is disabled")

    if baseline.type == "ipguard":
        compliance_service = ComplianceService(db)
        sync_result = await compliance_service.sync_ipguard_data(baseline.tag)
        return SyncResult(
            success=sync_result.get("success", False),
            message=sync_result.get("message", ""),
            entries_processed=sync_result.get("entries", 0),
        )
    else:
        raise HTTPException(status_code=400, detail=f"Sync not supported for type: {baseline.type}")
