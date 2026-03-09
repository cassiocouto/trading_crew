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
    """Buy when price is near/below the lower band; sell near/above the upper band.

    ``proximity_pct`` controls how close the price needs to be to the band
    before a signal fires, expressed as a fraction of the total band width.
    0.0 = only fire when price is exactly at/beyond the band edge (original
    strict behaviour); 0.10 = fire when price is within 10 % of band width
    from either edge (default — more responsive).
    """

    name = "bollinger_bands"

    def __init__(self, proximity_pct: float = 0.10) -> None:
        self._proximity_pct = max(0.0, proximity_pct)

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

        # Proximity threshold in price terms
        threshold = band_width * self._proximity_pct
        lower_trigger = lower + threshold
        upper_trigger = upper - threshold

        if price <= lower_trigger:
            # How far below (or near) the lower band, scaled to band width
            distance_pct = ((lower_trigger - price) / band_width) * 100
            confidence = min(0.55 + distance_pct * 0.05, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"Price {price:.2f} near/below lower Bollinger Band {lower:.2f} "
                    f"(proximity={self._proximity_pct:.0%} of band width, "
                    f"middle={middle:.2f}, upper={upper:.2f})"
                ),
            )

        if price >= upper_trigger:
            distance_pct = ((price - upper_trigger) / band_width) * 100
            confidence = min(0.55 + distance_pct * 0.05, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"Price {price:.2f} near/above upper Bollinger Band {upper:.2f} "
                    f"(proximity={self._proximity_pct:.0%} of band width, "
                    f"middle={middle:.2f}, lower={lower:.2f})"
                ),
            )

        return None
