"""WebSocket connection manager and DB-polling event emitter.

The poller maintains per-connection integer watermarks and detects new DB rows
without any IPC coupling to the trading loop process:

  - cycle_complete   : MAX(id) on cycle_history exceeds watermark
  - order_filled     : new OrderRecord with status='filled' beyond watermark
  - signal_generated : MAX(id) on trade_signals exceeds watermark
  - circuit_breaker  : newest CycleRecord has circuit_breaker_tripped=True
                       AND its id exceeds the cycle watermark
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from trading_crew.api.schemas import WsEvent

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks active WebSocket connections and broadcasts events to all."""

    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.append(ws)
        logger.debug("WS client connected (%d active)", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active = [c for c in self._active if c is not ws]
        logger.debug("WS client disconnected (%d active)", len(self._active))

    async def broadcast(self, event: WsEvent) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._active):
            try:
                await ws.send_text(event.model_dump_json())
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


async def ws_events_handler(ws: WebSocket) -> None:
    """Handle a single WebSocket client: poll DB and push incremental events."""
    db: DatabaseService = ws.app.state.db
    poll_interval: int = ws.app.state.ws_poll_interval

    await manager.connect(ws)

    # Initialise watermarks from current max IDs so we only push *new* rows.
    cycle_wm, order_wm, signal_wm = await asyncio.to_thread(_get_initial_watermarks, db)

    try:
        while True:
            await asyncio.sleep(poll_interval)

            events, cycle_wm, order_wm, signal_wm = await asyncio.to_thread(
                _collect_events, db, cycle_wm, order_wm, signal_wm
            )
            for event in events:
                await manager.broadcast(event)
    except WebSocketDisconnect:
        logger.debug("WS client disconnected normally")
    except Exception as exc:
        logger.warning("WS handler error: %s", exc)
    finally:
        manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Internal helpers (all run in a thread via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _get_initial_watermarks(db: DatabaseService) -> tuple[int, int, int]:
    """Return current max IDs for cycle_history, orders, trade_signals."""
    from sqlalchemy import func, select

    from trading_crew.db.models import CycleRecord, OrderRecord, TradeSignalRecord
    from trading_crew.db.session import get_session

    with get_session(db._engine) as session:
        cycle_wm = int(session.execute(select(func.max(CycleRecord.id))).scalar() or 0)
        order_wm = int(session.execute(select(func.max(OrderRecord.id))).scalar() or 0)
        signal_wm = int(session.execute(select(func.max(TradeSignalRecord.id))).scalar() or 0)
    return cycle_wm, order_wm, signal_wm


def _collect_events(
    db: DatabaseService,
    cycle_wm: int,
    order_wm: int,
    signal_wm: int,
) -> tuple[list[WsEvent], int, int, int]:
    """Query DB for new rows and return a list of WsEvents plus updated watermarks.

    Running in a threadpool, returns plain data so the caller can broadcast
    events back on the async event loop without touching asyncio internals.
    """
    from sqlalchemy import select

    from trading_crew.db.models import CycleRecord, OrderRecord, TradeSignalRecord
    from trading_crew.db.session import get_session

    events: list[WsEvent] = []

    with get_session(db._engine) as session:
        # --- cycle_complete / circuit_breaker ---
        new_cycles = (
            session.execute(
                select(CycleRecord).where(CycleRecord.id > cycle_wm).order_by(CycleRecord.id)
            )
            .scalars()
            .all()
        )
        for record in new_cycles:
            cycle_payload = {
                "cycle_number": record.cycle_number,
                "portfolio_balance": record.portfolio_balance,
                "realized_pnl": record.realized_pnl,
                "num_orders_filled": record.num_orders_filled,
                "circuit_breaker_tripped": record.circuit_breaker_tripped,
            }
            events.append(WsEvent(type="cycle_complete", payload=cycle_payload))
            if record.circuit_breaker_tripped:
                events.append(WsEvent(type="circuit_breaker", payload=cycle_payload))
            cycle_wm = max(cycle_wm, record.id)

        # --- order_filled ---
        new_fills = (
            session.execute(
                select(OrderRecord).where(
                    OrderRecord.id > order_wm,
                    OrderRecord.status == "filled",
                )
            )
            .scalars()
            .all()
        )
        for order_rec in new_fills:
            order_payload = {
                "exchange_order_id": order_rec.exchange_order_id,
                "symbol": order_rec.symbol,
                "side": order_rec.side,
                "filled_amount": order_rec.filled_amount,
                "average_fill_price": order_rec.average_fill_price,
                "strategy_name": order_rec.strategy_name,
            }
            events.append(WsEvent(type="order_filled", payload=order_payload))

        # Update order watermark to max seen (not just fills)
        new_orders_max = session.execute(
            select(OrderRecord.id).where(OrderRecord.id > order_wm).order_by(OrderRecord.id.desc())
        ).scalar()
        if new_orders_max:
            order_wm = new_orders_max

        # --- signal_generated ---
        new_signals = (
            session.execute(select(TradeSignalRecord).where(TradeSignalRecord.id > signal_wm))
            .scalars()
            .all()
        )
        for signal_rec in new_signals:
            signal_payload = {
                "symbol": signal_rec.symbol,
                "signal_type": signal_rec.signal_type,
                "strategy_name": signal_rec.strategy_name,
                "confidence": signal_rec.confidence,
            }
            events.append(WsEvent(type="signal_generated", payload=signal_payload))
            signal_wm = max(signal_wm, signal_rec.id)

    return events, cycle_wm, order_wm, signal_wm


# Keep _poll_and_emit as an alias for tests that reference it directly.
def _poll_and_emit(
    db: DatabaseService,
    cycle_wm: int,
    order_wm: int,
    signal_wm: int,
) -> tuple[list[WsEvent], int, int, int]:
    """Thin wrapper used by tests; returns (events, updated watermarks)."""
    return _collect_events(db, cycle_wm, order_wm, signal_wm)
