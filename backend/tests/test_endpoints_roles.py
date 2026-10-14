"""6C HTTP API endpoint layer — /api/v1/roles integration tests.

Exercises the RBAC CRUD endpoints against a real in-memory DB. A superuser
override makes every ``require_permission(...)`` guard pass so these tests
focus on route wiring, data constraints, and response contracts.
"""
import pytest

from app.models.role import Permission, Role, RolePermission, UserRole
from app.models.user import User


def _make_role(**overrides) -> Role:
    defaults = dict(name="custom_role", description="a custom role", is_default=False)
    defaults.update(overrides)
    return Role(**defaults)


def _make_permission(**overrides) -> Permission:
    defaults = dict(code="terminal:read", name="Read terminals", module="terminal")
    defaults.update(overrides)
    return Permission(**defaults)


def _make_user(**overrides) -> User:
    defaults = dict(username="someuser", email="u@example.com", hashed_password="h",
                    is_active=True, is_superuser=False, provider="local")
    defaults.update(overrides)
    return User(**defaults)


async def _seed(db, *objs) -> None:
    for o in objs:
        db.add(o)
    await db.commit()


class TestListPermissions:
    @pytest.mark.asyncio
    async def test_empty(self, api_db, api_client):
        resp = await api_client.get("/api/v1/roles/permissions")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_lists_permissions(self, api_db, api_client):
        await _seed(api_db, _make_permission(), _make_permission(
            code="role:read", name="Read roles", module="role"))
        resp = await api_client.get("/api/v1/roles/permissions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestListRoles:
    @pytest.mark.asyncio
    async def test_empty(self, api_db, api_client):
        resp = await api_client.get("/api/v1/roles/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_role_with_permissions_and_user_count(self, api_db, api_client):
        role = _make_role()
        perm = _make_permission()
        user = _make_user(username="alice")
        await _seed(api_db, role, perm, user)
        # Flush to obtain IDs before adding association rows.
        await api_db.flush()
        api_db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        api_db.add(UserRole(user_id=user.id, role_id=role.id))
        await api_db.commit()

        resp = await api_client.get("/api/v1/roles/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "custom_role"
        assert data[0]["permissions"] == ["terminal:read"]
        assert data[0]["user_count"] == 1


class TestCreateRole:
    @pytest.mark.asyncio
    async def test_create_role(self, api_db, api_client):
        resp = await api_client.post(
            "/api/v1/roles/",
            json={"name": "new_role", "description": "desc", "permission_ids": []},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "new_role"
        assert body["user_count"] == 0

    @pytest.mark.asyncio
    async def test_create_role_with_permissions(self, api_db, api_client):
        perm = _make_permission()
        await _seed(api_db, perm)
        await api_db.flush()
        resp = await api_client.post(
            "/api/v1/roles/",
            json={"name": "op", "description": "", "permission_ids": [perm.id]},
        )
        assert resp.status_code == 201
        assert resp.json()["permissions"] == ["terminal:read"]

    @pytest.mark.asyncio
    async def test_duplicate_name_rejected(self, api_db, api_client):
        await _seed(api_db, _make_role(name="dup"))
        resp = await api_client.post(
            "/api/v1/roles/",
            json={"name": "dup", "description": "", "permission_ids": []},
        )
        assert resp.status_code == 400


class TestGetRole:
    @pytest.mark.asyncio
    async def test_found(self, api_db, api_client):
        role = _make_role()
        await _seed(api_db, role)
        resp = await api_client.get(f"/api/v1/roles/{role.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "custom_role"

    @pytest.mark.asyncio
    async def test_not_found(self, api_db, api_client):
        resp = await api_client.get("/api/v1/roles/9999")
        assert resp.status_code == 404


class TestUpdateRole:
    @pytest.mark.asyncio
    async def test_update_description(self, api_db, api_client):
        role = _make_role()
        await _seed(api_db, role)
        resp = await api_client.put(
            f"/api/v1/roles/{role.id}",
            json={"description": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "updated"

    @pytest.mark.asyncio
    async def test_cannot_modify_superadmin(self, api_db, api_client):
        role = _make_role(name="superadmin")
        await _seed(api_db, role)
        resp = await api_client.put(
            f"/api/v1/roles/{role.id}",
            json={"description": "x"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_rename_builtin_role(self, api_db, api_client):
        role = _make_role(name="admin")
        await _seed(api_db, role)
        resp = await api_client.put(
            f"/api/v1/roles/{role.id}",
            json={"name": "renamed"},
        )
        assert resp.status_code == 400


class TestDeleteRole:
    @pytest.mark.asyncio
    async def test_delete_custom_role(self, api_db, api_client):
        role = _make_role()
        await _seed(api_db, role)
        resp = await api_client.delete(f"/api/v1/roles/{role.id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_cannot_delete_builtin(self, api_db, api_client):
        role = _make_role(name="auditor")
        await _seed(api_db, role)
        resp = await api_client.delete(f"/api/v1/roles/{role.id}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_delete_role_with_users(self, api_db, api_client):
        role = _make_role()
        user = _make_user()
        await _seed(api_db, role, user)
        await api_db.flush()
        api_db.add(UserRole(user_id=user.id, role_id=role.id))
        await api_db.commit()
        resp = await api_client.delete(f"/api/v1/roles/{role.id}")
        assert resp.status_code == 400


class TestAssignUserRoles:
    @pytest.mark.asyncio
    async def test_assign_role_to_user(self, api_db, api_client):
        user = _make_user()
        role = _make_role()
        await _seed(api_db, user, role)
        # First seeded user is id=1 in a fresh DB; use a second user so we are
        # not blocked by the "initial system admin" guard.
        user2 = _make_user(username="other")
        api_db.add(user2)
        await api_db.flush()

        resp = await api_client.put(
            f"/api/v1/roles/users/{user2.id}/roles",
            json={"role_id": role.id},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_cannot_modify_initial_admin(self, api_db, api_client):
        user = _make_user()  # id=1
        role = _make_role()
        await _seed(api_db, user, role)
        resp = await api_client.put(
            f"/api/v1/roles/users/{user.id}/roles",
            json={"role_id": role.id},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_role_not_found(self, api_db, api_client):
        user = _make_user(username="other2")
        await _seed(api_db, user)
        resp = await api_client.put(
            f"/api/v1/roles/users/{user.id}/roles",
            json={"role_id": 9999},
        )
        assert resp.status_code == 400


class TestGetRoleUsers:
    @pytest.mark.asyncio
    async def test_list_users(self, api_db, api_client):
        role = _make_role()
        user = _make_user(username="alice")
        await _seed(api_db, role, user)
        await api_db.flush()
        api_db.add(UserRole(user_id=user.id, role_id=role.id))
        await api_db.commit()

        resp = await api_client.get(f"/api/v1/roles/{role.id}/users")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_role_not_found(self, api_db, api_client):
        resp = await api_client.get("/api/v1/roles/9999/users")
        assert resp.status_code == 404