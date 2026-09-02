import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.core.logging_config import setup_logging
from app.core.security import close_redis_client
from app.services.config_service import get_config_value
from app.services.event_emitter import emit_compliance_alert
from app.middleware.error_handler import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware

# Configure logging (centralized: loguru + intercept stdlib logging)
setup_logging()


async def _is_task_paused(task_name: str) -> bool:
    """Check if a scheduler task is paused via Redis control key"""
    try:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        ctrl_key = f"scheduler:ctrl:{task_name}"
        val = await redis_client.get(ctrl_key)
        return val == b"paused" or val == "paused"
    except Exception:
        return False


async def _acquire_task_lock(task_name: str, ttl: int = 300) -> bool:
    """Acquire a distributed lock for a scheduler task via Redis.
    Returns True if lock acquired, False if another instance holds it."""
    try:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        lock_key = f"scheduler:lock:{task_name}"
        # SET with NX (only if not exists) and EX (expire)
        acquired = await redis_client.set(lock_key, "locked", nx=True, ex=ttl)
        return acquired is not None
    except Exception:
        # If Redis is unavailable, allow task to run (fail-open)
        return True


async def _release_task_lock(task_name: str) -> None:
    """Release a distributed lock for a scheduler task"""
    try:
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        lock_key = f"scheduler:lock:{task_name}"
        await redis_client.delete(lock_key)
    except Exception:
        pass


async def _get_scheduler_interval(key: str, default: int) -> int:
    """Get scheduler interval from config, clamped to 30-86400 seconds"""
    try:
        async with async_session_factory() as db:
            from app.services.config_service import ConfigService
            config_service = ConfigService(db)
            value = await config_service.get_value(key)
            if value is not None:
                interval = int(value)
                return max(30, min(86400, interval))
    except Exception:
        pass
    return default


async def _cache_reconcile_result(results: dict) -> None:
    """Cache latest firewall reconciliation result to Redis for stats display.
    Key: reconcile:latest, TTL 1 hour."""
    try:
        import json
        from datetime import datetime, UTC
        from app.core.security import get_redis_client
        redis_client = await get_redis_client()
        payload = {
            "firewall_ip_count": results.get("firewall_ip_count", 0),
            "db_entry_count": results.get("db_entry_count", 0),
            "firewall_errors": results.get("firewall_errors", []),
            "synced_at": datetime.now(UTC).isoformat(),
        }
        await redis_client.setex("reconcile:latest", 3600, json.dumps(payload))
    except Exception as e:
        logger.warning(f"Failed to cache reconciliation result: {e}")


async def cleanup_expired_blacklist():
    """Background task to periodically clean up expired blacklist entries"""
    while True:
        interval = await _get_scheduler_interval("scheduler_firewall_query_interval", 3600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("firewall_query"):
                continue
            if not await _acquire_task_lock("firewall_query"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.terminal_service import TerminalService
                    service = TerminalService(db)
                    count = await service.cleanup_expired_blacklist()
                    if count > 0:
                        logger.info(f"Cleaned up {count} expired blacklist entries [source=scheduler]")
            finally:
                await _release_task_lock("firewall_query")
        except Exception as e:
            logger.error(f"Error in blacklist cleanup task: {type(e).__name__}: {e} [source=scheduler]")


async def cleanup_expired_logs():
    """Background task to periodically clean up expired audit and notification logs"""
    while True:
        try:
            await asyncio.sleep(86400)
            if await _is_task_paused("log_cleanup"):
                continue
            if not await _acquire_task_lock("log_cleanup", 7200):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.config_service import ConfigService
                    config_service = ConfigService(db)
                    
                    retention_days = await config_service.get_value("audit_log_retention_days")
                    if retention_days is None:
                        retention_days = 90
                    else:
                        retention_days = int(retention_days)

                    from datetime import datetime, timedelta, UTC
                    cutoff_time = datetime.now(UTC) - timedelta(days=retention_days)

                    from sqlalchemy import delete, select, func
                    from app.models.log import AuditLog
                    from app.models.notification import NotificationLog

                    audit_stmt = delete(AuditLog).where(AuditLog.timestamp < cutoff_time)
                    audit_result = await db.execute(audit_stmt)
                    audit_deleted = audit_result.rowcount or 0

                    notif_stmt = delete(NotificationLog).where(
                        NotificationLog.sent_at < cutoff_time,
                        NotificationLog.archived == True
                    )
                    notif_result = await db.execute(notif_stmt)
                    notif_deleted = notif_result.rowcount or 0

                    await db.commit()

                    if audit_deleted > 0 or notif_deleted > 0:
                        logger.info(f"Cleaned up {audit_deleted} audit logs and {notif_deleted} notification logs older than {retention_days} days [source=scheduler]")
            finally:
                await _release_task_lock("log_cleanup")
        except Exception as e:
            logger.error(f"Error in log cleanup task: {type(e).__name__}: {e} [source=scheduler]")


async def firewall_reconciliation():
    """Background task to periodically reconcile firewall blocked IPs with database blacklist"""
    while True:
        try:
            await asyncio.sleep(300)
            if await _is_task_paused("firewall_reconciliation"):
                continue
            if not await _acquire_task_lock("firewall_reconciliation", 600):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.firewall_reconciliation_service import FirewallReconciliationService
                    recon_svc = FirewallReconciliationService(db)
                    results = await recon_svc.reconcile()

                    # Cache latest reconciliation result for firewall stats display
                    await _cache_reconcile_result(results)

                    if results["missing_in_db"] or results["missing_in_firewall"]:
                        logger.warning(f"Firewall reconciliation found {len(results['missing_in_db'])} IPs missing in DB and {len(results['missing_in_firewall'])} IPs missing in firewall")
                        logger.info(f"Reconciliation results: created_in_db={results['created_in_db']}, reblocked_on_firewall={results['reblocked_on_firewall']}")
            finally:
                await _release_task_lock("firewall_reconciliation")
        except Exception as e:
            logger.error(f"Error in firewall reconciliation task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_arp_collection():
    """Background task to periodically collect ARP data from all enabled sources"""
    while True:
        interval = await _get_scheduler_interval("scheduler_arp_collection_interval", 300)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("arp_collection"):
                continue
            if not await _acquire_task_lock("arp_collection"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.arp_collector_service import ArpCollectorService
                    service = ArpCollectorService(db)
                    await service.run_scheduled_collection()
            finally:
                await _release_task_lock("arp_collection")
        except Exception as e:
            logger.error(f"Error in scheduled ARP collection task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_ipguard_sync():
    """Background task to periodically sync IPGuard baseline data"""
    while True:
        interval = await _get_scheduler_interval("scheduler_ipguard_sync_interval", 600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("ipguard_sync"):
                continue
            if not await _acquire_task_lock("ipguard_sync"):
                continue
            try:
                async with async_session_factory() as db:
                    from sqlalchemy import select

                    from app.models.compliance_baseline import ComplianceBaseline
                    from app.services.compliance_service import ComplianceService
                    service = ComplianceService(db)
                    stmt = select(ComplianceBaseline).where(ComplianceBaseline.enabled == True)
                    result = await db.execute(stmt)
                    baselines = result.scalars().all()
                    for baseline in baselines:
                        try:
                            await service.sync_ipguard_data(baseline.tag)
                            logger.info(f"Synced IPGuard data for baseline: {baseline.tag} [source=scheduler]")
                            # NOTE: Do NOT immediately trigger full compliance recalculation here.
                            # This causes race conditions with ARP collection (IPGuard updated but ARP not yet refreshed).
                            # The next scheduled compliance check / ARP collection will pick up the new cache naturally.
                        except Exception as e:
                            logger.error(f"Error syncing IPGuard data for {baseline.tag}: {type(e).__name__}: {e} [source=scheduler]")
                            # Emit datasource sync failed event for notification dispatch.
                            # fire-and-forget: emit_event logs errors internally and never raises.
                            from app.services.event_emitter import emit_datasource_sync_failed
                            await emit_datasource_sync_failed(
                                source_name=baseline.tag,
                                source_tag=baseline.tag,
                                error=f"{type(e).__name__}: {e}",
                            )
            finally:
                await _release_task_lock("ipguard_sync")
        except Exception as e:
            logger.error(f"Error in scheduled IPGuard sync task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_compliance_check():
    """Background task to periodically run compliance checks"""
    while True:
        interval = await _get_scheduler_interval("scheduler_compliance_check_interval", 300)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("compliance_check"):
                continue
            if not await _acquire_task_lock("compliance_check"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.compliance_service import ComplianceService
                    service = ComplianceService(db)
                    from app.services.data_source_service import DataSourceService
                    ds_service = DataSourceService(db)
                    sources = await ds_service.list_data_sources(type="arp_ssh", enabled=True)
                    sources2 = await ds_service.list_data_sources(type="arp_api", enabled=True)
                    all_arp_sources = sources + sources2
                    for source in all_arp_sources:
                        try:
                            from sqlalchemy import select as sa_select

                            from app.models.terminal import Terminal
                            stmt = sa_select(Terminal).where(
                                (Terminal.source_tag == source.tag) &
                                (Terminal.compliance_status == "unknown")
                            )
                            r = await db.execute(stmt)
                            unchecked = r.scalars().all()
                            if unchecked:
                                check_entries = [
                                    {"ip_address": e.ip_address, "mac_address": e.mac_address, "source_tag": e.source_tag}
                                    for e in unchecked
                                ]
                                result = await service.batch_check_compliance(check_entries)

                                # Build lookup maps for compliance results (keyed by normalized MAC for uniqueness)
                                result_lookup = {}
                                if result.details:
                                    def _norm_mac(m: str) -> str:
                                        return (m or "").replace('-', '').replace(':', '').replace('.', '').upper()
                                    for item in result.details.get("bypass", []):
                                        mac_key = _norm_mac(item.get("mac_address", ""))
                                        result_lookup[mac_key] = {
                                            "compliance_status": "bypass",
                                            "wl_match_type": item.get("wl_match_type"),
                                            "wl_comments": item.get("wl_comments"),
                                        }
                                    for item in result.details.get("compliant", []):
                                        mac_key = _norm_mac(item.get("mac_address", ""))
                                        result_lookup[mac_key] = {
                                            "compliance_status": "compliant",
                                            "wl_match_type": None,
                                            "wl_comments": None,
                                        }
                                    for item in result.details.get("non_compliant", []):
                                        mac_key = _norm_mac(item.get("mac_address", ""))
                                        result_lookup[mac_key] = {
                                            "compliance_status": "non_compliant",
                                            "wl_match_type": None,
                                            "wl_comments": None,
                                        }

                                # Apply compliance results for newly discovered (unknown)
                                # terminals, with confirm-threshold protection against
                                # immediate false blocks.
                                for entry in unchecked:
                                    mac_key = entry.mac_address_normalized or ""
                                    r = result_lookup.get(mac_key)
                                    if r:
                                        await service.apply_initial_compliance_result(
                                            entry,
                                            r["compliance_status"],
                                            r["wl_match_type"],
                                            r["wl_comments"],
                                            entry.ip_address or "",
                                            entry.mac_address or "",
                                        )

                                await db.commit()
                                if result.non_compliant > 0 or result.bypass > 0:
                                    logger.info(f"Compliance check for {source.tag}: {result.compliant} compliant, {result.bypass} bypass, {result.non_compliant} non-compliant")
                                    # Trigger auto-block for non-compliant terminals
                                    if result.non_compliant > 0:
                                        try:
                                            block_result = await service.auto_block_non_compliant(source.tag)
                                            if block_result.blocked > 0:
                                                logger.info(f"Auto-blocked {block_result.blocked} non-compliant terminals from {source.tag} [source=scheduler]")
                                        except Exception as be:
                                            logger.error(f"Error auto-blocking for {source.tag}: {type(be).__name__}: {be} [source=scheduler]")
                        except Exception as e:
                            logger.error(f"Error in compliance check for {source.tag}: {type(e).__name__}: {e} [source=scheduler]")

                        # Retry blocking for non_compliant + unblocked terminals
                        try:
                            retry_stmt = sa_select(Terminal).where(
                                (Terminal.source_tag == source.tag) &
                                (Terminal.compliance_status == "non_compliant") &
                                (Terminal.status == "unblocked")
                            )
                            retry_r = await db.execute(retry_stmt)
                            retry_terminals = retry_r.scalars().all()
                            if retry_terminals:
                                import re
                                from datetime import datetime as dt_cls, UTC as utc_cls, timedelta as td_cls

                                block_time = await service._get_block_time()
                                match = re.match(r'^(\d+)([dhm])$', block_time.lower())
                                td = td_cls(days=30)
                                if match:
                                    value = int(match.group(1))
                                    unit = match.group(2)
                                    if unit == 'd':
                                        td = td_cls(days=value)
                                    elif unit == 'h':
                                        td = td_cls(hours=value)
                                    elif unit == 'm':
                                        td = td_cls(minutes=value)

                                retry_blocked = 0
                                whitelist_fixed = 0
                                no_firewall_fixed = 0
                                block_failed = 0
                                # Load whitelist cache once for authoritative whitelist check
                                retry_whitelist_data = await service._load_whitelist_cache()

                                # Pre-pass: authoritative whitelist check. Whitelist is admin-configured
                                # truth; compliance_status may be stale due to historical crashes, so
                                # never re-block a whitelist-matched terminal; self-heal it instead.
                                remaining_retry = []
                                for terminal in retry_terminals:
                                    ip_addr = terminal.ip_address or ""
                                    mac_addr = terminal.mac_address or ""
                                    wl_hit = service._match_whitelist_in_memory(retry_whitelist_data, ip_addr, mac_addr)
                                    if wl_hit:
                                        terminal.compliance_status = "bypass"
                                        terminal.compliant_confirm_count = 0
                                        terminal.non_compliant_confirm_count = 0
                                        terminal.block_state = None
                                        whitelist_fixed += 1
                                        logger.info(
                                            f"Retry-block skipped for {ip_addr}/{mac_addr}: whitelist match "
                                            f"({wl_hit.get('match_type')}), compliance_status set to bypass [source=scheduler]"
                                        )
                                    else:
                                        remaining_retry.append(terminal)

                                # Commit whitelist self-heal separately so a later retry-block
                                # IntegrityError rollback cannot discard these fixes.
                                if whitelist_fixed > 0:
                                    try:
                                        await db.commit()
                                        logger.info(
                                            f"Retry-block whitelist self-heal: fixed {whitelist_fixed} "
                                            f"stale whitelist terminals from {source.tag} [source=scheduler]"
                                        )
                                    except Exception as wl_err:
                                        await db.rollback()
                                        logger.error(
                                            f"Retry-block whitelist self-heal commit failed for {source.tag}: "
                                            f"{type(wl_err).__name__}: {wl_err} [source=scheduler]"
                                        )

                                for terminal in remaining_retry:
                                    ip_addr = terminal.ip_address or ""
                                    mac_addr = terminal.mac_address or ""
                                    mac_norm = mac_addr.replace('-', '').replace(':', '').replace('.', '').upper() if mac_addr else None
                                    fw_tags = await service._get_bound_firewall_tags(terminal.source_tag)
                                    if not fw_tags:
                                        terminal.block_state = "no_firewall"
                                        no_firewall_fixed += 1
                                        continue
                                    all_success = True
                                    for fw_tag in fw_tags:
                                        success = await service._block_on_firewall(
                                            ip_addr, fw_tag,
                                            reason="Auto-blocked: retry (compliance check)"
                                        )
                                        if not success:
                                            all_success = False
                                            logger.warning(f"Retry block failed for {ip_addr} on firewall '{fw_tag}' [source=scheduler]")
                                    if all_success:
                                        terminal.status = "blocked"
                                        terminal.firewall_tag = fw_tags[0] if len(fw_tags) == 1 else ",".join(fw_tags)
                                        terminal.block_state = None
                                        # Idempotency per firewall: keyed by (ip, firewall).
                                        for fw_tag in fw_tags:
                                            await service._attach_active_blacklist(
                                                ip_address=ip_addr,
                                                mac_address=mac_addr,
                                                mac_norm=mac_norm,
                                                firewall_tag=fw_tag,
                                                reason="Auto-blocked: non-compliant (retry)",
                                                source_tag=terminal.source_tag,
                                                expires_at=dt_cls.now(utc_cls) + td,
                                            )
                                        retry_blocked += 1
                                        logger.info(f"Retry block succeeded for {ip_addr} on firewall(s) '{','.join(fw_tags)}' [source=scheduler]")
                                    else:
                                        terminal.block_state = "block_failed"
                                        block_failed += 1

                                if retry_blocked > 0:
                                    try:
                                        await db.commit()
                                        logger.info(f"Retry-blocked {retry_blocked} non-compliant unblocked terminals from {source.tag} [source=scheduler]")
                                    except IntegrityError as ie:
                                        # Unique constraint violation (duplicate active blacklist entry):
                                        # rollback this batch to avoid poisoning the whole scheduler
                                        # session, then continue with other sources.
                                        await db.rollback()
                                        logger.error(
                                            f"Retry-block commit failed for {source.tag} due to IntegrityError, "
                                            f"rolled back to protect scheduler session: {ie} [source=scheduler]"
                                        )

                                # Commit block_state backfill (no_firewall / block_failed) so legacy
                                # NULL rows converge even when nothing was actually (re-)blocked.
                                if no_firewall_fixed > 0 or block_failed > 0:
                                    try:
                                        await db.commit()
                                        if no_firewall_fixed:
                                            logger.info(
                                                f"Retry-block marked {no_firewall_fixed} non-compliant "
                                                f"terminals as no_firewall (unblockable) from {source.tag} [source=scheduler]"
                                            )
                                        if block_failed:
                                            logger.info(
                                                f"Retry-block marked {block_failed} non-compliant terminals "
                                                f"as block_failed (awaiting retry) from {source.tag} [source=scheduler]"
                                            )
                                    except IntegrityError as ie:
                                        await db.rollback()
                                        logger.error(
                                            f"Retry-block block_state commit failed for {source.tag} due to "
                                            f"IntegrityError, rolled back: {ie} [source=scheduler]"
                                        )
                        except Exception as re_err:
                            logger.error(f"Error in retry-block for {source.tag}: {type(re_err).__name__}: {re_err} [source=scheduler]")
                            try:
                                await db.rollback()
                            except Exception:
                                pass

                    # ========== Periodic full compliance recalculation (self-healing) ==========
                    # Ensures terminals stuck in stale states (e.g. whitelist terminals left as
                    # non_compliant by historical crashes) are corrected automatically every cycle.
                    # recalculate_all_compliance() holds a Redis distributed lock internally,
                    # so it is safe against concurrent manual/recalc triggers.
                    try:
                        async with async_session_factory() as recalc_db:
                            from app.services.compliance_service import ComplianceService as _RecalcSvc
                            recalc_svc = _RecalcSvc(recalc_db)
                            await recalc_svc.recalculate_all_compliance()
                    except Exception as recalc_err:
                        logger.error(
                            f"Error in periodic full compliance recalculation: "
                            f"{type(recalc_err).__name__}: {recalc_err} [source=scheduler]"
                        )

                    # ========== Global compliance alert (based on DB stats, not per-source unchecked) ==========
                    try:
                        from app.services.terminal_service import TerminalService
                        t_service = TerminalService(db)
                        stats = await t_service.get_stats()
                        db_compliant = int(stats.get("compliant", 0))
                        db_bypass = int(stats.get("bypass", 0))
                        db_non_compliant = int(stats.get("non_compliant", 0))
                        db_unknown = int(stats.get("unknown", 0))
                        checked = db_compliant + db_bypass + db_non_compliant + db_unknown
                        effective_compliant = db_compliant + db_bypass
                        rate = (effective_compliant / checked * 100) if checked > 0 else 100.0
                        alert_threshold = float(await get_config_value("alert_compliance_rate_threshold", 80))
                        logger.info(
                            f"Overall compliance stats: total_checked={checked}, compliant={db_compliant}, "
                            f"bypass={db_bypass}, non_compliant={db_non_compliant}, unknown={db_unknown}, rate={rate:.1f}% "
                            f"[source=scheduler]"
                        )
                        await emit_compliance_alert(
                            compliance_rate=rate,
                            non_compliant_count=db_non_compliant,
                            threshold=alert_threshold,
                            compliant_count=db_compliant,
                            bypass_count=db_bypass,
                            total_checked=checked,
                        )
                    except Exception as alert_err:
                        logger.error(f"Error emitting overall compliance alert: {type(alert_err).__name__}: {alert_err} [source=scheduler]")
            finally:
                await _release_task_lock("compliance_check")
        except Exception as e:
            logger.error(f"Error in scheduled compliance check task: {type(e).__name__}: {e} [source=scheduler]")
            try:
                await _release_task_lock("compliance_check")
            except Exception:
                pass


async def scheduled_auto_unblock():
    """Background task to periodically auto-unblock compliant terminals"""
    while True:
        interval = await _get_scheduler_interval("scheduler_auto_unblock_interval", 600)
        try:
            await asyncio.sleep(interval)
            if await _is_task_paused("auto_unblock"):
                continue
            if not await _acquire_task_lock("auto_unblock"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.compliance_service import ComplianceService
                    service = ComplianceService(db)
                    result = await service.auto_unblock_compliant()
                    if result.unblocked > 0:
                        logger.info(f"Auto-unblocked {result.unblocked} compliant terminals")
            finally:
                await _release_task_lock("auto_unblock")
        except Exception as e:
            logger.error(f"Error in scheduled auto-unblock task: {type(e).__name__}: {e} [source=scheduler]")


async def scheduled_backup():
    """Background task to periodically run backup if enabled.

    Parses the cron schedule from backup_config (e.g., "8 18 * * *" = 18:08 daily)
    and only runs backup when current time matches the schedule.
    Polls every 60 seconds to check if it's time to run.
    """
    last_backup_key = "notify:last_backup_run"
    poll_interval = 60  # Check every 60 seconds

    while True:
        try:
            await asyncio.sleep(poll_interval)
            if await _is_task_paused("backup"):
                continue
            if not await _acquire_task_lock("backup"):
                continue
            try:
                async with async_session_factory() as db:
                    from app.services.backup_service import BackupService
                    service = BackupService(db=db)
                    config = await service.load_config()
                    if not config.enabled:
                        continue

                    # Parse cron schedule and check if current time matches
                    if not _should_run_backup_now(config.schedule):
                        continue

                    # Avoid duplicate runs within the same minute window
                    from app.core.security import get_redis_client
                    from app.core.timezone import now as _now_tz
                    redis = await get_redis_client()
                    last_run = await redis.get(last_backup_key)
                    now_str = _now_tz().strftime("%Y-%m-%d %H:%M")
                    if last_run and last_run.decode() == now_str:
                        continue

                    await redis.setex(last_backup_key, 120, now_str)

                    logger.info(f"Scheduled backup starting (cron='{config.schedule}') [source=scheduler]")
                    job = await service.run_backup("full")

                    # Write to audit log so frontend can see backup history
                    from app.services.terminal_service import TerminalService
                    ts = TerminalService(db)
                    await ts.log_action(
                        "system", "scheduled_backup", "backup", str(job.id),
                        {
                            "status": job.status,
                            "file_path": job.file_path,
                            "file_size": job.file_size,
                            "backup_type": "full",
                            "checksum": job.checksum,
                            "error_message": job.error_message,
                            "options": {
                                "database": config.backup_database,
                                "config": config.backup_config,
                                "whitelist": config.backup_whitelist,
                                "logs": config.backup_logs,
                            }
                        },
                        ip_address="System",
                        resource_name=job.file_path,
                    )
                    await db.commit()

                    if job.status == "completed":
                        logger.info(f"Scheduled backup completed: {job.file_path} ({job.file_size} bytes) [source=scheduler]")
                    else:
                        logger.error(f"Scheduled backup failed: {job.error_message} [source=scheduler]")
            finally:
                await _release_task_lock("backup")
        except Exception as e:
            logger.error(f"Error in scheduled backup task: {type(e).__name__}: {e} [source=scheduler]")


def _should_run_backup_now(cron_expr: str) -> bool:
    """Check if current time matches the cron schedule.

    Supports basic cron format: "minute hour day month dayofweek"
    Each field can be: * (any), a number, or comma-separated numbers.
    """
    from app.core.timezone import now as _now
    import re

    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False

        minute_str, hour_str, day_str, month_str, dow_str = parts
        current = _now()

        def match_field(field_str: str, current_val: int) -> bool:
            if field_str == "*":
                return True
            for part in field_str.split(","):
                part = part.strip()
                if part == "*":
                    return True
                if "/" in part:
                    base, step = part.split("/", 1)
                    if base == "*" or base == "0":
                        if current_val % int(step) == 0:
                            return True
                else:
                    if int(part) == current_val:
                        return True
            return False

        return (
            match_field(minute_str, current.minute) and
            match_field(hour_str, current.hour) and
            match_field(day_str, current.day) and
            match_field(month_str, current.month) and
            match_field(dow_str, current.weekday())
        )
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Terminal Network Access Manager...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Seed default system configs (idempotent)
    async with async_session_factory() as db:
        from app.services.config_service import ConfigService
        config_service = ConfigService(db)
        count = await config_service.seed_defaults()
        if count > 0:
            logger.info(f"Seeded {count} default system configs")
        else:
            logger.info("System configs already initialized")

        # Migrate legacy "Terminal Access Platform" → "Terminal Access Manager"
        from sqlalchemy import text
        legacy_rows = await db.execute(
            text("SELECT id, value FROM system_config WHERE value LIKE '%Terminal Access Platform%'")
        )
        for row in legacy_rows:
            new_value = row[1].replace("Terminal Access Platform", "Terminal Access Manager")
            await db.execute(
                text("UPDATE system_config SET value = :val WHERE id = :id"),
                {"val": new_value, "id": row[0]}
            )
            logger.info(f"Migrated config id={row[0]}: '{row[1]}' → '{new_value}'")
        await db.commit()

        # Migrate legacy action names in audit_logs
        action_migrations = {
            "block_ip": "block_terminal",
            "unblock_ip": "unblock_terminal",
            "block": "block_blacklist",
            "unblock": "unblock_blacklist",
        }
        for old_action, new_action in action_migrations.items():
            result = await db.execute(
                text("UPDATE audit_logs SET action = :new WHERE action = :old"),
                {"new": new_action, "old": old_action}
            )
            if result.rowcount > 0:
                logger.info(f"Migrated {result.rowcount} audit log action(s): '{old_action}' → '{new_action}'")
        await db.commit()

    # Initialize global notification service (singleton).
    # Module-level singleton instead of ContextVar: scheduler tasks spawned here
    # run in the same event loop but separate task contexts, and ContextVar
    # values do not propagate into them — which previously caused
    # emit_event() to silently no-op with "Notification service not initialized".
    from app.services.event_emitter import set_notification_service
    from app.services.notification_service import NotificationService

    notification_service = NotificationService(db=None)
    await notification_service.initialize_channels()
    await notification_service.start_workers()
    set_notification_service(notification_service)
    logger.info(
        f"Notification service initialized with {len(notification_service._channels)} channel(s)"
    )

    cleanup_task = asyncio.create_task(cleanup_expired_blacklist())
    arp_collection_task = asyncio.create_task(scheduled_arp_collection())
    ipguard_sync_task = asyncio.create_task(scheduled_ipguard_sync())
    compliance_check_task = asyncio.create_task(scheduled_compliance_check())
    auto_unblock_task = asyncio.create_task(scheduled_auto_unblock())
    log_cleanup_task = asyncio.create_task(cleanup_expired_logs())
    firewall_reconciliation_task = asyncio.create_task(firewall_reconciliation())
    backup_task = asyncio.create_task(scheduled_backup())
    logger.info("All background scheduler tasks started")

    yield

    # Shutdown
    logger.info("Shutting down Terminal Network Access Manager...")

    # Stop notification workers
    await notification_service.stop_workers()
    logger.info("Notification workers stopped")

    # Cancel background tasks and wait for them to finish
    for task in [cleanup_task, arp_collection_task, ipguard_sync_task, compliance_check_task, auto_unblock_task, log_cleanup_task, firewall_reconciliation_task, backup_task]:
        task.cancel()
    await asyncio.gather(*[cleanup_task, arp_collection_task, ipguard_sync_task, compliance_check_task, auto_unblock_task, log_cleanup_task, firewall_reconciliation_task, backup_task], return_exceptions=True)
    logger.info("Background tasks cancelled")

    # Close Redis connections
    await close_redis_client()
    logger.info("Redis connections closed")

    # Dispose database engine
    from app.core.database import engine
    await engine.dispose()
    logger.info("Database engine disposed")

    # Close email HTTP client
    try:
        from app.services.notification_channels.email_channel import _email_http_client
        if _email_http_client is not None and not _email_http_client.is_closed:
            await _email_http_client.aclose()
            logger.info("Email HTTP client closed")
    except Exception as e:
        logger.warning(f"Error closing email HTTP client: {e}")


# Determine API docs visibility based on environment
docs_url = f"{settings.API_V1_STR}/docs" if settings.ENVIRONMENT != "production" else None
redoc_url = f"{settings.API_V1_STR}/redoc" if settings.ENVIRONMENT != "production" else None

# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A secure platform for managing network terminals and access control",
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.ENVIRONMENT != "production" else None,
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan
)

# Register global exception handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Add request-id middleware (registered last so it runs first)
app.add_middleware(RequestIDMiddleware)

# Add request logging middleware (registered second so it runs second, after request_id is set)
app.add_middleware(RequestLoggingMiddleware)

# Add rate limiting middleware (registered first so it runs last)
app.add_middleware(RateLimitMiddleware)

# Configure CORS
if settings.BACKEND_CORS_ORIGINS:
    origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]

    # Security check: allow_credentials=True with wildcard origin is invalid per CORS spec
    # and would allow any site to make authenticated requests
    if "*" in origins and len(origins) == 1:
        logger.warning(
            "CORS: allow_origins='*' with allow_credentials=True is insecure. "
            "Falling back to allow_credentials=False."
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Serve uploaded branding assets

UPLOAD_DIR = settings.UPLOAD_DIR


def _ensure_upload_dir():
    """Ensure upload directory exists (safe to call multiple times)"""
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        return True
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot create upload directory {UPLOAD_DIR}: {e}")
        return False


if _ensure_upload_dir():
    app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health_check():
    """Health check endpoint with dependency verification"""
    import redis.asyncio as aioredis
    from sqlalchemy import text

    from app.core.database import engine

    health_status = {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "db": "ok",
        "redis": "ok"
    }

    # Check database connection
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        if settings.ENVIRONMENT == "production":
            health_status["db"] = "error"
        else:
            health_status["db"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check Redis connection
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
    except Exception as e:
        if settings.ENVIRONMENT == "production":
            health_status["redis"] = "error"
        else:
            health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    status_code = 200 if health_status["status"] == "healthy" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=health_status, status_code=status_code)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION
    }


# Prometheus monitoring (enabled in all environments for observability)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)

    # Expose custom business metrics at /metrics/custom
    from fastapi.responses import Response

    from app.services.metrics_service import get_metrics

    @app.get("/metrics/custom", include_in_schema=False)
    async def custom_metrics():
        """Custom business metrics for Prometheus"""
        return Response(content=get_metrics(), media_type="text/plain")

    logger.info("Prometheus metrics enabled at /metrics and /metrics/custom")
except ImportError:
    logger.warning("prometheus-fastapi-instrumentator not installed, metrics disabled")


# Enhanced health check endpoints
@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness check - verifies all dependencies are available.
    Used by Kubernetes readinessProbe.
    """
    import redis.asyncio as aioredis
    from sqlalchemy import text

    from app.core.database import engine

    checks = {
        "database": "unknown",
        "redis": "unknown",
    }

    # Check database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:50]}"

    # Check Redis
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL)
        await redis_client.ping()
        await redis_client.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:50]}"

    # Determine overall status
    all_ok = all(v == "ok" for v in checks.values())

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """
    Liveness check - verifies the application is running.
    Used by Kubernetes livenessProbe.
    """
    return {
        "status": "alive",
        "version": settings.VERSION,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
