"""Error handling: what the user sees vs. what goes to the logs.

* 500 — the full traceback is written to the server log together with a
  short random error id. The client gets only that id: a friendly HTML
  page for browsers, ``{"detail": ..., "error_id": ...}`` for API clients.
  No file paths, SQL or stack frames ever leave the server.
  (With DEBUG=true — sandbox only — Starlette shows its debug traceback
  page instead, which is what a developer wants locally.)
* 404 — a styled page for browsers, the usual JSON for the API.
* Business-rule errors from services keep their JSON shape.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.errors import DomainError

logger = logging.getLogger("app.errors")


def wants_html(request: Request) -> bool:
    """Browser navigation sends Accept: text/html; API clients don't."""
    accept = request.headers.get("accept", "")
    return "text/html" in accept and not request.url.path.startswith("/api/")


def _render(request: Request, status_code: int, **context: object) -> Response:
    # Imported lazily to avoid a circular import (web → services → errors).
    from app.web.common import templates

    return templates.TemplateResponse(
        request,
        "error.html",
        {"user": None, "status_code": status_code, **context},
        status_code=status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    error_id = uuid.uuid4().hex[:8]
    logger.exception(
        "Unhandled error %s on %s %s", error_id, request.method, request.url.path
    )
    if wants_html(request):
        return _render(request, 500, error_id=error_id)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_id": error_id},
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code == 404 and wants_html(request):
        return _render(request, 404)
    return await http_exception_handler(request, exc)


async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Map business-rule violations raised by services to HTTP responses."""
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
