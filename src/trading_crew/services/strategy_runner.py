"""Deterministic strategy execution engine.

Runs registered strategies against MarketAnalysis data and aggregates
signals. Supports two modes:
  - Individual: every strategy produces independent signals
  - Ensemble: strategies vote per symbol, producing one consensus signal

Returns a ``StrategyEvaluation`` that bundles the filtered actionable signals
with the full per-strategy vote breakdown.  The vote data feeds the
``UncertaintyScorer`` to detect strategy disagreement.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from trading_crew.models.signal import (
    SignalStrength,
    SignalType,
    StrategyEvaluation,
    StrategyVote,
    TradeSignal,
)

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis
    from trading_crew.models.portfolio import Portfolio
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

    def evaluate(
        self,
        analyses: dict[str, MarketAnalysis],
        portfolio: Portfolio | None = None,
    ) -> StrategyEvaluation:
        """Run all strategies against the provided analyses.

        Args:
            analyses: Market analyses keyed by symbol.
            portfolio: Current portfolio snapshot used for two pre-flight
                checks: SELL signals are suppressed when the portfolio holds
                no position in the symbol, and BUY signals are suppressed
                when the available quote balance is zero or negative.  Pass
                ``None`` to skip both checks (e.g. in backtesting).

        Returns:
            StrategyEvaluation with actionable signals and full vote breakdown.
        """
        if self._ensemble:
            return self._evaluate_ensemble(analyses, portfolio)
        return self._evaluate_individual(analyses, portfolio)

    def _evaluate_individual(
        self,
        analyses: dict[str, MarketAnalysis],
        portfolio: Portfolio | None,
    ) -> StrategyEvaluation:
        signals: list[TradeSignal] = []
        votes: dict[str, list[StrategyVote]] = {}
        for symbol, analysis in analyses.items():
            symbol_votes: list[StrategyVote] = []
            for strategy in self._strategies:
                try:
                    signal = strategy.generate_signal(analysis)
                except Exception:
                    logger.exception("Strategy %s failed for %s", strategy.name, symbol)
                    symbol_votes.append(
                        StrategyVote(strategy.name, symbol, None, filtered_reason="error")
                    )
                    continue

                if signal is None:
                    symbol_votes.append(
                        StrategyVote(strategy.name, symbol, None, filtered_reason="none")
                    )
                    continue
                if not signal.is_actionable:
                    symbol_votes.append(
                        StrategyVote(strategy.name, symbol, signal, filtered_reason="hold")
                    )
                    continue

                # Portfolio pre-flight: skip SELL when nothing is held, skip BUY
                # when the quote balance is empty.  The risk pipeline handles
                # finer-grained checks; these guards just prevent noise signals.
                if portfolio is not None:
                    if signal.signal_type == SignalType.SELL and symbol not in portfolio.positions:
                        logger.debug(
                            "Skipping SELL from %s for %s — no open position",
                            strategy.name,
                            symbol,
                        )
                        symbol_votes.append(
                            StrategyVote(
                                strategy.name, symbol, signal, filtered_reason="no_position"
                            )
                        )
                        continue
                    if signal.signal_type == SignalType.BUY and portfolio.balance_quote <= 0:
                        logger.debug(
                            "Skipping BUY from %s for %s — zero quote balance",
                            strategy.name,
                            symbol,
                        )
                        symbol_votes.append(
                            StrategyVote(strategy.name, symbol, signal, filtered_reason="no_funds")
                        )
                        continue

                if signal.confidence < self._min_confidence:
                    logger.debug(
                        "Signal from %s for %s below min confidence (%.2f < %.2f)",
                        strategy.name,
                        symbol,
                        signal.confidence,
                        self._min_confidence,
                    )
                    symbol_votes.append(
                        StrategyVote(
                            strategy.name, symbol, signal, filtered_reason="below_min_confidence"
                        )
                    )
                    continue
                symbol_votes.append(StrategyVote(strategy.name, symbol, signal))
                signals.append(signal)
                logger.info(
                    "Signal: %s %s %s (confidence=%.2f, strategy=%s)",
                    signal.signal_type.value,
                    signal.symbol,
                    signal.strength.value,
                    signal.confidence,
                    signal.strategy_name,
                )
            votes[symbol] = symbol_votes
        return StrategyEvaluation(signals=signals, votes=votes)

    def _evaluate_ensemble(
        self,
        analyses: dict[str, MarketAnalysis],
        portfolio: Portfolio | None,
    ) -> StrategyEvaluation:
        signals: list[TradeSignal] = []
        votes: dict[str, list[StrategyVote]] = {}
        for _symbol, analysis in analyses.items():
            symbol_votes: list[StrategyVote] = []
            consensus = self._vote(analysis, symbol_votes, portfolio)
            votes[analysis.symbol] = symbol_votes
            if consensus is not None:
                signals.append(consensus)
        return StrategyEvaluation(signals=signals, votes=votes)

    def _vote(
        self,
        analysis: MarketAnalysis,
        out_votes: list[StrategyVote],
        portfolio: Portfolio | None,
    ) -> TradeSignal | None:
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
                out_votes.append(
                    StrategyVote(strategy.name, analysis.symbol, None, filtered_reason="error")
                )
                continue
            if signal is not None and signal.is_actionable:
                # Portfolio pre-flight (same logic as individual mode)
                if portfolio is not None:
                    if (
                        signal.signal_type == SignalType.SELL
                        and analysis.symbol not in portfolio.positions
                    ):
                        out_votes.append(
                            StrategyVote(
                                strategy.name,
                                analysis.symbol,
                                signal,
                                filtered_reason="no_position",
                            )
                        )
                        continue
                    if signal.signal_type == SignalType.BUY and portfolio.balance_quote <= 0:
                        out_votes.append(
                            StrategyVote(
                                strategy.name,
                                analysis.symbol,
                                signal,
                                filtered_reason="no_funds",
                            )
                        )
                        continue
                raw_signals.append(signal)
                out_votes.append(StrategyVote(strategy.name, analysis.symbol, signal))
                logger.debug(
                    "Ensemble vote: %s → %s %s (confidence=%.2f)",
                    strategy.name,
                    signal.signal_type.value,
                    analysis.symbol,
                    signal.confidence,
                )
            else:
                reason = "none" if signal is None else "hold"
                out_votes.append(
                    StrategyVote(strategy.name, analysis.symbol, signal, filtered_reason=reason)
                )
                logger.debug("Ensemble vote: %s → no signal for %s", strategy.name, analysis.symbol)

        if not raw_signals:
            logger.debug("Ensemble: all strategies returned no signal for %s", analysis.symbol)
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
