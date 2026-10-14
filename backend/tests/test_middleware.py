"""Tests for middleware — rate limiting, request ID, logging, error handlers"""
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.middleware.error_handler import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware


def _make_request(path="/api/v1/x", headers=None, client=("1.2.3.4", 123)):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("test", 80),
        "client": client,
        "scheme": "http",
    }
    return Request(scope)


async def _call_next_ok(request):
    return Response("ok", status_code=200)


# ---------------------------------------------------------------- Request ID


class TestRequestIDMiddleware:
    def _mw(self):
        return RequestIDMiddleware(MagicMock())

    @pytest.mark.asyncio
    async def test_reuses_client_supplied_id(self):
        mw = self._mw()
        request = _make_request(headers={"x-request-id": "trace-123"})
        response = await mw.dispatch(request, _call_next_ok)
        assert response.headers["X-Request-ID"] == "trace-123"

    @pytest.mark.asyncio
    async def test_generates_id_when_absent(self):
        mw = self._mw()
        request = _make_request(headers={})
        response = await mw.dispatch(request, _call_next_ok)
        assert response.headers["X-Request-ID"]
        assert len(response.headers["X-Request-ID"]) == 12


# ------------------------------------------------------------- Logging


class TestRequestLoggingMiddleware:
    def _mw(self):
        return RequestLoggingMiddleware(MagicMock())

    @pytest.mark.asyncio
    async def test_excluded_path_skips_timing_header(self):
        mw = self._mw()
        request = _make_request(path="/health")
        response = await mw.dispatch(request, _call_next_ok)
        assert "X-Response-Time" not in response.headers

    @pytest.mark.asyncio
    async def test_sets_timing_header(self):
        mw = self._mw()
        request = _make_request(path="/api/v1/x", headers={"x-forwarded-for": "5.5.5.5, 6.6.6.6"})
        response = await mw.dispatch(request, _call_next_ok)
        assert "X-Response-Time" in response.headers

    @pytest.mark.asyncio
    async def test_falls_back_to_client_host(self):
        mw = self._mw()
        request = _make_request(path="/api/v1/x", headers={}, client=("8.8.8.8", 123))
        response = await mw.dispatch(request, _call_next_ok)
        assert "X-Response-Time" in response.headers


# ------------------------------------------------------------- Error handlers


class TestErrorHandlers:
    @pytest.mark.asyncio
    async def test_http_exception_preserves_detail(self):
        exc = MagicMock()
        exc.status_code = 400
        exc.detail = {"message": "foo", "captcha_required": True}
        exc.headers = None
        resp = await http_exception_handler(_make_request(), exc)
        assert resp.status_code == 400
        assert json.loads(resp.body) == {"detail": {"message": "foo", "captcha_required": True}}

    @pytest.mark.asyncio
    async def test_validation_exception_returns_422(self):
        exc = MagicMock()
        exc.errors.return_value = [{"loc": ["body", "password"], "msg": "too short"}]
        resp = await validation_exception_handler(_make_request(), exc)
        assert resp.status_code == 422
        body = json.loads(resp.body)
        assert body["detail"][0]["msg"] == "too short"

    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_500_with_error_id(self):
        exc = RuntimeError("boom")
        resp = await unhandled_exception_handler(_make_request(), exc)
        assert resp.status_code == 500
        body = json.loads(resp.body)
        assert body["detail"]["message"] == "Internal server error"
        assert body["detail"]["error_id"]


# ------------------------------------------------------------- Rate limiting


class _FakePipe:
    def __init__(self, count):
        self.count = count

    def zremrangebyscore(self, *a, **k):
        return None

    def zadd(self, *a, **k):
        return None

    def zcard(self, *a, **k):
        return None

    def expire(self, *a, **k):
        return None

    async def execute(self):
        return [0, 0, self.count, 1]


class _FakeRateRedis:
    def __init__(self, count, oldest=None):
        self.count = count
        self.oldest = oldest

    def pipeline(self):
        return _FakePipe(self.count)

    async def zrange(self, *a, **k):
        return self.oldest or []


class TestRateLimitMiddleware:
    def _mw(self, count=1, oldest=None):
        mw = RateLimitMiddleware(MagicMock())
        mw._redis = _FakeRateRedis(count, oldest)
        return mw

    def test_get_client_id_forwarded(self):
        mw = self._mw()
        request = _make_request(headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2"})
        assert mw._get_client_id(request) == "1.1.1.1"

    def test_get_client_id_no_forwarded(self):
        mw = self._mw()
        request = _make_request(headers={}, client=("9.9.9.9", 123))
        assert mw._get_client_id(request) == "9.9.9.9"

    def test_get_client_id_no_client(self):
        mw = self._mw()
        request = _make_request(headers={}, client=None)
        assert mw._get_client_id(request) == "unknown"

    @pytest.mark.asyncio
    async def test_get_rate_limit_auth_path(self):
        mw = self._mw()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.services.config_service.get_config_value", AsyncMock(return_value=7))
            assert await mw._get_rate_limit("/api/v1/auth/login") == 7

    @pytest.mark.asyncio
    async def test_get_rate_limit_general_path(self):
        mw = self._mw()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.services.config_service.get_config_value", AsyncMock(return_value=120))
            assert await mw._get_rate_limit("/api/v1/terminals") == 120

    @pytest.mark.asyncio
    async def test_get_rate_limit_auth_exception_falls_back(self):
        mw = self._mw()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.services.config_service.get_config_value",
                AsyncMock(side_effect=Exception("down")),
            )
            assert await mw._get_rate_limit("/api/v1/auth/login") == settings.AUTH_RATE_LIMIT_PER_MINUTE

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed(self):
        mw = self._mw(count=1)
        assert await mw._check_rate_limit("1.2.3.4", "/api/v1/x", 5) == (True, 0)

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded_with_oldest(self):
        mw = self._mw(count=6, oldest=[("m", time.time() - 30)])
        allowed, retry_after = await mw._check_rate_limit("1.2.3.4", "/api/v1/x", 5)
        assert allowed is False
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded_without_oldest(self):
        mw = self._mw(count=6, oldest=[])
        assert await mw._check_rate_limit("1.2.3.4", "/api/v1/x", 5) == (False, 60)

    @pytest.mark.asyncio
    async def test_dispatch_skips_health(self):
        mw = self._mw(count=99)
        request = _make_request(path="/health")
        response = await mw.dispatch(request, _call_next_ok)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_skips_non_api(self):
        mw = self._mw(count=99)
        request = _make_request(path="/assets/main.js")
        response = await mw.dispatch(request, _call_next_ok)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_rate_limited_returns_429(self):
        mw = self._mw()
        mw._get_rate_limit = AsyncMock(return_value=5)
        mw._check_rate_limit = AsyncMock(return_value=(False, 30))
        request = _make_request(path="/api/v1/x")
        response = await mw.dispatch(request, _call_next_ok)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "30"

    @pytest.mark.asyncio
    async def test_dispatch_allowed(self):
        mw = self._mw()
        mw._get_rate_limit = AsyncMock(return_value=5)
        mw._check_rate_limit = AsyncMock(return_value=(True, 0))
        request = _make_request(path="/api/v1/x")
        response = await mw.dispatch(request, _call_next_ok)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_exception_fails_open(self):
        mw = self._mw()
        mw._get_rate_limit = AsyncMock(return_value=5)
        mw._check_rate_limit = AsyncMock(side_effect=Exception("redis down"))
        request = _make_request(path="/api/v1/x")
        response = await mw.dispatch(request, _call_next_ok)
        assert response.status_code == 200