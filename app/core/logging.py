"""Logging setup driven by settings (verbose in sandbox, quieter in prod)."""

import logging

from app.config import Settings


def configure_logging(settings: Settings) -> None:
    level = "DEBUG" if settings.debug else settings.log_level.upper()
    # basicConfig is a no-op if handlers already exist (uvicorn, pytest), so
    # nobody else's handlers are removed; the level is applied either way.
    logging.basicConfig(
        format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    )
    logging.getLogger().setLevel(level)
    logging.getLogger("app").setLevel(level)
