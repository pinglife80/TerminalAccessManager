from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Request
from sqlalchemy.ext.asyncio import AsyncSession
import os
import uuid
import shutil

from app.core.database import get_db
from app.core.security import require_permission, get_client_ip
from app.models.user import User
from app.schemas.system_config import (
    SystemConfigResponse, SystemConfigUpdate, ConfigUpdateResult,
    AllConfigsResponse, ConfigCategory,
)
from app.services.config_service import ConfigService

router = APIRouter(prefix="/settings", tags=["settings"])

# Upload directory for branding assets
UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/x-icon", "image/vnd.microsoft.icon"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".ico"}
# Note: SVG is excluded due to XSS risk (SVG can embed JavaScript)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


@router.get("/branding")
async def get_public_branding(
    db: AsyncSession = Depends(get_db),
):
    """Get branding configuration (public, no auth required).
    Used by login page to display custom background and favicon."""
    service = ConfigService(db)
    all_configs = await service.get_all_grouped()
    # Only return branding-related fields
    return all_configs.branding


@router.get("/", response_model=AllConfigsResponse)
async def get_all_configs(
    current_user: User = Depends(require_permission("settings:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get all system configurations grouped by category (requires settings:read permission)"""
    service = ConfigService(db)
    return await service.get_all_grouped()


@router.get("/list", response_model=list[SystemConfigResponse])
async def list_configs(
    category: str | None = Query(None, description="Filter by category"),
    current_user: User = Depends(require_permission("settings:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all config entries with metadata (requires settings:read permission)"""
    service = ConfigService(db)
    return await service.list_all(category)


@router.put("/update", response_model=list[ConfigUpdateResult])
async def update_configs(
    updates: list[SystemConfigUpdate],
    request: Request,
    current_user: User = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
):
    """Update one or more config values (requires settings:write permission).
    Read-only configs cannot be changed through this endpoint.
    Changes take effect immediately via cache invalidation."""
    service = ConfigService(db)

    # Get old values before update for audit
    old_values = {}
    for update in updates:
        old_values[update.key] = await service.get(update.key)

    results = await service.batch_update(updates, updated_by=current_user.username)

    # Audit log for each updated config
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    for update in updates:
        await ts.log_action(current_user.username, "update_config", "system", update.key,
                            {"message": "Updated system configuration", "key": update.key,
                             "old_value": old_values.get(update.key), "new_value": update.value},
                            ip_address=get_client_ip(request),
                            resource_name=update.key)

    return results


@router.put("/{key}", response_model=ConfigUpdateResult)
async def update_single_config(
    key: str,
    update: SystemConfigUpdate,
    request: Request,
    current_user: User = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
):
    """Update a single config value by key (requires settings:write permission)"""
    service = ConfigService(db)
    old_value = await service.get(key)
    result = await service.set(key, update.value, updated_by=current_user.username)
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "update_config", "system", key,
                        {"message": "Updated system configuration", "key": key,
                         "old_value": old_value, "new_value": update.value},
                        ip_address=get_client_ip(request),
                        resource_name=key)

    return result


@router.post("/seed", response_model=dict)
async def seed_default_configs(
    current_user: User = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
):
    """Seed default configs into the database. Idempotent - skips existing keys."""
    service = ConfigService(db)
    count = await service.seed_defaults()
    return {"message": f"Seeded {count} new configs", "count": count}


@router.post("/invalidate-cache", response_model=dict)
async def invalidate_config_cache(
    current_user: User = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate all config cache entries in Redis.
    Forces next reads to load from database."""
    service = ConfigService(db)
    await service._invalidate_all_cache()
    return {"message": "Config cache invalidated"}


@router.post("/upload", response_model=dict)
async def upload_branding_asset(
    request: Request,
    file: UploadFile = File(...),
    purpose: str = Query(..., description="Purpose: 'login_bg' or 'favicon'"),
    current_user: User = Depends(require_permission("settings:upload")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a branding asset (login background image or favicon).
    Returns the URL path that can be used as login_bg_url or favicon_url."""
    if purpose not in ("login_bg", "favicon"):
        raise HTTPException(status_code=400, detail="purpose must be 'login_bg' or 'favicon'")

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}"
        )

    # Read and check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    # Validate file extension against whitelist
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Generate UUID-based filename to prevent URL guessing and path traversal
    filename = f"{purpose}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    # URL path served by nginx
    url_path = f"/uploads/{filename}"

    # Auto-update the corresponding config key
    config_key = "login_bg_url" if purpose == "login_bg" else "favicon_url"
    service = ConfigService(db)
    result = await service.set(config_key, url_path, updated_by=current_user.username)

    # Audit log
    from app.services.terminal_service import TerminalService
    ts = TerminalService(db)
    await ts.log_action(current_user.username, "upload_branding", "system", config_key,
                        {"message": "Uploaded branding asset", "purpose": purpose, "url": url_path,
                         "file_size": len(content)},
                        ip_address=get_client_ip(request),
                        resource_name=config_key)

    return {
        "url": url_path,
        "config_key": config_key,
        "updated": result.success,
        "message": f"File uploaded and {config_key} updated" if result.success else f"File uploaded but config update failed: {result.message}",
    }
