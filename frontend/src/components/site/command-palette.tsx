"use client";

/**
 * Global command palette (Ctrl+K / Cmd+K): jump to any part by number or description.
 * A modal combobox: arrow keys move, Enter opens, Escape closes, focus returns to the trigger.
 */

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CornerDownLeft, Hash, Loader2, Search } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { listParts } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { Kbd } from "../ui/kbd";
import { SourceBadges } from "../source-badges";

const Ctx = createContext<{ open: () => void } | null>(null);

export function useCommandPalette() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCommandPalette must be used inside CommandPaletteProvider");
  return ctx;
}

export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const returnFocus = useRef<HTMLElement | null>(null);

  const open = useCallback(() => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    setOpen(true);
  }, []);
  const close = useCallback(() => {
    setOpen(false);
    window.setTimeout(() => returnFocus.current?.focus?.(), 0);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) close();
        else open();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, open, close]);

  const value = useMemo(() => ({ open }), [open]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <AnimatePresence>{isOpen ? <Palette onClose={close} /> : null}</AnimatePresence>
    </Ctx.Provider>
  );
}

function Palette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const deferred = useDeferredValue(query.trim());
  const { data, isFetching, isError } = useQuery({
    queryKey: ["parts", deferred],
    queryFn: () => listParts(deferred || undefined),
    placeholderData: (prev) => prev,
  });
  const parts = data?.parts ?? [];
  const exact = parts.some((p) => p.part_key.toUpperCase() === deferred.toUpperCase());
  const showOpenAnyway = deferred.length > 0 && !exact && /\d/.test(deferred);
  const count = parts.length + (showOpenAnyway ? 1 : 0);
  const activeIndex = count ? Math.min(active, count - 1) : 0;

  function go(partKey: string) {
    onClose();
    router.push(`/parts/${encodeURIComponent(partKey)}`);
  }
  function choose(i: number) {
    if (i < parts.length) go(parts[i].part_key);
    else if (showOpenAnyway) go(deferred);
  }

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className="absolute inset-0 bg-zinc-950/40 backdrop-blur-sm" onClick={onClose} aria-hidden />
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Find a part"
        className="relative w-full max-w-xl overflow-hidden rounded-2xl border border-zinc-200 bg-white/95 shadow-2xl shadow-black/20 backdrop-blur-xl dark:border-white/10 dark:bg-zinc-900/95"
        initial={{ opacity: 0, scale: 0.96, y: -12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: -8 }}
        transition={{ type: "spring", stiffness: 420, damping: 32 }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          } else if (e.key === "Tab") {
            e.preventDefault(); // keep focus in the dialog; the input is the only stop
          }
        }}
      >
        <div className="flex items-center gap-3 border-b border-zinc-200 px-4 dark:border-white/10">
          {isFetching ? (
            <Loader2 className="size-4.5 animate-spin text-cyan-500" aria-hidden />
          ) : (
            <Search className="size-4.5 text-zinc-400" aria-hidden />
          )}
          <input
            autoFocus
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={count ? `${listId}-${activeIndex}` : undefined}
            aria-label="Part number or description"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((i) => (count ? (i + 1) % count : 0));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((i) => (count ? (i - 1 + count) % count : 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                choose(activeIndex);
              }
            }}
            placeholder="Jump to a part: 2280, bushing, flange…"
            className="h-14 flex-1 bg-transparent text-base outline-none placeholder:text-zinc-400"
          />
          <Kbd>Esc</Kbd>
        </div>

        <ul id={listId} role="listbox" aria-label="Parts" className="max-h-[50vh] overflow-y-auto p-2">
          {isError ? (
            <li className="px-3 py-6 text-center text-sm text-red-600 dark:text-red-400">
              Can&apos;t reach the API. Is the backend running?
            </li>
          ) : count === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-zinc-500">
              {deferred ? "No part matches that." : "No parts ingested yet."}
            </li>
          ) : null}
          {parts.map((p, i) => (
            <Option
              key={p.part_key}
              id={`${listId}-${i}`}
              active={i === activeIndex}
              onHover={() => setActive(i)}
              onChoose={() => choose(i)}
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-zinc-100 font-mono text-[11px] text-zinc-500 dark:bg-white/5">
                Ø
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-mono text-sm font-semibold">{p.display_part_number}</span>
                <span className="block truncate text-xs text-zinc-500">
                  {p.description ?? "No description"}
                </span>
              </span>
              <SourceBadges sources={p.sources} compact />
            </Option>
          ))}
          {showOpenAnyway ? (
            <Option
              id={`${listId}-${parts.length}`}
              active={activeIndex === parts.length}
              onHover={() => setActive(parts.length)}
              onChoose={() => choose(parts.length)}
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-zinc-100 dark:bg-white/5">
                <Hash className="size-4 text-zinc-500" aria-hidden />
              </span>
              <span className="flex-1 text-sm">
                Open part <span className="font-mono font-semibold">{deferred}</span> anyway
                <span className="block text-xs text-zinc-500">The part page suggests close matches</span>
              </span>
            </Option>
          ) : null}
        </ul>

        <div className="flex items-center justify-between border-t border-zinc-200 px-4 py-2 text-[11px] text-zinc-500 dark:border-white/10">
          <span className="inline-flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> to move
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Kbd>
              <CornerDownLeft className="size-3" aria-hidden />
            </Kbd>
            to open
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
}

function Option({
  id,
  active,
  onHover,
  onChoose,
  children,
}: {
  id: string;
  active: boolean;
  onHover: () => void;
  onChoose: () => void;
  children: ReactNode;
}) {
  return (
    <li
      id={id}
      role="option"
      aria-selected={active}
      onPointerMove={onHover}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onChoose}
      className="relative flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5"
    >
      {active ? (
        <motion.span
          layoutId="palette-active"
          aria-hidden
          className="absolute inset-0 rounded-xl bg-zinc-100 ring-1 ring-cyan-500/30 dark:bg-white/5"
          transition={{ type: "spring", stiffness: 500, damping: 38 }}
        />
      ) : null}
      <span className="relative flex min-w-0 flex-1 items-center gap-3">{children}</span>
      <ArrowRight
        className={cn("relative size-4 shrink-0 transition", active ? "text-cyan-500" : "text-transparent")}
        aria-hidden
      />
    </li>
  );
}
