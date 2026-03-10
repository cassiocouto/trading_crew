interface Props {
  status: string;
}

const COLOR: Record<string, string> = {
  filled: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-400",
  open: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-400",
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-400",
  partially_filled: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-400",
  cancelled: "bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400",
  rejected: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-400",
  buy: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-400",
  sell: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-400",
  active: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-400",
  inactive: "bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-400",
};

export function StatusBadge({ status }: Props) {
  const cls = COLOR[status.toLowerCase()] ?? "bg-gray-100 text-gray-700 dark:bg-gray-500/15 dark:text-gray-400";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}
