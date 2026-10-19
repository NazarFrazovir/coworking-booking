"""Management commands.

Admins are never created through the public API — only by someone with
server/DB access:

    python -m app.cli create-admin --email admin@example.com --name "Admin"

(password is prompted interactively, or taken from --password).
An existing user can be promoted with ``promote --email ...``.

Every command works on the database of the current APP_ENV:

    APP_ENV=sandbox python -m app.cli seed-demo     # demo data, sandbox only
    APP_ENV=production python -m app.cli show-config
"""

import argparse
import getpass
import sys

import pydantic
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.space import Space
from app.models.user import UserRole
from app.schemas.user import UserCreate
from app.services import users as user_service
from app.services.errors import DomainError


def _create_admin(args: argparse.Namespace) -> int:
    # Same validation rules as public registration (email format, lengths),
    # so an admin can always log in through the API afterwards.
    try:
        UserCreate(
            full_name=args.name, email=args.email, password=args.password or "x" * 8
        )
    except pydantic.ValidationError as exc:
        print(exc, file=sys.stderr)
        return 1
    password = args.password or getpass.getpass("Password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        try:
            user = user_service.register_user(
                db,
                full_name=args.name,
                email=args.email,
                password=password,
                role=UserRole.ADMIN,
            )
        except DomainError as exc:
            print(exc.detail, file=sys.stderr)
            return 1
        print(f"Admin created: id={user.id} email={user.email}")
    return 0


def _promote(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        user = user_service.get_by_email(db, args.email)
        if user is None:
            print("User not found", file=sys.stderr)
            return 1
        user.role = UserRole.ADMIN
        db.commit()
        print(f"User {user.email} is now admin")
    return 0


DEMO_SPACES = [
    ("Переговорна Карпати", "2 поверх", 8, "meeting"),
    ("Зала Говерла", "1 поверх, зала з проєктором", 30, "hall"),
    ("Кабінет Петрос", "3 поверх", 4, "office"),
    ("Робоче місце 12", "Open space", 1, "desk"),
]
DEMO_USERS = [
    ("Олена Коваль", "olena@example.com"),
    ("Тарас Мельник", "taras@example.com"),
]
DEMO_PASSWORD = "sandbox-demo-1"


def _seed_demo(_args: argparse.Namespace) -> int:
    """Fill the sandbox with demo spaces and users. Refuses in production."""
    if settings.app_env != "sandbox":
        print(
            f"seed-demo runs only with APP_ENV=sandbox (now: {settings.app_env}). "
            "Demo data must never reach production.",
            file=sys.stderr,
        )
        return 1
    with SessionLocal() as db:
        existing = set(db.scalars(select(Space.name)))
        added = 0
        for name, location, capacity, kind in DEMO_SPACES:
            if name not in existing:
                db.add(
                    Space(
                        name=name, location=location, capacity=capacity, space_type=kind
                    )
                )
                added += 1
        db.commit()
        users = 0
        for full_name, email in DEMO_USERS:
            if user_service.get_by_email(db, email) is None:
                user_service.register_user(
                    db, full_name=full_name, email=email, password=DEMO_PASSWORD
                )
                users += 1
    print(f"Sandbox seeded: {added} spaces, {users} users (password: {DEMO_PASSWORD})")
    return 0


def _show_config(_args: argparse.Namespace) -> int:
    """Print the effective configuration with secrets masked."""
    print(f"APP_ENV       = {settings.app_env}")
    print(f"DEBUG         = {settings.debug}")
    print(f"LOG_LEVEL     = {settings.log_level}")
    print(f"DOCS_ENABLED  = {settings.docs_enabled}")
    print(f"DATABASE      = {settings.safe_database_url}")
    print(f"COOKIE_SECURE = {settings.cookie_secure}")
    print("JWT_SECRET_KEY= ********** (set)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="create an administrator")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="Administrator")
    create.add_argument("--password", help="omit to be prompted")
    create.set_defaults(func=_create_admin)

    promote = sub.add_parser("promote", help="make an existing user admin")
    promote.add_argument("--email", required=True)
    promote.set_defaults(func=_promote)

    seed = sub.add_parser("seed-demo", help="demo data for the sandbox")
    seed.set_defaults(func=_seed_demo)

    show = sub.add_parser("show-config", help="print effective config (masked)")
    show.set_defaults(func=_show_config)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
