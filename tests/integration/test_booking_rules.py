"""MVP business logic: booking rules."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models.space import Space
from app.models.user import User
from tests.helpers import API, auth_headers, slot


def _book(client: TestClient, who: User, space_id: int, s: dict) -> tuple[int, dict]:
    r = client.post(
        f"{API}/bookings/", json={"space_id": space_id, **s}, headers=auth_headers(who)
    )
    return r.status_code, r.json()


def test_overlapping_booking_is_rejected(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    assert _book(client, user, space.id, slot(2, duration_h=2))[0] == 201
    # starts inside the existing [2h, 4h) interval
    assert _book(client, other_user, space.id, slot(3))[0] == 409


def test_adjacent_bookings_are_allowed(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    assert _book(client, user, space.id, slot(2))[0] == 201
    assert _book(client, other_user, space.id, slot(3))[0] == 201  # [3h,4h)


def test_cancelled_slot_can_be_booked_again(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    _, booking = _book(client, user, space.id, slot(2))
    client.post(f"{API}/bookings/{booking['id']}/cancel", headers=auth_headers(user))
    assert _book(client, other_user, space.id, slot(2))[0] == 201


def test_cannot_book_in_the_past(client: TestClient, user: User, space: Space) -> None:
    start = datetime.now(UTC) - timedelta(hours=3)
    s = {
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=1)).isoformat(),
    }
    assert _book(client, user, space.id, s)[0] == 422


def test_end_must_be_after_start(client: TestClient, user: User, space: Space) -> None:
    s = slot(2)
    s["start_time"], s["end_time"] = s["end_time"], s["start_time"]
    assert _book(client, user, space.id, s)[0] == 422


def test_too_long_booking_is_rejected(
    client: TestClient, user: User, space: Space
) -> None:
    assert _book(client, user, space.id, slot(1, duration_h=24))[0] == 422


def test_unknown_or_inactive_space_returns_404(
    client: TestClient, user: User, space: Space, db_session
) -> None:
    assert _book(client, user, 9999, slot(2))[0] == 404
    space.is_active = False
    db_session.commit()
    assert _book(client, user, space.id, slot(2))[0] == 404


def test_reschedule_checks_overlap_but_ignores_itself(
    client: TestClient, user: User, other_user: User, space: Space
) -> None:
    _, mine = _book(client, user, space.id, slot(2, duration_h=2))
    _book(client, other_user, space.id, slot(6))

    # shifting my own booking by 1h overlaps only with itself → OK
    r = client.patch(
        f"{API}/bookings/{mine['id']}",
        json=slot(3, duration_h=2),
        headers=auth_headers(user),
    )
    assert r.status_code == 200

    # moving onto someone else's slot → conflict
    r = client.patch(
        f"{API}/bookings/{mine['id']}", json=slot(6), headers=auth_headers(user)
    )
    assert r.status_code == 409


def test_availability_shows_busy_slots_without_personal_data(
    client: TestClient, user: User, space: Space
) -> None:
    s = slot(2)
    _book(client, user, space.id, s)
    day = s["start_time"][:10]
    r = client.get(f"{API}/spaces/{space.id}/availability", params={"day": day})
    assert r.status_code == 200
    slots = r.json()
    assert len(slots) == 1
    assert set(slots[0]) == {"start_time", "end_time"}  # no user_id leaked
