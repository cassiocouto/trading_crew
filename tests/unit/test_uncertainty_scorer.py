"""Unit tests for the UncertaintyScorer service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trading_crew.models.market import MarketAnalysis, MarketMetadata
from trading_crew.models.portfolio import Portfolio
from trading_crew.models.risk import RiskParams
from trading_crew.models.signal import (
    SignalStrength,
    SignalType,
    StrategyVote,
    TradeSignal,
)
from trading_crew.services.sentiment_service import SentimentSnapshot
from trading_crew.services.uncertainty_scorer import (
    UncertaintyScorer,
    UncertaintyWeights,
)


def _analysis(symbol: str = "BTC/USDT", regime: str = "ranging") -> MarketAnalysis:
    return MarketAnalysis(
        symbol=symbol,
        exchange="binance",
        timestamp=datetime.now(UTC),
        current_price=50_000.0,
        indicators={"atr_14": 1500.0},
        metadata=MarketMetadata(market_regime=regime),
    )


def _signal(symbol: str = "BTC/USDT", direction: str = "buy") -> TradeSignal:
    return TradeSignal(
        symbol=symbol,
        exchange="binance",
        signal_type=SignalType(direction),
        strength=SignalStrength.MODERATE,
        confidence=0.7,
        strategy_name="test",
        entry_price=50_000.0,
    )


def _portfolio(balance: float = 10_000.0, peak: float = 10_000.0) -> Portfolio:
    return Portfolio(balance_quote=balance, peak_balance=peak)


def _risk_params(max_dd: float = 15.0) -> RiskParams:
    return RiskParams(max_drawdown_pct=max_dd)


class TestVolatileRegime:
    def test_no_analyses_yields_zero(self) -> None:
        scorer = UncertaintyScorer()
        result = scorer.score({}, {}, _portfolio(), _risk_params())
        factor = next(f for f in result.factors if f.name == "volatile_regime")
        assert factor.weighted_contribution == 0.0

    def test_all_volatile_yields_full_weight(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(volatile_regime=0.3))
        analyses = {"BTC/USDT": _analysis(regime="volatile")}
        result = scorer.score(analyses, {}, _portfolio(), _risk_params())
        factor = next(f for f in result.factors if f.name == "volatile_regime")
        assert factor.raw_value == 1.0
        assert factor.weighted_contribution == pytest.approx(0.3)

    def test_partial_volatile(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(volatile_regime=0.3))
        analyses = {
            "BTC/USDT": _analysis("BTC/USDT", regime="volatile"),
            "ETH/USDT": _analysis("ETH/USDT", regime="ranging"),
        }
        result = scorer.score(analyses, {}, _portfolio(), _risk_params())
        factor = next(f for f in result.factors if f.name == "volatile_regime")
        assert factor.raw_value == pytest.approx(0.5)
        assert factor.weighted_contribution == pytest.approx(0.15)


class TestSentiment:
    def test_no_sentiment_yields_zero(self) -> None:
        scorer = UncertaintyScorer()
        result = scorer.score({}, {}, _portfolio(), _risk_params(), sentiment=None)
        extreme = next(f for f in result.factors if f.name == "sentiment_extreme")
        low_conf = next(f for f in result.factors if f.name == "low_sentiment_confidence")
        assert extreme.weighted_contribution == 0.0
        assert low_conf.weighted_contribution == 0.0

    def test_extreme_sentiment_triggers(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(sentiment_extreme=0.2))
        sentiment = SentimentSnapshot(score=-0.8, confidence=0.9, sources=[])
        result = scorer.score({}, {}, _portfolio(), _risk_params(), sentiment=sentiment)
        factor = next(f for f in result.factors if f.name == "sentiment_extreme")
        assert factor.raw_value == pytest.approx(0.8)
        assert factor.weighted_contribution == pytest.approx(0.2)

    def test_mild_sentiment_does_not_trigger(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(sentiment_extreme=0.2))
        sentiment = SentimentSnapshot(score=0.2, confidence=0.9, sources=[])
        result = scorer.score({}, {}, _portfolio(), _risk_params(), sentiment=sentiment)
        factor = next(f for f in result.factors if f.name == "sentiment_extreme")
        assert factor.weighted_contribution == 0.0

    def test_low_confidence_triggers(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(low_sentiment_confidence=0.2))
        sentiment = SentimentSnapshot(score=0.0, confidence=0.3, sources=[])
        result = scorer.score({}, {}, _portfolio(), _risk_params(), sentiment=sentiment)
        factor = next(f for f in result.factors if f.name == "low_sentiment_confidence")
        assert factor.weighted_contribution == pytest.approx(0.2)


class TestStrategyDisagreement:
    def test_no_votes_yields_zero(self) -> None:
        scorer = UncertaintyScorer()
        result = scorer.score({}, {}, _portfolio(), _risk_params())
        factor = next(f for f in result.factors if f.name == "strategy_disagreement")
        assert factor.weighted_contribution == 0.0

    def test_full_agreement_yields_zero(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(strategy_disagreement=0.3))
        votes = {
            "BTC/USDT": [
                StrategyVote("s1", "BTC/USDT", _signal(direction="buy")),
                StrategyVote("s2", "BTC/USDT", _signal(direction="buy")),
                StrategyVote("s3", "BTC/USDT", _signal(direction="buy")),
            ]
        }
        result = scorer.score({}, votes, _portfolio(), _risk_params())
        factor = next(f for f in result.factors if f.name == "strategy_disagreement")
        assert factor.raw_value == pytest.approx(0.0)

    def test_split_disagreement(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(strategy_disagreement=0.3))
        votes = {
            "BTC/USDT": [
                StrategyVote("s1", "BTC/USDT", _signal(direction="buy")),
                StrategyVote("s2", "BTC/USDT", _signal(direction="sell")),
                StrategyVote("s3", "BTC/USDT", None, filtered_reason="none"),
            ]
        }
        result = scorer.score({}, votes, _portfolio(), _risk_params())
        factor = next(f for f in result.factors if f.name == "strategy_disagreement")
        # max_faction = 1 (each has 1), disagreement = 1 - 1/3 = 0.667
        assert factor.raw_value == pytest.approx(2 / 3)


class TestDrawdownProximity:
    def test_no_drawdown(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(drawdown_proximity=0.2))
        result = scorer.score({}, {}, _portfolio(10_000, 10_000), _risk_params(15.0))
        factor = next(f for f in result.factors if f.name == "drawdown_proximity")
        assert factor.raw_value == pytest.approx(0.0)

    def test_at_half_drawdown_limit(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(drawdown_proximity=0.2))
        # peak=10000, balance=9250 -> drawdown = 7.5%, limit = 15% -> proximity = 0.5
        result = scorer.score({}, {}, _portfolio(9_250, 10_000), _risk_params(15.0))
        factor = next(f for f in result.factors if f.name == "drawdown_proximity")
        assert factor.raw_value == pytest.approx(0.5)
        assert factor.weighted_contribution == pytest.approx(0.1)


class TestRegimeChange:
    def test_no_previous_regimes(self) -> None:
        scorer = UncertaintyScorer()
        result = scorer.score(
            {"BTC/USDT": _analysis(regime="volatile")},
            {},
            _portfolio(),
            _risk_params(),
            previous_regimes=None,
        )
        factor = next(f for f in result.factors if f.name == "regime_change")
        assert factor.weighted_contribution == 0.0

    def test_regime_changed(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(regime_change=0.3))
        result = scorer.score(
            {"BTC/USDT": _analysis(regime="volatile")},
            {},
            _portfolio(),
            _risk_params(),
            previous_regimes={"BTC/USDT": "ranging"},
        )
        factor = next(f for f in result.factors if f.name == "regime_change")
        assert factor.raw_value == 1.0
        assert factor.weighted_contribution == pytest.approx(0.3)

    def test_regime_unchanged(self) -> None:
        scorer = UncertaintyScorer(weights=UncertaintyWeights(regime_change=0.3))
        result = scorer.score(
            {"BTC/USDT": _analysis(regime="ranging")},
            {},
            _portfolio(),
            _risk_params(),
            previous_regimes={"BTC/USDT": "ranging"},
        )
        factor = next(f for f in result.factors if f.name == "regime_change")
        assert factor.raw_value == 0.0


class TestScoreCombined:
    def test_score_capped_at_one(self) -> None:
        weights = UncertaintyWeights(
            volatile_regime=1.0,
            sentiment_extreme=1.0,
            low_sentiment_confidence=1.0,
            strategy_disagreement=1.0,
            drawdown_proximity=1.0,
            regime_change=1.0,
        )
        scorer = UncertaintyScorer(weights=weights, activation_threshold=0.5)
        analyses = {"BTC/USDT": _analysis(regime="volatile")}
        sentiment = SentimentSnapshot(score=-0.9, confidence=0.2, sources=[])
        votes = {
            "BTC/USDT": [
                StrategyVote("s1", "BTC/USDT", _signal(direction="buy")),
                StrategyVote("s2", "BTC/USDT", _signal(direction="sell")),
            ]
        }
        result = scorer.score(
            analyses,
            votes,
            _portfolio(8_500, 10_000),
            _risk_params(15.0),
            sentiment=sentiment,
            previous_regimes={"BTC/USDT": "ranging"},
        )
        assert result.score == 1.0
        assert result.recommend_advisory is True

    def test_threshold_gating(self) -> None:
        scorer = UncertaintyScorer(
            weights=UncertaintyWeights(
                volatile_regime=0.0,
                sentiment_extreme=0.0,
                low_sentiment_confidence=0.0,
                strategy_disagreement=0.0,
                drawdown_proximity=0.0,
                regime_change=0.0,
            ),
            activation_threshold=0.6,
        )
        result = scorer.score({}, {}, _portfolio(), _risk_params())
        assert result.score == 0.0
        assert result.recommend_advisory is False

    def test_exactly_at_threshold(self) -> None:
        scorer = UncertaintyScorer(
            weights=UncertaintyWeights(volatile_regime=0.6),
            activation_threshold=0.6,
        )
        analyses = {"BTC/USDT": _analysis(regime="volatile")}
        result = scorer.score(analyses, {}, _portfolio(), _risk_params())
        assert result.score == pytest.approx(0.6)
        assert result.recommend_advisory is True
