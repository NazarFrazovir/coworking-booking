"""User registration and authentication logic."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.services.errors import AuthenticationError, ConflictError

# Used to make "unknown email" and "wrong password" take the same time,
# so response timing doesn't reveal which emails are registered.
_DUMMY_HASH = hash_password("timing-attack-dummy-password")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User).where(func.lower(User.email) == normalize_email(email))
    )


def register_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str,
    role: UserRole = UserRole.USER,
) -> User:
    if get_by_email(db, email) is not None:
        raise ConflictError("Email already registered")
    user = User(
        full_name=full_name.strip(),
        email=normalize_email(email),
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent registration with same email
        db.rollback()
        raise ConflictError("Email already registered") from exc
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    """Return the user for valid credentials, otherwise raise 401.

    The error message is deliberately the same for every failure reason.
    """
    user = get_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise AuthenticationError("Incorrect email or password")
    if not verify_password(password, user.hashed_password) or not user.is_active:
        raise AuthenticationError("Incorrect email or password")
    return user
