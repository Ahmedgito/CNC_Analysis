"use client";

import { motion } from "motion/react";

/** Ø mark inside a slowly turning dashed ring, like a tool path around a bore. */
export function Logo() {
  return (
    <span className="relative grid size-8 place-items-center" aria-hidden>
      <motion.svg
        viewBox="0 0 32 32"
        className="absolute inset-0 text-cyan-500"
        animate={{ rotate: 360 }}
        transition={{ duration: 18, ease: "linear", repeat: Infinity }}
      >
        <circle
          cx="16"
          cy="16"
          r="14.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.25"
          strokeDasharray="3 3.4"
        />
      </motion.svg>
      <span className="grid size-6 place-items-center rounded-full bg-zinc-900 font-mono text-[11px] font-bold text-white dark:bg-white dark:text-zinc-900">
        Ø
      </span>
    </span>
  );
}
