"use client";

/**
 * Infinite marquee. Content is rendered twice and shifted by half the track; it pauses on hover
 * and focus, and stands still for reduced motion.
 */

import {
  motion,
  useAnimationFrame,
  useMotionValue,
  useReducedMotionConfig,
  useTransform,
} from "motion/react";
import { type ReactNode, useRef } from "react";
import { cn } from "@/lib/cn";

export function Marquee({
  children,
  className,
  reverse = false,
  /** Percent of one copy's width per second. */
  speed = 2.2,
  label,
}: {
  children: ReactNode;
  className?: string;
  reverse?: boolean;
  speed?: number;
  label: string;
}) {
  const reduce = useReducedMotionConfig();
  const paused = useRef(false);
  const pct = useMotionValue(reverse ? -50 : 0);
  const x = useTransform(pct, (v) => `${v}%`);

  useAnimationFrame((_, delta) => {
    if (reduce || paused.current) return;
    const step = (speed / 2) * (delta / 1000) * (reverse ? 1 : -1);
    let next = pct.get() + step;
    if (next <= -50) next += 50;
    if (next >= 0) next -= 50;
    pct.set(next);
  });

  return (
    <section
      aria-label={label}
      className={cn(
        "relative overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)]",
        className,
      )}
      onPointerEnter={() => (paused.current = true)}
      onPointerLeave={() => (paused.current = false)}
      onFocus={() => (paused.current = true)}
      onBlur={() => (paused.current = false)}
    >
      <motion.div className="flex w-max" style={{ x }}>
        <div className="flex shrink-0 gap-3 pr-3">{children}</div>
        <div className="flex shrink-0 gap-3 pr-3" aria-hidden>
          {children}
        </div>
      </motion.div>
    </section>
  );
}
