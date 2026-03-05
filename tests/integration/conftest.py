"""Shared fixtures for integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from trading_crew.models.market import OHLCV, Ticker
from trading_crew.models.order import (
    Order,
    OrderFill,
    OrderRequest,
    OrderStatus,
)

# ---------------------------------------------------------------------------
# OHLCV fixture factories
# ---------------------------------------------------------------------------


def _make_bullish_candles(
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    n: int = 60,
    start_price: float = 45_000.0,
) -> list[OHLCV]:
    """Generate deterministic bullish OHLCV candles.

    Prices trend upward so that the EMA-crossover strategy fires a BUY signal
    on the last bar (short EMA crosses above long EMA).
    """
    candles: list[OHLCV] = []
    start = datetime(2024, 1, 1, tzinfo=UTC)
    price = start_price
    for i in range(n):
        close = price + i * 50.0  # steady uptrend
        candles.append(
            OHLCV(
                symbol=symbol,
                exchange=exchange,
                timeframe="1h",
                timestamp=start + timedelta(hours=i),
                open=close - 25.0,
                high=close + 50.0,
                low=close - 50.0,
                close=close,
                volume=100.0 + i,
            )
        )
    return candles


# ---------------------------------------------------------------------------
# Mock async exchange
# ---------------------------------------------------------------------------


def make_mock_exchange(
    symbol: str = "BTC/USDT",
    exchange_id: str = "binance",
    ticker_price: float = 50_000.0,
    n_candles: int = 60,
) -> MagicMock:
    """Build a mock async exchange service with deterministic responses."""
    mock = MagicMock()
    mock.exchange_id = exchange_id
    mock.is_paper = True

    ticker = Ticker(
        symbol=symbol,
        exchange=exchange_id,
        bid=ticker_price - 10.0,
        ask=ticker_price + 10.0,
        last=ticker_price,
        volume_24h=1_000.0,
        timestamp=datetime.now(UTC),
    )
    candles = _make_bullish_candles(symbol, exchange_id, n_candles)

    mock.fetch_ticker = AsyncMock(return_value=ticker)
    mock.fetch_ohlcv = AsyncMock(return_value=candles)

    # Paper-mode order fill
    def _make_fill(request: OrderRequest) -> Order:
        fill_price = ticker_price
        fill = OrderFill(
            price=fill_price,
            amount=request.amount,
            fee=fill_price * request.amount * 0.001,
            fee_currency="USDT",
            timestamp=datetime.now(UTC),
        )
        return Order(
            id=f"paper-mock-{request.symbol.replace('/', '')}",
            request=request,
            status=OrderStatus.FILLED,
            filled_amount=request.amount,
            average_fill_price=fill_price,
            fills=[fill],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    mock.create_order = AsyncMock(side_effect=_make_fill)
    mock.fetch_order_status = AsyncMock(
        return_value={"id": "mock", "status": "closed", "filled": 0.01, "remaining": 0.0}
    )
    mock.cancel_order = AsyncMock()
    mock.fetch_balance = AsyncMock(return_value={"USDT": 10_000.0})
    mock.normalize_order_precision = AsyncMock(
        side_effect=lambda sym, amount, price=None: (amount, price)
    )
    mock.get_market_limits = AsyncMock(
        return_value={"amount_min": 0.0001, "cost_min": 1.0, "price_min": None}
    )
    mock.close = AsyncMock()

    return mock
