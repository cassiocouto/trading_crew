"""Pydantic response schemas for the dashboard API.

These models are deliberately decoupled from the SQLAlchemy ORM to avoid
leaking database internals and allow independent evolution of the API surface.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class PositionResponse(BaseModel):
    symbol: str
    entry_price: float
    amount: float
    current_price: float | None
    stop_loss_price: float | None
    take_profit_price: float | None
    strategy_name: str


class PortfolioResponse(BaseModel):
    balance_quote: float
    realized_pnl: float
    total_fees: float
    num_positions: int
    positions: dict[str, PositionResponse]
    timestamp: datetime | None


class PnLPointResponse(BaseModel):
    timestamp: datetime
    total_balance_quote: float
    unrealized_pnl: float
    realized_pnl: float
    total_fees: float
    num_open_positions: int
    drawdown_pct: float


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class OrderResponse(BaseModel):
    id: int
    exchange_order_id: str
    symbol: str
    exchange: str
    side: str
    order_type: str
    status: str
    requested_amount: float
    filled_amount: float
    requested_price: float | None
    average_fill_price: float | None
    stop_loss_price: float | None
    take_profit_price: float | None
    total_fee: float
    strategy_name: str
    signal_confidence: float
    created_at: datetime
    updated_at: datetime


class FailedOrderResponse(BaseModel):
    id: int
    symbol: str
    exchange: str
    side: str
    order_type: str
    requested_amount: float
    requested_price: float | None
    strategy_name: str
    error_reason: str
    resolved: bool
    timestamp: datetime


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


class SignalResponse(BaseModel):
    id: int
    symbol: str
    exchange: str
    signal_type: str
    strength: str
    confidence: float
    strategy_name: str
    entry_price: float
    stop_loss_price: float | None
    take_profit_price: float | None
    reason: str
    risk_verdict: str | None
    timestamp: datetime


class StrategyStatsResponse(BaseModel):
    strategy_name: str
    total_signals: int
    buy_signals: int
    sell_signals: int
    avg_confidence: float
    orders_placed: int
    orders_filled: int


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


class CycleResponse(BaseModel):
    id: int
    cycle_number: int
    timestamp: datetime
    num_signals: int
    num_orders_placed: int
    num_orders_filled: int
    num_orders_cancelled: int
    num_orders_failed: int
    portfolio_balance: float
    realized_pnl: float
    circuit_breaker_tripped: bool
    errors_json: str


# ---------------------------------------------------------------------------
# System / Agents
# ---------------------------------------------------------------------------


class SystemStatusResponse(BaseModel):
    version: str
    trading_mode: str
    market_pipeline_mode: str
    strategy_pipeline_mode: str
    execution_pipeline_mode: str
    total_cycles: int
    circuit_breaker_active: bool
    dashboard_ws_poll_interval_seconds: int


class AgentStatusResponse(BaseModel):
    name: str
    pipeline_mode: str
    last_run_at: datetime | None
    tokens_estimated: int
    is_active: bool


# ---------------------------------------------------------------------------
# WebSocket event envelope
# ---------------------------------------------------------------------------


class WsEvent(BaseModel):
    type: str
    payload: dict  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


class BacktestRunRequest(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    start: datetime
    end: datetime
    initial_balance: float = 10_000.0
    strategy_names: list[str] | None = None
    fee_rate: float = 0.001
    slippage_pct: float = 0.0005


class BacktestTradeResponse(BaseModel):
    symbol: str
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    fees: float
    entry_time: datetime | None
    exit_time: datetime | None


class BacktestResultResponse(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    total_trades: int
    total_fees: float
    final_balance: float
    trades: list[BacktestTradeResponse]
