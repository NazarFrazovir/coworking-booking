"""Pydantic schemas for the Space resource."""

from pydantic import BaseModel, ConfigDict


class SpaceBase(BaseModel):
    name: str
    location: str
    capacity: int
    space_type: str


class SpaceCreate(SpaceBase):
    pass


class SpaceRead(SpaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
