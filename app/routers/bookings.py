"""Booking endpoints.

Every endpoint requires authentication. ``user_id`` always comes from the
token, never from the request body, and every operation on an existing
booking goes through ``ensure_owner_or_admin`` (IDOR protection).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ensure_owner_or_admin, get_current_user
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingRead, BookingUpdate
from app.services import bookings as booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _get_own_booking(db: Session, booking_id: int, current_user: User) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    ensure_owner_or_admin(current_user, booking.user_id)
    return booking


@router.post("/", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Booking:
    return booking_service.create_booking(
        db,
        user_id=current_user.id,
        space_id=payload.space_id,
        start=payload.start_time,
        end=payload.end_time,
    )


@router.get("/", response_model=list[BookingRead])
def list_my_bookings(
    status_filter: BookingStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Booking]:
    """Bookings of the current user only (admins use /admin/bookings)."""
    query = select(Booking).where(Booking.user_id == current_user.id)
    if status_filter:
        query = query.where(Booking.status == status_filter)
    return list(db.scalars(query.order_by(Booking.start_time)))


@router.get("/{booking_id}", response_model=BookingRead)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Booking:
    return _get_own_booking(db, booking_id, current_user)


@router.patch("/{booking_id}", response_model=BookingRead)
def reschedule_booking(
    booking_id: int,
    payload: BookingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Booking:
    booking = _get_own_booking(db, booking_id, current_user)
    return booking_service.reschedule_booking(
        db, booking, start=payload.start_time, end=payload.end_time
    )


@router.post("/{booking_id}/cancel", response_model=BookingRead)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Booking:
    booking = _get_own_booking(db, booking_id, current_user)
    return booking_service.cancel_booking(db, booking)
