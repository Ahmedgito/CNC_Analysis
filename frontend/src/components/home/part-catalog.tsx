"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, FileSpreadsheet, Filter, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ApiError, listParts } from "@/lib/api/client";
import type { PartSummary } from "@/lib/api/schemas";
import { SourceBadges } from "../source-badges";
import { SpotlightCard } from "../ui/spotlight-card";
import { Tilt } from "../ui/tilt";
import { SectionHeading } from "./section-heading";

export function PartCatalog() {
  const [filter, setFilter] = useState("");
  const { data, error, isPending } = useQuery({ queryKey: ["parts", ""], queryFn: () => listParts() });

  const parts = useMemo(() => {
    const all = data?.parts ?? [];
    const f = filter.trim().toLowerCase();
    if (!f) return all;
    return all.filter(
      (p) =>
        p.part_key.toLowerCase().includes(f) ||
        (p.description ?? "").toLowerCase().includes(f) ||
        p.files.some((file) => file.toLowerCase().includes(f)),
    );
  }, [data, filter]);

  return (
    <section id="parts" aria-labelledby="parts-title" className="scroll-mt-24 px-4 py-20 sm:px-6">
      <SectionHeading id="parts-title" eyebrow="Part catalogue" title="Every part found in your files">
        Parts are discovered from any workbook layout. Each card shows which sources exist for it.
      </SectionHeading>

      <div className="mx-auto max-w-7xl">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <label className="relative flex w-full items-center sm:w-80">
            <span className="sr-only">Filter parts</span>
            <Filter className="pointer-events-none absolute left-3 size-4 text-zinc-400" aria-hidden />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by number, name or file"
              className="h-10 w-full rounded-xl border border-zinc-200 bg-white pr-9 pl-9 text-sm outline-none transition placeholder:text-zinc-400 focus:border-cyan-400 focus:ring-4 focus:ring-cyan-500/10 dark:border-white/10 dark:bg-zinc-900"
            />
            {filter ? (
              <button
                type="button"
                onClick={() => setFilter("")}
                aria-label="Clear filter"
                className="absolute right-2 grid size-6 place-items-center rounded-md text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-white/10"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            ) : null}
          </label>
          <p className="text-xs text-zinc-500" aria-live="polite">
            {isPending ? "Loading parts…" : `${parts.length} of ${data?.total ?? 0} parts`}
          </p>
        </div>

        {error ? (
          <div
            role="alert"
            className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300"
          >
            <p className="font-medium">Can&apos;t load parts</p>
            <p>{error instanceof ApiError ? error.message : String(error)}</p>
          </div>
        ) : isPending ? (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => (
              <li key={i} className="h-52 animate-pulse rounded-2xl bg-zinc-200/60 dark:bg-white/5" />
            ))}
          </ul>
        ) : parts.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-zinc-300 p-10 text-center text-sm text-zinc-500 dark:border-white/15">
            {filter
              ? "No part matches that filter."
              : "No parts ingested yet. Run `uv run cnc ingest ../data` in the backend."}
          </p>
        ) : (
          <motion.ul layout className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence mode="popLayout">
              {parts.map((p, i) => (
                <motion.li
                  key={p.part_key}
                  layout
                  initial={{ opacity: 0, y: 24, scale: 0.97 }}
                  whileInView={{ opacity: 1, y: 0, scale: 1 }}
                  viewport={{ once: true, margin: "-40px" }}
                  exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.15 } }}
                  transition={{ duration: 0.55, delay: Math.min(i, 8) * 0.06, ease: [0.16, 1, 0.3, 1] }}
                >
                  <PartCard part={p} />
                </motion.li>
              ))}
            </AnimatePresence>
          </motion.ul>
        )}
      </div>
    </section>
  );
}

function PartCard({ part }: { part: PartSummary }) {
  return (
    <Tilt className="h-full">
      <SpotlightCard className="h-full" surfaceClassName="bg-white dark:bg-zinc-900/90">
        <Link
          href={`/parts/${encodeURIComponent(part.part_key)}`}
          className="group flex h-full flex-col gap-4 rounded-[inherit] p-5 outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
        >
          <div className="flex items-start justify-between">
            <span className="font-mono text-[10px] font-medium tracking-[0.2em] text-zinc-400 uppercase">
              Part no.
            </span>
            <span className="grid size-8 place-items-center rounded-full border border-zinc-200 text-zinc-400 transition group-hover:border-cyan-400/60 group-hover:bg-cyan-500 group-hover:text-white dark:border-white/10">
              <ArrowUpRight
                className="size-4 transition-transform duration-300 group-hover:rotate-45"
                aria-hidden
              />
            </span>
          </div>
          <div>
            <p className="font-mono text-4xl font-semibold tracking-tight">{part.display_part_number}</p>
            <p className="mt-1 text-zinc-600 dark:text-zinc-400">
              {part.description ?? "No description in the record"}
            </p>
          </div>
          <div className="mt-auto flex flex-col gap-3 border-t border-dashed border-zinc-200 pt-4 dark:border-white/10">
            <ul className="flex flex-col gap-1" aria-label="Files">
              {part.files.map((f) => (
                <li key={f} className="flex items-center gap-1.5 font-mono text-xs text-zinc-500">
                  <FileSpreadsheet className="size-3.5 text-emerald-500" aria-hidden />
                  {f}
                </li>
              ))}
            </ul>
            <SourceBadges sources={part.sources} />
          </div>
        </Link>
      </SpotlightCard>
    </Tilt>
  );
}
