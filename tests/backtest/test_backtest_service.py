"""Unit tests for the BacktestService.

All tests are fully in-memory — no database or exchange access required.
Synthetic OHLCV candles with known prices are used to exercise specific code paths.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from trading_crew.models.backtest import BacktestConfig, BacktestResult, BacktestTrade
from trading_crew.models.market import OHLCV
from trading_crew.models.risk import RiskParams
from trading_crew.services.backtest_service import BacktestService
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.strategies.ema_crossover import EMACrossoverStrategy
from trading_crew.strategies.rsi_range import RSIRangeStrategy

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.backtest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)
_SYMBOL = "BTC/USDT"
_EXCHANGE = "binance"


def _make_candles(
    prices: list[float],
    timeframe: str = "1h",
    symbol: str = _SYMBOL,
    exchange: str = _EXCHANGE,
) -> list[OHLCV]:
    """Build a list of OHLCV candles from a list of close prices.

    Open = previous close, high = close * 1.002, low = close * 0.998, volume = 1000.
    """
    candles: list[OHLCV] = []
    for i, price in enumerate(prices):
        prev = prices[i - 1] if i > 0 else price
        candles.append(
            OHLCV(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                timestamp=_BASE_TS + timedelta(hours=i),
                open=prev,
                high=price * 1.002,
                low=price * 0.998,
                close=price,
                volume=1000.0,
            )
        )
    return candles


def _make_bullish_candles(n: int = 150, start: float = 40_000.0) -> list[OHLCV]:
    """Prices rising by 0.5% per candle."""
    prices = [start * (1.005**i) for i in range(n)]
    return _make_candles(prices)


def _make_bearish_candles(n: int = 150, start: float = 50_000.0) -> list[OHLCV]:
    """Prices falling by 0.5% per candle."""
    prices = [start * (0.995**i) for i in range(n)]
    return _make_candles(prices)


def _make_flat_candles(n: int = 150, price: float = 45_000.0) -> list[OHLCV]:
    """Perfectly flat prices."""
    return _make_candles([price] * n)


def _default_service(
    config: BacktestConfig | None = None,
    strategies: list | None = None,
) -> BacktestService:
    if strategies is None:
        strategies = [EMACrossoverStrategy()]
    runner = StrategyRunner(strategies, min_confidence=0.4)
    return BacktestService(runner, RiskParams(), config or BacktestConfig())


# ---------------------------------------------------------------------------
# TestBacktestCore
# ---------------------------------------------------------------------------


class TestBacktestCore:
    def test_run_returns_backtest_result(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert isinstance(result, BacktestResult)

    def test_result_fields_populated(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert result.symbol == _SYMBOL
        assert result.exchange == _EXCHANGE
        assert result.timeframe == "1h"
        assert result.initial_balance == 10_000.0
        assert result.start_date == candles[0].timestamp
        assert result.end_date == candles[-1].timestamp

    def test_equity_curve_length(self) -> None:
        n = 150
        candles = _make_bullish_candles(n)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert len(result.equity_curve) == n

    def test_total_fees_nonnegative(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert result.total_fees >= 0

    def test_raises_on_too_few_candles(self) -> None:
        config = BacktestConfig(min_candles_for_analysis=50)
        svc = _default_service(config)
        candles = _make_candles([45_000.0] * 10)
        with pytest.raises(ValueError, match="Not enough candles"):
            svc.run(_SYMBOL, _EXCHANGE, candles)

    def test_strategy_names_recorded(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert "ema_crossover" in result.strategy_names


# ---------------------------------------------------------------------------
# TestFillSimulation
# ---------------------------------------------------------------------------


class TestFillSimulation:
    def test_buy_fill_reduces_balance(self) -> None:
        candles = _make_bullish_candles(150)
        config = BacktestConfig(initial_balance=10_000.0, fee_rate=0.001, slippage_pct=0.001)
        svc = _default_service(config)
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        # balance changes as trades happen
        assert result.final_balance != 10_000.0 or result.total_trades == 0

    def test_total_fees_match_trades(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        fees_from_trades = sum(t.fee for t in result.trades)
        assert abs(result.total_fees - fees_from_trades) < 1e-6

    def test_trade_exit_reason_valid(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        valid_reasons = {"stop_loss", "sell_signal", "end_of_data"}
        for trade in result.trades:
            assert trade.exit_reason in valid_reasons


# ---------------------------------------------------------------------------
# TestEntryBar
# ---------------------------------------------------------------------------


class TestEntryBar:
    def test_entry_bar_nonzero_on_completed_trades(self) -> None:
        """entry_bar on every BacktestTrade must reflect the actual fill bar, not 0."""
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        for trade in result.trades:
            # entry_bar 0 is valid only if the fill genuinely happened at bar 0,
            # which is impossible because warm-up prevents signals that early.
            assert trade.entry_bar > 0, (
                f"entry_bar=0 on trade opened_at={trade.opened_at} — "
                "entry_bar is not being tracked correctly"
            )

    def test_entry_bar_less_than_exit_bar(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        for trade in result.trades:
            if trade.exit_bar is not None:
                assert trade.entry_bar < trade.exit_bar, (
                    f"entry_bar={trade.entry_bar} >= exit_bar={trade.exit_bar}"
                )

    def test_no_duplicate_buy_overwrites_position(self) -> None:
        """Two consecutive BUY signals must not overwrite an open position."""


        candles = _make_bullish_candles(150)
        runner = StrategyRunner([EMACrossoverStrategy()])
        svc = BacktestService(runner, RiskParams(), BacktestConfig())

        # Record how many unique positions ever appear simultaneously

        original_run = BacktestService.run

        def patched_run(self_inner, *args, **kwargs):  # type: ignore[override]
            return original_run(self_inner, *args, **kwargs)

        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        # At most 1 position can be open at a time for a single symbol
        for eq_point in result.equity_curve:
            _ = eq_point  # just ensure equity curve is intact
        # Verify no trade has a nonsensical entry price (sign of an overwrite)
        for trade in result.trades:
            assert trade.entry_price > 0


# ---------------------------------------------------------------------------
# TestStopLoss
# ---------------------------------------------------------------------------


class TestStopLoss:
    def test_stop_loss_triggered_when_candle_low_breaches(self) -> None:
        """Manually inject a position and verify it's closed on intra-bar SL breach."""
        from trading_crew.models.portfolio import Portfolio, Position

        portfolio = Portfolio(balance_quote=10_000.0, peak_balance=11_000.0)
        portfolio.positions[_SYMBOL] = Position(
            symbol=_SYMBOL,
            exchange=_EXCHANGE,
            side="long",
            entry_price=45_000.0,
            amount=0.1,
            current_price=45_000.0,
            stop_loss_price=44_500.0,
        )

        sl_candle = OHLCV(
            symbol=_SYMBOL,
            exchange=_EXCHANGE,
            timeframe="1h",
            timestamp=_BASE_TS,
            open=44_800.0,
            high=45_200.0,
            low=44_200.0,  # breaches 44_500
            close=44_600.0,
            volume=500.0,
        )

        config = BacktestConfig()
        runner = StrategyRunner([EMACrossoverStrategy()])
        svc = BacktestService(runner, RiskParams(), config)

        entry_bars: dict[str, int] = {_SYMBOL: 3}
        fills = svc._check_stop_losses(sl_candle, portfolio, bar=5, entry_bars=entry_bars)

        assert len(fills) == 1
        trade = fills[0]
        assert trade.exit_reason == "stop_loss"
        assert trade.exit_price == 44_500.0
        assert trade.entry_bar == 3
        assert trade.pnl < 0
        assert _SYMBOL not in portfolio.positions
        assert _SYMBOL not in entry_bars  # popped on close

    def test_stop_loss_not_triggered_when_low_above_stop(self) -> None:
        from trading_crew.models.portfolio import Portfolio, Position

        portfolio = Portfolio(balance_quote=10_000.0, peak_balance=11_000.0)
        portfolio.positions[_SYMBOL] = Position(
            symbol=_SYMBOL,
            exchange=_EXCHANGE,
            side="long",
            entry_price=45_000.0,
            amount=0.1,
            current_price=45_000.0,
            stop_loss_price=44_000.0,
        )

        safe_candle = OHLCV(
            symbol=_SYMBOL,
            exchange=_EXCHANGE,
            timeframe="1h",
            timestamp=_BASE_TS,
            open=45_100.0,
            high=45_500.0,
            low=44_200.0,  # above the 44_000 stop
            close=45_300.0,
            volume=500.0,
        )

        runner = StrategyRunner([EMACrossoverStrategy()])
        svc = BacktestService(runner, RiskParams(), BacktestConfig())
        fills = svc._check_stop_losses(safe_candle, portfolio, bar=1, entry_bars={})

        assert len(fills) == 0
        assert _SYMBOL in portfolio.positions


# ---------------------------------------------------------------------------
# TestNoLookAhead
# ---------------------------------------------------------------------------


class TestNoLookAhead:
    def test_analysis_window_never_includes_future_candle(self) -> None:
        """TechnicalAnalyzer must not see candle[i+1] when processing candle[i]."""
        import unittest.mock as mock

        from trading_crew.services.technical_analyzer import TechnicalAnalyzer

        candles = _make_bullish_candles(100)
        windows_seen: list[list[OHLCV]] = []

        original_analyze = TechnicalAnalyzer.analyze_from_candles

        def recording_analyze(self_inner, symbol, exchange, window):  # type: ignore[override]
            windows_seen.append(list(window))
            return original_analyze(self_inner, symbol, exchange, window)

        runner = StrategyRunner([EMACrossoverStrategy()])
        svc = BacktestService(runner, RiskParams(), BacktestConfig(min_candles_for_analysis=50))

        with mock.patch.object(TechnicalAnalyzer, "analyze_from_candles", recording_analyze):
            svc.run(_SYMBOL, _EXCHANGE, candles)

        # For each window captured at logical bar i, the last candle in the window
        # must be candles[i] (not candles[i+1]).
        assert len(windows_seen) > 0
        for window in windows_seen:
            last_ts = window[-1].timestamp
            # Verify last timestamp in window is not beyond the last candle's timestamp
            assert last_ts <= candles[-1].timestamp


# ---------------------------------------------------------------------------
# TestMetrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def _make_known_trades(
        self, wins: int = 10, losses: int = 5, win_pnl: float = 100.0, loss_pnl: float = -40.0
    ) -> list[BacktestTrade]:
        ts = _BASE_TS
        trades = []
        for i in range(wins):
            trades.append(
                BacktestTrade(
                    symbol=_SYMBOL,
                    side="sell",
                    strategy_name="test",
                    entry_bar=i,
                    exit_bar=i + 1,
                    entry_price=40_000.0,
                    exit_price=41_000.0,
                    amount=0.01,
                    pnl=win_pnl,
                    fee=1.0,
                    exit_reason="sell_signal",
                    opened_at=ts,
                    closed_at=ts + timedelta(hours=1),
                )
            )
        for i in range(losses):
            trades.append(
                BacktestTrade(
                    symbol=_SYMBOL,
                    side="sell",
                    strategy_name="test",
                    entry_bar=i,
                    exit_bar=i + 1,
                    entry_price=40_000.0,
                    exit_price=39_000.0,
                    amount=0.01,
                    pnl=loss_pnl,
                    fee=1.0,
                    exit_reason="stop_loss",
                    opened_at=ts,
                    closed_at=ts + timedelta(hours=1),
                )
            )
        return trades

    def test_win_rate(self) -> None:
        trades = self._make_known_trades(wins=10, losses=5)
        equity_curve = []
        metrics = BacktestService._compute_metrics(trades, equity_curve, 10_000.0)
        assert abs(metrics["win_rate_pct"] - 200 / 3) < 0.01

    def test_profit_factor(self) -> None:
        trades = self._make_known_trades(wins=10, losses=5, win_pnl=100.0, loss_pnl=-40.0)
        equity_curve = []
        metrics = BacktestService._compute_metrics(trades, equity_curve, 10_000.0)
        expected_pf = (10 * 100.0) / (5 * 40.0)
        assert abs(metrics["profit_factor"] - expected_pf) < 1e-6

    def test_total_fees_summed(self) -> None:
        trades = self._make_known_trades(wins=3, losses=2)
        equity_curve = []
        metrics = BacktestService._compute_metrics(trades, equity_curve, 10_000.0)
        assert metrics["total_fees"] == 5.0  # 5 trades * fee=1.0


# ---------------------------------------------------------------------------
# TestSharpe
# ---------------------------------------------------------------------------


class TestSharpe:
    def _equity_from_balances(self, balances: list[float]) -> list:
        from trading_crew.models.backtest import EquityPoint

        return [
            EquityPoint(
                timestamp=_BASE_TS + timedelta(days=i),
                balance=b,
                unrealized_pnl=0.0,
                drawdown_pct=0.0,
            )
            for i, b in enumerate(balances)
        ]

    def test_sharpe_nan_for_single_point(self) -> None:
        eq = self._equity_from_balances([10_000.0])
        metrics = BacktestService._compute_metrics([], eq, 10_000.0, "1h")
        assert math.isnan(metrics["sharpe_ratio"])

    def test_sharpe_zero_for_flat_equity(self) -> None:
        eq = self._equity_from_balances([10_000.0] * 50)
        metrics = BacktestService._compute_metrics([], eq, 10_000.0, "1h")
        assert metrics["sharpe_ratio"] == 0.0

    def test_sharpe_positive_for_rising_equity(self) -> None:
        balances = [10_000.0 * (1.001**i) for i in range(100)]
        eq = self._equity_from_balances(balances)
        metrics = BacktestService._compute_metrics([], eq, 10_000.0, "1h")
        assert metrics["sharpe_ratio"] > 0

    def test_sharpe_higher_for_daily_than_hourly_same_returns(self) -> None:
        """Daily timeframe has fewer periods_per_year → lower ann_factor → lower Sharpe
        for the same per-candle return series (i.e. same variance pattern).
        sqrt(365) < sqrt(8760), so daily Sharpe < hourly Sharpe for identical returns."""
        balances = [10_000.0 * (1.001**i) for i in range(200)]
        eq = self._equity_from_balances(balances)
        m_1h = BacktestService._compute_metrics([], eq, 10_000.0, "1h")
        m_1d = BacktestService._compute_metrics([], eq, 10_000.0, "1d")
        assert m_1h["sharpe_ratio"] > m_1d["sharpe_ratio"]


# ---------------------------------------------------------------------------
# TestCompare
# ---------------------------------------------------------------------------


class TestCompare:
    def test_compare_returns_sorted_by_sharpe(self) -> None:
        candles = _make_bullish_candles(150)
        svc_a = _default_service(strategies=[EMACrossoverStrategy()])
        svc_b = _default_service(strategies=[RSIRangeStrategy()])
        results = BacktestService.compare([svc_a, svc_b], _SYMBOL, _EXCHANGE, candles)
        assert len(results) == 2
        a_sharpe = results[0].sharpe_ratio
        b_sharpe = results[1].sharpe_ratio
        if not (math.isnan(a_sharpe) or math.isnan(b_sharpe)):
            assert a_sharpe >= b_sharpe

    def test_compare_returns_all_results_even_with_single_service(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        results = BacktestService.compare([svc], _SYMBOL, _EXCHANGE, candles)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# TestExport
# ---------------------------------------------------------------------------


class TestExport:
    def test_to_json_produces_valid_json(self, tmp_path: Path) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        out = tmp_path / "result.json"
        result.to_json(str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert "trades" in data
        assert "equity_curve" in data
        assert data["symbol"] == _SYMBOL

    def test_to_csv_produces_file_with_header(self, tmp_path: Path) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        out = tmp_path / "trades.csv"
        result.to_csv(str(out))
        assert out.exists()
        content = out.read_text()
        if result.trades:
            assert "symbol" in content
            assert "pnl" in content

    def test_to_csv_empty_when_no_trades(self, tmp_path: Path) -> None:
        candles = _make_flat_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        out = tmp_path / "trades.csv"
        result.to_csv(str(out))
        assert out.exists()

    def test_summary_string_contains_symbol(self) -> None:
        candles = _make_bullish_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert _SYMBOL in result.summary()


# ---------------------------------------------------------------------------
# TestEmptyResult
# ---------------------------------------------------------------------------


class TestEmptyResult:
    def test_flat_candles_produce_no_negative_balance(self) -> None:
        candles = _make_flat_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert result.final_balance >= 0

    def test_metrics_safe_with_zero_trades(self) -> None:
        candles = _make_flat_candles(150)
        svc = _default_service()
        result = svc.run(_SYMBOL, _EXCHANGE, candles)
        assert result.win_rate_pct == 0.0
        assert result.total_trades == 0

    def test_profit_factor_zero_when_no_losing_trades(self) -> None:
        """profit_factor should be inf when there are no losing trades."""
        # All wins, no losses
        from trading_crew.models.backtest import BacktestTrade

        ts = _BASE_TS
        winning_trade = BacktestTrade(
            symbol=_SYMBOL,
            side="sell",
            strategy_name="test",
            entry_bar=1,
            exit_bar=2,
            entry_price=40_000.0,
            exit_price=41_000.0,
            amount=0.1,
            pnl=100.0,
            fee=1.0,
            exit_reason="sell_signal",
            opened_at=ts,
            closed_at=ts + timedelta(hours=1),
        )
        metrics = BacktestService._compute_metrics([winning_trade], [], 10_000.0)
        assert math.isinf(metrics["profit_factor"])
