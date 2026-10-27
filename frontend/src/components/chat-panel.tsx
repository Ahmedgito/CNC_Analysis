"use client";

import {
  Calculator,
  Cog,
  Layers,
  MessageSquareText,
  Ruler,
  ShieldQuestion,
  Sparkles,
  Wrench,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { ApiError, askStream } from "@/lib/api/client";
import type { AskResult, StageEvent } from "@/lib/api/schemas";
import { cn } from "@/lib/cn";
import { AnswerCard } from "./answer-card";
import { AIChatInput } from "./ui/ai-chat-input";
import { BorderBeam } from "./ui/border-beam";
import { PipelineStepper } from "./workspace/pipeline-stepper";

type Turn = {
  id: number;
  question: string;
  stages: StageEvent[];
  result?: AskResult;
  error?: string;
};

const SUGGESTIONS = [
  { Icon: Layers, q: "What material is it made of?" },
  { Icon: Ruler, q: "What is the raw stock size?" },
  { Icon: Cog, q: "List the operations in order" },
  { Icon: Calculator, q: "What is the total setup time?" },
  { Icon: Wrench, q: "Which tools are used?" },
  { Icon: ShieldQuestion, q: "What is the unit price?" },
];

export function ChatPanel({
  partNumber,
  selectedCellId,
  onSelectCell,
  className,
}: {
  partNumber: string;
  selectedCellId?: string | null;
  onSelectCell?: (cellId: string) => void;
  className?: string;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  useEffect(() => {
    // Scroll only the thread, never the window.
    const el = scrollRef.current;
    el?.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns]);

  useEffect(() => () => abortRef.current?.abort(), []);

  function update(id: number, patch: (t: Turn) => Partial<Turn>) {
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)));
  }

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const id = nextId.current++;
    setTurns((prev) => [...prev, { id, question: q, stages: [] }]);
    setInput("");
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await askStream(partNumber, q, {
        conversationId,
        signal: controller.signal,
        onStage: (stage) => update(id, (t) => ({ stages: [...t.stages, stage] })),
      });
      if (result.conversation_id) setConversationId(result.conversation_id);
      update(id, () => ({ result }));
      const first = result.evidence[0];
      if (first) onSelectCell?.(first.cell_id);
    } catch (err) {
      const message =
        err instanceof DOMException && err.name === "AbortError"
          ? "Stopped."
          : err instanceof ApiError
            ? err.message
            : "Something went wrong. Please try again.";
      update(id, () => ({ error: message }));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  const asked = new Set(turns.map((t) => t.question));
  const remaining = SUGGESTIONS.map((s) => s.q).filter((q) => !asked.has(q));

  return (
    <section
      aria-label="Ask about this part"
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-white/10 dark:bg-zinc-900/70",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-2.5 dark:border-white/10">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <MessageSquareText className="size-4 text-cyan-500" aria-hidden /> Ask about part{" "}
          <span className="font-mono">{partNumber}</span>
        </p>
        {turns.length ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setTurns([]);
              setConversationId(null);
            }}
            className="rounded-lg px-2 py-1 text-xs text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-800 disabled:opacity-40 dark:hover:bg-white/5 dark:hover:text-zinc-200"
          >
            New conversation
          </button>
        ) : null}
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto p-4" aria-live="polite">
        {turns.length === 0 ? (
          <motion.div
            className="flex h-full flex-col justify-center gap-6 py-6"
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.06 } } }}
          >
            <motion.div
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              className="flex flex-col items-center gap-3 text-center"
            >
              <span className="relative grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-cyan-500 to-teal-400 text-white shadow-lg shadow-cyan-500/25">
                <Sparkles className="size-5" aria-hidden />
                <motion.span
                  aria-hidden
                  className="absolute inset-0 rounded-2xl ring-2 ring-cyan-400"
                  animate={{ scale: [1, 1.3], opacity: [0.6, 0] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              </span>
              <div>
                <p className="font-semibold">
                  Ask anything about part <span className="font-mono">{partNumber}</span>
                </p>
                <p className="mt-1 max-w-sm text-sm text-zinc-500">
                  Answers come only from its files, and each one links to the cells it used.
                </p>
              </div>
            </motion.div>
            <ul className="grid gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map(({ Icon, q }) => (
                <motion.li key={q} variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}>
                  <motion.button
                    type="button"
                    onClick={() => ask(q)}
                    whileHover={{ y: -2 }}
                    whileTap={{ scale: 0.98 }}
                    className="group flex w-full items-center gap-3 rounded-xl border border-zinc-200 bg-white px-3 py-2.5 text-left text-sm text-zinc-700 transition-colors hover:border-cyan-400/60 hover:bg-cyan-50/40 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:border-white/10 dark:bg-white/[0.02] dark:text-zinc-300 dark:hover:bg-cyan-400/5"
                  >
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-zinc-100 text-zinc-500 transition-colors group-hover:bg-cyan-500 group-hover:text-white dark:bg-white/5">
                      <Icon className="size-4" aria-hidden />
                    </span>
                    {q}
                  </motion.button>
                </motion.li>
              ))}
            </ul>
          </motion.div>
        ) : (
          <ol className="flex flex-col gap-6">
            <AnimatePresence initial={false}>
              {turns.map((t) => (
                <motion.li
                  key={t.id}
                  className="flex flex-col gap-2"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                >
                  <motion.p
                    initial={{ opacity: 0, x: 24, scale: 0.96 }}
                    animate={{ opacity: 1, x: 0, scale: 1 }}
                    transition={{ type: "spring", stiffness: 380, damping: 28 }}
                    className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-zinc-900 px-3.5 py-2 text-sm text-white shadow-sm dark:bg-white dark:text-zinc-900"
                  >
                    {t.question}
                  </motion.p>
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35, delay: 0.08, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <BorderBeam
                      active={!t.result && !t.error}
                      className="rounded-2xl rounded-bl-md"
                      surfaceClassName="rounded-[calc(1rem-1px)] rounded-bl-[calc(0.375rem-1px)] bg-white p-3.5 dark:bg-zinc-900"
                    >
                      <AnimatePresence mode="wait" initial={false}>
                        {t.result ? (
                          <motion.div key="answer" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                            <AnswerCard
                              result={t.result}
                              selectedCellId={selectedCellId}
                              onSelectCell={onSelectCell}
                            />
                          </motion.div>
                        ) : t.error ? (
                          <motion.p
                            key="error"
                            role="alert"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="text-sm text-red-700 dark:text-red-400"
                          >
                            {t.error}
                          </motion.p>
                        ) : (
                          <motion.div key="progress" exit={{ opacity: 0, transition: { duration: 0.15 } }}>
                            <PipelineStepper events={t.stages} />
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </BorderBeam>
                  </motion.div>
                </motion.li>
              ))}
            </AnimatePresence>
          </ol>
        )}
      </div>

      <div className="border-t border-zinc-200 p-3 dark:border-white/10">
        <AIChatInput
          id="question"
          value={input}
          onChange={setInput}
          onSubmit={(q) => void ask(q)}
          onStop={() => abortRef.current?.abort()}
          busy={busy}
          placeholders={[
            `Ask about part ${partNumber}…`,
            "What material is it made of?",
            "Total setup time across operations?",
            "Which machine runs it?",
            "Stock diameter in inches?",
          ]}
          focusedPlaceholder="Ask about material, sizes, operations, tools, times…"
          suggestions={remaining.slice(0, 4)}
        />
      </div>
    </section>
  );
}
