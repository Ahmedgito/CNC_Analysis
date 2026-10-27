"use client";

import {
  AlertTriangle,
  ArrowLeftRight,
  BookOpen,
  Box,
  Calculator,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Cpu,
  Eye,
  FileSearch,
  FileSpreadsheet,
  FileText,
  History,
  Link2,
  LocateFixed,
  ScanEye,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useId, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { AnswerStatus, AskAction, AskResult, Evidence } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { CrossCheckList } from "./cross-checks";
import { HoverCard } from "./ui/hover-card";

const STATUS: Record<AnswerStatus, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  answered: {
    label: "Answered from the files",
    className:
      "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/25",
    Icon: CheckCircle2,
  },
  computed: {
    label: "Computed from the files",
    className:
      "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-400/10 dark:text-sky-300 dark:ring-sky-400/25",
    Icon: Calculator,
  },
  not_found: {
    label: "Not in the files",
    className:
      "bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25",
    Icon: FileSearch,
  },
  clarify: {
    label: "Needs clarification",
    className:
      "bg-violet-50 text-violet-800 ring-violet-200 dark:bg-violet-400/10 dark:text-violet-300 dark:ring-violet-400/25",
    Icon: CircleHelp,
  },
  needs_consent: {
    label: "Needs your go-ahead",
    className:
      "bg-orange-50 text-orange-900 ring-orange-200 dark:bg-orange-400/10 dark:text-orange-200 dark:ring-orange-400/25",
    Icon: ScanEye,
  },
  blocked: {
    label: "Request blocked",
    className:
      "bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-400/10 dark:text-rose-300 dark:ring-rose-400/25",
    Icon: ShieldAlert,
  },
  part_not_found: {
    label: "Unknown part",
    className:
      "bg-zinc-100 text-zinc-700 ring-zinc-200 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10",
    Icon: FileSearch,
  },
  invalid_question: {
    label: "Invalid question",
    className:
      "bg-zinc-100 text-zinc-700 ring-zinc-200 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10",
    Icon: CircleHelp,
  },
  error: {
    label: "Service error",
    className:
      "bg-red-50 text-red-800 ring-red-200 dark:bg-red-400/10 dark:text-red-300 dark:ring-red-400/25",
    Icon: XCircle,
  },
};

export function StatusPill({ status }: { status: AnswerStatus }) {
  const { label, className, Icon } = STATUS[status];
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 26 }}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1",
        className,
      )}
    >
      <motion.span
        initial={{ rotate: -40, scale: 0.6 }}
        animate={{ rotate: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 400, damping: 14, delay: 0.1 }}
        className="inline-flex"
      >
        <Icon className="size-3.5" aria-hidden />
      </motion.span>
      {label}
    </motion.span>
  );
}

/** "file › sheet › C2" for a cell, "file › p1 › Dimension › Diameter" for a drawing callout,
 * "file › Model › Outer diameter" for a measured model feature. */
export function evidenceLabel(e: Evidence) {
  if (e.locator) return `${e.file} › ${e.locator}`;
  return e.source === "pdf" ? `${e.file} › p${e.page ?? 1}` : `${e.file} › ${e.sheet} › ${e.cell}`;
}

function EvidencePreview({ evidence }: { evidence: Evidence }) {
  const pdf = evidence.source === "pdf";
  const iges = evidence.source === "iges";
  return (
    <span className="flex flex-col gap-2">
      <span className="flex items-center justify-between gap-2 font-mono text-[11px] text-zinc-500">
        <span className="truncate">
          {evidence.file} › {iges ? "3D model" : pdf ? `page ${evidence.page ?? 1}` : evidence.sheet}
        </span>
        <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-zinc-700 dark:bg-white/10 dark:text-zinc-200">
          {iges
            ? (evidence.feature ?? "feature").replaceAll("_", " ")
            : pdf
              ? (evidence.region ?? "drawing").replace("_", " ")
              : evidence.cell}
        </span>
      </span>
      <span className="text-[11px] tracking-wide text-zinc-500 uppercase">{evidence.header}</span>
      <span className="text-sm font-semibold break-words text-zinc-900 dark:text-white">
        {evidence.value}
      </span>
      <span className="flex items-center gap-1 text-[11px] text-cyan-700 dark:text-cyan-300">
        <LocateFixed className="size-3" aria-hidden />
        {iges
          ? "Click to show this feature on the 3D model"
          : pdf
            ? "Click to locate this callout on the drawing"
            : "Click to locate this cell in the record"}
      </span>
      {iges && evidence.method ? (
        <span className="text-[11px] text-indigo-700 dark:text-indigo-300">
          Measured by the app from the model&apos;s geometry: {evidence.method}.
        </span>
      ) : null}
      {evidence.confidence === "vision" ? (
        <span className="text-[11px] text-violet-700 dark:text-violet-300">
          Read from a scanned image by the vision model. Check it against the drawing before relying on it.
        </span>
      ) : null}
      {evidence.stale ? (
        <span className="text-[11px] text-zinc-500">
          History: an archived or superseded value, not the current one.
        </span>
      ) : null}
      {evidence.auto_linked ? (
        <span className="text-[11px] text-zinc-500">
          Linked automatically: the answer states this value but the model did not cite it.
        </span>
      ) : null}
      {evidence.hidden ? (
        <span className="text-[11px] text-amber-700 dark:text-amber-300">From a hidden sheet or row.</span>
      ) : null}
    </span>
  );
}

export function EvidenceChip({
  evidence,
  active,
  onSelect,
}: {
  evidence: Evidence;
  active?: boolean;
  onSelect?: (factId: string) => void;
}) {
  const pdf = evidence.source === "pdf";
  const iges = evidence.source === "iges";
  const vision = evidence.confidence === "vision";
  const SourceIcon = iges ? Box : pdf ? FileText : FileSpreadsheet;
  return (
    <HoverCard content={<EvidencePreview evidence={evidence} />}>
      <motion.button
        type="button"
        onClick={() => onSelect?.(evidence.fact_id)}
        whileHover={{ y: -1 }}
        whileTap={{ scale: 0.97 }}
        className={cn(
          "inline-flex max-w-full items-center gap-1 rounded-lg border px-2 py-1 text-left font-mono text-xs transition-colors focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none",
          active
            ? "border-amber-400 bg-amber-100 text-amber-900 shadow-sm shadow-amber-500/20 dark:bg-amber-400/15 dark:text-amber-200"
            : "border-zinc-200 bg-zinc-50 text-zinc-700 hover:border-cyan-400/60 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:text-zinc-300",
          (evidence.auto_linked || vision) && "border-dashed",
          vision && !active && "border-violet-400/70",
          evidence.stale && "opacity-70",
        )}
      >
        <SourceIcon
          className={cn(
            "size-3 shrink-0",
            iges ? "text-indigo-500" : pdf ? "text-rose-500" : "text-emerald-600",
          )}
          aria-hidden
        />
        {evidence.auto_linked ? <Link2 className="size-3 shrink-0" aria-hidden /> : null}
        {vision ? (
          <Eye className="size-3 shrink-0 text-violet-500" aria-label="read by vision model" />
        ) : null}
        {evidence.stale ? <History className="size-3 shrink-0" aria-label="history" /> : null}
        <span className="truncate">{evidenceLabel(evidence)}</span>
        <span className="truncate font-sans text-zinc-500 dark:text-zinc-400">
          · {pdf || iges ? evidence.value : evidence.header}
        </span>
      </motion.button>
    </HoverCard>
  );
}

/** Chips shown before "See all". */
export const SOURCE_PREVIEW = 4;

/**
 * The first few sources, keeping at least one per source kind (spreadsheet, drawing, model) so
 * a collapsed answer still shows every file it drew on.
 */
export function previewSources(evidence: Evidence[], n = SOURCE_PREVIEW): Evidence[] {
  if (evidence.length <= n) return evidence;
  const preview = evidence.slice(0, n);
  for (const kind of ["excel", "pdf", "iges"] as const) {
    const first = evidence.find((e) => e.source === kind);
    if (!first || preview.some((e) => e.source === kind)) continue;
    // Replace the last chip of the kind that has the most chips in the preview.
    const counts = preview.reduce<Record<string, number>>(
      (m, e) => ({ ...m, [e.source]: (m[e.source] ?? 0) + 1 }),
      {},
    );
    const crowded = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0];
    const at = preview.findLastIndex((e) => e.source === crowded);
    if (at >= 0) preview[at] = first;
  }
  return evidence.filter((e) => preview.includes(e)); // keep the answer's citation order
}

const markdown = {
  p: (props: React.ComponentProps<"p">) => <p className="leading-relaxed" {...props} />,
  ul: (props: React.ComponentProps<"ul">) => (
    <ul className="list-disc space-y-1 pl-5 marker:text-cyan-500" {...props} />
  ),
  ol: (props: React.ComponentProps<"ol">) => (
    <ol className="list-decimal space-y-1 pl-5 marker:text-cyan-500" {...props} />
  ),
  strong: (props: React.ComponentProps<"strong">) => <strong className="font-semibold" {...props} />,
  code: (props: React.ComponentProps<"code">) => (
    <code className="rounded bg-zinc-100 px-1 font-mono text-[0.85em] dark:bg-white/10" {...props} />
  ),
  // Model output never becomes a live link.
  a: ({ children }: React.ComponentProps<"a">) => <span className="underline">{children}</span>,
};

const reveal = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } },
};

export function AnswerCard({
  result,
  selectedFactId,
  onSelectFact,
  onAction,
}: {
  result: AskResult;
  selectedFactId?: string | null;
  onSelectFact?: (factId: string) => void;
  /** Approve an offered action (e.g. reading a scan); undefined while another question runs. */
  onAction?: (action: AskAction) => void;
}) {
  const v = result.verification;
  const p = result.provider;
  const [showFields, setShowFields] = useState(false);
  const [approved, setApproved] = useState<string | null>(null);
  const [showAllSources, setShowAllSources] = useState(false);
  const sourcesId = useId();
  const preview = previewSources(result.evidence);
  // A highlighted fact hidden behind "See all" (e.g. picked from the cross-check list) opens it.
  const selectedHidden =
    selectedFactId != null &&
    result.evidence.some((e) => e.fact_id === selectedFactId) &&
    !preview.some((e) => e.fact_id === selectedFactId);
  const sourcesOpen = showAllSources || selectedHidden;
  const shownSources = sourcesOpen ? result.evidence : preview;
  const hiddenCount = result.evidence.length - preview.length;
  const kindCount = (k: Evidence["source"]) => result.evidence.filter((e) => e.source === k).length;
  // "7 spreadsheet, 5 drawing, 1 model" whenever the answer drew on more than one kind of file.
  const sourceSummary = (
    [
      [kindCount("excel"), "spreadsheet"],
      [kindCount("pdf"), "drawing"],
      [kindCount("iges"), "model"],
    ] as const
  ).filter(([n]) => n > 0);
  const verified = v && v.citations_checked + v.auto_linked > 0;

  return (
    <motion.article
      className="flex flex-col gap-3"
      aria-label="Answer"
      initial="hidden"
      animate="show"
      variants={{ show: { transition: { staggerChildren: 0.07 } } }}
    >
      <motion.div variants={reveal} className="flex flex-wrap items-center gap-2">
        <StatusPill status={result.status} />
        {result.status === "answered" || result.status === "computed" ? (
          <span className="text-xs text-zinc-500">confidence {result.confidence}</span>
        ) : null}
      </motion.div>

      <motion.div variants={reveal} className="flex flex-col gap-2 text-[0.95rem]">
        <ReactMarkdown components={markdown}>{result.answer}</ReactMarkdown>
      </motion.div>

      {result.computation ? (
        <motion.div
          variants={reveal}
          className="relative overflow-hidden rounded-xl border border-sky-200 bg-sky-50/70 p-3.5 dark:border-sky-400/20 dark:bg-sky-400/5"
        >
          <div className="flex items-start justify-between gap-3">
            <p className="flex items-center gap-1.5 text-xs font-medium tracking-wide text-sky-800 uppercase dark:text-sky-300">
              <Calculator className="size-3.5" aria-hidden /> Working ({result.computation.label})
            </p>
            <motion.span
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 16, delay: 0.35 }}
              className="rounded-lg bg-sky-600 px-2 py-0.5 font-mono text-sm font-semibold text-white dark:bg-sky-400 dark:text-sky-950"
            >
              {result.computation.display}
            </motion.span>
          </div>
          <p className="mt-2 font-mono text-sm">{result.computation.working}</p>
          <p className="mt-1 flex items-center gap-1 text-xs text-zinc-500">
            <Cpu className="size-3" aria-hidden />
            Calculated by the app from the cited cells, not by the language model.
          </p>
        </motion.div>
      ) : null}

      {result.evidence.length ? (
        <motion.div variants={reveal} className="flex flex-col gap-1.5">
          <p className="flex flex-wrap items-baseline gap-x-2 text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase">
            Sources
            <span className="font-mono tracking-normal text-zinc-400 normal-case">
              {result.evidence.length}
              {sourceSummary.length > 1
                ? ` · ${sourceSummary.map(([n, label]) => `${n} ${label}`).join(", ")}`
                : ""}
            </span>
          </p>
          <motion.div layout className="flex flex-wrap gap-1.5" id={sourcesId}>
            <AnimatePresence initial={true} mode="popLayout">
              {shownSources.map((e, i) => (
                <motion.span
                  key={e.fact_id}
                  layout
                  initial={{ opacity: 0, scale: 0.9, y: 4 }}
                  animate={{ opacity: 1, scale: 1, y: 0, transition: { delay: Math.min(i, 12) * 0.03 } }}
                  exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.12 } }}
                  className="max-w-full"
                >
                  <EvidenceChip evidence={e} active={selectedFactId === e.fact_id} onSelect={onSelectFact} />
                </motion.span>
              ))}
            </AnimatePresence>
          </motion.div>
          {hiddenCount > 0 && !selectedHidden ? (
            <button
              type="button"
              aria-expanded={sourcesOpen}
              aria-controls={sourcesId}
              onClick={() => setShowAllSources((v) => !v)}
              className="group inline-flex w-fit items-center gap-1 rounded-lg px-1.5 py-0.5 text-xs font-medium text-cyan-700 transition-colors hover:bg-cyan-50 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:text-cyan-300 dark:hover:bg-cyan-400/10"
            >
              {sourcesOpen ? "Show fewer" : `See all ${result.evidence.length} sources`}
              {sourcesOpen ? null : (
                <span className="rounded-full bg-cyan-100 px-1.5 font-mono text-[10px] text-cyan-800 dark:bg-cyan-400/15 dark:text-cyan-200">
                  +{hiddenCount}
                </span>
              )}
              <ChevronDown
                className={cn("size-3.5 transition-transform duration-200", sourcesOpen && "rotate-180")}
                aria-hidden
              />
            </button>
          ) : null}
        </motion.div>
      ) : null}

      {result.actions.length ? (
        <motion.div variants={reveal} className="flex flex-col gap-2">
          {result.actions.map((a) => (
            <motion.button
              key={`${a.id}-${a.file}`}
              type="button"
              disabled={!onAction || approved !== null}
              onClick={() => {
                setApproved(a.file);
                onAction?.(a);
              }}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              className="group relative inline-flex w-fit items-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 px-3.5 py-2 text-sm font-medium text-white shadow-md shadow-orange-500/25 transition-opacity focus-visible:ring-2 focus-visible:ring-orange-400 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span
                aria-hidden
                className="absolute inset-y-0 -left-1/2 w-1/2 -skew-x-12 bg-white/25 transition-transform duration-700 group-hover:translate-x-[300%]"
              />
              <ScanEye className="relative size-4" aria-hidden />
              <span className="relative">{approved === a.file ? "Reading the scan…" : a.label}</span>
            </motion.button>
          ))}
          <p className="text-xs text-zinc-500">
            The page images are sent to the vision model. Values read this way are labelled{" "}
            <span className="inline-flex items-center gap-0.5 text-violet-700 dark:text-violet-300">
              <Eye className="size-3" aria-hidden /> vision
            </span>{" "}
            so you can check them against the drawing.
          </p>
        </motion.div>
      ) : null}

      {result.cross_checks.length ? (
        <motion.div variants={reveal} className="flex flex-col gap-1.5">
          <p className="flex items-center gap-1.5 text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase">
            <ArrowLeftRight className="size-3" aria-hidden /> Spreadsheet · drawing · model
          </p>
          <CrossCheckList checks={result.cross_checks} onSelect={onSelectFact} />
        </motion.div>
      ) : null}

      {result.status === "not_found" && result.available_fields.length ? (
        <motion.div variants={reveal} className="text-sm text-zinc-600 dark:text-zinc-400">
          <button
            type="button"
            aria-expanded={showFields}
            onClick={() => setShowFields((s) => !s)}
            className="inline-flex items-center gap-1 text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase hover:text-zinc-800 dark:hover:text-zinc-200"
          >
            What the record does contain
            <ChevronDown
              className={cn("size-3.5 transition-transform", showFields && "rotate-180")}
              aria-hidden
            />
          </button>
          <motion.p
            initial={false}
            aria-hidden={!showFields}
            animate={
              showFields
                ? { height: "auto", opacity: 1, marginTop: 4 }
                : { height: 0, opacity: 0, marginTop: 0 }
            }
            className="overflow-hidden"
          >
            {result.available_fields.join(" · ")}
          </motion.p>
        </motion.div>
      ) : null}

      {result.suggestions.length ? (
        <motion.p variants={reveal} className="text-sm text-zinc-600 dark:text-zinc-400">
          Did you mean{" "}
          {result.suggestions.map((s, i) => (
            <span key={s}>
              <Link href={`/parts/${encodeURIComponent(s)}`} className="font-mono underline">
                {s}
              </Link>
              {i < result.suggestions.length - 1 ? ", " : "?"}
            </span>
          ))}
        </motion.p>
      ) : null}

      {result.general_knowledge.length ? (
        <motion.aside
          variants={reveal}
          className="rounded-xl border border-dashed border-zinc-300 p-3 text-sm text-zinc-600 dark:border-white/15 dark:text-zinc-400"
        >
          <p className="mb-1 flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
            <BookOpen className="size-3.5" aria-hidden /> Background (general knowledge, not from the files)
          </p>
          <ul className="list-disc space-y-1 pl-5">
            {result.general_knowledge.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </motion.aside>
      ) : null}

      {result.warnings.length ? (
        <motion.ul variants={reveal} className="flex flex-col gap-1">
          {result.warnings.map((w) => (
            <li key={w} className="flex gap-1.5 text-xs text-amber-800 dark:text-amber-300">
              <AlertTriangle className="size-3.5 shrink-0" aria-hidden /> {w}
            </li>
          ))}
        </motion.ul>
      ) : null}

      {verified || p ? (
        <motion.footer
          variants={reveal}
          className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-zinc-100 pt-2.5 text-xs text-zinc-500 dark:border-white/5"
        >
          {v && verified ? (
            <span
              className="inline-flex items-center gap-1.5"
              title={v.dropped.map((d) => `${d.fact_id}: ${d.reason}`).join("\n")}
            >
              <ShieldCheck className="size-3.5 text-emerald-500" aria-hidden />
              <span>
                {v.citations_verified}/{v.citations_checked} citations verified
                {v.auto_linked ? `, ${v.auto_linked} auto-linked` : ""}
                {v.dropped.length ? `, ${v.dropped.length} rejected` : ""}
              </span>
              <span
                aria-hidden
                className="h-1 w-12 overflow-hidden rounded-full bg-zinc-200 dark:bg-white/10"
              >
                <motion.span
                  className="block h-full rounded-full bg-emerald-500"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${v.citations_checked ? (v.citations_verified / v.citations_checked) * 100 : 100}%`,
                  }}
                  transition={{ duration: 0.8, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
                />
              </span>
            </span>
          ) : null}
          {p ? (
            <span>
              {p.model} · {(p.latency_ms / 1000).toFixed(1)} s
              {p.fallback_used ? (
                <span
                  className="ml-1 rounded bg-amber-100 px-1 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200"
                  title={p.fallback_reason ?? ""}
                >
                  fallback provider
                </span>
              ) : null}
            </span>
          ) : null}
        </motion.footer>
      ) : null}
    </motion.article>
  );
}
