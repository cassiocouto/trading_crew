import type { OrderResponse } from "@/types";
import { StatusBadge } from "./StatusBadge";

interface Props {
  orders: OrderResponse[];
}

export function OrdersTable({ orders }: Props) {
  if (orders.length === 0) {
    return <p className="text-sm text-gray-400 py-4 dark:text-gray-500">No orders</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th className="py-2 pr-4">Symbol</th>
            <th className="py-2 pr-4">Side</th>
            <th className="py-2 pr-4">Type</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2 pr-4">Amount</th>
            <th className="py-2 pr-4">Fill Price</th>
            <th className="py-2 pr-4">Fee</th>
            <th className="py-2 pr-4">Strategy</th>
            <th className="py-2">Created</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id} className="border-b border-gray-100 last:border-0 dark:border-gray-800">
              <td className="py-2 pr-4 font-medium">{o.symbol}</td>
              <td className="py-2 pr-4">
                <StatusBadge status={o.side} />
              </td>
              <td className="py-2 pr-4 text-gray-500 dark:text-gray-400">{o.order_type}</td>
              <td className="py-2 pr-4">
                <StatusBadge status={o.status} />
              </td>
              <td className="py-2 pr-4">{o.filled_amount.toFixed(6)}</td>
              <td className="py-2 pr-4">
                {o.average_fill_price != null ? `$${o.average_fill_price.toLocaleString()}` : "—"}
              </td>
              <td className="py-2 pr-4">${o.total_fee.toFixed(4)}</td>
              <td className="py-2 pr-4 text-gray-500 dark:text-gray-400">{o.strategy_name || "—"}</td>
              <td className="py-2 text-gray-400 text-xs dark:text-gray-500">
                {new Date(o.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
