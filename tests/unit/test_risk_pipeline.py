"""Unit tests for the RiskPipeline service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trading_crew.models.market import MarketAnalysis, MarketMetadata
from trading_crew.models.order import OrderSide, OrderType
from trading_crew.models.portfolio import Portfolio, Position
from trading_crew.models.risk import RiskParams, RiskVerdict
from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.risk.circuit_breaker import CircuitBreaker
from trading_crew.services.risk_pipeline import RiskPipeline


def _make_signal(
    symbol: str = "BTC/USDT",
    signal_type: SignalType = SignalType.BUY,
    confidence: float = 0.8,
    entry_price: float = 50_000.0,
    stop_loss_price: float | None = None,
) -> TradeSignal:
    return TradeSignal(
        symbol=symbol,
        exchange="binance",
        signal_type=signal_type,
        strength=SignalStrength.STRONG,
        confidence=confidence,
        strategy_name="test_strategy",
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        reason="Test signal",
    )


def _make_portfolio(
    balance: float = 10_000.0,
    peak: float = 10_000.0,
    positions: dict[str, Position] | None = None,
) -> Portfolio:
    return Portfolio(
        balance_quote=balance,
        peak_balance=peak,
        positions=positions or {},
    )


def _make_analysis(
    symbol: str = "BTC/USDT",
    price: float = 50_000.0,
    **indicators: float,
) -> MarketAnalysis:
    return MarketAnalysis(
        symbol=symbol,
        exchange="binance",
        timestamp=datetime.now(UTC),
        current_price=price,
        indicators=indicators,
        metadata=MarketMetadata(),
    )


def _make_pipeline(
    risk_params: RiskParams | None = None,
    stop_loss_method: str = "fixed",
    atr_stop_multiplier: float = 2.0,
) -> RiskPipeline:
    params = risk_params or RiskParams()
    breaker = CircuitBreaker(params)
    return RiskPipeline(
        risk_params=params,
        circuit_breaker=breaker,
        stop_loss_method=stop_loss_method,
        atr_stop_multiplier=atr_stop_multiplier,
    )


# -- Basic approval flow ------------------------------------------------------


class TestRiskPipelineApproval:
    def test_approved_signal(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal()
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)

        assert result.is_approved
        assert result.approved_amount > 0
        assert result.stop_loss_price is not None
        assert "circuit_breaker" in result.checks_passed
        assert "min_confidence" in result.checks_passed
        assert "position_sizing" in result.checks_passed

    def test_approved_sell_signal(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(signal_type=SignalType.SELL)
        portfolio = _make_portfolio(
            balance=100_000.0,
            peak=100_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=1.0,
                    current_price=50_000.0,
                ),
            },
        )

        result = pipeline.evaluate(signal, portfolio)
        assert result.is_approved

    def test_stop_loss_set_for_buy(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(entry_price=50_000.0)
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)
        assert result.stop_loss_price is not None
        assert result.stop_loss_price < signal.entry_price

    def test_stop_loss_set_for_sell(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(signal_type=SignalType.SELL, entry_price=50_000.0)
        portfolio = _make_portfolio(
            balance=100_000.0,
            peak=100_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=1.0,
                    current_price=50_000.0,
                ),
            },
        )

        result = pipeline.evaluate(signal, portfolio)
        assert result.stop_loss_price is not None
        assert result.stop_loss_price > signal.entry_price


# -- Rejection scenarios -------------------------------------------------------


class TestRiskPipelineRejections:
    def test_rejected_below_min_confidence(self) -> None:
        params = RiskParams(min_confidence=0.9)
        pipeline = _make_pipeline(risk_params=params)
        signal = _make_signal(confidence=0.5)
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)
        assert result.verdict == RiskVerdict.REJECTED
        assert "min_confidence" in result.checks_failed

    def test_rejected_zero_balance(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal()
        portfolio = _make_portfolio(balance=0.0, peak=0.0)

        result = pipeline.evaluate(signal, portfolio)
        assert result.verdict == RiskVerdict.REJECTED
        assert "position_sizing" in result.checks_failed

    def test_rejected_exposure_limit(self) -> None:
        params = RiskParams(max_portfolio_exposure_pct=5.0)
        pipeline = _make_pipeline(risk_params=params)
        signal = _make_signal()
        portfolio = _make_portfolio(
            balance=10_000.0,
            positions={
                "ETH/USDT": Position(
                    symbol="ETH/USDT",
                    exchange="binance",
                    entry_price=3_000.0,
                    amount=2.0,
                    current_price=3_000.0,
                ),
            },
        )

        result = pipeline.evaluate(signal, portfolio)
        assert result.verdict == RiskVerdict.REJECTED
        assert "exposure_limit" in result.checks_failed

    def test_rejected_concentration_limit(self) -> None:
        params = RiskParams(max_position_size_pct=0.5)
        pipeline = _make_pipeline(risk_params=params)
        signal = _make_signal()
        portfolio = _make_portfolio(
            balance=10_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=0.001,
                    current_price=50_000.0,
                ),
            },
        )

        result = pipeline.evaluate(signal, portfolio)
        assert result.verdict == RiskVerdict.REJECTED
        assert "concentration_limit" in result.checks_failed


# -- Circuit breaker -----------------------------------------------------------


class TestRiskPipelineCircuitBreaker:
    def test_circuit_break_on_drawdown(self) -> None:
        params = RiskParams(max_drawdown_pct=5.0)
        pipeline = _make_pipeline(risk_params=params)
        signal = _make_signal()
        portfolio = _make_portfolio(balance=8_000.0, peak=10_000.0)

        result = pipeline.evaluate(signal, portfolio)
        assert result.verdict == RiskVerdict.CIRCUIT_BREAK
        assert "circuit_breaker" in result.checks_failed


# -- Stop-loss methods ---------------------------------------------------------


class TestRiskPipelineStopLoss:
    def test_fixed_stop_loss_default(self) -> None:
        params = RiskParams(default_stop_loss_pct=5.0)
        pipeline = _make_pipeline(risk_params=params, stop_loss_method="fixed")
        signal = _make_signal(entry_price=10_000.0)
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)
        assert result.stop_loss_price is not None
        assert result.stop_loss_price == pytest.approx(9_500.0)

    def test_atr_stop_loss(self) -> None:
        pipeline = _make_pipeline(stop_loss_method="atr", atr_stop_multiplier=2.0)
        signal = _make_signal(entry_price=50_000.0)
        portfolio = _make_portfolio()
        analysis = _make_analysis(atr_14=1_000.0)

        result = pipeline.evaluate(signal, portfolio, analysis)
        assert result.stop_loss_price is not None
        assert result.stop_loss_price == pytest.approx(48_000.0)

    def test_atr_falls_back_to_fixed_when_no_atr(self) -> None:
        params = RiskParams(default_stop_loss_pct=3.0)
        pipeline = _make_pipeline(
            risk_params=params, stop_loss_method="atr", atr_stop_multiplier=2.0
        )
        signal = _make_signal(entry_price=50_000.0)
        portfolio = _make_portfolio()
        analysis = _make_analysis()

        result = pipeline.evaluate(signal, portfolio, analysis)
        assert result.stop_loss_price is not None
        assert result.stop_loss_price == pytest.approx(48_500.0)

    def test_signal_provided_stop_loss_preserved(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(entry_price=50_000.0, stop_loss_price=47_000.0)
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)
        assert result.stop_loss_price == pytest.approx(47_000.0)


# -- Order request generation -------------------------------------------------


class TestRiskPipelineOrderRequest:
    def test_approved_generates_order_request(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal()
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)
        order_req = RiskPipeline.to_order_request(signal, result)

        assert order_req is not None
        assert order_req.symbol == "BTC/USDT"
        assert order_req.side == OrderSide.BUY
        assert order_req.order_type == OrderType.MARKET
        assert order_req.amount > 0
        assert order_req.strategy_name == "test_strategy"
        assert order_req.signal_confidence == 0.8

    def test_sell_signal_generates_sell_order(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(signal_type=SignalType.SELL)
        portfolio = _make_portfolio(
            balance=100_000.0,
            peak=100_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=1.0,
                    current_price=50_000.0,
                ),
            },
        )

        result = pipeline.evaluate(signal, portfolio)
        order_req = RiskPipeline.to_order_request(signal, result)

        assert order_req is not None
        assert order_req.side == OrderSide.SELL

    def test_rejected_signal_no_order_request(self) -> None:
        params = RiskParams(min_confidence=0.99)
        pipeline = _make_pipeline(risk_params=params)
        signal = _make_signal(confidence=0.5)
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)
        order_req = RiskPipeline.to_order_request(signal, result)

        assert order_req is None

    def test_circuit_break_no_order_request(self) -> None:
        params = RiskParams(max_drawdown_pct=1.0)
        pipeline = _make_pipeline(risk_params=params)
        signal = _make_signal()
        portfolio = _make_portfolio(balance=5_000.0, peak=10_000.0)

        result = pipeline.evaluate(signal, portfolio)
        order_req = RiskPipeline.to_order_request(signal, result)

        assert order_req is None


# -- Inventory check (SELL without holdings) ----------------------------------


class TestRiskPipelineInventory:
    def test_sell_rejected_when_no_position(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(signal_type=SignalType.SELL)
        portfolio = _make_portfolio()

        result = pipeline.evaluate(signal, portfolio)
        assert result.verdict == RiskVerdict.REJECTED
        assert "inventory" in result.checks_failed
        assert "short selling" in result.reasons[0].lower()

    def test_sell_rejected_when_different_symbol_held(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(symbol="BTC/USDT", signal_type=SignalType.SELL)
        portfolio = _make_portfolio(
            positions={
                "ETH/USDT": Position(
                    symbol="ETH/USDT",
                    exchange="binance",
                    entry_price=3_000.0,
                    amount=1.0,
                    current_price=3_000.0,
                ),
            },
        )

        result = pipeline.evaluate(signal, portfolio)
        assert result.verdict == RiskVerdict.REJECTED
        assert "inventory" in result.checks_failed

    def test_sell_approved_when_position_exists(self) -> None:
        pipeline = _make_pipeline()
        signal = _make_signal(signal_type=SignalType.SELL)
        portfolio = _make_portfolio(
            balance=100_000.0,
            peak=100_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=1.0,
                    current_price=50_000.0,
                ),
            },
        )

        result = pipeline.evaluate(signal, portfolio)
        assert result.is_approved
        assert "inventory" in result.checks_passed
