"""Booking business rules.

Rules enforced:
1. ``end_time`` > ``start_time``; duration ≤ ``settings.max_booking_hours``.
2. A booking cannot start in the past.
3. The space must exist and be active.
4. No two *confirmed* bookings of one space may overlap in time.
5. Only confirmed future bookings can be rescheduled or cancelled.

Concurrency: before checking for overlaps the space row is locked with
``SELECT ... FOR UPDATE``. Two concurrent requests for the same space are
therefore serialized by PostgreSQL, so both cannot pass the overlap check
at once. Requests for *different* spaces don't block each other.
The partial unique index on (space_id, start_time) remains as a last-line
DB-level guarantee.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.booking import Booking, BookingStatus
from app.models.space import Space
from app.services.errors import ConflictError, NotFoundError, ValidationError


def to_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC and convert aware ones to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _validate_interval(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = to_utc(start), to_utc(end)
    if end <= start:
        raise ValidationError("end_time must be after start_time")
    if end - start > timedelta(hours=settings.max_booking_hours):
        raise ValidationError(
            f"A booking cannot be longer than {settings.max_booking_hours} hours"
        )
    if start < datetime.now(UTC):
        raise ValidationError("Cannot book a slot in the past")
    return start, end


def _lock_active_space(db: Session, space_id: int) -> Space:
    space = db.scalar(select(Space).where(Space.id == space_id).with_for_update())
    if space is None or not space.is_active:
        raise NotFoundError("Space not found")
    return space


def _ensure_no_overlap(
    db: Session,
    space_id: int,
    start: datetime,
    end: datetime,
    exclude_booking_id: int | None = None,
) -> None:
    # Two intervals [a, b) and [c, d) overlap  <=>  a < d AND c < b
    query = select(Booking.id).where(
        Booking.space_id == space_id,
        Booking.status == BookingStatus.CONFIRMED,
        Booking.start_time < end,
        Booking.end_time > start,
    )
    if exclude_booking_id is not None:
        query = query.where(Booking.id != exclude_booking_id)
    if db.scalar(query.limit(1)) is not None:
        raise ConflictError("This slot is already booked")


def _commit(db: Session, booking: Booking) -> Booking:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("This slot is already booked") from exc
    db.refresh(booking)
    return booking


def create_booking(
    db: Session, *, user_id: int, space_id: int, start: datetime, end: datetime
) -> Booking:
    start, end = _validate_interval(start, end)
    _lock_active_space(db, space_id)
    _ensure_no_overlap(db, space_id, start, end)
    booking = Booking(
        user_id=user_id,
        space_id=space_id,
        start_time=start,
        end_time=end,
        status=BookingStatus.CONFIRMED,
    )
    db.add(booking)
    return _commit(db, booking)


def _ensure_modifiable(booking: Booking) -> None:
    if booking.status != BookingStatus.CONFIRMED:
        raise ConflictError("Booking is already cancelled")
    if to_utc(booking.start_time) < datetime.now(UTC):
        raise ConflictError("Past bookings cannot be changed")


def reschedule_booking(
    db: Session, booking: Booking, *, start: datetime, end: datetime
) -> Booking:
    _ensure_modifiable(booking)
    start, end = _validate_interval(start, end)
    _lock_active_space(db, booking.space_id)
    _ensure_no_overlap(db, booking.space_id, start, end, exclude_booking_id=booking.id)
    booking.start_time = start
    booking.end_time = end
    return _commit(db, booking)


def cancel_booking(db: Session, booking: Booking) -> Booking:
    _ensure_modifiable(booking)
    booking.status = BookingStatus.CANCELLED
    return _commit(db, booking)


def busy_slots(db: Session, space_id: int, day_start: datetime) -> list[Booking]:
    """Confirmed bookings of a space intersecting the 24h window from day_start."""
    day_start = to_utc(day_start)
    day_end = day_start + timedelta(days=1)
    return list(
        db.scalars(
            select(Booking)
            .where(
                Booking.space_id == space_id,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.start_time < day_end,
                Booking.end_time > day_start,
            )
            .order_by(Booking.start_time)
        )
    )
