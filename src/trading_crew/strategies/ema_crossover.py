"""EMA Crossover strategy.

Ported from silvia_v2's AdaptiveEMABehavior, cleaned up and made stateless.
Generates buy signals when the fast EMA crosses above the slow EMA, and sell
signals on the reverse crossover.

Indicators required in MarketAnalysis:
  - ema_fast (default: EMA 12)
  - ema_slow (default: EMA 50)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.strategies.base import BaseStrategy

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis


class EMACrossoverStrategy(BaseStrategy):
    """Buy on bullish EMA crossover, sell on bearish crossover."""

    name = "ema_crossover"

    def __init__(self, fast_key: str = "ema_fast", slow_key: str = "ema_slow") -> None:
        self._fast_key = fast_key
        self._slow_key = slow_key

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        fast_ema = analysis.get_indicator(self._fast_key)
        slow_ema = analysis.get_indicator(self._slow_key)

        if fast_ema is None or slow_ema is None:
            return None

        price = analysis.current_price

        if fast_ema > slow_ema and price > fast_ema:
            spread_pct = ((fast_ema - slow_ema) / slow_ema) * 100
            confidence = min(0.5 + spread_pct * 0.1, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"Bullish EMA crossover: fast={fast_ema:.2f} > slow={slow_ema:.2f}, "
                    f"price={price:.2f} above fast EMA"
                ),
            )

        if fast_ema < slow_ema and price < fast_ema:
            spread_pct = ((slow_ema - fast_ema) / fast_ema) * 100
            confidence = min(0.5 + spread_pct * 0.1, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"Bearish EMA crossover: fast={fast_ema:.2f} < slow={slow_ema:.2f}, "
                    f"price={price:.2f} below fast EMA"
                ),
            )

        return None
