"""Unit tests for risk management modules."""

from __future__ import annotations

import pytest

from trading_crew.models.portfolio import Portfolio, Position
from trading_crew.models.risk import RiskParams
from trading_crew.risk.position_sizer import calculate_position_size
from trading_crew.risk.stop_loss import atr_based_stop, fixed_percentage_stop
from trading_crew.risk.portfolio_limits import check_concentration_limit, check_exposure_limit
from trading_crew.risk.circuit_breaker import CircuitBreaker


@pytest.mark.unit
class TestPositionSizer:
    def test_basic_position_sizing(self) -> None:
        portfolio = Portfolio(balance_quote=10000.0)
        params = RiskParams(risk_per_trade_pct=2.0, default_stop_loss_pct=3.0)

        size = calculate_position_size(
            portfolio=portfolio,
            entry_price=60000.0,
            stop_loss_price=58200.0,
            risk_params=params,
        )
        assert size > 0
        assert size <= 10000.0

    def test_zero_balance(self) -> None:
        portfolio = Portfolio(balance_quote=0.0)
        params = RiskParams()
        size = calculate_position_size(portfolio, 60000.0, 58000.0, params)
        assert size == 0.0

    def test_respects_max_position_size(self) -> None:
        portfolio = Portfolio(balance_quote=100000.0)
        params = RiskParams(max_position_size_pct=5.0, risk_per_trade_pct=50.0)

        size = calculate_position_size(portfolio, 60000.0, 58000.0, params)
        assert size <= 5000.0


@pytest.mark.unit
class TestStopLoss:
    def test_fixed_percentage_long(self) -> None:
        stop = fixed_percentage_stop(60000.0, 3.0, "long")
        assert stop == 58200.0

    def test_fixed_percentage_short(self) -> None:
        stop = fixed_percentage_stop(60000.0, 3.0, "short")
        assert stop == 61800.0

    def test_atr_based_long(self) -> None:
        stop = atr_based_stop(60000.0, atr_value=500.0, multiplier=2.0, side="long")
        assert stop == 59000.0

    def test_atr_based_short(self) -> None:
        stop = atr_based_stop(60000.0, atr_value=500.0, multiplier=2.0, side="short")
        assert stop == 61000.0


@pytest.mark.unit
class TestPortfolioLimits:
    def test_exposure_within_limit(self) -> None:
        portfolio = Portfolio(balance_quote=10000.0)
        params = RiskParams(max_portfolio_exposure_pct=80.0)
        ok, _ = check_exposure_limit(portfolio, 5000.0, params)
        assert ok is True

    def test_exposure_exceeds_limit(self) -> None:
        portfolio = Portfolio(balance_quote=10000.0)
        params = RiskParams(max_portfolio_exposure_pct=30.0)
        ok, reason = check_exposure_limit(portfolio, 5000.0, params)
        assert ok is False
        assert "exposure" in reason.lower()

    def test_concentration_within_limit(self) -> None:
        portfolio = Portfolio(balance_quote=10000.0)
        params = RiskParams(max_position_size_pct=20.0)
        ok, _ = check_concentration_limit(portfolio, "BTC/USDT", 1500.0, params)
        assert ok is True

    def test_concentration_exceeds_limit(self) -> None:
        portfolio = Portfolio(balance_quote=10000.0)
        params = RiskParams(max_position_size_pct=10.0)
        ok, reason = check_concentration_limit(portfolio, "BTC/USDT", 1500.0, params)
        assert ok is False
        assert "single-asset" in reason.lower()


@pytest.mark.unit
class TestCircuitBreaker:
    def test_not_tripped_initially(self) -> None:
        params = RiskParams(max_drawdown_pct=15.0)
        cb = CircuitBreaker(params)
        assert cb.is_tripped is False

    def test_trips_on_drawdown(self) -> None:
        params = RiskParams(max_drawdown_pct=10.0)
        cb = CircuitBreaker(params)

        portfolio = Portfolio(balance_quote=8500.0, peak_balance=10000.0)
        tripped = cb.check(portfolio)

        assert tripped is True
        assert cb.is_tripped is True
        assert "15.00%" in cb.trip_reason

    def test_stays_tripped(self) -> None:
        params = RiskParams(max_drawdown_pct=10.0)
        cb = CircuitBreaker(params)

        portfolio = Portfolio(balance_quote=8500.0, peak_balance=10000.0)
        cb.check(portfolio)

        healthy_portfolio = Portfolio(balance_quote=10000.0, peak_balance=10000.0)
        assert cb.check(healthy_portfolio) is True

    def test_manual_reset(self) -> None:
        params = RiskParams(max_drawdown_pct=10.0)
        cb = CircuitBreaker(params)

        portfolio = Portfolio(balance_quote=8500.0, peak_balance=10000.0)
        cb.check(portfolio)
        cb.reset()

        assert cb.is_tripped is False
