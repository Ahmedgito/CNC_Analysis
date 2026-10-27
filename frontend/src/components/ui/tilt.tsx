"use client";

/** 3D tilt toward the pointer. Disabled for reduced motion and for touch input. */

import { motion, useMotionValue, useReducedMotionConfig, useSpring, useTransform } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Tilt({
  children,
  className,
  max = 7,
}: {
  children: ReactNode;
  className?: string;
  /** Maximum rotation in degrees. */
  max?: number;
}) {
  const reduce = useReducedMotionConfig();
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const spring = { stiffness: 260, damping: 22 };
  const rotateY = useSpring(useTransform(px, [0, 1], [-max, max]), spring);
  const rotateX = useSpring(useTransform(py, [0, 1], [max, -max]), spring);

  return (
    <div className={cn("perspective-[1000px]", className)}>
      <motion.div
        className="h-full transform-3d"
        style={reduce ? undefined : { rotateX, rotateY }}
        whileHover={reduce ? undefined : { scale: 1.015 }}
        transition={{ type: "spring", stiffness: 300, damping: 24 }}
        onPointerMove={(e) => {
          if (reduce || e.pointerType !== "mouse") return;
          const rect = e.currentTarget.getBoundingClientRect();
          px.set((e.clientX - rect.left) / rect.width);
          py.set((e.clientY - rect.top) / rect.height);
        }}
        onPointerLeave={() => {
          px.set(0.5);
          py.set(0.5);
        }}
      >
        {children}
      </motion.div>
    </div>
  );
}
