"""Tests for security module — Redis fail-closed/fail-open and token management"""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request

from app.core.config import settings
from app.core.security import (
    add_token_to_blacklist,
    authenticate_user,
    check_captcha_required,
    check_login_attempts,
    create_access_token_async,
    create_refresh_token_async,
    generate_captcha,
    get_client_ip,
    get_current_active_superuser,
    get_current_user,
    get_token_version,
    hash_password,
    increment_token_version,
    is_token_blacklisted,
    record_failed_login,
    reset_login_attempts,
    verify_captcha,
    verify_password,
)
from app.services.terminal_service import _escape_like, _normalize_mac


def _solve_question(question: str) -> str:
    """Compute the arithmetic answer for a captcha question string."""
    if "+" in question:
        a, b = question.split("+")
        return str(int(a.strip()) + int(b.strip()))
    a, b = question.split("-")
    return str(int(a.strip()) - int(b.strip()))


def _make_request(headers: dict | None = None, client: tuple | None = ("1.2.3.4", 123)) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/x",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("test", 80),
        "client": client,
        "scheme": "http",
    }
    return Request(scope)


def _mock_user(id=1, username="testuser", is_active=True, is_superuser=False):
    user = MagicMock()
    user.id = id
    user.username = username
    user.is_active = is_active
    user.is_superuser = is_superuser
    return user


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


class TestRedisFailureBehavior:
    """Test that security functions behave correctly when Redis is unavailable

    Security-critical functions (token blacklist, captcha) use fail-closed strategy:
    return the safe/restrictive value when Redis is down.
    Availability functions (login attempts, token version) use fail-open strategy:
    return permissive defaults when Redis is down.
    """

    @pytest.mark.asyncio
    async def test_is_token_blacklisted_fail_closed(self):
        """Token blacklist should return True (reject) when Redis is unavailable (fail-closed)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await is_token_blacklisted("some-jti")
            assert result is True

    @pytest.mark.asyncio
    async def test_get_token_version_fail_open(self):
        """Token version should return 0 when Redis is unavailable (fail-open)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await get_token_version(1)
            assert result == 0

    @pytest.mark.asyncio
    async def test_increment_token_version_fail_open(self):
        """Token version increment should return 0 when Redis is unavailable (fail-open)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await increment_token_version(1)
            assert result == 0

    @pytest.mark.asyncio
    async def test_check_login_attempts_fail_open(self):
        """Login attempt check should return False (not locked) when Redis is unavailable (fail-open)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await check_login_attempts("testuser")
            assert result is False

    @pytest.mark.asyncio
    async def test_check_captcha_required_fail_open(self):
        """Captcha check should return False (not required) when Redis is unavailable (fail-open)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await check_captcha_required("testuser")
            assert result is False

    @pytest.mark.asyncio
    async def test_record_failed_login_fail_open(self):
        """Recording failed login should not raise when Redis is unavailable (fail-open)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            # Should not raise
            await record_failed_login("testuser")

    @pytest.mark.asyncio
    async def test_reset_login_attempts_fail_open(self):
        """Resetting login attempts should not raise when Redis is unavailable (fail-open)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            # Should not raise
            await reset_login_attempts("testuser")

    @pytest.mark.asyncio
    async def test_verify_captcha_fail_closed(self):
        """Captcha verification should return False when Redis is unavailable (fail-closed)"""
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis connection error")):
            result = await verify_captcha("some-id", "42")
            assert result is False


class TestRedisNormalOperation:
    """Test security functions with mock Redis working normally"""

    @pytest.mark.asyncio
    async def test_token_blacklist_flow(self, mock_redis_patch):
        """Test adding and checking token blacklist"""
        # Token not blacklisted initially
        result = await is_token_blacklisted("test-jti")
        assert result is False

        # Add to blacklist
        from datetime import datetime, timedelta

        from app.core.security import add_token_to_blacklist
        exp = datetime.now(UTC) + timedelta(hours=1)
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


class TestGetClientIp:
    """Test client IP extraction respecting proxy headers"""

    def test_x_real_ip_takes_priority(self):
        request = _make_request(headers={"x-real-ip": " 10.0.0.1 "})
        assert get_client_ip(request) == "10.0.0.1"

    def test_x_forwarded_for_first_value(self):
        request = _make_request(headers={"x-forwarded-for": "1.1.1.1, 2.2.2.2"})
        assert get_client_ip(request) == "1.1.1.1"

    def test_fallback_to_client_host(self):
        request = _make_request(headers={}, client=("9.9.9.9", 123))
        assert get_client_ip(request) == "9.9.9.9"

    def test_request_none_returns_none(self):
        assert get_client_ip(None) is None

    def test_no_client_returns_none(self):
        request = _make_request(headers={}, client=None)
        assert get_client_ip(request) is None


class TestPasswordHashing:
    """Test password hashing and verification"""

    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("SecurePass123")
        assert hashed != "SecurePass123"
        assert verify_password("SecurePass123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("SecurePass123")
        assert verify_password("WrongPass456", hashed) is False

    def test_hash_is_salted(self):
        h1 = hash_password("SecurePass123")
        h2 = hash_password("SecurePass123")
        assert h1 != h2


class TestGenerateCaptcha:
    """Test arithmetic captcha generation"""

    @pytest.mark.asyncio
    async def test_generate_returns_id_and_question(self, mock_redis_patch):
        captcha_id, question = await generate_captcha()
        assert captcha_id
        assert "+" in question or "-" in question

    @pytest.mark.asyncio
    async def test_generate_redis_unavailable_raises(self):
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis down")):
            with pytest.raises(Exception):
                await generate_captcha()


class TestVerifyCaptchaNormal:
    """Test captcha verification with working Redis"""

    @pytest.mark.asyncio
    async def test_verify_correct_answer(self, mock_redis_patch):
        captcha_id, question = await generate_captcha()
        assert await verify_captcha(captcha_id, _solve_question(question)) is True

    @pytest.mark.asyncio
    async def test_verify_one_time_use(self, mock_redis_patch):
        captcha_id, question = await generate_captcha()
        answer = _solve_question(question)
        assert await verify_captcha(captcha_id, answer) is True
        # Second attempt with same id should fail (already consumed)
        assert await verify_captcha(captcha_id, answer) is False

    @pytest.mark.asyncio
    async def test_verify_unknown_id_returns_false(self, mock_redis_patch):
        assert await verify_captcha("nonexistent-id", "42") is False

    @pytest.mark.asyncio
    async def test_verify_non_numeric_answer(self, mock_redis_patch):
        captcha_id, _ = await generate_captcha()
        # Store a numeric answer, then submit a non-numeric answer
        assert await verify_captcha(captcha_id, "not-a-number") is False


class TestAddTokenToBlacklist:
    """Test token blacklist TTL handling"""

    @pytest.mark.asyncio
    async def test_expired_token_not_blacklisted(self, mock_redis_patch):
        # exp in the past (ttl <= 0) -> skip setex
        exp = datetime.now(UTC) - timedelta(hours=1)
        await add_token_to_blacklist("expired-jti", exp)
        assert await is_token_blacklisted("expired-jti") is False

    @pytest.mark.asyncio
    async def test_blacklist_redis_unavailable_no_raise(self):
        # Redis unavailable -> skip blacklisting silently (fail-open, never raises)
        with patch("app.core.security.get_redis_client", side_effect=Exception("Redis down")):
            await add_token_to_blacklist("jti", datetime.now(UTC) + timedelta(hours=1))


class TestCreateTokens:
    """Test JWT access/refresh token creation"""

    @pytest.mark.asyncio
    async def test_access_token_with_expires_delta(self, mock_redis_patch):
        token = await create_access_token_async(
            {"sub": "testuser"}, expires_delta=timedelta(minutes=5)
        )
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"
        assert payload["jti"]
        assert "ver" not in payload  # no user_id -> no ver

    @pytest.mark.asyncio
    async def test_access_token_includes_version(self, mock_redis_patch):
        token = await create_access_token_async({"sub": "testuser"}, user_id=1)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["ver"] == 0

    @pytest.mark.asyncio
    async def test_refresh_token_type(self, mock_redis_patch):
        token = await create_refresh_token_async({"sub": "testuser"}, user_id=1)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["type"] == "refresh"
        assert payload["ver"] == 0


class TestAuthenticateUser:
    """Test direct user authentication"""

    @pytest.mark.asyncio
    async def test_success(self, mock_async_session):
        user = _mock_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_async_session.execute.return_value = result

        with patch("app.core.security.verify_password", return_value=True):
            assert await authenticate_user(mock_async_session, "testuser", "pw") is user

    @pytest.mark.asyncio
    async def test_user_not_found(self, mock_async_session):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = result
        assert await authenticate_user(mock_async_session, "ghost", "pw") is None

    @pytest.mark.asyncio
    async def test_wrong_password(self, mock_async_session):
        user = _mock_user()
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_async_session.execute.return_value = result

        with patch("app.core.security.verify_password", return_value=False):
            assert await authenticate_user(mock_async_session, "testuser", "bad") is None


class TestGetCurrentUser:
    """Test JWT validation dependency"""

    def _mock_db_with_user(self, mock_async_session, user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_async_session.execute.return_value = result
        return mock_async_session

    @pytest.mark.asyncio
    async def test_valid_token(self, mock_redis_patch, mock_async_session):
        user = _mock_user()
        db = self._mock_db_with_user(mock_async_session, user)
        token = await create_access_token_async({"sub": "testuser"}, user_id=1)
        assert await get_current_user(db=db, token=token) is user

    @pytest.mark.asyncio
    async def test_invalid_token(self, mock_redis_patch, mock_async_session):
        with pytest.raises(HTTPException) as e:
            await get_current_user(db=mock_async_session, token="not.a.jwt")
        assert e.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_username(self, mock_redis_patch, mock_async_session):
        token = jwt.encode({"jti": "x", "type": "access"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        with pytest.raises(HTTPException) as e:
            await get_current_user(db=mock_async_session, token=token)
        assert e.value.status_code == 401

    @pytest.mark.asyncio
    async def test_blacklisted_token(self, mock_redis_patch, mock_async_session):
        user = _mock_user()
        db = self._mock_db_with_user(mock_async_session, user)
        token = await create_access_token_async({"sub": "testuser"}, user_id=1)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        await add_token_to_blacklist(payload["jti"], datetime.now(UTC) + timedelta(hours=1))
        with pytest.raises(HTTPException) as e:
            await get_current_user(db=db, token=token)
        assert e.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found(self, mock_redis_patch, mock_async_session):
        db = self._mock_db_with_user(mock_async_session, None)
        token = await create_access_token_async({"sub": "testuser"}, user_id=1)
        with pytest.raises(HTTPException) as e:
            await get_current_user(db=db, token=token)
        assert e.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user(self, mock_redis_patch, mock_async_session):
        user = _mock_user(is_active=False)
        db = self._mock_db_with_user(mock_async_session, user)
        token = await create_access_token_async({"sub": "testuser"}, user_id=1)
        with pytest.raises(HTTPException) as e:
            await get_current_user(db=db, token=token)
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_token_version_mismatch(self, mock_redis_patch, mock_async_session):
        user = _mock_user()
        db = self._mock_db_with_user(mock_async_session, user)
        # Token issued with ver=99 while current version is 0
        token = jwt.encode(
            {"sub": "testuser", "jti": "x", "type": "access", "ver": 99,
             "exp": datetime.now(UTC) + timedelta(minutes=5)},
            settings.SECRET_KEY, algorithm=settings.ALGORITHM,
        )
        with pytest.raises(HTTPException) as e:
            await get_current_user(db=db, token=token)
        assert e.value.status_code == 401

    @pytest.mark.asyncio
    async def test_legacy_token_without_ver_accepted(self, mock_redis_patch, mock_async_session):
        user = _mock_user()
        db = self._mock_db_with_user(mock_async_session, user)
        token = jwt.encode(
            {"sub": "testuser", "jti": "x", "type": "access",
             "exp": datetime.now(UTC) + timedelta(minutes=5)},
            settings.SECRET_KEY, algorithm=settings.ALGORITHM,
        )
        assert await get_current_user(db=db, token=token) is user


class TestGetCurrentActiveSuperuser:
    """Test superuser dependency"""

    @pytest.mark.asyncio
    async def test_non_superuser_denied(self):
        with pytest.raises(HTTPException) as e:
            await get_current_active_superuser(current_user=_mock_user(is_superuser=False))
        assert e.value.status_code == 403

    @pytest.mark.asyncio
    async def test_superuser_allowed(self):
        user = _mock_user(is_superuser=True)
        assert await get_current_active_superuser(current_user=user) is user


class TestLoginLockoutThreshold:
    """Test lockout threshold with hot-reloadable config (via Redis cache)"""

    @pytest.mark.asyncio
    async def test_locks_after_threshold(self, mock_redis_patch):
        # Configure max_login_attempts=2 and lockout_duration=15 via Redis cache
        mock_redis_patch._data["sys_config:max_login_attempts"] = "2"
        mock_redis_patch._data["sys_config:lockout_duration_minutes"] = "15"

        await record_failed_login("t")
        assert await check_login_attempts("t") is False

        await record_failed_login("t")
        assert await check_login_attempts("t") is True

    @pytest.mark.asyncio
    async def test_captcha_required_after_threshold(self, mock_redis_patch):
        mock_redis_patch._data["sys_config:captcha_threshold"] = "2"
        # Directly seed 2 failed attempts
        await record_failed_login("u")
        await record_failed_login("u")
        assert await check_captcha_required("u") is True

    @pytest.mark.asyncio
    async def test_captcha_not_required_below_threshold(self, mock_redis_patch):
        mock_redis_patch._data["sys_config:captcha_threshold"] = "5"
        await record_failed_login("v")
        assert await check_captcha_required("v") is False
