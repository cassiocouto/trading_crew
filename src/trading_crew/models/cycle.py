"""Trading cycle state — typed contract for planned inter-crew data handoff.

Defines the structured shape of data that will flow between crews:
  MarketCrew  -> CycleState.market_analyses
  StrategyCrew -> CycleState.signals, CycleState.risk_results
  ExecutionCrew -> CycleState.orders

Phase 1 status:
  This DTO is instantiated per cycle for logging and audit, but the fields
  are NOT yet populated from crew outputs. Crew results currently flow as
  unstructured LLM text. Deterministic typed handoff (parsing crew outputs
  into these fields) is planned for Phase 5 when the pipeline migrates to
  a CrewAI Flow.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from trading_crew.models.market import MarketAnalysis
from trading_crew.models.order import Order
from trading_crew.models.risk import RiskCheckResult
from trading_crew.models.signal import TradeSignal


class CycleState(BaseModel):
    """Typed state passed between crews within a single trading cycle.

    Attributes:
        cycle_number: Monotonically increasing cycle counter.
        timestamp: When this cycle started.
        symbols: Trading pairs evaluated in this cycle.
        market_analyses: Output of the Market Intelligence Crew, keyed by symbol.
        signals: Trade signals produced by the Strategy Crew.
        risk_results: Risk check results for each signal.
        orders: Orders placed by the Execution Crew.
        errors: Non-fatal errors encountered during the cycle.
    """

    cycle_number: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    symbols: list[str] = Field(default_factory=list)
    market_analyses: dict[str, MarketAnalysis] = Field(default_factory=dict)
    signals: list[TradeSignal] = Field(default_factory=list)
    risk_results: list[RiskCheckResult] = Field(default_factory=list)
    orders: list[Order] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

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
        n_orders = len(self.orders)
        return (
            f"Cycle {self.cycle_number}: "
            f"{n_analyses} analyses, {n_signals} signals, "
            f"{n_approved} risk-approved, {n_orders} orders"
        )
