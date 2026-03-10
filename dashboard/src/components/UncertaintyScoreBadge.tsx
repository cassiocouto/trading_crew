import { HelpTooltip } from "@/components/HelpTooltip";

interface Props {
  /** Raw uncertainty score [0–1] from the latest cycle. */
  score: number;
  /** The configured activation threshold — used to colour the badge. */
  threshold?: number;
  /** Whether the advisory crew was actually invoked this cycle. */
  advisoryRan?: boolean;
  /** Render a compact inline chip instead of the full label + bar layout. */
  compact?: boolean;
}

const TOOLTIP =
  "The uncertainty score (0–1) is computed each cycle from six market factors: " +
  "volatile regime (ATR/price), sentiment extremes (Fear & Greed Index), " +
  "low sentiment confidence, strategy disagreement (conflicting buy/sell votes), " +
  "drawdown proximity (how close to the circuit-breaker limit), and regime change " +
  "(symbols switching between trending / ranging / volatile). " +
  "Each factor is multiplied by its configurable weight and the results are summed and clamped to [0–1]. " +
  "When the score reaches the activation threshold the advisory AI crew is invoked once for that cycle.";

function scoreColor(score: number, threshold: number) {
  if (score >= threshold)
    return {
      bg: "bg-red-100 dark:bg-red-500/15",
      text: "text-red-700 dark:text-red-400",
      bar: "bg-red-400",
    };
  if (score >= threshold * 0.6)
    return {
      bg: "bg-amber-100 dark:bg-amber-500/15",
      text: "text-amber-700 dark:text-amber-400",
      bar: "bg-amber-400",
    };
  return {
    bg: "bg-green-100 dark:bg-green-500/15",
    text: "text-green-700 dark:text-green-400",
    bar: "bg-green-400",
  };
}

export function UncertaintyScoreBadge({
  score,
  threshold = 0.6,
  advisoryRan = false,
  compact = false,
}: Props) {
  const c = scoreColor(score, threshold);

  if (compact) {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${c.bg} ${c.text}`}>
        {score.toFixed(2)}
        {advisoryRan && <span title="Advisory crew ran this cycle">⚡</span>}
      </span>
    );
  }

  const pct = Math.min(100, Math.round(score * 100));
  const thresholdPct = Math.min(100, Math.round(threshold * 100));

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="flex items-center text-gray-500 dark:text-gray-400">
          Uncertainty score
          <HelpTooltip text={TOOLTIP} />
        </span>
        <span className={`rounded-full px-2 py-0.5 font-semibold ${c.bg} ${c.text}`}>
          {score.toFixed(2)}
          {advisoryRan && <span className="ml-1" title="Advisory crew ran this cycle">⚡</span>}
        </span>
      </div>

      {/* Progress bar with threshold marker */}
      <div className="relative h-2 w-full overflow-visible rounded-full bg-gray-100 dark:bg-gray-800">
        <div
          className={`h-full rounded-full transition-all ${c.bar}`}
          style={{ width: `${pct}%` }}
        />
        {/* Threshold tick */}
        <div
          className="absolute top-[-2px] h-[10px] w-px bg-gray-400 dark:bg-gray-500"
          style={{ left: `${thresholdPct}%` }}
          title={`Activation threshold: ${threshold.toFixed(2)}`}
        />
      </div>

      <div className="flex items-center justify-between text-[10px] text-gray-400 dark:text-gray-500">
        <span>0</span>
        <span>threshold {threshold.toFixed(2)}</span>
        <span>1</span>
      </div>

      {advisoryRan && (
        <p className="text-[10px] text-purple-600 dark:text-purple-400">⚡ Advisory crew activated this cycle</p>
      )}
    </div>
  );
}
