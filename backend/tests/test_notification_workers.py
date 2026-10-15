"""Unit tests for NotificationWorkers (app/services/notification_workers.py).

Covers event enqueueing, lazy dependency resolution, subscribed-channel
resolution, retry delay math, the async delivery pipeline (escalation /
suppression / template rendering / channel delivery / retry scheduling),
and the main/retry/supervisor worker loops. Redis, rule-engine, logger and
channel boundaries are mocked.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notification_channels.base import NotificationResult
from app.services.notification_workers import (
    MAX_RETRIES,
    NotificationWorkers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload(**overrides):
    p = {
        "event_type": "terminal.blocked",
        "event_id": "evt-1",
        "timestamp": "2026-01-01T12:00:00",
        "data": {"ip": "1.2.3.4"},
        "source": "system",
        "severity": "info",
        "retry_count": 0,
    }
    p.update(overrides)
    return p


def _channel(channel_type="email", send_result=None):
    if send_result is None:
        send_result = NotificationResult(True, "ok", channel_type, event_id="evt-1")
    ch = MagicMock()
    ch.channel_type = channel_type
    ch.send = AsyncMock(return_value=send_result)
    return ch


def _rules_engine():
    re = MagicMock()
    re.get_rules_for_event = AsyncMock(return_value={})
    re.check_escalation = AsyncMock(return_value=False)
    re.check_suppression = AsyncMock(return_value=False)
    re.increment_suppressed_count = AsyncMock(return_value=1)
    re.get_and_clear_suppressed_count = AsyncMock(return_value=0)
    re.set_suppression = AsyncMock()
    re.match_rule = MagicMock(return_value=None)
    return re


def _logger():
    lg = MagicMock()
    lg.render_template = AsyncMock(return_value=None)
    lg.log_suppressed = AsyncMock()
    lg.log_sent = AsyncMock()
    lg.log_failed = AsyncMock()
    lg.log_retrying = AsyncMock()
    return lg


def _rule(suppress_enabled=False, escalate_enabled=False, **kw):
    rule = MagicMock()
    rule.escalate_enabled = escalate_enabled
    rule.escalate_threshold = 5
    rule.escalate_window = 3600
    rule.escalate_severity = "error"
    rule.suppress_enabled = suppress_enabled
    rule.suppress_window = 300
    for k, v in kw.items():
        setattr(rule, k, v)
    return rule


class _Task:
    """Minimal awaitable task stand-in for supervisor/stop tests."""

    def __init__(self, done):
        self._done = done
        self.cancelled = False

    def done(self):
        return self._done

    def cancel(self):
        self.cancelled = True

    def __await__(self):
        async def _inner():
            return None
        return _inner().__await__()


class _CrashTask(_Task):
    def __init__(self):
        super().__init__(True)

    def result(self):
        raise RuntimeError("worker crash")


class _CleanTask(_Task):
    def __init__(self):
        super().__init__(True)

    def result(self):
        return None


class _CancelledTask(_Task):
    def __init__(self):
        super().__init__(True)

    def result(self):
        raise asyncio.CancelledError()


class _BadAwaitTask(_Task):
    def __init__(self):
        super().__init__(False)

    def __await__(self):
        async def _inner():
            raise RuntimeError("boom")
        return _inner().__await__()


class _CancellingAwaitTask(_Task):
    def __init__(self):
        super().__init__(False)

    def __await__(self):
        async def _inner():
            raise asyncio.CancelledError()
        return _inner().__await__()


def _workers(channels=None, configs=None):
    return NotificationWorkers(channels or {}, configs or {})


# ---------------------------------------------------------------------------
# Lazy dependency resolution
# ---------------------------------------------------------------------------

class TestGetRulesEngine:
    @pytest.mark.asyncio
    async def test_creates_and_caches(self):
        w = _workers()
        sentinel = object()
        with patch("app.services.notification_rules.NotificationRulesEngine", return_value=sentinel) as m:
            r1 = w._get_rules_engine()
            r2 = w._get_rules_engine()
        assert r1 is sentinel
        assert r2 is sentinel
        m.assert_called_once()


class TestGetLogger:
    @pytest.mark.asyncio
    async def test_creates_and_caches(self):
        w = _workers()
        sentinel = object()
        db = MagicMock()
        with patch("app.services.notification_logging.NotificationLogger", return_value=sentinel) as m:
            l1 = w._get_logger(db)
            l2 = w._get_logger()
        assert l1 is sentinel
        assert l2 is sentinel
        m.assert_called_once_with(db)


class TestGetRedis:
    @pytest.mark.asyncio
    async def test_creates_and_caches(self):
        w = _workers()
        sentinel = object()
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=sentinel)) as m:
            r1 = await w._get_redis()
            r2 = await w._get_redis()
        assert r1 is sentinel
        assert r2 is sentinel
        m.assert_awaited_once()


# ---------------------------------------------------------------------------
# Subscribed channels
# ---------------------------------------------------------------------------

class TestGetSubscribedChannels:
    def test_matches_events(self):
        w = _workers(configs={
            "email": {"events": ["terminal.blocked"]},
            "webhook": {"events": ["terminal.unblocked"]},
            "noevents": {},
        })
        assert w._get_subscribed_channels("terminal.blocked") == ["email"]

    def test_no_match(self):
        w = _workers(configs={"email": {"events": ["terminal.blocked"]}})
        assert w._get_subscribed_channels("other") == []


# ---------------------------------------------------------------------------
# Retry delay
# ---------------------------------------------------------------------------

class TestRetryDelay:
    @pytest.mark.parametrize("count,expected", [(0, 10), (1, 20), (2, 40), (3, 80)])
    def test_exponential_backoff(self, count, expected):
        assert _workers()._retry_delay(count) == expected

    def test_capped_at_3600(self):
        assert _workers()._retry_delay(20) == 3600


# ---------------------------------------------------------------------------
# emit()
# ---------------------------------------------------------------------------

class TestEmit:
    @pytest.mark.asyncio
    async def test_success_enqueues(self):
        w = _workers()
        redis = AsyncMock()
        redis.lpush = AsyncMock()
        w._redis = redis
        result = await w.emit("terminal.blocked", {"ip": "1.2.3.4"}, source="s", severity="error")
        assert result == []
        redis.lpush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_exception_returns_empty(self):
        w = _workers()
        redis = AsyncMock()
        redis.lpush = AsyncMock(side_effect=RuntimeError("boom"))
        w._redis = redis
        assert await w.emit("terminal.blocked", {}) == []


# ---------------------------------------------------------------------------
# _deliver_notification()
# ---------------------------------------------------------------------------

class TestDeliverNoSubscribers:
    @pytest.mark.asyncio
    async def test_drops_event(self):
        w = _workers(channels={}, configs={})
        w._logger = _logger()
        await w._deliver_notification(_payload())
        w._logger.log_sent.assert_not_called()


class TestDeliverEscalation:
    @pytest.mark.asyncio
    async def test_escalation_applied(self):
        w = _workers()
        ch = _channel()
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        re = _rules_engine()
        re.get_rules_for_event = AsyncMock(return_value={"email": _rule(escalate_enabled=True)})
        re.check_escalation = AsyncMock(return_value=True)
        w._rules_engine = re
        lg = _logger()
        w._logger = lg

        await w._deliver_notification(_payload())

        sent_event = ch.send.await_args.args[0]
        assert sent_event.severity == "error"
        assert sent_event.data["escalated"] is True

    @pytest.mark.asyncio
    async def test_no_escalation_when_disabled(self):
        w = _workers()
        ch = _channel()
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        re = _rules_engine()
        re.get_rules_for_event = AsyncMock(return_value={"email": _rule(escalate_enabled=False)})
        w._rules_engine = re
        w._logger = _logger()

        await w._deliver_notification(_payload())

        re.check_escalation.assert_not_called()
        assert ch.send.await_args.args[0].severity == "info"


class TestDeliverChannelMissing:
    @pytest.mark.asyncio
    async def test_missing_channel_skipped(self):
        w = _workers()
        w._channels = {}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        re = _rules_engine()
        w._rules_engine = re
        lg = _logger()
        w._logger = lg
        await w._deliver_notification(_payload())
        lg.log_sent.assert_not_called()


class TestDeliverSuccess:
    @pytest.mark.asyncio
    async def test_no_template_no_rule(self):
        w = _workers()
        ch = _channel()
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        re = _rules_engine()
        w._rules_engine = re
        lg = _logger()
        w._logger = lg

        await w._deliver_notification(_payload())

        ch.send.assert_awaited_once()
        lg.log_sent.assert_awaited_once()
        lg.log_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_template_rendered_content(self):
        w = _workers()
        ch = _channel()
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        w._rules_engine = _rules_engine()
        lg = _logger()
        lg.render_template = AsyncMock(return_value={"subject": "S", "body": "B"})
        w._logger = lg

        await w._deliver_notification(_payload())

        kwargs = ch.send.await_args.kwargs
        assert kwargs["subject"] == "S"
        assert kwargs["message"] == "B"


class TestDeliverSuppression:
    @pytest.mark.asyncio
    async def test_suppressed(self):
        w = _workers()
        ch = _channel()
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        re = _rules_engine()
        re.match_rule = MagicMock(return_value=_rule(suppress_enabled=True))
        re.check_suppression = AsyncMock(return_value=True)
        w._rules_engine = re
        lg = _logger()
        w._logger = lg

        await w._deliver_notification(_payload())

        ch.send.assert_not_called()
        re.increment_suppressed_count.assert_awaited_once()
        lg.log_suppressed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_suppressed_count_attached(self):
        w = _workers()
        ch = _channel()
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        re = _rules_engine()
        re.match_rule = MagicMock(return_value=_rule(suppress_enabled=True))
        re.check_suppression = AsyncMock(return_value=False)
        re.get_and_clear_suppressed_count = AsyncMock(return_value=3)
        w._rules_engine = re
        w._logger = _logger()

        await w._deliver_notification(_payload())

        assert ch.send.await_args.args[0].data["suppressed_count"] == 3
        re.set_suppression.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_suppression_bypassed_when_escalated(self):
        w = _workers()
        ch = _channel()
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        re = _rules_engine()
        re.match_rule = MagicMock(return_value=_rule(suppress_enabled=True))
        re.check_suppression = AsyncMock(return_value=True)
        w._rules_engine = re
        w._logger = _logger()

        await w._deliver_notification(_payload(data={"escalated": True}))

        re.check_suppression.assert_not_called()
        ch.send.assert_awaited_once()


class TestDeliverFailure:
    @pytest.mark.asyncio
    async def test_auth_error_logs_failed_without_retry(self):
        w = _workers()
        ch = _channel(send_result=NotificationResult(False, "bad", "email", error_code="AUTH_ERROR"))
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        w._rules_engine = _rules_engine()
        lg = _logger()
        w._logger = lg

        with patch.object(w, "_schedule_retry") as sched:
            await w._deliver_notification(_payload())

        sched.assert_not_called()
        lg.log_failed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transient_error_schedules_retry(self):
        w = _workers()
        ch = _channel(send_result=NotificationResult(False, "x", "email", error_code="SEND_ERROR"))
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        w._rules_engine = _rules_engine()
        w._logger = _logger()

        with patch.object(w, "_schedule_retry") as sched:
            await w._deliver_notification(_payload())
        sched.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transient_error_exhausted_retries(self):
        w = _workers()
        ch = _channel(send_result=NotificationResult(False, "x", "email", error_code="SEND_ERROR"))
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        w._rules_engine = _rules_engine()
        lg = _logger()
        w._logger = lg

        with patch.object(w, "_schedule_retry") as sched:
            await w._deliver_notification(_payload(retry_count=MAX_RETRIES))

        sched.assert_not_called()
        lg.log_failed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_raises_exception(self):
        w = _workers()
        ch = _channel()
        ch.send = AsyncMock(side_effect=RuntimeError("boom"))
        w._channels = {"email": ch}
        w._channel_configs = {"email": {"events": ["terminal.blocked"]}}
        w._rules_engine = _rules_engine()
        lg = _logger()
        w._logger = lg

        with patch.object(w, "_schedule_retry") as sched:
            await w._deliver_notification(_payload())
        sched.assert_awaited_once()


# ---------------------------------------------------------------------------
# _schedule_retry()
# ---------------------------------------------------------------------------

class TestScheduleRetry:
    @pytest.mark.asyncio
    async def test_success(self):
        w = _workers()
        redis = AsyncMock()
        redis.zadd = AsyncMock()
        w._redis = redis
        lg = _logger()
        w._logger = lg
        result = NotificationResult(False, "fail", "email", event_id="evt-1", error_code="SEND_ERROR")

        await w._schedule_retry(_payload(), "email", result, 0)

        redis.zadd.assert_awaited_once()
        lg.log_retrying.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_swallowed(self):
        w = _workers()
        redis = AsyncMock()
        redis.zadd = AsyncMock(side_effect=RuntimeError("boom"))
        w._redis = redis
        w._logger = _logger()
        result = NotificationResult(False, "fail", "email", event_id="evt-1")
        # should not raise
        await w._schedule_retry(_payload(), "email", result, 0)


# ---------------------------------------------------------------------------
# Worker lifecycle / loops
# ---------------------------------------------------------------------------

class TestStartWorkers:
    @pytest.mark.asyncio
    async def test_creates_three_tasks(self):
        w = _workers()
        w._main_worker = MagicMock()
        w._retry_worker = MagicMock()
        w._worker_supervisor = MagicMock()
        with patch("asyncio.create_task", return_value="t") as ct:
            await w.start_workers()
        assert w._worker_running is True
        assert w._main_worker_task == "t"
        assert w._retry_worker_task == "t"
        assert w._supervisor_task == "t"
        assert ct.call_count == 3

    @pytest.mark.asyncio
    async def test_already_running(self):
        w = _workers()
        w._worker_running = True
        with patch("asyncio.create_task") as ct:
            await w.start_workers()
        ct.assert_not_called()


class TestStopWorkers:
    @pytest.mark.asyncio
    async def test_cancels_running_tasks(self):
        w = _workers()
        w._worker_running = True
        pending = _Task(False)
        done = _Task(True)
        w._main_worker_task = pending
        w._retry_worker_task = done
        w._supervisor_task = None
        await w.stop_workers()
        assert w._worker_running is False
        assert pending.cancelled is True
        assert done.cancelled is False

    @pytest.mark.asyncio
    async def test_await_exception_swallowed(self):
        w = _workers()
        w._worker_running = True
        w._main_worker_task = _BadAwaitTask()
        w._retry_worker_task = None
        w._supervisor_task = None
        # Should not raise even though await raises inside stop_workers
        await w.stop_workers()
        assert w._worker_running is False

    @pytest.mark.asyncio
    async def test_stop_workers_swallows_cancelled_error(self):
        w = _workers()
        w._worker_running = True
        w._main_worker_task = _CancellingAwaitTask()
        w._retry_worker_task = None
        w._supervisor_task = None
        # CancelledError must not propagate out of stop_workers
        await w.stop_workers()
        assert w._worker_running is False


class TestMainWorker:
    @pytest.mark.asyncio
    async def test_delivers_payload(self):
        w = _workers()
        redis = AsyncMock()
        payload_str = json.dumps(_payload())

        async def _brpop(*a, **k):
            w._worker_running = False
            return ("main", payload_str)

        redis.brpop = AsyncMock(side_effect=_brpop)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock()

        await w._main_worker()

        w._deliver_notification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_brpop_none_continues(self):
        w = _workers()
        redis = AsyncMock()

        async def _brpop(*a, **k):
            w._worker_running = False
            return None

        redis.brpop = AsyncMock(side_effect=_brpop)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock()

        await w._main_worker()

        w._deliver_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_brpop_error_handler(self):
        w = _workers()
        redis = AsyncMock()

        async def _brpop(*a, **k):
            w._worker_running = False
            raise RuntimeError("boom")

        redis.brpop = AsyncMock(side_effect=_brpop)
        w._redis = redis
        w._worker_running = True

        async def _sleep(_):
            return None

        with patch("asyncio.sleep", side_effect=_sleep):
            await w._main_worker()

    @pytest.mark.asyncio
    async def test_malformed_payload_dropped(self):
        w = _workers()
        redis = AsyncMock()

        async def _brpop(*a, **k):
            w._worker_running = False
            return ("main", "not-json{{")

        redis.brpop = AsyncMock(side_effect=_brpop)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock()
        w._requeue = AsyncMock()

        await w._main_worker()

        w._deliver_notification.assert_not_called()
        w._requeue.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivery_error_requeues(self):
        w = _workers()
        redis = AsyncMock()
        payload_str = json.dumps(_payload())

        async def _brpop(*a, **k):
            w._worker_running = False
            return ("main", payload_str)

        redis.brpop = AsyncMock(side_effect=_brpop)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock(side_effect=RuntimeError("boom"))
        w._requeue = AsyncMock()

        await w._main_worker()

        w._requeue.assert_awaited_once()
        assert w._requeue.call_args.args[0]["event_id"] == "evt-1"


class TestRetryWorker:
    @pytest.mark.asyncio
    async def test_processes_due_items(self):
        w = _workers()
        redis = AsyncMock()
        member = json.dumps(_payload(retry_count=1))
        redis.zrangebyscore = AsyncMock(return_value=[member])

        async def _zrem(*a, **k):
            w._worker_running = False
            return 1

        redis.zrem = AsyncMock(side_effect=_zrem)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock()

        await w._retry_worker()

        w._deliver_notification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_zrem_zero_skips(self):
        w = _workers()
        redis = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=[json.dumps(_payload())])

        async def _zrem(*a, **k):
            w._worker_running = False
            return 0

        redis.zrem = AsyncMock(side_effect=_zrem)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock()

        await w._retry_worker()

        w._deliver_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_items_sleeps(self):
        w = _workers()
        redis = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=[])
        w._redis = redis
        w._worker_running = True

        async def _sleep(_):
            w._worker_running = False

        with patch("asyncio.sleep", side_effect=_sleep):
            await w._retry_worker()

    @pytest.mark.asyncio
    async def test_item_error_swallowed(self):
        w = _workers()
        redis = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=[json.dumps(_payload())])

        async def _zrem(*a, **k):
            w._worker_running = False
            raise RuntimeError("boom")

        redis.zrem = AsyncMock(side_effect=_zrem)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock()

        await w._retry_worker()

        w._deliver_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_outer_error_swallowed(self):
        w = _workers()
        redis = AsyncMock()

        async def _zrangebyscore(*a, **k):
            w._worker_running = False
            raise RuntimeError("boom")

        redis.zrangebyscore = AsyncMock(side_effect=_zrangebyscore)
        w._redis = redis
        w._worker_running = True

        async def _sleep(_):
            return None

        with patch("asyncio.sleep", side_effect=_sleep):
            await w._retry_worker()

    @pytest.mark.asyncio
    async def test_malformed_payload_dropped(self):
        w = _workers()
        redis = AsyncMock()
        redis.zrangebyscore = AsyncMock(return_value=["not-json{{"])

        async def _zrem(*a, **k):
            w._worker_running = False
            return 1

        redis.zrem = AsyncMock(side_effect=_zrem)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock()

        await w._retry_worker()

        redis.zrem.assert_awaited_once()  # 移除坏数据
        w._deliver_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivery_error_requeues(self):
        w = _workers()
        redis = AsyncMock()
        member = json.dumps(_payload())
        redis.zrangebyscore = AsyncMock(return_value=[member])

        async def _zrem(*a, **k):
            w._worker_running = False
            return 1

        redis.zrem = AsyncMock(side_effect=_zrem)
        w._redis = redis
        w._worker_running = True
        w._deliver_notification = AsyncMock(side_effect=RuntimeError("boom"))
        w._requeue = AsyncMock()

        await w._retry_worker()

        w._requeue.assert_awaited_once()


class TestRequeue:
    @pytest.mark.asyncio
    async def test_requeue_increments_retry_count(self):
        w = _workers()
        redis = AsyncMock()
        w._redis = redis

        await w._requeue(_payload(), "boom")

        redis.zadd.assert_awaited_once()
        _, mapping = redis.zadd.call_args.args
        new_payload = json.loads(next(iter(mapping)))
        assert new_payload["retry_count"] == 1
        assert new_payload["event_id"] == "evt-1"

    @pytest.mark.asyncio
    async def test_requeue_drops_when_exhausted(self):
        w = _workers()
        redis = AsyncMock()
        w._redis = redis

        await w._requeue(_payload(retry_count=MAX_RETRIES), "boom")

        redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_requeue_redis_error_swallowed(self):
        w = _workers()
        redis = AsyncMock()
        redis.zadd = AsyncMock(side_effect=RuntimeError("boom"))
        w._redis = redis

        await w._requeue(_payload(), "boom")  # 不应抛出


class TestWorkerSupervisor:
    @pytest.mark.asyncio
    async def test_breaks_when_stopped(self):
        w = _workers()
        w._worker_running = True

        async def _sleep(_):
            w._worker_running = False

        with patch("asyncio.sleep", side_effect=_sleep):
            await w._worker_supervisor()

    @pytest.mark.asyncio
    async def test_crash_branch_logs(self):
        w = _workers()
        w._worker_running = True
        w._main_worker = MagicMock()
        w._retry_worker = MagicMock()
        w._main_worker_task = _CrashTask()
        w._retry_worker_task = None
        calls = {"n": 0}

        async def _sleep(_):
            calls["n"] += 1
            if calls["n"] >= 3:
                w._worker_running = False

        with patch("asyncio.sleep", side_effect=_sleep), patch("asyncio.create_task") as ct:
            await w._worker_supervisor()
        # The crash triggers a restart via create_task on the third loop pass.
        ct.assert_called_once()

    @pytest.mark.asyncio
    async def test_clean_exit_restarts(self):
        w = _workers()
        w._worker_running = True
        w._main_worker = MagicMock()
        w._retry_worker = MagicMock()
        w._main_worker_task = _CleanTask()
        w._retry_worker_task = None
        calls = {"n": 0}

        async def _sleep(_):
            calls["n"] += 1
            if calls["n"] == 2:
                w._worker_running = False

        with patch("asyncio.sleep", side_effect=_sleep), patch("asyncio.create_task") as ct:
            await w._worker_supervisor()
        ct.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_cancelled_error(self):
        w = _workers()
        w._worker_running = True
        w._main_worker = MagicMock()
        w._retry_worker = MagicMock()
        w._main_worker_task = _CancelledTask()
        w._retry_worker_task = None
        calls = {"n": 0}

        async def _sleep(_):
            calls["n"] += 1
            if calls["n"] == 2:
                w._worker_running = False

        with patch("asyncio.sleep", side_effect=_sleep), patch("asyncio.create_task") as ct:
            await w._worker_supervisor()
        ct.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_crash_branch(self):
        w = _workers()
        w._worker_running = True
        w._main_worker = MagicMock()
        w._retry_worker = MagicMock()
        w._main_worker_task = None
        w._retry_worker_task = _CrashTask()
        calls = {"n": 0}

        async def _sleep(_):
            calls["n"] += 1
            if calls["n"] >= 3:
                w._worker_running = False

        with patch("asyncio.sleep", side_effect=_sleep), patch("asyncio.create_task") as ct:
            await w._worker_supervisor()
        ct.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_clean_exit(self):
        w = _workers()
        w._worker_running = True
        w._main_worker = MagicMock()
        w._retry_worker = MagicMock()
        w._main_worker_task = None
        w._retry_worker_task = _CleanTask()
        calls = {"n": 0}

        async def _sleep(_):
            calls["n"] += 1
            if calls["n"] == 2:
                w._worker_running = False

        with patch("asyncio.sleep", side_effect=_sleep), patch("asyncio.create_task") as ct:
            await w._worker_supervisor()
        ct.assert_called_once()