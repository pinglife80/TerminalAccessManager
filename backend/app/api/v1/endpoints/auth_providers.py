"""
Authentication Provider API Endpoints for TerminalAccessManager.

Provides REST API for managing authentication providers.
"""


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.auth_config import AuthConfig
from app.models.user import User
from app.schemas.auth_provider import (
    AuthProviderCreate,
    AuthProviderResponse,
    AuthProviderUpdate,
    AuthTestResult,
)
from app.services.auth_providers.provider_factory import AuthProviderFactory

router = APIRouter(prefix="/auth/providers", tags=["Authentication Providers"])


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("auth.manage")),
):
    """Create a new authentication provider"""
    # Check if provider type is supported
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("auth.manage")),
):
    """Update an authentication provider"""
    provider = await db.get(AuthConfig, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider_data.name is not None:
        provider.name = provider_data.name
    if provider_data.config is not None:
        provider.config = provider_data.config
    if provider_data.enabled is not None:
        provider.enabled = provider_data.enabled
    if provider_data.priority is not None:
        provider.priority = provider_data.priority
    if provider_data.description is not None:
        provider.description = provider_data.description

    await db.commit()
    await db.refresh(provider)
    return provider


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("auth.manage")),
):
    """Delete an authentication provider"""
    provider = await db.get(AuthConfig, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.delete(provider)
    await db.commit()


@router.post("/{provider_id}/test", response_model=AuthTestResult)
async def test_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("auth.manage")),
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
        return AuthTestResult(**result)
    except Exception as e:
        return AuthTestResult(
            success=False,
            message=f"Test failed: {str(e)}",
        )
