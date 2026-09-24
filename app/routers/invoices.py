from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import AdminUser, Customer, Invoice, InvoiceItem, PointsMode, ShopSettings
from app.pagination import page_meta
from app.points import compute_line_points, compute_points
from app.schemas import (
    InvoiceCreate,
    InvoiceItemIn,
    InvoiceListOut,
    InvoiceOut,
    InvoiceUpdate,
    PaginatedInvoices,
)
from app.security import get_current_admin

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _get_settings(db: Session) -> ShopSettings:
    settings = db.scalar(select(ShopSettings).limit(1))
    if not settings:
        settings = ShopSettings()
        db.add(settings)
        db.flush()
    return settings


def _next_invoice_no(db: Session) -> str:
    count = db.scalar(select(func.count()).select_from(Invoice)) or 0
    return f"INV-{count + 1:05d}"


def _apply_items(
    invoice: Invoice,
    items: list[InvoiceItemIn],
    settings: ShopSettings,
    points_override: Decimal | None,
) -> None:
    invoice.items.clear()
    total_qty = Decimal("0")
    total_amount = Decimal("0")
    line_points_sum = Decimal("0")

    for item in items:
        line_amount = (item.qty * item.unit_price).quantize(Decimal("0.01"))
        line_pts = compute_line_points(
            line_amount=line_amount,
            qty=item.qty,
            settings=settings,
            item_override=item.points_earned if settings.points_mode == PointsMode.MANUAL else None,
        )
        invoice.items.append(
            InvoiceItem(
                item_name=item.item_name.strip(),
                qty=item.qty,
                unit=item.unit.strip() or "piece",
                unit_price=item.unit_price,
                line_amount=line_amount,
                points_earned=line_pts,
            )
        )
        total_qty += item.qty
        total_amount += line_amount
        line_points_sum += line_pts

    invoice.total_qty = total_qty
    invoice.total_amount = total_amount

    if points_override is not None:
        invoice.points_earned = points_override
        invoice.points_overridden = True
    elif settings.points_mode == PointsMode.MANUAL:
        invoice.points_earned = line_points_sum
        invoice.points_overridden = False
    else:
        invoice.points_earned = compute_points(
            amount=total_amount, qty=total_qty, settings=settings, override=None
        )
        invoice.points_overridden = False
        # redistribute line points proportionally for display when using invoice-level formula
        if total_amount > 0 and settings.points_mode in (
            PointsMode.RUPEES_PER_POINT,
            PointsMode.PERCENTAGE_OF_AMOUNT,
        ):
            remaining = invoice.points_earned
            for i, line in enumerate(invoice.items):
                if i == len(invoice.items) - 1:
                    line.points_earned = remaining
                else:
                    share = (line.line_amount / total_amount * invoice.points_earned).quantize(
                        Decimal("0.01")
                    )
                    line.points_earned = share
                    remaining -= share
        elif settings.points_mode == PointsMode.PER_QUANTITY:
            for line in invoice.items:
                line.points_earned = compute_line_points(
                    line_amount=line.line_amount, qty=line.qty, settings=settings
                )


def _adjust_lifetime(customer: Customer, delta: Decimal) -> None:
    customer.lifetime_points = (customer.lifetime_points or Decimal("0")) + delta


def _to_out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=inv.id,
        invoice_no=inv.invoice_no,
        customer_id=inv.customer_id,
        customer_name=inv.customer.name if inv.customer else None,
        customer_type_name=inv.customer.customer_type.name
        if inv.customer and inv.customer.customer_type
        else None,
        created_by_admin_id=inv.created_by_admin_id,
        purchased_at=inv.purchased_at,
        payment_mode=inv.payment_mode,
        notes=inv.notes,
        total_qty=inv.total_qty,
        total_amount=inv.total_amount,
        points_earned=inv.points_earned,
        points_overridden=inv.points_overridden,
        items=inv.items,
        created_at=inv.created_at,
    )


def _to_list(inv: Invoice) -> InvoiceListOut:
    return InvoiceListOut(
        id=inv.id,
        invoice_no=inv.invoice_no,
        customer_id=inv.customer_id,
        customer_name=inv.customer.name if inv.customer else None,
        purchased_at=inv.purchased_at,
        payment_mode=inv.payment_mode,
        total_qty=inv.total_qty,
        total_amount=inv.total_amount,
        points_earned=inv.points_earned,
        created_at=inv.created_at,
    )


@router.get("", response_model=PaginatedInvoices)
def list_invoices(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    customer_id: UUID | None = None,
    search: str | None = None,
) -> PaginatedInvoices:
    stmt = select(Invoice).options(joinedload(Invoice.customer))
    count_stmt = select(func.count()).select_from(Invoice)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
        count_stmt = count_stmt.where(Invoice.customer_id == customer_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.join(Customer).where(
            (Invoice.invoice_no.ilike(like)) | (Customer.name.ilike(like))
        )
        count_stmt = count_stmt.select_from(Invoice).join(Customer).where(
            (Invoice.invoice_no.ilike(like)) | (Customer.name.ilike(like))
        )
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Invoice.purchased_at.desc(), Invoice.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    return PaginatedInvoices(items=[_to_list(r) for r in rows], meta=page_meta(total, page, page_size))


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    body: InvoiceCreate,
    db: Annotated[Session, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(get_current_admin)],
) -> InvoiceOut:
    customer = db.get(Customer, body.customer_id)
    if not customer:
        raise HTTPException(status_code=400, detail="Customer not found")
    settings = _get_settings(db)
    if settings.points_mode == PointsMode.MANUAL:
        for item in body.items:
            if item.points_earned is None and body.points_override is None:
                raise HTTPException(
                    status_code=400,
                    detail="Manual points mode: enter points on each line or set invoice points override",
                )

    inv = Invoice(
        invoice_no=_next_invoice_no(db),
        customer_id=customer.id,
        created_by_admin_id=admin.id,
        purchased_at=body.purchased_at,
        payment_mode=body.payment_mode,
        notes=body.notes,
    )
    db.add(inv)
    db.flush()
    _apply_items(inv, body.items, settings, body.points_override)
    _adjust_lifetime(customer, inv.points_earned)
    db.commit()
    inv = db.scalar(
        select(Invoice)
        .options(
            joinedload(Invoice.items),
            joinedload(Invoice.customer).joinedload(Customer.customer_type),
        )
        .where(Invoice.id == inv.id)
    )
    return _to_out(inv)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> InvoiceOut:
    inv = db.scalar(
        select(Invoice)
        .options(
            joinedload(Invoice.items),
            joinedload(Invoice.customer).joinedload(Customer.customer_type),
        )
        .where(Invoice.id == invoice_id)
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _to_out(inv)


@router.put("/{invoice_id}", response_model=InvoiceOut)
def update_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> InvoiceOut:
    inv = db.scalar(
        select(Invoice).options(joinedload(Invoice.items), joinedload(Invoice.customer)).where(
            Invoice.id == invoice_id
        )
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    old_points = inv.points_earned
    old_customer = inv.customer

    if body.customer_id is not None:
        customer = db.get(Customer, body.customer_id)
        if not customer:
            raise HTTPException(status_code=400, detail="Customer not found")
        inv.customer_id = customer.id
        inv.customer = customer

    if body.purchased_at is not None:
        inv.purchased_at = body.purchased_at
    if body.payment_mode is not None:
        inv.payment_mode = body.payment_mode
    if body.notes is not None:
        inv.notes = body.notes

    settings = _get_settings(db)
    override = body.points_override
    if body.clear_points_override:
        override = None
        inv.points_overridden = False
    elif override is None and inv.points_overridden:
        override = inv.points_earned

    if body.items is not None:
        _apply_items(inv, body.items, settings, override)
    elif override is not None:
        inv.points_earned = override
        inv.points_overridden = True

    # lifetime points: remove old, add new (possibly different customer)
    _adjust_lifetime(old_customer, -old_points)
    _adjust_lifetime(inv.customer, inv.points_earned)

    db.commit()
    inv = db.scalar(
        select(Invoice)
        .options(
            joinedload(Invoice.items),
            joinedload(Invoice.customer).joinedload(Customer.customer_type),
        )
        .where(Invoice.id == invoice_id)
    )
    return _to_out(inv)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_invoice(
    invoice_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[AdminUser, Depends(get_current_admin)],
) -> Response:
    inv = db.scalar(
        select(Invoice).options(joinedload(Invoice.customer)).where(Invoice.id == invoice_id)
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _adjust_lifetime(inv.customer, -inv.points_earned)
    db.delete(inv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
