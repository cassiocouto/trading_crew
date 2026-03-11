// Typed fetch wrappers for all FastAPI dashboard endpoints.

import type {
  AgentStatusResponse,
  BacktestResultResponse,
  ClosedTradeResponse,
  ControlsResponse,
  ControlsUpdate,
  CycleResponse,
  FailedOrderResponse,
  OHLCVBar,
  OrderResponse,
  PnLPointResponse,
  PortfolioResponse,
  SettingsResponse,
  SettingsUpdate,
  SignalResponse,
  StrategyStatsResponse,
  SymbolTickerResponse,
  SystemStatusResponse,
  TradeStatsResponse,
} from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string, params?: Record<string, string | number | boolean>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  }
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getPortfolio: () => get<PortfolioResponse>("/api/portfolio/"),
  getPnlHistory: (limit = 100) => get<PnLPointResponse[]>("/api/portfolio/history", { limit }),
  getClosedTrades: (limit = 200, symbol?: string) => {
    const params: Record<string, string | number> = { limit };
    if (symbol) params.symbol = symbol;
    return get<ClosedTradeResponse[]>("/api/portfolio/trades", params);
  },
  getTradeStats: (symbol?: string) => {
    const params: Record<string, string> = {};
    if (symbol) params.symbol = symbol;
    return get<TradeStatsResponse>("/api/portfolio/trade-stats", params);
  },

  getOrders: (limit = 50, status?: string, symbol?: string) => {
    const params: Record<string, string | number | boolean> = { limit };
    if (status) params.status = status;
    if (symbol) params.symbol = symbol;
    return get<OrderResponse[]>("/api/orders/", params);
  },
  getFailedOrders: (unresolvedOnly = true, symbol?: string) => {
    const params: Record<string, string | number | boolean> = { unresolved_only: unresolvedOnly };
    if (symbol) params.symbol = symbol;
    return get<FailedOrderResponse[]>("/api/orders/failed", params);
  },

  getSignals: (limit = 50, strategy?: string, symbol?: string) => {
    const params: Record<string, string | number | boolean> = { limit };
    if (strategy) params.strategy = strategy;
    if (symbol) params.symbol = symbol;
    return get<SignalResponse[]>("/api/signals/", params);
  },
  getStrategyStats: () => get<StrategyStatsResponse[]>("/api/signals/strategy-stats"),

  getCycles: (limit = 50) => get<CycleResponse[]>("/api/cycles/", { limit }),
  getLatestCycle: () => get<CycleResponse>("/api/cycles/latest"),

  getSystemStatus: () => get<SystemStatusResponse>("/api/system/status"),
  getAgents: () => get<AgentStatusResponse[]>("/api/agents/"),

  // Settings
  getSettings: () => get<SettingsResponse>("/api/settings/"),
  updateSettings: (data: SettingsUpdate) => put<SettingsResponse>("/api/settings/", data),

  // Controls
  getControls: () => get<ControlsResponse>("/api/controls/"),
  updateControls: (data: ControlsUpdate) => patch<ControlsResponse>("/api/controls/", data),

  // Market
  getMarketSymbols: () => get<SymbolTickerResponse[]>("/api/market/symbols"),
  getMarketOHLCV: (symbol: string, timeframe = "1h", limit = 120) =>
    get<OHLCVBar[]>("/api/market/ohlcv", { symbol, timeframe, limit }),

  runBacktest: (req: {
    symbol: string;
    exchange: string;
    timeframe: string;
    start: string;
    end: string;
    initial_balance: number;
    fee_rate: number;
    slippage_pct: number;
    strategy_names?: string[];
    advisory_mode?: string;
    simulation_mode?: boolean;
  }) => post<BacktestResultResponse>("/api/backtest/run", req),
};

export const WS_URL = `${BASE_URL.replace(/^http/, "ws")}/ws/events`;
