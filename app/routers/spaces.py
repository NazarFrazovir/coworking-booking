"""Space catalogue: public read, admin-only write."""

from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.database import get_db
from app.models.booking import Booking
from app.models.space import Space
from app.models.user import User
from app.schemas.space import BusySlot, SpaceCreate, SpaceRead, SpaceUpdate
from app.services import bookings as booking_service

router = APIRouter(prefix="/spaces", tags=["spaces"])


def _get_space_or_404(db: Session, space_id: int, *, include_inactive: bool) -> Space:
    space = db.get(Space, space_id)
    if space is None or (not space.is_active and not include_inactive):
        raise HTTPException(status_code=404, detail="Space not found")
    return space


@router.get("/", response_model=list[SpaceRead])
def list_spaces(
    space_type: str | None = None,
    min_capacity: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> list[Space]:
    """Public catalogue of active spaces with simple filters."""
    query = select(Space).where(Space.is_active.is_(True))
    if space_type:
        query = query.where(Space.space_type == space_type)
    if min_capacity:
        query = query.where(Space.capacity >= min_capacity)
    return list(db.scalars(query.order_by(Space.id)))


@router.get("/{space_id}", response_model=SpaceRead)
def get_space(space_id: int, db: Session = Depends(get_db)) -> Space:
    return _get_space_or_404(db, space_id, include_inactive=False)


@router.get("/{space_id}/availability", response_model=list[BusySlot])
def get_availability(
    space_id: int,
    day: date = Query(description="Date (UTC) to check, e.g. 2026-10-20"),
    db: Session = Depends(get_db),
) -> list[Booking]:
    """Taken time slots of a space for a given day (no personal data)."""
    _get_space_or_404(db, space_id, include_inactive=False)
    day_start = datetime.combine(day, time.min, tzinfo=UTC)
    return booking_service.busy_slots(db, space_id, day_start)


@router.post("/", response_model=SpaceRead, status_code=status.HTTP_201_CREATED)
def create_space(
    payload: SpaceCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Space:
    space = Space(**payload.model_dump())
    db.add(space)
    db.commit()
    db.refresh(space)
    return space


@router.patch("/{space_id}", response_model=SpaceRead)
def update_space(
    space_id: int,
    payload: SpaceUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Space:
    space = _get_space_or_404(db, space_id, include_inactive=True)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(space, field, value)
    db.commit()
    db.refresh(space)
    return space


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_space(
    space_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Soft delete: the space disappears from the catalogue, history stays."""
    space = _get_space_or_404(db, space_id, include_inactive=True)
    space.is_active = False
    db.commit()
