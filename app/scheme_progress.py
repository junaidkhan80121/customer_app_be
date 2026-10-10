"""Compare a customer's purchases with a scheme threshold."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, Scheme, SchemeMetric


def in_window(purchased_at: date, scheme: Scheme) -> bool:
    if scheme.start_date and purchased_at < scheme.start_date:
        return False
    if scheme.end_date and purchased_at > scheme.end_date:
        return False
    return True


def measure(metric: SchemeMetric, amount: Decimal, qty: Decimal, points: Decimal) -> Decimal:
    if metric == SchemeMetric.AMOUNT:
        return amount
    if metric == SchemeMetric.QUANTITY:
        return qty
    return points


def progress_for_customer(db: Session, scheme: Scheme, customer_id: UUID) -> tuple[Decimal, int]:
    stmt = select(
        func.coalesce(func.sum(Invoice.total_amount), 0),
        func.coalesce(func.sum(Invoice.total_qty), 0),
        func.coalesce(func.sum(Invoice.points_earned), 0),
        func.count(Invoice.id),
    ).where(Invoice.customer_id == customer_id)
    if scheme.start_date:
        stmt = stmt.where(Invoice.purchased_at >= scheme.start_date)
    if scheme.end_date:
        stmt = stmt.where(Invoice.purchased_at <= scheme.end_date)
    amount, qty, points, count = db.execute(stmt).one()
    return measure(scheme.metric, Decimal(amount), Decimal(qty), Decimal(points)), int(count or 0)


def totals_subquery(scheme: Scheme):
    stmt = (
        select(
            Invoice.customer_id.label("customer_id"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("amount"),
            func.coalesce(func.sum(Invoice.total_qty), 0).label("qty"),
            func.coalesce(func.sum(Invoice.points_earned), 0).label("points"),
            func.count(Invoice.id).label("invoice_count"),
        )
        .group_by(Invoice.customer_id)
    )
    if scheme.start_date:
        stmt = stmt.where(Invoice.purchased_at >= scheme.start_date)
    if scheme.end_date:
        stmt = stmt.where(Invoice.purchased_at <= scheme.end_date)
    return stmt.subquery()


def progress_column(metric: SchemeMetric, totals):
    if metric == SchemeMetric.AMOUNT:
        return totals.c.amount
    if metric == SchemeMetric.QUANTITY:
        return totals.c.qty
    return totals.c.points


def qualified_count(db: Session, scheme: Scheme) -> int:
    totals = totals_subquery(scheme)
    progress = progress_column(scheme.metric, totals)
    stmt = select(func.count()).select_from(totals).where(progress >= scheme.threshold)
    return int(db.scalar(stmt) or 0)
