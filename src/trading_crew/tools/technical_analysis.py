"""CrewAI Tool for computing technical indicators.

Uses pandas and basic math to compute indicators. In Phase 2, this will
be enhanced with pandas-ta for the full indicator library.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from crewai.tools import BaseTool

from trading_crew.models.market import OHLCV, MarketAnalysis


class AnalyzeMarketTool(BaseTool):
    """Compute technical indicators from OHLCV data."""

    name: str = "analyze_market"
    description: str = (
        "Compute technical indicators (EMA, RSI, Bollinger Bands) from "
        "OHLCV candle data. Input: JSON with 'symbol', 'exchange', and "
        "'candles' (list of {open, high, low, close, volume} objects)."
    )

    def _run(self, input_str: str) -> str:
        params = json.loads(input_str)
        symbol = params["symbol"]
        exchange = params.get("exchange", "unknown")
        candles = params.get("candles", [])

        if len(candles) < 20:
            return json.dumps({"error": "Need at least 20 candles for analysis"})

        closes = [c["close"] for c in candles]

        indicators: dict[str, float] = {}
        indicators["ema_fast"] = self._ema(closes, 12)
        indicators["ema_slow"] = self._ema(closes, 50) if len(closes) >= 50 else closes[-1]

        rsi = self._rsi(closes, 14)
        if rsi is not None:
            indicators["rsi_14"] = rsi

        sma_20, std_20 = self._sma_std(closes, 20)
        indicators["bb_middle"] = sma_20
        indicators["bb_upper"] = sma_20 + 2 * std_20
        indicators["bb_lower"] = sma_20 - 2 * std_20

        indicators["range_high"] = max(c["high"] for c in candles)
        indicators["range_low"] = min(c["low"] for c in candles)

        analysis = MarketAnalysis(
            symbol=symbol,
            exchange=exchange,
            timestamp=datetime.now(timezone.utc),
            current_price=closes[-1],
            indicators=indicators,
        )

        return json.dumps(
            {
                "symbol": analysis.symbol,
                "current_price": analysis.current_price,
                "indicators": {k: round(v, 4) for k, v in analysis.indicators.items()},
                "timestamp": analysis.timestamp.isoformat(),
            },
            indent=2,
        )

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        """Compute Exponential Moving Average."""
        if len(values) < period:
            return values[-1]
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    @staticmethod
    def _rsi(values: list[float], period: int = 14) -> float | None:
        """Compute Relative Strength Index."""
        if len(values) < period + 1:
            return None
        deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _sma_std(values: list[float], period: int) -> tuple[float, float]:
        """Compute Simple Moving Average and Standard Deviation."""
        window = values[-period:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        return mean, variance**0.5
