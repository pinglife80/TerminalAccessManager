"""
Comprehensive test suite for authentication endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.main import app
from app.core.database import Base, get_db
from app.core.security import hash_password
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
    from sqlalchemy import select
    
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
    from sqlalchemy import select
    
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
        """Test user registration"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "securepass123"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert "id" in data
        assert "hashed_password" not in data
    
    def test_register_duplicate_username(self, client: TestClient, test_user):
        """Test registration with duplicate username fails"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "testuser",
                "email": "different@example.com",
                "password": "securepass123"
            }
        )
        
        assert response.status_code == 400
        assert "Username already registered" in response.json()["detail"]
    
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
        """Test token refresh"""
        # Login to get tokens
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "testuser",
                "password": "testpassword123"
            }
        )
        
        refresh_token = login_response.json()["refresh_token"]
        
        # Refresh token
        response = client.post(
            "/api/v1/auth/refresh",
            params={"refresh_token": refresh_token}
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


class TestHealthAndRoot:
    """Test basic application endpoints"""
    
    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "TerminalAccessManager" in data["message"]
        assert "version" in data
    
    def test_health_check(self, client: TestClient):
        """Test health check endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
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
