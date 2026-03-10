import type { PositionResponse } from "@/types";

interface Props {
  positions: Record<string, PositionResponse>;
}

export function PositionsTable({ positions }: Props) {
  const entries = Object.entries(positions);
  if (entries.length === 0) {
    return <p className="text-sm text-gray-400 py-4 dark:text-gray-500">No open positions</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th className="py-2 pr-4">Symbol</th>
            <th className="py-2 pr-4">Amount</th>
            <th className="py-2 pr-4">Entry Price</th>
            <th className="py-2 pr-4">Current Price</th>
            <th className="py-2 pr-4">P&amp;L</th>
            <th className="py-2 pr-4">Strategy</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([symbol, pos]) => {
            const pnl =
              pos.current_price != null
                ? (pos.current_price - pos.entry_price) * pos.amount
                : null;
            return (
              <tr key={symbol} className="border-b border-gray-100 last:border-0 dark:border-gray-800">
                <td className="py-2 pr-4 font-medium">{symbol}</td>
                <td className="py-2 pr-4">{pos.amount.toFixed(6)}</td>
                <td className="py-2 pr-4">${pos.entry_price.toLocaleString()}</td>
                <td className="py-2 pr-4">
                  {pos.current_price != null ? `$${pos.current_price.toLocaleString()}` : "—"}
                </td>
                <td
                  className={`py-2 pr-4 font-medium ${
                    pnl == null ? "text-gray-400 dark:text-gray-500" : pnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
                  }`}
                >
                  {pnl != null ? `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}` : "—"}
                </td>
                <td className="py-2 pr-4 text-gray-500 dark:text-gray-400">{pos.strategy_name || "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
