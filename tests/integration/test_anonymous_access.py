"""Scenario 1 — anonymous access to protected routes.

JSON API → 401 Unauthorized (+ WWW-Authenticate header).
HTML pages → 302 redirect to /login.
"""

import pytest
from fastapi.testclient import TestClient

from tests.helpers import API

PROTECTED_API_ROUTES = [
    ("get", f"{API}/users/me"),
    ("patch", f"{API}/users/1"),
    ("get", f"{API}/bookings/"),
    ("post", f"{API}/bookings/"),
    ("get", f"{API}/bookings/1"),
    ("post", f"{API}/bookings/1/cancel"),
    ("post", f"{API}/spaces/"),
    ("delete", f"{API}/spaces/1"),
    ("get", f"{API}/admin/stats"),
    ("get", f"{API}/admin/users"),
]


@pytest.mark.parametrize(("method", "url"), PROTECTED_API_ROUTES)
def test_api_without_token_returns_401(
    client: TestClient, method: str, url: str
) -> None:
    response = client.request(method, url, json={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token",
    ["garbage", "a.b.c", "eyJhbGciOiJIUzI1NiJ9.e30.invalid"],
)
def test_api_with_invalid_token_returns_401(client: TestClient, token: str) -> None:
    response = client.get(
        f"{API}/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/home", "/admin", "/"])
def test_html_pages_redirect_anonymous_to_login(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_public_routes_stay_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.get(f"{API}/spaces/").status_code == 200
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200
