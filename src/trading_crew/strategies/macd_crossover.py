"""MACD Crossover strategy.

Generates signals when the MACD line crosses its signal line.  Because the
MACD and its signal line are already computed by the TechnicalAnalyzer on
every cycle, this strategy fires more frequently than the extreme-condition
strategies (Bollinger Bands, RSI Range) and works in trending and volatile
regimes.

Signal logic
------------
- BUY:  MACD line crosses *above* the signal line (bullish momentum flip).
        Confidence scales with the histogram distance from zero.
- SELL: MACD line crosses *below* the signal line (bearish momentum flip).

Because the TechnicalAnalyzer only exposes a single snapshot (not a
previous-bar value), crossover is approximated by the histogram sign.
  histogram > 0  → MACD line above signal → bullish
  histogram < 0  → MACD line below signal → bearish

A minimum absolute histogram threshold (``min_histogram``) prevents signals
in near-zero / flat markets where noise would dominate.

Indicators required in MarketAnalysis:
  - macd_line      (MACD line: EMA12 - EMA26)
  - macd_signal    (9-period EMA of macd_line)
  - macd_histogram (macd_line - macd_signal)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.strategies.base import BaseStrategy

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis


class MACDCrossoverStrategy(BaseStrategy):
    """Buy on bullish MACD histogram, sell on bearish histogram."""

    name = "macd_crossover"

    def __init__(self, min_histogram: float = 0.0) -> None:
        """
        Args:
            min_histogram: Minimum absolute value of the MACD histogram required
                to generate a signal.  Set > 0 to avoid whipsaw signals in
                flat/ranging markets.  Defaults to 0 (fire on any non-zero bar).
        """
        self._min_histogram = abs(min_histogram)

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        macd_line = analysis.get_indicator("macd_line")
        macd_signal = analysis.get_indicator("macd_signal")
        histogram = analysis.get_indicator("macd_histogram")

        if macd_line is None or macd_signal is None or histogram is None:
            return None

        if abs(histogram) < self._min_histogram:
            return None

        price = analysis.current_price

        # Scale confidence by histogram magnitude relative to current price
        # so that stronger separations yield higher confidence.
        magnitude_pct = abs(histogram) / price * 100 if price > 0 else 0.0
        confidence = min(0.50 + magnitude_pct * 5.0, 0.85)

        if histogram > 0:
            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG if confidence > 0.70 else SignalStrength.MODERATE,
                confidence=confidence,
                strategy_name=self.name,
                entry_price=price,
                reason=(
                    f"MACD bullish: histogram={histogram:.4f} (macd={macd_line:.4f}, "
                    f"signal={macd_signal:.4f}), price={price:.2f}"
                ),
            )

        return TradeSignal(
            symbol=analysis.symbol,
            exchange=analysis.exchange,
            signal_type=SignalType.SELL,
            strength=SignalStrength.STRONG if confidence > 0.70 else SignalStrength.MODERATE,
            confidence=confidence,
            strategy_name=self.name,
            entry_price=price,
            reason=(
                f"MACD bearish: histogram={histogram:.4f} (macd={macd_line:.4f}, "
                f"signal={macd_signal:.4f}), price={price:.2f}"
            ),
        )
