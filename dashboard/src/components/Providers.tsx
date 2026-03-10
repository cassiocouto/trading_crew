"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
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
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <WsInitialiser />
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}
