from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, CustomerType
from app.schemas import CustomerTypeCreate, CustomerTypeOut, CustomerTypeUpdate
from app.security import get_current_admin

router = APIRouter(prefix="/api/customer-types", tags=["customer-types"])


@router.get("", response_model=list[CustomerTypeOut])
def list_types(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    active_only: bool = False,
) -> list[CustomerType]:
    stmt = select(CustomerType).order_by(CustomerType.name)
    if active_only:
        stmt = stmt.where(CustomerType.is_active.is_(True))
    return list(db.scalars(stmt).all())


@router.post("", response_model=CustomerTypeOut, status_code=status.HTTP_201_CREATED)
def create_type(
    body: CustomerTypeCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> CustomerType:
    name = body.name.strip()
    if db.scalar(select(CustomerType).where(CustomerType.name.ilike(name))):
        raise HTTPException(status_code=400, detail="Type already exists")
    row = CustomerType(name=name, is_active=body.is_active)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{type_id}", response_model=CustomerTypeOut)
def update_type(
    type_id: UUID,
    body: CustomerTypeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> CustomerType:
    row = db.get(CustomerType, type_id)
    if not row:
        raise HTTPException(status_code=404, detail="Type not found")
    if body.name is not None:
        name = body.name.strip()
        existing = db.scalar(
            select(CustomerType).where(CustomerType.name.ilike(name), CustomerType.id != type_id)
        )
        if existing:
            raise HTTPException(status_code=400, detail="Type already exists")
        row.name = name
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return row
