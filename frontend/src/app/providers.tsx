"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";
import { CommandPaletteProvider } from "@/components/site/command-palette";
import { useMotionPref } from "@/lib/motion-pref";

let browserQueryClient: QueryClient | undefined;

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
  });
}

function getQueryClient() {
  // Isolated per server render; one shared client in the browser.
  if (typeof window === "undefined") return makeClient();
  browserQueryClient ??= makeClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  const motionPref = useMotionPref();
  return (
    // "user" honours the OS prefers-reduced-motion setting; the in-app toggle can override it.
    <MotionConfig
      reducedMotion={motionPref === "full" ? "never" : motionPref === "reduced" ? "always" : "user"}
    >
      <QueryClientProvider client={getQueryClient()}>
        <CommandPaletteProvider>{children}</CommandPaletteProvider>
      </QueryClientProvider>
    </MotionConfig>
  );
}
