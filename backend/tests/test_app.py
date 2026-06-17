"""
Simple test to verify the FastAPI application starts correctly
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


def test_root_endpoint(client):
    """Test root endpoint returns welcome message"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Welcome to" in data["message"]


def test_health_check(client):
    """Test health check endpoint - may return 503 if Redis/DB unavailable in test env"""
    response = client.get("/health")
    # In test environment without Redis, health returns 503 which is expected
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "version" in data


class TestGlobalExceptionHandler:
    """Test global exception handler middleware"""

    def test_http_exception_preserves_detail(self, client):
        """HTTPException should preserve existing detail format (pass-through)"""
        # 404 is a standard HTTPException
        response = client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_validation_error_returns_422(self, client):
        """RequestValidationError should return 422 with standard format"""
        # Login without required fields triggers validation error
        response = client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_unhandled_exception_returns_500(self):
        """Unhandled exceptions should return 500 with error_id for tracing"""
        import asyncio
        from unittest.mock import MagicMock

        from fastapi import Request

        from app.middleware.error_handler import (
            unhandled_exception_handler,
        )

        # Test unhandled exception handler
        request_mock = MagicMock(spec=Request)
        request_mock.method = "GET"
        request_mock.url = MagicMock()
        request_mock.url.path = "/test"

        exc = RuntimeError("test unhandled error")
        response = asyncio.get_event_loop().run_until_complete(
            unhandled_exception_handler(request_mock, exc)
        )

        assert response.status_code == 500
        # response.body is bytes, decode to check JSON
        import json
        body = json.loads(response.body.decode())
        assert "detail" in body
        assert "message" in body["detail"]
        assert body["detail"]["message"] == "Internal server error"
        assert "error_id" in body["detail"]

    def test_http_exception_handler_passthrough(self):
        """HTTPException handler should pass through detail unchanged"""
        import asyncio
        from unittest.mock import MagicMock

        from fastapi import Request
        from starlette.exceptions import HTTPException as StarletteHTTPException

        from app.middleware.error_handler import http_exception_handler

        request_mock = MagicMock(spec=Request)

        # Test with structured detail
        exc = StarletteHTTPException(
            status_code=403,
            detail={"message": "Registration is disabled", "code": "REG_DISABLED"}
        )
        response = asyncio.get_event_loop().run_until_complete(
            http_exception_handler(request_mock, exc)
        )
        assert response.status_code == 403
        import json
        body = json.loads(response.body.decode())
        assert body["detail"]["message"] == "Registration is disabled"

        # Test with string detail
        exc2 = StarletteHTTPException(status_code=401, detail="Not authenticated")
        response2 = asyncio.get_event_loop().run_until_complete(
            http_exception_handler(request_mock, exc2)
        )
        assert response2.status_code == 401
        body2 = json.loads(response2.body.decode())
        assert body2["detail"] == "Not authenticated"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
