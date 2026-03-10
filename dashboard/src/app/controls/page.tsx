"use client";

import { useState } from "react";
import { AlertTriangle, BrainCircuit, Play, Zap } from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";
import { useControls, useUpdateControls } from "@/hooks/useApi";
import { useWebSocket } from "@/hooks/useWebSocket";

export default function ControlsPage() {
  useWebSocket();
  const { data: controls, isLoading } = useControls();
  const updateControls = useUpdateControls();

  const [confirmPauseExecution, setConfirmPauseExecution] = useState(false);

  const toggle = async (field: "execution_paused" | "advisory_paused", value: boolean) => {
    if (field === "execution_paused" && value === true) {
      setConfirmPauseExecution(true);
      return;
    }
    try {
      await updateControls.mutateAsync({ [field]: value });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update controls.");
    }
  };

  const confirmPause = async () => {
    try {
      await updateControls.mutateAsync({ execution_paused: true });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to pause execution.");
    } finally {
      setConfirmPauseExecution(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Controls</h1>
        <p className="mt-0.5 text-sm text-gray-500">
          Toggle execution and advisory agents. Changes take effect on the next trading cycle.
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="h-44 animate-pulse rounded-xl bg-gray-100" />
          <div className="h-44 animate-pulse rounded-xl bg-gray-100" />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Execution Agent Toggle */}
          <ControlCard
            icon={<Zap size={20} />}
            title="Execution Agent"
            helpText="Controls whether the bot is allowed to place orders on the exchange. When paused, every other phase still runs normally: market data is fetched, indicators are computed, strategies generate signals, and risk checks run — but no order is submitted. Resume when you are ready to trade again. Takes effect on the next cycle (within one loop interval)."
            description="When paused, the bot still runs analysis and generates signals but will not place any orders on the exchange."
            paused={controls?.execution_paused ?? false}
            available={true}
            unavailableReason={null}
            pending={updateControls.isPending}
            onToggle={(paused) => toggle("execution_paused", paused)}
          />

          {/* Advisory Crew Toggle */}
          <ControlCard
            icon={<BrainCircuit size={20} />}
            title="Advisory Crew"
            helpText={
              "The advisory crew is not a persistent process — it has no always-on 'active' mode. " +
              "Each cycle the bot computes an uncertainty score (0–1) from six market factors " +
              "(volatility, sentiment, strategy disagreement, drawdown proximity, regime change). " +
              "If the score reaches the activation threshold (default 0.6) the crew runs once " +
              "for that cycle, reviews the signals, and stops. The next cycle starts fresh and " +
              "the score is recomputed from scratch.\n\n" +
              "Pausing here forces the crew to be skipped every cycle regardless of the score — " +
              "useful when you want to reduce LLM costs or investigate signals without AI interference. " +
              "The deterministic pipeline continues running normally either way."
            }
            description="AI agents that activate automatically when the uncertainty score exceeds the threshold — at most once per cycle. Idle whenever market conditions are clear."
            paused={controls?.advisory_paused ?? false}
            available={controls?.advisory_available ?? false}
            unavailableReason={
              controls?.advisory_available === false
                ? "No LLM API key configured. Set OPENAI_API_KEY in .env and restart the bot."
                : null
            }
            pending={updateControls.isPending}
            onToggle={(paused) => toggle("advisory_paused", paused)}
          />
        </div>
      )}

      {/* Confirm pause dialog */}
      {confirmPauseExecution && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 shrink-0 text-amber-500" size={20} />
              <div>
                <h2 className="font-semibold text-gray-900">Pause execution?</h2>
                <p className="mt-1 text-sm text-gray-500">
                  The bot will continue running market analysis and generating signals, but{" "}
                  <strong>no orders will be placed</strong> until execution is unpaused.
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => setConfirmPauseExecution(false)}
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmPause}
                className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
              >
                Yes, pause execution
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface ControlCardProps {
  icon: React.ReactNode;
  title: string;
  helpText?: string;
  description: string;
  paused: boolean;
  available: boolean;
  unavailableReason: string | null;
  pending: boolean;
  onToggle: (paused: boolean) => void;
}

function ControlCard({
  icon,
  title,
  helpText,
  description,
  paused,
  available,
  unavailableReason,
  pending,
  onToggle,
}: ControlCardProps) {
  const isRunning = !paused;
  const disabled = (!available && paused) || pending;

  return (
    <div
      className={`rounded-xl border bg-white p-5 shadow-sm transition-colors ${
        !available ? "opacity-60" : ""
      } ${paused ? "border-amber-200" : "border-gray-200"}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div
          className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${
            isRunning && available ? "bg-indigo-50 text-indigo-600" : "bg-gray-100 text-gray-400"
          }`}
        >
          {icon}
        </div>

        {/* Read-only status badge — use the Pause/Resume button below to toggle */}
        <span
          title={unavailableReason ?? undefined}
          className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium select-none ${
            isRunning && available
              ? "bg-green-100 text-green-700"
              : "bg-amber-100 text-amber-700"
          }`}
        >
          <span
            className={`size-2 rounded-full ${
              isRunning && available ? "bg-green-500" : "bg-amber-500"
            }`}
          />
          {pending ? "Updating…" : isRunning && available ? "Running" : "Paused"}
        </span>
      </div>

      <h3 className="mt-4 flex items-center font-semibold text-gray-900">
        {title}
        {helpText && <HelpTooltip text={helpText} />}
      </h3>
      <p className="mt-1 text-sm text-gray-500">{description}</p>

      {unavailableReason && (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          {unavailableReason}
        </div>
      )}

      {available && !unavailableReason && (
        <button
          onClick={() => onToggle(!paused)}
          disabled={pending}
          className={`mt-4 w-full rounded-lg border px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
            paused
              ? "border-green-200 bg-green-50 text-green-700 hover:bg-green-100"
              : "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100"
          }`}
        >
          {paused ? (
            <span className="flex items-center justify-center gap-1.5">
              <Play size={13} />
              Resume {title}
            </span>
          ) : (
            `Pause ${title}`
          )}
        </button>
      )}
    </div>
  );
}
