"""Management commands.

Admins are never created through the public API — only by someone with
server/DB access:

    python -m app.cli create-admin --email admin@example.com --name "Admin"

(password is prompted interactively, or taken from --password).
An existing user can be promoted with ``promote --email ...``.
"""

import argparse
import getpass
import sys

import pydantic

from app.database import SessionLocal
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
