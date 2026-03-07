import type { AgentStatusResponse } from "@/types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  agent: AgentStatusResponse;
}

export function AgentCard({ agent }: Props) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">{agent.name}</h3>
        <StatusBadge status={agent.is_active ? "active" : "inactive"} />
      </div>
      <p className="mt-1 text-xs text-gray-500">{agent.role}</p>
      <dl className="mt-3 space-y-1 text-sm text-gray-600">
        <div className="flex justify-between">
          <dt>Advisory activations today</dt>
          <dd className="font-medium">{agent.advisory_activations_today}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Last active</dt>
          <dd className="font-medium">
            {agent.last_run_at ? new Date(agent.last_run_at).toLocaleString() : "Never"}
          </dd>
        </div>
      </dl>
    </div>
  );
}
