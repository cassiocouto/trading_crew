"""Unit tests for the StrategyRunner service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trading_crew.models.market import MarketAnalysis, MarketMetadata
from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.strategies.base import BaseStrategy
from trading_crew.strategies.bollinger import BollingerBandsStrategy
from trading_crew.strategies.composite import CompositeStrategy
from trading_crew.strategies.ema_crossover import EMACrossoverStrategy
from trading_crew.strategies.rsi_range import RSIRangeStrategy


def _make_analysis(
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    price: float = 50_000.0,
    **indicators: float,
) -> MarketAnalysis:
    return MarketAnalysis(
        symbol=symbol,
        exchange=exchange,
        timestamp=datetime.now(UTC),
        current_price=price,
        indicators=indicators,
        metadata=MarketMetadata(),
    )


class _AlwaysBuyStrategy(BaseStrategy):
    name = "always_buy"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            confidence=0.9,
            strategy_name=self.name,
            entry_price=analysis.current_price,
            reason="Always buy",
        )


class _AlwaysSellStrategy(BaseStrategy):
    name = "always_sell"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=SignalType.SELL,
            strength=SignalStrength.STRONG,
            confidence=0.8,
            strategy_name=self.name,
            entry_price=analysis.current_price,
            reason="Always sell",
        )


class _NeverSignalStrategy(BaseStrategy):
    name = "never_signal"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return None


class _FailingStrategy(BaseStrategy):
    name = "failing"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        raise RuntimeError("Strategy crashed")


# -- StrategyRunner tests -----------------------------------------------------


class TestStrategyRunnerInit:
    def test_requires_at_least_one_strategy(self) -> None:
        with pytest.raises(ValueError, match=r"(?i)at least one strategy"):
            StrategyRunner(strategies=[])

    def test_strategy_names(self) -> None:
        runner = StrategyRunner(strategies=[_AlwaysBuyStrategy(), _NeverSignalStrategy()])
        assert runner.strategy_names == ["always_buy", "never_signal"]


class TestStrategyRunnerIndividual:
    def test_returns_all_actionable_signals(self) -> None:
        runner = StrategyRunner(
            strategies=[_AlwaysBuyStrategy(), _AlwaysSellStrategy()],
            min_confidence=0.0,
        )
        analyses = {"BTC/USDT": _make_analysis()}
        signals = runner.evaluate(analyses)
        assert len(signals) == 2
        types = {s.signal_type for s in signals}
        assert types == {SignalType.BUY, SignalType.SELL}

    def test_filters_below_min_confidence(self) -> None:
        runner = StrategyRunner(
            strategies=[_AlwaysBuyStrategy()],
            min_confidence=0.95,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 0

    def test_none_signals_ignored(self) -> None:
        runner = StrategyRunner(
            strategies=[_NeverSignalStrategy()],
            min_confidence=0.0,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 0

    def test_failing_strategy_does_not_crash_runner(self) -> None:
        runner = StrategyRunner(
            strategies=[_FailingStrategy(), _AlwaysBuyStrategy()],
            min_confidence=0.0,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 1
        assert signals[0].strategy_name == "always_buy"

    def test_multiple_symbols(self) -> None:
        runner = StrategyRunner(
            strategies=[_AlwaysBuyStrategy()],
            min_confidence=0.0,
        )
        analyses = {
            "BTC/USDT": _make_analysis(symbol="BTC/USDT"),
            "ETH/USDT": _make_analysis(symbol="ETH/USDT", price=3_000.0),
        }
        signals = runner.evaluate(analyses)
        assert len(signals) == 2
        symbols = {s.symbol for s in signals}
        assert symbols == {"BTC/USDT", "ETH/USDT"}


class TestStrategyRunnerEnsemble:
    def test_consensus_buy_majority(self) -> None:
        runner = StrategyRunner(
            strategies=[_AlwaysBuyStrategy(), _AlwaysBuyStrategy(), _NeverSignalStrategy()],
            min_confidence=0.0,
            ensemble=True,
            ensemble_agreement_threshold=0.5,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert signals[0].strategy_name == "ensemble"

    def test_consensus_sell_majority(self) -> None:
        runner = StrategyRunner(
            strategies=[_AlwaysSellStrategy(), _AlwaysSellStrategy(), _NeverSignalStrategy()],
            min_confidence=0.0,
            ensemble=True,
            ensemble_agreement_threshold=0.5,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL

    def test_no_consensus_when_split(self) -> None:
        runner = StrategyRunner(
            strategies=[_AlwaysBuyStrategy(), _AlwaysSellStrategy(), _NeverSignalStrategy()],
            min_confidence=0.0,
            ensemble=True,
            ensemble_agreement_threshold=0.67,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 0

    def test_ensemble_below_min_confidence(self) -> None:
        class _LowConfidenceBuy(BaseStrategy):
            name = "low_confidence"

            def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
                return TradeSignal(
                    symbol=analysis.symbol,
                    exchange=analysis.exchange,
                    signal_type=SignalType.BUY,
                    strength=SignalStrength.WEAK,
                    confidence=0.3,
                    strategy_name=self.name,
                    entry_price=analysis.current_price,
                    reason="Low confidence buy",
                )

        runner = StrategyRunner(
            strategies=[_LowConfidenceBuy()],
            min_confidence=0.5,
            ensemble=True,
            ensemble_agreement_threshold=0.5,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 0

    def test_ensemble_with_failing_strategy(self) -> None:
        runner = StrategyRunner(
            strategies=[_AlwaysBuyStrategy(), _FailingStrategy()],
            min_confidence=0.0,
            ensemble=True,
            ensemble_agreement_threshold=0.5,
        )
        signals = runner.evaluate({"BTC/USDT": _make_analysis()})
        assert len(signals) == 1


class TestStrategyRunnerRealStrategies:
    """Test with actual built-in strategies against realistic indicator data."""

    def test_ema_crossover_buy_signal(self) -> None:
        analysis = _make_analysis(
            price=52_000.0,
            ema_fast=51_000.0,
            ema_slow=49_000.0,
        )
        runner = StrategyRunner(
            strategies=[EMACrossoverStrategy()],
            min_confidence=0.0,
        )
        signals = runner.evaluate({"BTC/USDT": analysis})
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY

    def test_bollinger_buy_signal(self) -> None:
        analysis = _make_analysis(
            price=48_000.0,
            bb_upper=52_000.0,
            bb_middle=50_000.0,
            bb_lower=48_100.0,
        )
        runner = StrategyRunner(
            strategies=[BollingerBandsStrategy()],
            min_confidence=0.0,
        )
        signals = runner.evaluate({"BTC/USDT": analysis})
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY

    def test_rsi_range_buy_signal(self) -> None:
        analysis = _make_analysis(
            price=45_000.0,
            rsi_14=25.0,
            range_low=44_000.0,
            range_high=55_000.0,
        )
        runner = StrategyRunner(
            strategies=[RSIRangeStrategy()],
            min_confidence=0.0,
        )
        signals = runner.evaluate({"BTC/USDT": analysis})
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY


# -- CompositeStrategy tests --------------------------------------------------


class TestCompositeStrategy:
    def test_requires_at_least_one_strategy(self) -> None:
        with pytest.raises(ValueError, match="at least one child strategy"):
            CompositeStrategy(strategies=[])

    def test_consensus_buy(self) -> None:
        composite = CompositeStrategy(
            strategies=[_AlwaysBuyStrategy(), _AlwaysBuyStrategy()],
            agreement_threshold=0.5,
            min_confidence=0.0,
        )
        signal = composite.generate_signal(_make_analysis())
        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.strategy_name == "composite"

    def test_no_consensus(self) -> None:
        composite = CompositeStrategy(
            strategies=[_AlwaysBuyStrategy(), _AlwaysSellStrategy(), _NeverSignalStrategy()],
            agreement_threshold=0.67,
            min_confidence=0.0,
        )
        signal = composite.generate_signal(_make_analysis())
        assert signal is None

    def test_sell_consensus(self) -> None:
        composite = CompositeStrategy(
            strategies=[_AlwaysSellStrategy(), _AlwaysSellStrategy()],
            agreement_threshold=0.5,
            min_confidence=0.0,
        )
        signal = composite.generate_signal(_make_analysis())
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
