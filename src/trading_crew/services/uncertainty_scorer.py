"""Uncertainty scorer — pure deterministic computation, zero LLM cost.

Computes a [0, 1] uncertainty score from market regime, sentiment, strategy
disagreement, drawdown proximity, and regime-change detection.  The score
determines whether the advisory crew should be activated for the current cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis
    from trading_crew.models.portfolio import Portfolio
    from trading_crew.models.risk import RiskParams
    from trading_crew.models.signal import StrategyVote
    from trading_crew.services.sentiment_service import SentimentSnapshot


@dataclass(frozen=True)
class UncertaintyFactor:
    """One contributing factor to the uncertainty score."""

    name: str
    raw_value: float
    weighted_contribution: float


@dataclass(frozen=True)
class UncertaintyResult:
    """Output of the uncertainty scorer."""

    score: float
    factors: list[UncertaintyFactor]
    recommend_advisory: bool


@dataclass(frozen=True)
class UncertaintyWeights:
    """Configurable weights for each uncertainty factor.

    Weights intentionally sum to >1.0 (currently 1.5).  This creates a
    saturation effect: when multiple factors fire simultaneously the score
    approaches 1.0 more aggressively, making advisory activation more
    likely during multi-factor uncertainty.  Individual factors are computed
    as ``raw_value * weight`` and the final score is clamped to [0.0, 1.0].
    """

    volatile_regime: float = 0.3
    sentiment_extreme: float = 0.2
    low_sentiment_confidence: float = 0.2
    strategy_disagreement: float = 0.3
    drawdown_proximity: float = 0.2
    regime_change: float = 0.3


class UncertaintyScorer:
    """Computes a market uncertainty score from deterministic pipeline output.

    Args:
        weights: Configurable per-factor weights.
        activation_threshold: Score at or above which advisory is recommended.
    """

    def __init__(
        self,
        weights: UncertaintyWeights | None = None,
        activation_threshold: float = 0.6,
    ) -> None:
        self._w = weights or UncertaintyWeights()
        self._threshold = max(0.0, min(1.0, activation_threshold))

    def update_threshold(self, threshold: float) -> None:
        """Update the activation threshold without recreating the scorer.

        Called each cycle after re-reading settings from disk so that
        dashboard changes take effect immediately without a bot restart.
        """
        self._threshold = max(0.0, min(1.0, threshold))

    def score(
        self,
        analyses: dict[str, MarketAnalysis],
        votes: dict[str, list[StrategyVote]],
        portfolio: Portfolio,
        risk_params: RiskParams,
        sentiment: SentimentSnapshot | None = None,
        previous_regimes: dict[str, str] | None = None,
    ) -> UncertaintyResult:
        """Compute the uncertainty score for the current cycle.

        All inputs come from the deterministic pipeline — no LLM calls.
        """
        factors: list[UncertaintyFactor] = []

        factors.append(self._volatile_regime(analyses))
        factors.append(self._sentiment_extreme(sentiment))
        factors.append(self._low_sentiment_confidence(sentiment))
        factors.append(self._strategy_disagreement(votes))
        factors.append(self._drawdown_proximity(portfolio, risk_params))
        factors.append(self._regime_change(analyses, previous_regimes))

        raw_score = max(0.0, min(1.0, sum(f.weighted_contribution for f in factors)))
        return UncertaintyResult(
            score=raw_score,
            factors=factors,
            recommend_advisory=raw_score >= self._threshold,
        )

    def _volatile_regime(self, analyses: dict[str, MarketAnalysis]) -> UncertaintyFactor:
        if not analyses:
            return UncertaintyFactor("volatile_regime", 0.0, 0.0)
        volatile_count = sum(1 for a in analyses.values() if a.metadata.market_regime == "volatile")
        raw = volatile_count / len(analyses)
        return UncertaintyFactor("volatile_regime", raw, raw * self._w.volatile_regime)

    def _sentiment_extreme(self, sentiment: SentimentSnapshot | None) -> UncertaintyFactor:
        if sentiment is None or sentiment.confidence == 0.0:
            return UncertaintyFactor("sentiment_extreme", 0.0, 0.0)
        raw = abs(sentiment.score)
        triggered = 1.0 if raw >= 0.5 else 0.0
        return UncertaintyFactor("sentiment_extreme", raw, triggered * self._w.sentiment_extreme)

    def _low_sentiment_confidence(self, sentiment: SentimentSnapshot | None) -> UncertaintyFactor:
        if sentiment is None:
            return UncertaintyFactor("low_sentiment_confidence", 0.0, 0.0)
        raw = 1.0 - sentiment.confidence
        triggered = 1.0 if raw >= 0.5 else 0.0
        return UncertaintyFactor(
            "low_sentiment_confidence", raw, triggered * self._w.low_sentiment_confidence
        )

    def _strategy_disagreement(self, votes: dict[str, list[StrategyVote]]) -> UncertaintyFactor:
        if not votes:
            return UncertaintyFactor("strategy_disagreement", 0.0, 0.0)

        disagreements: list[float] = []
        for symbol_votes in votes.values():
            if not symbol_votes:
                continue
            buy = sum(
                1
                for v in symbol_votes
                if v.signal is not None and v.signal.signal_type.value == "buy"
            )
            sell = sum(
                1
                for v in symbol_votes
                if v.signal is not None and v.signal.signal_type.value == "sell"
            )
            hold_or_none = len(symbol_votes) - buy - sell
            max_faction = max(buy, sell, hold_or_none)
            disagreement = 1.0 - (max_faction / len(symbol_votes))
            disagreements.append(disagreement)

        raw = sum(disagreements) / len(disagreements) if disagreements else 0.0
        return UncertaintyFactor("strategy_disagreement", raw, raw * self._w.strategy_disagreement)

    def _drawdown_proximity(
        self, portfolio: Portfolio, risk_params: RiskParams
    ) -> UncertaintyFactor:
        if risk_params.max_drawdown_pct <= 0:
            return UncertaintyFactor("drawdown_proximity", 0.0, 0.0)
        raw = min(1.0, portfolio.drawdown_pct / risk_params.max_drawdown_pct)
        return UncertaintyFactor("drawdown_proximity", raw, raw * self._w.drawdown_proximity)

    def _regime_change(
        self,
        analyses: dict[str, MarketAnalysis],
        previous_regimes: dict[str, str] | None,
    ) -> UncertaintyFactor:
        if not previous_regimes or not analyses:
            return UncertaintyFactor("regime_change", 0.0, 0.0)

        changed = 0
        compared = 0
        for symbol, analysis in analyses.items():
            prev = previous_regimes.get(symbol)
            if prev is None:
                continue
            compared += 1
            if analysis.metadata.market_regime != prev:
                changed += 1

        raw = changed / compared if compared > 0 else 0.0
        return UncertaintyFactor("regime_change", raw, raw * self._w.regime_change)
