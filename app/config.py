"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings.

    Values are read from environment variables / .env file so that the
    same codebase can run against different databases in dev, CI and prod
    without any code changes.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CoWork Booking API"
    environment: str = "development"

    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/coworking_booking"
    )

    api_v1_prefix: str = "/api/v1"

    # --- Auth (lab #2) ---
    # The default is only good for local development; production must
    # override it via the JWT_SECRET_KEY environment variable.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Name of the HttpOnly cookie used by the server-rendered pages.
    auth_cookie_name: str = "access_token"
    cookie_secure: bool = False

    # Business rules for bookings.
    max_booking_hours: int = 12


settings = Settings()
