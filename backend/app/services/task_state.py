"""
Task state tracking helper for async operations.

Stores lightweight task state in Redis so that the frontend can poll for the
outcome of long-running background operations (e.g. data-source deletion)
instead of blocking on a synchronous HTTP request.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.security import get_redis_client

logger = logging.getLogger(__name__)

# Runtime task state is transient; expire it after one hour so stale entries
# cannot accumulate. This is a single, centralized constant (not a scattered
# magic number) for task-state TTL.
DELETE_TASK_TTL = 3600

_TASK_KEY_PREFIX = "datasource:delete:task:"


def _task_key(task_id: str) -> str:
    return f"{_TASK_KEY_PREFIX}{task_id}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def set_task_state(task_id: str, state: dict[str, Any]) -> None:
    """Persist task state to Redis.

    Never raises: a Redis failure is logged but must not interrupt the
    underlying deletion workflow.
    """
    try:
        redis = await get_redis_client()
        await redis.set(
            _task_key(task_id),
            json.dumps(state, ensure_ascii=False),
            ex=DELETE_TASK_TTL,
        )
    except Exception as e:
        logger.warning(f"Failed to store task state for {task_id}: {e}")


async def get_task_state(task_id: str) -> dict[str, Any] | None:
    """Read task state from Redis, or None if missing/unreadable."""
    try:
        redis = await get_redis_client()
        raw = await redis.get(_task_key(task_id))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Failed to read task state for {task_id}: {e}")
        return None


def now_iso() -> str:
    """Timezone-aware UTC timestamp string (used to stamp task lifecycle)."""
    return _now_iso()