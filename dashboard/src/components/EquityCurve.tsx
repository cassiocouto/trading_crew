"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { PnLPointResponse } from "@/types";

interface Props {
  data: PnLPointResponse[];
}

export function EquityCurve({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-400">
        No equity data yet
      </div>
    );
  }

  const chartData = data.map((d) => ({
    time: new Date(d.timestamp).toLocaleDateString(),
    balance: Number(d.total_balance_quote.toFixed(2)),
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="time" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 11 }} width={80} tickFormatter={(v) => `$${v.toLocaleString()}`} />
        <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Balance"]} />
        <Line type="monotone" dataKey="balance" stroke="#4f46e5" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
