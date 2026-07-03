"""
Notification Rules Engine.

Handles suppression, aggregation, and escalation rules for notifications.
"""

import json
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationRule


class NotificationRulesEngine:
    """Engine for evaluating notification rules (suppression/escalation)."""

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            from app.core.security import get_redis_client
            self._redis = await get_redis_client()
        return self._redis

    async def get_rules_for_event(
        self,
        event_type: str,
        db: AsyncSession | None = None,
    ) -> dict[str | None, NotificationRule]:
        try:
            if db is None:
                from app.core.database import async_session_factory
                async with async_session_factory() as session:
                    stmt = select(NotificationRule).where(
                        NotificationRule.event_type == event_type,
                        NotificationRule.enabled == True,
                    )
                    result = await session.execute(stmt)
                    rules = result.scalars().all()
            else:
                stmt = select(NotificationRule).where(
                    NotificationRule.event_type == event_type,
                    NotificationRule.enabled == True,
                )
                result = await db.execute(stmt)
                rules = result.scalars().all()
            return {rule.channel_name: rule for rule in rules}
        except Exception as e:
            logger.error(f"Failed to load rules for {event_type}: {e}")
            return {}

    def match_rule(
        self,
        rules: dict[str | None, NotificationRule],
        channel_name: str,
    ) -> NotificationRule | None:
        return rules.get(channel_name) or rules.get(None)

    async def check_suppression(
        self, event_type: str, channel_name: str
    ) -> bool:
        try:
            redis = await self._get_redis()
            key = f"notify:suppress:{event_type}:{channel_name}"
            return await redis.exists(key) > 0
        except Exception as e:
            logger.warning(f"Suppression check failed ({event_type}/{channel_name}): {e}")
            return False

    async def increment_suppressed_count(
        self, event_type: str, channel_name: str
    ) -> int:
        try:
            redis = await self._get_redis()
            key = f"notify:count:{event_type}:{channel_name}"
            count = await redis.incr(key)
            await redis.expire(key, 86400)
            return count
        except Exception as e:
            logger.warning(f"Suppressed count increment failed: {e}")
            return 0

    async def get_and_clear_suppressed_count(
        self, event_type: str, channel_name: str
    ) -> int:
        try:
            redis = await self._get_redis()
            key = f"notify:count:{event_type}:{channel_name}"
            val = await redis.get(key)
            if val is None:
                return 0
            await redis.delete(key)
            return int(val)
        except Exception as e:
            logger.warning(f"Suppressed count read failed: {e}")
            return 0

    async def set_suppression(
        self, event_type: str, channel_name: str, window: int
    ) -> None:
        try:
            redis = await self._get_redis()
            key = f"notify:suppress:{event_type}:{channel_name}"
            await redis.setex(key, window, "1")
        except Exception as e:
            logger.warning(f"Suppression set failed ({event_type}/{channel_name}): {e}")

    async def check_escalation(
        self,
        event_type: str,
        threshold: int,
        window: int,
    ) -> bool:
        try:
            redis = await self._get_redis()
            key = f"notify:escalate:{event_type}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window)
            if count >= threshold:
                await redis.delete(key)
                return True
            return False
        except Exception as e:
            logger.warning(f"Escalation check failed ({event_type}): {e}")
            return False