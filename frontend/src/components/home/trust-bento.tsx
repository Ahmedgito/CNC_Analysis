"use client";

import {
  ArrowRightLeft,
  Box,
  Calculator,
  Check,
  FileSearch,
  FileSpreadsheet,
  FileText,
  MousePointerClick,
  ShieldCheck,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useInView } from "motion/react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { SpotlightCard } from "../ui/spotlight-card";
import { SectionHeading } from "./section-heading";

/** Ticks while the element is on screen; drives the looping mini-demos. */
function useTicker<T extends HTMLElement = HTMLDivElement>(ms: number, max: number) {
  const ref = useRef<T>(null);
  const inView = useInView(ref, { margin: "-20%" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!inView) return;
    const id = window.setInterval(() => setTick((t) => (t + 1) % max), ms);
    return () => window.clearInterval(id);
  }, [inView, ms, max]);
  return { ref, tick };
}

function Tile({
  title,
  body,
  icon,
  className,
  children,
  index,
}: {
  title: string;
  body: string;
  icon: ReactNode;
  className?: string;
  children: ReactNode;
  index: number;
}) {
  return (
    <motion.li
      className={cn("list-none", className)}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.6, delay: index * 0.07, ease: [0.16, 1, 0.3, 1] }}
    >
      <SpotlightCard className="h-full" surfaceClassName="bg-white dark:bg-zinc-900/80">
        <div className="flex h-full flex-col gap-5 p-6">
          <div className="flex-1">{children}</div>
          <div className="flex gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-cyan-50 text-cyan-700 dark:bg-cyan-400/10 dark:text-cyan-300">
              {icon}
            </span>
            <div>
              <h3 className="font-semibold">{title}</h3>
              <p className="mt-0.5 text-sm text-zinc-600 dark:text-zinc-400">{body}</p>
            </div>
          </div>
        </div>
      </SpotlightCard>
    </motion.li>
  );
}

// Real values from part 2280 in mfg_record_A.xlsx.
const SHEET = [
  { cell: "B2", header: "Description", value: "Flange" },
  { cell: "C2", header: "Material", value: "SS304" },
  { cell: "D2", header: "Stock Size (mm)", value: "Ø125 x 25 (round bar)" },
  { cell: "E2", header: "Finished Size (mm)", value: "Ø120 x 20" },
  { cell: "F2", header: "Holes", value: "6 x Ø10 through on Ø90 PCD; centre bore Ø40" },
  { cell: "G2", header: "Machine", value: "Mazak QT-200 lathe, Haas VF-2 mill" },
  { cell: "H2", header: "Cycle Time (min)", value: "28" },
  { cell: "I2", header: "General Tolerance", value: "±0.1 mm (ISO 2768-m)" },
];
const CHIPS = [1, 2, 5, 6];

function LocateDemo() {
  const { ref, tick } = useTicker(1900, CHIPS.length);
  const row = CHIPS[tick];
  return (
    <div ref={ref} className="grid h-full gap-5 md:grid-cols-[1.35fr_1fr] md:items-center">
      <div className="overflow-hidden rounded-xl border border-zinc-200 text-xs dark:border-white/10">
        <div className="flex items-center gap-1.5 border-b border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-[11px] text-zinc-500 dark:border-white/10 dark:bg-white/5">
          <FileSpreadsheet className="size-3.5 text-emerald-500" aria-hidden /> mfg_record_A.xlsx › Parts ›
          row 2
        </div>
        <table className="w-full">
          <tbody>
            {SHEET.map((r, i) => (
              <tr key={r.cell} className="border-b border-zinc-100 last:border-0 dark:border-white/5">
                <td className="w-2/5 px-3 py-2.5 text-zinc-500">{r.header}</td>
                <td className="relative px-3 py-2.5">
                  {i === row ? (
                    <motion.span
                      layoutId="bento-locate"
                      className="absolute inset-x-1.5 inset-y-1 rounded-md bg-amber-200/70 ring-2 ring-amber-400 dark:bg-amber-400/20"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  ) : null}
                  <span className="relative line-clamp-1 font-medium">{r.value}</span>
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-zinc-400">{r.cell}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-col gap-3">
        <p className="self-end rounded-2xl rounded-br-md bg-zinc-900 px-3 py-1.5 text-sm text-white dark:bg-white dark:text-zinc-900">
          Summarise how 2280 is made
        </p>
        <div className="rounded-2xl rounded-bl-md border border-zinc-200 p-3 text-sm dark:border-white/10">
          <p className="leading-relaxed">
            <span className="font-semibold">SS304</span> from a{" "}
            <span className="font-semibold">Ø125 x 25</span> round bar, machined on a{" "}
            <span className="font-semibold">Mazak QT-200 lathe and Haas VF-2 mill</span> in{" "}
            <span className="font-semibold">28 min</span> per piece.
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {CHIPS.map((r, i) => (
              <motion.span
                key={r}
                animate={i === tick ? { scale: 1.05 } : { scale: 1 }}
                className={cn(
                  "inline-flex items-center gap-1 rounded-md border px-2 py-1 font-mono text-[11px] transition-colors",
                  i === tick
                    ? "border-amber-400 bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200"
                    : "border-zinc-200 bg-zinc-50 text-zinc-600 dark:border-white/10 dark:bg-white/5 dark:text-zinc-400",
                )}
              >
                {i === tick ? <MousePointerClick className="size-3" aria-hidden /> : null}
                Parts › {SHEET[r].cell}
              </motion.span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function HonestDemo() {
  const { ref, tick } = useTicker(2600, 2);
  return (
    <div ref={ref} className="flex flex-col gap-2 text-sm">
      <p className="self-end rounded-2xl rounded-br-sm bg-zinc-900 px-3 py-1.5 text-white dark:bg-white dark:text-zinc-900">
        What is the unit price?
      </p>
      <AnimatePresence mode="wait">
        <motion.div
          key={tick}
          initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -6 }}
          className="rounded-2xl rounded-bl-sm border border-zinc-200 p-3 dark:border-white/10"
        >
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-400/10 dark:text-amber-300">
            <FileSearch className="size-3" aria-hidden /> Not in the files
          </span>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            No cost field in the record. It does have material, stock size, operations…
          </p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

const WORKING = "5 + 3 + 4 = 12 min";

function ComputeDemo() {
  const { ref, tick } = useTicker(110, WORKING.length + 18);
  const shown = WORKING.slice(0, Math.min(tick, WORKING.length));
  return (
    <div
      ref={ref}
      className="rounded-xl border border-sky-200 bg-sky-50/70 p-4 dark:border-sky-400/20 dark:bg-sky-400/5"
    >
      <p className="text-[11px] font-medium tracking-wide text-sky-800 uppercase dark:text-sky-300">
        Working · total setup time
      </p>
      <p className="mt-2 h-7 font-mono text-lg" aria-label={WORKING}>
        {shown}
        <motion.span
          aria-hidden
          className="ml-0.5 inline-block h-5 w-px translate-y-0.5 bg-sky-500"
          animate={{ opacity: [1, 0] }}
          transition={{ duration: 0.6, repeat: Infinity }}
        />
      </p>
      <p className="mt-1 font-mono text-[11px] text-zinc-500">Operations › F2, F3, F4</p>
    </div>
  );
}

const CITES = [
  { id: "Parts › C2", ok: true, text: "“SS304” matches" },
  { id: "Parts › D2", ok: true, text: "“Ø125 x 25” matches" },
  { id: "Parts › E9", ok: false, text: "“Ø52” is not in the file" },
];

function VerifyDemo() {
  const { ref, tick } = useTicker<HTMLUListElement>(900, CITES.length + 3);
  return (
    <ul ref={ref} className="flex flex-col gap-1.5 text-xs">
      {CITES.map((c, i) => {
        const done = tick > i;
        return (
          <li
            key={c.id}
            className="flex items-center gap-2 rounded-lg border border-zinc-200 px-2.5 py-2 dark:border-white/10"
          >
            <span
              className={cn(
                "grid size-5 place-items-center rounded-full transition-colors",
                !done
                  ? "bg-zinc-100 dark:bg-white/5"
                  : c.ok
                    ? "bg-emerald-500 text-white"
                    : "bg-red-500 text-white",
              )}
            >
              <AnimatePresence>
                {done ? (
                  <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}>
                    {c.ok ? <Check className="size-3" aria-hidden /> : <X className="size-3" aria-hidden />}
                  </motion.span>
                ) : null}
              </AnimatePresence>
            </span>
            <span className={cn("font-mono", done && !c.ok && "text-zinc-400 line-through")}>{c.id}</span>
            <span className="ml-auto text-zinc-500">{done ? c.text : "checking…"}</span>
          </li>
        );
      })}
    </ul>
  );
}

function SourcesDemo() {
  const nodes = [
    { label: "Excel", Icon: FileSpreadsheet, live: true, x: 18 },
    { label: "PDF", Icon: FileText, live: true, x: 50 },
    { label: "IGES", Icon: Box, live: false, x: 82 },
  ];
  return (
    <div className="relative h-36">
      <svg
        viewBox="0 0 100 60"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        aria-hidden
      >
        {nodes.map((n) => (
          <motion.path
            key={n.label}
            d={`M ${n.x} 18 C ${n.x} 34, 50 30, 50 46`}
            fill="none"
            strokeWidth={0.6}
            className={n.live ? "stroke-emerald-500" : "stroke-zinc-300 dark:stroke-zinc-700"}
            strokeDasharray={n.live ? undefined : "1.5 1.5"}
            initial={{ pathLength: 0 }}
            whileInView={{ pathLength: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2, ease: "easeInOut" }}
          />
        ))}
      </svg>
      {nodes.map((n) => (
        <span
          key={n.label}
          className={cn(
            "absolute top-0 inline-flex -translate-x-1/2 items-center gap-1 rounded-full border px-2 py-1 text-xs font-medium",
            n.live
              ? "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-300"
              : "border-dashed border-zinc-300 bg-white text-zinc-400 dark:border-white/15 dark:bg-zinc-900",
          )}
          style={{ left: `${n.x}%` }}
        >
          <n.Icon className="size-3.5" aria-hidden />
          {n.label}
          {n.live ? null : <span className="font-mono text-[9px]">soon</span>}
        </span>
      ))}
      <span className="absolute bottom-0 left-1/2 inline-flex -translate-x-1/2 items-center rounded-lg bg-zinc-900 px-3 py-1.5 font-mono text-xs text-white dark:bg-white dark:text-zinc-900">
        Part 2280
      </span>
    </div>
  );
}

function FailoverDemo() {
  const { ref, tick } = useTicker(2200, 2);
  const fallback = tick === 1;
  return (
    <div ref={ref} className="flex flex-col gap-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        {[
          { name: "Claude", active: !fallback },
          { name: "Groq", active: fallback },
        ].map((p) => (
          <motion.span
            key={p.name}
            animate={{ opacity: p.active ? 1 : 0.45, scale: p.active ? 1 : 0.96 }}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2 font-medium",
              p.active
                ? "border-cyan-400/60 bg-cyan-50 text-cyan-900 dark:bg-cyan-400/10 dark:text-cyan-200"
                : "border-zinc-200 dark:border-white/10",
            )}
          >
            <span className={cn("size-1.5 rounded-full", p.active ? "bg-cyan-500" : "bg-zinc-400")} />
            {p.name}
          </motion.span>
        ))}
      </div>
      <p className="flex items-center gap-1.5 text-zinc-500">
        <ArrowRightLeft className="size-3.5" aria-hidden />
        {fallback ? (
          <span>
            Claude overloaded → answered by Groq,{" "}
            <span className="rounded bg-amber-100 px-1 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200">
              fallback provider
            </span>
          </span>
        ) : (
          <span>Primary provider answering</span>
        )}
      </p>
    </div>
  );
}

export function TrustBento() {
  return (
    <section id="trust" aria-labelledby="trust-title" className="scroll-mt-24 px-4 py-20 sm:px-6">
      <SectionHeading
        id="trust-title"
        eyebrow="Built for trust"
        title="Guarantees you can see on every answer"
      >
        Each tile is a live miniature of what happens in the app.
      </SectionHeading>
      <ul className="mx-auto grid max-w-7xl auto-rows-fr gap-4 md:grid-cols-2 lg:grid-cols-6">
        <Tile
          index={0}
          className="md:col-span-2 lg:col-span-4 lg:row-span-2"
          icon={<MousePointerClick className="size-4.5" aria-hidden />}
          title="Click a source, see the cell"
          body="Every answer carries chips naming file, sheet and cell. Clicking one highlights it in the record."
        >
          <LocateDemo />
        </Tile>
        <Tile
          index={1}
          className="lg:col-span-2"
          icon={<FileSearch className="size-4.5" aria-hidden />}
          title="Says when it can't find it"
          body="Missing fields get an explicit “not in the files”, plus what the record does contain."
        >
          <HonestDemo />
        </Tile>
        <Tile
          index={2}
          className="lg:col-span-2"
          icon={<Calculator className="size-4.5" aria-hidden />}
          title="Maths done by code"
          body="The app computes totals and conversions from cited cells and shows the working."
        >
          <ComputeDemo />
        </Tile>
        <Tile
          index={3}
          className="lg:col-span-2"
          icon={<ShieldCheck className="size-4.5" aria-hidden />}
          title="Citations verified first"
          body="A cited value that doesn't match the stored cell is removed before you see the answer."
        >
          <VerifyDemo />
        </Tile>
        <Tile
          index={4}
          className="lg:col-span-2"
          icon={<FileSpreadsheet className="size-4.5" aria-hidden />}
          title="Excel and PDF today, IGES next"
          body="Spreadsheets and drawings are read, cited and cross-checked field by field; 3D models slot in next."
        >
          <SourcesDemo />
        </Tile>
        <Tile
          index={5}
          className="md:col-span-2 lg:col-span-2"
          icon={<ArrowRightLeft className="size-4.5" aria-hidden />}
          title="Fails over, and tells you"
          body="If Claude is unavailable, Groq answers and the answer footer says which model replied."
        >
          <FailoverDemo />
        </Tile>
      </ul>
    </section>
  );
}
