"""Space (coworking desk / conference room) ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.booking import Booking


class Space(Base):
    """A bookable physical space: a desk, a meeting room, etc."""

    __tablename__ = "spaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    space_type: Mapped[str] = mapped_column(String(50), nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="space")
