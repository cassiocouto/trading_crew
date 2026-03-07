"""Tests for apply_advisory_directives()."""

from __future__ import annotations

import pytest

from trading_crew.models.advisory import (
    AdjustmentAction,
    AdvisoryAdjustment,
    AdvisoryResult,
    apply_advisory_directives,
)
from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal


def _signal(symbol: str = "BTC/USDT", confidence: float = 0.8) -> TradeSignal:
    return TradeSignal(
        symbol=symbol,
        exchange="binance",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        confidence=confidence,
        strategy_name="test",
        entry_price=50_000.0,
    )


def _result(*adjustments: AdvisoryAdjustment) -> AdvisoryResult:
    return AdvisoryResult(adjustments=list(adjustments), summary="test", uncertainty_score=0.7)


class TestVetoSignal:
    def test_veto_removes_signal(self) -> None:
        signals = [_signal("BTC/USDT"), _signal("ETH/USDT")]
        result = _result(
            AdvisoryAdjustment(action=AdjustmentAction.VETO_SIGNAL, symbol="BTC/USDT", reason="x")
        )
        adjusted = apply_advisory_directives(signals, result)
        assert len(adjusted) == 1
        assert adjusted[0].symbol == "ETH/USDT"

    def test_veto_nonexistent_symbol_is_noop(self) -> None:
        signals = [_signal("BTC/USDT")]
        result = _result(
            AdvisoryAdjustment(action=AdjustmentAction.VETO_SIGNAL, symbol="SOL/USDT", reason="x")
        )
        adjusted = apply_advisory_directives(signals, result)
        assert len(adjusted) == 1


class TestAdjustConfidence:
    def test_confidence_override(self) -> None:
        signals = [_signal(confidence=0.9)]
        result = _result(
            AdvisoryAdjustment(
                action=AdjustmentAction.ADJUST_CONFIDENCE,
                symbol="BTC/USDT",
                reason="x",
                params={"new_confidence": 0.4},
            )
        )
        adjusted = apply_advisory_directives(signals, result)
        assert len(adjusted) == 1
        assert adjusted[0].confidence == pytest.approx(0.4)

    def test_confidence_clamped_to_range(self) -> None:
        signals = [_signal()]
        result = _result(
            AdvisoryAdjustment(
                action=AdjustmentAction.ADJUST_CONFIDENCE,
                symbol="BTC/USDT",
                reason="x",
                params={"new_confidence": 1.5},
            )
        )
        adjusted = apply_advisory_directives(signals, result)
        assert adjusted[0].confidence == pytest.approx(1.0)


class TestTightenStopLoss:
    def test_stop_loss_set_from_entry_price(self) -> None:
        signals = [_signal()]
        result = _result(
            AdvisoryAdjustment(
                action=AdjustmentAction.TIGHTEN_STOP_LOSS,
                symbol="BTC/USDT",
                reason="x",
                params={"stop_loss_pct": 0.02},
            )
        )
        adjusted = apply_advisory_directives(signals, result)
        expected_sl = 50_000.0 * (1.0 - 0.02)
        assert adjusted[0].stop_loss_price == pytest.approx(expected_sl)


class TestSitOut:
    def test_sit_out_clears_all_signals(self) -> None:
        signals = [_signal("BTC/USDT"), _signal("ETH/USDT")]
        result = _result(AdvisoryAdjustment(action=AdjustmentAction.SIT_OUT, reason="macro risk"))
        adjusted = apply_advisory_directives(signals, result)
        assert adjusted == []


class TestNoAdjustments:
    def test_empty_adjustments_returns_originals(self) -> None:
        signals = [_signal()]
        result = AdvisoryResult(adjustments=[], summary="ok", uncertainty_score=0.5)
        adjusted = apply_advisory_directives(signals, result)
        assert len(adjusted) == 1
        assert adjusted[0] is signals[0]


class TestCombinedAdjustments:
    def test_veto_plus_confidence(self) -> None:
        signals = [_signal("BTC/USDT"), _signal("ETH/USDT", confidence=0.9)]
        result = _result(
            AdvisoryAdjustment(action=AdjustmentAction.VETO_SIGNAL, symbol="BTC/USDT", reason="x"),
            AdvisoryAdjustment(
                action=AdjustmentAction.ADJUST_CONFIDENCE,
                symbol="ETH/USDT",
                reason="lower",
                params={"new_confidence": 0.5},
            ),
        )
        adjusted = apply_advisory_directives(signals, result)
        assert len(adjusted) == 1
        assert adjusted[0].symbol == "ETH/USDT"
        assert adjusted[0].confidence == pytest.approx(0.5)
