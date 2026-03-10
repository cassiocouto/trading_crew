"""Pydantic response schemas for the dashboard API.

These models are deliberately decoupled from the SQLAlchemy ORM to avoid
leaking database internals and allow independent evolution of the API surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    uncertainty_score: float = 0.0
    advisory_ran: bool = False
    advisory_adjustments_json: str = "[]"
    advisory_summary: str = ""


# ---------------------------------------------------------------------------
# System / Agents
# ---------------------------------------------------------------------------


class SystemStatusResponse(BaseModel):
    version: str
    trading_mode: str
    advisory_enabled: bool
    advisory_activation_threshold: float
    total_cycles: int
    circuit_breaker_active: bool
    dashboard_ws_poll_interval_seconds: int


class AgentStatusResponse(BaseModel):
    name: str
    role: str
    last_run_at: datetime | None
    advisory_activations_today: int = 0
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
    slippage_pct: float = 0.001
    advisory_mode: str = "deterministic_only"
    simulation_mode: bool = False


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
    advisory_mode: str = "deterministic_only"
    advisory_activations: int = 0
    advisory_vetoes: int = 0
    avg_uncertainty_score: float = 0.0


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class RiskParamsResponse(BaseModel):
    max_position_size_pct: float
    max_portfolio_exposure_pct: float
    max_drawdown_pct: float
    default_stop_loss_pct: float
    risk_per_trade_pct: float
    min_confidence: float
    cooldown_after_loss_seconds: int
    min_profit_margin_pct: float


class SettingsResponse(BaseModel):
    """Non-secret settings returned by the dashboard API.

    Secret fields (API keys, tokens, database URL) are excluded.
    """

    trading_mode: str
    exchange_id: str
    exchange_sandbox: bool
    exchange_rate_limit_threshold: int
    exchange_rate_limit_cooldown_seconds: int
    symbols: list[str]
    default_timeframe: str
    loop_interval_seconds: int
    execution_poll_interval_seconds: int
    stale_order_cancel_minutes: int
    stale_partial_fill_cancel_minutes: int
    ensemble_enabled: bool
    ensemble_agreement_threshold: float
    stop_loss_method: str
    atr_stop_multiplier: float
    initial_balance_quote: float
    anti_averaging_down: bool
    sell_guard_mode: str
    balance_sync_interval_seconds: int
    balance_drift_alert_threshold_pct: float
    market_data_candle_limit: int
    market_regime_volatility_threshold: float
    market_regime_trend_threshold: float
    sentiment_enabled: bool
    sentiment_fear_greed_enabled: bool
    sentiment_fear_greed_weight: float
    sentiment_request_timeout_seconds: int
    advisory_enabled: bool
    advisory_activation_threshold: float
    advisory_estimated_tokens: int
    uncertainty_weight_volatile_regime: float
    uncertainty_weight_sentiment_extreme: float
    uncertainty_weight_low_sentiment_confidence: float
    uncertainty_weight_strategy_disagreement: float
    uncertainty_weight_drawdown_proximity: float
    uncertainty_weight_regime_change: float
    daily_token_budget_enabled: bool
    daily_token_budget_tokens: int
    token_budget_degrade_mode: str
    save_cycle_history: bool
    stop_loss_monitoring_enabled: bool
    dashboard_enabled: bool
    dashboard_host: str
    dashboard_port: int
    dashboard_cors_origins: list[str]
    dashboard_ws_poll_interval_seconds: int
    telegram_notify_level: str
    crewai_verbose: bool
    log_level: str
    risk: RiskParamsResponse
    # Computed — derived from secret fields, not stored in YAML
    advisory_llm_configured: bool = False


class RiskParamsUpdate(BaseModel):
    """Partial update for risk parameters — all fields optional and typed."""

    max_position_size_pct: float | None = None
    max_portfolio_exposure_pct: float | None = None
    max_drawdown_pct: float | None = None
    default_stop_loss_pct: float | None = None
    risk_per_trade_pct: float | None = None
    min_confidence: float | None = None
    cooldown_after_loss_seconds: int | None = None
    min_profit_margin_pct: float | None = None


class SettingsUpdate(BaseModel):
    """Partial settings update written to settings.yaml.

    Enum fields use ``Literal`` types so Pydantic rejects invalid values before
    they are persisted to disk.  Dashboard-infrastructure fields (host, port,
    CORS origins) are intentionally excluded — they must be edited in
    settings.yaml directly to avoid bricking the dashboard via the dashboard.
    """

    trading_mode: Literal["paper", "live"] | None = None
    exchange_id: str | None = None
    exchange_sandbox: bool | None = None
    exchange_rate_limit_threshold: int | None = None
    exchange_rate_limit_cooldown_seconds: int | None = None
    symbols: list[str] | None = None
    default_timeframe: str | None = None
    loop_interval_seconds: int | None = None
    execution_poll_interval_seconds: int | None = None
    stale_order_cancel_minutes: int | None = None
    stale_partial_fill_cancel_minutes: int | None = None
    ensemble_enabled: bool | None = None
    ensemble_agreement_threshold: float | None = None
    stop_loss_method: Literal["fixed", "atr"] | None = None
    atr_stop_multiplier: float | None = None
    initial_balance_quote: float | None = None
    anti_averaging_down: bool | None = None
    sell_guard_mode: Literal["none", "break_even"] | None = None
    balance_sync_interval_seconds: int | None = None
    balance_drift_alert_threshold_pct: float | None = None
    market_data_candle_limit: int | None = None
    market_regime_volatility_threshold: float | None = None
    market_regime_trend_threshold: float | None = None
    sentiment_enabled: bool | None = None
    sentiment_fear_greed_enabled: bool | None = None
    sentiment_fear_greed_weight: float | None = None
    sentiment_request_timeout_seconds: int | None = None
    advisory_enabled: bool | None = None
    advisory_activation_threshold: float | None = None
    advisory_estimated_tokens: int | None = None
    uncertainty_weight_volatile_regime: float | None = None
    uncertainty_weight_sentiment_extreme: float | None = None
    uncertainty_weight_low_sentiment_confidence: float | None = None
    uncertainty_weight_strategy_disagreement: float | None = None
    uncertainty_weight_drawdown_proximity: float | None = None
    uncertainty_weight_regime_change: float | None = None
    daily_token_budget_enabled: bool | None = None
    daily_token_budget_tokens: int | None = None
    token_budget_degrade_mode: Literal["normal", "budget_stop"] | None = None
    save_cycle_history: bool | None = None
    stop_loss_monitoring_enabled: bool | None = None
    # Dashboard infrastructure fields are intentionally excluded; edit
    # settings.yaml directly for dashboard_host, dashboard_port, etc.
    telegram_notify_level: Literal["all", "trades_only", "critical_only"] | None = None
    crewai_verbose: bool | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    risk: RiskParamsUpdate | None = None


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------


class ControlsResponse(BaseModel):
    """Runtime control state returned by the dashboard API."""

    execution_paused: bool
    advisory_paused: bool
    advisory_available: bool


class ControlsUpdate(BaseModel):
    """Partial controls update written to runtime.yaml."""

    execution_paused: bool | None = None
    advisory_paused: bool | None = None


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


class OHLCVBar(BaseModel):
    """Single OHLCV candlestick bar."""

    timestamp: int  # Unix seconds (lightweight-charts expects this)
    open: float
    high: float
    low: float
    close: float
    volume: float


class SymbolTickerResponse(BaseModel):
    """Latest ticker info for a tracked symbol."""

    symbol: str
    last_price: float | None
    bid: float | None
    ask: float | None
    volume_24h: float | None
    timestamp: str | None
