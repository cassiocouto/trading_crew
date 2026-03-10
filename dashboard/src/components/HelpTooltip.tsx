"use client";

import { useState, useEffect, useRef } from "react";

interface HelpTooltipProps {
  text: string;
}

/**
 * A small "?" button that toggles an explanatory popover.
 * Closes on outside-click or Escape.
 */
export function HelpTooltip({ text }: HelpTooltipProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onMouse = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouse);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouse);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="ml-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-gray-300 text-[10px] leading-none text-gray-400 hover:border-gray-400 hover:text-gray-600 focus:outline-none dark:border-gray-600 dark:text-gray-500 dark:hover:border-gray-500 dark:hover:text-gray-300"
        aria-label="Help"
      >
        ?
      </button>
      {open && (
        <span className="absolute bottom-full left-1/2 z-50 mb-2 w-56 max-w-[min(224px,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-gray-200 bg-white p-2.5 text-xs leading-relaxed text-gray-600 shadow-lg dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300">
          {text}
          <span className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 border-4 border-transparent border-t-gray-200 dark:border-t-gray-600" />
        </span>
      )}
    </span>
  );
}
