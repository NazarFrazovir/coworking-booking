"""User cabinet (/home): browse spaces, book, cancel, edit profile.

All business rules come from the same services the JSON API uses, and
access checks use the same helpers, so the web UI can't bypass them.
"""

from datetime import date, time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user_optional
from app.core.security import hash_password, verify_password
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.services import bookings as booking_service
from app.services.bookings import to_utc
from app.services.errors import DomainError
from app.web.common import (
    combine_local,
    flash,
    forbidden,
    local_now,
    parse_day,
    redirect,
    schedule_context,
    templates,
)

router = APIRouter(include_in_schema=False)

ERRORS_UA = {
    "This slot is already booked": "Цей час уже зайнятий",
    "Cannot book a slot in the past": "Не можна бронювати час у минулому",
    "end_time must be after start_time": "Кінець має бути пізніше за початок",
    "Space not found": "Простір не знайдено або він неактивний",
    "Booking is already cancelled": "Бронювання вже скасоване",
    "Past bookings cannot be changed": "Минулі бронювання змінювати не можна",
}


def ua(detail: str) -> str:
    if detail.startswith("A booking cannot be longer"):
        return "Бронювання не може тривати довше 12 годин"
    return ERRORS_UA.get(detail, detail)


def _greeting(hour: int) -> str:
    if 5 <= hour < 12:
        return "Доброго ранку"
    if 12 <= hour < 18:
        return "Добрий день"
    return "Добрий вечір"


@router.get("/home", response_class=HTMLResponse)
def user_home(
    request: Request,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if user is None:
        return redirect("/login")
    if user.is_admin:
        return redirect("/admin")
    day = parse_day(request.query_params.get("day"))
    now = local_now()
    bookings = db.scalars(
        select(Booking)
        .options(joinedload(Booking.space))
        .where(Booking.user_id == user.id)
        .order_by(Booking.start_time)
    ).all()
    upcoming = [
        b
        for b in bookings
        if b.status == BookingStatus.CONFIRMED and to_utc(b.end_time) > now
    ]
    history = [b for b in reversed(bookings) if b not in upcoming]
    return templates.TemplateResponse(
        request,
        "home_user.html",
        {
            "user": user,
            "first_name": user.full_name.split()[0],
            "greeting": _greeting(now.hour),
            "upcoming": upcoming,
            "history": history[:20],
            "next_booking": upcoming[0] if upcoming else None,
            "confirmed": BookingStatus.CONFIRMED,
            **schedule_context(db, day, user),
            **flash(request),
        },
    )


@router.post("/home/bookings")
def create_booking(
    space_id: int = Form(...),
    day: date = Form(...),
    start: time = Form(...),
    end: time = Form(...),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if user is None:
        return redirect("/login")
    try:
        booking_service.create_booking(
            db,
            user_id=user.id,
            space_id=space_id,
            start=combine_local(day, start),
            end=combine_local(day, end),
        )
    except DomainError as exc:
        return redirect("/home", err=ua(exc.detail), day=day)
    return redirect("/home", msg="Бронювання створено", day=day)


@router.post("/home/bookings/{booking_id}/cancel")
def cancel_booking(
    request: Request,
    booking_id: int,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if user is None:
        return redirect("/login")
    booking = db.get(Booking, booking_id)
    if booking is None:
        return redirect("/home", err="Бронювання не знайдено")
    if booking.user_id != user.id and not user.is_admin:
        return forbidden(request, user)  # IDOR protection
    try:
        booking_service.cancel_booking(db, booking)
    except DomainError as exc:
        return redirect("/home", err=ua(exc.detail))
    return redirect("/home", msg="Бронювання скасовано")


@router.post("/home/profile")
def update_profile(
    full_name: str = Form(...),
    current_password: str = Form(""),
    new_password: str = Form(""),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> Response:
    if user is None:
        return redirect("/login")
    back = "/admin" if user.is_admin else "/home"
    full_name = full_name.strip()
    if len(full_name) < 2:
        return redirect(back, err="Ім'я має містити щонайменше 2 символи")
    if new_password:
        if not verify_password(current_password, user.hashed_password):
            return redirect(back, err="Поточний пароль невірний")
        if len(new_password) < 8:
            return redirect(back, err="Новий пароль має містити щонайменше 8 символів")
        user.hashed_password = hash_password(new_password)
    user.full_name = full_name
    db.commit()
    return redirect(back, msg="Профіль оновлено")
