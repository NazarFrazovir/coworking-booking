"""Space-related API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.space import Space
from app.schemas.space import SpaceCreate, SpaceRead

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.post("/", response_model=SpaceRead, status_code=status.HTTP_201_CREATED)
def create_space(payload: SpaceCreate, db: Session = Depends(get_db)) -> Space:
    space = Space(**payload.model_dump())
    db.add(space)
    db.commit()
    db.refresh(space)
    return space


@router.get("/", response_model=list[SpaceRead])
def list_spaces(db: Session = Depends(get_db)) -> list[Space]:
    return db.query(Space).all()


@router.get("/{space_id}", response_model=SpaceRead)
def get_space(space_id: int, db: Session = Depends(get_db)) -> Space:
    space = db.get(Space, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="Space not found")
    return space
