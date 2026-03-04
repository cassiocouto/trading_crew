"""Orders REST endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import FailedOrderResponse, OrderResponse
from trading_crew.db.models import FailedOrderRecord, OrderRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["orders"])


@router.get("/", response_model=list[OrderResponse])
def get_orders(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    db: DatabaseService = Depends(get_db),
) -> list[OrderResponse]:
    """Return recent orders, optionally filtered by status."""
    from sqlalchemy import select

    with get_session(db._engine) as session:
        stmt = select(OrderRecord).order_by(OrderRecord.id.desc()).limit(limit)
        if status:
            stmt = (
                select(OrderRecord)
                .where(OrderRecord.status == status)
                .order_by(OrderRecord.id.desc())
                .limit(limit)
            )
        records = session.execute(stmt).scalars().all()
        return [
            OrderResponse(
                id=r.id,
                exchange_order_id=r.exchange_order_id,
                symbol=r.symbol,
                exchange=r.exchange,
                side=r.side,
                order_type=r.order_type,
                status=r.status,
                requested_amount=r.requested_amount,
                filled_amount=r.filled_amount,
                requested_price=r.requested_price,
                average_fill_price=r.average_fill_price,
                stop_loss_price=r.stop_loss_price,
                take_profit_price=r.take_profit_price,
                total_fee=r.total_fee,
                strategy_name=r.strategy_name,
                signal_confidence=r.signal_confidence,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in records
        ]


@router.get("/failed", response_model=list[FailedOrderResponse])
def get_failed_orders(
    unresolved_only: bool = Query(default=True),
    db: DatabaseService = Depends(get_db),
) -> list[FailedOrderResponse]:
    """Return failed (dead-letter) orders."""
    from sqlalchemy import select

    with get_session(db._engine) as session:
        stmt = select(FailedOrderRecord).order_by(FailedOrderRecord.id.desc())
        if unresolved_only:
            stmt = (
                select(FailedOrderRecord)
                .where(FailedOrderRecord.resolved.is_(False))
                .order_by(FailedOrderRecord.id.desc())
            )
        records = session.execute(stmt).scalars().all()
        return [
            FailedOrderResponse(
                id=r.id,
                symbol=r.symbol,
                exchange=r.exchange,
                side=r.side,
                order_type=r.order_type,
                requested_amount=r.requested_amount,
                requested_price=r.requested_price,
                strategy_name=r.strategy_name,
                error_reason=r.error_reason,
                resolved=r.resolved,
                timestamp=r.timestamp,
            )
            for r in records
        ]
