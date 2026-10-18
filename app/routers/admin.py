"""Admin panel API.

The ``require_admin`` dependency is attached to the whole router, so a new
endpoint added here can't accidentally be left unprotected.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.space import Space
from app.models.user import User, UserRole
from app.schemas.booking import BookingRead
from app.schemas.user import ActiveUpdate, RoleUpdate, UserRead

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict[str, int]:
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "admins": db.scalar(
            select(func.count(User.id)).where(User.role == UserRole.ADMIN)
        )
        or 0,
        "active_spaces": db.scalar(
            select(func.count(Space.id)).where(Space.is_active.is_(True))
        )
        or 0,
        "confirmed_bookings": db.scalar(
            select(func.count(Booking.id)).where(
                Booking.status == BookingStatus.CONFIRMED
            )
        )
        or 0,
    }


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}/role", response_model=UserRead)
def change_role(
    user_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    user = _get_user_or_404(db, user_id)
    if user.id == admin.id and payload.role != UserRole.ADMIN:
        # Protects against the system ending up with zero admins by accident.
        raise HTTPException(status_code=409, detail="You cannot demote yourself")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/active", response_model=UserRead)
def set_active(
    user_id: int,
    payload: ActiveUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    """Block / unblock a user. A blocked user's tokens stop working at once,
    because every request re-loads the user from the DB."""
    user = _get_user_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot block yourself")
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


@router.get("/bookings", response_model=list[BookingRead])
def list_all_bookings(
    status_filter: BookingStatus | None = None,
    db: Session = Depends(get_db),
) -> list[Booking]:
    query = select(Booking)
    if status_filter:
        query = query.where(Booking.status == status_filter)
    return list(db.scalars(query.order_by(Booking.start_time)))
