"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useState, type ReactNode } from "react";

function WsInitialiser() {
  useWebSocket();
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [qc] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={qc}>
      <WsInitialiser />
      {children}
    </QueryClientProvider>
  );
}
