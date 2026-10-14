"""Unit tests for NotificationRulesEngine (app/services/notification_rules.py)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.notification import NotificationRule
from app.services.notification_rules import NotificationRulesEngine


class TestGetRedis:
    @pytest.mark.asyncio
    async def test_caches_redis_client(self):
        engine = NotificationRulesEngine()
        sentinel = object()
        with patch("app.core.security.get_redis_client", new=AsyncMock(return_value=sentinel)) as m:
            r1 = await engine._get_redis()
            r2 = await engine._get_redis()
        assert r1 is sentinel
        assert r2 is sentinel
        m.assert_awaited_once()


class TestGetRulesForEvent:
    def _rule(self, name, channel_name, priority=1):
        return NotificationRule(
            name=name,
            event_type="terminal.blocked",
            channel_name=channel_name,
            enabled=True,
            priority=priority,
        )

    @pytest.mark.asyncio
    async def test_dedups_by_channel_name_first_wins(self):
        r1 = self._rule("r1", "email", priority=1)
        r2 = self._rule("r2", "email", priority=2)
        r3 = self._rule("r3", None, priority=3)
        db = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [r1, r2, r3]
        db.execute = AsyncMock(return_value=result)

        engine = NotificationRulesEngine()
        rules = await engine.get_rules_for_event("terminal.blocked", db)

        assert rules == {"email": r1, None: r3}

    @pytest.mark.asyncio
    async def test_uses_factory_when_no_db(self):
        rule = self._rule("r1", "email")
        fake_session = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [rule]
        fake_session.execute = AsyncMock(return_value=result)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=fake_session)
        cm.__aexit__ = AsyncMock(return_value=False)

        engine = NotificationRulesEngine()
        with patch("app.core.database.async_session_factory", return_value=cm):
            rules = await engine.get_rules_for_event("terminal.blocked", None)

        assert rules == {"email": rule}

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=Exception("boom"))

        engine = NotificationRulesEngine()
        rules = await engine.get_rules_for_event("terminal.blocked", db)

        assert rules == {}


class TestMatchRule:
    def test_channel_specific_wins(self):
        engine = NotificationRulesEngine()
        specific = NotificationRule(name="s", event_type="x", channel_name="email")
        default = NotificationRule(name="d", event_type="x", channel_name=None)
        rules = {"email": specific, None: default}
        assert engine.match_rule(rules, "email") is specific

    def test_falls_back_to_default(self):
        engine = NotificationRulesEngine()
        default = NotificationRule(name="d", event_type="x", channel_name=None)
        rules = {None: default}
        assert engine.match_rule(rules, "slack") is default

    def test_no_match_returns_none(self):
        engine = NotificationRulesEngine()
        assert engine.match_rule({}, "slack") is None


class TestSuppression:
    @pytest.mark.asyncio
    async def test_check_suppression_false_then_true(self, mock_redis):
        engine = NotificationRulesEngine()
        engine._redis = mock_redis
        assert await engine.check_suppression("terminal.blocked", "email") is False
        await engine.set_suppression("terminal.blocked", "email", 300)
        assert await engine.check_suppression("terminal.blocked", "email") is True

    @pytest.mark.asyncio
    async def test_check_suppression_false_on_exception(self):
        engine = NotificationRulesEngine()
        engine._redis = MagicMock()
        engine._redis.exists = AsyncMock(side_effect=Exception("boom"))
        assert await engine.check_suppression("x", "y") is False


class TestSuppressedCount:
    @pytest.mark.asyncio
    async def test_increment_returns_increasing_count(self, mock_redis):
        engine = NotificationRulesEngine()
        engine._redis = mock_redis
        assert await engine.increment_suppressed_count("x", "y") == 1
        assert await engine.increment_suppressed_count("x", "y") == 2

    @pytest.mark.asyncio
    async def test_increment_zero_on_exception(self):
        engine = NotificationRulesEngine()
        engine._redis = MagicMock()
        engine._redis.incr = AsyncMock(side_effect=Exception("boom"))
        assert await engine.increment_suppressed_count("x", "y") == 0

    @pytest.mark.asyncio
    async def test_get_and_clear(self, mock_redis):
        engine = NotificationRulesEngine()
        engine._redis = mock_redis
        mock_redis._data["notify:count:x:y"] = "5"
        assert await engine.get_and_clear_suppressed_count("x", "y") == 5
        assert "notify:count:x:y" not in mock_redis._data
        assert await engine.get_and_clear_suppressed_count("x", "y") == 0

    @pytest.mark.asyncio
    async def test_get_and_clear_zero_on_exception(self):
        engine = NotificationRulesEngine()
        engine._redis = MagicMock()
        engine._redis.get = AsyncMock(side_effect=Exception("boom"))
        assert await engine.get_and_clear_suppressed_count("x", "y") == 0


class TestSetSuppression:
    @pytest.mark.asyncio
    async def test_sets_key(self, mock_redis):
        engine = NotificationRulesEngine()
        engine._redis = mock_redis
        await engine.set_suppression("x", "y", 60)
        assert mock_redis._data["notify:suppress:x:y"] == "1"

    @pytest.mark.asyncio
    async def test_swallows_exception(self):
        engine = NotificationRulesEngine()
        engine._redis = MagicMock()
        engine._redis.setex = AsyncMock(side_effect=Exception("boom"))
        # should not raise
        await engine.set_suppression("x", "y", 60)


class TestEscalation:
    @pytest.mark.asyncio
    async def test_escalates_after_threshold(self, mock_redis):
        engine = NotificationRulesEngine()
        engine._redis = mock_redis
        assert await engine.check_escalation("x", 3, 3600) is False
        assert await engine.check_escalation("x", 3, 3600) is False
        assert await engine.check_escalation("x", 3, 3600) is True
        assert "notify:escalate:x" not in mock_redis._data

    @pytest.mark.asyncio
    async def test_false_on_exception(self):
        engine = NotificationRulesEngine()
        engine._redis = MagicMock()
        engine._redis.incr = AsyncMock(side_effect=Exception("boom"))
        assert await engine.check_escalation("x", 3, 3600) is False