"""Tests for StrategyEvaluation vote breakdown preservation."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_crew.models.market import MarketAnalysis, MarketMetadata
from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.strategies.base import BaseStrategy


def _make_analysis(symbol: str = "BTC/USDT", price: float = 50_000.0) -> MarketAnalysis:
    return MarketAnalysis(
        symbol=symbol,
        exchange="binance",
        timestamp=datetime.now(UTC),
        current_price=price,
        indicators={},
        metadata=MarketMetadata(),
    )


class _BuyStrategy(BaseStrategy):
    name = "buy_strat"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            confidence=0.9,
            strategy_name=self.name,
            entry_price=analysis.current_price,
        )


class _SellStrategy(BaseStrategy):
    name = "sell_strat"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=SignalType.SELL,
            strength=SignalStrength.MODERATE,
            confidence=0.7,
            strategy_name=self.name,
            entry_price=analysis.current_price,
        )


class _NoneStrategy(BaseStrategy):
    name = "none_strat"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return None


class _HoldStrategy(BaseStrategy):
    name = "hold_strat"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=SignalType.HOLD,
            strength=SignalStrength.WEAK,
            confidence=0.5,
            strategy_name=self.name,
            entry_price=analysis.current_price,
        )


class _LowConfStrategy(BaseStrategy):
    name = "lowconf_strat"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=SignalType.BUY,
            strength=SignalStrength.WEAK,
            confidence=0.3,
            strategy_name=self.name,
            entry_price=analysis.current_price,
        )


class _ErrorStrategy(BaseStrategy):
    name = "error_strat"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        raise RuntimeError("boom")


class TestVoteBreakdown:
    def test_all_strategies_recorded_in_votes(self) -> None:
        runner = StrategyRunner(
            strategies=[_BuyStrategy(), _SellStrategy(), _NoneStrategy()],
            min_confidence=0.0,
        )
        evaluation = runner.evaluate({"BTC/USDT": _make_analysis()})
        votes = evaluation.votes["BTC/USDT"]
        assert len(votes) == 3
        names = {v.strategy_name for v in votes}
        assert names == {"buy_strat", "sell_strat", "none_strat"}

    def test_none_signal_recorded_with_filtered_reason(self) -> None:
        runner = StrategyRunner(strategies=[_NoneStrategy()], min_confidence=0.0)
        evaluation = runner.evaluate({"BTC/USDT": _make_analysis()})
        vote = evaluation.votes["BTC/USDT"][0]
        assert vote.signal is None
        assert vote.filtered_reason == "none"

    def test_hold_signal_recorded_with_filtered_reason(self) -> None:
        runner = StrategyRunner(strategies=[_HoldStrategy()], min_confidence=0.0)
        evaluation = runner.evaluate({"BTC/USDT": _make_analysis()})
        vote = evaluation.votes["BTC/USDT"][0]
        assert vote.signal is not None
        assert vote.filtered_reason == "hold"

    def test_below_confidence_recorded(self) -> None:
        runner = StrategyRunner(strategies=[_LowConfStrategy()], min_confidence=0.5)
        evaluation = runner.evaluate({"BTC/USDT": _make_analysis()})
        vote = evaluation.votes["BTC/USDT"][0]
        assert vote.signal is not None
        assert vote.filtered_reason == "below_min_confidence"
        assert len(evaluation.signals) == 0

    def test_error_strategy_recorded(self) -> None:
        runner = StrategyRunner(strategies=[_ErrorStrategy(), _BuyStrategy()], min_confidence=0.0)
        evaluation = runner.evaluate({"BTC/USDT": _make_analysis()})
        votes = evaluation.votes["BTC/USDT"]
        error_vote = next(v for v in votes if v.strategy_name == "error_strat")
        assert error_vote.signal is None
        assert error_vote.filtered_reason == "error"
        assert len(evaluation.signals) == 1

    def test_actionable_vote_has_no_filtered_reason(self) -> None:
        runner = StrategyRunner(strategies=[_BuyStrategy()], min_confidence=0.0)
        evaluation = runner.evaluate({"BTC/USDT": _make_analysis()})
        vote = evaluation.votes["BTC/USDT"][0]
        assert vote.signal is not None
        assert vote.filtered_reason is None

    def test_multiple_symbols_have_separate_vote_lists(self) -> None:
        runner = StrategyRunner(strategies=[_BuyStrategy()], min_confidence=0.0)
        analyses = {
            "BTC/USDT": _make_analysis("BTC/USDT"),
            "ETH/USDT": _make_analysis("ETH/USDT", price=3000.0),
        }
        evaluation = runner.evaluate(analyses)
        assert "BTC/USDT" in evaluation.votes
        assert "ETH/USDT" in evaluation.votes
        assert len(evaluation.votes["BTC/USDT"]) == 1
        assert len(evaluation.votes["ETH/USDT"]) == 1

    def test_ensemble_mode_preserves_votes(self) -> None:
        runner = StrategyRunner(
            strategies=[_BuyStrategy(), _BuyStrategy(), _NoneStrategy()],
            min_confidence=0.0,
            ensemble=True,
            ensemble_agreement_threshold=0.5,
        )
        evaluation = runner.evaluate({"BTC/USDT": _make_analysis()})
        votes = evaluation.votes["BTC/USDT"]
        assert len(votes) == 3
        none_votes = [v for v in votes if v.filtered_reason == "none"]
        assert len(none_votes) == 1
