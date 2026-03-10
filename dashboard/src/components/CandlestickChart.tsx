"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import type { IChartApi, Time } from "lightweight-charts";
import type { OHLCVBar } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface OverlayLine {
  /** Stable key used for imperative series tracking — must be unique. */
  id: string;
  /** Label shown in the crosshair tooltip. */
  label: string;
  /** Default series / histogram color. */
  color: string;
  lineStyle?: "solid" | "dashed" | "dotted";
  /** "line" (default) renders a LineSeries; "histogram" renders a HistogramSeries. */
  type?: "line" | "histogram";
  /** Per-bar data.  `color` is used per-bar for histograms (green/red). */
  data: { time: number; value: number; color?: string }[];
  /** Pane index: 0 = main price pane (default), 1 = first sub-pane, 2 = second. */
  pane?: number;
  /** lightweight-charts price scale id.  Defaults to "right". */
  priceScaleId?: string;
}

interface CandlestickChartProps {
  data: OHLCVBar[];
  /** Total chart height in px (includes all panes).  Parent is responsible for
   *  accounting for sub-pane height when RSI / MACD are enabled. */
  height?: number;
  showVolume?: boolean;
  overlayLines?: OverlayLine[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const LINE_STYLE_MAP = { solid: 0, dashed: 1, dotted: 2 } as const;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyLw = any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnySeries = any;

const CHART_COLORS = {
  light: {
    bg: "#ffffff",
    text: "#374151",
    grid: "#f3f4f6",
    border: "#e5e7eb",
  },
  dark: {
    bg: "#030712",
    text: "#d1d5db",
    grid: "#1f2937",
    border: "#374151",
  },
} as const;

/**
 * Diff-based overlay application.  Adds new series, removes stale ones, and
 * updates data for existing series — all without touching the chart instance.
 */
function applyOverlays(
  chart: IChartApi,
  lw: AnyLw,
  overlayLines: OverlayLine[],
  seriesMap: Map<string, AnySeries>,
) {
  const newIds = new Set(overlayLines.map((l) => l.id));

  // Remove stale series
  for (const [id, series] of [...seriesMap.entries()]) {
    if (!newIds.has(id)) {
      try {
        chart.removeSeries(series);
      } catch {
        // series may have already been removed on chart teardown
      }
      seriesMap.delete(id);
    }
  }

  // Add new series / update existing data
  for (const overlay of overlayLines) {
    const pane = overlay.pane ?? 0;
    const priceScaleId = overlay.priceScaleId ?? "right";

    if (!seriesMap.has(overlay.id)) {
      let series: AnySeries;
      if (overlay.type === "histogram") {
        series = chart.addSeries(
          lw.HistogramSeries,
          { color: overlay.color, priceScaleId },
          pane,
        );
      } else {
        const ls = overlay.lineStyle ? LINE_STYLE_MAP[overlay.lineStyle] : 0;
        series = chart.addSeries(
          lw.LineSeries,
          {
            color: overlay.color,
            lineWidth: 1,
            lineStyle: ls,
            priceScaleId,
            title: overlay.label,
            crosshairMarkerVisible: false,
            lastValueVisible: false,
            priceLineVisible: false,
          },
          pane,
        );
      }
      seriesMap.set(overlay.id, series);
    }

    const series = seriesMap.get(overlay.id)!;
    series.setData(
      overlay.data.map((d) => ({
        time: d.time as Time,
        value: d.value,
        ...(d.color !== undefined ? { color: d.color } : {}),
      })),
    );
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CandlestickChart({
  data,
  height = 400,
  showVolume = false,
  overlayLines,
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();

  // Live references so the overlay effect and the async init share state
  // without additional effect dependencies.
  const chartRef = useRef<IChartApi | null>(null);
  const lwRef = useRef<AnyLw>(null);
  const seriesMapRef = useRef<Map<string, AnySeries>>(new Map());

  // Always keep a ref to the latest overlayLines so the async init can read
  // them after the dynamic import resolves (overlay effect may have already
  // fired by then).
  const overlayLinesRef = useRef<OverlayLine[]>(overlayLines ?? []);
  overlayLinesRef.current = overlayLines ?? [];

  const isDark = resolvedTheme === "dark";
  const colors = isDark ? CHART_COLORS.dark : CHART_COLORS.light;

  // ---------------------------------------------------------------------------
  // Effect 1: chart lifecycle — recreate when data / height / volume / theme change.
  // Does NOT depend on overlayLines so EMA / BB toggles never cause a rebuild.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    // Tear down previous instance
    if (chartRef.current) {
      seriesMapRef.current.clear();
      chartRef.current.remove();
      chartRef.current = null;
      lwRef.current = null;
    }

    let observer: ResizeObserver | null = null;
    let destroyed = false;

    const init = async () => {
      const lw = await import("lightweight-charts");
      const el = containerRef.current;
      if (!el || destroyed) return;

      const chart = lw.createChart(el, {
        width: el.clientWidth,
        height,
        layout: {
          background: { type: lw.ColorType.Solid, color: colors.bg },
          textColor: colors.text,
        },
        grid: {
          vertLines: { color: colors.grid },
          horzLines: { color: colors.grid },
        },
        crosshair: { mode: lw.CrosshairMode.Normal },
        rightPriceScale: { borderColor: colors.border },
        timeScale: {
          borderColor: colors.border,
          timeVisible: true,
          secondsVisible: false,
        },
      });

      if (showVolume) {
        const volumeSeries = chart.addSeries(lw.HistogramSeries, {
          color: "#6366f1",
          priceFormat: { type: "volume" as const },
          priceScaleId: "volume",
        });
        chart.priceScale("volume").applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
        });
        volumeSeries.setData(
          data.map((bar) => ({
            time: bar.timestamp as Time,
            value: bar.volume,
            color: bar.close >= bar.open ? "#10b98133" : "#ef444433",
          })),
        );
      }

      const candleSeries = chart.addSeries(lw.CandlestickSeries, {
        upColor: "#10b981",
        downColor: "#ef4444",
        borderDownColor: "#ef4444",
        borderUpColor: "#10b981",
        wickDownColor: "#ef4444",
        wickUpColor: "#10b981",
      });
      candleSeries.setData(
        data.map((bar) => ({
          time: bar.timestamp as Time,
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
        })),
      );

      chart.timeScale().fitContent();

      // Store refs so the overlay effect can update series imperatively
      chartRef.current = chart;
      lwRef.current = lw;

      // Apply any overlays that were already set before init completed
      if (overlayLinesRef.current.length > 0) {
        applyOverlays(chart, lw, overlayLinesRef.current, seriesMapRef.current);
      }

      observer = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect.width;
        if (chart && width) chart.applyOptions({ width });
      });
      observer.observe(el);
    };

    init();

    return () => {
      destroyed = true;
      observer?.disconnect();
      seriesMapRef.current.clear();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        lwRef.current = null;
      }
    };
  }, [data, height, showVolume, colors]);

  // ---------------------------------------------------------------------------
  // Effect 2: overlay series — diff and update without touching the chart.
  // Runs whenever the overlayLines prop changes (e.g. strategy toggle).
  // If the chart hasn't initialised yet the init() function picks up the ref.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const chart = chartRef.current;
    const lw = lwRef.current;
    if (!chart || !lw) return;
    applyOverlays(chart, lw, overlayLines ?? [], seriesMapRef.current);
  }, [overlayLines]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-500"
        style={{ height }}
      >
        No market data collected yet for this symbol.
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
