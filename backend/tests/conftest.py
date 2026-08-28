"""Pytest configuration and fixtures"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment variables BEFORE importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-characters-long-for-testing"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-at-least-32-characters-long-for-testing"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["DB_PASSWORD"] = "test_password"

# Resolve VERSION from the repo root (single source of truth), matching the
# runtime behaviour where docker-compose injects VERSION into the environment.
# config.py's _load_version() checks env first, so this avoids the file-path
# fallback (which points at backend/VERSION, not the repo root VERSION file).
_VERSION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "VERSION",
)
if os.path.exists(_VERSION_FILE):
    with open(_VERSION_FILE) as _f:
        os.environ.setdefault("VERSION", _f.read().strip() or "test")
else:
    os.environ.setdefault("VERSION", "test")


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

    async def _ttl(key):
        # Return a positive TTL for existing keys, -2 for missing (Redis semantics)
        return 900 if key in redis_mock._data else -2

    def _pipeline(transaction=True):
        class _Pipe:
            def __init__(self, data):
                self._data = data
                self._ops = []

            def get(self, key):
                self._ops.append(("get", key))
                return None

            def delete(self, key):
                self._ops.append(("delete", key))
                return None

            async def execute(self):
                results = []
                for op, key in self._ops:
                    if op == "get":
                        results.append(self._data.get(key))
                    else:
                        results.append(self._data.pop(key, None))
                return results

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        return _Pipe(redis_mock._data)

    redis_mock.get = _get
    redis_mock.set = _set
    redis_mock.exists = _exists
    redis_mock.delete = _delete
    redis_mock.setex = _setex
    redis_mock.incr = _incr
    redis_mock.expire = _expire
    redis_mock.ttl = _ttl
    redis_mock.pipeline = _pipeline
    redis_mock.close = AsyncMock()

    return redis_mock


@pytest.fixture(autouse=True)
def mock_redis_patch(mock_redis):
    """Patch the get_redis_client function to return mock_redis."""
    with patch("app.core.security.get_redis_client", return_value=mock_redis):
        yield mock_redis


def make_mock_async_session():
    """Create a mock AsyncSession with the correct sync/async method split.

    SQLAlchemy's AsyncSession exposes a MIXED API: ``add``/``add_all``/
    ``expunge``/``expunge_all`` are synchronous, while ``execute``/``commit``/
    ``rollback``/``refresh``/``flush``/``close``/``delete``/``merge``/``get``
    are coroutines.

    Using a plain ``AsyncMock()`` for the session makes even the synchronous
    methods return coroutines, so ``self.db.add(obj)`` raises
    ``RuntimeWarning: coroutine ... was never awaited`` and ``assert_called_once``
    only proves "called", not that it was queued/committed correctly.

    This factory keeps sync methods as plain ``MagicMock`` (return None) and
    async methods as ``AsyncMock``, matching the real AsyncSession contract.
    """
    session = MagicMock()

    # Synchronous methods (not awaitable)
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.expunge = MagicMock()
    session.expunge_all = MagicMock()

    # Asynchronous methods (awaitable)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.close = AsyncMock()
    session.delete = AsyncMock()
    session.merge = AsyncMock()
    session.get = AsyncMock()

    return session


@pytest.fixture
def mock_async_session():
    """A mock AsyncSession with correct sync/async method split."""
    return make_mock_async_session()


# ---------------------------------------------------------------------------
# HTTP API endpoint integration test fixtures (6C)
#
# These fixtures exercise the FastAPI endpoint layer end-to-end against a real
# in-memory SQLite database, using a superuser current-user override so that
# every ``require_permission(...)`` guard passes without JWT/RBAC setup.
# ---------------------------------------------------------------------------

_ENDPOINT_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def api_engine():
    """Shared in-memory SQLite engine for endpoint tests (single connection)."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        _ENDPOINT_TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


@pytest.fixture
async def api_db(api_engine):
    """Fresh schema + a session for seeding data before each endpoint test."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    from app.core.database import Base

    async with api_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        api_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session

    async with api_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def api_client(api_db, api_engine):
    """Async HTTP client wired to the in-memory DB + superuser auth override."""
    from types import SimpleNamespace

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.main import app

    session_factory = async_sessionmaker(
        api_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def override_get_current_user():
        # Superuser short-circuits every require_permission(...) guard.
        return SimpleNamespace(
            id=1,
            username="testadmin",
            is_superuser=True,
            is_active=True,
        )

    overrides = app.dependency_overrides
    prev_get_db = overrides.get(get_db)
    prev_get_current_user = overrides.get(get_current_user)
    overrides[get_db] = override_get_db
    overrides[get_current_user] = override_get_current_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client
    finally:
        if prev_get_db is None:
            overrides.pop(get_db, None)
        else:
            overrides[get_db] = prev_get_db
        if prev_get_current_user is None:
            overrides.pop(get_current_user, None)
        else:
            overrides[get_current_user] = prev_get_current_user
