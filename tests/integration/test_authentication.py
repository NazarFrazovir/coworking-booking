"""Scenario 2 — registration, successful login and login errors."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from app.config import settings
from app.models.user import User, UserRole
from tests.helpers import API, TEST_PASSWORD, auth_headers

# ---------- registration ----------


def test_register_creates_regular_user_and_hashes_password(
    client: TestClient, db_session
) -> None:
    response = client.post(
        f"{API}/auth/register",
        json={
            "full_name": "Olena",
            "email": "Olena@Example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "user"
    assert body["email"] == "olena@example.com"  # normalized
    assert "password" not in body and "hashed_password" not in body

    stored = db_session.get(User, body["id"])
    assert stored.hashed_password.startswith("$2")  # bcrypt
    assert "password123" not in stored.hashed_password


def test_register_cannot_escalate_to_admin(client: TestClient) -> None:
    """Mass-assignment: a 'role' field in the payload must be ignored."""
    response = client.post(
        f"{API}/auth/register",
        json={
            "full_name": "Mallory",
            "email": "mallory@example.com",
            "password": "password123",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_register_duplicate_email_returns_409(client: TestClient, user: User) -> None:
    response = client.post(
        f"{API}/auth/register",
        json={"full_name": "Dup", "email": user.email.upper(), "password": "x" * 8},
    )
    assert response.status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        f"{API}/auth/register",
        json={"full_name": "Short", "email": "s@example.com", "password": "123"},
    )
    assert response.status_code == 422


# ---------- login (JSON API) ----------


def test_login_with_correct_credentials_returns_200_and_token(
    client: TestClient, user: User
) -> None:
    response = client.post(
        f"{API}/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "user"

    # the issued token actually grants access to a protected route
    me = client.get(
        f"{API}/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == user.email


def test_oauth2_form_login_used_by_swagger(client: TestClient, user: User) -> None:
    response = client.post(
        f"{API}/auth/token", data={"username": user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_wrong_password_returns_401(client: TestClient, user: User) -> None:
    response = client.post(
        f"{API}/auth/login", json={"email": user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_login_with_unknown_email_returns_same_401(client: TestClient) -> None:
    response = client.post(
        f"{API}/auth/login",
        json={"email": "nobody@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 401
    # Same message as for a wrong password → no user enumeration.
    assert response.json()["detail"] == "Incorrect email or password"


def test_blocked_user_cannot_login_and_old_token_stops_working(
    client: TestClient, make_user: Callable[..., User], db_session
) -> None:
    blocked = make_user(UserRole.USER)
    headers = auth_headers(blocked)  # token issued while still active
    blocked.is_active = False
    db_session.commit()

    login = client.post(
        f"{API}/auth/login", json={"email": blocked.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 401
    assert client.get(f"{API}/users/me", headers=headers).status_code == 401


# ---------- login (HTML pages, cookie-based) ----------


def test_html_login_sets_httponly_cookie_and_redirects_user_home(
    client: TestClient, user: User
) -> None:
    response = client.post(
        "/login", data={"email": user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/home"
    set_cookie = response.headers["set-cookie"]
    assert settings.auth_cookie_name in set_cookie
    assert "HttpOnly" in set_cookie

    home = client.get("/home")  # TestClient keeps the cookie
    assert home.status_code == 200
    assert user.full_name in home.text


def test_html_login_redirects_admin_to_admin_panel(
    client: TestClient, admin: User
) -> None:
    response = client.post(
        "/login", data={"email": admin.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 200


def test_html_login_with_wrong_password_shows_error(
    client: TestClient, user: User
) -> None:
    response = client.post("/login", data={"email": user.email, "password": "nope"})
    assert response.status_code == 401
    assert settings.auth_cookie_name not in response.headers.get("set-cookie", "")


def test_html_register_then_logout(client: TestClient) -> None:
    response = client.post(
        "/register",
        data={
            "full_name": "Taras",
            "email": "taras@example.com",
            "password": "pa55word!",
        },
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/home"
    assert client.get("/home").status_code == 200

    client.post("/logout")
    client.cookies.clear()
    assert client.get("/home").status_code == 302
