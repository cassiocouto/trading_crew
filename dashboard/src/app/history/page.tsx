"use client";

import { EquityCurve } from "@/components/EquityCurve";
import { StrategyStatsTable } from "@/components/StrategyStatsTable";
import { useCycles, usePnlHistory, useStrategyStats } from "@/hooks/useApi";

export default function HistoryPage() {
  const pnl = usePnlHistory(200);
  const cycles = useCycles(100);
  const stratStats = useStrategyStats();

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">History</h1>

      {/* Equity curve */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold">Equity Curve</h2>
        <EquityCurve data={pnl.data ?? []} />
      </div>

      {/* Strategy breakdown */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold">Strategy Breakdown</h2>
        <StrategyStatsTable stats={stratStats.data ?? []} />
      </div>

      {/* Cycle history */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold">Cycle History</h2>
        {cycles.isLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs font-medium uppercase text-gray-500">
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Time</th>
                  <th className="py-2 pr-4">Signals</th>
                  <th className="py-2 pr-4">Fills</th>
                  <th className="py-2 pr-4">Balance</th>
                  <th className="py-2 pr-4">PnL</th>
                  <th className="py-2">CB</th>
                </tr>
              </thead>
              <tbody>
                {(cycles.data ?? []).map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="py-2 pr-4 font-medium">{c.cycle_number}</td>
                    <td className="py-2 pr-4 text-xs text-gray-500">
                      {new Date(c.timestamp).toLocaleString()}
                    </td>
                    <td className="py-2 pr-4">{c.num_signals}</td>
                    <td className="py-2 pr-4">{c.num_orders_filled}</td>
                    <td className="py-2 pr-4">${c.portfolio_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                    <td
                      className={`py-2 pr-4 font-medium ${
                        c.realized_pnl >= 0 ? "text-green-600" : "text-red-600"
                      }`}
                    >
                      {c.realized_pnl >= 0 ? "+" : ""}${c.realized_pnl.toFixed(2)}
                    </td>
                    <td className="py-2">
                      {c.circuit_breaker_tripped ? (
                        <span className="text-red-500 font-bold">⚡</span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
