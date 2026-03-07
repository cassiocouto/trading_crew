"""Tests for SimulatedExchangeService."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trading_crew.models.market import OHLCV
from trading_crew.models.order import OrderRequest, OrderSide, OrderType
from trading_crew.services.simulated_exchange import SimulatedExchangeService

pytestmark = pytest.mark.unit


def _make_candles(n: int = 10) -> list[OHLCV]:
    return [
        OHLCV(
            symbol="BTC/USDT",
            exchange="binance",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, i, tzinfo=UTC),
            open=100.0 + i,
            high=105.0 + i,
            low=95.0 + i,
            close=102.0 + i,
            volume=1000.0,
        )
        for i in range(n)
    ]


@pytest.fixture
def exchange() -> SimulatedExchangeService:
    return SimulatedExchangeService(
        candles=_make_candles(),
        symbol="BTC/USDT",
        exchange_id="binance",
        fee_rate=0.001,
        slippage_pct=0.001,
    )


class TestProperties:
    def test_exchange_id(self, exchange: SimulatedExchangeService) -> None:
        assert exchange.exchange_id == "binance"

    def test_is_paper(self, exchange: SimulatedExchangeService) -> None:
        assert exchange.is_paper is True


class TestFetchOhlcv:
    @pytest.mark.asyncio
    async def test_returns_window(self, exchange: SimulatedExchangeService) -> None:
        exchange.advance_bar(5)
        candles = await exchange.fetch_ohlcv("BTC/USDT", "1h", limit=3)
        assert len(candles) == 3
        assert candles[-1].timestamp == datetime(2024, 1, 1, 5, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_window_clamped_at_start(self, exchange: SimulatedExchangeService) -> None:
        exchange.advance_bar(1)
        candles = await exchange.fetch_ohlcv("BTC/USDT", "1h", limit=100)
        assert len(candles) == 2

    @pytest.mark.asyncio
    async def test_unknown_symbol_raises(self, exchange: SimulatedExchangeService) -> None:
        with pytest.raises(ValueError, match="only supports BTC/USDT"):
            await exchange.fetch_ohlcv("ETH/USDT", "1h")


class TestFetchTicker:
    @pytest.mark.asyncio
    async def test_produces_valid_ticker(self, exchange: SimulatedExchangeService) -> None:
        exchange.advance_bar(3)
        ticker = await exchange.fetch_ticker("BTC/USDT")
        assert ticker.symbol == "BTC/USDT"
        assert ticker.exchange == "binance"
        assert ticker.last == 105.0  # close of candle at index 3
        assert ticker.bid < ticker.last
        assert ticker.ask > ticker.last
        assert ticker.volume_24h == 1000.0

    @pytest.mark.asyncio
    async def test_unknown_symbol_raises(self, exchange: SimulatedExchangeService) -> None:
        with pytest.raises(ValueError, match="only supports BTC/USDT"):
            await exchange.fetch_ticker("ETH/USDT")


class TestCreateOrder:
    @pytest.mark.asyncio
    async def test_buy_fills_with_slippage(self, exchange: SimulatedExchangeService) -> None:
        exchange.advance_bar(5)
        req = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.1,
        )
        order = await exchange.create_order(req)
        candle_close = 107.0
        assert order.status.value == "filled"
        assert order.id.startswith("sim-")
        assert order.filled_amount == 0.1
        assert order.average_fill_price is not None
        assert order.average_fill_price > candle_close  # buy slippage pushes up
        assert order.total_fee > 0

    @pytest.mark.asyncio
    async def test_sell_fills_with_slippage(self, exchange: SimulatedExchangeService) -> None:
        exchange.advance_bar(5)
        req = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.1,
        )
        order = await exchange.create_order(req)
        candle_close = 107.0
        assert order.average_fill_price is not None
        assert order.average_fill_price < candle_close  # sell slippage pushes down


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_marks_order(self, exchange: SimulatedExchangeService) -> None:
        exchange.advance_bar(0)
        req = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.01,
        )
        order = await exchange.create_order(req)
        await exchange.cancel_order(order.id, "BTC/USDT")
        status = await exchange.fetch_order_status(order.id, "BTC/USDT")
        assert status["status"] == "canceled"


class TestStubMethods:
    """All stub methods are callable without AttributeError."""

    @pytest.mark.asyncio
    async def test_close(self, exchange: SimulatedExchangeService) -> None:
        await exchange.close()

    @pytest.mark.asyncio
    async def test_fetch_tickers_parallel(self, exchange: SimulatedExchangeService) -> None:
        tickers = await exchange.fetch_tickers_parallel(["BTC/USDT"])
        assert len(tickers) == 1

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_range(self, exchange: SimulatedExchangeService) -> None:
        since = datetime(2024, 1, 1, 2, tzinfo=UTC)
        until = datetime(2024, 1, 1, 5, tzinfo=UTC)
        candles = await exchange.fetch_ohlcv_range("BTC/USDT", "1h", since, until)
        assert all(since <= c.timestamp <= until for c in candles)

    @pytest.mark.asyncio
    async def test_fetch_order_book(self, exchange: SimulatedExchangeService) -> None:
        book = await exchange.fetch_order_book("BTC/USDT")
        assert "bids" in book and "asks" in book

    @pytest.mark.asyncio
    async def test_fetch_balance(self, exchange: SimulatedExchangeService) -> None:
        bal = await exchange.fetch_balance()
        assert isinstance(bal, dict)

    @pytest.mark.asyncio
    async def test_normalize_order_precision(self, exchange: SimulatedExchangeService) -> None:
        amount, price = await exchange.normalize_order_precision("BTC/USDT", 0.123456789, 50000.123)
        assert amount == round(0.123456789, 8)
        assert price == round(50000.123, 2)

    @pytest.mark.asyncio
    async def test_get_market_limits(self, exchange: SimulatedExchangeService) -> None:
        limits = await exchange.get_market_limits("BTC/USDT")
        assert "amount_min" in limits
