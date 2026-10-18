"""Scenario 4 — horizontal access control (IDOR).

An authenticated user tries to read/modify another user's profile or
another user's booking by guessing its id → 403 Forbidden.
The owner and an admin are allowed.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.space import Space
from app.models.user import User
from tests.helpers import API, auth_headers, slot


def _create_booking(client: TestClient, owner: User, space: Space) -> int:
    response = client.post(
        f"{API}/bookings/",
        json={"space_id": space.id, **slot(2)},
        headers=auth_headers(owner),
    )
    assert response.status_code == 201
    return response.json()["id"]


# ---------- profiles ----------


def test_user_cannot_update_another_users_profile(
    client: TestClient, user: User, other_user: User, db_session: Session
) -> None:
    response = client.patch(
        f"{API}/users/{other_user.id}",
        json={"full_name": "Hacked by Alice"},
        headers=auth_headers(user),
    )
    assert response.status_code == 403
    db_session.refresh(other_user)
    assert other_user.full_name != "Hacked by Alice"


def test_user_cannot_change_another_users_password(
    client: TestClient, user: User, other_user: User, db_session: Session
) -> None:
    before = other_user.hashed_password
    response = client.patch(
        f"{API}/users/{other_user.id}",
        json={"password": "new-password-123"},
        headers=auth_headers(user),
    )
    assert response.status_code == 403
    db_session.refresh(other_user)
    assert other_user.hashed_password == before


def test_user_cannot_read_another_users_profile(
    client: TestClient, user: User, other_user: User
) -> None:
    response = client.get(f"{API}/users/{other_user.id}", headers=auth_headers(user))
    assert response.status_code == 403


def test_user_can_update_own_profile(client: TestClient, user: User) -> None:
    response = client.patch(
        f"{API}/users/{user.id}",
        json={"full_name": "Alice Updated"},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Alice Updated"


def test_admin_can_update_any_profile(
    client: TestClient, admin: User, other_user: User
) -> None:
    response = client.patch(
        f"{API}/users/{other_user.id}",
        json={"full_name": "Fixed by admin"},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200


# ---------- bookings (domain entity) ----------


def test_user_cannot_view_foreign_booking(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    booking_id = _create_booking(client, other_user, space)
    response = client.get(f"{API}/bookings/{booking_id}", headers=auth_headers(user))
    assert response.status_code == 403


def test_user_cannot_cancel_foreign_booking(
    client: TestClient,
    user: User,
    other_user: User,
    space: Space,
    db_session: Session,
) -> None:
    booking_id = _create_booking(client, other_user, space)
    response = client.post(
        f"{API}/bookings/{booking_id}/cancel", headers=auth_headers(user)
    )
    assert response.status_code == 403
    assert db_session.get(Booking, booking_id).status == "confirmed"


def test_user_cannot_reschedule_foreign_booking(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    booking_id = _create_booking(client, other_user, space)
    response = client.patch(
        f"{API}/bookings/{booking_id}", json=slot(5), headers=auth_headers(user)
    )
    assert response.status_code == 403


def test_foreign_bookings_not_listed(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    _create_booking(client, other_user, space)
    response = client.get(f"{API}/bookings/", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json() == []


def test_owner_can_cancel_own_booking(
    client: TestClient, user: User, space: Space
) -> None:
    booking_id = _create_booking(client, user, space)
    response = client.post(
        f"{API}/bookings/{booking_id}/cancel", headers=auth_headers(user)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_admin_can_cancel_any_booking(
    client: TestClient, admin: User, other_user: User, space: Space
) -> None:
    booking_id = _create_booking(client, other_user, space)
    response = client.post(
        f"{API}/bookings/{booking_id}/cancel", headers=auth_headers(admin)
    )
    assert response.status_code == 200


def test_user_id_in_body_is_ignored_when_booking(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    """Cannot create a booking on behalf of someone else."""
    response = client.post(
        f"{API}/bookings/",
        json={"space_id": space.id, "user_id": other_user.id, **slot(3)},
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    assert response.json()["user_id"] == user.id
