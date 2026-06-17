"""Pytest configuration and fixtures"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Set test environment variables BEFORE importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-for-testing"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-at-least-32-characters-long-for-testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["DB_PASSWORD"] = "test_password"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client that simulates Redis operations in memory."""
    redis_mock = AsyncMock()
    redis_mock._data = {}

    async def _get(key):
        return redis_mock._data.get(key)

    async def _set(key, value, ex=None, px=None, nx=False):
        if nx and key in redis_mock._data:
            return None
        redis_mock._data[key] = value
        return True

    async def _exists(key):
        return 1 if key in redis_mock._data else 0

    async def _delete(*keys):
        count = 0
        for key in keys:
            if key in redis_mock._data:
                del redis_mock._data[key]
                count += 1
        return count

    async def _setex(key, time, value):
        redis_mock._data[key] = value
        return True

    async def _incr(key):
        if key not in redis_mock._data:
            redis_mock._data[key] = "0"
        redis_mock._data[key] = str(int(redis_mock._data[key]) + 1)
        return int(redis_mock._data[key])

    async def _expire(key, time):
        return True

    async def _pipeline(transaction=True):
        pipe = AsyncMock()
        results = []

        async def _execute():
            return results

        pipe.execute = _execute
        pipe.get = lambda k: results.append(None) or None
        pipe.delete = lambda k: results.append(0) or None
        return pipe

    redis_mock.get = _get
    redis_mock.set = _set
    redis_mock.exists = _exists
    redis_mock.delete = _delete
    redis_mock.setex = _setex
    redis_mock.incr = _incr
    redis_mock.expire = _expire
    redis_mock.pipeline = _pipeline
    redis_mock.close = AsyncMock()

    return redis_mock


@pytest.fixture
def mock_redis_patch(mock_redis):
    """Patch the get_redis_client function to return mock_redis."""
    with patch("app.core.security.get_redis_client", return_value=mock_redis):
        yield mock_redis
