"""Authentication / authorization dependencies.

All access-control decisions in the app go through this module, so the
rules live in one place instead of being scattered across endpoints:

* ``get_current_user``      — authentication (who are you?) → 401
* ``require_roles(...)``    — vertical access control (role) → 403
* ``ensure_owner_or_admin`` — horizontal access control (IDOR) → 403
"""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User, UserRole

# auto_error=False: we also accept the token from a cookie (HTML pages),
# so a missing Authorization header must not fail immediately.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/token", auto_error=False
)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _extract_token(request: Request, bearer_token: str | None) -> str | None:
    if bearer_token:
        return bearer_token
    return request.cookies.get(settings.auth_cookie_name)


def _user_from_token(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user_optional(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Current user or ``None`` — used by HTML pages that redirect instead."""
    return _user_from_token(_extract_token(request, bearer_token), db)


def get_current_user(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    """Current authenticated user, otherwise 401 Unauthorized."""
    if user is None:
        raise _UNAUTHORIZED
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """Dependency factory for vertical (role-based) access control."""
    allowed = {r.value for r in roles}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


require_admin = require_roles(UserRole.ADMIN)


def ensure_owner_or_admin(current_user: User, owner_id: int) -> None:
    """Horizontal access control: only the owner (or an admin) may proceed.

    Raises 403 rather than 404 on purpose — the lab's IDOR scenario expects
    403. (A stricter alternative is 404 to hide the resource's existence.)
    """
    if current_user.id != owner_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources",
        )
