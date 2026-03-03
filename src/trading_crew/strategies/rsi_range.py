"""RSI Range strategy.

Ported from silvia_v2's RangeRSIBehavior. Uses RSI(14) combined with
price position within the recent range to identify oversold/overbought
conditions.

Indicators required in MarketAnalysis:
  - rsi_14    (Relative Strength Index, 14 periods)
  - range_low (recent range low, e.g. 30-day low)
  - range_high (recent range high, e.g. 30-day high)
"""

from __future__ import annotations

from trading_crew.models.market import MarketAnalysis
from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.strategies.base import BaseStrategy


class RSIRangeStrategy(BaseStrategy):
    """Buy when RSI is oversold and price is near range low; sell on the reverse."""

    name = "rsi_range"

    def __init__(
        self,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
        range_low_pct: float = 0.20,
        range_high_pct: float = 0.80,
    ) -> None:
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._range_low_pct = range_low_pct
        self._range_high_pct = range_high_pct

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        rsi = analysis.get_indicator("rsi_14")
        range_low = analysis.get_indicator("range_low")
        range_high = analysis.get_indicator("range_high")

        if rsi is None or range_low is None or range_high is None:
            return None

        price = analysis.current_price
        total_range = range_high - range_low

        if total_range <= 0:
            return None

        position_in_range = (price - range_low) / total_range

        if rsi < self._rsi_oversold and position_in_range < self._range_low_pct:
            confidence = min(0.5 + (self._rsi_oversold - rsi) * 0.015, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"RSI oversold ({rsi:.1f} < {self._rsi_oversold}) and price in "
                    f"bottom {self._range_low_pct*100:.0f}% of range "
                    f"({range_low:.2f} - {range_high:.2f})"
                ),
            )

        if rsi > self._rsi_overbought and position_in_range > self._range_high_pct:
            confidence = min(0.5 + (rsi - self._rsi_overbought) * 0.015, 0.95)

            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"RSI overbought ({rsi:.1f} > {self._rsi_overbought}) and price in "
                    f"top {(1 - self._range_high_pct)*100:.0f}% of range "
                    f"({range_low:.2f} - {range_high:.2f})"
                ),
            )

        return None
