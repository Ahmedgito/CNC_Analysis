"use client";

import { ArrowLeftRight, Box, FileText } from "lucide-react";
import { motion } from "motion/react";
import type { PartRecord } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { useFactSelection } from "@/lib/selection";
import { CrossCheckList } from "./cross-checks";
import { DrawingViewer } from "./drawing-viewer";
import { ModelPanel } from "./model/model-panel";

/**
 * The drawing and the 3D model side by side, with the three-way cross-check underneath. One
 * selection drives all of them: clicking "Outer diameter" lights up the spreadsheet value, the
 * drawing callout and the model face together.
 */
export function CompareView({
  record,
  onSelectFact,
  className,
}: {
  record: PartRecord;
  onSelectFact: (factId: string) => void;
  className?: string;
}) {
  const { field, primary } = useFactSelection();
  const drawing = record.drawings.find((d) => d.readable) ?? record.drawings[0];
  const model = record.models[0];
  const check = record.cross_checks.find((c) => c.field === field);
  return (
    <section
      aria-label="Compare drawing and model"
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-white/10 dark:bg-zinc-900/70",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-2.5 dark:border-white/10">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <ArrowLeftRight className="size-4 text-cyan-500" aria-hidden /> Compare the files
        </p>
        <p className="text-xs text-zinc-500">
          {check ? (
            <motion.span key={check.field} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}>
              Showing <span className="font-medium text-zinc-700 dark:text-zinc-300">{check.label}</span> in
              every file
            </motion.span>
          ) : (
            "Select a value in any file to see it in the others"
          )}
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-2">
            <h3 className="flex items-center gap-1.5 text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase">
              <FileText className="size-3.5 text-rose-500" aria-hidden /> {drawing?.file ?? "No drawing"}
            </h3>
            {drawing ? (
              <DrawingViewer
                partNumber={record.part_key}
                drawing={drawing}
                selected={primary}
                onSelect={onSelectFact}
              />
            ) : (
              <p className="text-sm text-zinc-500">This part has no PDF drawing.</p>
            )}
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <h3 className="flex items-center gap-1.5 text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase">
              <Box className="size-3.5 text-indigo-500" aria-hidden /> {model?.file ?? "No 3D model"}
            </h3>
            {model ? (
              <ModelPanel
                partNumber={record.part_key}
                model={model}
                checks={record.cross_checks}
                onSelect={onSelectFact}
              />
            ) : (
              <p className="text-sm text-zinc-500">This part has no IGES model.</p>
            )}
          </div>
        </div>
        {record.cross_checks.length ? (
          <div className="mt-6 flex flex-col gap-2">
            <h3 className="text-[11px] font-medium tracking-[0.15em] text-zinc-500 uppercase">
              Spreadsheet · drawing · model
            </h3>
            <CrossCheckList checks={record.cross_checks} onSelect={onSelectFact} filterable />
          </div>
        ) : null}
      </div>
    </section>
  );
}
