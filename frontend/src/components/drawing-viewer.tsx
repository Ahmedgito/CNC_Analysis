"use client";

import { AlertTriangle, CornerDownRight, Eye, History, ScanEye, ZoomIn, ZoomOut } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { drawingPageUrl } from "@/lib/api/client";
import type { DrawingFact, DrawingSlice, Region } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";

const REGIONS: { region: Region; label: string }[] = [
  { region: "title_block", label: "Title block" },
  { region: "note", label: "Notes" },
  { region: "dimension", label: "Dimensions" },
  { region: "revision", label: "Revisions" },
  { region: "text", label: "Other text" },
];

const pct = (v: number, of: number) => `${(v / of) * 100}%`;

/** Values that were not read as printed text get a visible label, never a silent pass. */
function FactFlags({ fact }: { fact: DrawingFact }) {
  return (
    <>
      {fact.confidence === "vision" ? (
        <span
          title="Read from a scanned image by the vision model"
          className="inline-flex items-center gap-0.5 rounded border border-dashed border-violet-400/70 px-1 text-[10px] text-violet-700 dark:text-violet-300"
        >
          <Eye className="size-2.5" aria-hidden /> vision
        </span>
      ) : null}
      {fact.confidence === "inferred" ? (
        <span
          title="Type inferred from the shape of the text, not from a label"
          className="rounded border border-dashed border-zinc-300 px-1 text-[10px] text-zinc-500 dark:border-white/15"
        >
          inferred
        </span>
      ) : null}
      {fact.stale ? (
        <span
          title={fact.stale_reason ?? "History, not the current value"}
          className="inline-flex items-center gap-0.5 rounded bg-zinc-100 px-1 text-[10px] text-zinc-500 dark:bg-white/5"
        >
          <History className="size-2.5" aria-hidden /> history
        </span>
      ) : null}
    </>
  );
}

export function DrawingViewer({
  partNumber,
  drawing,
  selected,
  onSelect,
}: {
  partNumber: string;
  drawing: DrawingSlice;
  selected?: string | null;
  onSelect?: (factId: string) => void;
}) {
  const factById = new Map(drawing.facts.map((f) => [f.fact_id, f]));
  const selectedFact = selected ? factById.get(selected) : undefined;
  const [page, setPage] = useState(selectedFact?.page ?? 1);
  const [zoom, setZoom] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);

  // Follow a citation onto its page (derived during render, no effect needed).
  const [lastSelected, setLastSelected] = useState(selected);
  if (selected !== lastSelected) {
    setLastSelected(selected);
    if (selectedFact && selectedFact.page !== page) setPage(selectedFact.page);
  }

  const meta = drawing.pages.find((p) => p.page === page);
  const onPage = drawing.facts.filter((f) => f.page === page);
  const boxes = onPage.flatMap((f) => f.bboxes.map((b, i) => ({ fact: f, b, first: i === 0 })));
  const unreadScan = drawing.scanned && !drawing.readable;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
        {drawing.title ? (
          <span className="font-medium text-zinc-700 dark:text-zinc-300">{drawing.title}</span>
        ) : null}
        {drawing.current_revision ? <span>Rev {drawing.current_revision}</span> : null}
        {drawing.units ? <span>Units {drawing.units}</span> : null}
        <span>
          {drawing.page_count} page{drawing.page_count === 1 ? "" : "s"}
        </span>
        {drawing.part_number_source ? (
          <span title="Where the part number linking this drawing was read">
            linked by {drawing.part_number_source.replace("_", " ")}
          </span>
        ) : null}
        {drawing.extraction === "vision" ? (
          <span className="inline-flex items-center gap-1 text-violet-700 dark:text-violet-300">
            <Eye className="size-3" aria-hidden /> read by the vision model
          </span>
        ) : null}
      </div>

      {unreadScan ? (
        <p className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/5 dark:text-amber-200">
          <ScanEye className="size-4 shrink-0" aria-hidden />
          This drawing is a scanned image with no text layer, so nothing on it has been read. Ask a question
          about it and approve reading it with the vision model.
        </p>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        {drawing.page_count > 1 ? (
          <div className="flex gap-1" role="group" aria-label="Pages">
            {Array.from({ length: drawing.page_count }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={n === page}
                onClick={() => setPage(n)}
                className={cn(
                  "rounded-md px-2 py-0.5 font-mono text-xs transition-colors",
                  n === page
                    ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900"
                    : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-white/5",
                )}
              >
                p{n}
              </button>
            ))}
          </div>
        ) : (
          <span className="font-mono text-[11px] text-zinc-400">page 1</span>
        )}
        <button
          type="button"
          onClick={() => setZoom((z) => !z)}
          aria-pressed={zoom}
          className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-white/5 dark:hover:text-zinc-200"
        >
          {zoom ? <ZoomOut className="size-3.5" aria-hidden /> : <ZoomIn className="size-3.5" aria-hidden />}
          {zoom ? "Fit" : "Zoom"}
        </button>
      </div>

      <div
        className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-white/10"
        data-hscroll
      >
        <div
          className={cn("relative transition-[width] duration-300", zoom ? "w-[220%]" : "w-full")}
          style={meta ? { aspectRatio: `${meta.width} / ${meta.height}` } : undefined}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- server-rendered PNG through the API proxy */}
          <img
            src={drawingPageUrl(partNumber, drawing.file, page, zoom ? 200 : 110)}
            alt={`${drawing.file}, page ${page}`}
            className="absolute inset-0 size-full object-contain"
            draggable={false}
          />
          {meta
            ? boxes.map(({ fact, b, first }, i) => {
                const isSelected = fact.fact_id === selected;
                const isHovered = fact.fact_id === hovered;
                return (
                  <button
                    key={`${fact.fact_id}-${i}`}
                    type="button"
                    data-cell-id={first ? fact.fact_id : undefined}
                    onClick={() => onSelect?.(fact.fact_id)}
                    onMouseEnter={() => setHovered(fact.fact_id)}
                    onMouseLeave={() => setHovered(null)}
                    aria-label={`${fact.label}: ${fact.value}`}
                    title={`${fact.label}: ${fact.value}`}
                    className={cn(
                      "absolute rounded-[3px] transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-cyan-500 focus-visible:outline-none",
                      isSelected
                        ? "z-10 bg-amber-300/35 ring-2 ring-amber-500"
                        : isHovered
                          ? "bg-cyan-400/25 ring-2 ring-cyan-500"
                          : fact.stale
                            ? "ring-1 ring-zinc-400/40 hover:bg-zinc-400/10"
                            : "ring-1 ring-cyan-500/35 hover:bg-cyan-400/15",
                    )}
                    style={{
                      left: `calc(${pct(b[0], meta.width)} - 2px)`,
                      top: `calc(${pct(b[1], meta.height)} - 2px)`,
                      width: `calc(${pct(b[2] - b[0], meta.width)} + 4px)`,
                      height: `calc(${pct(b[3] - b[1], meta.height)} + 4px)`,
                    }}
                  >
                    {isSelected ? (
                      <motion.span
                        aria-hidden
                        className="pointer-events-none absolute -inset-1 rounded-md ring-2 ring-amber-400"
                        initial={{ scale: 1.8, opacity: 0 }}
                        animate={{ scale: [1.8, 1, 1.35], opacity: [0, 1, 0] }}
                        transition={{ duration: 1.4, repeat: 2, ease: "easeOut" }}
                      />
                    ) : null}
                  </button>
                );
              })
            : null}
        </div>
      </div>

      {REGIONS.map(({ region, label }) => {
        const facts = onPage.filter((f) => f.region === region);
        if (!facts.length) return null;
        return (
          <section key={region} aria-label={label} className="flex flex-col gap-1">
            <h3 className="text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase">
              {label} <span className="font-mono tracking-normal text-zinc-400">· {facts.length}</span>
            </h3>
            <ul className="divide-y divide-zinc-100 text-sm dark:divide-white/5">
              {facts.map((f) => {
                const target = f.points_to ? factById.get(f.points_to) : undefined;
                return (
                  <li key={f.fact_id}>
                    <button
                      type="button"
                      onClick={() => onSelect?.(f.fact_id)}
                      onMouseEnter={() => setHovered(f.fact_id)}
                      onMouseLeave={() => setHovered(null)}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-md px-1 py-1.5 text-left transition-colors",
                        f.fact_id === selected
                          ? "bg-amber-50 dark:bg-amber-400/10"
                          : "hover:bg-zinc-50 dark:hover:bg-white/[0.03]",
                        f.stale && "text-zinc-500",
                      )}
                    >
                      <span className="w-2/5 shrink-0">
                        <span className="block font-medium text-zinc-800 dark:text-zinc-200">{f.label}</span>
                        <span className="block text-xs text-zinc-400">
                          {(f.canonical ?? f.kind ?? "unmapped").replaceAll("_", " ")}
                        </span>
                      </span>
                      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <span className={cn("break-words", f.stale && "line-through decoration-zinc-400")}>
                          {f.value}
                          {f.unit ? <span className="ml-1 text-xs text-zinc-400">{f.unit}</span> : null}
                        </span>
                        {target ? (
                          <span className="inline-flex items-center gap-1 text-xs text-cyan-700 dark:text-cyan-300">
                            <CornerDownRight className="size-3" aria-hidden />
                            {target.label}: {target.value}
                          </span>
                        ) : null}
                        <span className="flex flex-wrap gap-1">
                          <FactFlags fact={f} />
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {drawing.warnings.length ? (
        <ul className="flex flex-col gap-1">
          {drawing.warnings.map((w) => (
            <li key={w} className="flex gap-1.5 text-xs text-amber-800 dark:text-amber-300">
              <AlertTriangle className="size-3.5 shrink-0" aria-hidden /> {w}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
