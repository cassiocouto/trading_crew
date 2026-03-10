import type { StrategyStatsResponse } from "@/types";

interface Props {
  stats: StrategyStatsResponse[];
}

export function StrategyStatsTable({ stats }: Props) {
  if (stats.length === 0) {
    return <p className="text-sm text-gray-400 py-4 dark:text-gray-500">No strategy data yet</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th className="py-2 pr-4">Strategy</th>
            <th className="py-2 pr-4">Signals</th>
            <th className="py-2 pr-4">Buys</th>
            <th className="py-2 pr-4">Sells</th>
            <th className="py-2 pr-4">Avg Conf.</th>
            <th className="py-2 pr-4">Orders Placed</th>
            <th className="py-2">Fill Rate</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((s) => {
            const fillRate =
              s.orders_placed > 0
                ? `${((s.orders_filled / s.orders_placed) * 100).toFixed(0)}%`
                : "—";
            return (
              <tr key={s.strategy_name} className="border-b border-gray-100 last:border-0 dark:border-gray-800">
                <td className="py-2 pr-4 font-medium">{s.strategy_name}</td>
                <td className="py-2 pr-4">{s.total_signals}</td>
                <td className="py-2 pr-4 text-green-600 dark:text-green-400">{s.buy_signals}</td>
                <td className="py-2 pr-4 text-red-600 dark:text-red-400">{s.sell_signals}</td>
                <td className="py-2 pr-4">{(s.avg_confidence * 100).toFixed(1)}%</td>
                <td className="py-2 pr-4">{s.orders_placed}</td>
                <td className="py-2">{fillRate}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
