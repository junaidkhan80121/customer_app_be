from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, ShopSettings, TimeSlab
from app.schemas import (
    ShopSettingsOut,
    ShopSettingsUpdate,
    TimeSlabCreate,
    TimeSlabOut,
    TimeSlabUpdate,
)
from app.security import get_current_admin

router = APIRouter(prefix="/api", tags=["settings"])


def _ensure_settings(db: Session) -> ShopSettings:
    row = db.scalar(select(ShopSettings).limit(1))
    if not row:
        row = ShopSettings()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _validate_slab_dates(start_date, end_date) -> None:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date must be on or before end date")


@router.get("/settings", response_model=ShopSettingsOut)
def get_settings(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> ShopSettings:
    return _ensure_settings(db)


@router.patch("/settings", response_model=ShopSettingsOut)
def update_settings(
    body: ShopSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> ShopSettings:
    row = _ensure_settings(db)
    if body.points_mode is not None:
        row.points_mode = body.points_mode
    if body.rupees_per_point is not None:
        row.rupees_per_point = body.rupees_per_point
    if body.points_percentage is not None:
        row.points_percentage = body.points_percentage
    if body.points_per_quantity is not None:
        row.points_per_quantity = body.points_per_quantity
    db.commit()
    db.refresh(row)
    return row


@router.get("/time-slabs", response_model=list[TimeSlabOut])
def list_slabs(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> list[TimeSlab]:
    return list(db.scalars(select(TimeSlab).order_by(TimeSlab.months)).all())


@router.post("/time-slabs", response_model=TimeSlabOut, status_code=status.HTTP_201_CREATED)
def create_slab(
    body: TimeSlabCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> TimeSlab:
    _validate_slab_dates(body.start_date, body.end_date)
    if body.is_default:
        db.execute(update(TimeSlab).values(is_default=False))
    row = TimeSlab(
        name=body.name.strip(),
        months=body.months,
        start_date=body.start_date,
        end_date=body.end_date,
        is_default=body.is_default,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/time-slabs/{slab_id}", response_model=TimeSlabOut)
def update_slab(
    slab_id: UUID,
    body: TimeSlabUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> TimeSlab:
    row = db.get(TimeSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Time slab not found")

    data = body.model_dump(exclude_unset=True)

    if data.get("is_default") is True:
        db.execute(update(TimeSlab).values(is_default=False))
        row.is_default = True
    elif "is_default" in data and data["is_default"] is False:
        row.is_default = False
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "months" in data and data["months"] is not None:
        row.months = data["months"]
    if "start_date" in data:
        row.start_date = data["start_date"]
    if "end_date" in data:
        row.end_date = data["end_date"]

    _validate_slab_dates(row.start_date, row.end_date)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/time-slabs/{slab_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_slab(
    slab_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Response:
    row = db.get(TimeSlab, slab_id)
    if not row:
        raise HTTPException(status_code=404, detail="Time slab not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
