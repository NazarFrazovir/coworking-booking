"""Pydantic schemas for the Booking resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingStatus


class BookingBase(BaseModel):
    space_id: int
    start_time: datetime
    end_time: datetime


class BookingCreate(BookingBase):
    """``user_id`` is NOT accepted from the client — it is always taken
    from the authenticated user, so nobody can book on someone's behalf."""


class BookingUpdate(BaseModel):
    """Reschedule an existing booking."""

    start_time: datetime
    end_time: datetime


class BookingRead(BookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: BookingStatus
