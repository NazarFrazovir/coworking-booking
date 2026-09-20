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


settings = Settings()
