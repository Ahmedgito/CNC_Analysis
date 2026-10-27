"use client";

import { AlertCircle, FileDown, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { ApiError, downloadReport } from "@/lib/api/client";
import { cn } from "@/lib/cn";

/**
 * Downloads the part report as PDF: every source file, the three-way cross-check, the full record,
 * drawings with their read regions, model features and, once a question has been asked, the
 * conversation with its verified sources.
 */
export function ReportButton({
  partNumber,
  conversationId,
}: {
  partNumber: string;
  conversationId?: string | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await downloadReport(partNumber, conversationId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not build the report. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const title = error
    ? `Report failed: ${error}`
    : conversationId
      ? "Download a PDF report of this part, including the questions asked here"
      : "Download a PDF report of this part: sources, cross-check, record, drawings and models";

  return (
    <button
      type="button"
      onClick={download}
      disabled={busy}
      aria-busy={busy}
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-wait",
        error
          ? "border-rose-300 text-rose-700 hover:border-rose-400 dark:border-rose-400/30 dark:text-rose-300"
          : "border-zinc-200 text-zinc-600 hover:border-cyan-400/60 hover:text-cyan-700 dark:border-white/10 dark:text-zinc-300 dark:hover:text-cyan-300",
      )}
    >
      {busy ? (
        <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
      ) : error ? (
        <AlertCircle className="size-3.5" aria-hidden />
      ) : (
        <FileDown className="size-3.5" aria-hidden />
      )}
      {busy ? "Building report…" : error ? "Retry report" : "Download report"}
    </button>
  );
}
