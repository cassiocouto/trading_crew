"use client";

import { useState } from "react";
import { CandlestickChart } from "@/components/CandlestickChart";
import {
  useMarketOHLCV,
  useMarketSymbols,
  useOrders,
  useFailedOrders,
  useSignals,
  useLatestCycle,
  useStrategyStats,
} from "@/hooks/useApi";
import type { OHLCVBar, OrderResponse, FailedOrderResponse, SignalResponse, StrategyStatsResponse } from "@/types";

const TIMEFRAMES = [
  { label: "1H", value: "1h" },
  { label: "4H", value: "4h" },
  { label: "1D", value: "1d" },
];

const OHLCV_LIMIT = 200;
const SIDEBAR_ORDER_LIMIT = 25;
const SIGNALS_LIMIT = 30;

// ---------------------------------------------------------------------------
// ATR / Volatility helpers
// ---------------------------------------------------------------------------

function calcATR(bars: OHLCVBar[], period = 14): number | null {
  if (bars.length < period + 1) return null;
  const trValues: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    trValues.push(
      Math.max(
        bars[i].high - bars[i].low,
        Math.abs(bars[i].high - bars[i - 1].close),
        Math.abs(bars[i].low - bars[i - 1].close),
      ),
    );
  }
  const slice = trValues.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

function volatilityRegime(atrPct: number): { label: string; color: string } {
  if (atrPct < 1) return { label: "Low", color: "text-emerald-600" };
  if (atrPct < 2) return { label: "Normal", color: "text-blue-600" };
  if (atrPct < 4) return { label: "Elevated", color: "text-amber-600" };
  return { label: "High", color: "text-red-600" };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function MarketsPage() {
  const { data: symbols, isLoading: symbolsLoading } = useMarketSymbols();
  const [activeSymbol, setActiveSymbol] = useState<string>("");
  const [timeframe, setTimeframe] = useState("1h");
  const [showVolume, setShowVolume] = useState(false);

  const selectedSymbol = activeSymbol || symbols?.[0]?.symbol || "";

  const { data: ohlcv, isLoading: candlesLoading } = useMarketOHLCV(selectedSymbol, timeframe, OHLCV_LIMIT);
  const { data: orders, isLoading: ordersLoading } = useOrders(SIDEBAR_ORDER_LIMIT, undefined, selectedSymbol || undefined);
  const { data: failedOrders, isLoading: failedLoading } = useFailedOrders(true, selectedSymbol || undefined);
  const { data: signals, isLoading: signalsLoading } = useSignals(SIGNALS_LIMIT, undefined, selectedSymbol || undefined);
  const { data: latestCycle } = useLatestCycle();
  const { data: strategyStats } = useStrategyStats();

  const activeSymbolData = symbols?.find((s) => s.symbol === selectedSymbol);

  // Strategies that have produced signals for this symbol
  const activeStrategies = signals
    ? [...new Set(signals.map((s) => s.strategy_name))]
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Markets</h1>
        <p className="mt-0.5 text-sm text-gray-500">Price, signals, and order history for tracked symbols.</p>
      </div>

      {symbolsLoading ? (
        <div className="h-12 animate-pulse rounded-lg bg-gray-100" />
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1">
            {symbols?.map((s) => (
              <button
                key={s.symbol}
                onClick={() => setActiveSymbol(s.symbol)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  selectedSymbol === s.symbol
                    ? "bg-indigo-600 text-white"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                {s.symbol}
              </button>
            ))}
          </div>
          <div className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.value}
                onClick={() => setTimeframe(tf.value)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  timeframe === tf.value
                    ? "bg-indigo-600 text-white"
                    : "text-gray-600 hover:bg-gray-50"
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Ticker summary */}
      {activeSymbolData && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Last Price" value={activeSymbolData.last_price?.toFixed(2) ?? "—"} />
          <StatCard label="Bid" value={activeSymbolData.bid?.toFixed(2) ?? "—"} />
          <StatCard label="Ask" value={activeSymbolData.ask?.toFixed(2) ?? "—"} />
          <StatCard
            label="24h Volume"
            value={activeSymbolData.volume_24h != null ? formatVolume(activeSymbolData.volume_24h) : "—"}
          />
        </div>
      )}

      {/* Main content + sidebar */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Chart — 2/3 width on lg */}
        <div className="lg:col-span-2">
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-700">
                {selectedSymbol} · {timeframe.toUpperCase()}
              </span>
              <div className="flex items-center gap-3">
                {candlesLoading && <span className="text-xs text-gray-400">Loading…</span>}
                <label className="flex cursor-pointer items-center gap-1.5 text-xs text-gray-500 select-none">
                  <input
                    type="checkbox"
                    checked={showVolume}
                    onChange={(e) => setShowVolume(e.target.checked)}
                    className="h-3.5 w-3.5 rounded accent-indigo-600"
                  />
                  Volume
                </label>
              </div>
            </div>
            {candlesLoading ? (
              <div className="h-96 animate-pulse rounded-lg bg-gray-50" />
            ) : (
              <CandlestickChart data={ohlcv ?? []} height={420} showVolume={showVolume} />
            )}
          </div>
          {ohlcv && ohlcv.length > 0 && (
            <p className="mt-2 text-xs text-gray-400">
              {ohlcv.length} candles · populated by the trading bot each cycle
            </p>
          )}
        </div>

        {/* Sidebar — 1/3 width on lg */}
        <div className="flex flex-col gap-4 lg:col-span-1">
          <CycleStrategyPanel
            cycleNumber={latestCycle?.cycle_number ?? null}
            activeStrategies={activeStrategies}
            strategyStats={strategyStats ?? []}
            symbol={selectedSymbol}
          />
          <SignalsPanel signals={signals ?? []} loading={signalsLoading} />
          <VolatilityPanel bars={ohlcv ?? []} />
          <OrdersPanel orders={orders ?? []} loading={ordersLoading} />
          <FailedOrdersPanel orders={failedOrders ?? []} loading={failedLoading} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cycle & Strategies panel
// ---------------------------------------------------------------------------

function CycleStrategyPanel({
  cycleNumber,
  activeStrategies,
  strategyStats,
  symbol,
}: {
  cycleNumber: number | null;
  activeStrategies: string[];
  strategyStats: StrategyStatsResponse[];
  symbol: string;
}) {
  const [open, setOpen] = useState(true);

  const statsForSymbolStrategies = strategyStats.filter((s) =>
    activeStrategies.includes(s.strategy_name),
  );

  return (
    <SidebarPanel
      title="Cycle & Strategies"
      badge={
        cycleNumber != null ? (
          <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
            #{cycleNumber}
          </span>
        ) : undefined
      }
      open={open}
      onToggle={() => setOpen((v) => !v)}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-500">Current cycle</span>
          <span className="font-semibold text-gray-800">
            {cycleNumber != null ? `#${cycleNumber}` : "—"}
          </span>
        </div>

        <div>
          <p className="mb-1.5 text-xs text-gray-500">
            Strategies active for <span className="font-medium text-gray-700">{symbol || "—"}</span>
          </p>
          {activeStrategies.length === 0 ? (
            <p className="text-xs text-gray-400">No signals generated yet for this symbol.</p>
          ) : (
            <ul className="space-y-2">
              {statsForSymbolStrategies.length > 0
                ? statsForSymbolStrategies.map((s) => (
                    <li key={s.strategy_name} className="rounded-lg bg-gray-50 px-3 py-2">
                      <p className="text-xs font-semibold text-gray-800">{s.strategy_name}</p>
                      <div className="mt-1 flex gap-3 text-xs text-gray-500">
                        <span>
                          <span className="font-medium text-emerald-600">{s.buy_signals}</span> buy
                        </span>
                        <span>
                          <span className="font-medium text-red-500">{s.sell_signals}</span> sell
                        </span>
                        <span>
                          {(s.avg_confidence * 100).toFixed(0)}% avg conf
                        </span>
                      </div>
                    </li>
                  ))
                : activeStrategies.map((name) => (
                    <li key={name} className="rounded-lg bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-800">
                      {name}
                    </li>
                  ))}
            </ul>
          )}
        </div>
      </div>
    </SidebarPanel>
  );
}

// ---------------------------------------------------------------------------
// Signals panel
// ---------------------------------------------------------------------------

function SignalsPanel({ signals, loading }: { signals: SignalResponse[]; loading: boolean }) {
  const [open, setOpen] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <SidebarPanel
      title="Latest Signals"
      badge={
        signals.length > 0 ? (
          <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
            {signals.length}
          </span>
        ) : undefined
      }
      open={open}
      onToggle={() => setOpen((v) => !v)}
    >
      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-gray-50" />)}
        </div>
      ) : signals.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-400">No signals for this symbol yet.</p>
      ) : (
        <ul className="divide-y divide-gray-50">
          {signals.map((sig) => (
            <li key={sig.id} className="py-2 first:pt-0 last:pb-0">
              <button
                className="w-full text-left"
                onClick={() => setExpanded((prev) => (prev === sig.id ? null : sig.id))}
              >
                <div className="flex items-center gap-1.5">
                  <SignalTypeBadge type={sig.signal_type} />
                  <span className="text-xs font-medium text-gray-800">{sig.strategy_name}</span>
                  <span className="ml-auto shrink-0 text-xs text-gray-400">
                    {fmtDate(sig.timestamp)}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center gap-2">
                  <ConfidenceBar confidence={sig.confidence} />
                  <span className="text-xs text-gray-500">
                    {(sig.confidence * 100).toFixed(0)}% · {sig.strength}
                  </span>
                  {sig.risk_verdict && (
                    <RiskVerdictBadge verdict={sig.risk_verdict} />
                  )}
                </div>
              </button>
              {expanded === sig.id && sig.reason && (
                <div className="mt-1.5 rounded bg-gray-50 px-2 py-2 text-xs leading-relaxed text-gray-600">
                  {sig.reason}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </SidebarPanel>
  );
}

// ---------------------------------------------------------------------------
// Volatility panel
// ---------------------------------------------------------------------------

function VolatilityPanel({ bars }: { bars: OHLCVBar[] }) {
  const [open, setOpen] = useState(false);

  const atr = calcATR(bars, 14);
  const lastClose = bars.at(-1)?.close ?? null;
  const atrPct = atr != null && lastClose != null && lastClose > 0 ? (atr / lastClose) * 100 : null;
  const regime = atrPct != null ? volatilityRegime(atrPct) : null;

  const window20 = bars.slice(-20);
  const rangeHigh = window20.length > 0 ? Math.max(...window20.map((b) => b.high)) : null;
  const rangeLow = window20.length > 0 ? Math.min(...window20.map((b) => b.low)) : null;
  const rangePct =
    rangeHigh != null && rangeLow != null && rangeLow > 0
      ? ((rangeHigh - rangeLow) / rangeLow) * 100
      : null;

  return (
    <SidebarPanel
      title="Volatility"
      badge={
        regime ? (
          <span className={`text-xs font-semibold ${regime.color}`}>{regime.label}</span>
        ) : undefined
      }
      open={open}
      onToggle={() => setOpen((v) => !v)}
    >
      {bars.length < 15 ? (
        <p className="py-4 text-center text-xs text-gray-400">
          Not enough candles to compute ATR (need ≥ 15).
        </p>
      ) : (
        <dl className="space-y-3">
          <VolRow label="ATR (14)" value={atr != null ? atr.toFixed(4) : "—"} />
          <VolRow
            label="ATR %"
            value={atrPct != null ? `${atrPct.toFixed(2)}%` : "—"}
            hint="ATR as % of last close"
          />
          <VolRow
            label="20-bar range"
            value={
              rangeHigh != null && rangeLow != null
                ? `${rangeLow.toFixed(2)} – ${rangeHigh.toFixed(2)}`
                : "—"
            }
          />
          <VolRow
            label="Range %"
            value={rangePct != null ? `${rangePct.toFixed(2)}%` : "—"}
            hint="(High − Low) / Low over last 20 bars"
          />
        </dl>
      )}
    </SidebarPanel>
  );
}

function VolRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="flex items-center gap-1 text-xs text-gray-500">
        {label}
        {hint && (
          <span className="group relative cursor-default">
            <span className="text-gray-300">ⓘ</span>
            <span className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden w-44 -translate-x-1/2 rounded bg-gray-800 px-2 py-1 text-xs text-white shadow group-hover:block">
              {hint}
            </span>
          </span>
        )}
      </dt>
      <dd className="text-xs font-semibold text-gray-800">{value}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Orders panel
// ---------------------------------------------------------------------------

function OrdersPanel({ orders, loading }: { orders: OrderResponse[]; loading: boolean }) {
  const [open, setOpen] = useState(false);

  return (
    <SidebarPanel
      title="Orders"
      badge={
        orders.length > 0 ? (
          <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
            {orders.length}
          </span>
        ) : undefined
      }
      open={open}
      onToggle={() => setOpen((v) => !v)}
    >
      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-gray-50" />)}
        </div>
      ) : orders.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-400">No orders for this symbol.</p>
      ) : (
        <ul className="divide-y divide-gray-50">
          {orders.map((o) => (
            <li key={o.id} className="flex items-start justify-between gap-2 py-2 first:pt-0 last:pb-0">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <SideBadge side={o.side} />
                  <span className="truncate text-xs font-medium text-gray-800">
                    {o.average_fill_price?.toFixed(2) ?? o.requested_price?.toFixed(2) ?? "—"}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-xs text-gray-400">
                  {o.strategy_name} · {fmtDate(o.created_at)}
                </p>
              </div>
              <StatusBadge status={o.status} />
            </li>
          ))}
        </ul>
      )}
    </SidebarPanel>
  );
}

// ---------------------------------------------------------------------------
// Failed orders panel
// ---------------------------------------------------------------------------

function FailedOrdersPanel({ orders, loading }: { orders: FailedOrderResponse[]; loading: boolean }) {
  const [open, setOpen] = useState(false);

  return (
    <SidebarPanel
      title="Failed Orders"
      badge={
        orders.length > 0 ? (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
            {orders.length}
          </span>
        ) : undefined
      }
      open={open}
      onToggle={() => setOpen((v) => !v)}
    >
      {loading ? (
        <div className="space-y-2">
          {[0, 1].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-gray-50" />)}
        </div>
      ) : orders.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-400">No unresolved failures.</p>
      ) : (
        <ul className="divide-y divide-gray-50">
          {orders.map((o) => (
            <li key={o.id} className="py-2 first:pt-0 last:pb-0">
              <div className="flex items-center gap-1.5">
                <SideBadge side={o.side} />
                <span className="text-xs font-medium text-gray-800">
                  {o.requested_price?.toFixed(2) ?? "market"}
                </span>
                <span className="ml-auto text-xs text-gray-400">{fmtDate(o.timestamp)}</span>
              </div>
              <p className="mt-0.5 truncate text-xs text-red-500" title={o.error_reason}>
                {o.error_reason}
              </p>
            </li>
          ))}
        </ul>
      )}
    </SidebarPanel>
  );
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function SidebarPanel({
  title,
  badge,
  open,
  onToggle,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-700">{title}</span>
          {badge}
        </div>
        <svg
          className={`h-4 w-4 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="border-t border-gray-100 px-4 py-3">{children}</div>}
    </div>
  );
}

function SignalTypeBadge({ type }: { type: string }) {
  const t = type.toLowerCase();
  const cls =
    t === "buy"
      ? "bg-emerald-100 text-emerald-700"
      : t === "sell"
        ? "bg-red-100 text-red-700"
        : "bg-gray-100 text-gray-600";
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-bold uppercase ${cls}`}>
      {type}
    </span>
  );
}

function RiskVerdictBadge({ verdict }: { verdict: string }) {
  const v = verdict.toLowerCase();
  const cls =
    v === "approved"
      ? "bg-emerald-50 text-emerald-600"
      : v === "rejected"
        ? "bg-red-50 text-red-600"
        : "bg-gray-50 text-gray-500";
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${cls}`}>{verdict}</span>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 70 ? "bg-emerald-400" : pct >= 40 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function SideBadge({ side }: { side: string }) {
  const isBuy = side.toLowerCase() === "buy";
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-bold uppercase ${
        isBuy ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
      }`}
    >
      {side}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    filled: "bg-emerald-100 text-emerald-700",
    open: "bg-blue-100 text-blue-700",
    cancelled: "bg-gray-100 text-gray-500",
    failed: "bg-red-100 text-red-700",
    pending: "bg-amber-100 text-amber-700",
  };
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${colors[status.toLowerCase()] ?? "bg-gray-100 text-gray-500"}`}>
      {status}
    </span>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-base font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function formatVolume(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(2)}K`;
  return v.toFixed(2);
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
