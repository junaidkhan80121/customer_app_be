from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, Item
from app.pagination import page_meta
from app.schemas import ItemCreate, ItemOut, ItemUpdate, PaginatedItems
from app.security import get_current_admin

router = APIRouter(prefix="/api/items", tags=["items"])


def _sku(value: str) -> str:
    return value.strip().upper()


def _existing_sku(db: Session, sku: str, exclude_id: UUID | None = None) -> Item | None:
    stmt = select(Item).where(func.lower(Item.sku) == sku.lower())
    if exclude_id is not None:
        stmt = stmt.where(Item.id != exclude_id)
    return db.scalar(stmt)


@router.get("", response_model=PaginatedItems)
def list_items(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    points_enabled: bool | None = None,
    active_only: bool = False,
    sort: str = Query("name", pattern="^(name|sku|price|points|status)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
) -> PaginatedItems:
    stmt = select(Item)
    count_stmt = select(func.count()).select_from(Item)

    if search:
        like = f"%{search.strip()}%"
        filt = or_(Item.name.ilike(like), Item.sku.ilike(like), Item.description.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)
    if points_enabled is not None:
        stmt = stmt.where(Item.points_enabled.is_(points_enabled))
        count_stmt = count_stmt.where(Item.points_enabled.is_(points_enabled))
    if active_only:
        stmt = stmt.where(Item.is_active.is_(True))
        count_stmt = count_stmt.where(Item.is_active.is_(True))

    ascending = order == "asc"
    columns = {
        "name": Item.name,
        "sku": Item.sku,
        "price": Item.price,
        "points": Item.points_enabled,
        "status": Item.is_active,
    }
    primary = columns.get(sort, Item.name)
    primary_order = primary.asc() if ascending else primary.desc()

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(primary_order, Item.name.asc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PaginatedItems(items=list(rows), meta=page_meta(total, page, page_size))


@router.post("", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    body: ItemCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Item:
    sku = _sku(body.sku)
    if _existing_sku(db, sku):
        raise HTTPException(status_code=400, detail="SKU already exists")
    row = Item(
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        sku=sku,
        price=body.price,
        points_enabled=body.points_enabled,
        is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Item:
    row = db.get(Item, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return row


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: UUID,
    body: ItemUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Item:
    row = db.get(Item, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    if body.sku is not None:
        sku = _sku(body.sku)
        if _existing_sku(db, sku, exclude_id=item_id):
            raise HTTPException(status_code=400, detail="SKU already exists")
        row.sku = sku
    if body.name is not None:
        row.name = body.name.strip()
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.price is not None:
        row.price = body.price
    if body.points_enabled is not None:
        row.points_enabled = body.points_enabled
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_item(
    item_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Response:
    row = db.get(Item, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
