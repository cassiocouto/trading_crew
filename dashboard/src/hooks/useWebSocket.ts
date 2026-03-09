"use client";

import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WS_URL } from "@/lib/api";
import type { WsEvent } from "@/types";

// Map from WS event type to the React Query keys that should be invalidated.
const EVENT_QUERY_MAP: Record<string, string[][]> = {
  cycle_complete: [["cycles"], ["portfolio"], ["pnl-history"]],
  order_filled: [["orders"], ["portfolio"]],
  signal_generated: [["signals"], ["strategy-stats"]],
  circuit_breaker: [["system-status"], ["cycles"]],
  controls_updated: [["controls"]],
};

export function useWebSocket() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.debug("[WS] connected");
    };

    ws.onmessage = (evt) => {
      try {
        const event = JSON.parse(evt.data as string) as WsEvent;
        const keys = EVENT_QUERY_MAP[event.type] ?? [];
        keys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      console.debug("[WS] disconnected — reconnecting in 5s");
      reconnectTimer.current = setTimeout(connect, 5000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [queryClient]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
