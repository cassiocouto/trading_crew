"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BacktestResultResponse } from "@/types";

function BacktestError({ message }: { message: string }) {
  let detail = message;
  try {
    const parsed = JSON.parse(message.replace(/^API error \d+:\s*/, ""));
    if (parsed.detail) detail = parsed.detail;
  } catch {
    /* use raw message */
  }

  const needsData = /no ohlcv data|fetch data/i.test(detail);

  return (
    <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
      <p className="text-sm font-medium text-red-800 dark:text-red-300">{detail}</p>
      {needsData && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400">
          Run <code className="rounded bg-red-100 px-1.5 py-0.5 font-mono dark:bg-red-900/40">make backtest-data</code> in
          the project root to fetch historical candles first.
        </p>
      )}
    </div>
  );
}

export default function BacktestPage() {
  const [form, setForm] = useState({
    symbol: "BTC/USDT",
    exchange: "binance",
    timeframe: "1h",
    start: "2024-01-01",
    end: "2024-12-31",
    initial_balance: 10000,
    fee_rate: 0.001,
    slippage_pct: 0.0005,
    advisory_mode: "deterministic_only",
    simulation_mode: false,
  });

  const mutation = useMutation({
    mutationFn: () =>
      api.runBacktest({
        ...form,
        start: new Date(form.start).toISOString(),
        end: new Date(form.end).toISOString(),
        advisory_mode: form.advisory_mode,
        simulation_mode: form.simulation_mode,
      }),
  });

  const result: BacktestResultResponse | undefined = mutation.data;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Backtest</h1>

      {/* Config form */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-4 font-semibold">Configuration</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {(
            [
              { key: "symbol", label: "Symbol" },
              { key: "exchange", label: "Exchange" },
              { key: "timeframe", label: "Timeframe" },
              { key: "start", label: "Start Date", type: "date" },
              { key: "end", label: "End Date", type: "date" },
              { key: "initial_balance", label: "Initial Balance ($)", type: "number" },
              { key: "fee_rate", label: "Fee Rate", type: "number" },
              { key: "slippage_pct", label: "Slippage %", type: "number" },
            ] as { key: keyof typeof form; label: string; type?: string }[]
          ).map(({ key, label, type = "text" }) => (
            <div key={key}>
              <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{label}</label>
              <input
                type={type}
                className="w-full rounded-md border border-gray-200 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                value={form[key] as string | number}
                step={type === "number" ? "any" : undefined}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    [key]: type === "number" ? parseFloat(e.target.value) : e.target.value,
                  }))
                }
              />
            </div>
          ))}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Advisory Mode</label>
            <select
              className="w-full rounded-md border border-gray-200 px-3 py-1.5 text-sm bg-white dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              value={form.advisory_mode}
              onChange={(e) => setForm((f) => ({ ...f, advisory_mode: e.target.value }))}
            >
              <option value="deterministic_only">Deterministic Only</option>
              <option value="with_advisory">With Advisory</option>
            </select>
          </div>
          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600"
                checked={form.simulation_mode}
                onChange={(e) => setForm((f) => ({ ...f, simulation_mode: e.target.checked }))}
              />
              <span className="font-medium text-gray-700 dark:text-gray-300">Full Simulation</span>
            </label>
            <span className="ml-1 text-[10px] text-gray-400 dark:text-gray-500" title="Run the real TradingFlow against historical data instead of the fast legacy backtest">(?)</span>
          </div>
        </div>

        <button
          className="mt-4 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "Running…" : "Run Backtest"}
        </button>

        {mutation.isError && <BacktestError message={(mutation.error as Error).message} />}
      </div>

      {/* Results */}
      {result && !mutation.isError && (
        <div className="space-y-4">
          {/* Summary metrics */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Total Return", value: `${result.total_return_pct >= 0 ? "+" : ""}${result.total_return_pct.toFixed(2)}%` },
              { label: "Sharpe Ratio", value: result.sharpe_ratio.toFixed(3) },
              { label: "Max Drawdown", value: `${result.max_drawdown_pct.toFixed(2)}%` },
              { label: "Win Rate", value: `${(result.win_rate * 100).toFixed(1)}%` },
              { label: "Profit Factor", value: result.profit_factor.toFixed(2) },
              { label: "Total Trades", value: result.total_trades },
              { label: "Total Fees", value: `$${result.total_fees.toFixed(2)}` },
              { label: "Final Balance", value: `$${result.final_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })}` },
              ...(result.advisory_mode === "with_advisory"
                ? [
                    { label: "Advisory Activations", value: result.advisory_activations },
                    { label: "Advisory Vetoes", value: result.advisory_vetoes },
                    { label: "Avg Uncertainty", value: result.avg_uncertainty_score.toFixed(3) },
                  ]
                : []),
            ].map(({ label, value }) => (
              <div key={label} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-900">
                <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
                <p className="mt-0.5 text-lg font-bold">{value}</p>
              </div>
            ))}
          </div>

          {/* Trade table */}
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
            <h2 className="mb-3 font-semibold">Trades ({result.trades.length})</h2>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700 dark:text-gray-400">
                    <th className="py-2 pr-4">Symbol</th>
                    <th className="py-2 pr-4">Entry Bar</th>
                    <th className="py-2 pr-4">Exit Bar</th>
                    <th className="py-2 pr-4">Entry Price</th>
                    <th className="py-2 pr-4">Exit Price</th>
                    <th className="py-2 pr-4">Amount</th>
                    <th className="py-2 pr-4">P&amp;L</th>
                    <th className="py-2">Fees</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} className="border-b border-gray-100 last:border-0 dark:border-gray-800">
                      <td className="py-2 pr-4 font-medium">{t.symbol}</td>
                      <td className="py-2 pr-4">{t.entry_bar}</td>
                      <td className="py-2 pr-4">{t.exit_bar >= 0 ? t.exit_bar : "—"}</td>
                      <td className="py-2 pr-4">${t.entry_price.toLocaleString()}</td>
                      <td className="py-2 pr-4">
                        {t.exit_price > 0 ? `$${t.exit_price.toLocaleString()}` : "—"}
                      </td>
                      <td className="py-2 pr-4">{t.amount.toFixed(6)}</td>
                      <td
                        className={`py-2 pr-4 font-medium ${
                          t.pnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                        }`}
                      >
                        {t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}
                      </td>
                      <td className="py-2">${t.fees.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
