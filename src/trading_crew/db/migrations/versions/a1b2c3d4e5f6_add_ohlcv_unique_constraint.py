"""add ohlcv unique constraint with dedup

For databases initialized via init_db() before the unique constraint was
added to the ORM model, this migration:
  1. Removes duplicate candles (keeps the row with the lowest id).
  2. Adds the uq_ohlcv_candle unique constraint.

Revision ID: a1b2c3d4e5f6
Revises: 935f5ab19963
Create Date: 2026-03-03 17:35:00.000000
"""

import contextlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "935f5ab19963"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Step 1: Remove duplicate candles, keeping the row with the lowest id.
    if dialect == "sqlite":
        conn.execute(
            sa.text("""
            DELETE FROM ohlcv
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM ohlcv
                GROUP BY symbol, exchange, timeframe, timestamp
            )
        """)
        )
    else:
        # PostgreSQL / MySQL — use standard CTE-based dedup
        conn.execute(
            sa.text("""
            DELETE FROM ohlcv
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY symbol, exchange, timeframe, timestamp
                               ORDER BY id
                           ) AS rn
                    FROM ohlcv
                ) ranked
                WHERE rn > 1
            )
        """)
        )

    # Step 2: Add the unique constraint (skip if it already exists, e.g.
    # when this DB was created fresh with the updated ORM model).
    with contextlib.suppress(Exception):
        op.create_unique_constraint(
            "uq_ohlcv_candle",
            "ohlcv",
            ["symbol", "exchange", "timeframe", "timestamp"],
        )


def downgrade() -> None:
    with contextlib.suppress(Exception):
        op.drop_constraint("uq_ohlcv_candle", "ohlcv", type_="unique")
