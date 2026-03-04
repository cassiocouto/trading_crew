import type { AgentStatusResponse } from "@/types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  agent: AgentStatusResponse;
}

const AGENT_LABELS: Record<string, string> = {
  market_intelligence: "Market Intelligence",
  strategy: "Strategy",
  execution: "Execution",
};

export function AgentCard({ agent }: Props) {
  const label = AGENT_LABELS[agent.name] ?? agent.name;
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">{label}</h3>
        <StatusBadge status={agent.is_active ? "active" : "inactive"} />
      </div>
      <dl className="mt-3 space-y-1 text-sm text-gray-600">
        <div className="flex justify-between">
          <dt>Pipeline mode</dt>
          <dd className="font-medium">{agent.pipeline_mode}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Est. tokens / cycle</dt>
          <dd className="font-medium">{agent.tokens_estimated.toLocaleString()}</dd>
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
