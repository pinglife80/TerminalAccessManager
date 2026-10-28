import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_client_ip, get_current_user, require_permission
from app.models.user import User
from app.schemas.compliance_scope import (
    ComplianceScopeCreate,
    ComplianceScopeListResponse,
    ComplianceScopeResponse,
    ComplianceScopeUpdate,
)
from app.services.compliance_scope_service import ComplianceScopeService
from app.services.terminal_service import TerminalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance-scope", tags=["compliance-scope"])


async def _log_scope_action(
    db: AsyncSession,
    current_user: User,
    request: Request,
    action: str,
    scope,
) -> None:
    """Record an audit log entry for a compliance scope mutation."""
    await TerminalService(db).log_action(
        current_user.username,
        action,
        "compliance_scope",
        str(scope.id),
        {
            "scope_type": scope.scope_type,
            "scope_value": scope.scope_value,
            "description": scope.description,
            "is_active": scope.is_active,
        },
        ip_address=get_client_ip(request),
        resource_name=scope.description or scope.scope_value,
        user_id=current_user.id,
    )


@router.get("", response_model=ComplianceScopeListResponse)
async def list_scopes(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:read")),
):
    service = ComplianceScopeService(db)
    items = await service.list_scopes(is_active=is_active)
    return ComplianceScopeListResponse(
        items=[ComplianceScopeResponse.model_validate(item) for item in items],
        total=len(items),
    )


@router.post("", response_model=ComplianceScopeResponse)
async def create_scope(
    data: ComplianceScopeCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = ComplianceScopeService(db)
    try:
        scope = await service.create_scope(data, current_user.username)
        await _log_scope_action(db, current_user, request, "create_scope", scope)
        return ComplianceScopeResponse.model_validate(scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{scope_id}", response_model=ComplianceScopeResponse)
async def get_scope(
    scope_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:read")),
):
    service = ComplianceScopeService(db)
    scope = await service.get_scope(scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Compliance scope not found")
    return ComplianceScopeResponse.model_validate(scope)


@router.put("/{scope_id}", response_model=ComplianceScopeResponse)
async def update_scope(
    scope_id: int,
    data: ComplianceScopeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = ComplianceScopeService(db)
    try:
        scope = await service.update_scope(scope_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not scope:
        raise HTTPException(status_code=404, detail="Compliance scope not found")
    await _log_scope_action(db, current_user, request, "update_scope", scope)
    return ComplianceScopeResponse.model_validate(scope)


@router.delete("/{scope_id}")
async def delete_scope(
    scope_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = ComplianceScopeService(db)
    scope = await service.get_scope(scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Compliance scope not found")
    success = await service.delete_scope(scope_id)
    if not success:
        raise HTTPException(status_code=404, detail="Compliance scope not found")
    await _log_scope_action(db, current_user, request, "delete_scope", scope)
    return {"success": True, "message": f"Deleted compliance scope {scope_id}"}


@router.post("/{scope_id}/toggle", response_model=ComplianceScopeResponse)
async def toggle_scope(
    scope_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = ComplianceScopeService(db)
    scope = await service.toggle_scope(scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Compliance scope not found")
    await _log_scope_action(db, current_user, request, "toggle_scope", scope)
    return ComplianceScopeResponse.model_validate(scope)
