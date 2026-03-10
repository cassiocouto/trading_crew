import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { SignalResponse } from "@/types";

interface Props {
  signal: SignalResponse;
}

export function SignalRow({ signal }: Props) {
  const Icon =
    signal.signal_type === "buy"
      ? TrendingUp
      : signal.signal_type === "sell"
      ? TrendingDown
      : Minus;

  const iconClass =
    signal.signal_type === "buy"
      ? "text-green-500"
      : signal.signal_type === "sell"
      ? "text-red-500"
      : "text-gray-400 dark:text-gray-500";

  return (
    <div className="flex items-start gap-3 rounded-lg border border-gray-100 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${iconClass}`} />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-gray-900 dark:text-gray-100">{signal.symbol}</span>
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
            {signal.strategy_name}
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-500">{signal.strength}</span>
        </div>
        <p className="mt-0.5 text-xs text-gray-500 truncate dark:text-gray-400">{signal.reason || "—"}</p>
      </div>
      <div className="text-right shrink-0">
        <div className="text-xs font-medium text-gray-700 dark:text-gray-300">
          {(signal.confidence * 100).toFixed(0)}%
        </div>
        <div className="mt-0.5 h-1.5 w-16 rounded-full bg-gray-200 dark:bg-gray-700">
          <div
            className="h-full rounded-full bg-indigo-500"
            style={{ width: `${signal.confidence * 100}%` }}
          />
        </div>
        <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">
          {new Date(signal.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}
