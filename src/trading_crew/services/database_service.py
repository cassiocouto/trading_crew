"""Database service for persisting trading data.

Provides high-level operations for storing and querying market data, orders,
positions, and P&L snapshots. All methods accept and return Pydantic domain
models, converting to/from SQLAlchemy ORM models internally.

This service replaces the JSON-file persistence from silvia_v2 with proper
relational storage that supports querying, indexing, and transactions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from trading_crew.db.models import (
    OHLCVRecord,
    OrderRecord,
    PnLSnapshotRecord,
    PositionRecord,
    TickerRecord,
    TradeSignalRecord,
)
from trading_crew.db.session import get_engine, get_session
from trading_crew.models.market import OHLCV, Ticker
from trading_crew.models.order import Order, OrderStatus
from trading_crew.models.portfolio import PnLSnapshot
from trading_crew.models.signal import TradeSignal

logger = logging.getLogger(__name__)


class DatabaseService:
    """High-level persistence operations for the trading system.

    All public methods manage their own sessions and transactions. Callers
    don't need to worry about session lifecycle.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._engine = get_engine(database_url)

    # -- Market Data ----------------------------------------------------------

    def save_ticker(self, ticker: Ticker) -> None:
        """Persist a ticker snapshot."""
        with get_session(self._engine) as session:
            record = TickerRecord(
                symbol=ticker.symbol,
                exchange=ticker.exchange,
                bid=ticker.bid,
                ask=ticker.ask,
                last=ticker.last,
                volume_24h=ticker.volume_24h,
                timestamp=ticker.timestamp,
            )
            session.add(record)
        logger.debug("Saved ticker: %s %s @ %.2f", ticker.exchange, ticker.symbol, ticker.last)

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> int:
        """Persist a batch of OHLCV candles. Returns count saved."""
        if not candles:
            return 0
        with get_session(self._engine) as session:
            records = [
                OHLCVRecord(
                    symbol=c.symbol,
                    exchange=c.exchange,
                    timeframe=c.timeframe,
                    timestamp=c.timestamp,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                )
                for c in candles
            ]
            session.add_all(records)
        logger.debug("Saved %d OHLCV candles", len(records))
        return len(records)

    def get_recent_ohlcv(
        self, symbol: str, exchange: str, timeframe: str, limit: int = 100
    ) -> list[OHLCV]:
        """Fetch the most recent OHLCV candles for a symbol."""
        with get_session(self._engine) as session:
            stmt = (
                select(OHLCVRecord)
                .where(
                    OHLCVRecord.symbol == symbol,
                    OHLCVRecord.exchange == exchange,
                    OHLCVRecord.timeframe == timeframe,
                )
                .order_by(OHLCVRecord.timestamp.desc())
                .limit(limit)
            )
            records = session.execute(stmt).scalars().all()
            return [
                OHLCV(
                    symbol=r.symbol,
                    exchange=r.exchange,
                    timeframe=r.timeframe,
                    timestamp=r.timestamp,
                    open=r.open,
                    high=r.high,
                    low=r.low,
                    close=r.close,
                    volume=r.volume,
                )
                for r in reversed(records)
            ]

    # -- Orders ---------------------------------------------------------------

    def save_order(self, order: Order) -> None:
        """Persist a new or updated order."""
        with get_session(self._engine) as session:
            existing = self._find_order_record(session, order.id)
            if existing:
                existing.status = order.status.value
                existing.filled_amount = order.filled_amount
                existing.average_fill_price = order.average_fill_price
                existing.total_fee = order.total_fee
                existing.updated_at = order.updated_at
            else:
                record = OrderRecord(
                    exchange_order_id=order.id,
                    symbol=order.request.symbol,
                    exchange=order.request.exchange,
                    side=order.request.side.value,
                    order_type=order.request.order_type.value,
                    status=order.status.value,
                    requested_amount=order.request.amount,
                    filled_amount=order.filled_amount,
                    requested_price=order.request.price,
                    average_fill_price=order.average_fill_price,
                    stop_loss_price=order.request.stop_loss_price,
                    take_profit_price=order.request.take_profit_price,
                    total_fee=order.total_fee,
                    strategy_name=order.request.strategy_name,
                    signal_confidence=order.request.signal_confidence,
                    created_at=order.created_at,
                    updated_at=order.updated_at,
                    raw_exchange_response=json.dumps(order.exchange_data, default=str),
                )
                session.add(record)
        logger.debug("Saved order %s [%s]", order.id, order.status.value)

    def get_open_orders(self) -> list[OrderRecord]:
        """Fetch all orders with an active (non-terminal) status."""
        with get_session(self._engine) as session:
            stmt = select(OrderRecord).where(
                OrderRecord.status.in_(["pending", "open", "partially_filled"])
            )
            return list(session.execute(stmt).scalars().all())

    # -- Signals (audit trail) ------------------------------------------------

    def save_signal(self, signal: TradeSignal, risk_verdict: str | None = None) -> None:
        """Persist a trade signal for audit trail and analysis."""
        with get_session(self._engine) as session:
            record = TradeSignalRecord(
                symbol=signal.symbol,
                exchange=signal.exchange,
                signal_type=signal.signal_type.value,
                strength=signal.strength.value,
                confidence=signal.confidence,
                strategy_name=signal.strategy_name,
                entry_price=signal.entry_price,
                stop_loss_price=signal.stop_loss_price,
                take_profit_price=signal.take_profit_price,
                reason=signal.reason,
                risk_verdict=risk_verdict,
                timestamp=signal.timestamp,
            )
            session.add(record)

    # -- Portfolio ------------------------------------------------------------

    def save_pnl_snapshot(self, snapshot: PnLSnapshot) -> None:
        """Persist a portfolio P&L snapshot."""
        with get_session(self._engine) as session:
            record = PnLSnapshotRecord(
                timestamp=snapshot.timestamp,
                total_balance_quote=snapshot.total_balance_quote,
                unrealized_pnl=snapshot.unrealized_pnl,
                realized_pnl=snapshot.realized_pnl,
                total_fees=snapshot.total_fees,
                num_open_positions=snapshot.num_open_positions,
                drawdown_pct=snapshot.drawdown_pct,
            )
            session.add(record)

    def get_pnl_history(
        self, since: datetime | None = None, limit: int = 500
    ) -> list[PnLSnapshot]:
        """Fetch P&L snapshots for equity curve rendering."""
        with get_session(self._engine) as session:
            stmt = select(PnLSnapshotRecord).order_by(PnLSnapshotRecord.timestamp.desc())
            if since:
                stmt = stmt.where(PnLSnapshotRecord.timestamp >= since)
            stmt = stmt.limit(limit)
            records = session.execute(stmt).scalars().all()
            return [
                PnLSnapshot(
                    timestamp=r.timestamp,
                    total_balance_quote=r.total_balance_quote,
                    unrealized_pnl=r.unrealized_pnl,
                    realized_pnl=r.realized_pnl,
                    total_fees=r.total_fees,
                    num_open_positions=r.num_open_positions,
                    drawdown_pct=r.drawdown_pct,
                )
                for r in reversed(records)
            ]

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _find_order_record(session: Session, exchange_order_id: str) -> OrderRecord | None:
        """Look up an order record by its exchange-assigned ID."""
        stmt = select(OrderRecord).where(
            OrderRecord.exchange_order_id == exchange_order_id
        )
        return session.execute(stmt).scalar_one_or_none()
