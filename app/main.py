"""CoWork Booking API entrypoint."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import admin, auth, bookings, spaces, users
from app.services.errors import DomainError
from app.web import pages

app = FastAPI(title=settings.app_name)

app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(users.router, prefix=settings.api_v1_prefix)
app.include_router(spaces.router, prefix=settings.api_v1_prefix)
app.include_router(bookings.router, prefix=settings.api_v1_prefix)
app.include_router(admin.router, prefix=settings.api_v1_prefix)
app.include_router(pages.router)


@app.exception_handler(DomainError)
def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Map business-rule violations raised by services to HTTP responses."""
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
    )


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Liveness/readiness probe endpoint."""
    return {"status": "ok", "environment": settings.environment}
