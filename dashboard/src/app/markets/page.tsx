"use client";

import { useState } from "react";
import { CandlestickChart } from "@/components/CandlestickChart";
import { useMarketOHLCV, useMarketSymbols } from "@/hooks/useApi";

const TIMEFRAMES = [
  { label: "1H", value: "1h" },
  { label: "4H", value: "4h" },
  { label: "1D", value: "1d" },
];

const OHLCV_LIMIT = 200;

export default function MarketsPage() {
  const { data: symbols, isLoading: symbolsLoading } = useMarketSymbols();
  const [activeSymbol, setActiveSymbol] = useState<string>("");
  const [timeframe, setTimeframe] = useState("1h");

  const selectedSymbol = activeSymbol || symbols?.[0]?.symbol || "";
  const { data: ohlcv, isLoading: candlesLoading } = useMarketOHLCV(selectedSymbol, timeframe, OHLCV_LIMIT);

  const activeSymbolData = symbols?.find((s) => s.symbol === selectedSymbol);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Markets</h1>
        <p className="mt-0.5 text-sm text-gray-500">Price and volume data for tracked symbols.</p>
      </div>

      {symbolsLoading ? (
        <div className="h-12 animate-pulse rounded-lg bg-gray-100" />
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          {/* Symbol tabs */}
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

          {/* Timeframe selector */}
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
            value={
              activeSymbolData.volume_24h != null
                ? formatVolume(activeSymbolData.volume_24h)
                : "—"
            }
          />
        </div>
      )}

      {/* Chart */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-700">
            {selectedSymbol} · {timeframe.toUpperCase()}
          </span>
          {candlesLoading && (
            <span className="text-xs text-gray-400">Loading…</span>
          )}
        </div>
        {candlesLoading ? (
          <div className="h-96 animate-pulse rounded-lg bg-gray-50" />
        ) : (
          <CandlestickChart data={ohlcv ?? []} height={420} />
        )}
      </div>

      {ohlcv && ohlcv.length > 0 && (
        <p className="text-xs text-gray-400">
          Showing {ohlcv.length} candles · data sourced from the local database
          (populated by the trading bot each cycle)
        </p>
      )}
    </div>
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
