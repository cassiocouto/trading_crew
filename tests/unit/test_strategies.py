"""Unit tests for trading strategies."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trading_crew.models.market import MarketAnalysis
from trading_crew.models.signal import SignalType
from trading_crew.strategies.bollinger import BollingerBandsStrategy
from trading_crew.strategies.ema_crossover import EMACrossoverStrategy
from trading_crew.strategies.rsi_range import RSIRangeStrategy


def _make_analysis(**indicator_overrides: float) -> MarketAnalysis:
    """Helper to create a MarketAnalysis with custom indicators."""
    indicators: dict[str, float] = {
        "ema_fast": 60000.0,
        "ema_slow": 59000.0,
        "rsi_14": 50.0,
        "bb_upper": 62000.0,
        "bb_middle": 60000.0,
        "bb_lower": 58000.0,
        "range_high": 65000.0,
        "range_low": 55000.0,
    }
    indicators.update(indicator_overrides)
    return MarketAnalysis(
        symbol="BTC/USDT",
        exchange="binance",
        timestamp=datetime.now(UTC),
        current_price=indicators.get("current_price", 60500.0),
        indicators={k: v for k, v in indicators.items() if k != "current_price"},
    )


@pytest.mark.unit
class TestEMACrossover:
    def test_bullish_signal(self) -> None:
        strategy = EMACrossoverStrategy()
        analysis = _make_analysis(ema_fast=60500.0, ema_slow=59000.0, current_price=60800.0)
        signal = strategy.generate_signal(analysis)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5

    def test_bearish_signal(self) -> None:
        strategy = EMACrossoverStrategy()
        analysis = _make_analysis(ema_fast=58000.0, ema_slow=59000.0, current_price=57500.0)
        signal = strategy.generate_signal(analysis)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL

    def test_no_signal_when_emas_close(self) -> None:
        strategy = EMACrossoverStrategy()
        analysis = _make_analysis(ema_fast=60000.0, ema_slow=59900.0, current_price=59950.0)
        signal = strategy.generate_signal(analysis)
        assert signal is None

    def test_no_signal_when_indicators_missing(self) -> None:
        strategy = EMACrossoverStrategy()
        analysis = MarketAnalysis(
            symbol="BTC/USDT",
            exchange="binance",
            timestamp=datetime.now(UTC),
            current_price=60000.0,
            indicators={},
        )
        assert strategy.generate_signal(analysis) is None


@pytest.mark.unit
class TestBollingerBands:
    def test_buy_at_lower_band(self) -> None:
        strategy = BollingerBandsStrategy()
        analysis = _make_analysis(
            bb_lower=58000.0, bb_middle=60000.0, bb_upper=62000.0, current_price=57500.0
        )
        signal = strategy.generate_signal(analysis)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sell_at_upper_band(self) -> None:
        strategy = BollingerBandsStrategy()
        analysis = _make_analysis(
            bb_lower=58000.0, bb_middle=60000.0, bb_upper=62000.0, current_price=62500.0
        )
        signal = strategy.generate_signal(analysis)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL

    def test_no_signal_in_middle(self) -> None:
        strategy = BollingerBandsStrategy()
        analysis = _make_analysis(
            bb_lower=58000.0, bb_middle=60000.0, bb_upper=62000.0, current_price=60000.0
        )
        assert strategy.generate_signal(analysis) is None


@pytest.mark.unit
class TestRSIRange:
    def test_buy_oversold(self) -> None:
        strategy = RSIRangeStrategy()
        analysis = _make_analysis(
            rsi_14=25.0, range_low=55000.0, range_high=65000.0, current_price=55500.0
        )
        signal = strategy.generate_signal(analysis)

        assert signal is not None
        assert signal.signal_type == SignalType.BUY

    def test_sell_overbought(self) -> None:
        strategy = RSIRangeStrategy()
        analysis = _make_analysis(
            rsi_14=75.0, range_low=55000.0, range_high=65000.0, current_price=64000.0
        )
        signal = strategy.generate_signal(analysis)

        assert signal is not None
        assert signal.signal_type == SignalType.SELL

    def test_no_signal_neutral(self) -> None:
        strategy = RSIRangeStrategy()
        analysis = _make_analysis(
            rsi_14=50.0, range_low=55000.0, range_high=65000.0, current_price=60000.0
        )
        assert strategy.generate_signal(analysis) is None
