"""Base strategy interface.

All trading strategies must inherit from ``BaseStrategy`` and implement
``generate_signal()``. This is the stable public API for community-contributed
strategies.

Example:
    class MyStrategy(BaseStrategy):
        name = "my_strategy"

        def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
            if analysis.get_indicator("rsi_14") < 30:
                return TradeSignal(
                    symbol=analysis.symbol,
                    exchange=analysis.exchange,
                    signal_type=SignalType.BUY,
                    strength=SignalStrength.MODERATE,
                    confidence=0.7,
                    strategy_name=self.name,
                    entry_price=analysis.current_price,
                    reason="RSI oversold",
                )
            return None
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis
    from trading_crew.models.signal import TradeSignal


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies.

    Subclasses must set ``name`` and implement ``generate_signal()``.

    Attributes:
        name: Unique identifier for this strategy. Used in logging,
            signals, and the strategy registry.
    """

    name: str = "base"

    @abstractmethod
    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        """Evaluate market data and produce a trade signal.

        Args:
            analysis: Processed market data with technical indicators,
                produced by the Analyst Agent.

        Returns:
            A TradeSignal if the strategy detects an opportunity, or None
            if no action should be taken (equivalent to HOLD).
        """
        ...

    def __repr__(self) -> str:
        return f"<Strategy: {self.name}>"
