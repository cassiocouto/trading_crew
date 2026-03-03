"""CrewAI Tool for exchange operations.

Wraps the ExchangeService and exposes ticker, OHLCV, and order operations
to CrewAI agents. Agents call these tools through natural language descriptions.
"""

from __future__ import annotations

import json

from crewai.tools import BaseTool
from pydantic import Field

from trading_crew.services.exchange_service import ExchangeService


class FetchTickerTool(BaseTool):
    """Fetch current price data for a cryptocurrency trading pair."""

    name: str = "fetch_ticker"
    description: str = (
        "Fetch the current ticker (bid, ask, last price, volume) for a "
        "cryptocurrency trading pair. Input: symbol (e.g. 'BTC/USDT')."
    )
    exchange_service: ExchangeService = Field(exclude=True)

    def _run(self, symbol: str) -> str:
        ticker = self.exchange_service.fetch_ticker(symbol.strip())
        return json.dumps(
            {
                "symbol": ticker.symbol,
                "exchange": ticker.exchange,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "last": ticker.last,
                "volume_24h": ticker.volume_24h,
                "spread_pct": round(ticker.spread_pct, 4),
                "timestamp": ticker.timestamp.isoformat(),
            },
            indent=2,
        )


class FetchOHLCVTool(BaseTool):
    """Fetch historical candlestick data for technical analysis."""

    name: str = "fetch_ohlcv"
    description: str = (
        "Fetch OHLCV (candlestick) data for a trading pair. "
        "Input: JSON with 'symbol' (e.g. 'BTC/USDT'), optional 'timeframe' "
        "(default '1h'), and optional 'limit' (default 100)."
    )
    exchange_service: ExchangeService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        try:
            params = json.loads(input_str)
        except json.JSONDecodeError:
            params = {"symbol": input_str.strip()}

        symbol = params.get("symbol", "BTC/USDT")
        timeframe = params.get("timeframe", "1h")
        limit = int(params.get("limit", 100))

        candles = self.exchange_service.fetch_ohlcv(symbol, timeframe, limit)
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
                for c in candles[-20:]  # last 20 candles to avoid token overflow
            ],
            indent=2,
        )


class PlaceOrderTool(BaseTool):
    """Place a trading order on the exchange (or simulate in paper mode)."""

    name: str = "place_order"
    description: str = (
        "Place an order on the exchange. Input: JSON with 'symbol', 'side' "
        "(buy/sell), 'order_type' (market/limit), 'amount', and optional "
        "'price' (required for limit orders)."
    )
    exchange_service: ExchangeService = Field(exclude=True)

    def _run(self, input_str: str) -> str:
        from trading_crew.models.order import OrderRequest, OrderSide, OrderType

        params = json.loads(input_str)

        request = OrderRequest(
            symbol=params["symbol"],
            exchange=self.exchange_service.exchange_id,
            side=OrderSide(params["side"]),
            order_type=OrderType(params["order_type"]),
            amount=float(params["amount"]),
            price=float(params["price"]) if params.get("price") else None,
        )

        order = self.exchange_service.create_order(request)
        return json.dumps(
            {
                "order_id": order.id,
                "status": order.status.value,
                "filled_amount": order.filled_amount,
                "average_price": order.average_fill_price,
                "paper_mode": self.exchange_service.is_paper,
            },
            indent=2,
        )
