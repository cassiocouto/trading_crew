"use client";

import { useTheme } from "next-themes";
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
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-400 dark:text-gray-500">
        No equity data yet
      </div>
    );
  }

  const chartData = data.map((d) => ({
    time: new Date(d.timestamp).toLocaleDateString(),
    balance: Number(d.total_balance_quote.toFixed(2)),
  }));

  const gridStroke = isDark ? "#1f2937" : "#f0f0f0";
  const tickColor = isDark ? "#9ca3af" : "#6b7280";

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
        <XAxis dataKey="time" tick={{ fontSize: 11, fill: tickColor }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 11, fill: tickColor }} width={80} tickFormatter={(v) => `$${v.toLocaleString()}`} />
        <Tooltip
          formatter={(v) => [`$${Number(v).toLocaleString()}`, "Balance"]}
          contentStyle={{
            backgroundColor: isDark ? "#111827" : "#ffffff",
            borderColor: isDark ? "#374151" : "#e5e7eb",
            color: isDark ? "#e5e7eb" : "#171717",
          }}
        />
        <Line type="monotone" dataKey="balance" stroke="#4f46e5" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
