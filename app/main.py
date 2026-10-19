"""CoWork Booking entrypoint.

Run in the environment you want:

    APP_ENV=sandbox    uvicorn app.main:app --reload
    APP_ENV=production uvicorn app.main:app --host 0.0.0.0 --port 8000

``create_app`` takes the settings explicitly, so tests can build an app
in any mode (e.g. production with DEBUG off) without touching env vars.
"""

import logging

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.routers import admin, auth, bookings, spaces, users
from app.web import admin_pages, pages, user_pages

logger = logging.getLogger("app")


def create_app(settings: Settings) -> FastAPI:
    configure_logging(settings)

    docs = settings.docs_enabled
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    prefix = settings.api_v1_prefix
    for router in (auth, users, spaces, bookings, admin):
        app.include_router(router.router, prefix=prefix)
    for router in (pages, user_pages, admin_pages):
        app.include_router(router.router)

    register_error_handlers(app)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        """Liveness probe. Shows which environment answered."""
        return {"status": "ok", "environment": settings.app_env}

    logger.info(
        "Starting %s: APP_ENV=%s DEBUG=%s DB=%s",
        settings.app_name,
        settings.app_env,
        settings.debug,
        settings.safe_database_url,
    )
    return app


app = create_app(get_settings())
