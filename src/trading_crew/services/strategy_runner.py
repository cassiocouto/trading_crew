"""Deterministic strategy execution engine for Phase 3.

Runs registered strategies against MarketAnalysis data and aggregates
signals. Supports two modes:
  - Individual: every strategy produces independent signals
  - Ensemble: strategies vote per symbol, producing one consensus signal
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis
    from trading_crew.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyRunner:
    """Orchestrates strategy evaluation against market analyses.

    Args:
        strategies: List of strategy instances to run.
        min_confidence: Minimum confidence threshold for actionable signals.
        ensemble: If True, aggregate signals per symbol via weighted voting.
        ensemble_agreement_threshold: Fraction of strategies that must agree
            for an ensemble signal (e.g. 0.5 = majority).
    """

    def __init__(
        self,
        strategies: list[BaseStrategy],
        min_confidence: float = 0.5,
        ensemble: bool = False,
        ensemble_agreement_threshold: float = 0.5,
    ) -> None:
        if not strategies:
            raise ValueError("At least one strategy is required")
        self._strategies = strategies
        self._min_confidence = min_confidence
        self._ensemble = ensemble
        self._ensemble_threshold = max(0.0, min(1.0, ensemble_agreement_threshold))

    @property
    def strategy_names(self) -> list[str]:
        return [s.name for s in self._strategies]

    def evaluate(self, analyses: dict[str, MarketAnalysis]) -> list[TradeSignal]:
        """Run all strategies against the provided analyses.

        Returns:
            List of actionable signals that meet the minimum confidence threshold.
        """
        if self._ensemble:
            return self._evaluate_ensemble(analyses)
        return self._evaluate_individual(analyses)

    def _evaluate_individual(self, analyses: dict[str, MarketAnalysis]) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        for symbol, analysis in analyses.items():
            for strategy in self._strategies:
                try:
                    signal = strategy.generate_signal(analysis)
                except Exception:
                    logger.exception("Strategy %s failed for %s", strategy.name, symbol)
                    continue

                if signal is None:
                    continue
                if not signal.is_actionable:
                    continue
                if signal.confidence < self._min_confidence:
                    logger.debug(
                        "Signal from %s for %s below min confidence (%.2f < %.2f)",
                        strategy.name,
                        symbol,
                        signal.confidence,
                        self._min_confidence,
                    )
                    continue
                signals.append(signal)
                logger.info(
                    "Signal: %s %s %s (confidence=%.2f, strategy=%s)",
                    signal.signal_type.value,
                    signal.symbol,
                    signal.strength.value,
                    signal.confidence,
                    signal.strategy_name,
                )
        return signals

    def _evaluate_ensemble(self, analyses: dict[str, MarketAnalysis]) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        for _symbol, analysis in analyses.items():
            consensus = self._vote(analysis)
            if consensus is not None:
                signals.append(consensus)
        return signals

    def _vote(self, analysis: MarketAnalysis) -> TradeSignal | None:
        """Aggregate strategy signals for a single symbol via weighted voting."""
        raw_signals: list[TradeSignal] = []
        for strategy in self._strategies:
            try:
                signal = strategy.generate_signal(analysis)
            except Exception:
                logger.exception(
                    "Strategy %s failed during ensemble vote for %s",
                    strategy.name,
                    analysis.symbol,
                )
                continue
            if signal is not None and signal.is_actionable:
                raw_signals.append(signal)

        if not raw_signals:
            return None

        buy_signals = [s for s in raw_signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in raw_signals if s.signal_type == SignalType.SELL]
        total_strategies = len(self._strategies)

        buy_agreement = len(buy_signals) / total_strategies
        sell_agreement = len(sell_signals) / total_strategies

        if buy_agreement >= self._ensemble_threshold and buy_agreement >= sell_agreement:
            return self._build_consensus(analysis, buy_signals, SignalType.BUY)
        if sell_agreement >= self._ensemble_threshold:
            return self._build_consensus(analysis, sell_signals, SignalType.SELL)

        logger.debug(
            "Ensemble: no consensus for %s (buy=%.0f%%, sell=%.0f%%, threshold=%.0f%%)",
            analysis.symbol,
            buy_agreement * 100,
            sell_agreement * 100,
            self._ensemble_threshold * 100,
        )
        return None

    def _build_consensus(
        self,
        analysis: MarketAnalysis,
        agreeing_signals: list[TradeSignal],
        direction: SignalType,
    ) -> TradeSignal | None:
        """Build a consensus signal from agreeing strategies."""
        if not agreeing_signals:
            return None

        total_weight = sum(s.confidence for s in agreeing_signals)
        avg_confidence = total_weight / len(agreeing_signals)

        if avg_confidence < self._min_confidence:
            logger.debug(
                "Ensemble consensus for %s %s below min confidence (%.2f < %.2f)",
                analysis.symbol,
                direction.value,
                avg_confidence,
                self._min_confidence,
            )
            return None

        contributing = [s.strategy_name for s in agreeing_signals]
        strength = (
            SignalStrength.STRONG
            if avg_confidence > 0.75
            else SignalStrength.MODERATE
            if avg_confidence > 0.55
            else SignalStrength.WEAK
        )

        logger.info(
            "Ensemble %s %s: confidence=%.2f, strategies=%s",
            direction.value,
            analysis.symbol,
            avg_confidence,
            contributing,
        )

        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=direction,
            strength=strength,
            confidence=avg_confidence,
            strategy_name="ensemble",
            entry_price=analysis.current_price,
            reason=(
                f"Ensemble {direction.value}: {len(agreeing_signals)}/{len(self._strategies)} "
                f"strategies agree ({', '.join(contributing)})"
            ),
            metadata={"contributing_strategies": ", ".join(contributing)},
        )
