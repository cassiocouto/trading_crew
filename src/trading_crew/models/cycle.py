"""Trading cycle state — typed contract for pipeline data handoff.

Defines the structured shape of data that flows through a single cycle:
  Market intelligence  -> CycleState.market_analyses
  Strategy + Risk      -> CycleState.signals, risk_results, order_requests
  Uncertainty scoring  -> CycleState.uncertainty_score, uncertainty_factors
  Advisory (optional)  -> CycleState.advisory_ran, advisory_adjustments,
                          advisory_summary
  Execution            -> CycleState.orders, filled/cancelled/failed_orders
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from trading_crew.models.market import MarketAnalysis
from trading_crew.models.order import Order, OrderRequest
from trading_crew.models.risk import RiskCheckResult
from trading_crew.models.signal import TradeSignal


class CycleState(BaseModel):
    """Typed state passed between crews within a single trading cycle.

    Attributes:
        id: Auto-injected by CrewAI Flow as a UUID string. Declared explicitly
            here to prevent field-shadowing warnings from Pydantic.
        cycle_number: Monotonically increasing cycle counter.
        timestamp: When this cycle started.
        symbols: Trading pairs evaluated in this cycle.
        market_analyses: Output of the Market Intelligence Crew, keyed by symbol.
        signals: Trade signals produced by the Strategy Crew.
        risk_results: Risk check results for each signal.
        order_requests: Risk-approved order requests ready for execution.
        orders: All orders placed/tracked by the Execution Crew this cycle.
        filled_orders: Orders that reached FILLED status this cycle.
        cancelled_orders: Orders cancelled (stale or error) this cycle.
        failed_orders: Order requests that could not be placed (dead-letter).
            Stored as dicts (converted via ``FailedOrder.as_dict()``) to keep
            the state model serialisable without importing execution internals.
        errors: Non-fatal errors encountered during the cycle.
    """

    id: str = ""
    cycle_number: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    symbols: list[str] = Field(default_factory=list)
    market_analyses: dict[str, MarketAnalysis] = Field(default_factory=dict)
    signals: list[TradeSignal] = Field(default_factory=list)
    risk_results: list[RiskCheckResult] = Field(default_factory=list)
    order_requests: list[OrderRequest] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    filled_orders: list[Order] = Field(default_factory=list)
    cancelled_orders: list[Order] = Field(default_factory=list)
    failed_orders: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    circuit_breaker_tripped: bool = False

    uncertainty_score: float = 0.0
    uncertainty_factors: list[str] = Field(default_factory=list)
    advisory_ran: bool = False
    advisory_adjustments: list[dict[str, Any]] = Field(default_factory=list)
    advisory_summary: str = ""

    @property
    def has_actionable_signals(self) -> bool:
        """Whether any signals passed risk checks."""
        return any(r.is_approved for r in self.risk_results)

    @property
    def summary(self) -> str:
        """One-line summary of this cycle's results."""
        n_analyses = len(self.market_analyses)
        n_signals = len([s for s in self.signals if s.is_actionable])
        n_approved = len([r for r in self.risk_results if r.is_approved])
        n_requests = len(self.order_requests)
        n_placed = len(self.orders)
        n_filled = len(self.filled_orders)
        n_cancelled = len(self.cancelled_orders)
        n_failed = len(self.failed_orders)
        return (
            f"Cycle {self.cycle_number}: "
            f"{n_analyses} analyses, {n_signals} signals, "
            f"{n_approved} risk-approved, {n_requests} order requests, "
            f"{n_placed} placed, {n_filled} filled, "
            f"{n_cancelled} cancelled, {n_failed} failed"
        )
