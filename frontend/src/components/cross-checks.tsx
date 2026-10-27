"use client";

import {
  Box,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  FileSpreadsheet,
  FileText,
  Gauge,
  Layers,
  Repeat,
  Scale,
  XCircle,
} from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import type { CheckSide, CrossCheck, SourceKind, Verdict } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { useFactSelection } from "@/lib/selection";

const neutral =
  "bg-zinc-100 text-zinc-700 ring-zinc-200 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10";

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
  consistent: {
    label: "Fits the stock",
    className:
      "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/25",
    Icon: Layers,
  },
  within_tolerance: {
    label: "Within tolerance, check",
    className:
      "bg-amber-50 text-amber-900 ring-amber-300 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/30",
    Icon: Gauge,
  },
  not_modelled: {
    label: "Not modelled",
    className: neutral,
    Icon: CircleDashed,
  },
  disagree: {
    label: "Disagree",
    className:
      "bg-rose-50 text-rose-800 ring-rose-300 dark:bg-rose-400/10 dark:text-rose-300 dark:ring-rose-400/30",
    Icon: XCircle,
  },
  excel_only: { label: "Spreadsheet only", className: neutral, Icon: FileSpreadsheet },
  pdf_only: { label: "Drawing only", className: neutral, Icon: FileText },
  iges_only: { label: "Model only", className: neutral, Icon: Box },
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
  "within_tolerance",
  "not_comparable",
  "not_modelled",
  "agree_after_conversion",
  "equivalent_by_convention",
  "consistent",
  "agree",
  "excel_only",
  "pdf_only",
  "iges_only",
];
const NEEDS_LOOK: Verdict[] = ["within_tolerance", "not_comparable", "not_modelled"];

export function sortChecks(checks: CrossCheck[]) {
  return [...checks].sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));
}

export const SOURCE_META: Record<SourceKind, { label: string; short: string; Icon: typeof FileText }> = {
  excel: { label: "Spreadsheet", short: "Sheet", Icon: FileSpreadsheet },
  pdf: { label: "Drawing", short: "Drawing", Icon: FileText },
  iges: { label: "3D model", short: "Model", Icon: Box },
};
const PAIRS = [
  ["excel~pdf", "excel", "pdf"],
  ["pdf~iges", "pdf", "iges"],
  ["excel~iges", "excel", "iges"],
] as const;

export function VerdictPill({ verdict, small = false }: { verdict: Verdict; small?: boolean }) {
  const { label, className, Icon } = VERDICT[verdict];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full font-medium ring-1",
        small ? "px-1.5 py-px text-[10px]" : "px-2 py-0.5 text-[11px]",
        className,
      )}
    >
      <Icon className={small ? "size-2.5" : "size-3"} aria-hidden />
      {label}
    </span>
  );
}

/** Sides from the three-way contract, or built from the Level 2 fields for older records. */
function sidesOf(c: CrossCheck): CheckSide[] {
  if (c.sides.length) return c.sides;
  const out: CheckSide[] = [];
  if (c.excel.length || c.excel_value) out.push({ source: "excel", facts: c.excel, value: c.excel_value });
  if (c.pdf.length || c.pdf_value) out.push({ source: "pdf", facts: c.pdf, value: c.pdf_value });
  return out;
}

function Side({
  source,
  side,
  odd,
  dissent,
  onSelect,
}: {
  source: SourceKind;
  side?: CheckSide;
  odd: boolean;
  dissent: string[];
  onSelect?: (factId: string) => void;
}) {
  const { primary, isRelated } = useFactSelection();
  const { label, Icon } = SOURCE_META[source];
  const ids = side?.facts ?? [];
  const first = ids[0];
  const active = ids.some((i) => i === primary);
  const related = !active && ids.some((i) => isRelated(i));
  const dissenting = odd || ids.some((i) => dissent.includes(i));
  const value = side?.value;
  const body = (
    <>
      <span className="flex items-center gap-1 text-[10px] font-medium tracking-[0.14em] text-zinc-500 uppercase">
        <Icon className="size-3" aria-hidden /> {label}
        {dissenting ? (
          <span className="ml-auto rounded bg-rose-500 px-1 text-[9px] font-semibold tracking-normal text-white normal-case">
            {odd ? "odd one out" : "differs"}
          </span>
        ) : null}
      </span>
      <span className={cn("text-sm break-words", value ? "font-medium" : "text-zinc-400 italic")}>
        {value ?? (side?.note ? "does not state" : "not stated")}
      </span>
      {side?.normalised && side.normalised !== value ? (
        <span className="font-mono text-[11px] text-zinc-500">= {side.normalised}</span>
      ) : null}
      {side?.note ? <span className="text-[11px] text-zinc-500">{side.note}</span> : null}
    </>
  );
  const box = cn(
    "flex min-w-0 flex-1 flex-col gap-0.5 rounded-lg border px-2.5 py-1.5 text-left transition-colors",
    active
      ? "border-amber-400 bg-amber-50 dark:bg-amber-400/10"
      : related
        ? "border-amber-300/70 border-dashed bg-amber-50/40 dark:bg-amber-400/5"
        : dissenting
          ? "border-rose-300 bg-rose-50/60 dark:border-rose-400/30 dark:bg-rose-400/[0.06]"
          : "border-zinc-200 bg-zinc-50/60 dark:border-white/10 dark:bg-white/[0.02]",
  );
  if (!first || !onSelect) return <div className={box}>{body}</div>;
  return (
    <button
      type="button"
      onClick={() => onSelect(first)}
      title={`Locate ${first}`}
      className={cn(
        box,
        "hover:border-cyan-400/60 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none",
      )}
    >
      {body}
    </button>
  );
}

function CheckItem({
  check: c,
  onSelect,
  compact,
}: {
  check: CrossCheck;
  onSelect?: (factId: string) => void;
  compact: boolean;
}) {
  const sides = sidesOf(c);
  const sources = (["excel", "pdf", "iges"] as const).filter((s) => sides.some((x) => x.source === s));
  const pairs = PAIRS.filter(([k]) => c.pairs[k]);
  return (
    <motion.li
      variants={{ hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0 } }}
      title={compact ? c.detail : undefined}
      className={cn(
        "flex flex-col gap-2 rounded-xl border p-2.5",
        c.verdict === "disagree"
          ? "border-rose-200 bg-rose-50/40 dark:border-rose-400/20 dark:bg-rose-400/[0.04]"
          : c.verdict === "within_tolerance"
            ? "border-amber-200 bg-amber-50/30 dark:border-amber-400/20 dark:bg-amber-400/[0.03]"
            : "border-zinc-200 dark:border-white/10",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold">{c.label}</span>
        <VerdictPill verdict={c.verdict} />
      </div>
      <div className={cn("grid gap-1.5", sources.length >= 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}>
        {sources.map((s) => (
          <Side
            key={s}
            source={s}
            side={sides.find((x) => x.source === s)}
            odd={c.odd_one_out === s}
            dissent={c.dissent}
            onSelect={onSelect}
          />
        ))}
      </div>
      {pairs.length > 1 ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="Pairwise verdicts">
          {pairs.map(([k, a, b]) => (
            <li key={k} className="inline-flex items-center gap-1 text-[10px] text-zinc-500">
              {SOURCE_META[a].short} ↔ {SOURCE_META[b].short}
              <VerdictPill verdict={c.pairs[k] as Verdict} small />
            </li>
          ))}
        </ul>
      ) : null}
      {compact ? null : <p className="text-xs text-zinc-600 dark:text-zinc-400">{c.detail}</p>}
    </motion.li>
  );
}

type Filter = "all" | "disagree" | "look" | "agree";

export function CrossCheckList({
  checks,
  onSelect,
  compact = false,
  filterable = false,
}: {
  checks: CrossCheck[];
  onSelect?: (factId: string) => void;
  /** Hide the explanation line (answer cards show it as a tooltip instead). */
  compact?: boolean;
  /** Show the Disagree / Needs a look / Agree filter (the record's cross-check tab). */
  filterable?: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const counts = {
    all: checks.length,
    disagree: checks.filter((c) => c.verdict === "disagree").length,
    look: checks.filter((c) => NEEDS_LOOK.includes(c.verdict)).length,
    agree: checks.filter((c) => c.verdict !== "disagree" && !NEEDS_LOOK.includes(c.verdict)).length,
  };
  const shown = checks.filter((c) =>
    filter === "all"
      ? true
      : filter === "disagree"
        ? c.verdict === "disagree"
        : filter === "look"
          ? NEEDS_LOOK.includes(c.verdict)
          : c.verdict !== "disagree" && !NEEDS_LOOK.includes(c.verdict),
  );
  return (
    <div className="flex flex-col gap-2">
      {filterable ? (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter cross-checks">
          {(
            [
              ["all", "All"],
              ["disagree", "Disagree"],
              ["look", "Needs a look"],
              ["agree", "Agree"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-pressed={filter === id}
              disabled={counts[id] === 0 && id !== "all"}
              onClick={() => setFilter(id)}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs transition-colors disabled:opacity-40",
                filter === id
                  ? "border-zinc-900 bg-zinc-900 text-white dark:border-white dark:bg-white dark:text-zinc-900"
                  : "border-zinc-200 text-zinc-600 hover:border-zinc-400 dark:border-white/10 dark:text-zinc-400",
              )}
            >
              {label} <span className="font-mono opacity-70">{counts[id]}</span>
            </button>
          ))}
        </div>
      ) : null}
      <motion.ul
        key={filter}
        className="flex flex-col gap-2"
        initial="hidden"
        animate="show"
        variants={{ show: { transition: { staggerChildren: 0.05 } } }}
      >
        {sortChecks(shown).map((c) => (
          <CheckItem key={c.field} check={c} onSelect={onSelect} compact={compact} />
        ))}
      </motion.ul>
    </div>
  );
}
