"use client";

import { useState } from "react";
import { Shield, Activity, Clock, ChevronDown, ChevronRight } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { UncertaintyScoreBadge } from "@/components/UncertaintyScoreBadge";
import { useAgents, useCycles, useLatestCycle, useSystemStatus } from "@/hooks/useApi";
import type { CycleResponse } from "@/types";

export default function AgentsPage() {
  const agents = useAgents();
  const status = useSystemStatus();
  const cycles = useCycles(100);
  const latestCycle = useLatestCycle(30_000);

  const advisoryActivations = (cycles.data ?? []).filter((c) => c.advisory_ran);
  const activationsToday = (agents.data ?? []).reduce(
    (sum, a) => sum + a.advisory_activations_today,
    0,
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Advisory Crew</h1>

      {/* Advisory crew status card */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-100">
            <Shield className="h-5 w-5 text-purple-700" />
          </div>
          <div>
            <h2 className="font-semibold text-gray-800">Advisory Crew</h2>
            <p className="text-xs text-gray-500">
              Multi-agent advisory that activates when uncertainty exceeds the threshold
            </p>
          </div>
          {status.data && (
            <div className="ml-auto">
              <StatusBadge status={status.data.advisory_enabled ? "active" : "inactive"} />
            </div>
          )}
        </div>

        {status.data && (
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-sm">
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500 uppercase tracking-wide">Status</dt>
              <dd className="mt-1 font-semibold">
                {status.data.advisory_enabled ? (
                  <span className="text-green-700">Enabled</span>
                ) : (
                  <span className="text-gray-500">Disabled</span>
                )}
              </dd>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500 uppercase tracking-wide">Activation Threshold</dt>
              <dd className="mt-1 font-semibold">{status.data.advisory_activation_threshold.toFixed(2)}</dd>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500 uppercase tracking-wide">Activations Today</dt>
              <dd className="mt-1 font-semibold">{activationsToday}</dd>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500 uppercase tracking-wide">Total Cycles</dt>
              <dd className="mt-1 font-semibold">{status.data.total_cycles}</dd>
            </div>
          </dl>
        )}
        {latestCycle.data && (
          <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50 p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
              Latest Cycle #{latestCycle.data.cycle_number}
            </p>
            <UncertaintyScoreBadge
              score={latestCycle.data.uncertainty_score}
              threshold={status.data?.advisory_activation_threshold}
              advisoryRan={latestCycle.data.advisory_ran}
            />
          </div>
        )}
      </div>

      {/* Agent roster */}
      {agents.data && agents.data.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 font-semibold text-gray-800">Crew Members</h2>
          <div className="divide-y">
            {agents.data.map((a) => (
              <div key={a.name} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                <div>
                  <p className="font-medium text-gray-800">{a.name}</p>
                  <p className="text-xs text-gray-500">{a.role}</p>
                </div>
                <div className="flex items-center gap-4 text-sm text-gray-600">
                  <div className="flex items-center gap-1">
                    <Activity className="h-3.5 w-3.5 text-purple-500" />
                    <span>{a.advisory_activations_today} today</span>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-gray-400">
                    <Clock className="h-3.5 w-3.5" />
                    <span suppressHydrationWarning>
                      {a.last_run_at ? new Date(a.last_run_at).toLocaleString() : "Never"}
                    </span>
                  </div>
                  <StatusBadge status={a.is_active ? "active" : "inactive"} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent advisory activations */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-semibold text-gray-800">Recent Advisory Activations</h2>
        {cycles.isLoading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : advisoryActivations.length === 0 ? (
          <p className="text-sm text-gray-400 italic">No advisory activations recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs font-medium uppercase text-gray-500">
                  <th className="py-2 pr-2 w-4" />
                  <th className="py-2 pr-4">Cycle</th>
                  <th className="py-2 pr-4">Time</th>
                  <th className="py-2 pr-4">Uncertainty</th>
                  <th className="py-2 pr-4">Signals</th>
                  <th className="py-2 pr-4">PnL</th>
                  <th className="py-2">Adjustments</th>
                </tr>
              </thead>
              <tbody>
                {advisoryActivations.slice(0, 20).map((c) => (
                  <AdvisoryActivationRow key={c.id} cycle={c} threshold={status.data?.advisory_activation_threshold} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-400 max-w-prose">
        The advisory crew activates automatically when the uncertainty score exceeds the
        configured threshold. Advisory adjustments are applied to signals before execution.
        Click any row to read the crew&apos;s reasoning.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Advisory activation row — expandable to show crew summary
// ---------------------------------------------------------------------------

function AdvisoryActivationRow({
  cycle: c,
  threshold = 0.6,
}: {
  cycle: CycleResponse;
  threshold?: number;
}) {
  const [expanded, setExpanded] = useState(false);

  let hasAdjustments = false;
  let adjustments: unknown[] = [];
  try {
    const parsed = JSON.parse(c.advisory_adjustments_json);
    adjustments = Array.isArray(parsed) ? parsed : [];
    hasAdjustments = adjustments.length > 0;
  } catch { /* ignore */ }

  const hasSummary = c.advisory_summary && c.advisory_summary.trim().length > 0;
  const expandable = hasSummary || hasAdjustments;

  return (
    <>
      <tr
        className={`border-b last:border-0 ${expandable ? "cursor-pointer hover:bg-gray-50" : ""}`}
        onClick={expandable ? () => setExpanded((v) => !v) : undefined}
      >
        <td className="py-2 pr-2 text-gray-400">
          {expandable && (
            expanded
              ? <ChevronDown size={14} />
              : <ChevronRight size={14} />
          )}
        </td>
        <td className="py-2 pr-4 font-medium">#{c.cycle_number}</td>
        <td className="py-2 pr-4 text-xs text-gray-500" suppressHydrationWarning>
          {new Date(c.timestamp).toLocaleString()}
        </td>
        <td className="py-2 pr-4">
          <span
            className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
              c.uncertainty_score >= threshold
                ? "bg-red-100 text-red-800"
                : c.uncertainty_score >= threshold * 0.6
                  ? "bg-yellow-100 text-yellow-800"
                  : "bg-green-100 text-green-800"
            }`}
          >
            {c.uncertainty_score.toFixed(2)}
          </span>
        </td>
        <td className="py-2 pr-4">{c.num_signals}</td>
        <td className={`py-2 pr-4 font-medium ${c.realized_pnl >= 0 ? "text-green-600" : "text-red-600"}`}>
          {c.realized_pnl >= 0 ? "+" : ""}${c.realized_pnl.toFixed(2)}
        </td>
        <td className="py-2">
          {hasAdjustments ? (
            <span className="text-purple-600">✓ {adjustments.length} applied</span>
          ) : (
            <span className="text-gray-400">approved</span>
          )}
        </td>
      </tr>

      {expanded && expandable && (
        <tr className="border-b bg-purple-50 last:border-0">
          <td colSpan={7} className="px-4 py-3">
            {hasSummary && (
              <div className="mb-2">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-purple-700">
                  Crew reasoning
                </p>
                <p className="whitespace-pre-wrap text-xs text-gray-700">{c.advisory_summary}</p>
              </div>
            )}
            {hasAdjustments && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-purple-700">
                  Adjustments
                </p>
                <ul className="space-y-1">
                  {(adjustments as Array<{action?: string; symbol?: string; reason?: string; params?: Record<string, number>}>).map((adj, i) => (
                    <li key={i} className="text-xs text-gray-700">
                      <span className="font-medium text-purple-700">{adj.action}</span>
                      {adj.symbol && <span className="ml-1 text-gray-500">({adj.symbol})</span>}
                      {adj.reason && <span className="ml-1">— {adj.reason}</span>}
                      {adj.params && Object.keys(adj.params).length > 0 && (
                        <span className="ml-1 text-gray-400">
                          [{Object.entries(adj.params).map(([k, v]) => `${k}: ${v}`).join(", ")}]
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
