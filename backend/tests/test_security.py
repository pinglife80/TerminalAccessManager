"""Tests for security module — Redis fail-open and token management"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.security import (
    is_token_blacklisted,
    get_token_version,
    increment_token_version,
    check_login_attempts,
    check_captcha_required,
    record_failed_login,
    reset_login_attempts,
    verify_captcha,
)
from app.services.terminal_service import _escape_like, _normalize_mac


class TestEscapeLike:
    """Test LIKE wildcard escaping"""

    def test_escape_percent(self):
        assert _escape_like("test%value") == r"test\%value"

    def test_escape_underscore(self):
        assert _escape_like("test_value") == r"test\_value"

    def test_escape_both(self):
        assert _escape_like("a_b%c") == r"a\_b\%c"

    def test_no_escape_needed(self):
        assert _escape_like("normal") == "normal"

    def test_empty_string(self):
        assert _escape_like("") == ""


class TestNormalizeMac:
    """Test MAC address normalization"""

    def test_colon_separated(self):
        assert _normalize_mac("AA:BB:CC:DD:EE:FF") == "AABBCCDDEEFF"

    def test_dash_separated(self):
        assert _normalize_mac("AA-BB-CC-DD-EE-FF") == "AABBCCDDEEFF"

    def test_dot_separated(self):
        assert _normalize_mac("AABB.CCDD.EEFF") == "AABBCCDDEEFF"

    def test_mixed_case(self):
        assert _normalize_mac("aa:bb:cc:dd:ee:ff") == "AABBCCDDEEFF"

    def test_already_normalized(self):
        assert _normalize_mac("AABBCCDDEEFF") == "AABBCCDDEEFF"


class TestRedisFailOpen:
    """Test that security functions degrade gracefully when Redis is unavailable"""

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_fail_open(self):
        """Token blacklist should return False (allow) when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await is_token_blacklisted("some-jti")
            assert result is False

    @pytest.mark.asyncio
    async def test_get_token_version_fail_open(self):
        """Token version should return 0 when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await get_token_version(1)
            assert result == 0

    @pytest.mark.asyncio
    async def test_increment_token_version_fail_open(self):
        """Token version increment should return 0 when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await increment_token_version(1)
            assert result == 0

    @pytest.mark.asyncio
    async def test_check_login_attempts_fail_open(self):
        """Login attempt check should return False (not locked) when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await check_login_attempts("testuser")
            assert result is False

    @pytest.mark.asyncio
    async def test_check_captcha_required_fail_open(self):
        """Captcha check should return False (not required) when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await check_captcha_required("testuser")
            assert result is False

    @pytest.mark.asyncio
    async def test_record_failed_login_fail_open(self):
        """Recording failed login should not raise when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            # Should not raise
            await record_failed_login("testuser")

    @pytest.mark.asyncio
    async def test_reset_login_attempts_fail_open(self):
        """Resetting login attempts should not raise when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            # Should not raise
            await reset_login_attempts("testuser")

    @pytest.mark.asyncio
    async def test_verify_captcha_fail_closed(self):
        """Captcha verification should return False when Redis is unavailable"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await verify_captcha("some-id", "42")
            assert result is False


class TestRedisNormalOperation:
    """Test security functions with mock Redis working normally"""

    @pytest.mark.asyncio
    async def test_token_blacklist_flow(self, mock_redis_patch):
        """Test adding and checking token blacklist"""
        mock_redis = mock_redis_patch
        # Token not blacklisted initially
        result = await is_token_blacklisted("test-jti")
        assert result is False

        # Add to blacklist
        from datetime import datetime, timedelta, timezone
        from app.core.security import add_token_to_blacklist
        exp = datetime.now(timezone.utc) + timedelta(hours=1)
        await add_token_to_blacklist("test-jti", exp)

        # Now should be blacklisted
        result = await is_token_blacklisted("test-jti")
        assert result is True

    @pytest.mark.asyncio
    async def test_token_version_flow(self, mock_redis_patch):
        """Test token version increment and retrieval"""
        # Initial version should be 0
        version = await get_token_version(1)
        assert version == 0

        # Increment version
        new_version = await increment_token_version(1)
        assert new_version == 1

        # Get version should return new value
        version = await get_token_version(1)
        assert version == 1

    @pytest.mark.asyncio
    async def test_login_lockout_flow(self, mock_redis_patch):
        """Test login lockout mechanism"""
        # Not locked initially
        result = await check_login_attempts("testuser")
        assert result is False

        # Record failed logins
        await record_failed_login("testuser")

        # Should still not be locked after 1 attempt
        result = await check_login_attempts("testuser")
        assert result is False

    @pytest.mark.asyncio
    async def test_captcha_flow(self, mock_redis_patch):
        """Test captcha generation and verification"""
        from app.core.security import generate_captcha

        # Generate captcha
        captcha_id, question = await generate_captcha()
        assert captcha_id is not None
        assert question is not None
        assert "+" in question or "-" in question

        # Verify with wrong answer
        result = await verify_captcha(captcha_id, "99999")
        assert result is False

    @pytest.mark.asyncio
    async def test_reset_login_attempts(self, mock_redis_patch):
        """Test resetting login attempts"""
        # Record a failed login
        await record_failed_login("testuser")
        # Reset should not raise
        await reset_login_attempts("testuser")
