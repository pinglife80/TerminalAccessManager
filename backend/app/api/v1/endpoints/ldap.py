"""
LDAP User Import API Endpoints.

Provides endpoints for searching and importing LDAP users into the system.
"""

import asyncio
from typing import Any, List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.core.timezone import now
from app.models.auth_config import AuthConfig
from app.models.role import Role, UserRole
from app.models.user import User

router = APIRouter(prefix="/ldap", tags=["LDAP"])


class LDAPSearchRequest(BaseModel):
    search_base: Optional[str] = None
    search_filter: Optional[str] = None
    username: Optional[str] = None
    page_size: int = 10
    page_number: int = 1


class LDAPSearchResponse(BaseModel):
    users: List[dict[str, Any]]
    total: int
    page_size: int
    page_number: int


class LDAPImportRequest(BaseModel):
    user_dns: List[str]
    role_ids: List[int]


class LDAPImportResponse(BaseModel):
    success: bool
    message: str
    imported_count: int
    existing_count: int


async def _get_ldap_provider(db: AsyncSession):
    """Get LDAP provider from database configuration"""
    result = await db.execute(
        select(AuthConfig).where(
            AuthConfig.provider_type == "ldap",
            AuthConfig.enabled == True
        )
    )
    auth_config = result.scalar_one_or_none()
    if not auth_config:
        return None, None

    try:
        from app.services.auth_providers.ldap_provider import LDAPProvider
        return LDAPProvider(auth_config.config), auth_config
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LDAP module not available",
        )


@router.post("/search", response_model=LDAPSearchResponse)
async def search_ldap_users(
    request: LDAPSearchRequest,
    current_user: User = Depends(require_permission("user:write")),
    db: AsyncSession = Depends(get_db),
):
    """Search for users in LDAP directory"""
    provider, _ = await _get_ldap_provider(db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LDAP provider is not configured or not enabled",
        )

    try:
        search_result = await asyncio.to_thread(
            provider.search_users,
            search_base=request.search_base,
            search_filter=request.search_filter,
            username=request.username,
            page_size=request.page_size,
            page_number=request.page_number,
        )

        if "error" in search_result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=search_result["error"],
            )

        return LDAPSearchResponse(
            users=search_result.get("users", []),
            total=search_result.get("total", 0),
            page_size=request.page_size,
            page_number=request.page_number,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LDAP search failed: {str(e)}",
        )


@router.post("/import", response_model=LDAPImportResponse)
async def import_ldap_users(
    request: LDAPImportRequest,
    current_user: User = Depends(require_permission("user:write")),
    db: AsyncSession = Depends(get_db),
):
    """Import LDAP users into the system and assign roles"""
    if not request.user_dns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No users selected for import",
        )

    provider, _ = await _get_ldap_provider(db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LDAP provider is not configured or not enabled",
        )

    imported_count = 0
    existing_count = 0

    try:
        for user_dn in request.user_dns:
            try:
                result = await db.execute(select(User).where(User.provider_user_id == user_dn))
                existing_user = result.scalar_one_or_none()

                if existing_user:
                    existing_count += 1
                    continue

                user_info = await asyncio.to_thread(
                    provider.get_user_info_by_dn,
                    user_dn=user_dn,
                )
                if not user_info:
                    continue

                username = user_info.get("username") or user_info.get("samaccountname") or user_info.get("uid")
                if not username:
                    continue

                email = user_info.get("email") or user_info.get("mail")

                new_user = User(
                    username=username,
                    email=email,
                    provider="ldap",
                    provider_user_id=user_dn,
                    is_active=True,
                    is_superuser=False,
                )
                db.add(new_user)
                await db.flush()

                if request.role_ids:
                    for role_id in request.role_ids:
                        role_result = await db.execute(select(Role).where(Role.id == role_id))
                        role = role_result.scalar_one_or_none()
                        if role:
                            db.add(UserRole(user_id=new_user.id, role_id=role_id))

                imported_count += 1
            except Exception as e:
                continue

        await db.commit()

        return LDAPImportResponse(
            success=True,
            message=f"Import completed: {imported_count} new users, {existing_count} already existed",
            imported_count=imported_count,
            existing_count=existing_count,
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LDAP import failed: {str(e)}",
        )


@router.get("/ous", response_model=List[dict])
async def get_ldap_ous(
    current_user: User = Depends(require_permission("user:write")),
    db: AsyncSession = Depends(get_db),
):
    """Get LDAP Organizational Units for selection"""
    provider, _ = await _get_ldap_provider(db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LDAP provider is not configured or not enabled",
        )

    try:
        ous = await asyncio.to_thread(provider.get_ous)
        return ous
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get LDAP OUs: {str(e)}",
        )