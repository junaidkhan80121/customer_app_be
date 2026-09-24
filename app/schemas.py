from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import PaymentMode, PointsMode


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth ----
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminOut(ORMModel):
    id: UUID
    email: EmailStr
    name: str
    is_active: bool
    created_at: datetime


class AdminCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=128)


class AdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    is_active: bool | None = None


# ---- Customer types ----
class CustomerTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True


class CustomerTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    is_active: bool | None = None


class CustomerTypeOut(ORMModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime


# ---- Customers ----
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=7, max_length=20)
    address: str | None = None
    type_id: UUID
    is_active: bool = True


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    address: str | None = None
    type_id: UUID | None = None
    is_active: bool | None = None


class CustomerOut(ORMModel):
    id: UUID
    name: str
    phone: str
    address: str | None
    type_id: UUID
    type_name: str | None = None
    lifetime_points: Decimal
    is_active: bool
    created_at: datetime


# ---- Settings / slabs ----
class ShopSettingsOut(ORMModel):
    id: UUID
    points_mode: PointsMode
    rupees_per_point: Decimal
    points_percentage: Decimal
    points_per_quantity: Decimal
    updated_at: datetime | None = None


class ShopSettingsUpdate(BaseModel):
    points_mode: PointsMode | None = None
    rupees_per_point: Decimal | None = Field(default=None, gt=0)
    points_percentage: Decimal | None = Field(default=None, ge=0)
    points_per_quantity: Decimal | None = Field(default=None, ge=0)


class TimeSlabCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    months: int = Field(ge=1, le=120)
    start_date: date | None = None
    end_date: date | None = None
    is_default: bool = False


class TimeSlabUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    months: int | None = Field(default=None, ge=1, le=120)
    start_date: date | None = None
    end_date: date | None = None
    is_default: bool | None = None


class TimeSlabOut(ORMModel):
    id: UUID
    name: str
    months: int
    start_date: date | None = None
    end_date: date | None = None
    is_default: bool
    created_at: datetime


# ---- Invoices ----
class InvoiceItemIn(BaseModel):
    item_name: str = Field(min_length=1, max_length=200)
    qty: Decimal = Field(gt=0)
    unit: str = Field(default="piece", max_length=40)
    unit_price: Decimal = Field(ge=0)
    points_earned: Decimal | None = Field(default=None, ge=0)


class InvoiceItemOut(ORMModel):
    id: UUID
    item_name: str
    qty: Decimal
    unit: str
    unit_price: Decimal
    line_amount: Decimal
    points_earned: Decimal


class InvoiceCreate(BaseModel):
    customer_id: UUID
    purchased_at: date
    payment_mode: PaymentMode = PaymentMode.CASH
    notes: str | None = None
    items: list[InvoiceItemIn] = Field(min_length=1)
    points_override: Decimal | None = Field(default=None, ge=0)


class InvoiceUpdate(BaseModel):
    customer_id: UUID | None = None
    purchased_at: date | None = None
    payment_mode: PaymentMode | None = None
    notes: str | None = None
    items: list[InvoiceItemIn] | None = Field(default=None, min_length=1)
    points_override: Decimal | None = Field(default=None, ge=0)
    clear_points_override: bool = False


class InvoiceOut(ORMModel):
    id: UUID
    invoice_no: str
    customer_id: UUID
    customer_name: str | None = None
    customer_type_name: str | None = None
    created_by_admin_id: UUID
    purchased_at: date
    payment_mode: PaymentMode
    notes: str | None
    total_qty: Decimal
    total_amount: Decimal
    points_earned: Decimal
    points_overridden: bool
    items: list[InvoiceItemOut] = []
    created_at: datetime


class InvoiceListOut(ORMModel):
    id: UUID
    invoice_no: str
    customer_id: UUID
    customer_name: str | None = None
    purchased_at: date
    payment_mode: PaymentMode
    total_qty: Decimal
    total_amount: Decimal
    points_earned: Decimal
    created_at: datetime


# ---- Rankings / pagination ----
class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class RankingRow(BaseModel):
    customer_id: UUID
    customer_name: str
    phone: str
    type_name: str
    total_qty: Decimal
    total_amount: Decimal
    total_points: Decimal
    invoice_count: int


class RankingResponse(BaseModel):
    items: list[RankingRow]
    meta: PageMeta
    slab_name: str | None = None
    from_date: date | None = None
    to_date: date | None = None


class PaginatedCustomers(BaseModel):
    items: list[CustomerOut]
    meta: PageMeta


class PaginatedInvoices(BaseModel):
    items: list[InvoiceListOut]
    meta: PageMeta


class DashboardOut(BaseModel):
    customer_count: int
    invoice_count: int
    sales_amount: Decimal
    top_buyers: list[RankingRow]
