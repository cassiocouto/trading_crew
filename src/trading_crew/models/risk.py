"""Risk management models.

These models define the parameters and results of risk validation. Every trade
signal must pass through the risk pipeline before becoming an order.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RiskVerdict(StrEnum):
    """Outcome of a risk check.

    APPROVED: Signal passes all risk checks, proceed to execution.
    REDUCED: Signal approved but position size was reduced.
    REJECTED: Signal rejected by risk rules.
    CIRCUIT_BREAK: Trading halted due to critical risk threshold.
    """

    APPROVED = "approved"
    REDUCED = "reduced"
    REJECTED = "rejected"
    CIRCUIT_BREAK = "circuit_break"


class RiskParams(BaseModel, frozen=True):
    """Configurable risk management parameters.

    These are loaded from configuration and define the risk envelope
    for the entire portfolio.

    Attributes:
        max_position_size_pct: Maximum size of a single position as a
            percentage of total portfolio. Prevents over-concentration.
        max_portfolio_exposure_pct: Maximum total exposure (sum of all
            positions) as a percentage of portfolio.
        max_drawdown_pct: Maximum allowed drawdown before circuit breaker
            halts all trading.
        default_stop_loss_pct: Default stop-loss distance as a percentage
            below entry price.
        risk_per_trade_pct: Maximum portfolio percentage risked on a
            single trade (used for position sizing).
        min_confidence: Minimum signal confidence to consider for trading.
        cooldown_after_loss_seconds: Mandatory wait time after a losing
            trade before the next entry.
    """

    max_position_size_pct: float = Field(default=10.0, gt=0, le=100)
    max_portfolio_exposure_pct: float = Field(default=80.0, gt=0, le=100)
    max_drawdown_pct: float = Field(default=15.0, gt=0, le=100)
    default_stop_loss_pct: float = Field(default=3.0, gt=0, le=50)
    risk_per_trade_pct: float = Field(default=2.0, gt=0, le=100)
    min_confidence: float = Field(default=0.5, ge=0, le=1.0)
    cooldown_after_loss_seconds: int = Field(default=300, ge=0)
    min_profit_margin_pct: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description=(
            "Minimum profit margin above break-even required before a sell signal is approved. "
            "0.0 = pure break-even (default). e.g. 1.0 = require at least 1% profit above cost."
        ),
    )


class RiskCheckResult(BaseModel, frozen=True):
    """Result of running a trade signal through the risk pipeline.

    Attributes:
        verdict: Overall risk decision.
        approved_amount: Adjusted position size (may be less than requested).
        approved_price: Adjusted price (usually unchanged).
        stop_loss_price: Final stop-loss level after risk adjustments.
        take_profit_price: Final take-profit level.
        reasons: Human-readable explanations for any adjustments or rejections.
        checks_passed: Names of individual risk checks that passed.
        checks_failed: Names of individual risk checks that failed.
    """

    verdict: RiskVerdict
    approved_amount: float = Field(ge=0)
    approved_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    reasons: list[str] = Field(default_factory=list)
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[str] = Field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        """Whether the signal was approved (possibly with adjustments)."""
        return self.verdict in (RiskVerdict.APPROVED, RiskVerdict.REDUCED)
