import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_client_ip, require_permission
from app.models.user import User
from app.schemas.system_config import (
    AllConfigsResponse,
    ConfigUpdateResult,
    SystemConfigResponse,
    SystemConfigUpdate,
)
from app.services.config_service import ConfigService

router = APIRouter(prefix="/settings", tags=["settings"])

# Upload directory for branding assets
UPLOAD_DIR = settings.UPLOAD_DIR

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
    email_keys = {
        "email_enabled", "email_host", "email_port", "email_use_tls", "email_use_ssl",
        "email_username", "email_password", "email_from", "email_from_name", "email_rate_limit"
    }
    email_updates = [u for u in updates if u.key in email_keys]

    for update in updates:
        await ts.log_action(current_user.username, "update_config", "system", update.key,
                            {"message": "Updated system configuration", "key": update.key,
                             "old_value": old_values.get(update.key), "new_value": update.value},
                            ip_address=get_client_ip(request),
                            resource_name=update.key)

    if email_updates:
        email_changes = {}
        for update in email_updates:
            email_changes[update.key] = {
                "old_value": old_values.get(update.key),
                "new_value": update.value
            }
        await ts.log_action(current_user.username, "save_email_config", "system", "email_config",
                            {"message": "Saved email configuration", "changes": email_changes},
                            ip_address=get_client_ip(request),
                            resource_name="email_config")

    from app.services.event_emitter import emit_config_changed
    changes = [{"key": u.key, "old_value": old_values.get(u.key), "new_value": u.value} for u in updates]
    for c in changes:
        await emit_config_changed(c["key"], current_user.username, c.get("old_value"), c.get("new_value"))

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

    from app.services.event_emitter import emit_config_changed
    await emit_config_changed(key, current_user.username, old_value, update.value)

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


@router.post("/email/test", response_model=dict)
async def test_email_configuration(
    email: str = Query(..., description="Recipient email address for the test email"),
    current_user: User = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
):
    """Send a test email using the current global SMTP configuration.

    Reads SMTP settings from the database (system_config table) with .env
    fallback. Useful for validating the configuration after changing it
    on the Email Settings page.
    """
    from app.services.email_service import EmailSendError, EmailRateLimitError, send_email

    test_subject = "[TAM] Email Configuration Test"
    test_html = """
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #2563eb;">Terminal Access Manager</h2>
            <p>This is a test email from Terminal Access Manager.</p>
            <p>If you received this email, your SMTP configuration is working correctly.</p>
            <div style="margin-top: 30px; padding: 15px; background-color: #f9fafb; border-radius: 4px;">
                <p style="color: #666; font-size: 12px; margin: 0;">
                    Sent at: {timestamp}<br>
                    Triggered by: {username}
                </p>
            </div>
        </div>
    </body>
    </html>
    """.format(
        timestamp=__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        username=current_user.username,
    )

    try:
        result = await send_email(
            to_email=email,
            subject=test_subject,
            html_content=test_html,
        )
        if result:
            # Audit log
            from app.services.terminal_service import TerminalService
            ts = TerminalService(db)
            await ts.log_action(current_user.username, "test_email", "system", "email_config",
                                {"message": "Sent test email", "recipient": email},
                                ip_address="",
                                resource_name="email_config")
            return {"success": True, "message": f"Test email sent to {email}"}
        return {"success": False, "message": "Email send returned False"}
    except EmailRateLimitError:
        return {"success": False, "message": "Rate limit exceeded. Please wait and try again."}
    except EmailSendError as e:
        return {"success": False, "message": f"Send failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {type(e).__name__}: {str(e)}"}


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
