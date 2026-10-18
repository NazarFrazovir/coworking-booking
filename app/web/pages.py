"""Server-rendered pages: login, registration and role-specific home pages.

Browsers can't attach an ``Authorization`` header to normal navigation, so
the pages store the same JWT in an HttpOnly cookie (not readable from JS →
protected from XSS token theft; SameSite=Lax → basic CSRF protection).
Unlike the JSON API (which answers 401), protected pages redirect an
anonymous visitor to /login with 302.
"""

from pathlib import Path

import pydantic
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user_optional
from app.core.security import create_access_token
from app.database import get_db
from app.models.booking import Booking
from app.models.space import Space
from app.models.user import User
from app.routers.admin import stats as admin_stats
from app.schemas.user import UserCreate
from app.services import users as user_service
from app.services.errors import DomainError

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

router = APIRouter(include_in_schema=False)


def _home_url(user: User) -> str:
    return "/admin" if user.is_admin else "/home"


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def _login_response(user: User) -> RedirectResponse:
    response = _redirect(_home_url(user))
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_access_token(user.id, user.role),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return response


@router.get("/")
def index(user: User | None = Depends(get_current_user_optional)) -> Response:
    return _redirect(_home_url(user) if user else "/login")


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request, user: User | None = Depends(get_current_user_optional)
) -> Response:
    if user:
        return _redirect(_home_url(user))
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    try:
        user = user_service.authenticate(db, email, password)
    except DomainError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": exc.detail, "email": email},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return _login_response(user)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> Response:
    return templates.TemplateResponse(request, "register.html", {})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    form = {"full_name": full_name, "email": email}
    try:
        data = UserCreate(full_name=full_name, email=email, password=password)
        user = user_service.register_user(
            db, full_name=data.full_name, email=data.email, password=data.password
        )
    except pydantic.ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        )
        return templates.TemplateResponse(
            request, "register.html", {"error": errors, **form}, status_code=400
        )
    except DomainError as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": exc.detail, **form},
            status_code=exc.status_code,
        )
    return _login_response(user)


@router.post("/logout")
def logout() -> Response:
    response = _redirect("/login")
    response.delete_cookie(settings.auth_cookie_name)
    return response


@router.get("/home", response_class=HTMLResponse)
def user_home(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if user is None:
        return _redirect("/login")
    if user.is_admin:
        return _redirect("/admin")
    bookings = db.scalars(
        select(Booking).where(Booking.user_id == user.id).order_by(Booking.start_time)
    ).all()
    spaces = db.scalars(select(Space).where(Space.is_active.is_(True))).all()
    return templates.TemplateResponse(
        request,
        "home_user.html",
        {"user": user, "bookings": bookings, "spaces": spaces},
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_home(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if user is None:
        return _redirect("/login")
    if not user.is_admin:
        return templates.TemplateResponse(
            request, "forbidden.html", {"user": user}, status_code=403
        )
    users = db.scalars(select(User).order_by(User.id)).all()
    return templates.TemplateResponse(
        request,
        "home_admin.html",
        {"user": user, "stats": admin_stats(db), "users": users},
    )
