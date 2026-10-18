"""Shared pytest fixtures.

By default tests run against an in-memory SQLite DB (fast, zero setup).
Set ``TEST_DATABASE_URL`` to run the very same suite against PostgreSQL:

    export TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost/coworking_test
    pytest

Every test gets a fresh schema, so tests are fully independent.
"""

import os
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register models on Base.metadata)
from app.core.security import hash_password
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.space import Space
from app.models.user import User, UserRole
from tests.helpers import TEST_PASSWORD

# bcrypt is intentionally slow; hash the shared test password only once.
_TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture(scope="session")
def engine() -> Engine:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        return create_engine(url, future=True)
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session, None, None]:
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, future=True)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    # follow_redirects=False so tests can assert on 302 responses.
    with TestClient(fastapi_app, follow_redirects=False) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def make_user(db_session: Session) -> Callable[..., User]:
    counter = {"n": 0}

    def _make(
        role: UserRole = UserRole.USER,
        email: str | None = None,
        is_active: bool = True,
    ) -> User:
        counter["n"] += 1
        user = User(
            full_name=f"Test User {counter['n']}",
            email=email or f"{role.value}{counter['n']}@example.com",
            hashed_password=_TEST_PASSWORD_HASH,
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture()
def user(make_user: Callable[..., User]) -> User:
    return make_user(UserRole.USER, email="alice@example.com")


@pytest.fixture()
def other_user(make_user: Callable[..., User]) -> User:
    return make_user(UserRole.USER, email="bob@example.com")


@pytest.fixture()
def admin(make_user: Callable[..., User]) -> User:
    return make_user(UserRole.ADMIN, email="admin@example.com")


@pytest.fixture()
def space(db_session: Session) -> Space:
    s = Space(name="Room A", location="Floor 1", capacity=6, space_type="meeting")
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s
