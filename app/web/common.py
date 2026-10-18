"""Shared helpers for server-rendered pages."""

from datetime import date, datetime, time
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models.user import User

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

LOCAL_TZ = ZoneInfo(settings.display_timezone)


def local_dt(value: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Show a stored (UTC) datetime in the coworking's local time zone."""
    if value is None:
        return ""
    if value.tzinfo is None:  # SQLite returns naive UTC values
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(LOCAL_TZ).strftime(fmt)


templates.env.filters["local"] = local_dt


def combine_local(day: date, at: time) -> datetime:
    """Date + time typed in a form are local time → aware datetime."""
    return datetime.combine(day, at, tzinfo=LOCAL_TZ)


def home_url(user: User) -> str:
    return "/admin" if user.is_admin else "/home"


def redirect(url: str, *, msg: str | None = None, err: str | None = None) -> Response:
    """302 redirect (Post/Redirect/Get) with an optional flash message."""
    params = {k: v for k, v in {"msg": msg, "err": err}.items() if v}
    if params:
        url = f"{url}?{urlencode(params)}"
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def forbidden(request: Request, user: User | None) -> Response:
    return templates.TemplateResponse(
        request, "forbidden.html", {"user": user}, status_code=403
    )


def flash(request: Request) -> dict[str, str | None]:
    return {
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
    }
