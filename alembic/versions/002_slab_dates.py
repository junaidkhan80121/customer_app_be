"""optional fixed start/end dates on time slabs

Revision ID: 002_slab_dates
Revises: 001_initial
Create Date: 2026-03-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_slab_dates"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("time_slabs", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("time_slabs", sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("time_slabs", "end_date")
    op.drop_column("time_slabs", "start_date")
