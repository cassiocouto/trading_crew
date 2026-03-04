"""Backtest REST endpoint.

The handler is a plain ``def`` (not ``async def``) so FastAPI automatically
runs it in a threadpool executor, keeping the event loop free during both the
synchronous DB query and the CPU-bound simulation.
"""

from __future__ import annotations

import math
from datetime import UTC
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import (
    BacktestResultResponse,
    BacktestRunRequest,
    BacktestTradeResponse,
)

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["backtest"])


@router.post("/run", response_model=BacktestResultResponse)
def run_backtest(
    req: BacktestRunRequest,
    db: DatabaseService = Depends(get_db),
) -> BacktestResultResponse:
    """Run a backtest over stored OHLCV data (read-only, no data fetching).

    The handler is synchronous so FastAPI offloads it to a threadpool, keeping
    the event loop unblocked for the DB query and CPU-bound simulation.
    """
    from trading_crew.models.backtest import BacktestConfig
    from trading_crew.models.risk import RiskParams
    from trading_crew.services.backtest_service import BacktestService
    from trading_crew.services.strategy_runner import StrategyRunner
    from trading_crew.strategies.bollinger import BollingerBandsStrategy
    from trading_crew.strategies.ema_crossover import EMACrossoverStrategy
    from trading_crew.strategies.rsi_range import RSIRangeStrategy

    # Normalise datetimes to UTC-aware for range query
    start = req.start if req.start.tzinfo else req.start.replace(tzinfo=UTC)
    end = req.end if req.end.tzinfo else req.end.replace(tzinfo=UTC)

    candles = db.get_ohlcv_range(
        symbol=req.symbol,
        exchange=req.exchange,
        timeframe=req.timeframe,
        start=start,
        end=end,
    )
    if not candles:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No OHLCV data found for {req.symbol}/{req.exchange}/{req.timeframe} "
                f"between {start.date()} and {end.date()}. "
                "Fetch data via CLI first: make backtest-data"
            ),
        )

    config = BacktestConfig(
        initial_balance=req.initial_balance,
        fee_rate=req.fee_rate,
        slippage_pct=req.slippage_pct,
    )
    risk_params = RiskParams()

    # Build strategies from optional names list; default to EMA + RSI
    _all = {
        "ema_crossover": EMACrossoverStrategy,
        "rsi_range": RSIRangeStrategy,
        "bollinger": BollingerBandsStrategy,
    }
    if req.strategy_names:
        strategies = [_all[n]() for n in req.strategy_names if n in _all]
        if not strategies:
            strategies = [EMACrossoverStrategy()]
    else:
        strategies = [EMACrossoverStrategy()]

    runner = StrategyRunner(strategies)
    service = BacktestService(runner, risk_params, config)

    result = service.run(
        symbol=req.symbol,
        exchange=req.exchange,
        candles=candles,
        timeframe=req.timeframe,
    )

    if result is None:
        raise HTTPException(status_code=422, detail="Backtest produced no result")

    trades = [
        BacktestTradeResponse(
            symbol=t.symbol,
            entry_bar=t.entry_bar,
            exit_bar=t.exit_bar if t.exit_bar is not None else -1,
            entry_price=t.entry_price,
            exit_price=t.exit_price if t.exit_price is not None else 0.0,
            amount=t.amount,
            pnl=t.pnl,
            fees=t.fee,
            entry_time=t.opened_at,
            exit_time=t.closed_at,
        )
        for t in result.trades
    ]

    sharpe = result.sharpe_ratio if not math.isnan(result.sharpe_ratio) else 0.0
    strategy_name = result.strategy_names[0] if result.strategy_names else "combined"

    return BacktestResultResponse(
        strategy_name=strategy_name,
        symbol=result.symbol,
        timeframe=result.timeframe,
        total_return_pct=result.total_return_pct,
        sharpe_ratio=sharpe,
        max_drawdown_pct=result.max_drawdown_pct,
        win_rate=result.win_rate_pct / 100.0,
        profit_factor=result.profit_factor,
        total_trades=result.total_trades,
        total_fees=result.total_fees,
        final_balance=result.final_balance,
        trades=trades,
    )
