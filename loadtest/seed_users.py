"""Prepare the SANDBOX database for load testing.

Creates N virtual users (loaduser0001@example.com … ) that Locust logs in
with, and makes sure there are bookable spaces. Refuses to run outside
sandbox: load-test data must never reach production.

    APP_ENV=sandbox python -m loadtest.seed_users --users 300

All users share one password hash (bcrypt is deliberately slow; hashing
300 passwords one by one would take a minute and is not what we test).
"""

import argparse
import sys

from sqlalchemy import func, select

from app.cli import DEMO_SPACES
from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.space import Space
from app.models.user import User

PASSWORD = "loadtest-pass-1"
EMAIL = "loaduser{:04d}@example.com"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=300)
    args = parser.parse_args(argv)

    if settings.app_env != "sandbox":
        print(f"Refusing: APP_ENV={settings.app_env}, sandbox only.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        existing_spaces = set(db.scalars(select(Space.name)))
        for name, location, capacity, kind in DEMO_SPACES:
            if name not in existing_spaces:
                db.add(Space(name=name, location=location, capacity=capacity,
                             space_type=kind))  # fmt: skip
        existing = set(
            db.scalars(select(User.email).where(User.email.like("loaduser%")))
        )
        shared_hash = hash_password(PASSWORD)
        added = 0
        for i in range(1, args.users + 1):
            email = EMAIL.format(i)
            if email not in existing:
                db.add(User(full_name=f"Load User {i}", email=email,
                            hashed_password=shared_hash))  # fmt: skip
                added += 1
        db.commit()
        spaces = db.scalar(select(func.count(Space.id)).where(Space.is_active))
    print(
        f"Load-test users added: {added} (total {args.users}); active spaces: {spaces}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
