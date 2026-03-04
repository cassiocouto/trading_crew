"""Cycle history REST endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import CycleResponse
from trading_crew.db.models import CycleRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["cycles"])


@router.get("/", response_model=list[CycleResponse])
def get_cycles(
    limit: int = Query(default=50, ge=1, le=500),
    db: DatabaseService = Depends(get_db),
) -> list[CycleResponse]:
    """Return recent cycle summaries, newest first."""
    from sqlalchemy import select

    with get_session(db._engine) as session:
        records = session.execute(
            select(CycleRecord).order_by(CycleRecord.id.desc()).limit(limit)
        ).scalars().all()
        return [_cycle_to_response(r) for r in records]


@router.get("/latest", response_model=CycleResponse)
def get_latest_cycle(db: DatabaseService = Depends(get_db)) -> CycleResponse:
    """Return the most recent completed cycle."""
    cycle = db.get_latest_cycle()
    if cycle is None:
        raise HTTPException(status_code=404, detail="No cycle data available")
    return _cycle_to_response(cycle)


def _cycle_to_response(record: CycleRecord) -> CycleResponse:
    return CycleResponse(
        id=record.id,
        cycle_number=record.cycle_number,
        timestamp=record.timestamp,
        num_signals=record.num_signals,
        num_orders_placed=record.num_orders_placed,
        num_orders_filled=record.num_orders_filled,
        num_orders_cancelled=record.num_orders_cancelled,
        num_orders_failed=record.num_orders_failed,
        portfolio_balance=record.portfolio_balance,
        realized_pnl=record.realized_pnl,
        circuit_breaker_tripped=record.circuit_breaker_tripped,
        errors_json=record.errors_json,
    )
