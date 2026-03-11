"use client";

import { useState } from "react";
import type { ClosedTradeResponse } from "@/types";

type SortKey = "closed_at" | "pnl" | "pnl_pct" | "hold_duration_hours" | "amount";

interface Props {
  trades: ClosedTradeResponse[];
}

function fmtUsd(n: number): string {
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pnlColor(n: number): string {
  if (n === 0) return "";
  return n > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400";
}

function fmtDuration(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

export function ClosedTradesTable({ trades }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("closed_at");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...trades].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "closed_at") cmp = new Date(a.closed_at).getTime() - new Date(b.closed_at).getTime();
    else cmp = (a[sortKey] as number) - (b[sortKey] as number);
    return sortAsc ? cmp : -cmp;
  });

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  }

  const arrow = (key: SortKey) => (sortKey === key ? (sortAsc ? " \u25B2" : " \u25BC") : "");

  if (trades.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-gray-400 dark:text-gray-500">
        No closed trades yet
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th className="px-3 py-2">Symbol</th>
            <th className="px-3 py-2">Strategy</th>
            <th className="px-3 py-2 text-right">Entry</th>
            <th className="px-3 py-2 text-right">Exit</th>
            <th className="cursor-pointer px-3 py-2 text-right" onClick={() => toggleSort("amount")}>Amt{arrow("amount")}</th>
            <th className="cursor-pointer px-3 py-2 text-right" onClick={() => toggleSort("pnl")}>P&L{arrow("pnl")}</th>
            <th className="cursor-pointer px-3 py-2 text-right" onClick={() => toggleSort("pnl_pct")}>P&L %{arrow("pnl_pct")}</th>
            <th className="px-3 py-2 text-right">Fees</th>
            <th className="cursor-pointer px-3 py-2 text-right" onClick={() => toggleSort("hold_duration_hours")}>Hold{arrow("hold_duration_hours")}</th>
            <th className="cursor-pointer px-3 py-2 text-right" onClick={() => toggleSort("closed_at")}>Closed{arrow("closed_at")}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((t, i) => (
            <tr key={`${t.symbol}-${t.closed_at}-${i}`} className="border-b border-gray-100 dark:border-gray-800">
              <td className="px-3 py-2 font-medium">{t.symbol}</td>
              <td className="px-3 py-2 text-gray-500 dark:text-gray-400">{t.strategy_name}</td>
              <td className="px-3 py-2 text-right tabular-nums">${t.entry_price.toLocaleString()}</td>
              <td className="px-3 py-2 text-right tabular-nums">${t.exit_price.toLocaleString()}</td>
              <td className="px-3 py-2 text-right tabular-nums">{t.amount.toFixed(6)}</td>
              <td className={`px-3 py-2 text-right tabular-nums font-medium ${pnlColor(t.pnl)}`}>{fmtUsd(t.pnl)}</td>
              <td className={`px-3 py-2 text-right tabular-nums ${pnlColor(t.pnl_pct)}`}>{t.pnl_pct > 0 ? "+" : ""}{t.pnl_pct.toFixed(1)}%</td>
              <td className="px-3 py-2 text-right tabular-nums text-gray-500 dark:text-gray-400">${t.fee.toFixed(2)}</td>
              <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-400">{fmtDuration(t.hold_duration_hours)}</td>
              <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-400">{new Date(t.closed_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
