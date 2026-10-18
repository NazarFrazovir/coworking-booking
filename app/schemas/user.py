"""Pydantic schemas for the User resource and authentication."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserBase(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr


class UserCreate(UserBase):
    """Public registration payload.

    Intentionally has NO ``role`` field: anything extra the client sends
    (e.g. ``"role": "admin"``) is ignored, so self-registration can never
    escalate privileges (mass-assignment protection).
    """

    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    """Fields a user may change in their own profile."""

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: UserRole
    is_active: bool
    created_at: datetime | None = None


class RoleUpdate(BaseModel):
    role: UserRole


class ActiveUpdate(BaseModel):
    is_active: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
