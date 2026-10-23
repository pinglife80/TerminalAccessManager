"""
Background task runners for data-source / binding deletion.

The delete endpoints submit these as asyncio background tasks so that the
firewall-unblock step (which performs serial external HTTP calls) no longer
blocks the HTTP request beyond the frontend's 30s timeout. The frontend polls
task state via ``GET /data-sources/delete-tasks/{task_id}``.
"""

from loguru import logger

from app.core.database import async_session_factory
from app.services.data_source_service import DataSourceService
from app.services.task_state import now_iso, set_task_state


async def run_delete_data_source_task(
    task_id: str,
    source_id: int,
    username: str | None,
    client_ip: str | None,
) -> None:
    """Execute a data-source deletion in the background, updating task state."""
    await set_task_state(task_id, {"status": "running", "kind": "source"})
    db = async_session_factory()
    try:
        service = DataSourceService(db)
        deleted = await service.safe_delete_data_source(
            source_id, username=username, client_ip=client_ip
        )
        if not deleted:
            await set_task_state(task_id, {
                "status": "failed",
                "kind": "source",
                "error": "Data source not found",
                "finished_at": now_iso(),
            })
            return
        await set_task_state(task_id, {
            "status": "success",
            "kind": "source",
            "message": "Data source deleted",
            "finished_at": now_iso(),
        })
    except Exception as e:
        logger.exception(f"Data source deletion task {task_id} failed: {e}")
        await db.rollback()
        await set_task_state(task_id, {
            "status": "failed",
            "kind": "source",
            "error": str(e),
            "finished_at": now_iso(),
        })
    finally:
        await db.close()


async def run_delete_binding_task(
    task_id: str,
    binding_id: int,
    username: str | None,
    client_ip: str | None,
) -> None:
    """Execute a binding deletion in the background, updating task state."""
    await set_task_state(task_id, {"status": "running", "kind": "binding"})
    db = async_session_factory()
    try:
        service = DataSourceService(db)
        deleted = await service.safe_delete_binding(
            binding_id, username=username, client_ip=client_ip
        )
        if not deleted:
            await set_task_state(task_id, {
                "status": "failed",
                "kind": "binding",
                "error": "Binding not found",
                "finished_at": now_iso(),
            })
            return
        await set_task_state(task_id, {
            "status": "success",
            "kind": "binding",
            "message": "Binding deleted",
            "finished_at": now_iso(),
        })
    except Exception as e:
        logger.exception(f"Binding deletion task {task_id} failed: {e}")
        await db.rollback()
        await set_task_state(task_id, {
            "status": "failed",
            "kind": "binding",
            "error": str(e),
            "finished_at": now_iso(),
        })
    finally:
        await db.close()