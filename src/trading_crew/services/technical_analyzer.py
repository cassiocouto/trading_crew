"""Pure technical-analysis engine shared by tools and services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from trading_crew.models.market import MarketAnalysis, MarketMetadata

DEFAULT_VOLATILITY_THRESHOLD = 0.03
DEFAULT_TREND_THRESHOLD = 0.01


class TechnicalAnalyzer:
    """Deterministic indicator computation and regime classification."""

    def __init__(
        self,
        volatility_threshold: float = DEFAULT_VOLATILITY_THRESHOLD,
        trend_threshold: float = DEFAULT_TREND_THRESHOLD,
    ) -> None:
        self._volatility_threshold = max(0.0, volatility_threshold)
        self._trend_threshold = max(0.0, trend_threshold)

    def analyze_from_candles(
        self, symbol: str, exchange: str, candles: list[Any]
    ) -> MarketAnalysis:
        if len(candles) < 20:
            raise ValueError("Need at least 20 candles for analysis")

        closes = [self._value(c, "close") for c in candles]
        highs = [self._value(c, "high") for c in candles]
        lows = [self._value(c, "low") for c in candles]

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

        macd_line, macd_signal, macd_hist = self._macd(closes)
        indicators["macd_line"] = macd_line
        indicators["macd_signal"] = macd_signal
        indicators["macd_histogram"] = macd_hist

        atr = self._atr(highs, lows, closes, period=14)
        if atr is not None:
            indicators["atr_14"] = atr

        indicators["range_high"] = max(self._value(c, "high") for c in candles)
        indicators["range_low"] = min(self._value(c, "low") for c in candles)
        regime = self._classify_regime(indicators)

        metadata = MarketMetadata(market_regime=regime, candle_count=len(candles))
        return MarketAnalysis(
            symbol=symbol,
            exchange=exchange,
            timestamp=datetime.now(UTC),
            current_price=closes[-1],
            indicators=indicators,
            metadata=metadata,
        )

    @staticmethod
    def _value(candle: Any, key: str) -> float:
        """Read OHLCV value from either dict-like or typed model candles."""
        if isinstance(candle, dict):
            return float(candle[key])
        return float(getattr(candle, key))

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        if len(values) < period:
            return values[-1]
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

    @staticmethod
    def _ema_series(values: list[float], period: int) -> list[float]:
        if not values:
            return []
        multiplier = 2 / (period + 1)
        ema = values[0]
        out = [ema]
        for price in values[1:]:
            ema = (price - ema) * multiplier + ema
            out.append(ema)
        return out

    def _macd(self, closes: list[float]) -> tuple[float, float, float]:
        if not closes:
            return 0.0, 0.0, 0.0
        ema_12 = self._ema_series(closes, 12)
        ema_26 = self._ema_series(closes, 26)
        macd_series = [a - b for a, b in zip(ema_12, ema_26, strict=False)]
        signal_series = self._ema_series(macd_series, 9)
        macd_line = macd_series[-1]
        macd_signal = signal_series[-1]
        return macd_line, macd_signal, macd_line - macd_signal

    @staticmethod
    def _rsi(values: list[float], period: int = 14) -> float | None:
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
        window = values[-period:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        return mean, variance**0.5

    @staticmethod
    def _atr(
        highs: list[float], lows: list[float], closes: list[float], period: int = 14
    ) -> float | None:
        if len(closes) < period + 1:
            return None
        true_ranges: list[float] = []
        for i in range(1, len(closes)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        if len(true_ranges) < period:
            return None
        atr = sum(true_ranges[:period]) / period
        for tr in true_ranges[period:]:
            atr = ((atr * (period - 1)) + tr) / period
        return atr

    def _classify_regime(self, indicators: dict[str, float]) -> str:
        """Classify market regime from trend and volatility.

        Thresholds are conservative defaults calibrated for large-cap crypto:
        - volatile when ATR/price > 3%
        - trending when EMA spread/price > 1%
        - otherwise ranging
        """
        ema_fast = indicators.get("ema_fast", 0.0)
        ema_slow = indicators.get("ema_slow", 0.0)
        atr = indicators.get("atr_14", 0.0)
        price_ref = indicators.get("bb_middle", indicators.get("ema_slow", 1.0)) or 1.0
        trend_strength = abs(ema_fast - ema_slow) / price_ref
        volatility_strength = atr / price_ref if atr > 0 else 0.0
        if volatility_strength > self._volatility_threshold:
            return "volatile"
        if trend_strength > self._trend_threshold:
            return "trending"
        return "ranging"
