"""Portfolio REST endpoints."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import PnLPointResponse, PortfolioResponse, PositionResponse
from trading_crew.db.models import PortfolioRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["portfolio"])


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

        raw_positions: dict = json.loads(record.positions_json or "{}")
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
        return PortfolioResponse(
            balance_quote=record.balance_quote,
            realized_pnl=record.realized_pnl,
            total_fees=record.total_fees,
            num_positions=record.num_positions,
            positions=positions,
            timestamp=record.timestamp,
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
