"use client";

/** Word-by-word blur-in reveal for headlines (text generate effect family on 21st.dev). */

import { motion } from "motion/react";
import { cn } from "@/lib/cn";

export function BlurText({
  text,
  className,
  wordClassName,
  delay = 0,
  stagger = 0.07,
}: {
  text: string;
  className?: string;
  wordClassName?: string;
  delay?: number;
  stagger?: number;
}) {
  const words = text.split(" ");
  return (
    <span className={className}>
      <span className="sr-only">{text}</span>
      <span aria-hidden>
        {words.map((word, i) => (
          <motion.span
            key={`${word}-${i}`}
            className={cn("inline-block will-change-[filter,transform]", wordClassName)}
            initial={{ opacity: 0, filter: "blur(12px)", y: 14 }}
            animate={{ opacity: 1, filter: "blur(0px)", y: 0 }}
            transition={{ duration: 0.7, delay: delay + i * stagger, ease: [0.16, 1, 0.3, 1] }}
          >
            {word}
            {i < words.length - 1 ? " " : null}
          </motion.span>
        ))}
      </span>
    </span>
  );
}
