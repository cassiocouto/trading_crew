"""CrewAI Tool for database operations.

Allows agents to store and retrieve trading data from the database.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from crewai.tools import BaseTool
from pydantic import Field

from trading_crew.services.database_service import DatabaseService
from trading_crew.utils.datetime import parse_iso_utc


class SaveTickerTool(BaseTool):
    """Save a ticker snapshot to the database for historical tracking."""

    name: str = "save_ticker"
    description: str = (
        "Save a ticker price snapshot to the database. Input: JSON with "
        "'symbol', 'exchange', 'bid', 'ask', 'last', 'volume_24h'."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.market import Ticker

        params = json.loads(input_str)
        ticker = Ticker(
            symbol=params["symbol"],
            exchange=params["exchange"],
            bid=float(params["bid"]),
            ask=float(params["ask"]),
            last=float(params["last"]),
            volume_24h=float(params.get("volume_24h", 0)),
            timestamp=datetime.now(UTC),
        )
        self.db_service.save_ticker(ticker)
        return f"Saved ticker: {ticker.symbol} @ {ticker.last}"


class GetRecentCandlesTool(BaseTool):
    """Retrieve recent OHLCV candles from the database."""

    name: str = "get_recent_candles"
    description: str = (
        "Retrieve recent OHLCV candles from the database. Input: JSON with "
        "'symbol', 'exchange', 'timeframe' (e.g. '1h'), and optional 'limit'."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        params = json.loads(input_str)
        candles = self.db_service.get_recent_ohlcv(
            symbol=params["symbol"],
            exchange=params["exchange"],
            timeframe=params.get("timeframe", "1h"),
            limit=int(params.get("limit", 100)),
        )
        return json.dumps(
            [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ],
            indent=2,
        )


class SaveOHLCVBatchTool(BaseTool):
    """Save OHLCV candles to the database."""

    name: str = "save_ohlcv_batch"
    description: str = (
        "Save a batch of OHLCV candles to the database. Input: JSON with "
        "'symbol', 'exchange', optional 'timeframe' (default '1h'), and "
        "'candles' list containing {timestamp, open, high, low, close, volume}."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.market import OHLCV

        params = json.loads(input_str)
        symbol = params["symbol"]
        exchange = params["exchange"]
        timeframe = params.get("timeframe", "1h")
        raw_candles: list[dict[str, Any]] = params.get("candles", [])

        candles: list[OHLCV] = []
        for c in raw_candles:
            candles.append(
                OHLCV(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    timestamp=self._parse_timestamp(c.get("timestamp")),
                    open=float(c["open"]),
                    high=float(c["high"]),
                    low=float(c["low"]),
                    close=float(c["close"]),
                    volume=float(c.get("volume", 0)),
                )
            )

        count = self.db_service.save_ohlcv_batch(candles)
        return f"Saved {count} OHLCV candles for {exchange} {symbol} ({timeframe})"

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        return parse_iso_utc(value)


class SaveOrderTool(BaseTool):
    """Save or update an order record in the database."""

    name: str = "save_order"
    description: str = (
        "Save or update an order in the database. Input: JSON with 'order_id', "
        "'symbol', 'exchange', 'side' (buy/sell), 'order_type' (market/limit), "
        "'status', 'requested_amount', 'filled_amount', optional 'requested_price', "
        "optional 'average_fill_price', optional 'stop_loss_price', "
        "optional 'take_profit_price', optional 'strategy_name'."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.order import (
            Order,
            OrderRequest,
            OrderSide,
            OrderStatus,
            OrderType,
        )

        try:
            params = json.loads(input_str)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        try:
            request = OrderRequest(
                symbol=params["symbol"],
                exchange=params["exchange"],
                side=OrderSide(params["side"]),
                order_type=OrderType(params["order_type"]),
                amount=float(params["requested_amount"]),
                price=float(params["requested_price"]) if params.get("requested_price") else None,
                stop_loss_price=float(params["stop_loss_price"]) if params.get("stop_loss_price") else None,
                take_profit_price=float(params["take_profit_price"]) if params.get("take_profit_price") else None,
                strategy_name=params.get("strategy_name", ""),
            )
            order = Order(
                id=params["order_id"],
                request=request,
                status=OrderStatus(params["status"]),
                filled_amount=float(params.get("filled_amount", 0)),
                average_fill_price=float(params["average_fill_price"]) if params.get("average_fill_price") else None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            self.db_service.save_order(order)
            return json.dumps({"saved": True, "order_id": order.id, "status": order.status.value})
        except Exception as e:
            return json.dumps({"error": f"Failed to save order: {e}"})


class GetOpenOrdersTool(BaseTool):
    """Retrieve all open (non-terminal) orders from the database."""

    name: str = "get_open_orders"
    description: str = (
        "Retrieve all open orders from the database. Returns a JSON list of "
        "orders with status 'pending', 'open', or 'partially_filled'. "
        "No input required (pass an empty string or '{}')."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        records = self.db_service.get_open_orders()
        return json.dumps(
            [
                {
                    "order_id": r.exchange_order_id,
                    "symbol": r.symbol,
                    "exchange": r.exchange,
                    "side": r.side,
                    "order_type": r.order_type,
                    "status": r.status,
                    "requested_amount": r.requested_amount,
                    "filled_amount": r.filled_amount,
                    "requested_price": r.requested_price,
                    "average_fill_price": r.average_fill_price,
                    "strategy_name": r.strategy_name,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in records
            ],
            indent=2,
        )


class UpdateOrderStatusTool(BaseTool):
    """Update the status of an order in the database by its exchange order ID."""

    name: str = "update_order_status"
    description: str = (
        "Update the status of an order in the database. "
        "Input: JSON with 'order_id' (exchange-assigned) and 'status' "
        "(pending/open/partially_filled/filled/cancelled/rejected). "
        "Returns confirmation or error."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        try:
            params = json.loads(input_str)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        order_id = params.get("order_id", "")
        status = params.get("status", "")

        if not order_id or not status:
            return json.dumps({"error": "Both 'order_id' and 'status' are required"})

        updated = self.db_service.update_order_status_by_exchange_id(order_id, status)
        if updated:
            return json.dumps({"updated": True, "order_id": order_id, "status": status})
        return json.dumps({"updated": False, "error": f"Order {order_id} not found"})


class SavePortfolioTool(BaseTool):
    """Persist the current portfolio state to the database.

    Used by the Monitor agent in HYBRID mode to snapshot portfolio state
    after each reconciliation pass.
    """

    name: str = "save_portfolio"
    description: str = (
        "Save the current portfolio state to the database. "
        "Input: JSON with 'balance_quote' (float), 'realized_pnl' (float), "
        "'total_fees' (float), and 'positions' (dict mapping symbol → "
        "{entry_price, amount, current_price, stop_loss_price, take_profit_price, "
        "strategy_name}). Returns confirmation or error."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.portfolio import Portfolio, Position

        try:
            params = json.loads(input_str)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        try:
            positions = {
                sym: Position(
                    symbol=sym,
                    exchange="",
                    entry_price=float(pos["entry_price"]),
                    amount=float(pos["amount"]),
                    current_price=float(pos.get("current_price", pos["entry_price"])),
                    stop_loss_price=float(pos["stop_loss_price"]) if pos.get("stop_loss_price") else None,
                    take_profit_price=float(pos["take_profit_price"]) if pos.get("take_profit_price") else None,
                    strategy_name=pos.get("strategy_name", ""),
                )
                for sym, pos in params.get("positions", {}).items()
            }
            portfolio = Portfolio(
                balance_quote=float(params["balance_quote"]),
                realized_pnl=float(params.get("realized_pnl", 0.0)),
                total_fees=float(params.get("total_fees", 0.0)),
                positions=positions,
            )
            self.db_service.save_portfolio(portfolio)
            return json.dumps({
                "saved": True,
                "balance_quote": portfolio.balance_quote,
                "num_positions": len(portfolio.positions),
            })
        except Exception as e:
            return json.dumps({"error": f"Failed to save portfolio: {e}"})


class GetFailedOrdersTool(BaseTool):
    """Retrieve failed order records from the dead-letter queue.

    Allows the Monitor agent (or operators) to inspect orders that could not
    be placed and take corrective action.
    """

    name: str = "get_failed_orders"
    description: str = (
        "Retrieve failed order records from the dead-letter queue. "
        "Input: JSON with optional 'unresolved_only' (bool, default true). "
        "Returns a JSON list of failed orders with symbol, side, amount, "
        "error_reason, and timestamp."
    )
    db_service: DatabaseService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        try:
            params = json.loads(input_str) if input_str.strip() else {}
        except json.JSONDecodeError:
            params = {}

        unresolved_only = bool(params.get("unresolved_only", True))
        records = self.db_service.get_failed_orders(unresolved_only=unresolved_only)
        return json.dumps(records, indent=2, default=str)
