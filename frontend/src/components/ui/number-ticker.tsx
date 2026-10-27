"use client";

/**
 * Number ticker: counts up to `value` when scrolled into view.
 * In the style of 21st.dev danielpetho/basic-number-ticker. Screen readers get the final value.
 */

import { animate, useInView, useReducedMotionConfig } from "motion/react";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

function formatNumber(n: number, decimals: number, suffix: string) {
  return `${n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`;
}

export function NumberTicker({
  value,
  className,
  decimals = 0,
  suffix = "",
  duration = 1.4,
}: {
  value: number;
  className?: string;
  decimals?: number;
  suffix?: string;
  duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });
  const reduce = useReducedMotionConfig();

  useEffect(() => {
    const el = ref.current;
    if (!el || !inView) return;
    if (reduce) {
      el.textContent = formatNumber(value, decimals, suffix);
      return;
    }
    const controls = animate(0, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (n) => {
        el.textContent = formatNumber(n, decimals, suffix);
      },
    });
    return () => controls.stop();
  }, [inView, value, reduce, duration, decimals, suffix]);

  return (
    <span className={cn("tabular-nums", className)}>
      <span ref={ref} aria-hidden>
        {formatNumber(0, decimals, suffix)}
      </span>
      <span className="sr-only">{formatNumber(value, decimals, suffix)}</span>
    </span>
  );
}
