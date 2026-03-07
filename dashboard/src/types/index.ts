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
