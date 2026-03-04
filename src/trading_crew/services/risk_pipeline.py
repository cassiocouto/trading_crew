"""Deterministic risk validation pipeline for Phase 3.

Every trade signal passes through this pipeline before execution:
  TradeSignal -> confidence filter -> circuit breaker -> position sizing
  -> stop-loss -> portfolio limits -> concentration limits -> RiskCheckResult

If the signal is approved, an OrderRequest is produced. If any stage rejects
the signal, the pipeline short-circuits with a rejection reason.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from trading_crew.models.order import OrderRequest, OrderSide, OrderType
from trading_crew.models.risk import RiskCheckResult, RiskVerdict
from trading_crew.risk.portfolio_limits import (
    check_concentration_limit,
    check_exposure_limit,
)
from trading_crew.risk.position_sizer import calculate_position_size
from trading_crew.risk.stop_loss import atr_based_stop, fixed_percentage_stop

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis
    from trading_crew.models.portfolio import Portfolio, Position
    from trading_crew.models.risk import RiskParams
    from trading_crew.models.signal import TradeSignal
    from trading_crew.risk.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class RiskPipeline:
    """Full risk validation pipeline.

    Args:
        risk_params: Risk configuration parameters.
        circuit_breaker: Portfolio-level circuit breaker instance.
        stop_loss_method: "fixed" for percentage-based, "atr" for ATR-based.
        atr_stop_multiplier: ATR multiplier for ATR-based stops.
    """

    def __init__(
        self,
        risk_params: RiskParams,
        circuit_breaker: CircuitBreaker,
        stop_loss_method: str = "fixed",
        atr_stop_multiplier: float = 2.0,
    ) -> None:
        self._risk_params = risk_params
        self._circuit_breaker = circuit_breaker
        self._stop_loss_method = stop_loss_method
        self._atr_stop_multiplier = atr_stop_multiplier

    def evaluate(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        analysis: MarketAnalysis | None = None,
    ) -> RiskCheckResult:
        """Run a signal through the full risk pipeline.

        Args:
            signal: Trade signal to validate.
            portfolio: Current portfolio state.
            analysis: Optional market analysis for ATR-based stops.

        Returns:
            RiskCheckResult with verdict, approved amounts, and reasons.
        """
        checks_passed: list[str] = []
        checks_failed: list[str] = []
        reasons: list[str] = []

        if self._circuit_breaker.check(portfolio):
            return RiskCheckResult(
                verdict=RiskVerdict.CIRCUIT_BREAK,
                approved_amount=0.0,
                reasons=[f"Circuit breaker: {self._circuit_breaker.trip_reason}"],
                checks_failed=["circuit_breaker"],
            )
        checks_passed.append("circuit_breaker")

        if signal.confidence < self._risk_params.min_confidence:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECTED,
                approved_amount=0.0,
                reasons=[
                    f"Confidence {signal.confidence:.2f} below minimum "
                    f"{self._risk_params.min_confidence:.2f}"
                ],
                checks_passed=checks_passed,
                checks_failed=["min_confidence"],
            )
        checks_passed.append("min_confidence")

        is_sell = signal.signal_type.value == "sell"

        if is_sell:
            held = portfolio.positions.get(signal.symbol)
            if held is None or held.amount <= 0:
                return RiskCheckResult(
                    verdict=RiskVerdict.REJECTED,
                    approved_amount=0.0,
                    reasons=[
                        f"No open position for {signal.symbol}; "
                        "short selling is not supported"
                    ],
                    checks_passed=checks_passed,
                    checks_failed=["inventory"],
                )
            checks_passed.append("inventory")
            return self._evaluate_sell(
                signal, portfolio, held, analysis, checks_passed, reasons
            )

        return self._evaluate_buy(
            signal, portfolio, analysis, checks_passed, checks_failed, reasons
        )

    def _evaluate_sell(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        held: Position,
        analysis: MarketAnalysis | None,
        checks_passed: list[str],
        reasons: list[str],
    ) -> RiskCheckResult:
        """SELL-specific pipeline: cap at held amount, skip exposure/concentration."""
        stop_loss_price = self._compute_stop_loss(signal, analysis)

        sizing = calculate_position_size(
            portfolio=portfolio,
            entry_price=signal.entry_price,
            stop_loss_price=stop_loss_price,
            risk_params=self._risk_params,
        )
        risk_amount = sizing.value / signal.entry_price if signal.entry_price > 0 else 0.0
        sell_amount = min(risk_amount, held.amount) if risk_amount > 0 else held.amount

        if sell_amount <= 0:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECTED,
                approved_amount=0.0,
                stop_loss_price=stop_loss_price,
                reasons=["No sellable quantity"],
                checks_passed=checks_passed,
                checks_failed=["position_sizing"],
            )
        checks_passed.append("position_sizing")

        verdict = RiskVerdict.APPROVED
        if sell_amount < held.amount:
            verdict = RiskVerdict.REDUCED
            reasons.append(
                f"Sell capped to {sell_amount:.6f} of {held.amount:.6f} held"
            )

        logger.info(
            "Risk %s: SELL %s amount=%.6f stop=%.2f (%s)",
            verdict.value,
            signal.symbol,
            sell_amount,
            stop_loss_price or 0.0,
            ", ".join(checks_passed),
        )

        return RiskCheckResult(
            verdict=verdict,
            approved_amount=sell_amount,
            approved_price=signal.entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=signal.take_profit_price,
            reasons=reasons,
            checks_passed=checks_passed,
        )

    def _evaluate_buy(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        analysis: MarketAnalysis | None,
        checks_passed: list[str],
        checks_failed: list[str],
        reasons: list[str],
    ) -> RiskCheckResult:
        """BUY-specific pipeline: position sizing + exposure/concentration limits."""
        stop_loss_price = self._compute_stop_loss(signal, analysis)

        sizing = calculate_position_size(
            portfolio=portfolio,
            entry_price=signal.entry_price,
            stop_loss_price=stop_loss_price,
            risk_params=self._risk_params,
        )
        position_value = sizing.value

        if position_value <= 0:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECTED,
                approved_amount=0.0,
                stop_loss_price=stop_loss_price,
                reasons=["Position size calculation yielded zero (insufficient balance)"],
                checks_passed=checks_passed,
                checks_failed=["position_sizing"],
            )
        checks_passed.append("position_sizing")

        exposure_ok, exposure_reason = check_exposure_limit(
            portfolio, position_value, self._risk_params
        )
        if not exposure_ok:
            checks_failed.append("exposure_limit")
            reasons.append(exposure_reason)
        else:
            checks_passed.append("exposure_limit")

        concentration_ok, concentration_reason = check_concentration_limit(
            portfolio, signal.symbol, position_value, self._risk_params
        )
        if not concentration_ok:
            checks_failed.append("concentration_limit")
            reasons.append(concentration_reason)
        else:
            checks_passed.append("concentration_limit")

        if checks_failed:
            return RiskCheckResult(
                verdict=RiskVerdict.REJECTED,
                approved_amount=0.0,
                stop_loss_price=stop_loss_price,
                reasons=reasons,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
            )

        position_amount = position_value / signal.entry_price if signal.entry_price > 0 else 0.0

        verdict = RiskVerdict.APPROVED
        if sizing.was_capped:
            verdict = RiskVerdict.REDUCED
            reasons.append(
                f"Position capped from {sizing.risk_based_value:.2f} to "
                f"{sizing.value:.2f} by max-position or available-balance limit"
            )

        logger.info(
            "Risk %s: BUY %s amount=%.6f stop=%.2f (%s)",
            verdict.value,
            signal.symbol,
            position_amount,
            stop_loss_price or 0.0,
            ", ".join(checks_passed),
        )

        return RiskCheckResult(
            verdict=verdict,
            approved_amount=position_amount,
            approved_price=signal.entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=signal.take_profit_price,
            reasons=reasons,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )

    def _compute_stop_loss(
        self,
        signal: TradeSignal,
        analysis: MarketAnalysis | None,
    ) -> float:
        """Determine the stop-loss price for a signal."""
        if signal.stop_loss_price is not None:
            return signal.stop_loss_price

        side = "long" if signal.signal_type.value == "buy" else "short"

        if self._stop_loss_method == "atr" and analysis is not None:
            atr = analysis.get_indicator("atr_14")
            if atr is not None and atr > 0:
                return atr_based_stop(
                    entry_price=signal.entry_price,
                    atr_value=atr,
                    multiplier=self._atr_stop_multiplier,
                    side=side,
                )

        return fixed_percentage_stop(
            entry_price=signal.entry_price,
            stop_pct=self._risk_params.default_stop_loss_pct,
            side=side,
        )

    @staticmethod
    def to_order_request(
        signal: TradeSignal,
        result: RiskCheckResult,
    ) -> OrderRequest | None:
        """Convert an approved signal + risk result into an OrderRequest.

        Returns None if the signal was not approved.
        """
        if not result.is_approved or result.approved_amount <= 0:
            return None

        return OrderRequest(
            symbol=signal.symbol,
            exchange=signal.exchange,
            side=OrderSide.BUY if signal.signal_type.value == "buy" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=result.approved_amount,
            price=result.approved_price,
            stop_loss_price=result.stop_loss_price,
            take_profit_price=result.take_profit_price,
            strategy_name=signal.strategy_name,
            signal_confidence=signal.confidence,
        )
