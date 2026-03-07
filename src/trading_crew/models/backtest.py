"""Backtesting result models.

These models carry the full output of a backtest run: configuration,
individual trade records, equity curve snapshots, and aggregate metrics.
All models use Pydantic BaseModel for consistency with the rest of the codebase.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BacktestAdvisoryMode(StrEnum):
    """Whether the backtest uses pure deterministic signals or also runs advisory."""

    DETERMINISTIC_ONLY = "deterministic_only"
    WITH_ADVISORY = "with_advisory"


class BacktestConfig(BaseModel):
    """Configuration for a single backtest run.

    Attributes:
        initial_balance: Starting quote-currency balance.
        fee_rate: Taker fee as a fraction (0.001 = 0.1%).
        slippage_pct: Simulated fill slippage as a fraction applied to open price.
        min_candles_for_analysis: Minimum candles needed before the first signal.
        candle_window_size: Rolling window of candles passed to TechnicalAnalyzer.
        advisory_mode: Run in deterministic-only or deterministic + advisory mode.
    """

    initial_balance: float = Field(default=10_000.0, gt=0)
    fee_rate: float = Field(default=0.001, ge=0, le=0.1)
    slippage_pct: float = Field(default=0.001, ge=0, le=0.05)
    min_candles_for_analysis: int = Field(default=50, ge=20)
    candle_window_size: int = Field(default=500, ge=50)
    advisory_mode: BacktestAdvisoryMode = BacktestAdvisoryMode.DETERMINISTIC_ONLY
    simulation_mode: bool = Field(
        default=False,
        description="True = full TradingFlow simulation, False = legacy fast backtest",
    )


class BacktestTrade(BaseModel, frozen=True):
    """A single completed (or forced-closed) simulated trade.

    Attributes:
        symbol: Trading pair.
        side: "buy" or "sell".
        strategy_name: Strategy that generated the entry signal.
        entry_bar: Candle index at which the position was opened.
        exit_bar: Candle index at which the position was closed (None if end-of-data).
        entry_price: Actual fill price including slippage.
        exit_price: Actual exit price (stop-loss or signal close price).
        amount: Position size in base currency.
        pnl: Realized profit/loss in quote currency after fees.
        fee: Total fees paid for entry + exit in quote currency.
        exit_reason: One of "stop_loss", "sell_signal", "end_of_data".
        opened_at: Timestamp of the entry candle.
        closed_at: Timestamp of the exit candle (None if not yet closed).
    """

    symbol: str
    side: str
    strategy_name: str
    entry_bar: int
    exit_bar: int | None
    entry_price: float
    exit_price: float | None
    amount: float
    pnl: float
    fee: float
    exit_reason: str
    opened_at: datetime
    closed_at: datetime | None


class EquityPoint(BaseModel, frozen=True):
    """A point-in-time portfolio value snapshot for the equity curve.

    Attributes:
        timestamp: Candle timestamp for this snapshot.
        balance: Total portfolio value (cash + open positions at close price).
        unrealized_pnl: Sum of unrealized P&L from all open positions.
        drawdown_pct: Current drawdown from peak equity as a percentage.
    """

    timestamp: datetime
    balance: float
    unrealized_pnl: float
    drawdown_pct: float


class BacktestResult(BaseModel):
    """Full result of a single backtest run.

    Sharpe ratio convention:
      - Returns are computed as per-day equity changes from equity_curve.
      - Risk-free rate = 0 (standard for crypto).
      - Annualization factor = sqrt(365) (calendar-day basis).
      - Returns float("nan") when fewer than 2 equity points exist.
    """

    symbol: str
    exchange: str
    timeframe: str
    strategy_names: list[str]
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_fees: float
    trades: list[BacktestTrade]
    equity_curve: list[EquityPoint]
    advisory_activations: int = 0
    advisory_vetoes: int = 0
    uncertainty_scores: list[float] = Field(default_factory=list)

    def summary(self) -> str:
        """Return a one-line human-readable summary of the backtest result."""
        sharpe = f"{self.sharpe_ratio:.2f}" if not math.isnan(self.sharpe_ratio) else "n/a"
        return (
            f"{self.symbol} [{self.timeframe}] | "
            f"Return: {self.total_return_pct:+.1f}% | "
            f"Sharpe: {sharpe} | "
            f"MaxDD: {self.max_drawdown_pct:.1f}% | "
            f"WinRate: {self.win_rate_pct:.1f}% | "
            f"Trades: {self.total_trades}"
        )

    def to_json(self, path: str) -> None:
        """Export the full result to a JSON file."""

        def _default(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        data = self.model_dump()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=_default)

    def to_csv(self, path: str) -> None:
        """Export trade records to a CSV file.

        The CSV contains one row per trade. The equity curve is not exported.
        """
        if not self.trades:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write("")
            return

        fieldnames = list(BacktestTrade.model_fields.keys())
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for trade in self.trades:
                writer.writerow(trade.model_dump())
