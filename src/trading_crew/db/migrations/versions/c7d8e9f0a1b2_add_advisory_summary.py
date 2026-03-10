"""add_advisory_summary

Revision ID: c7d8e9f0a1b2
Revises: e7a1b2c3d4f5
Create Date: 2026-03-08 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"  # pragma: allowlist secret
down_revision: str | None = "e7a1b2c3d4f5"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cycle_history",
        sa.Column("advisory_summary", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("cycle_history", "advisory_summary")
