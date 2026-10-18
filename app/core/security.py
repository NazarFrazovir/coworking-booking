"""Password hashing and JWT helpers.

Pure functions with no FastAPI / DB dependencies, so they are trivially
unit-testable and reusable from CLI scripts.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings

# bcrypt only looks at the first 72 bytes of the password.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash (salt is embedded in the result)."""
    pw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Constant-time check of ``password`` against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:_BCRYPT_MAX_BYTES],
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        # Malformed hash (e.g. legacy "hashed:..." rows from lab #1).
        return False


def create_access_token(
    subject: int | str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Issue a signed JWT.

    ``sub`` is the user id. ``role`` is included for clients (e.g. to pick
    which home page to show) but the server never trusts it for
    authorization — the role is always re-read from the database.
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate signature + expiry and return the payload.

    Raises ``jwt.InvalidTokenError`` (or a subclass) on any problem.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp"]},
    )
