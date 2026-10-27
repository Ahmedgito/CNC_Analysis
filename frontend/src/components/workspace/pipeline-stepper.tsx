"use client";

/**
 * Live answer pipeline, driven by the server's SSE stage events.
 * In the style of 21st.dev arunjdass/ai-agent-processing-states, with shimmer text for the
 * current step.
 */

import { Check, Loader2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import type { StageEvent } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { TextShimmer } from "../ui/text-shimmer";

type Stage = StageEvent["stage"];

const LABEL: Record<Stage, string> = {
  validating: "Checking the question",
  loading_record: "Loading the part record",
  reading_scan: "Reading the scanned drawing with the vision model",
  asking_llm: "Asking the model",
  verifying: "Verifying every citation against the file",
  computing: "Computing from the cited cells",
  saving: "Saving the answer",
};
const BASE: Stage[] = ["validating", "loading_record", "asking_llm", "verifying", "saving"];

function useElapsed() {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(id);
  }, []);
  return ((now - start) / 1000).toFixed(1);
}

export function PipelineStepper({ events }: { events: StageEvent[] }) {
  const elapsed = useElapsed();
  const seen = events.map((e) => e.stage);
  // Optional steps (reading a scan, computing) appear once the server reports them.
  const order: Stage[] = BASE.flatMap((s): Stage[] => {
    if (s === "loading_record" && seen.includes("reading_scan")) return [s, "reading_scan"];
    if (s === "verifying" && seen.includes("computing")) return [s, "computing"];
    return [s];
  });
  const current = seen.at(-1);
  const currentIndex = current ? order.indexOf(current) : -1;
  const detail = (stage: Stage) => events.findLast((e) => e.stage === stage)?.detail;

  return (
    <div className="flex flex-col gap-3" role="status" aria-label="Answer progress">
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span className="inline-flex items-center gap-1.5 font-medium">
          <Loader2 className="size-3.5 animate-spin text-cyan-500" aria-hidden />
          Working on it
        </span>
        <span className="font-mono tabular-nums">{elapsed}s</span>
      </div>
      <ol className="relative flex flex-col gap-2.5 pl-1">
        <span aria-hidden className="absolute top-2 bottom-2 left-[11px] w-px bg-zinc-200 dark:bg-white/10" />
        <motion.span
          aria-hidden
          className="absolute top-2 bottom-2 left-[11px] w-px origin-top bg-gradient-to-b from-emerald-400 to-cyan-400"
          initial={{ scaleY: 0 }}
          animate={{ scaleY: Math.max(0, currentIndex) / (order.length - 1) }}
          transition={{ type: "spring", stiffness: 120, damping: 20 }}
        />
        <AnimatePresence initial={false}>
          {order.map((stage, i) => {
            const state = i < currentIndex ? "done" : i === currentIndex ? "current" : "pending";
            const extra = stage === "asking_llm" || stage === "reading_scan" ? detail(stage) : null;
            return (
              <motion.li
                key={stage}
                layout
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                className="relative flex items-center gap-3 text-sm"
              >
                <span
                  className={cn(
                    "relative z-1 grid size-[22px] shrink-0 place-items-center rounded-full border transition-colors duration-300",
                    state === "done" && "border-emerald-500 bg-emerald-500 text-white",
                    state === "current" && "border-cyan-400 bg-white dark:bg-zinc-900",
                    state === "pending" && "border-zinc-300 bg-white dark:border-white/15 dark:bg-zinc-900",
                  )}
                >
                  {state === "done" ? (
                    <motion.span
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 20 }}
                    >
                      <Check className="size-3" aria-hidden />
                    </motion.span>
                  ) : state === "current" ? (
                    <motion.span
                      className="size-2 rounded-full bg-cyan-500"
                      animate={{ scale: [1, 1.5, 1], opacity: [1, 0.6, 1] }}
                      transition={{ duration: 1, repeat: Infinity }}
                    />
                  ) : null}
                </span>
                {state === "current" ? (
                  <TextShimmer className="font-medium">
                    {LABEL[stage]}
                    {extra ? ` (${extra})` : ""}…
                  </TextShimmer>
                ) : (
                  <span
                    className={
                      state === "done"
                        ? "text-zinc-700 dark:text-zinc-300"
                        : "text-zinc-400 dark:text-zinc-600"
                    }
                  >
                    {LABEL[stage]}
                    {extra ? <span className="font-mono text-xs text-zinc-500"> · {extra}</span> : null}
                  </span>
                )}
                <span className="sr-only">
                  {state === "done" ? ", done" : state === "current" ? ", in progress" : ", pending"}
                </span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
    </div>
  );
}
