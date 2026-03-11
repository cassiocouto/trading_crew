"""Portfolio REST endpoints."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import (
    ClosedTradeResponse,
    PnLPointResponse,
    PortfolioResponse,
    PositionResponse,
    TradeStatsResponse,
)
from trading_crew.db.models import OrderRecord, PortfolioRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from datetime import datetime

    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["portfolio"])


# ---------------------------------------------------------------------------
# FIFO lot-matching helper (adapted from simulation_runner._build_trades)
# ---------------------------------------------------------------------------


@dataclass
class _BuyLot:
    amount: float
    price: float
    fee: float
    strategy_name: str
    created_at: datetime | None
    remaining: float = field(init=False)

    def __post_init__(self) -> None:
        self.remaining = self.amount


@dataclass
class _OrderTuple:
    """Lightweight snapshot of an OrderRecord, safe to use outside a session."""

    symbol: str
    side: str
    filled_amount: float
    average_fill_price: float
    total_fee: float
    strategy_name: str
    created_at: datetime | None


def _build_closed_trades(
    engine: object,
    *,
    symbol: str | None = None,
    limit: int = 200,
) -> list[ClosedTradeResponse]:
    """FIFO lot-matching over filled OrderRecords, returning closed trades."""
    from sqlalchemy import select

    with get_session(engine) as session:  # type: ignore[arg-type]
        query = (
            select(OrderRecord)
            .where(OrderRecord.status == "filled")
            .order_by(OrderRecord.created_at)
        )
        if symbol:
            query = query.where(OrderRecord.symbol == symbol)
        rows = session.execute(query).scalars().all()
        orders = [
            _OrderTuple(
                symbol=r.symbol,
                side=r.side,
                filled_amount=r.filled_amount or 0.0,
                average_fill_price=r.average_fill_price or 0.0,
                total_fee=r.total_fee or 0.0,
                strategy_name=r.strategy_name or "",
                created_at=r.created_at,
            )
            for r in rows
            if (r.filled_amount or 0.0) > 0 and (r.average_fill_price or 0.0) > 0
        ]

    buy_lots: dict[str, deque[_BuyLot]] = {}
    trades: list[ClosedTradeResponse] = []

    for order in orders:
        if order.side == "buy":
            lot = _BuyLot(
                amount=order.filled_amount,
                price=order.average_fill_price,
                fee=order.total_fee,
                strategy_name=order.strategy_name,
                created_at=order.created_at,
            )
            buy_lots.setdefault(order.symbol, deque()).append(lot)
        elif order.side == "sell":
            queue = buy_lots.get(order.symbol)
            if not queue:
                continue
            remaining_sell = order.filled_amount
            exit_price = order.average_fill_price
            total_exit_fee = order.total_fee

            while remaining_sell > 1e-10 and queue:
                lot = queue[0]
                matched = min(lot.remaining, remaining_sell)
                fraction = matched / (order.filled_amount or 1.0)
                exit_fee_share = total_exit_fee * fraction
                entry_fee_share = lot.fee * (matched / lot.amount) if lot.amount > 0 else 0.0
                pnl = (exit_price - lot.price) * matched - entry_fee_share - exit_fee_share
                cost = lot.price * matched
                pnl_pct = (pnl / cost * 100) if cost > 0 else 0.0
                opened = lot.created_at
                closed = order.created_at
                hold_h = 0.0
                if opened and closed:
                    hold_h = (closed - opened).total_seconds() / 3600

                trades.append(
                    ClosedTradeResponse(
                        symbol=order.symbol,
                        strategy_name=lot.strategy_name,
                        entry_price=lot.price,
                        exit_price=exit_price,
                        amount=matched,
                        pnl=round(pnl, 4),
                        pnl_pct=round(pnl_pct, 2),
                        fee=round(entry_fee_share + exit_fee_share, 4),
                        opened_at=opened,
                        closed_at=closed,
                        hold_duration_hours=round(hold_h, 2),
                    )
                )

                remaining_sell -= matched
                if matched >= lot.remaining - 1e-10:
                    queue.popleft()
                else:
                    lot.remaining -= matched

    trades.sort(key=lambda t: t.closed_at, reverse=True)
    return trades[:limit]


@router.get("/", response_model=PortfolioResponse)
def get_portfolio(db: DatabaseService = Depends(get_db)) -> PortfolioResponse:
    """Return the latest portfolio snapshot."""
    from sqlalchemy import select

    with get_session(db._engine) as session:
        record = session.execute(
            select(PortfolioRecord).order_by(PortfolioRecord.id.desc()).limit(1)
        ).scalar_one_or_none()

        if record is None:
            return PortfolioResponse(
                balance_quote=0.0,
                realized_pnl=0.0,
                total_fees=0.0,
                num_positions=0,
                positions={},
                timestamp=None,
            )

        raw_positions: dict[str, dict[str, object]] = json.loads(record.positions_json or "{}")
        positions = {
            symbol: PositionResponse(
                symbol=symbol,
                entry_price=pos.get("entry_price", 0.0),
                amount=pos.get("amount", 0.0),
                current_price=pos.get("current_price"),
                stop_loss_price=pos.get("stop_loss_price"),
                take_profit_price=pos.get("take_profit_price"),
                strategy_name=pos.get("strategy_name", ""),
            )
            for symbol, pos in raw_positions.items()
        }
        unrealized = sum(
            (p.current_price - p.entry_price) * p.amount
            for p in positions.values()
            if p.current_price is not None
        )
        market_value = sum((p.current_price or 0.0) * p.amount for p in positions.values())
        total_balance = record.balance_quote + market_value

        return PortfolioResponse(
            balance_quote=record.balance_quote,
            realized_pnl=record.realized_pnl,
            total_fees=record.total_fees,
            num_positions=record.num_positions,
            positions=positions,
            timestamp=record.timestamp,
            total_balance_quote=round(total_balance, 2),
            unrealized_pnl=round(unrealized, 2),
        )


@router.get("/history", response_model=list[PnLPointResponse])
def get_pnl_history(
    limit: int = Query(default=100, ge=1, le=1000),
    db: DatabaseService = Depends(get_db),
) -> list[PnLPointResponse]:
    """Return PnL snapshots for the equity curve chart."""
    snapshots = db.get_pnl_history(limit=limit)
    return [
        PnLPointResponse(
            timestamp=s.timestamp,
            total_balance_quote=s.total_balance_quote,
            unrealized_pnl=s.unrealized_pnl,
            realized_pnl=s.realized_pnl,
            total_fees=s.total_fees,
            num_open_positions=s.num_open_positions,
            drawdown_pct=s.drawdown_pct,
        )
        for s in snapshots
    ]


@router.get("/trades", response_model=list[ClosedTradeResponse])
def get_closed_trades(
    limit: int = Query(default=200, ge=1, le=1000),
    symbol: str | None = Query(default=None),
    db: DatabaseService = Depends(get_db),
) -> list[ClosedTradeResponse]:
    """Return closed trades computed via FIFO lot-matching of filled orders."""
    return _build_closed_trades(db._engine, symbol=symbol, limit=limit)


@router.get("/trade-stats", response_model=TradeStatsResponse)
def get_trade_stats(
    symbol: str | None = Query(default=None),
    db: DatabaseService = Depends(get_db),
) -> TradeStatsResponse:
    """Return aggregate trade statistics."""
    trades = _build_closed_trades(db._engine, symbol=symbol, limit=10_000)
    if not trades:
        return TradeStatsResponse(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_pnl=0.0,
            total_pnl=0.0,
            profit_factor=0.0,
            avg_hold_hours=0.0,
        )
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    total_pnl = sum(t.pnl for t in trades)
    gross_profit = sum(t.pnl for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0
    return TradeStatsResponse(
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=round(len(wins) / len(trades) * 100, 1),
        avg_pnl=round(total_pnl / len(trades), 2),
        total_pnl=round(total_pnl, 2),
        profit_factor=round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0,
        avg_hold_hours=round(sum(t.hold_duration_hours for t in trades) / len(trades), 1),
    )
