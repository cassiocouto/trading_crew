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
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from trading_crew.db.models import (
    CycleRecord,
    FailedOrderRecord,
    OHLCVRecord,
    OrderRecord,
    PnLSnapshotRecord,
    PortfolioRecord,
    TickerRecord,
    TradeSignalRecord,
)
from trading_crew.db.session import get_engine, get_session
from trading_crew.models.market import OHLCV, Ticker
from trading_crew.models.portfolio import PnLSnapshot

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from trading_crew.models.order import Order
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
        """Persist a batch of OHLCV candles with upsert semantics.

        Existing candles (matched by symbol+exchange+timeframe+timestamp) are
        updated with fresh values. New candles are inserted. This prevents
        duplicate accumulation on repeated fetches.

        Returns:
            Number of candles processed.
        """
        if not candles:
            return 0
        with get_session(self._engine) as session:
            count = 0
            for c in candles:
                existing = (
                    session.query(OHLCVRecord)
                    .filter_by(
                        symbol=c.symbol,
                        exchange=c.exchange,
                        timeframe=c.timeframe,
                        timestamp=c.timestamp,
                    )
                    .first()
                )
                if existing:
                    existing.open = c.open
                    existing.high = c.high
                    existing.low = c.low
                    existing.close = c.close
                    existing.volume = c.volume
                else:
                    session.add(
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
                    )
                count += 1
        logger.debug("Upserted %d OHLCV candles", count)
        return count

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

    def get_ohlcv_range(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCV]:
        """Fetch OHLCV candles within a specific date range, ascending by timestamp.

        Args:
            symbol: Trading pair.
            exchange: Exchange identifier.
            timeframe: Candle period (e.g. "1h").
            start: Inclusive start datetime (timezone-aware recommended).
            end: Inclusive end datetime.

        Returns:
            Candles sorted oldest-first whose timestamp falls in [start, end].
        """
        with get_session(self._engine) as session:
            stmt = (
                select(OHLCVRecord)
                .where(
                    OHLCVRecord.symbol == symbol,
                    OHLCVRecord.exchange == exchange,
                    OHLCVRecord.timeframe == timeframe,
                    OHLCVRecord.timestamp >= start,
                    OHLCVRecord.timestamp <= end,
                )
                .order_by(OHLCVRecord.timestamp.asc())
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
                for r in records
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

    def count_open_orders(self) -> int:
        """Count all orders with an active (non-terminal) status."""
        with get_session(self._engine) as session:
            stmt = (
                select(func.count())
                .select_from(OrderRecord)
                .where(OrderRecord.status.in_(["pending", "open", "partially_filled"]))
            )
            result = session.execute(stmt).scalar_one()
            return int(result)

    def update_order_status_by_exchange_id(self, exchange_order_id: str, status: str) -> bool:
        """Update order status by exchange-assigned ID.

        Returns:
            True if an order was found and updated, False otherwise.
        """
        normalized = status.lower()
        with get_session(self._engine) as session:
            record = self._find_order_record(session, exchange_order_id)
            if record is None:
                return False
            record.status = normalized
            return True

    def finalize_pending_order(self, pending_id: str, placed_order: Order) -> bool:
        """Promote a PENDING placeholder record to the real exchange-assigned ID.

        Called after a successful ``create_order()`` call to avoid leaving an
        orphaned PENDING record in the DB.  Updates the record's
        ``exchange_order_id`` and ``status`` in-place so the ``created_at``
        timestamp (used for stale-order detection) is preserved.

        Args:
            pending_id: The temporary ID used when saving the PENDING record
                (e.g. ``"pending-abc123"``).
            placed_order: The ``Order`` returned by the exchange with the real
                ``exchange_order_id`` and final status.

        Returns:
            True if the pending record was found and updated, False otherwise.
        """
        from datetime import datetime as _dt

        from trading_crew.models.order import Order as _Order

        if not isinstance(placed_order, _Order):
            raise TypeError(f"Expected Order, got {type(placed_order)}")

        with get_session(self._engine) as session:
            record = self._find_order_record(session, pending_id)
            if record is None:
                logger.warning(
                    "finalize_pending_order: PENDING record %s not found; saving real order instead",
                    pending_id,
                )
                return False
            record.exchange_order_id = placed_order.id
            record.status = placed_order.status.value
            record.filled_amount = placed_order.filled_amount
            record.average_fill_price = placed_order.average_fill_price
            record.total_fee = placed_order.total_fee
            record.updated_at = placed_order.updated_at or _dt.now(UTC)
        logger.debug(
            "Finalized pending order %s → %s [%s]",
            pending_id,
            placed_order.id,
            placed_order.status.value,
        )
        return True

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

    def get_pnl_history(self, since: datetime | None = None, limit: int = 500) -> list[PnLSnapshot]:
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

    # -- Portfolio State -------------------------------------------------------

    #: Maximum number of portfolio snapshots to retain.  Older rows are pruned
    #: on each save so the table stays bounded.  The crash-recovery reader only
    #: ever needs the latest row; a small surplus gives a short audit window.
    _MAX_PORTFOLIO_SNAPSHOTS: int = 10

    def save_portfolio(self, portfolio: object) -> None:
        """Persist the latest portfolio state, pruning stale snapshots.

        Keeps only the most recent ``_MAX_PORTFOLIO_SNAPSHOTS`` rows so the
        ``portfolio_snapshots`` table does not grow unboundedly over weeks of
        trading.  (Time-series P&L is persisted separately by
        ``save_pnl_snapshot``.)

        Accepts the ``Portfolio`` domain model (typed as ``object`` to avoid
        a circular import — the real type is ``trading_crew.models.portfolio.Portfolio``).
        """
        from trading_crew.models.portfolio import Portfolio

        if not isinstance(portfolio, Portfolio):
            raise TypeError(f"Expected Portfolio, got {type(portfolio)}")

        positions_data = {
            symbol: {
                "entry_price": pos.entry_price,
                "amount": pos.amount,
                "current_price": pos.current_price,
                "stop_loss_price": pos.stop_loss_price,
                "take_profit_price": pos.take_profit_price,
                "strategy_name": pos.strategy_name,
            }
            for symbol, pos in portfolio.positions.items()
        }

        pruned = 0
        with get_session(self._engine) as session:
            # Insert the new snapshot
            record = PortfolioRecord(
                balance_quote=portfolio.balance_quote,
                realized_pnl=portfolio.realized_pnl,
                total_fees=portfolio.total_fees,
                num_positions=len(portfolio.positions),
                positions_json=json.dumps(positions_data, default=str),
            )
            session.add(record)
            session.flush()  # assign PK before pruning

            # Prune rows that exceed the retention window
            stmt = (
                select(PortfolioRecord.id)
                .order_by(PortfolioRecord.id.desc())
                .offset(self._MAX_PORTFOLIO_SNAPSHOTS)
            )
            stale_ids = list(session.execute(stmt).scalars().all())
            if stale_ids:
                session.query(PortfolioRecord).filter(
                    PortfolioRecord.id.in_(stale_ids)
                ).delete(synchronize_session=False)
                pruned = len(stale_ids)

        logger.debug(
            "Saved portfolio snapshot: balance=%.2f, positions=%d (pruned %d old rows)",
            portfolio.balance_quote,
            len(portfolio.positions),
            pruned,
        )

    # -- Failed Orders (dead-letter) ------------------------------------------

    def save_failed_order(self, order_request: object, error_reason: str) -> None:
        """Persist a failed order request for dead-letter review.

        Accepts the ``OrderRequest`` domain model (typed as ``object`` to avoid
        a circular import — the real type is ``trading_crew.models.order.OrderRequest``).
        """
        from trading_crew.models.order import OrderRequest

        if not isinstance(order_request, OrderRequest):
            raise TypeError(f"Expected OrderRequest, got {type(order_request)}")

        with get_session(self._engine) as session:
            record = FailedOrderRecord(
                symbol=order_request.symbol,
                exchange=order_request.exchange,
                side=order_request.side.value,
                order_type=order_request.order_type.value,
                requested_amount=order_request.amount,
                requested_price=order_request.price,
                strategy_name=order_request.strategy_name,
                error_reason=error_reason,
            )
            session.add(record)
        logger.warning(
            "Dead-letter: failed to place %s %s for %s — %s",
            order_request.side.value,
            order_request.symbol,
            order_request.strategy_name,
            error_reason[:200],
        )

    def get_failed_orders(self, unresolved_only: bool = True) -> list[dict]:
        """Retrieve failed order records for manual review.

        Args:
            unresolved_only: When True, returns only unresolved entries.

        Returns:
            List of dicts with failed order details.
        """
        with get_session(self._engine) as session:
            stmt = select(FailedOrderRecord)
            if unresolved_only:
                stmt = stmt.where(FailedOrderRecord.resolved.is_(False))
            stmt = stmt.order_by(FailedOrderRecord.timestamp.desc())
            records = session.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "exchange": r.exchange,
                    "side": r.side,
                    "order_type": r.order_type,
                    "requested_amount": r.requested_amount,
                    "requested_price": r.requested_price,
                    "strategy_name": r.strategy_name,
                    "error_reason": r.error_reason,
                    "resolved": r.resolved,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in records
            ]

    # -- Cycle history --------------------------------------------------------

    def save_cycle_summary(self, state: object, portfolio: object) -> None:
        """Persist a one-row summary for a completed trading cycle.

        Accepts the ``CycleState`` and ``Portfolio`` domain models (typed as
        ``object`` to avoid circular imports).

        On a ``cycle_number`` collision (e.g. restart with the same counter)
        the existing row is updated in-place so the history table remains
        consistent without duplicate entries.
        """
        import json as _json

        from trading_crew.models.cycle import CycleState
        from trading_crew.models.portfolio import Portfolio

        if not isinstance(state, CycleState):
            raise TypeError(f"Expected CycleState, got {type(state)}")
        if not isinstance(portfolio, Portfolio):
            raise TypeError(f"Expected Portfolio, got {type(portfolio)}")

        with get_session(self._engine) as session:
            existing = (
                session.query(CycleRecord)
                .filter_by(cycle_number=state.cycle_number)
                .first()
            )
            timestamp = state.timestamp if state.timestamp.tzinfo is None else state.timestamp.replace(tzinfo=None)
            if existing:
                existing.timestamp = timestamp
                existing.num_signals = len(state.signals)
                existing.num_orders_placed = len(state.orders)
                existing.num_orders_filled = len(state.filled_orders)
                existing.num_orders_cancelled = len(state.cancelled_orders)
                existing.num_orders_failed = len(state.failed_orders)
                existing.portfolio_balance = portfolio.balance_quote
                existing.realized_pnl = portfolio.realized_pnl
                existing.circuit_breaker_tripped = state.circuit_breaker_tripped
                existing.errors_json = _json.dumps(state.errors)
            else:
                record = CycleRecord(
                    cycle_number=state.cycle_number,
                    timestamp=timestamp,
                    num_signals=len(state.signals),
                    num_orders_placed=len(state.orders),
                    num_orders_filled=len(state.filled_orders),
                    num_orders_cancelled=len(state.cancelled_orders),
                    num_orders_failed=len(state.failed_orders),
                    portfolio_balance=portfolio.balance_quote,
                    realized_pnl=portfolio.realized_pnl,
                    circuit_breaker_tripped=state.circuit_breaker_tripped,
                    errors_json=_json.dumps(state.errors),
                )
                session.add(record)
        logger.debug(
            "Saved cycle summary: cycle=%d, signals=%d, filled=%d, balance=%.2f",
            state.cycle_number,
            len(state.signals),
            len(state.filled_orders),
            portfolio.balance_quote,
        )

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _find_order_record(session: Session, exchange_order_id: str) -> OrderRecord | None:
        """Look up an order record by its exchange-assigned ID."""
        stmt = select(OrderRecord).where(OrderRecord.exchange_order_id == exchange_order_id)
        return session.execute(stmt).scalar_one_or_none()
