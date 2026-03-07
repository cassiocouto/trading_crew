"use client";

import { AlertTriangle, Shield } from "lucide-react";
import { AgentCard } from "@/components/AgentCard";
import { MetricCard } from "@/components/MetricCard";
import { PositionsTable } from "@/components/PositionsTable";
import { StatusBadge } from "@/components/StatusBadge";
import { useAgents, useLatestCycle, usePortfolio, useSystemStatus } from "@/hooks/useApi";

export default function OverviewPage() {
  const portfolio = usePortfolio();
  const latestCycle = useLatestCycle();
  const systemStatus = useSystemStatus();
  const agents = useAgents();

  const p = portfolio.data;
  const cb = systemStatus.data?.circuit_breaker_active ?? false;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Overview</h1>

      {cb && (
        <div className="flex items-center gap-3 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-red-700">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span className="font-medium">Circuit breaker active — trading halted</span>
        </div>
      )}

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard
          label="Balance"
          value={p ? `$${p.balance_quote.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—"}
        />
        <MetricCard
          label="Realized PnL"
          value={p ? `${p.realized_pnl >= 0 ? "+" : ""}$${p.realized_pnl.toFixed(2)}` : "—"}
          highlight={p ? (p.realized_pnl >= 0 ? "green" : "red") : "neutral"}
        />
        <MetricCard
          label="Open Positions"
          value={p?.num_positions ?? "—"}
        />
        <MetricCard
          label="Total Cycles"
          value={systemStatus.data?.total_cycles ?? "—"}
          sub={
            latestCycle.data
              ? `Last: ${new Date(latestCycle.data.timestamp).toLocaleTimeString()}`
              : undefined
          }
        />
      </div>

      {/* Last cycle badge */}
      {latestCycle.data && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-gray-500">Last cycle #{latestCycle.data.cycle_number}:</span>
          <StatusBadge status={latestCycle.data.circuit_breaker_tripped ? "rejected" : "filled"} />
          <span className="text-gray-600">
            {latestCycle.data.num_orders_filled} fills / {latestCycle.data.num_signals} signals
          </span>
        </div>
      )}

      {/* Open positions */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold">Open Positions</h2>
        <PositionsTable positions={p?.positions ?? {}} />
      </div>

      {/* Advisory & Agent status */}
      <div>
        <h2 className="mb-3 font-semibold">Advisory Crew</h2>
        {systemStatus.data && (
          <div className="mb-4 flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm text-sm">
            <Shield className="h-5 w-5 text-purple-600 shrink-0" />
            <span className="font-medium">
              Advisory {systemStatus.data.advisory_enabled ? "enabled" : "disabled"}
            </span>
            <span className="text-gray-400">|</span>
            <span className="text-gray-600">
              Threshold: {systemStatus.data.advisory_activation_threshold.toFixed(2)}
            </span>
          </div>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(agents.data ?? []).map((a) => (
            <AgentCard key={a.name} agent={a} />
          ))}
        </div>
      </div>
    </div>
  );
}
