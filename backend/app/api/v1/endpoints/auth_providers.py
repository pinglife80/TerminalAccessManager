"""
Authentication Provider API Endpoints for TerminalAccessManager.

Provides REST API for managing authentication providers.
"""


from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_client_ip, get_current_user, require_permission
from app.models.auth_config import AuthConfig
from app.models.user import User
from app.services.terminal_service import TerminalService
from app.schemas.auth_provider import (
    AuthProviderCreate,
    AuthProviderResponse,
    AuthProviderUpdate,
    AuthTestResult,
)
from app.services.auth_providers.provider_factory import AuthProviderFactory

router = APIRouter(prefix="/auth/providers", tags=["Authentication Providers"])


@router.get("/available")
async def get_available_providers(db: AsyncSession = Depends(get_db)):
    """Get all enabled authentication providers for login selection"""
    from sqlalchemy import select
    from app.services.auth_providers.base import AuthProviderType

    providers = []

    providers.append({
        "id": "local",
        "name": "Local",
        "provider_type": AuthProviderType.LOCAL.value,
        "description": "Local account authentication",
        "enabled": True,
    })

    stmt = select(AuthConfig).where(AuthConfig.enabled == True).order_by(AuthConfig.priority)
    result = await db.execute(stmt)
    configs = result.scalars().all()

    for config in configs:
        providers.append({
            "id": str(config.id),
            "name": config.name,
            "provider_type": config.provider_type,
            "description": config.description or "",
            "enabled": config.enabled,
        })

    return providers


@router.get("", response_model=list[AuthProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all authentication providers"""
    from sqlalchemy import select

    stmt = select(AuthConfig).order_by(AuthConfig.priority, AuthConfig.name)
    result = await db.execute(stmt)
    providers = result.scalars().all()
    return providers


@router.post("", response_model=AuthProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    provider_data: AuthProviderCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings:write")),
):
    """Create a new authentication provider"""
    provider_class = AuthProviderFactory.get_provider_class(provider_data.provider_type)
    if not provider_class:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider type: {provider_data.provider_type}",
        )

    provider = AuthConfig(
        name=provider_data.name,
        provider_type=provider_data.provider_type,
        config=provider_data.config,
        enabled=provider_data.enabled,
        priority=provider_data.priority,
        description=provider_data.description,
        created_by=current_user.username,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "create_auth_provider", "auth_provider",
        str(provider.id),
        {"name": provider.name, "provider_type": provider.provider_type, "enabled": provider.enabled},
        ip_address=get_client_ip(request),
        resource_name=provider.name,
    )
    return provider


@router.get("/{provider_id}", response_model=AuthProviderResponse)
async def get_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get an authentication provider by ID"""
    provider = await db.get(AuthConfig, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.put("/{provider_id}", response_model=AuthProviderResponse)
async def update_provider(
    provider_id: int,
    provider_data: AuthProviderUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings:write")),
):
    """Update an authentication provider"""
    provider = await db.get(AuthConfig, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider_data.name is not None:
        provider.name = provider_data.name
    if provider_data.config is not None:
        new_config = dict(provider_data.config)
        if provider.provider_type == "ldap" and new_config.get("bind_password") is None:
            existing_config = provider.config or {}
            new_config["bind_password"] = existing_config.get("bind_password", "")
        provider.config = new_config
    if provider_data.enabled is not None:
        provider.enabled = provider_data.enabled
    if provider_data.priority is not None:
        provider.priority = provider_data.priority
    if provider_data.description is not None:
        provider.description = provider_data.description

    await db.commit()
    await db.refresh(provider)
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "update_auth_provider", "auth_provider",
        str(provider.id),
        {"name": provider.name, "enabled": provider.enabled, "priority": provider.priority},
        ip_address=get_client_ip(request),
        resource_name=provider.name,
    )
    return provider


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings:write")),
):
    """Delete an authentication provider"""
    provider = await db.get(AuthConfig, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider_name = provider.name
    provider_type = provider.provider_type
    await db.delete(provider)
    await db.commit()
    ts = TerminalService(db)
    await ts.log_action(
        current_user.username, "delete_auth_provider", "auth_provider",
        str(provider_id),
        {"name": provider_name, "provider_type": provider_type},
        ip_address=get_client_ip(request),
        resource_name=provider_name,
    )


@router.post("/{provider_id}/test", response_model=AuthTestResult)
async def test_provider(
    provider_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("settings:write")),
):
    """Test an authentication provider connection"""
    provider_config = await db.get(AuthConfig, provider_id)
    if not provider_config:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        provider = await AuthProviderFactory.create_provider(
            provider_config.provider_type,
            provider_config.config,
            db,
        )
        result = await provider.test_connection()
        ts = TerminalService(db)
        await ts.log_action(
            current_user.username, "test_auth_provider", "auth_provider",
            str(provider_id),
            {"name": provider_config.name, "provider_type": provider_config.provider_type, "success": result.get("success", False)},
            ip_address=get_client_ip(request),
            resource_name=provider_config.name,
        )
        return AuthTestResult(**result)
    except Exception as e:
        ts = TerminalService(db)
        await ts.log_action(
            current_user.username, "test_auth_provider", "auth_provider",
            str(provider_id),
            {"name": provider_config.name, "provider_type": provider_config.provider_type, "success": False, "error": str(e)},
            ip_address=get_client_ip(request),
            resource_name=provider_config.name,
        )
        return AuthTestResult(
            success=False,
            message=f"Test failed: {str(e)}",
        )
