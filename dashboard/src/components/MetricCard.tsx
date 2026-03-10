interface Props {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: "green" | "red" | "neutral";
}

export function MetricCard({ label, value, sub, highlight = "neutral" }: Props) {
  const valueClass =
    highlight === "green"
      ? "text-green-600 dark:text-green-400"
      : highlight === "red"
      ? "text-red-600 dark:text-red-400"
      : "text-gray-900 dark:text-gray-100";

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500" suppressHydrationWarning>{sub}</p>}
    </div>
  );
}
