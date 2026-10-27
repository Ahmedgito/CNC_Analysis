"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, MessageSquareText, SearchX, Table2 } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { ApiError, getPart } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { ChatPanel } from "./chat-panel";
import { RecordViewer } from "./record-viewer";
import { SourceBadges } from "./source-badges";
import { AnimatedTabs } from "./ui/animated-tabs";

type View = "record" | "ask";

const shell =
  "relative isolate flex w-full flex-1 flex-col gap-4 px-3 pt-22 pb-3 sm:px-6 lg:h-dvh lg:flex-none lg:pb-5";
const backdrop =
  "pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(rgb(113_113_122/0.18)_1px,transparent_1px)] bg-size-[22px_22px] [mask-image:linear-gradient(to_bottom,black,transparent_70%)] dark:bg-[radial-gradient(rgb(255_255_255/0.06)_1px,transparent_1px)]";

export function PartWorkspace({ partNumber }: { partNumber: string }) {
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null);
  const [view, setView] = useState<View>("ask");
  const { data, error, isPending } = useQuery({
    queryKey: ["part", partNumber],
    queryFn: () => getPart(partNumber),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });

  if (isPending) return <WorkspaceSkeleton />;

  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    const suggestions = error instanceof ApiError ? (error.problem.suggestions ?? []) : [];
    return (
      <div className={cn(shell, "items-center justify-center")}>
        <div aria-hidden className={backdrop} />
        <motion.div
          className="flex max-w-xl flex-col items-center gap-4 py-16 text-center"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <motion.span
            className="grid size-14 place-items-center rounded-2xl bg-zinc-100 text-zinc-500 dark:bg-white/5"
            initial={{ rotate: -12, scale: 0.8 }}
            animate={{ rotate: 0, scale: 1 }}
            transition={{ type: "spring", stiffness: 260, damping: 14 }}
          >
            <SearchX className="size-6" aria-hidden />
          </motion.span>
          <h1 className="text-2xl font-semibold">
            {notFound ? `Part ${partNumber} not found` : "Can't load this part"}
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            {notFound
              ? "This part number is not in any ingested file, so there is nothing to answer from."
              : error.message}
          </p>
          {suggestions.length ? (
            <p className="flex flex-wrap items-center justify-center gap-2 text-sm">
              Did you mean
              {suggestions.map((s) => (
                <Link
                  key={s}
                  href={`/parts/${encodeURIComponent(s)}`}
                  className="rounded-full border border-zinc-200 px-3 py-1 font-mono font-medium transition hover:border-cyan-400/60 hover:text-cyan-700 dark:border-white/10 dark:hover:text-cyan-300"
                >
                  {s}
                </Link>
              ))}
            </p>
          ) : null}
          <Link
            href="/"
            className="text-sm text-zinc-500 underline underline-offset-4 hover:text-zinc-900 dark:hover:text-white"
          >
            Back to all parts
          </Link>
        </motion.div>
      </div>
    );
  }

  const { record, related } = data;
  const description = record.sheets
    .flatMap((s) => s.rows.flatMap((r) => r.cells))
    .find((c) => c.canonical === "description")?.value;

  function selectCell(cellId: string, opts?: { auto?: boolean }) {
    setSelectedCellId(cellId);
    // On small screens a clicked source opens the record; the automatic first-source highlight
    // must not hide the answer that just arrived.
    if (!opts?.auto) setView("record");
  }

  return (
    <div className={shell}>
      <div aria-hidden className={backdrop} />
      <motion.div
        className="flex flex-wrap items-end justify-between gap-3"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="flex min-w-0 flex-col gap-1">
          <Link
            href="/"
            className="group inline-flex w-fit items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            <ArrowLeft className="size-4 transition-transform group-hover:-translate-x-0.5" aria-hidden /> All
            parts
          </Link>
          <h1 className="flex flex-wrap items-baseline gap-x-3 text-2xl font-semibold tracking-tight sm:text-3xl">
            <span className="font-mono">{record.display_part_number}</span>
            {description ? <span className="text-zinc-500">{description}</span> : null}
          </h1>
          {related.length ? (
            <p className="text-xs text-zinc-500">
              Related part numbers:{" "}
              {related.map((r) => (
                <Link key={r} href={`/parts/${encodeURIComponent(r)}`} className="mr-2 font-mono underline">
                  {r}
                </Link>
              ))}
            </p>
          ) : null}
        </div>
        <SourceBadges sources={record.sources} />
      </motion.div>

      <AnimatedTabs<View>
        label="View"
        variant="segment"
        className="lg:hidden"
        value={view}
        onChange={setView}
        tabs={[
          { id: "ask", label: "Ask", icon: <MessageSquareText className="size-4" aria-hidden /> },
          { id: "record", label: "Record", icon: <Table2 className="size-4" aria-hidden /> },
        ]}
      />

      <motion.div
        className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:grid-rows-[minmax(0,1fr)]"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
      >
        <RecordViewer
          record={record}
          selectedCellId={selectedCellId}
          className={cn("h-[72dvh] lg:h-auto", view === "record" ? "flex" : "hidden lg:flex")}
        />
        <ChatPanel
          partNumber={record.part_key}
          selectedCellId={selectedCellId}
          onSelectCell={selectCell}
          className={cn("h-[76dvh] lg:h-auto", view === "ask" ? "flex" : "hidden lg:flex")}
        />
      </motion.div>
    </div>
  );
}

export function WorkspaceSkeleton() {
  return (
    <div className={shell} aria-busy="true" aria-label="Loading part">
      <div className="h-14 w-72 animate-pulse rounded-xl bg-zinc-200/70 dark:bg-white/5" />
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <div className="h-96 animate-pulse rounded-2xl bg-zinc-200/60 lg:h-auto dark:bg-white/5" />
        <div className="h-96 animate-pulse rounded-2xl bg-zinc-200/60 lg:h-auto dark:bg-white/5" />
      </div>
    </div>
  );
}
