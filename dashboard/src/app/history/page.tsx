"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Shield } from "lucide-react";
import { EquityCurve } from "@/components/EquityCurve";
import { StrategyStatsTable } from "@/components/StrategyStatsTable";
import { useCycles, usePnlHistory, useStrategyStats } from "@/hooks/useApi";
import type { CycleResponse } from "@/types";

function uncertaintyColor(score: number): string {
  if (score < 0.3) return "text-green-600 dark:text-green-400";
  if (score <= 0.6) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

function uncertaintyBg(score: number): string {
  if (score < 0.3) return "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-400";
  if (score <= 0.6) return "bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-400";
  return "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-400";
}

function formatAdvisoryAdjustments(json: string): Record<string, unknown> | null {
  if (!json || json === "{}" || json === "[]" || json === "null") return null;
  try {
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function CycleRow({ c, isExpanded, onToggle }: { c: CycleResponse; isExpanded: boolean; onToggle: () => void }) {
  const adjustments = c.advisory_ran ? formatAdvisoryAdjustments(c.advisory_adjustments_json) : null;

  return (
    <>
      <tr
        className={`border-b border-gray-100 last:border-0 dark:border-gray-800 ${c.advisory_ran ? "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800" : ""}`}
        onClick={c.advisory_ran ? onToggle : undefined}
      >
        <td className="py-2 pr-4 font-medium">
          {c.advisory_ran && (
            <span className="mr-1 inline-flex text-gray-400 dark:text-gray-500">
              {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </span>
          )}
          {c.cycle_number}
        </td>
        <td className="py-2 pr-4 text-xs text-gray-500 dark:text-gray-400" suppressHydrationWarning>
          {new Date(c.timestamp).toLocaleString()}
        </td>
        <td className="py-2 pr-4">{c.num_signals}</td>
        <td className="py-2 pr-4">{c.num_orders_filled}</td>
        <td className="py-2 pr-4">${c.portfolio_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
        <td
          className={`py-2 pr-4 font-medium ${
            c.realized_pnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
          }`}
        >
          {c.realized_pnl >= 0 ? "+" : ""}${c.realized_pnl.toFixed(2)}
        </td>
        <td className="py-2 pr-4">
          <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${uncertaintyBg(c.uncertainty_score)}`}>
            {c.uncertainty_score.toFixed(2)}
          </span>
        </td>
        <td className="py-2 pr-4">
          {c.advisory_ran ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-800 dark:bg-purple-500/15 dark:text-purple-400">
              <Shield className="h-3 w-3" />
              Advisory
            </span>
          ) : (
            <span className="text-gray-300 dark:text-gray-600">—</span>
          )}
        </td>
        <td className="py-2">
          {c.circuit_breaker_tripped ? (
            <span className="text-red-500 font-bold">⚡</span>
          ) : (
            <span className="text-gray-300 dark:text-gray-600">—</span>
          )}
        </td>
      </tr>
      {isExpanded && c.advisory_ran && (
        <tr className="border-b border-gray-100 last:border-0 dark:border-gray-800">
          <td colSpan={9} className="bg-purple-50/50 px-6 py-3 space-y-3 dark:bg-purple-900/10">
            {c.advisory_summary && c.advisory_summary.trim().length > 0 && (
              <div className="text-xs">
                <span className="font-semibold text-purple-800 dark:text-purple-400">Crew Reasoning</span>
                <p className="mt-1.5 whitespace-pre-wrap rounded-md bg-white p-3 text-gray-700 border border-purple-100 dark:bg-gray-800 dark:text-gray-300 dark:border-purple-800">
                  {c.advisory_summary}
                </p>
              </div>
            )}
            <div className="text-xs">
              <span className="font-semibold text-purple-800 dark:text-purple-400">Adjustments</span>
              {adjustments ? (
                <pre className="mt-1.5 overflow-x-auto rounded-md bg-white p-3 text-gray-700 border border-purple-100 dark:bg-gray-800 dark:text-gray-300 dark:border-purple-800">
                  {JSON.stringify(adjustments, null, 2)}
                </pre>
              ) : (
                <p className="mt-1 text-gray-500 italic dark:text-gray-400">Proposal approved — no adjustments applied.</p>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function HistoryPage() {
  const pnl = usePnlHistory(200);
  const cycles = useCycles(100);
  const stratStats = useStrategyStats();
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleExpanded = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">History</h1>

      {/* Equity curve */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-3 font-semibold">Equity Curve</h2>
        <EquityCurve data={pnl.data ?? []} />
      </div>

      {/* Strategy breakdown */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-3 font-semibold">Strategy Breakdown</h2>
        <StrategyStatsTable stats={stratStats.data ?? []} />
      </div>

      {/* Cycle history */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-3 font-semibold">Cycle History</h2>
        {cycles.isLoading ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700 dark:text-gray-400">
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Time</th>
                  <th className="py-2 pr-4">Signals</th>
                  <th className="py-2 pr-4">Fills</th>
                  <th className="py-2 pr-4">Balance</th>
                  <th className="py-2 pr-4">PnL</th>
                  <th className="py-2 pr-4">Uncertainty</th>
                  <th className="py-2 pr-4">Advisory</th>
                  <th className="py-2">CB</th>
                </tr>
              </thead>
              <tbody>
                {(cycles.data ?? []).map((c) => (
                  <CycleRow
                    key={c.id}
                    c={c}
                    isExpanded={expandedIds.has(c.id)}
                    onToggle={() => toggleExpanded(c.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
