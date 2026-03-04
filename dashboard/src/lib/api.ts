// Typed fetch wrappers for all FastAPI dashboard endpoints.

import type {
  AgentStatusResponse,
  BacktestResultResponse,
  CycleResponse,
  FailedOrderResponse,
  OrderResponse,
  PnLPointResponse,
  PortfolioResponse,
  SignalResponse,
  StrategyStatsResponse,
  SystemStatusResponse,
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

export const api = {
  getPortfolio: () => get<PortfolioResponse>("/api/portfolio/"),
  getPnlHistory: (limit = 100) => get<PnLPointResponse[]>("/api/portfolio/history", { limit }),

  getOrders: (limit = 50, status?: string) =>
    get<OrderResponse[]>("/api/orders/", status ? { limit, status } : { limit }),
  getFailedOrders: (unresolvedOnly = true) =>
    get<FailedOrderResponse[]>("/api/orders/failed", { unresolved_only: unresolvedOnly }),

  getSignals: (limit = 50, strategy?: string) =>
    get<SignalResponse[]>("/api/signals/", strategy ? { limit, strategy } : { limit }),
  getStrategyStats: () => get<StrategyStatsResponse[]>("/api/signals/strategy-stats"),

  getCycles: (limit = 50) => get<CycleResponse[]>("/api/cycles/", { limit }),
  getLatestCycle: () => get<CycleResponse>("/api/cycles/latest"),

  getSystemStatus: () => get<SystemStatusResponse>("/api/system/status"),
  getAgents: () => get<AgentStatusResponse[]>("/api/agents/"),

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
  }) => post<BacktestResultResponse>("/api/backtest/run", req),
};

export const WS_URL = `${BASE_URL.replace(/^http/, "ws")}/ws/events`;
