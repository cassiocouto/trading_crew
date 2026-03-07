"""Simulated exchange service for full-fidelity backtesting.

Implements the same public interface as ``ExchangeService`` but replays
preloaded historical candles instead of hitting a live exchange.  Orders
are filled immediately at the current bar's close +/- slippage, matching
paper-mode behaviour.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from trading_crew.models.market import OHLCV, Ticker
from trading_crew.models.order import (
    Order,
    OrderFill,
    OrderRequest,
    OrderSide,
    OrderStatus,
)

logger = logging.getLogger(__name__)

_SYNTHETIC_SPREAD = 0.0005  # 5 bps bid/ask spread


class SimulatedExchangeService:
    """Drop-in replacement for ``ExchangeService`` that replays historical candles.

    Single-symbol only.  Calling ``fetch_ticker`` or ``fetch_ohlcv`` with an
    unknown symbol raises ``ValueError``.
    """

    def __init__(
        self,
        candles: list[OHLCV],
        symbol: str,
        exchange_id: str = "binance",
        fee_rate: float = 0.001,
        slippage_pct: float = 0.001,
    ) -> None:
        if not candles:
            raise ValueError("candles must be non-empty")
        self._candles = candles
        self._symbol = symbol
        self._exchange_id = exchange_id
        self._fee_rate = fee_rate
        self._slippage_pct = slippage_pct

        self._bar_index: int = 0
        self._orders: dict[str, dict[str, Any]] = {}
        self._next_order_id: int = 0

    # -- Properties (2) -------------------------------------------------------

    @property
    def exchange_id(self) -> str:
        return self._exchange_id

    @property
    def is_paper(self) -> bool:
        return True

    # -- Simulation control (not part of ExchangeService interface) -----------

    def advance_bar(self, index: int) -> None:
        """Advance the simulated clock to the given candle index."""
        self._bar_index = min(index, len(self._candles) - 1)

    @property
    def current_candle(self) -> OHLCV:
        return self._candles[self._bar_index]

    # -- Core methods used by MarketIntelligenceService (1) -------------------

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[OHLCV]:
        self._assert_symbol(symbol)
        start = max(0, self._bar_index - limit + 1)
        return self._candles[start : self._bar_index + 1]

    # -- Core methods used by ExecutionService (6) ----------------------------

    async def fetch_ticker(self, symbol: str) -> Ticker:
        self._assert_symbol(symbol)
        candle = self.current_candle
        return Ticker(
            symbol=symbol,
            exchange=self._exchange_id,
            bid=candle.close * (1 - _SYNTHETIC_SPREAD),
            ask=candle.close * (1 + _SYNTHETIC_SPREAD),
            last=candle.close,
            volume_24h=candle.volume,
            timestamp=candle.timestamp,
        )

    async def create_order(self, request: OrderRequest) -> Order:
        self._assert_symbol(request.symbol)
        candle = self.current_candle

        self._next_order_id += 1
        order_id = f"sim-{self._next_order_id}"

        if request.side == OrderSide.BUY:
            fill_price = candle.close * (1 + self._slippage_pct)
        else:
            fill_price = candle.close * (1 - self._slippage_pct)

        fee = request.amount * fill_price * self._fee_rate

        fill = OrderFill(
            price=fill_price,
            amount=request.amount,
            fee=fee,
            fee_currency="USDT",
            timestamp=candle.timestamp,
        )

        order = Order(
            id=order_id,
            request=request,
            status=OrderStatus.FILLED,
            filled_amount=request.amount,
            average_fill_price=fill_price,
            fills=[fill],
            created_at=candle.timestamp,
            updated_at=candle.timestamp,
        )

        self._orders[order_id] = {
            "status": "closed",
            "filled": request.amount,
            "average": fill_price,
            "fee": {"cost": fee, "currency": "USDT"},
            "timestamp": candle.timestamp.isoformat(),
        }

        return order

    async def fetch_order_status(self, order_id: str, symbol: str) -> dict[str, Any]:
        if order_id not in self._orders:
            return {"status": "closed", "filled": 0, "average": 0, "fee": {"cost": 0}}
        return self._orders[order_id]

    async def cancel_order(self, order_id: str, symbol: str) -> None:
        if order_id in self._orders:
            self._orders[order_id]["status"] = "canceled"

    async def normalize_order_precision(
        self,
        symbol: str,
        amount: float,
        price: float | None = None,
    ) -> tuple[float, float | None]:
        rounded_amount = round(amount, 8)
        rounded_price = round(price, 2) if price is not None else None
        return rounded_amount, rounded_price

    async def get_market_limits(self, symbol: str) -> dict[str, float | None]:
        return {"amount_min": 1e-8, "cost_min": 0.01, "price_min": 1e-8}

    # -- Stub methods (5) -- complete interface but not on critical path ------

    async def close(self) -> None:
        pass

    async def fetch_tickers_parallel(self, symbols: list[str]) -> list[Ticker]:
        return [await self.fetch_ticker(s) for s in symbols]

    async def fetch_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime,
        batch_size: int = 500,
    ) -> list[OHLCV]:
        self._assert_symbol(symbol)
        return [c for c in self._candles if since <= c.timestamp <= until]

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> dict[str, list[list[float]]]:
        return {"bids": [], "asks": []}

    async def fetch_balance(self) -> dict[str, float]:
        return {}

    # -- Internal helpers -----------------------------------------------------

    def _assert_symbol(self, symbol: str) -> None:
        if symbol != self._symbol:
            raise ValueError(f"SimulatedExchangeService only supports {self._symbol}, got {symbol}")
