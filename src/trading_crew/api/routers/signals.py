"""Signals REST endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import SignalResponse, StrategyStatsResponse
from trading_crew.db.models import OrderRecord, TradeSignalRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["signals"])


@router.get("/", response_model=list[SignalResponse])
def get_signals(
    limit: int = Query(default=50, ge=1, le=500),
    strategy: str | None = Query(default=None),
    db: DatabaseService = Depends(get_db),
) -> list[SignalResponse]:
    """Return recent trade signals, optionally filtered by strategy."""
    from sqlalchemy import select

    with get_session(db._engine) as session:
        stmt = select(TradeSignalRecord).order_by(TradeSignalRecord.id.desc()).limit(limit)
        if strategy:
            stmt = (
                select(TradeSignalRecord)
                .where(TradeSignalRecord.strategy_name == strategy)
                .order_by(TradeSignalRecord.id.desc())
                .limit(limit)
            )
        records = session.execute(stmt).scalars().all()
        return [
            SignalResponse(
                id=r.id,
                symbol=r.symbol,
                exchange=r.exchange,
                signal_type=r.signal_type,
                strength=r.strength,
                confidence=r.confidence,
                strategy_name=r.strategy_name,
                entry_price=r.entry_price,
                stop_loss_price=r.stop_loss_price,
                take_profit_price=r.take_profit_price,
                reason=r.reason,
                risk_verdict=r.risk_verdict,
                timestamp=r.timestamp,
            )
            for r in records
        ]


@router.get("/strategy-stats", response_model=list[StrategyStatsResponse])
def get_strategy_stats(db: DatabaseService = Depends(get_db)) -> list[StrategyStatsResponse]:
    """Return per-strategy signal and order aggregates.

    Two separate GROUP BY queries are merged in Python because there is no
    foreign key between TradeSignalRecord and OrderRecord.
    """
    from sqlalchemy import case, func, select

    with get_session(db._engine) as session:
        signal_rows = session.execute(
            select(
                TradeSignalRecord.strategy_name,
                func.count().label("total_signals"),
                func.sum(
                    case((TradeSignalRecord.signal_type == "buy", 1), else_=0)
                ).label("buy_signals"),
                func.sum(
                    case((TradeSignalRecord.signal_type == "sell", 1), else_=0)
                ).label("sell_signals"),
                func.avg(TradeSignalRecord.confidence).label("avg_confidence"),
            ).group_by(TradeSignalRecord.strategy_name)
        ).all()

        order_rows = session.execute(
            select(
                OrderRecord.strategy_name,
                func.count().label("orders_placed"),
                func.sum(
                    case((OrderRecord.status == "filled", 1), else_=0)
                ).label("orders_filled"),
            ).group_by(OrderRecord.strategy_name)
        ).all()

        # Merge by strategy_name in Python (must be done inside session scope)
        stats: dict[str, dict] = {}
        for row in signal_rows:
            stats[row.strategy_name] = {
                "total_signals": row.total_signals or 0,
                "buy_signals": int(row.buy_signals or 0),
                "sell_signals": int(row.sell_signals or 0),
                "avg_confidence": float(row.avg_confidence or 0.0),
                "orders_placed": 0,
                "orders_filled": 0,
            }
        for row in order_rows:
            if row.strategy_name not in stats:
                stats[row.strategy_name] = {
                    "total_signals": 0,
                    "buy_signals": 0,
                    "sell_signals": 0,
                    "avg_confidence": 0.0,
                    "orders_placed": 0,
                    "orders_filled": 0,
                }
            stats[row.strategy_name]["orders_placed"] = row.orders_placed or 0
            stats[row.strategy_name]["orders_filled"] = int(row.orders_filled or 0)

    return [
        StrategyStatsResponse(strategy_name=name, **data) for name, data in sorted(stats.items())
    ]
