"use client";

import { AgentCard } from "@/components/AgentCard";
import { useAgents, useSystemStatus } from "@/hooks/useApi";

export default function AgentsPage() {
  const agents = useAgents();
  const status = useSystemStatus();

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Agents</h1>

      {status.data && (
        <dl className="grid grid-cols-2 gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:grid-cols-3 text-sm">
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wide">Version</dt>
            <dd className="font-medium">{status.data.version}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wide">Trading Mode</dt>
            <dd className="font-medium capitalize">{status.data.trading_mode}</dd>
          </div>
          <div>
            <dt className="text-xs text-gray-500 uppercase tracking-wide">Total Cycles</dt>
            <dd className="font-medium">{status.data.total_cycles}</dd>
          </div>
        </dl>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {agents.isLoading && <p className="text-sm text-gray-400">Loading…</p>}
        {(agents.data ?? []).map((a) => (
          <AgentCard key={a.name} agent={a} />
        ))}
      </div>

      <p className="text-xs text-gray-400 max-w-prose">
        Agent activity is inferred from the most recently completed trading cycle.
        Pipeline mode and estimated token usage are read from application settings.
        Real-time CrewAI trace data is not available cross-process.
      </p>
    </div>
  );
}
