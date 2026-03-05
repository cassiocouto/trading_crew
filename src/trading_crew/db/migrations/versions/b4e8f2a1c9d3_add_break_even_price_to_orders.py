"""add_break_even_price_to_orders

Revision ID: b4e8f2a1c9d3
Revises: fd3e40da0c31
Create Date: 2026-03-04 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e8f2a1c9d3"
down_revision: str | None = "fd3e40da0c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("break_even_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "break_even_price")
