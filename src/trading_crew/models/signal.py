"""Trade signal models.

Signals are the output of the Strategy Crew — a recommendation to buy, sell,
or hold. They carry a confidence score and must pass through the Risk Manager
before becoming an order.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """Direction of a trade signal."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SignalStrength(str, Enum):
    """Qualitative confidence level of a signal.

    Used alongside the numeric confidence score for human-readable logging.
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class TradeSignal(BaseModel, frozen=True):
    """A recommendation to take a trading action.

    Produced by the Strategist Agent and consumed by the Risk Manager Agent.

    Attributes:
        symbol: Trading pair (e.g. "BTC/USDT").
        exchange: Target exchange.
        signal_type: Buy, sell, or hold.
        strength: Qualitative confidence level.
        confidence: Numeric confidence between 0 and 1.
        strategy_name: Which strategy produced this signal.
        entry_price: Suggested entry price (may differ from current market).
        stop_loss_price: Suggested stop-loss level (optional, Risk Manager may override).
        take_profit_price: Suggested take-profit level (optional).
        reason: Human-readable explanation of why this signal was generated.
        timestamp: When the signal was generated.
        metadata: Additional strategy-specific data.
    """

    symbol: str
    exchange: str
    signal_type: SignalType
    strength: SignalStrength
    confidence: float = Field(ge=0.0, le=1.0)
    strategy_name: str
    entry_price: float = Field(gt=0)
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    reason: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, float | str] = Field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Whether this signal suggests placing an order (not HOLD)."""
        return self.signal_type != SignalType.HOLD
