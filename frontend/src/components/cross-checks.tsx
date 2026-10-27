"use client";

import {
  ArrowLeftRight,
  CheckCircle2,
  CircleSlash,
  FileSpreadsheet,
  FileText,
  Repeat,
  Scale,
  XCircle,
} from "lucide-react";
import { motion } from "motion/react";
import type { CrossCheck, Verdict } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

export const VERDICT: Record<Verdict, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  agree: {
    label: "Agree",
    className:
      "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/25",
    Icon: CheckCircle2,
  },
  agree_after_conversion: {
    label: "Agree after unit conversion",
    className:
      "bg-teal-50 text-teal-800 ring-teal-200 dark:bg-teal-400/10 dark:text-teal-300 dark:ring-teal-400/25",
    Icon: Repeat,
  },
  equivalent_by_convention: {
    label: "Equivalent by convention",
    className:
      "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-400/10 dark:text-sky-300 dark:ring-sky-400/25",
    Icon: Scale,
  },
  disagree: {
    label: "Disagree",
    className:
      "bg-rose-50 text-rose-800 ring-rose-300 dark:bg-rose-400/10 dark:text-rose-300 dark:ring-rose-400/30",
    Icon: XCircle,
  },
  excel_only: {
    label: "Spreadsheet only",
    className:
      "bg-zinc-100 text-zinc-700 ring-zinc-200 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10",
    Icon: FileSpreadsheet,
  },
  pdf_only: {
    label: "Drawing only",
    className:
      "bg-zinc-100 text-zinc-700 ring-zinc-200 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10",
    Icon: FileText,
  },
  not_comparable: {
    label: "Not comparable",
    className:
      "bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25",
    Icon: CircleSlash,
  },
};

/** Disagreements first, then the checks that need a reader's judgement, then agreements. */
const ORDER: Verdict[] = [
  "disagree",
  "not_comparable",
  "agree_after_conversion",
  "equivalent_by_convention",
  "agree",
  "excel_only",
  "pdf_only",
];

export function sortChecks(checks: CrossCheck[]) {
  return [...checks].sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));
}

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  const { label, className, Icon } = VERDICT[verdict];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1",
        className,
      )}
    >
      <Icon className="size-3" aria-hidden />
      {label}
    </span>
  );
}

function Side({
  Icon,
  label,
  value,
  ids,
  selected,
  onSelect,
}: {
  Icon: typeof FileText;
  label: string;
  value?: string | null;
  ids: string[];
  selected?: string | null;
  onSelect?: (factId: string) => void;
}) {
  const id = ids[0];
  const active = id !== undefined && ids.includes(selected ?? "");
  const body = (
    <>
      <span className="flex items-center gap-1 text-[10px] font-medium tracking-[0.14em] text-zinc-500 uppercase">
        <Icon className="size-3" aria-hidden /> {label}
      </span>
      <span className={cn("text-sm break-words", value ? "font-medium" : "text-zinc-400 italic")}>
        {value ?? "not stated"}
      </span>
    </>
  );
  const box = cn(
    "flex min-w-0 flex-1 flex-col gap-0.5 rounded-lg border px-2.5 py-1.5 text-left transition-colors",
    active
      ? "border-amber-400 bg-amber-50 dark:bg-amber-400/10"
      : "border-zinc-200 bg-zinc-50/60 dark:border-white/10 dark:bg-white/[0.02]",
  );
  if (!id || !onSelect) return <div className={box}>{body}</div>;
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      title={`Locate ${id}`}
      className={cn(
        box,
        "hover:border-cyan-400/60 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none",
      )}
    >
      {body}
    </button>
  );
}

export function CrossCheckList({
  checks,
  selected,
  onSelect,
  compact = false,
}: {
  checks: CrossCheck[];
  selected?: string | null;
  onSelect?: (factId: string) => void;
  /** Hide the explanation line (answer cards show it as a tooltip instead). */
  compact?: boolean;
}) {
  return (
    <motion.ul
      className="flex flex-col gap-2"
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.05 } } }}
    >
      {sortChecks(checks).map((c) => (
        <motion.li
          key={c.field}
          variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0 } }}
          title={compact ? c.detail : undefined}
          className={cn(
            "flex flex-col gap-2 rounded-xl border p-2.5",
            c.verdict === "disagree"
              ? "border-rose-200 bg-rose-50/40 dark:border-rose-400/20 dark:bg-rose-400/[0.04]"
              : "border-zinc-200 dark:border-white/10",
          )}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">{c.label}</span>
            <VerdictPill verdict={c.verdict} />
          </div>
          <div className="flex items-stretch gap-1.5">
            <Side
              Icon={FileSpreadsheet}
              label="Spreadsheet"
              value={c.excel_value}
              ids={c.excel}
              selected={selected}
              onSelect={onSelect}
            />
            <ArrowLeftRight className="size-3.5 shrink-0 self-center text-zinc-400" aria-hidden />
            <Side
              Icon={FileText}
              label="Drawing"
              value={c.pdf_value}
              ids={c.pdf}
              selected={selected}
              onSelect={onSelect}
            />
          </div>
          {compact ? null : <p className="text-xs text-zinc-600 dark:text-zinc-400">{c.detail}</p>}
        </motion.li>
      ))}
    </motion.ul>
  );
}
