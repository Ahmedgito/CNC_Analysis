"use client";

/**
 * Accessible tabs with a sliding indicator (roving tabindex, arrow keys, Home/End).
 * In the style of 21st.dev educalvolpz/animated-tabs.
 */

import { motion } from "motion/react";
import { type ReactNode, useId, useRef } from "react";
import { cn } from "@/lib/cn";

export type TabItem<T extends string> = {
  id: T;
  label: ReactNode;
  /** Accessible name when `label` is not plain text. */
  ariaLabel?: string;
  icon?: ReactNode;
  meta?: ReactNode;
};

export function AnimatedTabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  variant = "pill",
  className,
  panelIdFor,
}: {
  tabs: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  /** Accessible name of the tab list. */
  label: string;
  variant?: "pill" | "segment" | "underline";
  className?: string;
  /** id of the panel each tab controls, for aria-controls. */
  panelIdFor?: (id: T) => string;
}) {
  const layoutId = useId();
  const refs = useRef(new Map<T, HTMLButtonElement>());

  function move(from: number, delta: number) {
    const next = tabs[(from + delta + tabs.length) % tabs.length];
    onChange(next.id);
    refs.current.get(next.id)?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn(
        "relative flex gap-1",
        variant === "segment" && "rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900",
        variant === "underline" && "border-b border-zinc-200 dark:border-zinc-800",
        className,
      )}
    >
      {tabs.map((tab, i) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              if (el) refs.current.set(tab.id, el);
              else refs.current.delete(tab.id);
            }}
            type="button"
            role="tab"
            id={`${layoutId}-tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={panelIdFor?.(tab.id)}
            aria-label={tab.ariaLabel}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                e.preventDefault();
                move(i, 1);
              } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                e.preventDefault();
                move(i, -1);
              } else if (e.key === "Home") {
                e.preventDefault();
                move(0, 0);
              } else if (e.key === "End") {
                e.preventDefault();
                move(tabs.length - 1, 0);
              }
            }}
            className={cn(
              "relative inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60",
              variant === "segment" && "flex-1 justify-center",
              variant === "underline" && "rounded-none pb-2.5",
              selected
                ? variant === "underline"
                  ? "text-zinc-900 dark:text-white"
                  : "text-zinc-900 dark:text-white"
                : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200",
            )}
          >
            {selected ? (
              <motion.span
                layoutId={layoutId}
                aria-hidden
                className={cn(
                  "absolute",
                  variant === "underline"
                    ? "inset-x-1 -bottom-px h-0.5 rounded-full bg-cyan-500"
                    : "inset-0 rounded-lg bg-white shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-800 dark:ring-white/10",
                )}
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            ) : null}
            <span className="relative z-1 inline-flex items-center gap-1.5">
              {tab.icon}
              <span className="font-medium">{tab.label}</span>
              {tab.meta}
            </span>
          </button>
        );
      })}
    </div>
  );
}
