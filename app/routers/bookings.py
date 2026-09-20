"""Booking-related API endpoints.

The interesting part here (and the reason this domain was chosen) is
`create_booking`: when two clients try to book the same space for the same
start_time concurrently, the database's UNIQUE constraint is the source of
truth, not application-level checks — that's what makes it safe under real
concurrent load.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingRead

router = APIRouter(prefix="/bookings", tags=["bookings"])

# TODO(lab #2+): replace with the authenticated user's id once auth exists.
DEMO_USER_ID = 1


@router.post("/", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)) -> Booking:
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    booking = Booking(
        user_id=DEMO_USER_ID,
        space_id=payload.space_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This slot is already booked"
        ) from exc
    db.refresh(booking)
    return booking


@router.get("/{booking_id}", response_model=BookingRead)
def get_booking(booking_id: int, db: Session = Depends(get_db)) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking
