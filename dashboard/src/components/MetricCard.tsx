interface Props {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: "green" | "red" | "neutral";
}

export function MetricCard({ label, value, sub, highlight = "neutral" }: Props) {
  const valueClass =
    highlight === "green"
      ? "text-green-600"
      : highlight === "red"
      ? "text-red-600"
      : "text-gray-900";

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400" suppressHydrationWarning>{sub}</p>}
    </div>
  );
}
