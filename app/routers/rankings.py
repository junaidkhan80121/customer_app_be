from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser, Customer, CustomerType, Invoice, TimeSlab
from app.pagination import page_meta
from app.schemas import DashboardOut, RankingResponse, RankingRow
from app.security import get_current_admin

router = APIRouter(prefix="/api", tags=["rankings"])


def _resolve_date_range(
    db: Session,
    slab_id: UUID | None,
    from_date: date | None,
    to_date: date | None,
) -> tuple[date | None, date | None, str | None]:
    if from_date or to_date:
        return from_date, to_date or date.today(), None

    slab: TimeSlab | None = None
    if slab_id:
        slab = db.get(TimeSlab, slab_id)
        if not slab:
            raise HTTPException(status_code=400, detail="Invalid time slab")
    else:
        slab = db.scalar(select(TimeSlab).where(TimeSlab.is_default.is_(True)))
        if not slab:
            slab = db.scalar(select(TimeSlab).order_by(TimeSlab.months).limit(1))

    if not slab:
        return None, date.today(), None

    end = date.today()
    start = end - relativedelta(months=slab.months)
    return start, end, slab.name


def _ranking_query(
    db: Session,
    *,
    start: date | None,
    end: date | None,
    type_id: UUID | None,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[RankingRow], int]:
    filters = []
    if start:
        filters.append(Invoice.purchased_at >= start)
    if end:
        filters.append(Invoice.purchased_at <= end)
    if type_id:
        filters.append(Customer.type_id == type_id)

    agg = (
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            Customer.phone.label("phone"),
            CustomerType.name.label("type_name"),
            func.coalesce(func.sum(Invoice.total_qty), 0).label("total_qty"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("total_amount"),
            func.coalesce(func.sum(Invoice.points_earned), 0).label("total_points"),
            func.count(Invoice.id).label("invoice_count"),
        )
        .select_from(Customer)
        .join(CustomerType, Customer.type_id == CustomerType.id)
        .join(Invoice, Invoice.customer_id == Customer.id)
        .where(*filters)
        .group_by(Customer.id, Customer.name, Customer.phone, CustomerType.name)
    )

    count_stmt = select(func.count()).select_from(agg.subquery())
    total = db.scalar(count_stmt) or 0

    order_expr = {
        "qty": func.coalesce(func.sum(Invoice.total_qty), 0).desc(),
        "amount": func.coalesce(func.sum(Invoice.total_amount), 0).desc(),
        "points": func.coalesce(func.sum(Invoice.points_earned), 0).desc(),
    }.get(sort, func.coalesce(func.sum(Invoice.total_amount), 0).desc())

    ordered = agg.order_by(order_expr, Customer.name.asc())

    rows = db.execute(ordered.offset((page - 1) * page_size).limit(page_size)).all()
    items = [
        RankingRow(
            customer_id=r.customer_id,
            customer_name=r.customer_name,
            phone=r.phone,
            type_name=r.type_name,
            total_qty=Decimal(r.total_qty),
            total_amount=Decimal(r.total_amount),
            total_points=Decimal(r.total_points),
            invoice_count=int(r.invoice_count),
        )
        for r in rows
    ]
    return items, total


@router.get("/rankings", response_model=RankingResponse)
def rankings(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    slab_id: UUID | None = None,
    type_id: UUID | None = None,
    sort: str = Query("amount", pattern="^(qty|amount|points)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    from_date: date | None = None,
    to_date: date | None = None,
) -> RankingResponse:
    start, end, slab_name = _resolve_date_range(db, slab_id, from_date, to_date)
    items, total = _ranking_query(
        db, start=start, end=end, type_id=type_id, sort=sort, page=page, page_size=page_size
    )
    return RankingResponse(
        items=items,
        meta=page_meta(total, page, page_size),
        slab_name=slab_name,
        from_date=start,
        to_date=end,
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> DashboardOut:
    start, end, _ = _resolve_date_range(db, None, None, None)
    top, _ = _ranking_query(
        db, start=start, end=end, type_id=None, sort="amount", page=1, page_size=5
    )
    customer_count = db.scalar(select(func.count()).select_from(Customer)) or 0
    invoice_count = db.scalar(select(func.count()).select_from(Invoice)) or 0
    sales = db.scalar(select(func.coalesce(func.sum(Invoice.total_amount), 0))) or 0
    return DashboardOut(
        customer_count=customer_count,
        invoice_count=invoice_count,
        sales_amount=Decimal(sales),
        top_buyers=top,
    )
