"use client";

/**
 * Border beam: a light runs around the element's edge while `active`.
 * In the style of 21st.dev kevingirelli/animated-border. A rotating conic gradient behind a
 * 1px inset surface; the square rotor is oversized so wide boxes are always covered.
 */

import { AnimatePresence, motion, useReducedMotionConfig } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function BorderBeam({
  active = true,
  children,
  className,
  surfaceClassName,
  duration = 4,
}: {
  active?: boolean;
  children: ReactNode;
  /** Outer element: set the radius here (`rounded-*`); the static border colour too. */
  className?: string;
  /** Inner surface: background and padding. */
  surfaceClassName?: string;
  duration?: number;
}) {
  const reduce = useReducedMotionConfig();
  return (
    <div className={cn("relative overflow-hidden rounded-2xl bg-zinc-200 p-px dark:bg-zinc-800", className)}>
      <AnimatePresence>
        {active ? (
          <motion.div
            key="rotor"
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-1/2 aspect-square w-[max(300%,40rem)] -translate-x-1/2 -translate-y-1/2 bg-[conic-gradient(from_0deg,transparent_0deg,transparent_250deg,rgb(34_211_238/0.15)_290deg,rgb(34_211_238)_340deg,rgb(165_243_252)_352deg,transparent_360deg)]"
            initial={{ opacity: 0 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, rotate: 360 }}
            exit={{ opacity: 0 }}
            transition={{
              opacity: { duration: 0.3 },
              rotate: { duration, ease: "linear", repeat: Infinity },
            }}
          />
        ) : null}
      </AnimatePresence>
      <div className={cn("relative rounded-[calc(1rem-1px)] bg-white dark:bg-zinc-950", surfaceClassName)}>
        {children}
      </div>
    </div>
  );
}
