"use client";

import { usePortfolio, usePnlHistory, useClosedTrades, useTradeStats } from "@/hooks/useApi";
import { PnLSummaryCards } from "@/components/PnLSummaryCards";
import { RichEquityCurve } from "@/components/RichEquityCurve";
import { PositionsTable } from "@/components/PositionsTable";
import { ClosedTradesTable } from "@/components/ClosedTradesTable";
import { TradeStatsBar } from "@/components/TradeStatsBar";

export default function PnLPage() {
  const portfolio = usePortfolio();
  const pnl = usePnlHistory(200);
  const trades = useClosedTrades(200);
  const stats = useTradeStats();

  const latestPnl = pnl.data?.[pnl.data.length - 1];
  const hasError = portfolio.isError || pnl.isError || trades.isError || stats.isError;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">P&L</h1>

      {hasError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          Some data failed to load. Displaying what is available.
        </div>
      )}

      {/* Section 1 — Summary cards */}
      <PnLSummaryCards portfolio={portfolio.data} latestPnl={latestPnl} isLoading={portfolio.isLoading} />

      {/* Section 2 — Rich equity curve */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Equity Curve</h2>
        <RichEquityCurve data={pnl.data ?? []} />
      </div>

      {/* Section 3 — Open positions */}
      {portfolio.data && Object.keys(portfolio.data.positions).length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
          <h2 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Open Positions</h2>
          <PositionsTable positions={portfolio.data.positions} />
        </div>
      )}

      {/* Section 4 — Closed trades journal */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <h2 className="mb-3 text-sm font-semibold text-gray-700 dark:text-gray-300">Trade Journal</h2>
        <TradeStatsBar stats={stats.data} />
        <div className="mt-3">
          <ClosedTradesTable trades={trades.data ?? []} />
        </div>
      </div>
    </div>
  );
}
