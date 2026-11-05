from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_client_ip, require_permission
from app.models.user import User
from app.schemas.terminal_exclusion import (
    ExclusionImpact,
    TerminalExclusionCreate,
    TerminalExclusionListResponse,
    TerminalExclusionPreview,
    TerminalExclusionResponse,
    TerminalExclusionUpdate,
    TerminalExclusionWithImpact,
)
from app.services.terminal_exclusion_service import TerminalExclusionService
from app.services.terminal_service import TerminalService

router = APIRouter(prefix="/terminal-exclusions", tags=["terminal-exclusions"])


async def _log_exclusion_action(
    db: AsyncSession,
    current_user: User,
    request: Request,
    action: str,
    rule=None,
    details: dict | None = None,
) -> None:
    """Record an audit log entry for a terminal exclusion mutation."""
    payload = details or {}
    if rule is not None:
        payload = {
            "ip_type": rule.ip_pattern_type,
            "ip_value": rule.ip_pattern,
            "mac_type": rule.mac_pattern_type,
            "mac_value": rule.mac_address,
            "comments": rule.comments,
            "is_active": rule.is_active,
            **payload,
        }
    await TerminalService(db).log_action(
        current_user.username,
        action,
        "terminal_exclusion",
        str(rule.id) if rule is not None else None,
        payload,
        ip_address=get_client_ip(request),
        resource_name=(rule.comments if rule is not None else None),
        user_id=current_user.id,
    )


@router.get("/", response_model=TerminalExclusionListResponse)
async def list_rules(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:read")),
):
    service = TerminalExclusionService(db)
    items = await service.list_rules(is_active=is_active)
    return TerminalExclusionListResponse(
        items=[TerminalExclusionResponse.from_model(item) for item in items],
        total=len(items),
    )


@router.post("/preview", response_model=ExclusionImpact)
async def preview_rule(
    data: TerminalExclusionPreview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:read")),
):
    service = TerminalExclusionService(db)
    try:
        return await service.preview_rule(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/", response_model=TerminalExclusionWithImpact)
async def create_rule(
    data: TerminalExclusionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = TerminalExclusionService(db)
    try:
        rule, impact = await service.create_rule(data, current_user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await _log_exclusion_action(
        db, current_user, request, "create_exclusion", rule,
        details={
            "matched": impact.matched,
            "purged": impact.purgeable,
            "retained": impact.retained,
        },
    )
    return TerminalExclusionWithImpact(
        rule=TerminalExclusionResponse.from_model(rule),
        impact=impact,
    )


@router.get("/{rule_id}", response_model=TerminalExclusionResponse)
async def get_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:read")),
):
    rule = await TerminalExclusionService(db).get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Terminal exclusion rule not found")
    return TerminalExclusionResponse.from_model(rule)


@router.put("/{rule_id}", response_model=TerminalExclusionWithImpact)
async def update_rule(
    rule_id: int,
    data: TerminalExclusionUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = TerminalExclusionService(db)
    try:
        rule, impact = await service.update_rule(rule_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rule:
        raise HTTPException(status_code=404, detail="Terminal exclusion rule not found")
    await _log_exclusion_action(
        db, current_user, request, "update_exclusion", rule,
        details={
            "matched": impact.matched if impact else 0,
            "purged": impact.purgeable if impact else 0,
            "retained": impact.retained if impact else 0,
        },
    )
    return TerminalExclusionWithImpact(
        rule=TerminalExclusionResponse.from_model(rule),
        impact=impact or ExclusionImpact(),
    )


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = TerminalExclusionService(db)
    rule = await service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Terminal exclusion rule not found")
    await service.delete_rule(rule_id)
    await _log_exclusion_action(db, current_user, request, "delete_exclusion", rule)
    return {"success": True, "message": f"Deleted terminal exclusion rule {rule_id}"}


@router.post("/{rule_id}/toggle", response_model=TerminalExclusionWithImpact)
async def toggle_rule(
    rule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("compliance:write")),
):
    service = TerminalExclusionService(db)
    rule, impact = await service.toggle_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Terminal exclusion rule not found")
    await _log_exclusion_action(
        db, current_user, request, "toggle_exclusion", rule,
        details={
            "matched": impact.matched if impact else 0,
            "purged": impact.purgeable if impact else 0,
            "retained": impact.retained if impact else 0,
        },
    )
    return TerminalExclusionWithImpact(
        rule=TerminalExclusionResponse.from_model(rule),
        impact=impact or ExclusionImpact(),
    )
