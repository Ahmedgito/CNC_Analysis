"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { getReadiness } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { HoverCard } from "../ui/hover-card";

type Tone = "ok" | "warn" | "down" | "checking";

const TONE: Record<Tone, { dot: string; text: string }> = {
  ok: { dot: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-300" },
  warn: { dot: "bg-amber-500", text: "text-amber-700 dark:text-amber-300" },
  down: { dot: "bg-red-500", text: "text-red-700 dark:text-red-300" },
  checking: { dot: "bg-zinc-400", text: "text-zinc-500" },
};

/** Readiness flag names from `/readyz` and how to show them. Unknown flags are humanised. */
const ENGINE_LABELS: Record<string, string> = {
  anthropic_key: "Claude API",
  claude_code_token: "Claude Code",
  groq_key: "Groq",
};

export function describeEngines(providers: Record<string, unknown>): string {
  const names = Object.entries(providers)
    .filter(([, configured]) => configured === true)
    .map(
      ([flag]) =>
        ENGINE_LABELS[flag] ??
        flag
          .replace(/_(key|token)$/, "")
          .split("_")
          .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
          .join(" "),
    );
  return names.length ? names.join(" + ") : "offline rules engine";
}

/** Live backend health: API reachable, database up, which answer engine is configured. */
export function ApiStatus({ className }: { className?: string }) {
  const { data, isError, isPending } = useQuery({
    queryKey: ["readyz"],
    queryFn: ({ signal }) => getReadiness(signal),
    refetchInterval: 20_000,
    retry: 0,
  });

  const engine = describeEngines(data?.providers ?? {});

  const tone: Tone = isPending ? "checking" : isError ? "down" : data?.database ? "ok" : "warn";
  const label =
    tone === "checking"
      ? "Checking"
      : tone === "down"
        ? "API offline"
        : tone === "warn"
          ? "DB issue"
          : "Live";

  return (
    <HoverCard
      side="bottom"
      className="right-0 left-auto origin-top-right"
      content={
        <span className="flex flex-col gap-1.5">
          <span className="font-semibold text-zinc-900 dark:text-white">System status</span>
          <Row k="API" v={isError ? "unreachable" : isPending ? "checking…" : "reachable"} />
          <Row k="Database" v={data ? (data.database ? "connected" : "not connected") : "–"} />
          <Row k="Parts indexed" v={data?.parts != null ? String(data.parts) : "–"} />
          <Row k="Answer engine" v={data ? engine : "–"} />
        </span>
      }
    >
      <button
        type="button"
        aria-label={`System status: ${label}, answer engine ${engine}`}
        className={cn(
          "inline-flex h-8 items-center gap-2 rounded-full border border-zinc-200 bg-white/60 px-3 text-xs font-medium focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:border-white/10 dark:bg-white/5",
          TONE[tone].text,
          className,
        )}
      >
        <span className="relative flex size-2">
          {tone === "ok" ? (
            <motion.span
              aria-hidden
              className="absolute inset-0 rounded-full bg-emerald-400"
              animate={{ scale: [1, 2.4], opacity: [0.7, 0] }}
              transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
            />
          ) : null}
          <span className={cn("relative size-2 rounded-full", TONE[tone].dot)} />
        </span>
        {label}
      </button>
    </HoverCard>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <span className="flex justify-between gap-4">
      <span className="text-zinc-500">{k}</span>
      <span className="font-mono text-zinc-800 dark:text-zinc-200">{v}</span>
    </span>
  );
}
