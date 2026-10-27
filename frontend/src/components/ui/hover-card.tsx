"use client";

/**
 * Hover / focus preview card anchored above its trigger (animated tooltip family on 21st.dev).
 * The trigger keeps its own accessible name; the card is linked with aria-describedby.
 */

import { AnimatePresence, motion } from "motion/react";
import { type ReactElement, type ReactNode, cloneElement, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";

export function HoverCard({
  children,
  content,
  className,
  side = "top",
}: {
  children: ReactElement<{ "aria-describedby"?: string }>;
  content: ReactNode;
  className?: string;
  side?: "top" | "bottom";
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const timer = useRef<number | null>(null);
  const show = () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), 120);
  };
  const hide = () => {
    if (timer.current) window.clearTimeout(timer.current);
    setOpen(false);
  };

  return (
    <span
      className="relative inline-flex max-w-full"
      onPointerEnter={show}
      onPointerLeave={hide}
      onFocus={show}
      onBlur={hide}
      onKeyDown={(e) => e.key === "Escape" && hide()}
    >
      {cloneElement(children, { "aria-describedby": id })}
      {/* Always present, so assistive tech reads the description; the animated card is visual. */}
      <span id={id} hidden>
        {content}
      </span>
      <AnimatePresence>
        {open ? (
          <motion.span
            aria-hidden
            initial={{ opacity: 0, y: side === "top" ? 6 : -6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: side === "top" ? 4 : -4, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 500, damping: 32 }}
            className={cn(
              "pointer-events-none absolute left-0 z-30 w-72 max-w-[80vw] origin-bottom-left rounded-xl border border-zinc-200 bg-white/95 p-3 text-left text-xs shadow-xl backdrop-blur dark:border-white/10 dark:bg-zinc-900/95",
              side === "top" ? "bottom-full mb-2" : "top-full mt-2 origin-top-left",
              className,
            )}
          >
            {content}
          </motion.span>
        ) : null}
      </AnimatePresence>
    </span>
  );
}
