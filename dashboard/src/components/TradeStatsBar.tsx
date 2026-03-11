"use client";

import type { TradeStatsResponse } from "@/types";

interface Props {
  stats: TradeStatsResponse | undefined;
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-center">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`text-sm font-semibold ${color ?? "text-gray-900 dark:text-gray-100"}`}>{value}</p>
    </div>
  );
}

export function TradeStatsBar({ stats }: Props) {
  if (!stats || stats.total_trades === 0) return null;

  const pnlColor =
    stats.total_pnl > 0
      ? "text-green-600 dark:text-green-400"
      : stats.total_pnl < 0
        ? "text-red-600 dark:text-red-400"
        : undefined;

  return (
    <div className="flex flex-wrap items-center justify-center gap-6 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 dark:border-gray-700 dark:bg-gray-800/50">
      <Stat label="Total Trades" value={String(stats.total_trades)} />
      <Stat label="Win Rate" value={`${stats.win_rate}%`} color={stats.win_rate >= 50 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"} />
      <Stat label="Wins / Losses" value={`${stats.winning_trades} / ${stats.losing_trades}`} />
      <Stat
        label="Total P&L"
        value={`${stats.total_pnl >= 0 ? "+" : ""}$${Math.abs(stats.total_pnl).toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        color={pnlColor}
      />
      <Stat
        label="Avg P&L"
        value={`${stats.avg_pnl >= 0 ? "+" : ""}$${Math.abs(stats.avg_pnl).toLocaleString(undefined, { minimumFractionDigits: 2 })}`}
        color={stats.avg_pnl > 0 ? "text-green-600 dark:text-green-400" : stats.avg_pnl < 0 ? "text-red-600 dark:text-red-400" : undefined}
      />
      <Stat label="Profit Factor" value={stats.profit_factor > 0 ? String(stats.profit_factor) : "—"} />
      <Stat label="Avg Hold" value={stats.avg_hold_hours < 24 ? `${stats.avg_hold_hours.toFixed(1)}h` : `${(stats.avg_hold_hours / 24).toFixed(1)}d`} />
    </div>
  );
}
