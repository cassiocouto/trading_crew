"use client";

import { useState } from "react";
import { OrdersTable } from "@/components/OrdersTable";
import { StatusBadge } from "@/components/StatusBadge";
import { useFailedOrders, useOrders, usePortfolio } from "@/hooks/useApi";

const STATUS_OPTIONS = ["", "filled", "open", "pending", "partially_filled", "cancelled", "rejected"];

export default function OrdersPage() {
  const [status, setStatus] = useState("");
  const [showFailed, setShowFailed] = useState(false);

  const orders = useOrders(100, status || undefined);
  const failedOrders = useFailedOrders();
  const portfolio = usePortfolio();

  const positions = portfolio.data?.positions ?? {};
  const positionEntries = Object.entries(positions);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Orders</h1>

      {/* Per-position P&L cards */}
      {positionEntries.length > 0 && (
        <div>
          <h2 className="mb-3 font-semibold text-sm text-gray-600 uppercase tracking-wide dark:text-gray-400">
            Open Position P&amp;L
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {positionEntries.map(([symbol, pos]) => {
              const pnl =
                pos.current_price != null
                  ? (pos.current_price - pos.entry_price) * pos.amount
                  : null;
              return (
                <div key={symbol} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-900">
                  <div className="text-sm font-semibold">{symbol}</div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {pos.amount.toFixed(6)} @ ${pos.entry_price.toLocaleString()}
                  </div>
                  {pnl != null && (
                    <div
                      className={`mt-1 text-sm font-bold ${pnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}
                    >
                      {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Orders table */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="font-semibold">Recent Orders</h2>
          <select
            className="ml-auto rounded-md border border-gray-200 px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s || "All statuses"}
              </option>
            ))}
          </select>
        </div>
        {orders.isLoading ? (
          <p className="text-sm text-gray-400 dark:text-gray-500">Loading…</p>
        ) : (
          <OrdersTable orders={orders.data ?? []} />
        )}
      </div>

      {/* Failed orders */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
        <button
          className="flex w-full items-center justify-between text-left"
          onClick={() => setShowFailed((v) => !v)}
        >
          <div className="flex items-center gap-2">
            <h2 className="font-semibold">Failed Orders</h2>
            {(failedOrders.data?.length ?? 0) > 0 && (
              <StatusBadge status="rejected" />
            )}
          </div>
          <span className="text-xs text-gray-400 dark:text-gray-500">{showFailed ? "▲" : "▼"}</span>
        </button>
        {showFailed && (
          <div className="mt-4 overflow-x-auto">
            {failedOrders.data?.length === 0 ? (
              <p className="text-sm text-gray-400 dark:text-gray-500">No unresolved failed orders</p>
            ) : (
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700 dark:text-gray-400">
                    <th className="py-2 pr-4">Symbol</th>
                    <th className="py-2 pr-4">Side</th>
                    <th className="py-2 pr-4">Amount</th>
                    <th className="py-2 pr-4">Strategy</th>
                    <th className="py-2 pr-4">Error</th>
                    <th className="py-2">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {(failedOrders.data ?? []).map((f) => (
                    <tr key={f.id} className="border-b border-gray-100 last:border-0 dark:border-gray-800">
                      <td className="py-2 pr-4 font-medium">{f.symbol}</td>
                      <td className="py-2 pr-4">
                        <StatusBadge status={f.side} />
                      </td>
                      <td className="py-2 pr-4">{f.requested_amount}</td>
                      <td className="py-2 pr-4 text-gray-500 dark:text-gray-400">{f.strategy_name || "—"}</td>
                      <td className="py-2 pr-4 text-red-600 text-xs max-w-xs truncate dark:text-red-400">
                        {f.error_reason}
                      </td>
                      <td className="py-2 text-xs text-gray-400 dark:text-gray-500" suppressHydrationWarning>
                        {new Date(f.timestamp).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
