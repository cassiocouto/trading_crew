"""Unit tests for the SellGuard implementations."""

from __future__ import annotations

import pytest

from trading_crew.models.risk import RiskParams
from trading_crew.risk.sell_guard import AllowAllSellGuard, BreakEvenSellGuard


@pytest.fixture()
def risk_params() -> RiskParams:
    return RiskParams()  # min_profit_margin_pct = 0.0 by default


@pytest.fixture()
def risk_params_with_margin() -> RiskParams:
    return RiskParams(min_profit_margin_pct=1.0)  # require 1% above break-even


class TestAllowAllSellGuard:
    def test_always_allows(self, risk_params: RiskParams) -> None:
        guard = AllowAllSellGuard()
        ok, reason = guard.evaluate("BTC/USDT", 50_000.0, None, risk_params)
        assert ok is True
        assert reason == "no guard"

    def test_allows_even_with_break_even(self, risk_params: RiskParams) -> None:
        guard = AllowAllSellGuard()
        ok, _reason = guard.evaluate("BTC/USDT", 40_000.0, 50_000.0, risk_params)
        assert ok is True


class TestBreakEvenSellGuard:
    def test_no_break_even_allows(self, risk_params: RiskParams) -> None:
        """When no prior filled BUY exists, sell is allowed."""
        guard = BreakEvenSellGuard()
        ok, reason = guard.evaluate("BTC/USDT", 50_000.0, None, risk_params)
        assert ok is True
        assert "no break-even" in reason

    def test_price_above_break_even_approved(self, risk_params: RiskParams) -> None:
        guard = BreakEvenSellGuard()
        ok, reason = guard.evaluate("BTC/USDT", 50_100.0, 50_000.0, risk_params)
        assert ok is True
        assert "clears" in reason

    def test_price_exactly_at_break_even_approved(self, risk_params: RiskParams) -> None:
        guard = BreakEvenSellGuard()
        ok, _reason = guard.evaluate("BTC/USDT", 50_000.0, 50_000.0, risk_params)
        assert ok is True

    def test_price_below_break_even_rejected(self, risk_params: RiskParams) -> None:
        guard = BreakEvenSellGuard()
        ok, reason = guard.evaluate("BTC/USDT", 49_900.0, 50_000.0, risk_params)
        assert ok is False
        assert "holding" in reason
        assert "49900" in reason or "49,900" in reason or "49900.0000" in reason

    def test_price_above_margin_approved(self, risk_params_with_margin: RiskParams) -> None:
        """break_even=100, margin=1% → min_sell=101; price=102 → APPROVED."""
        guard = BreakEvenSellGuard()
        ok, _reason = guard.evaluate("BTC/USDT", 102.0, 100.0, risk_params_with_margin)
        assert ok is True

    def test_price_between_break_even_and_margin_rejected(
        self, risk_params_with_margin: RiskParams
    ) -> None:
        """break_even=100, margin=1% → min_sell=101; price=100.5 → REJECTED."""
        guard = BreakEvenSellGuard()
        ok, reason = guard.evaluate("BTC/USDT", 100.5, 100.0, risk_params_with_margin)
        assert ok is False
        assert "margin" in reason

    def test_reason_includes_margin_when_nonzero(self, risk_params_with_margin: RiskParams) -> None:
        guard = BreakEvenSellGuard()
        _, reason = guard.evaluate("BTC/USDT", 99.0, 100.0, risk_params_with_margin)
        assert "margin" in reason

    def test_reason_omits_margin_when_zero(self, risk_params: RiskParams) -> None:
        guard = BreakEvenSellGuard()
        _, reason = guard.evaluate("BTC/USDT", 99.0, 100.0, risk_params)
        assert "margin" not in reason
