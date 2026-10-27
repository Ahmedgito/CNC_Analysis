"use client";

/**
 * Shimmering status text for work in progress.
 * In the style of 21st.dev serafimcloud/text-shimmer (Agent Elements).
 */

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function TextShimmer({
  children,
  className,
  duration = 1.8,
}: {
  children: ReactNode;
  className?: string;
  duration?: number;
}) {
  return (
    <motion.span
      className={cn(
        "inline-block bg-[linear-gradient(90deg,var(--shimmer-base)_0%,var(--shimmer-base)_40%,var(--shimmer-hi)_50%,var(--shimmer-base)_60%,var(--shimmer-base)_100%)] bg-size-[250%_100%] bg-clip-text text-transparent",
        "[--shimmer-base:var(--color-zinc-500)] [--shimmer-hi:var(--color-zinc-900)]",
        "dark:[--shimmer-base:var(--color-zinc-500)] dark:[--shimmer-hi:var(--color-white)]",
        className,
      )}
      initial={{ backgroundPosition: "100% 0" }}
      animate={{ backgroundPosition: "-150% 0" }}
      transition={{ duration, ease: "linear", repeat: Infinity }}
    >
      {children}
    </motion.span>
  );
}
