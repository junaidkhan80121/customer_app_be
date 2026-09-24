from __future__ import annotations

from decimal import Decimal
from math import floor

from app.models import PointsMode, ShopSettings


def compute_points(
    *,
    amount: Decimal,
    qty: Decimal,
    settings: ShopSettings,
    override: Decimal | None = None,
) -> Decimal:
    """Compute points from shop settings. Override wins when provided (manual invoice override)."""
    if override is not None:
        return Decimal(override).quantize(Decimal("0.01"))

    mode = settings.points_mode
    if mode == PointsMode.MANUAL:
        return Decimal("0")

    if mode == PointsMode.RUPEES_PER_POINT:
        per = settings.rupees_per_point or Decimal("1")
        if per <= 0:
            return Decimal("0")
        return Decimal(floor(float(amount / per))).quantize(Decimal("0.01"))

    if mode == PointsMode.PERCENTAGE_OF_AMOUNT:
        pct = settings.points_percentage or Decimal("0")
        return (amount * pct / Decimal("100")).quantize(Decimal("0.01"))

    if mode == PointsMode.PER_QUANTITY:
        per_qty = settings.points_per_quantity or Decimal("0")
        return (qty * per_qty).quantize(Decimal("0.01"))

    return Decimal("0")


def compute_line_points(
    *,
    line_amount: Decimal,
    qty: Decimal,
    settings: ShopSettings,
    item_override: Decimal | None = None,
) -> Decimal:
    if item_override is not None:
        return Decimal(item_override).quantize(Decimal("0.01"))
    if settings.points_mode == PointsMode.MANUAL:
        return Decimal("0")
    return compute_points(amount=line_amount, qty=qty, settings=settings, override=None)
