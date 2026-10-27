"use client";

/**
 * Spotlight card: a soft light follows the pointer, and lights the card edge where it passes.
 * In the style of 21st.dev ibelick/spotlight and manuarora700/card-spotlight.
 */

import { motion, useMotionTemplate, useMotionValue, useSpring } from "motion/react";
import { type ComponentProps, useState } from "react";
import { cn } from "@/lib/cn";

type SpotlightCardProps = ComponentProps<"div"> & {
  /** Classes for the inner surface (background, padding). */
  surfaceClassName?: string;
  /** Spotlight radius in px. */
  radius?: number;
};

export function SpotlightCard({
  children,
  className,
  surfaceClassName,
  radius = 320,
  onPointerMove,
  onPointerEnter,
  onPointerLeave,
  ...props
}: SpotlightCardProps) {
  const x = useMotionValue(-1000);
  const y = useMotionValue(-1000);
  const sx = useSpring(x, { stiffness: 500, damping: 50 });
  const sy = useSpring(y, { stiffness: 500, damping: 50 });
  const [hovered, setHovered] = useState(false);

  const edge = useMotionTemplate`radial-gradient(${radius * 0.6}px circle at ${sx}px ${sy}px, rgb(34 211 238 / 0.65), transparent 70%)`;
  const glow = useMotionTemplate`radial-gradient(${radius}px circle at ${sx}px ${sy}px, rgb(34 211 238 / 0.10), transparent 75%)`;

  return (
    <div
      className={cn("group/spot relative rounded-2xl bg-zinc-200/80 p-px dark:bg-white/10", className)}
      onPointerMove={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        x.set(e.clientX - rect.left);
        y.set(e.clientY - rect.top);
        onPointerMove?.(e);
      }}
      onPointerEnter={(e) => {
        setHovered(true);
        onPointerEnter?.(e);
      }}
      onPointerLeave={(e) => {
        setHovered(false);
        onPointerLeave?.(e);
      }}
      {...props}
    >
      {/* Lit edge: the 1px padding of this wrapper shows the gradient as a border. */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-[inherit]"
        style={{ background: edge }}
        animate={{ opacity: hovered ? 1 : 0 }}
        transition={{ duration: 0.3 }}
      />
      <div
        className={cn(
          "relative h-full overflow-hidden rounded-[calc(1rem-1px)] bg-white dark:bg-zinc-900",
          surfaceClassName,
        )}
      >
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: glow }}
          animate={{ opacity: hovered ? 1 : 0 }}
          transition={{ duration: 0.3 }}
        />
        <div className="relative h-full">{children}</div>
      </div>
    </div>
  );
}
