import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.compliance_scope import (
    ComplianceScopeCreate,
    ComplianceScopeListResponse,
    ComplianceScopeResponse,
    ComplianceScopeUpdate,
)
from app.services.compliance_scope_service import ComplianceScopeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance-scope", tags=["compliance-scope"])


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = ComplianceScopeService(db)
    try:
        scope = await service.create_scope(data, current_user.username)
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
    return ComplianceScopeResponse.model_validate(scope)


@router.delete("/{scope_id}")
async def delete_scope(
    scope_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = ComplianceScopeService(db)
    success = await service.delete_scope(scope_id)
    if not success:
        raise HTTPException(status_code=404, detail="Compliance scope not found")
    return {"success": True, "message": f"Deleted compliance scope {scope_id}"}


@router.post("/{scope_id}/toggle", response_model=ComplianceScopeResponse)
async def toggle_scope(
    scope_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = ComplianceScopeService(db)
    scope = await service.toggle_scope(scope_id)
    if not scope:
        raise HTTPException(status_code=404, detail="Compliance scope not found")
    return ComplianceScopeResponse.model_validate(scope)
