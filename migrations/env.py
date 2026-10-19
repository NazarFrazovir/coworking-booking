"""Alembic environment.

The target database is chosen by APP_ENV exactly like for the app itself:

    APP_ENV=sandbox    alembic upgrade head
    APP_ENV=production alembic upgrade head

The URL is passed to SQLAlchemy as an object (not via alembic.ini), so a
password containing '%' or other special characters is handled safely and
is never written to any file.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.config import settings
from app.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

print(f"[alembic] APP_ENV={settings.app_env} → {settings.safe_database_url}")


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url_obj,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.database_url_obj, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
