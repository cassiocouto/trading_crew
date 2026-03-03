"""Unit tests for Pydantic data models.

Tests validate model construction, validation rules, computed properties,
and serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from trading_crew.models.market import OHLCV, MarketAnalysis, Ticker
from trading_crew.models.order import (
    Order,
    OrderFill,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading_crew.models.portfolio import Portfolio, Position
from trading_crew.models.risk import RiskCheckResult, RiskParams, RiskVerdict
from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal


@pytest.mark.unit
class TestTicker:
    def test_create_ticker(self) -> None:
        ticker = Ticker(
            symbol="BTC/USDT",
            exchange="binance",
            bid=60000.0,
            ask=60010.0,
            last=60005.0,
            volume_24h=1234.5,
            timestamp=datetime.now(UTC),
        )
        assert ticker.symbol == "BTC/USDT"
        assert ticker.spread == 10.0

    def test_spread_pct(self) -> None:
        ticker = Ticker(
            symbol="BTC/USDT",
            exchange="binance",
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume_24h=0,
            timestamp=datetime.now(UTC),
        )
        assert abs(ticker.spread_pct - 0.995) < 0.01

    def test_ticker_is_immutable(self) -> None:
        ticker = Ticker(
            symbol="BTC/USDT",
            exchange="binance",
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume_24h=0,
            timestamp=datetime.now(UTC),
        )
        with pytest.raises((TypeError, ValidationError)):
            ticker.last = 200.0  # type: ignore[misc]


@pytest.mark.unit
class TestOHLCV:
    def test_create_ohlcv(self) -> None:
        candle = OHLCV(
            symbol="ETH/USDT",
            exchange="binance",
            timeframe="1h",
            timestamp=datetime.now(UTC),
            open=3000.0,
            high=3100.0,
            low=2900.0,
            close=3050.0,
            volume=500.0,
        )
        assert candle.close == 3050.0

    def test_volume_must_be_non_negative(self) -> None:
        with pytest.raises(ValueError):
            OHLCV(
                symbol="ETH/USDT",
                exchange="binance",
                timeframe="1h",
                timestamp=datetime.now(UTC),
                open=3000.0,
                high=3100.0,
                low=2900.0,
                close=3050.0,
                volume=-1.0,
            )


@pytest.mark.unit
class TestMarketAnalysis:
    def test_get_indicator(self) -> None:
        analysis = MarketAnalysis(
            symbol="BTC/USDT",
            exchange="binance",
            timestamp=datetime.now(UTC),
            current_price=60000.0,
            indicators={"ema_fast": 59500.0, "rsi_14": 65.0},
        )
        assert analysis.get_indicator("ema_fast") == 59500.0
        assert analysis.get_indicator("nonexistent") is None


@pytest.mark.unit
class TestTradeSignal:
    def test_buy_signal_is_actionable(self) -> None:
        signal = TradeSignal(
            symbol="BTC/USDT",
            exchange="binance",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            confidence=0.85,
            strategy_name="test",
            entry_price=60000.0,
        )
        assert signal.is_actionable is True

    def test_hold_signal_is_not_actionable(self) -> None:
        signal = TradeSignal(
            symbol="BTC/USDT",
            exchange="binance",
            signal_type=SignalType.HOLD,
            strength=SignalStrength.WEAK,
            confidence=0.3,
            strategy_name="test",
            entry_price=60000.0,
        )
        assert signal.is_actionable is False

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValueError):
            TradeSignal(
                symbol="BTC/USDT",
                exchange="binance",
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                confidence=1.5,
                strategy_name="test",
                entry_price=60000.0,
            )


@pytest.mark.unit
class TestOrder:
    def _make_request(self) -> OrderRequest:
        return OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            amount=0.1,
            price=60000.0,
        )

    def test_add_fill(self) -> None:
        order = Order(id="test-001", request=self._make_request())
        fill = OrderFill(price=60000.0, amount=0.05, fee=0.3)
        order.add_fill(fill)

        assert order.filled_amount == 0.05
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.average_fill_price == 60000.0

    def test_fully_filled(self) -> None:
        order = Order(id="test-002", request=self._make_request())
        order.add_fill(OrderFill(price=60000.0, amount=0.1, fee=0.6))

        assert order.status == OrderStatus.FILLED
        assert order.fill_pct == 100.0

    def test_order_status_properties(self) -> None:
        assert OrderStatus.FILLED.is_terminal is True
        assert OrderStatus.OPEN.is_active is True
        assert OrderStatus.CANCELLED.is_active is False


@pytest.mark.unit
class TestPosition:
    def test_unrealized_pnl_long(self) -> None:
        pos = Position(
            symbol="BTC/USDT",
            exchange="binance",
            entry_price=60000.0,
            amount=0.1,
            current_price=62000.0,
        )
        assert pos.unrealized_pnl == 200.0
        assert pos.unrealized_pnl_pct == pytest.approx(3.333, rel=0.01)

    def test_stop_loss_triggered(self) -> None:
        pos = Position(
            symbol="BTC/USDT",
            exchange="binance",
            entry_price=60000.0,
            amount=0.1,
            current_price=57000.0,
            stop_loss_price=58000.0,
        )
        assert pos.should_stop_loss is True

    def test_stop_loss_not_triggered(self) -> None:
        pos = Position(
            symbol="BTC/USDT",
            exchange="binance",
            entry_price=60000.0,
            amount=0.1,
            current_price=59000.0,
            stop_loss_price=58000.0,
        )
        assert pos.should_stop_loss is False


@pytest.mark.unit
class TestPortfolio:
    def test_total_balance(self) -> None:
        portfolio = Portfolio(
            balance_quote=10000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=60000.0,
                    amount=0.1,
                    current_price=62000.0,
                )
            },
        )
        assert portfolio.total_market_value == 6200.0
        assert portfolio.total_balance == 16200.0

    def test_drawdown(self) -> None:
        portfolio = Portfolio(
            balance_quote=8500.0,
            peak_balance=10000.0,
        )
        assert portfolio.drawdown_pct == 15.0


@pytest.mark.unit
class TestRisk:
    def test_risk_params_defaults(self) -> None:
        params = RiskParams()
        assert params.max_position_size_pct == 10.0
        assert params.max_drawdown_pct == 15.0

    def test_risk_check_approved(self) -> None:
        result = RiskCheckResult(
            verdict=RiskVerdict.APPROVED,
            approved_amount=0.1,
        )
        assert result.is_approved is True

    def test_risk_check_rejected(self) -> None:
        result = RiskCheckResult(
            verdict=RiskVerdict.REJECTED,
            approved_amount=0.0,
            reasons=["Exceeds position limit"],
        )
        assert result.is_approved is False
