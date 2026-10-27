"use client";

import {
  AlertTriangle,
  ArrowLeftRight,
  EyeOff,
  FileSpreadsheet,
  FileText,
  History,
  Rows3,
  ScanEye,
  Table2,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { CellRef, DrawingSlice, PartRecord, SheetSlice } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { CrossCheckList } from "./cross-checks";
import { DrawingViewer } from "./drawing-viewer";
import { AnimatedTabs } from "./ui/animated-tabs";

const sheetKey = (s: SheetSlice) => `${s.file}::${s.sheet}`;
const drawingKey = (d: DrawingSlice) => `pdf::${d.file}`;
const CHECKS = "checks";

function HistoryTag({ reason }: { reason?: string | null }) {
  return (
    <span
      title={reason ?? "History, never used as the current value"}
      className="ml-1 inline-flex items-center gap-0.5 rounded bg-zinc-100 px-1 align-middle font-sans text-[10px] font-normal text-zinc-500 not-italic dark:bg-white/5"
    >
      <History className="size-2.5" aria-hidden /> history
    </span>
  );
}

function CellText({ cell, selected }: { cell: CellRef; selected: boolean }) {
  return (
    <span
      data-cell-id={cell.cell_id}
      title={`${cell.file} › ${cell.sheet} › ${cell.col}${cell.row}${cell.comment ? `\nComment: ${cell.comment}` : ""}`}
      className={cn(
        "relative inline-block rounded-md px-1 py-0.5 transition-colors duration-300",
        selected && "bg-amber-200/80 text-amber-950 dark:bg-amber-400/20 dark:text-amber-100",
        cell.hidden && "text-zinc-500 italic",
      )}
    >
      {selected ? (
        <>
          <motion.span
            aria-hidden
            className="pointer-events-none absolute -inset-0.5 rounded-md ring-2 ring-amber-400"
            initial={{ scale: 1.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 18 }}
          />
          <motion.span
            aria-hidden
            className="pointer-events-none absolute -inset-0.5 rounded-md ring-2 ring-amber-400"
            animate={{ scale: [1, 1.25], opacity: [0.7, 0] }}
            transition={{ duration: 1.4, repeat: 2, ease: "easeOut" }}
          />
        </>
      ) : null}
      <span className="relative">{cell.value}</span>
      {cell.comment ? <sup className="relative ml-0.5 text-amber-600">●</sup> : null}
      {selected ? <span className="sr-only"> (cited cell)</span> : null}
    </span>
  );
}

const rowIn = {
  hidden: { opacity: 0, y: 6 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3 } },
};

function AttributeTable({ sheet, selected }: { sheet: SheetSlice; selected?: string | null }) {
  return (
    <div className="flex flex-col gap-4">
      {sheet.rows.map((row) => (
        <table key={row.row} className={cn("w-full text-sm", row.stale && "opacity-60")}>
          <caption className="pb-1 text-left font-mono text-[11px] text-zinc-400">
            {sheet.layout === "card" ? "Part card, labels down the first column" : `Row ${row.row}`}
            {row.stale ? <HistoryTag reason={row.stale_reason} /> : null}
          </caption>
          <motion.tbody
            className="divide-y divide-zinc-100 dark:divide-white/5"
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.025 } } }}
          >
            {row.cells.map((c) => (
              <motion.tr
                key={c.cell_id}
                variants={rowIn}
                className={cn(
                  "align-top transition-colors",
                  selected === c.cell_id
                    ? "bg-amber-50/70 dark:bg-amber-400/5"
                    : "hover:bg-zinc-50 dark:hover:bg-white/[0.02]",
                )}
              >
                <th scope="row" className="w-2/5 py-2 pr-3 pl-1 text-left font-normal">
                  <span className="block font-medium text-zinc-800 dark:text-zinc-200">{c.header}</span>
                  {c.canonical ? (
                    <span className="block text-xs text-zinc-400">{c.canonical.replaceAll("_", " ")}</span>
                  ) : (
                    <span className="block text-xs text-zinc-400 italic">unmapped column</span>
                  )}
                </th>
                <td className="py-2 pr-2">
                  <CellText cell={c} selected={selected === c.cell_id} />
                </td>
                <td className="py-2 pr-1 text-right font-mono text-xs text-zinc-400">
                  {c.col}
                  {c.row}
                </td>
              </motion.tr>
            ))}
          </motion.tbody>
        </table>
      ))}
    </div>
  );
}

function RowsTable({ sheet, selected }: { sheet: SheetSlice; selected?: string | null }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-white/10" data-hscroll>
      <table className="w-full text-sm">
        <thead className="bg-zinc-50 dark:bg-white/[0.03]">
          <tr className="border-b border-zinc-200 text-left dark:border-white/10">
            <th className="py-2 pr-3 pl-3 font-mono text-xs font-normal text-zinc-400">Row</th>
            {sheet.columns.map((col) => (
              <th key={col.col} scope="col" className="py-2 pr-3 align-bottom font-medium whitespace-nowrap">
                {col.header}
                <span className="block text-xs font-normal text-zinc-400">
                  {col.canonical?.replaceAll("_", " ") ?? "unmapped"}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <motion.tbody
          className="divide-y divide-zinc-100 dark:divide-white/5"
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.05 } } }}
        >
          {sheet.rows.map((row) => {
            const byCol = new Map(row.cells.map((c) => [c.col, c]));
            return (
              <motion.tr
                key={row.row}
                variants={rowIn}
                className={cn("hover:bg-zinc-50 dark:hover:bg-white/[0.02]", row.stale && "text-zinc-500")}
              >
                <td className="py-2 pr-3 pl-3 font-mono text-xs whitespace-nowrap text-zinc-400">
                  {row.row}
                  {row.stale ? <HistoryTag reason={row.stale_reason} /> : null}
                </td>
                {sheet.columns.map((col) => {
                  const cell = byCol.get(col.col);
                  return (
                    <td key={col.col} className="py-2 pr-3 whitespace-nowrap">
                      {cell ? <CellText cell={cell} selected={selected === cell.cell_id} /> : null}
                    </td>
                  );
                })}
              </motion.tr>
            );
          })}
        </motion.tbody>
      </table>
    </div>
  );
}

export function RecordViewer({
  record,
  selectedFactId,
  onSelectFact,
  className,
}: {
  record: PartRecord;
  /** A spreadsheet cell id or a drawing fact id; the viewer opens the tab that holds it. */
  selectedFactId?: string | null;
  onSelectFact?: (factId: string) => void;
  className?: string;
}) {
  const panelId = useId();
  const firstTab = record.sheets[0]
    ? sheetKey(record.sheets[0])
    : record.drawings[0]
      ? drawingKey(record.drawings[0])
      : "";
  const [active, setActive] = useState(firstTab);
  const containerRef = useRef<HTMLDivElement>(null);

  const tabOfFact = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of record.sheets) {
      for (const r of s.rows) for (const c of r.cells) map.set(c.cell_id, sheetKey(s));
      for (const b of s.banner) map.set(b.cell_id, sheetKey(s));
    }
    for (const d of record.drawings) for (const f of d.facts) map.set(f.fact_id, drawingKey(d));
    return map;
  }, [record]);

  // Jump to the tab that holds the selected fact (derived during render, no effect needed).
  const target = selectedFactId ? tabOfFact.get(selectedFactId) : undefined;
  const [lastTarget, setLastTarget] = useState<string | undefined>(undefined);
  if (target && target !== lastTarget) {
    setLastTarget(target);
    setActive(target);
  }

  useEffect(() => {
    const container = containerRef.current;
    if (!selectedFactId || !container) return;
    let raf = 0;
    let tries = 0;
    // A freshly switched sheet mounts after its exit animation, so look for the cell for a
    // few frames before giving up.
    const locate = () => {
      const el = container.querySelector<HTMLElement>(`[data-cell-id="${CSS.escape(selectedFactId)}"]`);
      if (!el) {
        if (tries++ < 45) raf = requestAnimationFrame(locate);
        return;
      }
      // Scroll only this panel (scrollIntoView would also scroll the window).
      const box = el.getBoundingClientRect();
      const view = container.getBoundingClientRect();
      container.scrollTo({
        top: container.scrollTop + box.top - view.top - view.height / 2 + box.height / 2,
        behavior: "smooth",
      });
      const hscroll = el.closest<HTMLElement>("[data-hscroll]");
      if (hscroll) {
        const hv = hscroll.getBoundingClientRect();
        hscroll.scrollTo({
          left: hscroll.scrollLeft + box.left - hv.left - hv.width / 2 + box.width / 2,
          behavior: "smooth",
        });
      }
    };
    raf = requestAnimationFrame(locate);
    return () => cancelAnimationFrame(raf);
  }, [selectedFactId, active]);

  const sheet = record.sheets.find((s) => sheetKey(s) === active);
  const drawing = record.drawings.find((d) => drawingKey(d) === active);
  const showChecks = active === CHECKS && record.cross_checks.length > 0;
  const current = sheet ?? (drawing || showChecks ? undefined : record.sheets[0]);
  const activeKey = showChecks
    ? CHECKS
    : drawing
      ? drawingKey(drawing)
      : current
        ? sheetKey(current)
        : firstTab;
  const cellCount = record.sheets.reduce((n, s) => n + s.rows.reduce((m, r) => m + r.cells.length, 0), 0);
  const factCount = record.drawings.reduce((n, d) => n + d.facts.length, 0);
  const disagreements = record.cross_checks.filter((c) => c.verdict === "disagree").length;

  return (
    <section
      aria-label="Part record"
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-white/10 dark:bg-zinc-900/70",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-2.5 dark:border-white/10">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Table2 className="size-4 text-cyan-500" aria-hidden /> Part record
        </p>
        <p className="font-mono text-[11px] text-zinc-500">
          {record.sheets.length} sheet{record.sheets.length === 1 ? "" : "s"} · {cellCount} cells
          {record.drawings.length
            ? ` · ${record.drawings.length} drawing${record.drawings.length === 1 ? "" : "s"} · ${factCount} facts`
            : ""}
        </p>
      </div>

      <div className="overflow-x-auto border-b border-zinc-200 px-2 py-2 [scrollbar-width:none] dark:border-white/10">
        <AnimatedTabs
          label="Sheets"
          value={activeKey}
          onChange={setActive}
          panelIdFor={() => panelId}
          tabs={[
            ...record.sheets.map((s) => ({
              id: sheetKey(s),
              ariaLabel: `${s.sheet} sheet in ${s.file}${s.hidden ? ", hidden sheet" : ""}${s.stale ? ", history" : ""}`,
              icon:
                s.kind === "rows" ? (
                  <Rows3 className="size-3.5" aria-hidden />
                ) : (
                  <FileSpreadsheet className="size-3.5" aria-hidden />
                ),
              label: s.sheet,
              meta: (
                <>
                  <span className="text-xs font-normal text-zinc-400">{s.file}</span>
                  {s.hidden ? <EyeOff className="size-3.5" aria-hidden /> : null}
                  {s.stale ? <History className="size-3.5 text-zinc-400" aria-hidden /> : null}
                </>
              ),
            })),
            ...record.drawings.map((d) => ({
              id: drawingKey(d),
              ariaLabel: `Drawing ${d.file}${d.scanned && !d.readable ? ", scanned and not read yet" : ""}`,
              icon: <FileText className="size-3.5" aria-hidden />,
              label: d.file,
              meta:
                d.scanned && !d.readable ? (
                  <ScanEye className="size-3.5 text-amber-500" aria-hidden />
                ) : d.current_revision ? (
                  <span className="text-xs font-normal text-zinc-400">Rev {d.current_revision}</span>
                ) : null,
            })),
            ...(record.cross_checks.length
              ? [
                  {
                    id: CHECKS,
                    ariaLabel: `Cross-check, ${disagreements} disagreement${disagreements === 1 ? "" : "s"}`,
                    icon: <ArrowLeftRight className="size-3.5" aria-hidden />,
                    label: "Cross-check",
                    meta: disagreements ? (
                      <span className="rounded-full bg-rose-500 px-1.5 text-[10px] font-semibold text-white">
                        {disagreements}
                      </span>
                    ) : null,
                  },
                ]
              : []),
          ]}
        />
      </div>

      <div ref={containerRef} id={panelId} role="tabpanel" className="min-h-0 flex-1 overflow-y-auto p-4">
        <AnimatePresence mode="wait" initial={false}>
          {showChecks ? (
            <motion.div
              key={CHECKS}
              className="flex flex-col gap-3"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.2 }}
            >
              <p className="text-xs text-zinc-500">
                The app compares the spreadsheet and the drawing field by field, converting units only when
                the files state them. Nothing is corrected: both values stay cited.
              </p>
              <CrossCheckList
                checks={record.cross_checks}
                selected={selectedFactId}
                onSelect={onSelectFact}
              />
            </motion.div>
          ) : drawing ? (
            <motion.div
              key={drawingKey(drawing)}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.2 }}
            >
              <DrawingViewer
                partNumber={record.part_key}
                drawing={drawing}
                selected={selectedFactId}
                onSelect={onSelectFact}
              />
            </motion.div>
          ) : current ? (
            <motion.div
              key={sheetKey(current)}
              className="flex flex-col gap-4"
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.2 }}
            >
              {current.banner.length ? (
                <div className="rounded-xl bg-zinc-50 p-3 text-xs text-zinc-500 dark:bg-white/[0.03]">
                  <p className="mb-1 font-medium tracking-wide uppercase">Sheet title / banner</p>
                  {current.banner.map((b) => (
                    <p key={b.cell_id}>
                      <CellText cell={b} selected={selectedFactId === b.cell_id} />
                    </p>
                  ))}
                </div>
              ) : null}
              {current.stale ? (
                <p className="flex gap-2 rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-600 dark:border-white/10 dark:bg-white/[0.03] dark:text-zinc-400">
                  <History className="size-4 shrink-0" aria-hidden />
                  History: {current.stale_reason ?? "archived data"}. Shown for reference; answers never use
                  it as the current value.
                </p>
              ) : null}
              <p className="text-xs text-zinc-500">
                {current.layout === "card" ? "Vertical part card" : `Header on row ${current.header_row}`} ·{" "}
                {current.kind === "rows"
                  ? `${current.rows.length} row${current.rows.length === 1 ? "" : "s"} for this part`
                  : "one record row for this part"}
                {current.default_unit ? ` · units ${current.default_unit} unless stated` : ""}
              </p>
              {current.kind === "rows" ? (
                <RowsTable sheet={current} selected={selectedFactId} />
              ) : (
                <AttributeTable sheet={current} selected={selectedFactId} />
              )}
            </motion.div>
          ) : (
            <p className="text-sm text-zinc-500">This part has no spreadsheet rows.</p>
          )}
        </AnimatePresence>

        {record.warnings.length ? (
          <ul className="mt-6 flex flex-col gap-2">
            {record.warnings.map((w) => (
              <li
                key={w}
                className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/5 dark:text-amber-200"
              >
                <AlertTriangle className="size-4 shrink-0" aria-hidden />
                {w}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
