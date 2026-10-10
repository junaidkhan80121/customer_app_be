"""catalog items and invoice line link

Revision ID: 003_items
Revises: 002_slab_dates
Create Date: 2026-10-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_items"
down_revision: Union[str, None] = "002_slab_dates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("points_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_items_name", "items", ["name"])
    op.create_index("ix_items_sku", "items", ["sku"], unique=True)

    op.add_column("invoice_items", sa.Column("item_id", sa.Uuid(), nullable=True))
    op.add_column("invoice_items", sa.Column("sku", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_invoice_items_item_id",
        "invoice_items",
        "items",
        ["item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_invoice_items_item_id", "invoice_items", type_="foreignkey")
    op.drop_column("invoice_items", "sku")
    op.drop_column("invoice_items", "item_id")
    op.drop_index("ix_items_sku", table_name="items")
    op.drop_index("ix_items_name", table_name="items")
    op.drop_table("items")
