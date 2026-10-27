"use client";

import { CirclePause, MonitorCog, Sparkles } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { type MotionPref, setMotionPref, useMotionPref, useOsReducedMotion } from "@/lib/motion-pref";
import { useMounted } from "@/lib/theme";
import { cn } from "@/lib/cn";

const NEXT: Record<MotionPref, MotionPref> = { system: "full", full: "reduced", reduced: "system" };
const ICON = { system: MonitorCog, full: Sparkles, reduced: CirclePause } as const;

/** Cycles the app's motion setting: follow the system, full animation, or reduced. */
export function MotionToggle({ className }: { className?: string }) {
  const mounted = useMounted();
  const pref = useMotionPref();
  const osReduced = useOsReducedMotion();
  const Icon = ICON[pref];
  const describe = (p: MotionPref) =>
    p === "system"
      ? `Motion follows the system${osReduced ? " (reduced)" : ""}`
      : p === "full"
        ? "Full motion"
        : "Reduced motion";

  return (
    <button
      type="button"
      onClick={() => setMotionPref(NEXT[pref])}
      aria-label={mounted ? `${describe(pref)}. Switch to ${describe(NEXT[pref]).toLowerCase()}` : "Motion"}
      title={mounted ? describe(pref) : undefined}
      className={cn(
        "relative grid size-9 place-items-center overflow-hidden rounded-full text-zinc-600 transition hover:bg-zinc-900/5 hover:text-zinc-900 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white",
        pref === "full" && "text-cyan-600 dark:text-cyan-300",
        className,
      )}
    >
      {mounted ? (
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={pref}
            initial={{ scale: 0.4, opacity: 0, rotate: -90 }}
            animate={{ scale: 1, opacity: 1, rotate: 0 }}
            exit={{ scale: 0.4, opacity: 0, rotate: 90 }}
            transition={{ type: "spring", stiffness: 420, damping: 24 }}
          >
            <Icon className="size-4.5" aria-hidden />
          </motion.span>
        </AnimatePresence>
      ) : (
        <span className="size-4.5" />
      )}
      {mounted && pref === "system" && osReduced ? (
        <span aria-hidden className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-amber-400" />
      ) : null}
    </button>
  );
}
