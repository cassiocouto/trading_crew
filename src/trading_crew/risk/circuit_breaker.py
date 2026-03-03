"""Circuit breaker — halts trading when drawdown exceeds threshold.

The circuit breaker monitors portfolio drawdown and pauses all trading
activity when the maximum allowed drawdown is breached. This prevents
catastrophic losses during extreme market conditions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from trading_crew.models.portfolio import Portfolio
from trading_crew.models.risk import RiskParams

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Portfolio-level circuit breaker.

    Tracks drawdown and provides a simple is_tripped interface that agents
    check before generating or executing orders.

    Attributes:
        is_tripped: True if the circuit breaker has been activated.
        tripped_at: Timestamp when the breaker was tripped.
        trip_reason: Human-readable reason for the trip.
    """

    def __init__(self, risk_params: RiskParams) -> None:
        self._max_drawdown_pct = risk_params.max_drawdown_pct
        self.is_tripped: bool = False
        self.tripped_at: datetime | None = None
        self.trip_reason: str = ""

    def check(self, portfolio: Portfolio) -> bool:
        """Check if the circuit breaker should trip.

        Args:
            portfolio: Current portfolio state.

        Returns:
            True if trading should be halted.
        """
        if self.is_tripped:
            return True

        drawdown = portfolio.drawdown_pct

        if drawdown >= self._max_drawdown_pct:
            self.is_tripped = True
            self.tripped_at = datetime.now(timezone.utc)
            self.trip_reason = (
                f"Drawdown {drawdown:.2f}% exceeded limit of {self._max_drawdown_pct:.1f}%"
            )
            logger.critical("CIRCUIT BREAKER TRIPPED: %s", self.trip_reason)
            return True

        return False

    def reset(self) -> None:
        """Manually reset the circuit breaker.

        Should only be called after reviewing the situation and confirming
        it is safe to resume trading.
        """
        if self.is_tripped:
            logger.warning("Circuit breaker manually reset (was tripped at %s)", self.tripped_at)
        self.is_tripped = False
        self.tripped_at = None
        self.trip_reason = ""
