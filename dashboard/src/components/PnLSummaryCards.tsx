"use client";

import type { PortfolioResponse, PnLPointResponse } from "@/types";

interface Props {
  portfolio: PortfolioResponse | undefined;
  latestPnl: PnLPointResponse | undefined;
  isLoading?: boolean;
}

function Card({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`mt-1 text-xl font-semibold ${color ?? "text-gray-900 dark:text-gray-100"}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
    </div>
  );
}

function fmt(n: number | null | undefined, prefix = "$"): string {
  if (n == null) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${prefix}${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pnlColor(n: number | null | undefined): string {
  if (n == null || n === 0) return "text-gray-900 dark:text-gray-100";
  return n > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400";
}

export function PnLSummaryCards({ portfolio, latestPnl, isLoading }: Props) {
  const totalBalance = portfolio?.total_balance_quote;
  const unrealized = portfolio?.unrealized_pnl;
  const realized = portfolio?.realized_pnl;
  const fees = portfolio?.total_fees;
  const drawdown = latestPnl?.drawdown_pct;

  const placeholder = isLoading ? "..." : "—";

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      <Card
        label="Total Balance"
        value={totalBalance != null ? `$${totalBalance.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : placeholder}
        sub={portfolio ? `Cash: $${portfolio.balance_quote.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : undefined}
      />
      <Card label="Unrealized P&L" value={unrealized != null ? fmt(unrealized) : placeholder} color={pnlColor(unrealized)} />
      <Card label="Realized P&L" value={realized != null ? fmt(realized) : placeholder} color={pnlColor(realized)} />
      <Card
        label="Total Fees"
        value={fees != null ? `$${fees.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : placeholder}
      />
      <Card
        label="Max Drawdown"
        value={drawdown != null ? `${drawdown.toFixed(1)}%` : placeholder}
        color={drawdown != null && drawdown > 5 ? "text-red-600 dark:text-red-400" : undefined}
      />
    </div>
  );
}
