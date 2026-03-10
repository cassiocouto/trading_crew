"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ControlsUpdate, SettingsUpdate } from "@/types";

const STALE = 30_000; // 30 seconds

export const usePortfolio = () =>
  useQuery({ queryKey: ["portfolio"], queryFn: api.getPortfolio, staleTime: STALE });

export const usePnlHistory = (limit = 100) =>
  useQuery({ queryKey: ["pnl-history", limit], queryFn: () => api.getPnlHistory(limit), staleTime: STALE });

export const useOrders = (limit = 50, status?: string, symbol?: string, refetchInterval?: number) =>
  useQuery({
    queryKey: ["orders", limit, status, symbol],
    queryFn: () => api.getOrders(limit, status, symbol),
    staleTime: STALE,
    refetchInterval,
  });

export const useFailedOrders = (unresolvedOnly = true, symbol?: string, refetchInterval?: number) =>
  useQuery({
    queryKey: ["failed-orders", unresolvedOnly, symbol],
    queryFn: () => api.getFailedOrders(unresolvedOnly, symbol),
    staleTime: STALE,
    refetchInterval,
  });

export const useSignals = (limit = 50, strategy?: string, symbol?: string, refetchInterval?: number) =>
  useQuery({
    queryKey: ["signals", limit, strategy, symbol],
    queryFn: () => api.getSignals(limit, strategy, symbol),
    staleTime: STALE,
    refetchInterval,
  });

export const useStrategyStats = (refetchInterval?: number) =>
  useQuery({
    queryKey: ["strategy-stats"],
    queryFn: api.getStrategyStats,
    staleTime: STALE,
    refetchInterval,
  });

export const useCycles = (limit = 50) =>
  useQuery({ queryKey: ["cycles", limit], queryFn: () => api.getCycles(limit), staleTime: STALE });

export const useLatestCycle = (refetchInterval?: number) =>
  useQuery({
    queryKey: ["latest-cycle"],
    queryFn: api.getLatestCycle,
    staleTime: STALE,
    refetchInterval,
  });

export const useSystemStatus = () =>
  useQuery({ queryKey: ["system-status"], queryFn: api.getSystemStatus, staleTime: STALE });

export const useAgents = () =>
  useQuery({ queryKey: ["agents"], queryFn: api.getAgents, staleTime: STALE });

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: api.getSettings, staleTime: 60_000 });

export const useUpdateSettings = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SettingsUpdate) => api.updateSettings(data),
    onSuccess: () => {
      // Invalidate both: settings (form state) and system-status (threshold
      // displayed on Overview, Agents, and Markets pages).
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["system-status"] });
    },
  });
};

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

export const useControls = () =>
  useQuery({
    queryKey: ["controls"],
    queryFn: api.getControls,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });

export const useUpdateControls = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ControlsUpdate) => api.updateControls(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["controls"] });
    },
  });
};

// ---------------------------------------------------------------------------
// Market data
// ---------------------------------------------------------------------------

// Symbol ticker auto-refreshes every 15 s everywhere it is used — it drives
// the live price display in the Markets page header.
export const useMarketSymbols = () =>
  useQuery({
    queryKey: ["market-symbols"],
    queryFn: api.getMarketSymbols,
    staleTime: 15_000,
    refetchInterval: 15_000,
  });

export const useMarketOHLCV = (symbol: string, timeframe = "1h", limit = 120) =>
  useQuery({
    queryKey: ["market-ohlcv", symbol, timeframe, limit],
    queryFn: () => api.getMarketOHLCV(symbol, timeframe, limit),
    staleTime: 60_000,
    refetchInterval: 60_000,
    enabled: Boolean(symbol),
  });
