"""Unit tests for technical analysis tool outputs."""

from __future__ import annotations

import json

import pytest

from trading_crew.services.technical_analyzer import TechnicalAnalyzer
from trading_crew.tools.technical_analysis import AnalyzeMarketTool


def _build_candles(count: int = 60) -> list[dict[str, float]]:
    candles: list[dict[str, float]] = []
    base = 100.0
    for i in range(count):
        close = base + i * 0.8
        candles.append(
            {
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 10_000 + i * 10,
            }
        )
    return candles


@pytest.mark.unit
def test_analyze_market_tool_includes_phase2_indicators() -> None:
    tool = AnalyzeMarketTool()
    payload = {
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "candles": _build_candles(),
    }

    raw = tool._run(json.dumps(payload))
    data = json.loads(raw)
    indicators = data["indicators"]

    assert "ema_fast" in indicators
    assert "ema_slow" in indicators
    assert "rsi_14" in indicators
    assert "bb_upper" in indicators
    assert "macd_line" in indicators
    assert "macd_signal" in indicators
    assert "macd_histogram" in indicators
    assert "atr_14" in indicators
    assert data["metadata"]["market_regime"] in {"trending", "ranging", "volatile"}
    assert data["metadata"]["candle_count"] == 60


@pytest.mark.unit
def test_analyze_market_tool_requires_minimum_candles() -> None:
    tool = AnalyzeMarketTool()
    payload = {
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "candles": _build_candles(10),
    }

    raw = tool._run(json.dumps(payload))
    data = json.loads(raw)
    assert "error" in data


@pytest.mark.unit
def test_regime_classification_handles_missing_atr() -> None:
    regime = TechnicalAnalyzer()._classify_regime(
        {
            "ema_fast": 110.0,
            "ema_slow": 100.0,
            "bb_middle": 100.0,
            # atr_14 intentionally missing
        }
    )
    assert regime == "trending"


@pytest.mark.unit
def test_regime_classification_respects_configurable_thresholds() -> None:
    indicators = {
        "ema_fast": 101.2,
        "ema_slow": 100.0,
        "bb_middle": 100.0,
        "atr_14": 2.0,
    }
    assert TechnicalAnalyzer()._classify_regime(indicators) == "trending"
    assert (
        TechnicalAnalyzer(volatility_threshold=0.03, trend_threshold=0.02)._classify_regime(
            indicators
        )
        == "ranging"
    )
