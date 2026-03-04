"""Composite/ensemble strategy.

Wraps multiple strategies and produces a consensus signal via weighted
voting. This can be used as a single ``BaseStrategy`` in any context
where an individual strategy is expected.

For orchestration-level ensemble (running all strategies independently
and aggregating at the runner level), see ``StrategyRunner`` with
``ensemble=True``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.strategies.base import BaseStrategy

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis

logger = logging.getLogger(__name__)


class CompositeStrategy(BaseStrategy):
    """Ensemble strategy that aggregates signals from multiple child strategies.

    Produces a single consensus signal per call to ``generate_signal``. The
    consensus is determined by weighted voting among child strategies.

    Args:
        strategies: Child strategies to aggregate.
        agreement_threshold: Fraction of strategies that must agree for a
            consensus (e.g. 0.5 = majority, 0.67 = supermajority).
        min_confidence: Minimum average confidence for the consensus signal.
    """

    name = "composite"

    def __init__(
        self,
        strategies: list[BaseStrategy],
        agreement_threshold: float = 0.5,
        min_confidence: float = 0.5,
    ) -> None:
        if not strategies:
            raise ValueError("CompositeStrategy requires at least one child strategy")
        self._strategies = strategies
        self._agreement_threshold = max(0.0, min(1.0, agreement_threshold))
        self._min_confidence = min_confidence

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        raw_signals: list[TradeSignal] = []
        for strategy in self._strategies:
            try:
                signal = strategy.generate_signal(analysis)
            except Exception:
                logger.exception("Child strategy %s failed for %s", strategy.name, analysis.symbol)
                continue
            if signal is not None and signal.is_actionable:
                raw_signals.append(signal)

        if not raw_signals:
            return None

        buy_signals = [s for s in raw_signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in raw_signals if s.signal_type == SignalType.SELL]
        total = len(self._strategies)

        buy_agreement = len(buy_signals) / total
        sell_agreement = len(sell_signals) / total

        if buy_agreement >= self._agreement_threshold and buy_agreement >= sell_agreement:
            return self._consensus(analysis, buy_signals, SignalType.BUY)
        if sell_agreement >= self._agreement_threshold:
            return self._consensus(analysis, sell_signals, SignalType.SELL)

        return None

    def _consensus(
        self,
        analysis: MarketAnalysis,
        signals: list[TradeSignal],
        direction: SignalType,
    ) -> TradeSignal | None:
        avg_confidence = sum(s.confidence for s in signals) / len(signals)
        if avg_confidence < self._min_confidence:
            return None

        contributing = [s.strategy_name for s in signals]
        strength = (
            SignalStrength.STRONG
            if avg_confidence > 0.75
            else SignalStrength.MODERATE
            if avg_confidence > 0.55
            else SignalStrength.WEAK
        )

        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=direction,
            strength=strength,
            confidence=avg_confidence,
            strategy_name=self.name,
            entry_price=analysis.current_price,
            reason=(
                f"Composite {direction.value}: {len(signals)}/{len(self._strategies)} "
                f"strategies agree ({', '.join(contributing)})"
            ),
            metadata={"contributing_strategies": ", ".join(contributing)},
        )
