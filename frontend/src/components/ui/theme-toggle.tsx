"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { applyMode, type ThemeMode, useMounted, useThemeMode } from "@/lib/theme";
import { cn } from "@/lib/cn";

const NEXT: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
const ICON = { light: Sun, dark: Moon, system: Monitor } as const;
const LABEL = { light: "Light theme", dark: "Dark theme", system: "System theme" } as const;

export function ThemeToggle({ className }: { className?: string }) {
  const mounted = useMounted();
  const mode = useThemeMode();
  const Icon = ICON[mode];
  return (
    <button
      type="button"
      onClick={() => applyMode(NEXT[mode])}
      aria-label={mounted ? `${LABEL[mode]}. Switch to ${LABEL[NEXT[mode]].toLowerCase()}` : "Theme"}
      title={mounted ? LABEL[mode] : undefined}
      className={cn(
        "relative grid size-9 place-items-center overflow-hidden rounded-full text-zinc-600 transition hover:bg-zinc-900/5 hover:text-zinc-900 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white",
        className,
      )}
    >
      {mounted ? (
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={mode}
            initial={{ y: 14, opacity: 0, rotate: -60 }}
            animate={{ y: 0, opacity: 1, rotate: 0 }}
            exit={{ y: -14, opacity: 0, rotate: 60 }}
            transition={{ type: "spring", stiffness: 400, damping: 26 }}
          >
            <Icon className="size-4.5" aria-hidden />
          </motion.span>
        </AnimatePresence>
      ) : (
        <span className="size-4.5" />
      )}
    </button>
  );
}
