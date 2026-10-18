"""Helpers shared by test modules (kept out of conftest so they can be imported)."""

from datetime import UTC, datetime, timedelta

from app.core.security import create_access_token
from app.models.user import User

API = "/api/v1"
TEST_PASSWORD = "correct-horse-42"


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def slot(hours_from_now: int, duration_h: int = 1) -> dict[str, str]:
    """A future [start, end) slot aligned to a whole hour, as JSON strings."""
    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    start = base + timedelta(days=1, hours=hours_from_now)
    end = start + timedelta(hours=duration_h)
    return {"start_time": start.isoformat(), "end_time": end.isoformat()}
