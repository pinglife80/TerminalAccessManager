"""
Notification Workers.

Handles async notification delivery via Redis queue with retry mechanism.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from app.core.timezone import now, now_utc
from app.services.notification_channels import (
    NotificationChannelBase,
    NotificationEvent,
    NotificationResult,
    get_channel,
)

QUEUE_KEY = "notify:queue:main"
RETRY_KEY = "notify:queue:retry"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 10
WORKER_POLL_INTERVAL = 1
RETRY_WORKER_INTERVAL = 5
WORKER_RESTART_DELAY = 5


class NotificationWorkers:
    """Async worker manager for notification delivery."""

    def __init__(
        self,
        channels: dict[str, NotificationChannelBase],
        channel_configs: dict[str, dict],
    ):
        self._channels = channels
        self._channel_configs = channel_configs
        self._worker_running = False
        self._main_worker_task: Any = None
        self._retry_worker_task: Any = None
        self._supervisor_task: Any = None
        self._rules_engine = None
        self._logger = None
        self._redis = None

    def _get_rules_engine(self):
        if self._rules_engine is None:
            from app.services.notification_rules import NotificationRulesEngine
            self._rules_engine = NotificationRulesEngine()
        return self._rules_engine

    def _get_logger(self, db=None):
        if self._logger is None:
            from app.services.notification_logging import NotificationLogger
            self._logger = NotificationLogger(db)
        return self._logger

    async def _get_redis(self):
        if self._redis is None:
            from app.core.security import get_redis_client
            self._redis = await get_redis_client()
        return self._redis

    def _get_subscribed_channels(self, event_type: str) -> list[str]:
        subscribed = []
        for channel_name, channel_info in self._channel_configs.items():
            if event_type in channel_info.get("events", []):
                subscribed.append(channel_name)
        return subscribed

    async def start_workers(self) -> None:
        import asyncio

        if self._worker_running:
            logger.warning("Notification workers already running")
            return
        self._worker_running = True
        self._main_worker_task = asyncio.create_task(self._main_worker())
        self._retry_worker_task = asyncio.create_task(self._retry_worker())
        self._supervisor_task = asyncio.create_task(self._worker_supervisor())
        logger.info("Notification workers started")

    async def stop_workers(self) -> None:
        self._worker_running = False
        for task in (
            self._main_worker_task,
            self._retry_worker_task,
            self._supervisor_task,
        ):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except Exception:
                    pass
        logger.info("Notification workers stopped")

    async def _worker_supervisor(self) -> None:
        import asyncio

        logger.info("Notification worker supervisor started")
        while self._worker_running:
            try:
                await asyncio.sleep(WORKER_RESTART_DELAY)
                if not self._worker_running:
                    break

                if (
                    self._main_worker_task is not None
                    and self._main_worker_task.done()
                ):
                    try:
                        self._main_worker_task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(
                            f"Main worker crashed with error: {e}. "
                            f"Restarting in {WORKER_RESTART_DELAY}s..."
                        )
                        await asyncio.sleep(WORKER_RESTART_DELAY)
                        if self._worker_running:
                            self._main_worker_task = asyncio.create_task(
                                self._main_worker()
                            )
                            logger.info("Main worker restarted")
                    else:
                        logger.warning("Main worker exited cleanly, restarting...")
                        if self._worker_running:
                            self._main_worker_task = asyncio.create_task(
                                self._main_worker()
                            )

                if (
                    self._retry_worker_task is not None
                    and self._retry_worker_task.done()
                ):
                    try:
                        self._retry_worker_task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(
                            f"Retry worker crashed with error: {e}. "
                            f"Restarting in {WORKER_RESTART_DELAY}s..."
                        )
                        await asyncio.sleep(WORKER_RESTART_DELAY)
                        if self._worker_running:
                            self._retry_worker_task = asyncio.create_task(
                                self._retry_worker()
                            )
                            logger.info("Retry worker restarted")
                    else:
                        logger.warning("Retry worker exited cleanly, restarting...")
                        if self._worker_running:
                            self._retry_worker_task = asyncio.create_task(
                                self._retry_worker()
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker supervisor error: {e}")
                await asyncio.sleep(WORKER_RESTART_DELAY)
        logger.info("Notification worker supervisor stopped")

    async def emit(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        source: str = "system",
        severity: str = "info",
    ) -> list[NotificationResult]:
        event = NotificationEvent(
            id=str(uuid.uuid4()),
            type=event_type,
            timestamp=now(),
            data=dict(data) if data else {},
            source=source,
            severity=severity,
        )
        try:
            redis = await self._get_redis()
            payload = json.dumps(
                {
                    "event_id": event.id,
                    "event_type": event.type,
                    "data": event.data,
                    "source": event.source,
                    "severity": event.severity,
                    "timestamp": event.timestamp.isoformat(),
                    "retry_count": 0,
                    "queued_at": now().isoformat(),
                }
            )
            await redis.lpush(QUEUE_KEY, payload)
            logger.debug(f"Event enqueued: {event_type} (id={event.id[:8]})")
        except Exception as e:
            logger.error(f"Failed to enqueue event {event_type}: {e}")
        return []

    async def _main_worker(self) -> None:
        import asyncio

        while self._worker_running:
            try:
                redis = await self._get_redis()
                result = await redis.brpop(QUEUE_KEY, timeout=WORKER_POLL_INTERVAL)
                if result is None:
                    continue
                _, payload_str = result
                payload = json.loads(payload_str)
                await self._deliver_notification(payload)
            except Exception as e:
                logger.error(f"Main worker error: {e}")
                await asyncio.sleep(WORKER_POLL_INTERVAL)

    async def _retry_worker(self) -> None:
        import asyncio

        while self._worker_running:
            try:
                redis = await self._get_redis()
                now_ts = now_utc().timestamp()
                items = await redis.zrangebyscore(RETRY_KEY, 0, now_ts)
                for member in items:
                    try:
                        removed = await redis.zrem(RETRY_KEY, member)
                        if removed == 0:
                            continue
                        payload = json.loads(member)
                        await self._deliver_notification(payload)
                    except Exception as e:
                        logger.error(f"Retry worker item error: {e}")
                if not items:
                    await asyncio.sleep(RETRY_WORKER_INTERVAL)
            except Exception as e:
                logger.error(f"Retry worker error: {e}")
                await asyncio.sleep(RETRY_WORKER_INTERVAL)

    async def _deliver_notification(self, payload: dict[str, Any]) -> None:
        event_type = payload["event_type"]
        event_id = payload["event_id"]
        retry_count = payload.get("retry_count", 0)
        event = NotificationEvent(
            id=event_id,
            type=event_type,
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            data=dict(payload.get("data", {})),
            source=payload.get("source", "system"),
            severity=payload.get("severity", "info"),
        )

        retry_channel = payload.get("_channel_name")
        if retry_channel:
            # Retry is scoped to the single failed channel to avoid
            # re-delivering to channels that already succeeded.
            subscribed_channels = [retry_channel] if retry_channel in self._channels else []
        else:
            subscribed_channels = self._get_subscribed_channels(event_type)
        if not subscribed_channels:
            logger.debug(f"No subscribers for {event_type}, dropping")
            return

        rules_engine = self._get_rules_engine()
        rules = await rules_engine.get_rules_for_event(event_type)

        for rule in rules.values():
            if rule.escalate_enabled:
                escalated = await rules_engine.check_escalation(
                    event_type, rule.escalate_threshold, rule.escalate_window
                )
                if escalated:
                    event.severity = rule.escalate_severity
                    event.data["escalated"] = True
                    logger.info(
                        f"Event {event_type} escalated to {rule.escalate_severity} "
                        f"(threshold {rule.escalate_threshold} reached)"
                    )
                break
        notification_logger = self._get_logger()

        for channel_name in subscribed_channels:
            channel = self._channels.get(channel_name)
            if not channel:
                continue

            rule = rules_engine.match_rule(rules, channel_name)
            bypass_suppression = event.data.get("escalated", False)

            if rule and rule.suppress_enabled:
                if not bypass_suppression and await rules_engine.check_suppression(
                    event_type, channel_name
                ):
                    count = await rules_engine.increment_suppressed_count(
                        event_type, channel_name
                    )
                    logger.debug(
                        f"Suppressed {event_type} for {channel_name} "
                        f"({count} in window)"
                    )
                    await notification_logger.log_suppressed(
                        event, channel_name, rule.suppress_window
                    )
                    continue

                suppressed_count = await rules_engine.get_and_clear_suppressed_count(
                    event_type, channel_name
                )
                if suppressed_count > 0:
                    event.data["suppressed_count"] = suppressed_count

            success = False
            result: NotificationResult | None = None
            try:
                template_content = await notification_logger.render_template(
                    event, channel.channel_type
                )
                if template_content:
                    result = await channel.send(
                        event=event,
                        subject=template_content.get("subject"),
                        message=template_content.get("body"),
                    )
                else:
                    result = await channel.send(event)
                success = result.success
            except Exception as e:
                logger.error(f"Delivery failed for {channel_name}: {e}")
                result = NotificationResult(
                    success=False,
                    message=str(e),
                    channel=getattr(channel, "channel_type", "unknown"),
                    event_id=event.id,
                    error_code="SEND_ERROR",
                )

            if success:
                if rule and rule.suppress_enabled:
                    await rules_engine.set_suppression(
                        event_type, channel_name, rule.suppress_window
                    )
                await notification_logger.log_sent(event, channel_name, result)
            elif result and result.error_code == "AUTH_ERROR":
                # Auth errors are permanent — don't retry, just log
                logger.warning(
                    f"Skipping retry for {channel_name}: SMTP auth failed. "
                    f"Fix email credentials in Settings -> Email Settings."
                )
                await notification_logger.log_failed(
                    event, channel_name, result, retry_count
                )
            else:
                if retry_count < MAX_RETRIES:
                    await self._schedule_retry(
                        payload, channel_name, result, retry_count
                    )
                else:
                    await notification_logger.log_failed(
                        event, channel_name, result, retry_count
                    )

    def _retry_delay(self, retry_count: int) -> int:
        delay = RETRY_BASE_DELAY * (2 ** retry_count)
        return min(delay, 3600)

    async def _schedule_retry(
        self,
        payload: dict[str, Any],
        channel_name: str,
        result: NotificationResult,
        retry_count: int,
    ) -> None:
        try:
            redis = await self._get_redis()
            new_retry_count = retry_count + 1
            delay = self._retry_delay(retry_count)
            next_retry_ts = now_utc() + timedelta(seconds=delay)
            new_payload = {**payload, "retry_count": new_retry_count}
            new_payload["_channel_name"] = channel_name
            member = json.dumps(new_payload, sort_keys=True)
            await redis.zadd(RETRY_KEY, {member: next_retry_ts.timestamp()})
            logger.info(
                f"Scheduled retry #{new_retry_count} for {payload['event_type']}/"
                f"{channel_name} in {delay}s"
            )
            event = NotificationEvent(
                id=payload["event_id"],
                type=payload["event_type"],
                timestamp=datetime.fromisoformat(payload["timestamp"]),
                data=dict(payload.get("data", {})),
                source=payload.get("source", "system"),
                severity=payload.get("severity", "info"),
            )
            notification_logger = self._get_logger()
            await notification_logger.log_retrying(
                event, channel_name, result, new_retry_count, next_retry_ts
            )
        except Exception as e:
            logger.error(f"Failed to schedule retry: {e}")