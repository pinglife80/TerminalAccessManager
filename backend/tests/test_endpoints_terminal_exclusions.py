"""HTTP API tests for the optional unblock flag on terminal exclusion rules."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import get_current_user
from app.main import app

BASE_URL = "/api/v1/terminal-exclusions"


def _payload(unblock_blocked: bool) -> dict:
    return {
        "ip_type": "single_ip",
        "ip_value": "10.0.0.9",
        "mac_type": None,
        "mac_value": None,
        "comments": "excluded printer",
        "unblock_blocked": unblock_blocked,
    }


def _restricted_user():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        username="ops",
        is_superuser=False,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_create_with_unblock_requires_blacklist_write(api_client):
    _restricted_user()
    with (
        patch(
            "app.core.security.get_user_permissions",
            AsyncMock(return_value={"compliance:write"}),
        ),
        patch(
            "app.api.v1.endpoints.terminal_exclusions.get_user_permissions",
            AsyncMock(return_value={"compliance:write"}),
        ),
    ):
        response = await api_client.post(f"{BASE_URL}/", json=_payload(True))

    assert response.status_code == 403
    assert "blacklist:write" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_without_unblock_does_not_require_blacklist_write(api_client):
    _restricted_user()
    with (
        patch(
            "app.core.security.get_user_permissions",
            AsyncMock(return_value={"compliance:write"}),
        ),
        patch(
            "app.api.v1.endpoints.terminal_exclusions.get_user_permissions",
            AsyncMock(return_value={"compliance:write"}),
        ),
    ):
        response = await api_client.post(f"{BASE_URL}/", json=_payload(False))

    assert response.status_code == 200
    assert response.json()["unblock"] is None


@pytest.mark.asyncio
async def test_toggle_accepts_unblock_body(api_client):
    created = await api_client.post(f"{BASE_URL}/", json=_payload(False))
    assert created.status_code == 200
    rule_id = created.json()["rule"]["id"]

    # 超管无需 blacklist:write；停用方向即使携带 unblock_blocked 也应安全返回。
    response = await api_client.post(
        f"{BASE_URL}/{rule_id}/toggle", json={"unblock_blocked": True}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["rule"]["is_active"] is False
    assert data["unblock"] is None
