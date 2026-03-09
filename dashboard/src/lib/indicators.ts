/**
 * Client-side technical indicator series computation.
 *
 * All formulas mirror TechnicalAnalyzer
 * (src/trading_crew/services/technical_analyzer.py) exactly so that chart
 * overlays match the backend's decision values.
 *
 * Note on EMA warm-up: EMA is seeded with a simple average of the first
 * `period` bars.  Values for the first ~3× period bars are still approximate
 * as the EMA has not fully converged — this is a standard display
 * approximation consistent with most charting packages.
 */

import type { OHLCVBar } from "@/types";

export type TV = { time: number; value: number };

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * EMA seeded with SMA of the first `period` bars (matches
 * TechnicalAnalyzer._ema).  Returns a series starting at bar index
 * `period - 1` — the first `period - 1` bars are omitted.
 */
function _emaSmaSeeded(closes: number[], period: number): number[] {
  if (closes.length < period) return [];
  const k = 2 / (period + 1);
  let ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  const out: number[] = [ema];
  for (let i = period; i < closes.length; i++) {
    ema = (closes[i] - ema) * k + ema;
    out.push(ema);
  }
  return out;
}

/**
 * EMA seeded at the very first value (no SMA seed).  Matches
 * TechnicalAnalyzer._ema_series — used internally for MACD so that the
 * histogram matches the backend calculation.
 */
function _emaRaw(values: number[], period: number): number[] {
  if (values.length === 0) return [];
  const k = 2 / (period + 1);
  let ema = values[0];
  const out = [ema];
  for (let i = 1; i < values.length; i++) {
    ema = (values[i] - ema) * k + ema;
    out.push(ema);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * EMA aligned to OHLCV bar timestamps.
 * Returns entries starting from bar index `period - 1` (first valid value).
 */
export function emaAligned(bars: OHLCVBar[], period: number): TV[] {
  if (bars.length < period) return [];
  const closes = bars.map((b) => b.close);
  const series = _emaSmaSeeded(closes, period);
  return series.map((value, i) => ({ time: bars[i + period - 1].timestamp, value }));
}

/**
 * Bollinger Bands aligned to OHLCV bar timestamps.
 * Defaults: period = 20, mult = 2, matching TechnicalAnalyzer._sma_std.
 * Uses population standard deviation (not sample), consistent with the backend.
 */
export function bollingerAligned(
  bars: OHLCVBar[],
  period = 20,
  mult = 2,
): { upper: TV[]; middle: TV[]; lower: TV[] } {
  const upper: TV[] = [];
  const middle: TV[] = [];
  const lower: TV[] = [];

  for (let i = period - 1; i < bars.length; i++) {
    const window = bars.slice(i - period + 1, i + 1).map((b) => b.close);
    const mean = window.reduce((a, b) => a + b, 0) / period;
    const variance = window.reduce((acc, x) => acc + (x - mean) ** 2, 0) / period;
    const std = Math.sqrt(variance);
    const t = bars[i].timestamp;
    upper.push({ time: t, value: mean + mult * std });
    middle.push({ time: t, value: mean });
    lower.push({ time: t, value: mean - mult * std });
  }

  return { upper, middle, lower };
}

/**
 * RSI(14) aligned to OHLCV bar timestamps using Wilder smoothing.
 * Matches TechnicalAnalyzer._rsi exactly.
 * Returns from bar index `period` (first bar with a valid RSI value).
 */
export function rsiAligned(bars: OHLCVBar[], period = 14): TV[] {
  const closes = bars.map((b) => b.close);
  if (closes.length < period + 1) return [];

  const deltas = closes.slice(1).map((v, i) => v - closes[i]);
  const gains = deltas.map((d) => (d > 0 ? d : 0));
  const losses = deltas.map((d) => (d < 0 ? -d : 0));

  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;

  const toRsi = (ag: number, al: number) => (al === 0 ? 100 : 100 - 100 / (1 + ag / al));

  // First valid RSI value is at bar index `period` (needs period+1 closes)
  const out: TV[] = [{ time: bars[period].timestamp, value: toRsi(avgGain, avgLoss) }];

  for (let i = period; i < deltas.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
    out.push({ time: bars[i + 1].timestamp, value: toRsi(avgGain, avgLoss) });
  }

  return out;
}

/**
 * MACD(12, 26, 9) aligned to OHLCV bar timestamps.
 * Uses _emaRaw (seeds at first value) to match TechnicalAnalyzer._macd.
 * Skips the first WARMUP bars where the EMA has not yet stabilised.
 */
export function macdAligned(bars: OHLCVBar[]): {
  line: TV[];
  signal: TV[];
  histogram: TV[];
} {
  const empty = { line: [], signal: [], histogram: [] };
  if (bars.length < 36) return empty;

  const closes = bars.map((b) => b.close);
  const ema12 = _emaRaw(closes, 12);
  const ema26 = _emaRaw(closes, 26);
  const macdRaw = ema12.map((v, i) => v - ema26[i]);
  const signalRaw = _emaRaw(macdRaw, 9);

  const WARMUP = 35;
  const line: TV[] = [];
  const signal: TV[] = [];
  const histogram: TV[] = [];

  for (let i = WARMUP; i < bars.length; i++) {
    const t = bars[i].timestamp;
    const m = macdRaw[i];
    const s = signalRaw[i];
    line.push({ time: t, value: m });
    signal.push({ time: t, value: s });
    histogram.push({ time: t, value: m - s });
  }

  return { line, signal, histogram };
}
