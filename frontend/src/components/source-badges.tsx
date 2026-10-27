"use client";

import { Box, FileSpreadsheet, FileText } from "lucide-react";
import { motion } from "motion/react";
import type { SourceStatus } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

export const SOURCES = [
  { key: "excel", label: "Excel", Icon: FileSpreadsheet },
  { key: "pdf", label: "PDF", Icon: FileText },
  { key: "iges", label: "IGES", Icon: Box },
] as const;

/** Excel / PDF / IGES availability. Available sources pulse softly; missing ones are dashed. */
export function SourceBadges({
  sources,
  className,
  compact = false,
}: {
  sources: Record<string, SourceStatus>;
  className?: string;
  /** Icon-only pills (names stay available to screen readers and on hover). */
  compact?: boolean;
}) {
  return (
    <ul className={cn("flex flex-wrap gap-1.5", className)} aria-label="Sources">
      {SOURCES.map(({ key, label, Icon }) => {
        const s = sources[key];
        const ok = Boolean(s?.available);
        const title = ok
          ? `${label}: ${s?.files.join(", ")}`
          : `${label}: not available${s?.note ? ` (${s.note})` : ""}`;
        return (
          <li
            key={key}
            title={title}
            className={cn(
              "relative inline-flex items-center gap-1 rounded-full border text-xs font-medium",
              compact ? "size-6 justify-center" : "px-2 py-0.5",
              ok
                ? "border-emerald-300/70 bg-emerald-50 text-emerald-700 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-300"
                : "border-dashed border-zinc-300 text-zinc-400 dark:border-white/15 dark:text-zinc-500",
            )}
          >
            {ok ? (
              <motion.span
                aria-hidden
                className="absolute inset-0 rounded-full ring-1 ring-emerald-400/60"
                animate={{ opacity: [0.7, 0], scale: [1, 1.35] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: "easeOut" }}
              />
            ) : null}
            <Icon className="size-3.5" aria-hidden />
            <span className={compact ? "sr-only" : undefined}>{label}</span>
            <span className="sr-only">{ok ? "available" : "not available"}</span>
          </li>
        );
      })}
    </ul>
  );
}
