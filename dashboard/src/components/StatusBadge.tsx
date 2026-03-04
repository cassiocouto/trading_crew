interface Props {
  status: string;
}

const COLOR: Record<string, string> = {
  filled: "bg-green-100 text-green-800",
  open: "bg-blue-100 text-blue-800",
  pending: "bg-yellow-100 text-yellow-800",
  partially_filled: "bg-orange-100 text-orange-800",
  cancelled: "bg-gray-100 text-gray-600",
  rejected: "bg-red-100 text-red-800",
  buy: "bg-green-100 text-green-800",
  sell: "bg-red-100 text-red-800",
  active: "bg-green-100 text-green-800",
  inactive: "bg-gray-100 text-gray-600",
};

export function StatusBadge({ status }: Props) {
  const cls = COLOR[status.toLowerCase()] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}
