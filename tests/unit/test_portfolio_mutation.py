"""Unit tests for portfolio mutation and rollback helpers in main.py."""

from __future__ import annotations

import pytest

from trading_crew.main import _apply_single_order_to_portfolio, _rollback_portfolio
from trading_crew.models.cycle import CycleState
from trading_crew.models.order import OrderRequest, OrderSide, OrderType
from trading_crew.models.portfolio import Portfolio, Position


def _make_portfolio(
    balance: float = 10_000.0,
    peak: float = 10_000.0,
    positions: dict[str, Position] | None = None,
) -> Portfolio:
    return Portfolio(
        balance_quote=balance,
        peak_balance=peak,
        positions=positions or {},
    )


def _buy_request(
    symbol: str = "BTC/USDT",
    amount: float = 0.1,
    price: float = 50_000.0,
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        exchange="binance",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=amount,
        price=price,
        strategy_name="test",
    )


def _sell_request(
    symbol: str = "BTC/USDT",
    amount: float = 0.1,
    price: float = 50_000.0,
) -> OrderRequest:
    return OrderRequest(
        symbol=symbol,
        exchange="binance",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        amount=amount,
        price=price,
        strategy_name="test",
    )


# -- BUY reservation ----------------------------------------------------------


class TestBuyReservation:
    def test_buy_deducts_balance_and_creates_position(self) -> None:
        portfolio = _make_portfolio(balance=10_000.0)
        req = _buy_request(amount=0.1, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        assert portfolio.balance_quote == pytest.approx(5_000.0)
        assert "BTC/USDT" in portfolio.positions
        pos = portfolio.positions["BTC/USDT"]
        assert pos.amount == pytest.approx(0.1)
        assert pos.entry_price == pytest.approx(50_000.0)

    def test_buy_caps_at_available_balance_and_scales_amount(self) -> None:
        """Balance=2000, order=0.1 BTC@50k (notional=5000).

        Only 2000 should be spent; position amount must be 2000/50000=0.04,
        NOT the full 0.1. Total balance must not exceed initial 2000.
        """
        portfolio = _make_portfolio(balance=2_000.0, peak=2_000.0)
        req = _buy_request(amount=0.1, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        assert portfolio.balance_quote == pytest.approx(0.0)
        assert "BTC/USDT" in portfolio.positions
        pos = portfolio.positions["BTC/USDT"]
        assert pos.amount == pytest.approx(0.04)
        assert pos.entry_price == pytest.approx(50_000.0)
        assert portfolio.total_balance == pytest.approx(2_000.0)

    def test_buy_extends_existing_position(self) -> None:
        portfolio = _make_portfolio(
            balance=10_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=48_000.0,
                    amount=0.1,
                    current_price=50_000.0,
                ),
            },
        )
        req = _buy_request(amount=0.1, price=52_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        pos = portfolio.positions["BTC/USDT"]
        assert pos.amount == pytest.approx(0.2)
        expected_avg = (48_000.0 * 0.1 + 52_000.0 * 0.1) / 0.2
        assert pos.entry_price == pytest.approx(expected_avg)

    def test_buy_extend_capped_scales_amount_proportionally(self) -> None:
        """Extending a position with insufficient balance scales the addition."""
        portfolio = _make_portfolio(
            balance=1_000.0,
            peak=6_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=0.1,
                    current_price=50_000.0,
                ),
            },
        )
        req = _buy_request(amount=0.1, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        assert portfolio.balance_quote == pytest.approx(0.0)
        pos = portfolio.positions["BTC/USDT"]
        added = 1_000.0 / 50_000.0
        assert pos.amount == pytest.approx(0.1 + added)

    def test_buy_with_zero_balance_is_noop(self) -> None:
        portfolio = _make_portfolio(balance=0.0)
        req = _buy_request(amount=0.1, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        assert portfolio.balance_quote == pytest.approx(0.0)
        assert "BTC/USDT" not in portfolio.positions


# -- SELL reservation ----------------------------------------------------------


class TestSellReservation:
    def test_sell_credits_balance_and_removes_position(self) -> None:
        portfolio = _make_portfolio(
            balance=5_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=0.1,
                    current_price=50_000.0,
                ),
            },
        )
        req = _sell_request(amount=0.1, price=55_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        assert portfolio.balance_quote == pytest.approx(5_000.0 + 0.1 * 55_000.0)
        assert "BTC/USDT" not in portfolio.positions

    def test_sell_partial_reduces_position(self) -> None:
        portfolio = _make_portfolio(
            balance=5_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=1.0,
                    current_price=50_000.0,
                ),
            },
        )
        req = _sell_request(amount=0.3, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        pos = portfolio.positions["BTC/USDT"]
        assert pos.amount == pytest.approx(0.7)
        assert portfolio.balance_quote == pytest.approx(5_000.0 + 0.3 * 50_000.0)

    def test_sell_without_position_is_ignored(self) -> None:
        portfolio = _make_portfolio(balance=10_000.0)
        req = _sell_request(amount=0.1, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        assert portfolio.balance_quote == pytest.approx(10_000.0)
        assert "BTC/USDT" not in portfolio.positions

    def test_sell_more_than_held_is_capped(self) -> None:
        """SELL amount exceeding held amount should only sell what is held."""
        portfolio = _make_portfolio(
            balance=5_000.0,
            positions={
                "BTC/USDT": Position(
                    symbol="BTC/USDT",
                    exchange="binance",
                    entry_price=50_000.0,
                    amount=0.05,
                    current_price=50_000.0,
                ),
            },
        )
        req = _sell_request(amount=0.1, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        expected_credit = 0.05 * 50_000.0
        assert portfolio.balance_quote == pytest.approx(5_000.0 + expected_credit)
        assert "BTC/USDT" not in portfolio.positions

    def test_sell_different_symbol_is_ignored(self) -> None:
        portfolio = _make_portfolio(
            balance=5_000.0,
            positions={
                "ETH/USDT": Position(
                    symbol="ETH/USDT",
                    exchange="binance",
                    entry_price=3_000.0,
                    amount=1.0,
                    current_price=3_000.0,
                ),
            },
        )
        req = _sell_request(symbol="BTC/USDT", amount=0.1, price=50_000.0)

        _apply_single_order_to_portfolio(portfolio, req)

        assert portfolio.balance_quote == pytest.approx(5_000.0)
        assert "ETH/USDT" in portfolio.positions


# -- Rollback -----------------------------------------------------------------


class TestRollbackPortfolio:
    def test_rollback_restores_snapshot(self) -> None:
        portfolio = _make_portfolio(balance=10_000.0, peak=10_000.0)
        snapshot = portfolio.model_copy(deep=True)

        req = _buy_request(amount=0.1, price=50_000.0)
        _apply_single_order_to_portfolio(portfolio, req)
        assert portfolio.balance_quote == pytest.approx(5_000.0)

        state = CycleState(cycle_number=1, symbols=["BTC/USDT"])
        state.order_requests.append(req)

        _rollback_portfolio(portfolio, snapshot, state)

        assert portfolio.balance_quote == pytest.approx(10_000.0)
        assert portfolio.peak_balance == pytest.approx(10_000.0)
        assert "BTC/USDT" not in portfolio.positions

    def test_rollback_noop_when_no_snapshot(self) -> None:
        portfolio = _make_portfolio(balance=5_000.0)
        state = CycleState(cycle_number=1, symbols=["BTC/USDT"])
        state.order_requests.append(_buy_request())

        _rollback_portfolio(portfolio, None, state)

        assert portfolio.balance_quote == pytest.approx(5_000.0)

    def test_rollback_noop_when_no_order_requests(self) -> None:
        portfolio = _make_portfolio(balance=10_000.0)
        snapshot = portfolio.model_copy(deep=True)

        portfolio.balance_quote = 3_000.0
        state = CycleState(cycle_number=1, symbols=["BTC/USDT"])

        _rollback_portfolio(portfolio, snapshot, state)

        assert portfolio.balance_quote == pytest.approx(3_000.0)

    def test_rollback_after_execution_failure_scenario(self) -> None:
        """Simulates: strategy reserves capital, execution raises, rollback."""
        portfolio = _make_portfolio(balance=10_000.0, peak=10_000.0)
        snapshot = portfolio.model_copy(deep=True)

        buy = _buy_request(amount=0.05, price=50_000.0)
        _apply_single_order_to_portfolio(portfolio, buy)
        assert portfolio.balance_quote == pytest.approx(7_500.0)
        assert "BTC/USDT" in portfolio.positions

        state = CycleState(cycle_number=1, symbols=["BTC/USDT"])
        state.order_requests.append(buy)

        _rollback_portfolio(portfolio, snapshot, state)

        assert portfolio.balance_quote == pytest.approx(10_000.0)
        assert "BTC/USDT" not in portfolio.positions
        assert portfolio.peak_balance == pytest.approx(10_000.0)

    def test_rollback_safe_when_exception_before_snapshot_creation(self) -> None:
        """Regression: exception in market stage before snapshot is taken.

        portfolio_snapshot is initialized to None at the top of the try block.
        If the market pipeline throws before the strategy stage sets the real
        snapshot, the except handler calls _rollback_portfolio(portfolio, None, state).
        This must be a safe no-op — no UnboundLocalError, no state corruption.
        """
        portfolio = _make_portfolio(balance=8_000.0, peak=8_000.0)
        original_balance = portfolio.balance_quote

        state = CycleState(cycle_number=1, symbols=["BTC/USDT"])
        state.order_requests.append(_buy_request())

        _rollback_portfolio(portfolio, None, state)

        assert portfolio.balance_quote == pytest.approx(original_balance)
        assert portfolio.peak_balance == pytest.approx(8_000.0)
        assert len(portfolio.positions) == 0
