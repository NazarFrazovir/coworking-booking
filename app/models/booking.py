"""Booking ORM model.

A booking reserves one space for one user for a time interval. The unique
constraint on (space_id, start_time) is a first line of defense against the
classic race condition of the domain — two users booking the same slot at
the same instant. It will be complemented later (caching lab / load
balancing lab) with row-level locking or a distributed lock.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.space import Space
    from app.models.user import User


class Booking(Base):
    """A reservation of a Space by a User for a given time slot."""

    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("space_id", "start_time", name="uq_space_start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="confirmed")

    user: Mapped["User"] = relationship(back_populates="bookings")
    space: Mapped["Space"] = relationship(back_populates="bookings")
