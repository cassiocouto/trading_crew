"use client";

import { useEffect, useRef } from "react";
import type { IChartApi, Time } from "lightweight-charts";
import type { OHLCVBar } from "@/types";

interface CandlestickChartProps {
  data: OHLCVBar[];
  height?: number;
  showVolume?: boolean;
}

export function CandlestickChart({ data, height = 400, showVolume = false }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || data.length === 0) return;

    let chart: IChartApi | null = null;
    let observer: ResizeObserver | null = null;
    let destroyed = false;

    const init = async () => {
      const lw = await import("lightweight-charts");
      const el = containerRef.current;
      // Bail out if the effect was cleaned up while we were awaiting the import.
      // This prevents a double-chart in React 18 Strict Mode.
      if (!el || destroyed) return;

      chart = lw.createChart(el, {
        width: el.clientWidth,
        height,
        layout: {
          background: { type: lw.ColorType.Solid, color: "#ffffff" },
          textColor: "#374151",
        },
        grid: {
          vertLines: { color: "#f3f4f6" },
          horzLines: { color: "#f3f4f6" },
        },
        crosshair: { mode: lw.CrosshairMode.Normal },
        rightPriceScale: { borderColor: "#e5e7eb" },
        timeScale: {
          borderColor: "#e5e7eb",
          timeVisible: true,
          secondsVisible: false,
        },
      });

      // lightweight-charts v5 API
      const candleSeries = chart.addSeries(lw.CandlestickSeries, {
        upColor: "#10b981",
        downColor: "#ef4444",
        borderDownColor: "#ef4444",
        borderUpColor: "#10b981",
        wickDownColor: "#ef4444",
        wickUpColor: "#10b981",
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
          }))
        );
      }

      candleSeries.setData(
        data.map((bar) => ({
          time: bar.timestamp as Time,
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
        }))
      );

      chart.timeScale().fitContent();

      observer = new ResizeObserver((entries) => {
        const width = entries[0]?.contentRect.width;
        if (chart && width) {
          chart.applyOptions({ width });
        }
      });
      observer.observe(el);
    };

    init();

    return () => {
      destroyed = true;
      observer?.disconnect();
      chart?.remove();
    };
  }, [data, height, showVolume]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-gray-200 bg-gray-50 text-sm text-gray-400"
        style={{ height }}
      >
        No market data collected yet for this symbol.
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
