from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user, require_permission, invalidate_user_permissions
from app.models.user import User
from app.models.role import Role, Permission, UserRole, RolePermission
from app.schemas.role import (
    RoleResponse, RoleDetailResponse, RoleCreate, RoleUpdate,
    PermissionResponse, UserRoleUpdate,
)
from app.schemas.terminal import ResponseMessage

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    module: Optional[str] = None,
    current_user: User = Depends(require_permission("role:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all permissions, optionally filtered by module"""
    stmt = select(Permission).order_by(Permission.module, Permission.id)
    if module:
        stmt = stmt.where(Permission.module == module)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/", response_model=List[RoleDetailResponse])
async def list_roles(
    current_user: User = Depends(require_permission("role:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all roles with user count and permission codes"""
    result = await db.execute(select(Role).order_by(Role.id))
    roles = result.scalars().all()

    response = []
    for role in roles:
        # Get permission codes
        perm_result = await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        )
        perm_codes = list(perm_result.scalars().all())

        # Get user count
        count_result = await db.execute(
            select(func.count(UserRole.user_id)).where(UserRole.role_id == role.id)
        )
        user_count = count_result.scalar() or 0

        response.append(RoleDetailResponse(
            id=role.id,
            name=role.name,
            description=role.description,
            is_default=role.is_default,
            created_at=role.created_at,
            updated_at=role.updated_at,
            permissions=perm_codes,
            user_count=user_count,
        ))

    return response


@router.get("/{role_id}", response_model=RoleDetailResponse)
async def get_role(
    role_id: int,
    current_user: User = Depends(require_permission("role:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get role details by ID"""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    perm_result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id)
    )
    perm_codes = list(perm_result.scalars().all())

    count_result = await db.execute(
        select(func.count(UserRole.user_id)).where(UserRole.role_id == role.id)
    )
    user_count = count_result.scalar() or 0

    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_default=role.is_default,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permissions=perm_codes,
        user_count=user_count,
    )


@router.post("/", response_model=RoleDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    data: RoleCreate,
    request: Request,
    current_user: User = Depends(require_permission("role:write")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new role"""
    # Check name uniqueness
    existing = await db.execute(select(Role).where(Role.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Role '{data.name}' already exists")

    role = Role(name=data.name, description=data.description)
    db.add(role)
    await db.commit()
    await db.refresh(role)

    # Assign permissions
    if data.permission_ids:
        for pid in data.permission_ids:
            # Verify permission exists
            perm = await db.execute(select(Permission).where(Permission.id == pid))
            if perm.scalar_one_or_none():
                db.add(RolePermission(role_id=role.id, permission_id=pid))
        await db.commit()

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "create_role", "role", str(role.id),
                        {"message": "Created role", "name": role.name},
                        ip_address=request.client.host if request.client else None)

    # Re-fetch to get full data
    return await get_role(role.id, current_user, db)


@router.put("/{role_id}", response_model=RoleDetailResponse)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    request: Request,
    current_user: User = Depends(require_permission("role:write")),
    db: AsyncSession = Depends(get_db),
):
    """Update a role (description and/or permissions)"""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Prevent modifying superadmin role
    if role.name == "superadmin":
        raise HTTPException(status_code=400, detail="Cannot modify superadmin role")

    if data.description is not None:
        role.description = data.description

    if data.permission_ids is not None:
        # Remove existing permissions
        await db.execute(
            RolePermission.__table__.delete().where(RolePermission.role_id == role_id)
        )
        # Add new permissions
        for pid in data.permission_ids:
            perm = await db.execute(select(Permission).where(Permission.id == pid))
            if perm.scalar_one_or_none():
                db.add(RolePermission(role_id=role_id, permission_id=pid))

    await db.commit()

    # Invalidate permissions cache for all users with this role
    user_result = await db.execute(
        select(UserRole.user_id).where(UserRole.role_id == role_id)
    )
    for (uid,) in user_result.all():
        await invalidate_user_permissions(uid)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "update_role", "role", str(role_id),
                        {"message": "Updated role", "name": role.name},
                        ip_address=request.client.host if request.client else None)

    return await get_role(role_id, current_user, db)


@router.delete("/{role_id}", response_model=ResponseMessage)
async def delete_role(
    role_id: int,
    request: Request,
    current_user: User = Depends(require_permission("role:delete")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a role"""
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Prevent deleting built-in roles
    if role.name in ("superadmin", "admin", "operator", "auditor", "viewer"):
        raise HTTPException(status_code=400, detail="Cannot delete built-in roles")

    # Check if any users have this role
    count_result = await db.execute(
        select(func.count(UserRole.user_id)).where(UserRole.role_id == role_id)
    )
    if count_result.scalar() > 0:
        raise HTTPException(status_code=400, detail="Cannot delete role with assigned users. Remove users from role first.")

    deleted_name = role.name
    await db.delete(role)
    await db.commit()

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "delete_role", "role", str(role_id),
                        {"message": "Deleted role", "name": deleted_name},
                        ip_address=request.client.host if request.client else None)

    return {"message": f"Role '{deleted_name}' deleted successfully", "success": True}


@router.put("/users/{user_id}/roles", response_model=ResponseMessage)
async def assign_user_roles(
    user_id: int,
    data: UserRoleUpdate,
    request: Request,
    current_user: User = Depends(require_permission("user:write")),
    db: AsyncSession = Depends(get_db),
):
    """Assign roles to a user (replaces all existing roles)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify all role IDs exist
    for rid in data.role_ids:
        role_result = await db.execute(select(Role).where(Role.id == rid))
        if not role_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Role ID {rid} not found")

    # Remove existing roles
    await db.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))

    # Assign new roles
    for rid in data.role_ids:
        db.add(UserRole(user_id=user_id, role_id=rid))

    # Sync is_superuser based on superadmin role
    superadmin_result = await db.execute(
        select(Role.id).where(Role.name == "superadmin")
    )
    superadmin_role_id = superadmin_result.scalar_one_or_none() or 1
    sa_result = await db.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == superadmin_role_id)
    )
    user.is_superuser = sa_result.scalar_one_or_none() is not None

    await db.commit()

    # Invalidate permission cache
    await invalidate_user_permissions(user_id)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    role_names_result = await db.execute(
        select(Role.name).where(Role.id.in_(data.role_ids))
    )
    role_names = list(role_names_result.scalars().all())
    await ts.log_action(current_user.username, "assign_roles", "user", str(user_id),
                        {"message": "Assigned roles to user", "username": user.username, "roles": role_names},
                        ip_address=request.client.host if request.client else None)

    return {"message": f"Roles updated for user '{user.username}'", "success": True}
