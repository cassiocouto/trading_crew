"use client";

import { useState, useEffect } from "react";
import { useTheme } from "next-themes";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
} from "recharts";
import type { PnLPointResponse } from "@/types";

type ViewMode = "balance" | "pnl" | "drawdown";

interface Props {
  data: PnLPointResponse[];
}

function num(v: unknown): number {
  if (typeof v === "number") return v;
  if (typeof v === "string") return Number(v) || 0;
  return 0;
}

const TAB_CLASSES =
  "rounded-md px-3 py-1 text-xs font-medium transition-colors cursor-pointer";
const ACTIVE =
  "bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300";
const INACTIVE =
  "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200";

export function RichEquityCurve({ data }: Props) {
  const [view, setView] = useState<ViewMode>("balance");
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const isDark = mounted && resolvedTheme === "dark";

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
    realized: Number(d.realized_pnl.toFixed(2)),
    unrealized: Number(d.unrealized_pnl.toFixed(2)),
    drawdown: Number((-d.drawdown_pct).toFixed(2)),
  }));

  const gridStroke = isDark ? "#1f2937" : "#f0f0f0";
  const tickColor = isDark ? "#9ca3af" : "#6b7280";

  const tabs: { key: ViewMode; label: string }[] = [
    { key: "balance", label: "Balance" },
    { key: "pnl", label: "P&L Breakdown" },
    { key: "drawdown", label: "Drawdown" },
  ];

  return (
    <div>
      <div className="mb-3 flex gap-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setView(t.key)}
            className={`${TAB_CLASSES} ${view === t.key ? ACTIVE : INACTIVE}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={280}>
        {view === "balance" ? (
          <AreaChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
            <XAxis dataKey="time" tick={{ fontSize: 11, fill: tickColor }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: tickColor }} width={80} tickFormatter={(v: number) => `$${v.toLocaleString()}`} />
            <Tooltip
              formatter={(v) => [`$${num(v).toLocaleString()}`, "Balance"]}
              contentStyle={{
                backgroundColor: isDark ? "#111827" : "#fff",
                borderColor: isDark ? "#374151" : "#e5e7eb",
                color: isDark ? "#e5e7eb" : "#171717",
              }}
            />
            <Area type="monotone" dataKey="balance" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.1} strokeWidth={2} />
          </AreaChart>
        ) : view === "pnl" ? (
          <ComposedChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
            <XAxis dataKey="time" tick={{ fontSize: 11, fill: tickColor }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: tickColor }} width={80} tickFormatter={(v: number) => `$${v.toLocaleString()}`} />
            <Tooltip
              formatter={(v, name) => [`$${num(v).toLocaleString()}`, name === "realized" ? "Realized" : "Unrealized"]}
              contentStyle={{
                backgroundColor: isDark ? "#111827" : "#fff",
                borderColor: isDark ? "#374151" : "#e5e7eb",
                color: isDark ? "#e5e7eb" : "#171717",
              }}
            />
            <Area type="monotone" dataKey="realized" stroke="#16a34a" fill="#16a34a" fillOpacity={0.15} strokeWidth={2} />
            <Area type="monotone" dataKey="unrealized" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.1} strokeWidth={2} />
          </ComposedChart>
        ) : (
          <AreaChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
            <XAxis dataKey="time" tick={{ fontSize: 11, fill: tickColor }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11, fill: tickColor }} width={80} tickFormatter={(v: number) => `${v}%`} />
            <Tooltip
              formatter={(v) => [`${num(v).toFixed(1)}%`, "Drawdown"]}
              contentStyle={{
                backgroundColor: isDark ? "#111827" : "#fff",
                borderColor: isDark ? "#374151" : "#e5e7eb",
                color: isDark ? "#e5e7eb" : "#171717",
              }}
            />
            <Area type="monotone" dataKey="drawdown" stroke="#dc2626" fill="#dc2626" fillOpacity={0.15} strokeWidth={2} />
          </AreaChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
