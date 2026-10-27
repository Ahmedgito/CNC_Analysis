"use client";

/**
 * AI chat input: springs open on focus, blur-in rotating placeholders, suggestion chips.
 * Source: 21st.dev, preetsuthar17/ai-chat-input (https://21st.dev/@preetsuthar17/components/ai-chat-input).
 * Adapted for this app: a real form (textarea, Enter to send, Shift+Enter for a new line), Send
 * morphs into Stop while an answer streams, the decorative attach/voice/search buttons are replaced
 * by working question suggestions, and a border beam runs while the pipeline is busy.
 */

import { ArrowUp, CornerDownLeft, Square } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { BorderBeam } from "./border-beam";

const letter = {
  initial: { opacity: 0, filter: "blur(12px)", y: 10 },
  animate: {
    opacity: 1,
    filter: "blur(0px)",
    y: 0,
    transition: {
      opacity: { duration: 0.25 },
      filter: { duration: 0.4 },
      y: { type: "spring" as const, stiffness: 80, damping: 20 },
    },
  },
  exit: {
    opacity: 0,
    filter: "blur(12px)",
    y: -10,
    transition: { opacity: { duration: 0.2 }, filter: { duration: 0.3 } },
  },
};

/** Cycles through hints with a letter-by-letter blur. Purely decorative (aria-hidden). */
export function RotatingPlaceholder({
  items,
  paused,
  className,
  interval = 3200,
}: {
  items: string[];
  paused: boolean;
  className?: string;
  interval?: number;
}) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (paused || items.length < 2) return;
    const id = window.setInterval(() => setIndex((i) => (i + 1) % items.length), interval);
    return () => window.clearInterval(id);
  }, [paused, items.length, interval]);

  const text = items[index % items.length] ?? "";
  return (
    <div aria-hidden className={cn("pointer-events-none absolute inset-0 flex items-center", className)}>
      <AnimatePresence mode="wait">
        {!paused ? (
          <motion.span
            key={text}
            className="truncate whitespace-nowrap text-zinc-400 select-none dark:text-zinc-500"
            initial="initial"
            animate="animate"
            exit="exit"
            variants={{
              animate: { transition: { staggerChildren: 0.018 } },
              exit: { transition: { staggerChildren: 0.01, staggerDirection: -1 } },
            }}
          >
            {text.split("").map((ch, i) => (
              <motion.span key={i} variants={letter} className="inline-block">
                {ch === " " ? " " : ch}
              </motion.span>
            ))}
          </motion.span>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

export function AIChatInput({
  id,
  value,
  onChange,
  onSubmit,
  onStop,
  busy = false,
  placeholders,
  focusedPlaceholder = "Ask a question…",
  suggestions = [],
  maxLength = 1000,
  label = "Question",
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onStop?: () => void;
  busy?: boolean;
  placeholders: string[];
  focusedPlaceholder?: string;
  suggestions?: string[];
  maxLength?: number;
  label?: string;
}) {
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const expanded = focused || value.length > 0;

  // Auto-grow the textarea up to ~6 lines.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !busy;

  return (
    <BorderBeam
      active={busy}
      className={cn(
        "rounded-3xl transition-shadow duration-300",
        expanded ? "shadow-xl shadow-cyan-950/5 dark:shadow-black/40" : "shadow-sm",
      )}
      surfaceClassName="rounded-[calc(1.5rem-1px)] bg-white dark:bg-zinc-900"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) onSubmit(value);
        }}
        onFocus={() => setFocused(true)}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false);
        }}
      >
        <motion.div layout transition={{ type: "spring", stiffness: 160, damping: 20 }}>
          <div className="flex items-end gap-2 p-2 pl-4">
            <label htmlFor={id} className="sr-only">
              {label}
            </label>
            <div className="relative flex-1 py-2">
              <textarea
                ref={textareaRef}
                id={id}
                rows={1}
                maxLength={maxLength}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (canSend) onSubmit(value);
                  }
                }}
                placeholder={focused ? focusedPlaceholder : ""}
                className="relative z-1 block max-h-40 w-full resize-none bg-transparent text-[0.95rem] leading-6 outline-none placeholder:text-zinc-400 dark:placeholder:text-zinc-500"
              />
              <RotatingPlaceholder items={placeholders} paused={expanded} />
            </div>
            <AnimatePresence mode="popLayout" initial={false}>
              {busy ? (
                <motion.button
                  key="stop"
                  type="button"
                  onClick={onStop}
                  aria-label="Stop"
                  initial={{ scale: 0.6, opacity: 0, rotate: -90 }}
                  animate={{ scale: 1, opacity: 1, rotate: 0 }}
                  exit={{ scale: 0.6, opacity: 0, rotate: 90 }}
                  className="grid size-10 shrink-0 place-items-center rounded-full border border-zinc-300 text-zinc-700 transition hover:bg-zinc-100 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                >
                  <Square className="size-3.5 fill-current" aria-hidden />
                </motion.button>
              ) : (
                <motion.button
                  key="send"
                  type="submit"
                  aria-label="Ask"
                  disabled={!canSend}
                  initial={{ scale: 0.6, opacity: 0, rotate: 90 }}
                  animate={{ scale: 1, opacity: 1, rotate: 0 }}
                  exit={{ scale: 0.6, opacity: 0, rotate: -90 }}
                  whileTap={{ scale: 0.9 }}
                  className="grid size-10 shrink-0 place-items-center rounded-full bg-zinc-900 text-white transition hover:bg-cyan-600 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none disabled:bg-zinc-200 disabled:text-zinc-400 dark:bg-white dark:text-zinc-900 dark:hover:bg-cyan-300 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-600"
                >
                  <ArrowUp className="size-4.5" aria-hidden />
                </motion.button>
              )}
            </AnimatePresence>
          </div>

          <AnimatePresence initial={false}>
            {expanded && !busy ? (
              <motion.div
                key="extras"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto", transition: { duration: 0.3, delay: 0.05 } }}
                exit={{ opacity: 0, height: 0, transition: { duration: 0.2 } }}
                className="overflow-hidden"
              >
                <div className="flex items-center gap-3 px-3 pb-3">
                  {suggestions.length ? (
                    <ul className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto [scrollbar-width:none]">
                      {suggestions.map((s, i) => (
                        <motion.li
                          key={s}
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0, transition: { delay: 0.05 + i * 0.035 } }}
                        >
                          <button
                            type="button"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => onSubmit(s)}
                            className="rounded-full bg-zinc-100 px-3 py-1 text-xs whitespace-nowrap text-zinc-700 transition hover:bg-cyan-50 hover:text-cyan-800 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-cyan-950 dark:hover:text-cyan-200"
                          >
                            {s}
                          </button>
                        </motion.li>
                      ))}
                    </ul>
                  ) : (
                    <span className="flex-1" />
                  )}
                  <span className="hidden shrink-0 items-center gap-1 text-[11px] text-zinc-400 sm:inline-flex">
                    <CornerDownLeft className="size-3" aria-hidden /> send · Shift+Enter new line
                  </span>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </motion.div>
      </form>
    </BorderBeam>
  );
}
