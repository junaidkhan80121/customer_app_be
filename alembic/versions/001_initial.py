"""initial schema for PostgreSQL

Revision ID: 001_initial
Revises:
Create Date: 2026-03-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    op.create_table(
        "customer_types",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "shop_settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("points_mode", sa.String(40), nullable=False),
        sa.Column("rupees_per_point", sa.Numeric(12, 2), nullable=False, server_default="100"),
        sa.Column("points_percentage", sa.Numeric(8, 2), nullable=False, server_default="5"),
        sa.Column("points_per_quantity", sa.Numeric(12, 2), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "time_slabs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("type_id", sa.Uuid(), sa.ForeignKey("customer_types.id"), nullable=False),
        sa.Column("lifetime_points", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_customers_name", "customers", ["name"])
    op.create_index("ix_customers_phone", "customers", ["phone"], unique=True)
    op.create_index("ix_customers_type_id", "customers", ["type_id"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("invoice_no", sa.String(40), nullable=False),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("created_by_admin_id", sa.Uuid(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("purchased_at", sa.Date(), nullable=False),
        sa.Column("payment_mode", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("total_qty", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("points_earned", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("points_overridden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("invoice_no", name="uq_invoice_no"),
    )
    op.create_index("ix_invoices_invoice_no", "invoices", ["invoice_no"])
    op.create_index("ix_invoices_purchased_at", "invoices", ["purchased_at"])
    op.create_index("ix_invoices_customer_purchased", "invoices", ["customer_id", "purchased_at"])

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("qty", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False, server_default="piece"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("points_earned", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    op.drop_table("customers")
    op.drop_table("time_slabs")
    op.drop_table("shop_settings")
    op.drop_table("customer_types")
    op.drop_table("admin_users")
