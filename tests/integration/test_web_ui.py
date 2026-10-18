"""Web UI (cookie-based) flows: booking via forms and the admin panel.

The same four access-control scenarios as for the API, but through the
HTML forms, so the UI can't become a back door around the API rules.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import create_access_token
from app.models.booking import Booking
from app.models.space import Space
from app.models.user import User, UserRole

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def login_as(client: TestClient, user: User) -> None:
    client.cookies.set(
        settings.auth_cookie_name, create_access_token(user.id, user.role)
    )


def book(client: TestClient, space: Space, start="10:00", end="11:00"):
    return client.post(
        "/home/bookings",
        data={"space_id": space.id, "day": TOMORROW, "start": start, "end": end},
    )


# ---------- user cabinet ----------


def test_user_books_and_cancels_via_form(
    client: TestClient, user: User, space: Space, db_session: Session
) -> None:
    login_as(client, user)
    r = book(client, space)
    assert r.status_code == 302
    assert "msg=" in r.headers["location"]

    booking = db_session.query(Booking).one()
    assert booking.user_id == user.id

    page = client.get("/home")
    assert page.status_code == 200
    assert space.name in page.text and "активне" in page.text

    r = client.post(f"/home/bookings/{booking.id}/cancel")
    assert r.status_code == 302
    db_session.refresh(booking)
    assert booking.status == "cancelled"


def test_form_overlap_shows_error(client: TestClient, user: User, space: Space) -> None:
    login_as(client, user)
    book(client, space, "10:00", "12:00")
    r = book(client, space, "11:00", "13:00")
    assert r.status_code == 302
    assert "err=" in r.headers["location"]
    page = client.get(r.headers["location"])
    assert "Цей час уже зайнятий" in page.text


def test_form_time_is_local_kyiv_time(
    client: TestClient, user: User, space: Space, db_session: Session
) -> None:
    login_as(client, user)
    book(client, space, "10:00", "11:00")
    booking = db_session.query(Booking).one()
    # Kyiv is UTC+2 or UTC+3, so 10:00 local is 07:00 or 08:00 UTC
    assert booking.start_time.hour in (7, 8)
    assert "10:00" in client.get("/home").text


def test_user_cannot_cancel_foreign_booking_via_form(
    client: TestClient,
    user: User,
    other_user: User,
    space: Space,
    db_session: Session,
) -> None:
    login_as(client, other_user)
    book(client, space)
    booking = db_session.query(Booking).one()

    login_as(client, user)
    r = client.post(f"/home/bookings/{booking.id}/cancel")
    assert r.status_code == 403
    db_session.refresh(booking)
    assert booking.status == "confirmed"


def test_profile_update_requires_current_password(
    client: TestClient, user: User, db_session: Session
) -> None:
    login_as(client, user)
    before = user.hashed_password
    r = client.post(
        "/home/profile",
        data={
            "full_name": "Alice New",
            "current_password": "wrong",
            "new_password": "new-password-1",
        },
    )
    assert "err=" in r.headers["location"]
    db_session.refresh(user)
    assert user.hashed_password == before


def test_anonymous_form_post_redirects_to_login(
    client: TestClient, space: Space
) -> None:
    r = book(client, space)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


# ---------- admin panel ----------

ADMIN_FORM_ACTIONS = [
    (
        "/admin/spaces",
        {"name": "X", "location": "Y", "capacity": 2, "space_type": "desk"},
    ),
    ("/admin/spaces/{space_id}/toggle", {}),
    ("/admin/users/{other_id}/role", {"role": "admin"}),
    ("/admin/users/{other_id}/toggle-active", {}),
    ("/admin/bookings/1/cancel", {}),
]


@pytest.mark.parametrize(("url", "data"), ADMIN_FORM_ACTIONS)
def test_regular_user_gets_403_on_admin_forms(
    client: TestClient,
    user: User,
    other_user: User,
    space: Space,
    url: str,
    data: dict,
) -> None:
    login_as(client, user)
    r = client.post(url.format(space_id=space.id, other_id=other_user.id), data=data)
    assert r.status_code == 403


def test_admin_manages_everything_via_forms(
    client: TestClient,
    admin: User,
    user: User,
    db_session: Session,
) -> None:
    # admin adds a space
    login_as(client, admin)
    r = client.post(
        "/admin/spaces",
        data={
            "name": "Карпати",
            "location": "2 поверх",
            "capacity": 8,
            "space_type": "meeting",
        },
    )
    assert r.status_code == 302
    space = db_session.query(Space).one()

    # user books it
    login_as(client, user)
    book(client, space)
    booking = db_session.query(Booking).one()

    # admin sees and cancels it, then blocks and promotes the user
    login_as(client, admin)
    page = client.get("/admin")
    assert "Карпати" in page.text and user.email in page.text

    client.post(f"/admin/bookings/{booking.id}/cancel")
    client.post(f"/admin/users/{user.id}/toggle-active")
    client.post(f"/admin/users/{user.id}/role", data={"role": "admin"})
    db_session.refresh(booking)
    db_session.refresh(user)
    assert booking.status == "cancelled"
    assert user.is_active is False
    assert user.role == UserRole.ADMIN

    # hiding a space removes it from the user catalogue
    client.post(f"/admin/spaces/{space.id}/toggle")
    db_session.refresh(space)
    assert space.is_active is False


def test_admin_cannot_block_or_demote_self_via_form(
    client: TestClient, admin: User, db_session: Session
) -> None:
    login_as(client, admin)
    client.post(f"/admin/users/{admin.id}/toggle-active")
    client.post(f"/admin/users/{admin.id}/role", data={"role": "user"})
    db_session.refresh(admin)
    assert admin.is_active and admin.role == UserRole.ADMIN
