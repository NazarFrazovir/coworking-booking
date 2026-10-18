"""Pydantic schemas for the Space resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SpaceBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=255)
    capacity: int = Field(ge=1, le=500)
    space_type: str = Field(min_length=1, max_length=50)


class SpaceCreate(SpaceBase):
    pass


class SpaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    capacity: int | None = Field(default=None, ge=1, le=500)
    space_type: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None


class SpaceRead(SpaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool


class BusySlot(BaseModel):
    """A taken interval — exposed publicly without revealing who booked it."""

    model_config = ConfigDict(from_attributes=True)

    start_time: datetime
    end_time: datetime
