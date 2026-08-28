"""
Comprehensive test suite for authentication endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import User

# Create test database engine (SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def override_get_db():
    """Override database dependency for testing"""
    async with TestingSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Override the database dependency
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
async def db_session():
    """Create a fresh database session for each test"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client with test database"""
    return TestClient(app)


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user"""

    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpassword123"),
        is_active=True,
        is_superuser=False
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user"""

    user = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("Admin123"),
        is_active=True,
        is_superuser=True
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


class TestAuthEndpoints:
    """Test authentication endpoints"""

    def test_register_new_user(self, client: TestClient):
        """Test user registration - disabled by default (ALLOW_REGISTRATION=False)"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "Securepass123"
            }
        )

        # Registration is disabled by default, expect 403
        assert response.status_code == 403

    def test_register_duplicate_username(self, client: TestClient, test_user):
        """Test registration is disabled by default"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "different@example.com",
                "password": "Securepass123"
            }
        )

        # Registration is disabled by default, expect 403
        assert response.status_code == 403

    def test_login_success(self, client: TestClient, test_user):
        """Test successful login"""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient, test_user):
        """Test login with wrong password fails"""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )

        assert response.status_code == 401
        detail = response.json()["detail"]
        # Detail is now a structured object with message field
        if isinstance(detail, dict):
            assert "Invalid credentials" in detail.get("message", "")
        else:
            assert "Invalid credentials" in detail

    def test_login_nonexistent_user(self, client: TestClient):
        """Test login with non-existent user fails"""
        response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent",
                "password": "password123"
            }
        )

        assert response.status_code == 401

    def test_get_current_user(self, client: TestClient, test_user):
        """Test getting current user info"""
        # First login to get token
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )

        token = login_response.json()["access_token"]

        # Get current user
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"

    def test_get_current_user_invalid_token(self, client: TestClient):
        """Test getting current user with invalid token fails"""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalidtoken"}
        )

        assert response.status_code == 401

    def test_refresh_token(self, client: TestClient, test_user):
        """Test token refresh - refresh endpoint uses Body(embed=True)"""
        # Login to get tokens
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )

        refresh_token = login_response.json()["refresh_token"]

        # Refresh token - use JSON body with embed=True (refresh_token as key)
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_logout(self, client: TestClient, test_user):
        """Test logout endpoint"""
        # Login first
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )

        token = login_response.json()["access_token"]

        # Logout
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


def _solve_question(question: str) -> str:
    """Compute the arithmetic answer for a captcha question string."""
    if "+" in question:
        a, b = question.split("+")
        return str(int(a.strip()) + int(b.strip()))
    a, b = question.split("-")
    return str(int(a.strip()) - int(b.strip()))


class TestLoginSecurity:
    """Test account lockout and captcha security flows"""

    def _login(self, client, username="testuser", password="testpassword123", **params):
        return client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": password},
            params=params,
        )

    def test_login_account_locked(self, client, test_user, mock_redis_patch):
        mock_redis_patch._data["login_lock:testuser"] = "3"
        response = self._login(client)
        assert response.status_code == 423
        detail = response.json()["detail"]
        assert detail["locked"] is True
        assert detail["lock_remaining"] > 0

    def test_login_captcha_required_without_captcha(self, client, test_user, mock_redis_patch):
        mock_redis_patch._data["login_attempts:testuser"] = "3"
        response = self._login(client)
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["captcha_required"] is True

    def test_login_captcha_wrong_answer(self, client, test_user, mock_redis_patch):
        mock_redis_patch._data["login_attempts:testuser"] = "3"
        captcha = client.get("/api/v1/auth/captcha").json()
        response = self._login(
            client, captcha_id=captcha["captcha_id"], captcha="-999"
        )
        assert response.status_code == 400
        assert response.json()["detail"]["captcha_required"] is True

    def test_login_captcha_correct_answer(self, client, test_user, mock_redis_patch):
        mock_redis_patch._data["login_attempts:testuser"] = "3"
        captcha = client.get("/api/v1/auth/captcha").json()
        answer = _solve_question(captcha["question"])
        response = self._login(
            client, captcha_id=captcha["captcha_id"], captcha=answer
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_login_inactive_user(self, client, test_user, mock_redis_patch):
        # LocalProvider returns "Account is disabled" -> unified 401
        response = self._login(client, username="inactive_user", password="whatever123")
        assert response.status_code == 401


class TestRefreshEdgeCases:
    """Test refresh token validation and rotation"""

    def _login(self, client, username="testuser", password="testpassword123"):
        return client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": password},
        )

    def test_refresh_invalid_token(self, client):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
        assert response.status_code == 401

    def test_refresh_access_token_rejected(self, client, test_user):
        login = self._login(client).json()
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login["access_token"]}
        )
        assert response.status_code == 401

    def test_refresh_rotation_revokes_old_token(self, client, test_user):
        refresh_token = self._login(client).json()["refresh_token"]
        first = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert first.status_code == 200

        # Reusing the old (now blacklisted) refresh token must fail
        second = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert second.status_code == 401


class TestPasswordAndProfile:
    """Test password change (token invalidation) and profile update"""

    def _login(self, client, username="testuser", password="testpassword123"):
        return client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": password},
        )

    def test_change_password_invalidates_old_token(self, client, test_user, mock_redis_patch):
        access_token = self._login(client).json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # Change password
        response = client.put(
            "/api/v1/auth/me/password",
            headers=headers,
            json={"current_password": "testpassword123", "new_password": "NewSecure456"},
        )
        assert response.status_code == 200

        # Old token must now be rejected due to version increment
        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 401

        # Old password should fail, new password should succeed
        assert self._login(client).status_code == 401
        assert self._login(client, password="NewSecure456").status_code == 200

    def test_change_password_wrong_current(self, client, test_user):
        access_token = self._login(client).json()["access_token"]
        response = client.put(
            "/api/v1/auth/me/password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"current_password": "wrongpassword", "new_password": "NewSecure456"},
        )
        assert response.status_code == 400

    def test_update_profile_email(self, client, test_user):
        access_token = self._login(client).json()["access_token"]
        response = client.put(
            "/api/v1/auth/me/profile",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"email": "newmail@example.com"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == "newmail@example.com"


class TestHealthAndRoot:
    """Test basic application endpoints"""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint"""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        # PROJECT_NAME is "Terminal Access Manager" (with spaces)
        assert "Terminal Access Manager" in data["message"]
        assert "version" in data

    def test_health_check(self, client: TestClient):
        """Test health check endpoint - may return 503 if Redis/DB unavailable"""
        response = client.get("/health")

        # In test environment without Redis, health returns 503 which is expected
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "environment" in data

    def test_api_docs_available(self, client: TestClient):
        """Test that API docs are accessible"""
        response = client.get("/api/v1/docs")

        assert response.status_code == 200

    def test_openapi_schema(self, client: TestClient):
        """Test OpenAPI schema generation"""
        response = client.get("/api/v1/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
        assert "info" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
