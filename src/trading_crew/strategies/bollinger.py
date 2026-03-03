"""Bollinger Bands strategy.

Ported from silvia_v2's BollingerBandBehavior. Generates buy signals when
price touches the lower band (oversold) and sell signals at the upper band
(overbought).

Indicators required in MarketAnalysis:
  - bb_upper  (upper Bollinger Band)
  - bb_middle (middle band / SMA)
  - bb_lower  (lower Bollinger Band)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.strategies.base import BaseStrategy

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis


class BollingerBandsStrategy(BaseStrategy):
    """Buy at lower band, sell at upper band."""

    name = "bollinger_bands"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        upper = analysis.get_indicator("bb_upper")
        middle = analysis.get_indicator("bb_middle")
        lower = analysis.get_indicator("bb_lower")

        if upper is None or middle is None or lower is None:
            return None

        price = analysis.current_price
        band_width = upper - lower

        if band_width <= 0:
            return None

        if price <= lower:
            distance_pct = ((lower - price) / band_width) * 100
            confidence = min(0.6 + distance_pct * 0.05, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"Price {price:.2f} at/below lower Bollinger Band {lower:.2f} "
                    f"(middle={middle:.2f}, upper={upper:.2f})"
                ),
            )

        if price >= upper:
            distance_pct = ((price - upper) / band_width) * 100
            confidence = min(0.6 + distance_pct * 0.05, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"Price {price:.2f} at/above upper Bollinger Band {upper:.2f} "
                    f"(middle={middle:.2f}, lower={lower:.2f})"
                ),
            )

        return None
