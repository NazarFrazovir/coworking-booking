"""Scenario 3 — vertical access control (roles).

A regular user must get 403 Forbidden on every admin-only endpoint,
while an admin gets through.
"""

import pytest
from fastapi.testclient import TestClient

from app.models.space import Space
from app.models.user import User
from tests.helpers import API, auth_headers

ADMIN_ONLY = [
    ("get", f"{API}/admin/stats", None),
    ("get", f"{API}/admin/users", None),
    ("get", f"{API}/admin/bookings", None),
    ("patch", f"{API}/admin/users/{{user_id}}/role", {"role": "admin"}),
    ("patch", f"{API}/admin/users/{{user_id}}/active", {"is_active": False}),
    (
        "post",
        f"{API}/spaces/",
        {"name": "X", "location": "Y", "capacity": 2, "space_type": "desk"},
    ),
    ("patch", f"{API}/spaces/{{space_id}}", {"name": "Hacked"}),
    ("delete", f"{API}/spaces/{{space_id}}", None),
]


@pytest.mark.parametrize(("method", "url", "body"), ADMIN_ONLY)
def test_regular_user_gets_403_on_admin_endpoints(
    client: TestClient,
    user: User,
    space: Space,
    method: str,
    url: str,
    body: dict | None,
) -> None:
    url = url.format(user_id=user.id, space_id=space.id)
    response = client.request(method, url, json=body, headers=auth_headers(user))
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


@pytest.mark.parametrize(("method", "url", "body"), ADMIN_ONLY[:3])
def test_admin_can_read_admin_endpoints(
    client: TestClient, admin: User, method: str, url: str, body: dict | None
) -> None:
    response = client.request(method, url, json=body, headers=auth_headers(admin))
    assert response.status_code == 200


def test_regular_user_gets_403_on_admin_html_page(
    client: TestClient, user: User
) -> None:
    client.cookies.set("access_token", auth_headers(user)["Authorization"][7:])
    response = client.get("/admin")
    assert response.status_code == 403


def test_admin_can_manage_spaces(client: TestClient, admin: User) -> None:
    headers = auth_headers(admin)
    created = client.post(
        f"{API}/spaces/",
        json={
            "name": "Desk 7",
            "location": "Open space",
            "capacity": 1,
            "space_type": "desk",
        },
        headers=headers,
    )
    assert created.status_code == 201
    space_id = created.json()["id"]

    assert (
        client.patch(
            f"{API}/spaces/{space_id}", json={"capacity": 2}, headers=headers
        ).json()["capacity"]
        == 2
    )

    assert client.delete(f"{API}/spaces/{space_id}", headers=headers).status_code == 204
    # soft-deleted space disappears from the public catalogue
    assert client.get(f"{API}/spaces/{space_id}").status_code == 404


def test_admin_promotes_user_and_new_role_applies_immediately(
    client: TestClient, admin: User, user: User
) -> None:
    user_headers = auth_headers(user)  # token issued while still "user"
    assert client.get(f"{API}/admin/stats", headers=user_headers).status_code == 403

    response = client.patch(
        f"{API}/admin/users/{user.id}/role",
        json={"role": "admin"},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200

    # role is read from the DB on every request, not from the token
    assert client.get(f"{API}/admin/stats", headers=user_headers).status_code == 200


def test_admin_cannot_demote_self(client: TestClient, admin: User) -> None:
    response = client.patch(
        f"{API}/admin/users/{admin.id}/role",
        json={"role": "user"},
        headers=auth_headers(admin),
    )
    assert response.status_code == 409


def test_forged_role_claim_in_token_is_not_trusted(
    client: TestClient, user: User
) -> None:
    """A valid token for a regular user that *claims* role=admin."""
    from app.core.security import create_access_token

    token = create_access_token(user.id, "admin")
    response = client.get(
        f"{API}/admin/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
