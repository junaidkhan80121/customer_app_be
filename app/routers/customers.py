from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import AdminUser, Customer, CustomerType, Invoice, InvoiceItem, PaymentMode, Scheme
from app.pagination import page_meta
from app.routers.invoices import _to_out as invoice_to_out
from app.scheme_progress import progress_for_customer
from app.schemas import (
    CustomerCreate,
    CustomerOut,
    CustomerPurchases,
    CustomerSchemeStatus,
    CustomerUpdate,
    PaginatedCustomers,
)
from app.security import get_current_admin

router = APIRouter(prefix="/api/customers", tags=["customers"])


def _to_out(c: Customer) -> CustomerOut:
    return CustomerOut(
        id=c.id,
        name=c.name,
        phone=c.phone,
        address=c.address,
        type_id=c.type_id,
        type_name=c.customer_type.name if c.customer_type else None,
        lifetime_points=c.lifetime_points,
        is_active=c.is_active,
        created_at=c.created_at,
    )


@router.get("", response_model=PaginatedCustomers)
def list_customers(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    type_id: UUID | None = None,
    active_only: bool = False,
    sort: str = Query("name", pattern="^(name|phone|type|points|status)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
) -> PaginatedCustomers:
    stmt = select(Customer).options(joinedload(Customer.customer_type))
    count_stmt = select(func.count()).select_from(Customer)
    if search:
        like = f"%{search.strip()}%"
        filt = or_(Customer.name.ilike(like), Customer.phone.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)
    if type_id:
        stmt = stmt.where(Customer.type_id == type_id)
        count_stmt = count_stmt.where(Customer.type_id == type_id)
    if active_only:
        stmt = stmt.where(Customer.is_active.is_(True))
        count_stmt = count_stmt.where(Customer.is_active.is_(True))

    if sort == "type":
        stmt = stmt.join(CustomerType)

    ascending = order == "asc"
    columns = {
        "name": Customer.name,
        "phone": Customer.phone,
        "type": CustomerType.name,
        "points": Customer.lifetime_points,
        "status": Customer.is_active,
    }
    primary = columns.get(sort, Customer.name)
    primary_order = primary.asc() if ascending else primary.desc()

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(primary_order, Customer.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return PaginatedCustomers(items=[_to_out(c) for c in rows], meta=page_meta(total, page, page_size))


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    body: CustomerCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> CustomerOut:
    if not db.get(CustomerType, body.type_id):
        raise HTTPException(status_code=400, detail="Invalid customer type")
    if db.scalar(select(Customer).where(Customer.phone == body.phone.strip())):
        raise HTTPException(status_code=400, detail="Phone already exists")
    row = Customer(
        name=body.name.strip(),
        phone=body.phone.strip(),
        address=body.address,
        type_id=body.type_id,
        is_active=body.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    row = db.scalar(
        select(Customer).options(joinedload(Customer.customer_type)).where(Customer.id == row.id)
    )
    return _to_out(row)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> CustomerOut:
    row = db.scalar(
        select(Customer).options(joinedload(Customer.customer_type)).where(Customer.id == customer_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _to_out(row)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: UUID,
    body: CustomerUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> CustomerOut:
    row = db.get(Customer, customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    if body.type_id is not None and not db.get(CustomerType, body.type_id):
        raise HTTPException(status_code=400, detail="Invalid customer type")
    if body.phone is not None:
        phone = body.phone.strip()
        existing = db.scalar(select(Customer).where(Customer.phone == phone, Customer.id != customer_id))
        if existing:
            raise HTTPException(status_code=400, detail="Phone already exists")
        row.phone = phone
    if body.name is not None:
        row.name = body.name.strip()
    if body.address is not None:
        row.address = body.address
    if body.type_id is not None:
        row.type_id = body.type_id
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    row = db.scalar(
        select(Customer).options(joinedload(Customer.customer_type)).where(Customer.id == customer_id)
    )
    return _to_out(row)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_customer(
    customer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Response:
    row = db.scalar(
        select(Customer)
        .options(joinedload(Customer.invoices).joinedload(Invoice.items))
        .where(Customer.id == customer_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    # Cascade removes invoices + line items via relationship
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _scoped_invoices(customer_id: UUID):
    return select(Invoice).where(Invoice.customer_id == customer_id)


@router.get("/{customer_id}/purchases", response_model=CustomerPurchases)
def customer_purchases(
    customer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    payment_mode: PaymentMode | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    sort: str = Query("date", pattern="^(date|amount|qty|points|invoice_no|payment)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> CustomerPurchases:
    if not db.get(Customer, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")

    stmt = _scoped_invoices(customer_id).options(
        joinedload(Invoice.items),
        joinedload(Invoice.customer).joinedload(Customer.customer_type),
    )
    count_stmt = select(func.count()).select_from(Invoice).where(Invoice.customer_id == customer_id)
    sum_stmt = select(
        func.coalesce(func.sum(Invoice.total_qty), 0),
        func.coalesce(func.sum(Invoice.total_amount), 0),
        func.coalesce(func.sum(Invoice.points_earned), 0),
    ).where(Invoice.customer_id == customer_id)

    if payment_mode:
        stmt = stmt.where(Invoice.payment_mode == payment_mode)
        count_stmt = count_stmt.where(Invoice.payment_mode == payment_mode)
        sum_stmt = sum_stmt.where(Invoice.payment_mode == payment_mode)
    if from_date:
        stmt = stmt.where(Invoice.purchased_at >= from_date)
        count_stmt = count_stmt.where(Invoice.purchased_at >= from_date)
        sum_stmt = sum_stmt.where(Invoice.purchased_at >= from_date)
    if to_date:
        stmt = stmt.where(Invoice.purchased_at <= to_date)
        count_stmt = count_stmt.where(Invoice.purchased_at <= to_date)
        sum_stmt = sum_stmt.where(Invoice.purchased_at <= to_date)
    if search:
        like = f"%{search.strip()}%"
        item_match = (
            select(InvoiceItem.id)
            .where(InvoiceItem.invoice_id == Invoice.id, InvoiceItem.item_name.ilike(like))
            .exists()
        )
        filt = or_(Invoice.invoice_no.ilike(like), Invoice.notes.ilike(like), item_match)
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)
        sum_stmt = sum_stmt.where(filt)

    ascending = order == "asc"
    columns = {
        "date": Invoice.purchased_at,
        "amount": Invoice.total_amount,
        "qty": Invoice.total_qty,
        "points": Invoice.points_earned,
        "invoice_no": Invoice.invoice_no,
        "payment": Invoice.payment_mode,
    }
    primary = columns.get(sort, Invoice.purchased_at)
    primary_order = primary.asc() if ascending else primary.desc()

    total = db.scalar(count_stmt) or 0
    qty, amount, points = db.execute(sum_stmt).one()
    rows = db.scalars(
        stmt.order_by(primary_order, Invoice.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return CustomerPurchases(
        items=[invoice_to_out(row) for row in rows],
        meta=page_meta(total, page, page_size),
        total_qty=Decimal(qty or 0),
        total_amount=Decimal(amount or 0),
        total_points=Decimal(points or 0),
    )


@router.get("/{customer_id}/schemes", response_model=list[CustomerSchemeStatus])
def customer_schemes(
    customer_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> list[CustomerSchemeStatus]:
    if not db.get(Customer, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    schemes = list(db.scalars(select(Scheme).where(Scheme.is_active.is_(True)).order_by(Scheme.name)).all())
    rows: list[CustomerSchemeStatus] = []
    for scheme in schemes:
        progress, _count = progress_for_customer(db, scheme, customer_id)
        rows.append(
            CustomerSchemeStatus(
                scheme_id=scheme.id,
                name=scheme.name,
                description=scheme.description,
                metric=scheme.metric,
                threshold=scheme.threshold,
                progress=progress,
                qualified=progress >= scheme.threshold,
                start_date=scheme.start_date,
                end_date=scheme.end_date,
            )
        )
    rows.sort(key=lambda row: (not row.qualified, row.name.lower()))
    return rows
