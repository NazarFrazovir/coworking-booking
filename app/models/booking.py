"""Booking ORM model.

A booking reserves one space for one user for a time interval.

Lab #1 used ``UNIQUE(space_id, start_time)``. In lab #2 bookings can be
cancelled, and a plain UNIQUE would forbid re-booking a slot that was
cancelled. It is therefore a *partial* unique index that only covers
``status = 'confirmed'`` rows (supported by both PostgreSQL and SQLite).
Overlapping (not just identical) intervals are rejected by the service
layer, which locks the space row first (see ``app/services/bookings.py``).
"""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.space import Space
    from app.models.user import User


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Booking(Base):
    """A reservation of a Space by a User for a given time slot."""

    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "uq_space_start_time_confirmed",
            "space_id",
            "start_time",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
            sqlite_where=text("status = 'confirmed'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default=BookingStatus.CONFIRMED, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="bookings")
    space: Mapped["Space"] = relationship(back_populates="bookings")
