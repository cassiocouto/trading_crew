"""add_advisory_columns

Revision ID: e7a1b2c3d4f5
Revises: b4e8f2a1c9d3
Create Date: 2026-03-06 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1b2c3d4f5"  # pragma: allowlist secret
down_revision: str | None = "b4e8f2a1c9d3"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cycle_history",
        sa.Column("uncertainty_score", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column(
        "cycle_history",
        sa.Column("uncertainty_factors_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "cycle_history",
        sa.Column("advisory_ran", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cycle_history",
        sa.Column("advisory_adjustments_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("cycle_history", "advisory_adjustments_json")
    op.drop_column("cycle_history", "advisory_ran")
    op.drop_column("cycle_history", "uncertainty_factors_json")
    op.drop_column("cycle_history", "uncertainty_score")
