"""Admin panel (/admin): spaces, users and bookings management.

Every handler goes through ``_admin_or_response``: anonymous → 302 /login,
non-admin → 403 page. The role is read from the DB, never from the cookie.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user_optional
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.space import Space
from app.models.user import User, UserRole
from app.routers.admin import stats as admin_stats
from app.services import bookings as booking_service
from app.services.errors import DomainError
from app.web.common import flash, forbidden, redirect, templates
from app.web.user_pages import ua

router = APIRouter(prefix="/admin", include_in_schema=False)


def _admin_or_response(request: Request, user: User | None) -> Response | None:
    """None if the user is an admin, otherwise the response to return."""
    if user is None:
        return redirect("/login")
    if not user.is_admin:
        return forbidden(request, user)
    return None


@router.get("", response_class=HTMLResponse)
def admin_home(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if (denied := _admin_or_response(request, user)) is not None:
        return denied
    users = db.scalars(select(User).order_by(User.id)).all()
    spaces = db.scalars(select(Space).order_by(Space.id)).all()
    bookings = db.scalars(
        select(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.space))
        .order_by(Booking.start_time.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "home_admin.html",
        {
            "user": user,
            "stats": admin_stats(db),
            "users": users,
            "spaces": spaces,
            "bookings": bookings,
            "confirmed": BookingStatus.CONFIRMED,
            **flash(request),
        },
    )


# ---------- spaces ----------


@router.post("/spaces")
def create_space(
    request: Request,
    name: str = Form(...),
    location: str = Form(...),
    capacity: int = Form(...),
    space_type: str = Form(...),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if (denied := _admin_or_response(request, user)) is not None:
        return denied
    name, location, space_type = name.strip(), location.strip(), space_type.strip()
    if not name or not location or not space_type or not 1 <= capacity <= 500:
        return redirect("/admin", err="Перевірте поля простору")
    db.add(
        Space(name=name, location=location, capacity=capacity, space_type=space_type)
    )
    db.commit()
    return redirect("/admin", msg=f"Простір «{name}» додано")


@router.post("/spaces/{space_id}/toggle")
def toggle_space(
    request: Request,
    space_id: int,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if (denied := _admin_or_response(request, user)) is not None:
        return denied
    space = db.get(Space, space_id)
    if space is None:
        return redirect("/admin", err="Простір не знайдено")
    space.is_active = not space.is_active
    db.commit()
    state = "активовано" if space.is_active else "приховано з каталогу"
    return redirect("/admin", msg=f"Простір «{space.name}» {state}")


# ---------- users ----------


@router.post("/users/{user_id}/role")
def change_role(
    request: Request,
    user_id: int,
    role: UserRole = Form(...),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if (denied := _admin_or_response(request, user)) is not None:
        return denied
    target = db.get(User, user_id)
    if target is None:
        return redirect("/admin", err="Користувача не знайдено")
    if target.id == user.id:
        return redirect("/admin", err="Не можна змінити роль самому собі")
    target.role = role
    db.commit()
    return redirect("/admin", msg=f"{target.email}: роль змінено на {role.value}")


@router.post("/users/{user_id}/toggle-active")
def toggle_active(
    request: Request,
    user_id: int,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if (denied := _admin_or_response(request, user)) is not None:
        return denied
    target = db.get(User, user_id)
    if target is None:
        return redirect("/admin", err="Користувача не знайдено")
    if target.id == user.id:
        return redirect("/admin", err="Не можна заблокувати самого себе")
    target.is_active = not target.is_active
    db.commit()
    state = "розблоковано" if target.is_active else "заблоковано"
    return redirect("/admin", msg=f"{target.email} {state}")


# ---------- bookings ----------


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    request: Request,
    booking_id: int,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if (denied := _admin_or_response(request, user)) is not None:
        return denied
    booking = db.get(Booking, booking_id)
    if booking is None:
        return redirect("/admin", err="Бронювання не знайдено")
    try:
        booking_service.cancel_booking(db, booking)
    except DomainError as exc:
        return redirect("/admin", err=ua(exc.detail))
    return redirect("/admin", msg=f"Бронювання #{booking_id} скасовано")
