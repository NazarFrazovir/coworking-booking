"""Space (coworking desk / conference room) ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
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
    # Soft delete: a space with booking history is never physically removed,
    # it is just hidden from the catalogue and cannot receive new bookings.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    bookings: Mapped[list["Booking"]] = relationship(back_populates="space")
