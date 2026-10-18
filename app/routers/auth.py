"""Registration and login (JSON API)."""

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, Token, UserCreate, UserRead
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_for(user: User) -> Token:
    return Token(
        access_token=create_access_token(user.id, user.role),
        role=user.role,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Self-registration. Always creates a regular ``user``."""
    return user_service.register_user(
        db,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
    )


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    """JSON login: ``{"email": ..., "password": ...}`` → bearer token."""
    user = user_service.authenticate(db, payload.email, payload.password)
    return _token_for(user)


@router.post("/token", response_model=Token, include_in_schema=True)
def login_form(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    """OAuth2 password flow (form fields ``username``=email, ``password``).

    This is what the "Authorize" button in Swagger UI (/docs) calls.
    """
    user = user_service.authenticate(db, form.username, form.password)
    return _token_for(user)
