"""
Comprehensive unit tests for SangforService.

All HTTP calls are mocked so the tests do NOT require Docker, Redis, PostgreSQL,
or a real Sangfor AF firewall.

Methods under test:
- _sanitize_description / _make_description / is_tam_managed_entry (pure helpers)
- _get_verify_setting / _create_client
- _authenticate
- _request_with_retry / _request_with_backoff
- block_ip / unblock_ip
- _find_blacklist_entry / get_blocked_ips / keepalive
- test_connection
- get_cached_service / close
- _execute_block / _execute_unblock / enqueue_operation
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.sangfor_service import (
    FirewallOperationType,
    SangforService,
    _service_cache,
    _token_expiry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_service(base_url="https://fw.example.com", username="admin", password="secret",
                 verify_ssl=True, ca_bundle=""):
    return SangforService(
        base_url=base_url,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
        ca_bundle=ca_bundle,
    )


def make_response(status_code=200, json_data=None, text="", headers=None):
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers if headers is not None else {}
    resp.json = MagicMock(return_value=json_data if json_data is not None else {})
    resp.raise_for_status = MagicMock()
    resp.text = text
    return resp


def make_http_error(status_code, text=""):
    """Build a real httpx.HTTPStatusError with a response carrying status/text."""
    request = httpx.Request("GET", "https://fw.example.com/")
    response = httpx.Response(status_code, request=request)
    response._content = text.encode()
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_module_cache():
    _service_cache.clear()
    _token_expiry.clear()
    yield
    _service_cache.clear()
    _token_expiry.clear()


@pytest.fixture
def service():
    return make_service()


# ===========================================================================
# Pure helpers
# ===========================================================================

class TestSanitizeDescription:
    def test_removes_forbidden(self):
        assert SangforService._sanitize_description("a:b/c") == "abc"

    def test_keeps_allowed(self):
        assert SangforService._sanitize_description("TAM-lab-Auto-blocked") == "TAM-lab-Auto-blocked"

    def test_empty(self):
        assert SangforService._sanitize_description("") == ""


class TestMakeDescription:
    def test_full(self):
        assert SangforService._make_description("lab", "Auto-blocked") == "TAM-lab-Auto-blocked"

    def test_no_source(self):
        assert SangforService._make_description("", "reason") == "TAM-reason"

    def test_no_reason(self):
        assert SangforService._make_description("lab", "") == "TAM-lab"

    def test_both_empty(self):
        assert SangforService._make_description("", "") == "TAM"

    def test_forbidden_colon_removed(self):
        assert SangforService._make_description("lab", "rea:son") == "TAM-lab-reason"

    def test_forbidden_slash_removed(self):
        assert SangforService._make_description("lab/x", "r") == "TAM-labx-r"


class TestIsTamManagedEntry:
    def test_tam_prefix(self):
        assert SangforService.is_tam_managed_entry("TAM-lab-x") is True

    def test_non_tam(self):
        assert SangforService.is_tam_managed_entry("OTHER-x") is False

    def test_empty(self):
        assert SangforService.is_tam_managed_entry("") is False

    def test_none(self):
        assert SangforService.is_tam_managed_entry(None) is False


# ===========================================================================
# Client / verify settings
# ===========================================================================

class TestGetVerifySetting:
    def test_ca_bundle(self):
        assert make_service(ca_bundle="/ca.pem")._get_verify_setting() == "/ca.pem"

    def test_verify_disabled(self):
        assert make_service(verify_ssl=False)._get_verify_setting() is False

    def test_default_true(self):
        # No ca bundle, verify_ssl True, no settings.SANGFOR_CA_BUNDLE in test env
        assert make_service()._get_verify_setting() is True

    def test_settings_ca_bundle(self):
        svc = make_service()
        with patch("app.services.sangfor_service.settings.SANGFOR_CA_BUNDLE", "/settings.pem"):
            assert svc._get_verify_setting() == "/settings.pem"


class TestCreateClient:
    def test_defaults(self, service):
        with patch("httpx.AsyncClient") as mock_cls:
            service._create_client()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["timeout"] == 30.0
        assert kwargs["follow_redirects"] is True
        assert kwargs["limits"] is service._connection_pool_limits

    def test_kwarg_override(self, service):
        with patch("httpx.AsyncClient") as mock_cls:
            service._create_client(timeout=10.0, verify=False)
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["timeout"] == 10.0
        assert kwargs["verify"] is False

    def test_verify_ssl_disabled(self, service):
        service._verify_ssl = False
        with patch("httpx.AsyncClient") as mock_cls:
            service._create_client()
        assert mock_cls.call_args.kwargs["verify"] is False


# ===========================================================================
# Authenticate
# ===========================================================================

class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_success(self, service):
        session = MagicMock()
        session.post = AsyncMock(return_value=make_response(
            200, {"code": 0, "data": {"loginResult": {"token": "tok123"}}}
        ))
        session.cookies = MagicMock()
        service.session = session

        await service._authenticate()

        assert service.token == "tok123"
        session.cookies.set.assert_called_once_with("token", "tok123")

    @pytest.mark.asyncio
    async def test_recursive_guard(self, service):
        service._authenticating = True
        with pytest.raises(RuntimeError):
            await service._authenticate()

    @pytest.mark.asyncio
    async def test_redirect_raises(self, service):
        session = MagicMock()
        session.post = AsyncMock(return_value=make_response(
            302, headers={"location": "http://other"}
        ))
        session.cookies = MagicMock()
        service.session = session

        with pytest.raises(ConnectionError):
            await service._authenticate()

    @pytest.mark.asyncio
    async def test_nonzero_code_raises(self, service):
        session = MagicMock()
        session.post = AsyncMock(return_value=make_response(200, {"code": 1, "message": "bad"}))
        session.cookies = MagicMock()
        service.session = session

        with pytest.raises(ConnectionError):
            await service._authenticate()

    @pytest.mark.asyncio
    async def test_missing_token_raises(self, service):
        session = MagicMock()
        session.post = AsyncMock(return_value=make_response(200, {"code": 0, "data": {}}))
        session.cookies = MagicMock()
        service.session = session

        with pytest.raises(ValueError):
            await service._authenticate()

    @pytest.mark.asyncio
    async def test_connect_error(self, service):
        session = MagicMock()
        session.post = AsyncMock(side_effect=httpx.ConnectError("conn refused"))
        session.cookies = MagicMock()
        service.session = session

        with pytest.raises(ConnectionError, match="Cannot connect"):
            await service._authenticate()

    @pytest.mark.asyncio
    async def test_connect_timeout(self, service):
        session = MagicMock()
        session.post = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
        session.cookies = MagicMock()
        service.session = session

        with pytest.raises(ConnectionError, match="timeout"):
            await service._authenticate()

    @pytest.mark.asyncio
    async def test_too_many_redirects(self, service):
        session = MagicMock()
        session.post = AsyncMock(side_effect=httpx.TooManyRedirects("redirects"))
        session.cookies = MagicMock()
        service.session = session

        with pytest.raises(ConnectionError, match="redirects"):
            await service._authenticate()


# ===========================================================================
# Session management
# ===========================================================================

class TestGetSession:
    @pytest.mark.asyncio
    async def test_creates_session_when_none(self, service):
        service.session = None
        service.token = "tok"
        with patch.object(service, "_create_client", return_value="CLIENT"):
            session = await service._get_session()

        assert session == "CLIENT"
        assert service.session == "CLIENT"

    @pytest.mark.asyncio
    async def test_authenticates_when_no_token(self, service):
        service.session = "CLIENT"
        service.token = None
        with patch.object(service, "_authenticate", AsyncMock()) as auth:
            session = await service._get_session()

        assert session == "CLIENT"
        auth.assert_called_once()


# ===========================================================================
# Request retry / backoff
# ===========================================================================

class TestRequestWithRetry:
    @pytest.mark.asyncio
    async def test_no_401(self, service):
        session = MagicMock()
        session.request = AsyncMock(return_value=make_response(200))
        service.token = "tok"

        with patch.object(service, "_get_session", AsyncMock(return_value=session)):
            resp = await service._request_with_retry("GET", "http://x")

        assert resp.status_code == 200
        assert session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_401_reauth(self, service):
        session = MagicMock()
        session.request = AsyncMock(side_effect=[make_response(401), make_response(200)])
        service.token = "tok"

        with patch.object(service, "_get_session", AsyncMock(return_value=session)):
            resp = await service._request_with_retry("GET", "http://x")

        assert resp.status_code == 200
        assert session.request.call_count == 2
        assert service.token is None


class TestRequestWithBackoff:
    @pytest.mark.asyncio
    async def test_success_first_try(self, service):
        with patch.object(service, "_request_with_retry", AsyncMock(return_value=make_response(200))) as retry:
            resp = await service._request_with_backoff("GET", "http://x")

        assert resp.status_code == 200
        retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_transient_then_success(self, service):
        retry = AsyncMock(side_effect=[httpx.ConnectError("x"), make_response(200)])
        with patch.object(service, "_request_with_retry", retry), \
             patch("asyncio.sleep", AsyncMock()) as sleep:
            resp = await service._request_with_backoff("GET", "http://x")

        assert resp.status_code == 200
        assert retry.call_count == 2
        sleep.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_exhausted_raises(self, service):
        retry = AsyncMock(side_effect=httpx.ConnectError("x"))
        with patch.object(service, "_request_with_retry", retry), \
             patch("asyncio.sleep", AsyncMock()):
            with pytest.raises(httpx.ConnectError):
                await service._request_with_backoff("GET", "http://x")

        assert retry.call_count == 4  # max_retries=3 -> 4 attempts

    @pytest.mark.asyncio
    async def test_5xx_retries(self, service):
        retry = AsyncMock(side_effect=[make_http_error(500), make_response(200)])
        with patch.object(service, "_request_with_retry", retry), \
             patch("asyncio.sleep", AsyncMock()):
            resp = await service._request_with_backoff("GET", "http://x")

        assert resp.status_code == 200
        assert retry.call_count == 2

    @pytest.mark.asyncio
    async def test_4xx_no_retry(self, service):
        retry = AsyncMock(side_effect=make_http_error(400))
        with patch.object(service, "_request_with_retry", retry), \
             patch("asyncio.sleep", AsyncMock()) as sleep:
            with pytest.raises(httpx.HTTPStatusError):
                await service._request_with_backoff("GET", "http://x")

        assert retry.call_count == 1
        sleep.assert_not_called()


# ===========================================================================
# Find entry / get blocked / keepalive
# ===========================================================================

class TestFindBlacklistEntry:
    @pytest.mark.asyncio
    async def test_found(self, service):
        resp = make_response(200, {"code": 0, "data": {"items": [{"url": "1.1.1.1", "description": "TAM-x"}]}})
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=resp)):
            entry = await service._find_blacklist_entry("1.1.1.1")

        assert entry == {"url": "1.1.1.1", "description": "TAM-x"}

    @pytest.mark.asyncio
    async def test_not_found(self, service):
        resp = make_response(200, {"code": 0, "data": {"items": [{"url": "2.2.2.2"}]}})
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=resp)):
            entry = await service._find_blacklist_entry("1.1.1.1")

        assert entry is None

    @pytest.mark.asyncio
    async def test_nonzero_code(self, service):
        resp = make_response(200, {"code": 1})
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=resp)):
            assert await service._find_blacklist_entry("1.1.1.1") is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, service):
        with patch.object(service, "_request_with_backoff", AsyncMock(side_effect=Exception("boom"))):
            assert await service._find_blacklist_entry("1.1.1.1") is None


class TestGetBlockedIps:
    @pytest.mark.asyncio
    async def test_success(self, service):
        resp = make_response(200, {"code": 0, "data": {"items": [{"url": "1.1.1.1"}]}})
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=resp)):
            result = await service.get_blocked_ips()

        assert result["data"]["items"] == [{"url": "1.1.1.1"}]

    @pytest.mark.asyncio
    async def test_search_param(self, service):
        resp = make_response(200, {"code": 0, "data": {"items": []}})
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=resp)) as req:
            await service.get_blocked_ips(search="1.1")

        assert req.call_args.kwargs["params"]["_search"] == "1.1"

    @pytest.mark.asyncio
    async def test_non_dict_result(self, service):
        resp = make_response(200, json_data=["not", "a", "dict"])
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=resp)):
            result = await service.get_blocked_ips()

        assert result == {"code": -1, "data": {"items": []}}

    @pytest.mark.asyncio
    async def test_exception_raises(self, service):
        with patch.object(service, "_request_with_backoff", AsyncMock(side_effect=Exception("boom"))):
            with pytest.raises(Exception):
                await service.get_blocked_ips()

    @pytest.mark.asyncio
    async def test_nonzero_code(self, service):
        resp = make_response(200, {"code": 1, "message": "err"})
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=resp)):
            result = await service.get_blocked_ips()

        assert result["code"] == 1

    @pytest.mark.asyncio
    async def test_pagination_aggregates_all_pages(self, service):
        """列表超过 200 条时应翻页聚合，避免漏读第二页导致误判 missing。"""
        def _page(method, url, **kwargs):
            start = kwargs["params"].get("_start", 0)
            assert kwargs["params"]["_length"] == 200
            if start == 0:
                items = [{"url": f"10.0.0.{i}"} for i in range(200)]
                return make_response(200, {"code": 0, "data": {"totalItems": 256, "totalPages": 2, "items": items}})
            items = [{"url": f"10.0.1.{i}"} for i in range(56)]
            return make_response(200, {"code": 0, "data": {"totalItems": 256, "totalPages": 2, "items": items}})

        with patch.object(service, "_request_with_backoff", AsyncMock(side_effect=_page)) as req:
            result = await service.get_blocked_ips()

        assert len(result["data"]["items"]) == 256
        assert req.call_count == 2
        assert req.call_args_list[1].kwargs["params"]["_start"] == 200

    @pytest.mark.asyncio
    async def test_pagination_stops_on_short_page_without_total(self, service):
        """totalItems 缺失时靠短页(<200)判断最后一页，而不是依赖 totalItems。"""
        def _page(method, url, **kwargs):
            start = kwargs["params"].get("_start", 0)
            if start == 0:
                items = [{"url": f"10.0.0.{i}"} for i in range(200)]
                return make_response(200, {"code": 0, "data": {"items": items}})
            items = [{"url": "10.0.1.1"}]
            return make_response(200, {"code": 0, "data": {"items": items}})

        with patch.object(service, "_request_with_backoff", AsyncMock(side_effect=_page)) as req:
            result = await service.get_blocked_ips()

        assert len(result["data"]["items"]) == 201
        assert req.call_count == 2


class TestKeepalive:
    @pytest.mark.asyncio
    async def test_ok(self, service):
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=make_response(200, {"code": 0}))):
            assert await service.keepalive() is True

    @pytest.mark.asyncio
    async def test_nonzero_code(self, service):
        with patch.object(service, "_request_with_backoff", AsyncMock(return_value=make_response(200, {"code": 1}))):
            assert await service.keepalive() is False

    @pytest.mark.asyncio
    async def test_exception(self, service):
        with patch.object(service, "_request_with_backoff", AsyncMock(side_effect=Exception("boom"))):
            assert await service.keepalive() is False


# ===========================================================================
# Block / Unblock
# ===========================================================================

class TestBlockIp:
    @pytest.mark.asyncio
    async def test_idempotent_skip(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "TAM-lab"}
        )
        service._request_with_backoff = AsyncMock()

        result = await service.block_ip(["1.1.1.1"], source_tag="lab")

        assert result["code"] == 0
        assert result["data"]["skipped"] == ["1.1.1.1"]
        assert result["data"]["blocked"] == []
        service._request_with_backoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_tam_proceeds_to_block(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "OTHER"}
        )
        service._request_with_backoff = AsyncMock(return_value=make_response(200, {"code": 0}))

        result = await service.block_ip(["1.1.1.1"], source_tag="lab")

        assert result["data"]["blocked"] == ["1.1.1.1"]
        service._request_with_backoff.assert_called_once()

    @pytest.mark.asyncio
    async def test_success(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(return_value=make_response(200, {"code": 0}))

        result = await service.block_ip(["1.1.1.1"], source_tag="lab", reason="bad")

        assert result["code"] == 0
        assert result["data"]["blocked"] == ["1.1.1.1"]
        # Description should be embedded in the request body.
        body = service._request_with_backoff.call_args.kwargs["json"]
        assert body["description"] == "TAM-lab-bad"
        assert body["type"] == "BLACK"
        assert body["enable"] is True

    @pytest.mark.asyncio
    async def test_409_skip(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(return_value=make_response(409))

        result = await service.block_ip(["1.1.1.1"])

        assert result["data"]["skipped"] == ["1.1.1.1"]

    @pytest.mark.asyncio
    async def test_http_error_recorded(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        resp = make_response(400, text="bad request body")
        resp.raise_for_status = MagicMock(side_effect=make_http_error(400, "bad request body"))
        service._request_with_backoff = AsyncMock(return_value=resp)

        result = await service.block_ip(["1.1.1.1"])

        assert len(result["data"]["errors"]) == 1
        assert result["code"] == 1

    @pytest.mark.asyncio
    async def test_nonzero_code_error(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(
            return_value=make_response(200, {"code": 1, "message": "fail"})
        )

        result = await service.block_ip(["1.1.1.1"])

        assert result["data"]["errors"] == [{"ip": "1.1.1.1", "error": "fail"}]
        assert result["code"] == 1

    @pytest.mark.asyncio
    async def test_empty_list_returns_failure(self, service):
        result = await service.block_ip([])
        assert result["code"] == 1
        assert result["data"]["blocked"] == []


class TestUnblockIp:
    @pytest.mark.asyncio
    async def test_empty_ip_skip(self, service):
        result = await service.unblock_ip([{"srcIP": ""}])
        assert result["data"]["unblocked"] == []
        assert result["code"] == 1

    @pytest.mark.asyncio
    async def test_not_existing_skip(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock()

        result = await service.unblock_ip([{"srcIP": "1.1.1.1"}])

        assert result["data"]["skipped"] == ["1.1.1.1"]
        service._request_with_backoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_tam_skip(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "OTHER"}
        )
        service._request_with_backoff = AsyncMock()

        result = await service.unblock_ip([{"srcIP": "1.1.1.1"}])

        assert result["data"]["skipped"] == ["1.1.1.1"]
        service._request_with_backoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_success(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "TAM-lab"}
        )
        service._request_with_backoff = AsyncMock(return_value=make_response(200, {"code": 0}))

        result = await service.unblock_ip([{"srcIP": "1.1.1.1"}])

        assert result["data"]["unblocked"] == ["1.1.1.1"]
        assert result["code"] == 0

    @pytest.mark.asyncio
    async def test_nonzero_code_error(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "TAM-lab"}
        )
        service._request_with_backoff = AsyncMock(
            return_value=make_response(200, {"code": 1, "message": "fail"})
        )

        result = await service.unblock_ip([{"srcIP": "1.1.1.1"}])

        assert result["data"]["errors"] == [{"ip": "1.1.1.1", "error": "fail"}]

    @pytest.mark.asyncio
    async def test_exception_recorded(self, service):
        service._find_blacklist_entry = AsyncMock(side_effect=Exception("boom"))
        service._request_with_backoff = AsyncMock()

        result = await service.unblock_ip([{"srcIP": "1.1.1.1"}])

        assert result["data"]["errors"] == [{"ip": "1.1.1.1", "error": "boom"}]
        assert result["code"] == 1
        service._request_with_backoff.assert_not_called()


# ===========================================================================
# Test connection
# ===========================================================================

class TestConnection:
    def _client(self, resp=None, post=None):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = post if post is not None else AsyncMock(return_value=resp)
        return client

    @pytest.mark.asyncio
    async def test_success(self, service):
        resp = make_response(200, {"code": 0, "data": {"loginResult": {"token": "tok"}, "role": "admin"}})
        with patch.object(service, "_create_client", return_value=self._client(resp)):
            result = await service.test_connection()

        assert result["success"] is True
        assert result["details"]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_redirect(self, service):
        resp = make_response(302, headers={"location": "http://other"})
        with patch.object(service, "_create_client", return_value=self._client(resp)):
            result = await service.test_connection()

        assert result["success"] is False
        assert "redirect" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_nonzero_code(self, service):
        resp = make_response(200, {"code": 1, "message": "bad"})
        with patch.object(service, "_create_client", return_value=self._client(resp)):
            result = await service.test_connection()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_missing_token(self, service):
        resp = make_response(200, {"code": 0, "data": {}})
        with patch.object(service, "_create_client", return_value=self._client(resp)):
            result = await service.test_connection()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_connect_error(self, service):
        client = self._client(post=AsyncMock(side_effect=httpx.ConnectError("conn")))
        with patch.object(service, "_create_client", return_value=client):
            result = await service.test_connection()

        assert result["success"] is False
        assert "Cannot connect" in result["message"]

    @pytest.mark.asyncio
    async def test_connect_timeout(self, service):
        client = self._client(post=AsyncMock(side_effect=httpx.ConnectTimeout("timeout")))
        with patch.object(service, "_create_client", return_value=client):
            result = await service.test_connection()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_too_many_redirects(self, service):
        client = self._client(post=AsyncMock(side_effect=httpx.TooManyRedirects("redirects")))
        with patch.object(service, "_create_client", return_value=client):
            result = await service.test_connection()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_http_status_error(self, service):
        client = self._client(post=AsyncMock(side_effect=make_http_error(401)))
        with patch.object(service, "_create_client", return_value=client):
            result = await service.test_connection()

        assert result["success"] is False
        assert "HTTP 401" in result["message"]

    @pytest.mark.asyncio
    async def test_generic_exception(self, service):
        client = self._client(post=AsyncMock(side_effect=Exception("boom")))
        with patch.object(service, "_create_client", return_value=client):
            result = await service.test_connection()

        assert result["success"] is False


# ===========================================================================
# Cached service / close
# ===========================================================================

class TestGetCachedService:
    @pytest.mark.asyncio
    async def test_cache_hit_valid_token(self):
        svc = make_service()
        svc.token = "tok"
        _service_cache["https://fw.example.com"] = svc
        _token_expiry["https://fw.example.com"] = datetime.now() + timedelta(minutes=5)

        result = await SangforService.get_cached_service(base_url="https://fw.example.com")

        assert result is svc

    @pytest.mark.asyncio
    async def test_cache_hit_expired_keepalive(self):
        svc = make_service()
        svc.token = "tok"
        svc.keepalive = AsyncMock(return_value=True)
        _service_cache["https://fw.example.com"] = svc
        _token_expiry["https://fw.example.com"] = datetime.now() - timedelta(minutes=5)

        result = await SangforService.get_cached_service(base_url="https://fw.example.com")

        assert result is svc
        svc.keepalive.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_authenticates(self):
        with patch.object(SangforService, "_authenticate", AsyncMock()) as auth:
            svc = await SangforService.get_cached_service(
                base_url="https://fw.example.com", username="u", password="p"
            )

        auth.assert_called_once()
        assert _service_cache["https://fw.example.com"] is svc
        assert "https://fw.example.com" in _token_expiry

    @pytest.mark.asyncio
    async def test_cache_miss_auth_failure_not_cached(self):
        with patch.object(SangforService, "_authenticate", AsyncMock(side_effect=Exception("auth fail"))):
            with pytest.raises(Exception):
                await SangforService.get_cached_service(base_url="https://fw.example.com")

        assert "https://fw.example.com" not in _service_cache

    @pytest.mark.asyncio
    async def test_cache_hit_empty_token_creates_new(self):
        cached = make_service()  # token is None
        _service_cache["https://fw.example.com"] = cached
        _token_expiry["https://fw.example.com"] = datetime.now() + timedelta(minutes=5)

        with patch.object(SangforService, "_authenticate", AsyncMock()) as auth:
            result = await SangforService.get_cached_service(base_url="https://fw.example.com")

        assert result is not cached
        assert _service_cache["https://fw.example.com"] is result
        auth.assert_called_once()


class TestClose:
    @pytest.mark.asyncio
    async def test_close_with_session(self, service):
        service.session = MagicMock()
        service.session.aclose = AsyncMock()
        service.token = "tok"
        _service_cache["https://fw.example.com"] = service
        _token_expiry["https://fw.example.com"] = datetime.now()

        await service.close()

        assert service.session is None
        assert service.token is None
        assert "https://fw.example.com" not in _service_cache
        assert "https://fw.example.com" not in _token_expiry

    @pytest.mark.asyncio
    async def test_close_without_session(self, service):
        service.session = None
        service.base_url = "https://fw2.example.com"
        await service.close()  # must not raise


# ===========================================================================
# Execute block / unblock / enqueue
# ===========================================================================

class TestExecuteBlock:
    @pytest.mark.asyncio
    async def test_success(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(return_value=make_response(200, {"code": 0}))
        await service._execute_block("1.1.1.1", "lab", "reason")
        service._request_with_backoff.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_skip(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "TAM-x"}
        )
        service._request_with_backoff = AsyncMock()
        await service._execute_block("1.1.1.1", "lab", "reason")
        service._request_with_backoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_409_skip(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(return_value=make_response(409))
        await service._execute_block("1.1.1.1", "lab", "reason")
        service._request_with_backoff.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_after_failure(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(
            side_effect=[Exception("boom"), make_response(200, {"code": 0})]
        )
        with patch("asyncio.sleep", AsyncMock()) as sleep:
            await service._execute_block("1.1.1.1", "lab", "reason")

        assert service._request_with_backoff.call_count == 2
        sleep.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_retries_exhausted(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(side_effect=Exception("boom"))

        with patch("asyncio.sleep", AsyncMock()) as sleep:
            await service._execute_block("1.1.1.1", "lab", "reason")

        assert service._request_with_backoff.call_count == 3
        assert sleep.call_count == 2  # after attempt 0 and 1

    @pytest.mark.asyncio
    async def test_nonzero_code(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock(
            return_value=make_response(200, {"code": 1, "message": "fail"})
        )

        await service._execute_block("1.1.1.1", "lab", "reason")

        service._request_with_backoff.assert_called_once()


class TestExecuteUnblock:
    @pytest.mark.asyncio
    async def test_success(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "TAM-x"}
        )
        service._request_with_backoff = AsyncMock(return_value=make_response(200, {"code": 0}))
        await service._execute_unblock("1.1.1.1")
        service._request_with_backoff.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_existing_skip(self, service):
        service._find_blacklist_entry = AsyncMock(return_value=None)
        service._request_with_backoff = AsyncMock()
        await service._execute_unblock("1.1.1.1")
        service._request_with_backoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_tam_skip(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "OTHER"}
        )
        service._request_with_backoff = AsyncMock()
        await service._execute_unblock("1.1.1.1")
        service._request_with_backoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_retries_exhausted(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "TAM-x"}
        )
        service._request_with_backoff = AsyncMock(side_effect=Exception("boom"))

        with patch("asyncio.sleep", AsyncMock()) as sleep:
            await service._execute_unblock("1.1.1.1")

        assert service._request_with_backoff.call_count == 3
        assert sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_nonzero_code(self, service):
        service._find_blacklist_entry = AsyncMock(
            return_value={"url": "1.1.1.1", "description": "TAM-x"}
        )
        service._request_with_backoff = AsyncMock(
            return_value=make_response(200, {"code": 1, "message": "fail"})
        )

        await service._execute_unblock("1.1.1.1")

        service._request_with_backoff.assert_called_once()


class TestEnqueueOperation:
    def test_enqueue_starts_queue(self, service):
        service._queue_running = False
        with patch("asyncio.create_task") as create_task:
            service.enqueue_operation(FirewallOperationType.BLOCK, "1.1.1.1", "lab", "reason")

        assert service._queue_running is True
        create_task.assert_called_once()
        assert service._operation_queue.qsize() == 1


class TestProcessQueue:
    @pytest.mark.asyncio
    async def test_process_block_operation(self, service):
        service._queue_running = False
        service._operation_queue.put_nowait(
            (FirewallOperationType.BLOCK, "1.1.1.1", "lab", "reason")
        )

        async def _wait_for(coro, timeout):
            return await coro

        with patch.object(service, "_execute_block", AsyncMock()) as block, \
             patch.object(service, "_execute_unblock", AsyncMock()) as unblock, \
             patch("asyncio.wait_for", side_effect=_wait_for):
            await service._process_queue()

        block.assert_called_once_with("1.1.1.1", "lab", "reason")
        unblock.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_unblock_operation(self, service):
        service._queue_running = False
        service._operation_queue.put_nowait((FirewallOperationType.UNBLOCK, "1.1.1.1", "", ""))

        async def _wait_for(coro, timeout):
            return await coro

        with patch.object(service, "_execute_unblock", AsyncMock()) as unblock, \
             patch.object(service, "_execute_block", AsyncMock()) as block, \
             patch("asyncio.wait_for", side_effect=_wait_for):
            await service._process_queue()

        unblock.assert_called_once_with("1.1.1.1")
        block.assert_not_called()

    @pytest.mark.asyncio
    async def test_operation_exception_isolated(self, service):
        service._queue_running = False
        service._operation_queue.put_nowait((FirewallOperationType.BLOCK, "1.1.1.1", "lab", "reason"))

        async def _wait_for(coro, timeout):
            return await coro

        with patch.object(service, "_execute_block", AsyncMock(side_effect=Exception("boom"))), \
             patch("asyncio.wait_for", side_effect=_wait_for):
            await service._process_queue()  # must not raise

        assert service._operation_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_timeout_continues(self, service):
        service._queue_running = True
        calls = {"n": 0}

        async def _wait_for(coro, timeout):
            if calls["n"] == 0:
                calls["n"] += 1
                service._queue_running = False  # stop loop after first timeout
                raise asyncio.TimeoutError()
            return await coro

        with patch("asyncio.wait_for", side_effect=_wait_for):
            await service._process_queue()

        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_outer_exception_isolated(self, service):
        service._queue_running = True
        calls = {"n": 0}

        async def _wait_for(coro, timeout):
            if calls["n"] == 0:
                calls["n"] += 1
                service._queue_running = False
                raise RuntimeError("queue boom")
            return await coro

        with patch("asyncio.wait_for", side_effect=_wait_for):
            await service._process_queue()  # must not raise

        assert calls["n"] == 1