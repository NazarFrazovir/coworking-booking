"""CoWork Booking API entrypoint."""

from fastapi import FastAPI

from app.config import settings
from app.routers import bookings, spaces, users

app = FastAPI(title=settings.app_name)

app.include_router(users.router, prefix=settings.api_v1_prefix)
app.include_router(spaces.router, prefix=settings.api_v1_prefix)
app.include_router(bookings.router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Liveness/readiness probe endpoint."""
    return {"status": "ok", "environment": settings.environment}
