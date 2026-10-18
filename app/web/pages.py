"""Server-rendered auth pages: login, registration, logout.

Browsers can't attach an ``Authorization`` header to normal navigation, so
the pages store the same JWT in an HttpOnly cookie (not readable from JS →
protected from XSS token theft; SameSite=Lax → basic CSRF protection).
Unlike the JSON API (which answers 401), protected pages redirect an
anonymous visitor to /login with 302.
"""

import pydantic
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import get_current_user_optional
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import users as user_service
from app.services.errors import DomainError
from app.web.common import home_url, redirect, templates

router = APIRouter(include_in_schema=False)


def _login_response(user: User) -> Response:
    response = redirect(home_url(user))
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
    return redirect(home_url(user) if user else "/login")


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request, user: User | None = Depends(get_current_user_optional)
) -> Response:
    if user:
        return redirect(home_url(user))
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
    except DomainError:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Невірний email або пароль", "email": email},
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
        fields = {e["loc"][-1] for e in exc.errors()}
        messages = {
            "full_name": "ім'я має містити щонайменше 2 символи",
            "email": "некоректний email",
            "password": "пароль має містити щонайменше 8 символів",
        }
        error = "; ".join(messages.get(str(f), str(f)) for f in sorted(fields))
        return templates.TemplateResponse(
            request, "register.html", {"error": error, **form}, status_code=400
        )
    except DomainError as exc:
        error = (
            "Користувач з таким email вже існує"
            if exc.status_code == 409
            else exc.detail
        )
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": error, **form},
            status_code=exc.status_code,
        )
    return _login_response(user)


@router.post("/logout")
def logout() -> Response:
    response = redirect("/login")
    response.delete_cookie(settings.auth_cookie_name)
    return response
