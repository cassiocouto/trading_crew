"""SQLAlchemy ORM models.

These tables persist market data, orders, positions, and portfolio snapshots.
They are the source of truth for the system's state and enable recovery after
restarts, historical analysis, and backtesting.

Naming convention: table names use plural nouns (e.g. "orders", "positions").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class TickerRecord(Base):
    """Persisted ticker snapshot.

    Stores every price fetch for historical analysis and backtesting.
    """

    __tablename__ = "tickers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    bid: Mapped[float] = mapped_column(Float, nullable=False)
    ask: Mapped[float] = mapped_column(Float, nullable=False)
    last: Mapped[float] = mapped_column(Float, nullable=False)
    volume_24h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, server_default=func.now()
    )


class OHLCVRecord(Base):
    """Persisted OHLCV candle.

    Has a unique constraint on (symbol, exchange, timeframe, timestamp) to
    prevent duplicate candles from accumulating on repeated fetches.
    """

    __tablename__ = "ohlcv"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "exchange", "timeframe", "timestamp",
            name="uq_ohlcv_candle",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(30), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class OrderRecord(Base):
    """Persisted order with full lifecycle tracking.

    Replaces the JSON-based order persistence from silvia_v2. Supports
    querying by status, symbol, strategy, and time range.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange_order_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(30), nullable=False)
    side: Mapped[str] = mapped_column(SAEnum("buy", "sell", name="order_side"), nullable=False)
    order_type: Mapped[str] = mapped_column(
        SAEnum("market", "limit", name="order_type"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        SAEnum(
            "pending", "open", "partially_filled", "filled", "cancelled", "rejected",
            name="order_status",
        ),
        nullable=False,
        default="pending",
        index=True,
    )
    requested_amount: Mapped[float] = mapped_column(Float, nullable=False)
    filled_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    requested_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    strategy_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    signal_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    raw_exchange_response: Mapped[str | None] = mapped_column(Text, nullable=True)


class PositionRecord(Base):
    """Persisted open position.

    When a position is closed, it's moved to ``closed_positions`` and the
    realized P&L is recorded.
    """

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(30), nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False, default="long")
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_open: Mapped[bool] = mapped_column(default=True, index=True)


class PnLSnapshotRecord(Base):
    """Periodic portfolio P&L snapshot for equity curve tracking."""

    __tablename__ = "pnl_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, server_default=func.now()
    )
    total_balance_quote: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_fees: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    num_open_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class TradeSignalRecord(Base):
    """Persisted trade signal for audit trail and strategy analysis.

    Every signal (including rejected ones) is recorded for post-mortem
    analysis and strategy refinement.
    """

    __tablename__ = "trade_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(30), nullable=False)
    signal_type: Mapped[str] = mapped_column(
        SAEnum("buy", "sell", "hold", name="signal_type"), nullable=False
    )
    strength: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(50), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True, server_default=func.now()
    )
