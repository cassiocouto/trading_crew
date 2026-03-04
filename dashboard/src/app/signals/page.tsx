"use client";

import { useState } from "react";
import { SignalRow } from "@/components/SignalRow";
import { useSignals, useStrategyStats } from "@/hooks/useApi";

export default function SignalsPage() {
  const [strategy, setStrategy] = useState("");
  const signals = useSignals(100, strategy || undefined);
  const stats = useStrategyStats();

  const strategies = Array.from(
    new Set((stats.data ?? []).map((s) => s.strategy_name))
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Signals</h1>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <select
          className="rounded-md border border-gray-200 px-3 py-1.5 text-sm"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
        >
          <option value="">All strategies</option>
          {strategies.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <span className="text-xs text-gray-400">
          {signals.data?.length ?? 0} signals shown
        </span>
      </div>

      {/* Signal feed */}
      <div className="space-y-2">
        {signals.isLoading && <p className="text-sm text-gray-400">Loading…</p>}
        {(signals.data ?? []).map((s) => (
          <SignalRow key={s.id} signal={s} />
        ))}
        {!signals.isLoading && (signals.data ?? []).length === 0 && (
          <p className="text-sm text-gray-400">No signals found</p>
        )}
      </div>
    </div>
  );
}
