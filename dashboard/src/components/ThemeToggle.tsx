"use client";

import { useTheme } from "next-themes";
import { Moon, Sun, Monitor } from "lucide-react";
import { useEffect, useState } from "react";

const CYCLE: ("light" | "dark" | "system")[] = ["light", "dark", "system"];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return <div className="h-9" />;

  const idx = CYCLE.indexOf(theme as (typeof CYCLE)[number]);
  const next = CYCLE[(idx + 1) % CYCLE.length];

  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  const label =
    theme === "dark" ? "Dark" : theme === "light" ? "Light" : "System";

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:bg-indigo-50 hover:text-indigo-700 dark:text-gray-400 dark:hover:bg-indigo-950 dark:hover:text-indigo-300"
      title={`Theme: ${label} — click to switch to ${next}`}
    >
      <Icon size={15} className="shrink-0" />
      {label}
    </button>
  );
}
