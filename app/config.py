"""Application configuration.

Which environment runs is decided by the ``APP_ENV`` variable
(``sandbox`` | ``production``; ``test`` is used only by pytest). Settings
are then read, in order of priority, from:

1. real environment variables (what cloud hosting / CI provide);
2. the file ``.env.<APP_ENV>`` in the project root (``.env.sandbox`` /
   ``.env.production``) — never committed, see ``config/*.example``.

There are deliberately NO defaults for secrets (DB password, JWT key):
if one is missing the app refuses to start instead of silently running
with a well-known value. Validators below also stop dangerous
combinations, e.g. DEBUG in production or production pointing at the
sandbox database.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

Environment = Literal["sandbox", "production", "test"]

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Placeholders from the *.example files; using one of them in production
# means somebody forgot to set a real secret.
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "example", "secret")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file_encoding="utf-8")

    # ---------- environment ----------
    app_env: Environment
    debug: bool = False
    log_level: str = "INFO"
    # Swagger UI / OpenAPI schema. Off in production by default: no need to
    # publish the full map of the API to everybody.
    docs_enabled: bool = True

    app_name: str = "CoWork Booking"
    api_v1_prefix: str = "/api/v1"

    # ---------- database ----------
    # Either a full DATABASE_URL (cloud hosting usually gives one) or the
    # POSTGRES_* parts, which docker compose also uses to create the DB.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: SecretStr | None = None
    sql_echo: bool = False

    # ---------- auth ----------
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    auth_cookie_name: str = "access_token"
    cookie_secure: bool = False

    # ---------- domain ----------
    display_timezone: str = "Europe/Kyiv"
    max_booking_hours: int = 12

    # ----------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def database_url(self) -> str:
        return self.database_url_obj.render_as_string(hide_password=False)

    @property
    def database_url_obj(self) -> URL:
        if self.database_url_override:
            url = make_url(self.database_url_override)
            # Heroku/Render style "postgres://" → explicit SQLAlchemy driver.
            if url.drivername in ("postgres", "postgresql"):
                url = url.set(drivername="postgresql+psycopg2")
            return url
        return URL.create(
            "postgresql+psycopg2",
            username=self.postgres_user,
            password=(
                self.postgres_password.get_secret_value()
                if self.postgres_password
                else None
            ),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def safe_database_url(self) -> str:
        """For logs: same URL with the password masked."""
        return self.database_url_obj.render_as_string(hide_password=True)

    # ---------- validation ----------

    @model_validator(mode="after")
    def _check(self) -> Self:
        self._check_database_configured()
        self._check_database_isolation()
        if self.is_production:
            self._check_production_safety()
        return self

    def _check_database_configured(self) -> None:
        if self.database_url_override:
            return
        missing = [
            name
            for name, value in (
                ("POSTGRES_DB", self.postgres_db),
                ("POSTGRES_USER", self.postgres_user),
                ("POSTGRES_PASSWORD", self.postgres_password),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"Database is not configured for '{self.app_env}': set DATABASE_URL "
                f"or {', '.join(missing)} in .env.{self.app_env}"
            )

    def _check_database_isolation(self) -> None:
        """Make it impossible to point one environment at the other's DB."""
        db_name = (self.database_url_obj.database or "").lower()
        if self.app_env == "production" and any(
            mark in db_name for mark in ("sandbox", "test", "dev")
        ):
            raise ValueError(
                f"Production must not use a sandbox/test database ('{db_name}')"
            )
        if self.app_env == "sandbox" and "prod" in db_name:
            raise ValueError(
                f"Sandbox must not use the production database ('{db_name}')"
            )

    def _check_production_safety(self) -> None:
        if self.debug:
            raise ValueError("DEBUG must be false in production")
        secret = self.jwt_secret_key.get_secret_value()
        if len(secret) < 32 or any(m in secret.lower() for m in _PLACEHOLDER_MARKERS):
            raise ValueError(
                "JWT_SECRET_KEY in production must be a random value of at least "
                '32 characters: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )


class ConfigError(RuntimeError):
    """Invalid configuration. The message never contains the values."""


def _describe(exc: ValidationError) -> str:
    problems = []
    for err in exc.errors():
        msg = err["msg"].removeprefix("Value error, ")
        field = ".".join(str(part) for part in err["loc"]).upper()
        problems.append(f"{field}: {msg}" if field else msg)
    return "; ".join(problems)


def env_file_for(app_env: str) -> Path:
    return PROJECT_ROOT / f".env.{app_env}"


def load_settings(app_env: str | None = None) -> Settings:
    """Build settings for ``app_env`` (default: the APP_ENV variable)."""
    app_env = app_env or os.getenv("APP_ENV", "sandbox")
    if app_env not in ("sandbox", "production", "test"):
        raise ConfigError(
            f"Unknown APP_ENV={app_env!r}; expected 'sandbox' or 'production'"
        )
    # A missing file is fine: everything may come from real env variables.
    try:
        return Settings(_env_file=env_file_for(app_env), app_env=app_env)
    except ValidationError as exc:
        # Re-raise without the pydantic error, whose text includes the input
        # values — i.e. it could print passwords into logs.
        raise ConfigError(
            f"Invalid configuration for APP_ENV={app_env}: {_describe(exc)}"
        ) from None


@lru_cache
def get_settings() -> Settings:
    return load_settings()


settings = get_settings()
