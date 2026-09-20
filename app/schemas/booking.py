"""Pydantic schemas for the Booking resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BookingBase(BaseModel):
    space_id: int
    start_time: datetime
    end_time: datetime


class BookingCreate(BookingBase):
    pass


class BookingRead(BookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
