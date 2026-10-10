from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import AdminUser, Customer, Scheme, SchemeMetric
from app.pagination import page_meta
from app.scheme_progress import progress_column, qualified_count, totals_subquery
from app.schemas import (
    PaginatedSchemeCustomers,
    PaginatedSchemes,
    SchemeCreate,
    SchemeCustomerRow,
    SchemeOut,
    SchemeUpdate,
)
from app.security import get_current_admin

router = APIRouter(prefix="/api/schemes", tags=["schemes"])


def _check_dates(start, end) -> None:
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="End date must be on or after the start date")


def _to_out(row: Scheme, count: int) -> SchemeOut:
    return SchemeOut(
        id=row.id,
        name=row.name,
        description=row.description,
        metric=row.metric,
        threshold=row.threshold,
        start_date=row.start_date,
        end_date=row.end_date,
        is_active=row.is_active,
        qualified_count=count,
        created_at=row.created_at,
    )


@router.get("", response_model=PaginatedSchemes)
def list_schemes(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    metric: SchemeMetric | None = None,
    active_only: bool = False,
    sort: str = Query("name", pattern="^(name|metric|threshold|qualified|status)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
) -> PaginatedSchemes:
    stmt = select(Scheme)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Scheme.name.ilike(like), Scheme.description.ilike(like)))
    if metric:
        stmt = stmt.where(Scheme.metric == metric)
    if active_only:
        stmt = stmt.where(Scheme.is_active.is_(True))

    rows = list(db.scalars(stmt).all())
    counted = [(row, qualified_count(db, row)) for row in rows]
    reverse = order == "desc"

    def sort_key(pair: tuple[Scheme, int]):
        row, count = pair
        if sort == "metric":
            return row.metric.value
        if sort == "threshold":
            return row.threshold
        if sort == "qualified":
            return count
        if sort == "status":
            return row.is_active
        return row.name.lower()

    counted.sort(key=sort_key, reverse=reverse)
    total = len(counted)
    start = (page - 1) * page_size
    page_rows = counted[start : start + page_size]
    return PaginatedSchemes(
        items=[_to_out(row, count) for row, count in page_rows],
        meta=page_meta(total, page, page_size),
    )


@router.post("", response_model=SchemeOut, status_code=status.HTTP_201_CREATED)
def create_scheme(
    body: SchemeCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> SchemeOut:
    _check_dates(body.start_date, body.end_date)
    name = body.name.strip()
    if db.scalar(select(Scheme).where(func.lower(Scheme.name) == name.lower())):
        raise HTTPException(status_code=400, detail="Scheme already exists")
    row = Scheme(
        name=name,
        description=(body.description or "").strip() or None,
        metric=body.metric,
        threshold=body.threshold,
        start_date=body.start_date,
        end_date=body.end_date,
        is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row, qualified_count(db, row))


@router.get("/{scheme_id}", response_model=SchemeOut)
def get_scheme(
    scheme_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> SchemeOut:
    row = db.get(Scheme, scheme_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return _to_out(row, qualified_count(db, row))


@router.get("/{scheme_id}/customers", response_model=PaginatedSchemeCustomers)
def scheme_customers(
    scheme_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    qualified_only: bool = False,
    sort: str = Query("progress", pattern="^(name|progress|invoices)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedSchemeCustomers:
    scheme = db.get(Scheme, scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")

    totals = totals_subquery(scheme)
    progress = func.coalesce(progress_column(scheme.metric, totals), 0)
    invoice_count = func.coalesce(totals.c.invoice_count, 0)
    stmt = (
        select(Customer, progress.label("progress"), invoice_count.label("invoice_count"))
        .outerjoin(totals, totals.c.customer_id == Customer.id)
        .options(joinedload(Customer.customer_type))
    )
    count_stmt = select(func.count()).select_from(Customer).outerjoin(
        totals, totals.c.customer_id == Customer.id
    )
    if qualified_only:
        stmt = stmt.where(progress >= scheme.threshold)
        count_stmt = count_stmt.where(progress >= scheme.threshold)
    if search:
        like = f"%{search.strip()}%"
        filt = or_(Customer.name.ilike(like), Customer.phone.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    ascending = order == "asc"
    if sort == "name":
        primary = Customer.name.asc() if ascending else Customer.name.desc()
    elif sort == "invoices":
        primary = invoice_count.asc() if ascending else invoice_count.desc()
    else:
        primary = progress.asc() if ascending else progress.desc()

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(primary, Customer.name.asc()).offset((page - 1) * page_size).limit(page_size)
    ).unique().all()
    items = [
        SchemeCustomerRow(
            customer_id=customer.id,
            customer_name=customer.name,
            phone=customer.phone,
            type_name=customer.customer_type.name if customer.customer_type else None,
            progress=Decimal(value or 0),
            invoice_count=int(count or 0),
            qualified=Decimal(value or 0) >= scheme.threshold,
        )
        for customer, value, count in rows
    ]
    return PaginatedSchemeCustomers(items=items, meta=page_meta(total, page, page_size))


@router.patch("/{scheme_id}", response_model=SchemeOut)
def update_scheme(
    scheme_id: UUID,
    body: SchemeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> SchemeOut:
    row = db.get(Scheme, scheme_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheme not found")
    if body.name is not None:
        name = body.name.strip()
        existing = db.scalar(
            select(Scheme).where(func.lower(Scheme.name) == name.lower(), Scheme.id != scheme_id)
        )
        if existing:
            raise HTTPException(status_code=400, detail="Scheme already exists")
        row.name = name
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.metric is not None:
        row.metric = body.metric
    if body.threshold is not None:
        row.threshold = body.threshold
    fields = body.model_fields_set
    if body.clear_dates or "start_date" in fields:
        row.start_date = None if body.clear_dates else body.start_date
    if body.clear_dates or "end_date" in fields:
        row.end_date = None if body.clear_dates else body.end_date
    _check_dates(row.start_date, row.end_date)
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return _to_out(row, qualified_count(db, row))


@router.delete("/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_scheme(
    scheme_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Response:
    row = db.get(Scheme, scheme_id)
    if not row:
        raise HTTPException(status_code=404, detail="Scheme not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
