"""Integration test: backtest regression guard.

Runs the EMA-crossover strategy on a fixed set of bullish OHLCV candles
and asserts that the key metrics stay within expected bounds. This test
protects against regressions when strategy logic or the backtest engine
is refactored.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import _make_bullish_candles
from trading_crew.models.backtest import BacktestConfig
from trading_crew.models.risk import RiskParams
from trading_crew.services.backtest_service import BacktestService
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.strategies.ema_crossover import EMACrossoverStrategy

SYMBOL = "BTC/USDT"
EXCHANGE = "binance"


@pytest.mark.integration
def test_backtest_regression_ema_crossover():
    """EMA-crossover backtest on bullish fixture must stay within metric bounds.

    Bounds are intentionally loose to allow tuning without constantly updating
    this test — the purpose is to guard against regressions (e.g. the backtest
    producing zero trades or a NaN Sharpe ratio).
    """
    candles = _make_bullish_candles(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        n=120,
        start_price=40_000.0,
    )

    strategy_runner = StrategyRunner(
        strategies=[EMACrossoverStrategy()],
        min_confidence=0.0,
        ensemble=False,
    )
    risk_params = RiskParams(
        max_position_pct=0.2,
        max_drawdown_pct=0.5,
        min_confidence=0.0,
    )
    config = BacktestConfig(
        initial_balance=10_000.0,
        slippage_pct=0.001,
        fee_rate=0.001,
    )
    service = BacktestService(
        strategy_runner=strategy_runner,
        risk_params=risk_params,
        config=config,
    )

    result = service.run(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        candles=candles,
        timeframe="1h",
    )

    assert result.total_trades >= 1, f"Expected at least 1 trade, got {result.total_trades}"
    assert result.sharpe_ratio == result.sharpe_ratio, "Sharpe ratio must not be NaN"
    assert result.win_rate_pct >= 0.0, "Win rate must be non-negative"
    assert result.win_rate_pct <= 100.0, "Win rate must not exceed 100"


@pytest.mark.integration
def test_backtest_regression_metrics_within_reasonable_bounds():
    """Detailed metric bounds check on a longer bullish fixture."""
    candles = _make_bullish_candles(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        n=200,
        start_price=40_000.0,
    )

    strategy_runner = StrategyRunner(
        strategies=[EMACrossoverStrategy()],
        min_confidence=0.0,
        ensemble=False,
    )
    risk_params = RiskParams(
        max_position_pct=0.1,
        max_drawdown_pct=0.5,
        min_confidence=0.0,
    )
    service = BacktestService(
        strategy_runner=strategy_runner,
        risk_params=risk_params,
    )

    result = service.run(
        symbol=SYMBOL,
        exchange=EXCHANGE,
        candles=candles,
        timeframe="1h",
    )

    # These bounds are intentionally wide — the test guards against complete
    # breakage, not against strategy performance variations.
    assert result.total_trades >= 1, "Strategy must produce at least 1 trade"
    # The Sharpe ratio is not bounded above on perfectly bullish synthetic data;
    # only guard against NaN and clearly pathological negative values.
    assert result.sharpe_ratio == result.sharpe_ratio, "Sharpe ratio must not be NaN"
    assert result.sharpe_ratio > -100.0, f"Sharpe ratio implausibly negative: {result.sharpe_ratio}"
    assert 0.0 <= result.win_rate_pct <= 100.0, f"Win rate out of [0, 100]: {result.win_rate_pct}"
