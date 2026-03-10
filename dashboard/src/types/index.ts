// TypeScript interfaces mirroring the FastAPI Pydantic schemas.

export interface PositionResponse {
  symbol: string;
  entry_price: number;
  amount: number;
  current_price: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  strategy_name: string;
}

export interface PortfolioResponse {
  balance_quote: number;
  realized_pnl: number;
  total_fees: number;
  num_positions: number;
  positions: Record<string, PositionResponse>;
  timestamp: string | null;
}

export interface PnLPointResponse {
  timestamp: string;
  total_balance_quote: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_fees: number;
  num_open_positions: number;
  drawdown_pct: number;
}

export interface OrderResponse {
  id: number;
  exchange_order_id: string;
  symbol: string;
  exchange: string;
  side: string;
  order_type: string;
  status: string;
  requested_amount: number;
  filled_amount: number;
  requested_price: number | null;
  average_fill_price: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  total_fee: number;
  strategy_name: string;
  signal_confidence: number;
  created_at: string;
  updated_at: string;
}

export interface FailedOrderResponse {
  id: number;
  symbol: string;
  exchange: string;
  side: string;
  order_type: string;
  requested_amount: number;
  requested_price: number | null;
  strategy_name: string;
  error_reason: string;
  resolved: boolean;
  timestamp: string;
}

export interface SignalResponse {
  id: number;
  symbol: string;
  exchange: string;
  signal_type: string;
  strength: string;
  confidence: number;
  strategy_name: string;
  entry_price: number;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  reason: string;
  risk_verdict: string | null;
  timestamp: string;
}

export interface StrategyStatsResponse {
  strategy_name: string;
  total_signals: number;
  buy_signals: number;
  sell_signals: number;
  avg_confidence: number;
  orders_placed: number;
  orders_filled: number;
}

export interface CycleResponse {
  id: number;
  cycle_number: number;
  timestamp: string;
  num_signals: number;
  num_orders_placed: number;
  num_orders_filled: number;
  num_orders_cancelled: number;
  num_orders_failed: number;
  portfolio_balance: number;
  realized_pnl: number;
  circuit_breaker_tripped: boolean;
  errors_json: string;
  uncertainty_score: number;
  advisory_ran: boolean;
  advisory_adjustments_json: string;
  advisory_summary: string;
}

export interface SystemStatusResponse {
  version: string;
  trading_mode: string;
  advisory_enabled: boolean;
  advisory_activation_threshold: number;
  total_cycles: number;
  circuit_breaker_active: boolean;
  dashboard_ws_poll_interval_seconds: number;
}

export interface AgentStatusResponse {
  name: string;
  role: string;
  last_run_at: string | null;
  advisory_activations_today: number;
  is_active: boolean;
}

export interface WsEvent {
  type: string;
  payload: Record<string, unknown>;
}

export interface BacktestTradeResponse {
  symbol: string;
  entry_bar: number;
  exit_bar: number;
  entry_price: number;
  exit_price: number;
  amount: number;
  pnl: number;
  fees: number;
  entry_time: string | null;
  exit_time: string | null;
}

export interface BacktestResultResponse {
  strategy_name: string;
  symbol: string;
  timeframe: string;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  total_fees: number;
  final_balance: number;
  trades: BacktestTradeResponse[];
  advisory_mode: string;
  advisory_activations: number;
  advisory_vetoes: number;
  avg_uncertainty_score: number;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export interface RiskParamsResponse {
  max_position_size_pct: number;
  max_portfolio_exposure_pct: number;
  max_drawdown_pct: number;
  default_stop_loss_pct: number;
  risk_per_trade_pct: number;
  min_confidence: number;
  cooldown_after_loss_seconds: number;
  min_profit_margin_pct: number;
}

export interface SettingsResponse {
  trading_mode: string;
  exchange_id: string;
  exchange_sandbox: boolean;
  exchange_rate_limit_threshold: number;
  exchange_rate_limit_cooldown_seconds: number;
  symbols: string[];
  default_timeframe: string;
  loop_interval_seconds: number;
  execution_poll_interval_seconds: number;
  stale_order_cancel_minutes: number;
  stale_partial_fill_cancel_minutes: number;
  ensemble_enabled: boolean;
  ensemble_agreement_threshold: number;
  stop_loss_method: string;
  atr_stop_multiplier: number;
  initial_balance_quote: number;
  anti_averaging_down: boolean;
  sell_guard_mode: string;
  balance_sync_interval_seconds: number;
  balance_drift_alert_threshold_pct: number;
  market_data_candle_limit: number;
  market_regime_volatility_threshold: number;
  market_regime_trend_threshold: number;
  sentiment_enabled: boolean;
  sentiment_fear_greed_enabled: boolean;
  sentiment_fear_greed_weight: number;
  sentiment_request_timeout_seconds: number;
  advisory_enabled: boolean;
  advisory_activation_threshold: number;
  advisory_estimated_tokens: number;
  uncertainty_weight_volatile_regime: number;
  uncertainty_weight_sentiment_extreme: number;
  uncertainty_weight_low_sentiment_confidence: number;
  uncertainty_weight_strategy_disagreement: number;
  uncertainty_weight_drawdown_proximity: number;
  uncertainty_weight_regime_change: number;
  daily_token_budget_enabled: boolean;
  daily_token_budget_tokens: number;
  token_budget_degrade_mode: string;
  save_cycle_history: boolean;
  stop_loss_monitoring_enabled: boolean;
  dashboard_enabled: boolean;
  dashboard_host: string;
  dashboard_port: number;
  dashboard_cors_origins: string[];
  dashboard_ws_poll_interval_seconds: number;
  telegram_notify_level: string;
  crewai_verbose: boolean;
  log_level: string;
  risk: RiskParamsResponse;
  advisory_llm_configured: boolean;
}

export interface RiskParamsUpdate {
  max_position_size_pct?: number;
  max_portfolio_exposure_pct?: number;
  max_drawdown_pct?: number;
  default_stop_loss_pct?: number;
  risk_per_trade_pct?: number;
  min_confidence?: number;
  cooldown_after_loss_seconds?: number;
  min_profit_margin_pct?: number;
}

export interface SettingsUpdate {
  trading_mode?: "paper" | "live";
  exchange_id?: string;
  exchange_sandbox?: boolean;
  exchange_rate_limit_threshold?: number;
  exchange_rate_limit_cooldown_seconds?: number;
  symbols?: string[];
  default_timeframe?: string;
  loop_interval_seconds?: number;
  execution_poll_interval_seconds?: number;
  stale_order_cancel_minutes?: number;
  stale_partial_fill_cancel_minutes?: number;
  ensemble_enabled?: boolean;
  ensemble_agreement_threshold?: number;
  stop_loss_method?: "fixed" | "atr";
  atr_stop_multiplier?: number;
  initial_balance_quote?: number;
  anti_averaging_down?: boolean;
  sell_guard_mode?: "none" | "break_even";
  balance_sync_interval_seconds?: number;
  balance_drift_alert_threshold_pct?: number;
  market_data_candle_limit?: number;
  market_regime_volatility_threshold?: number;
  market_regime_trend_threshold?: number;
  sentiment_enabled?: boolean;
  sentiment_fear_greed_enabled?: boolean;
  sentiment_fear_greed_weight?: number;
  sentiment_request_timeout_seconds?: number;
  advisory_enabled?: boolean;
  advisory_activation_threshold?: number;
  advisory_estimated_tokens?: number;
  uncertainty_weight_volatile_regime?: number;
  uncertainty_weight_sentiment_extreme?: number;
  uncertainty_weight_low_sentiment_confidence?: number;
  uncertainty_weight_strategy_disagreement?: number;
  uncertainty_weight_drawdown_proximity?: number;
  uncertainty_weight_regime_change?: number;
  daily_token_budget_enabled?: boolean;
  daily_token_budget_tokens?: number;
  token_budget_degrade_mode?: "normal" | "budget_stop";
  save_cycle_history?: boolean;
  stop_loss_monitoring_enabled?: boolean;
  telegram_notify_level?: "all" | "trades_only" | "critical_only";
  crewai_verbose?: boolean;
  log_level?: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  risk?: RiskParamsUpdate;
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

export interface ControlsResponse {
  execution_paused: boolean;
  advisory_paused: boolean;
  advisory_available: boolean;
}

export interface ControlsUpdate {
  execution_paused?: boolean;
  advisory_paused?: boolean;
}

// ---------------------------------------------------------------------------
// Market data
// ---------------------------------------------------------------------------

export interface OHLCVBar {
  timestamp: number; // Unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SymbolTickerResponse {
  symbol: string;
  last_price: number | null;
  bid: number | null;
  ask: number | null;
  volume_24h: number | null;
  timestamp: string | null;
}
