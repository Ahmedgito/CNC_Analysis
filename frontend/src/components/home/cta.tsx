"use client";

import { Search } from "lucide-react";
import { motion } from "motion/react";
import { useResolvedTheme } from "@/lib/theme";
import { useCommandPalette } from "../site/command-palette";
import { GridBeam } from "../ui/grid-beam";
import { Kbd } from "../ui/kbd";

export function Cta() {
  const palette = useCommandPalette();
  const theme = useResolvedTheme();
  return (
    <section className="px-4 pt-10 pb-24 sm:px-6">
      <motion.div
        className="mx-auto max-w-5xl"
        initial={{ opacity: 0, y: 24, scale: 0.98 }}
        whileInView={{ opacity: 1, y: 0, scale: 1 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      >
        <GridBeam
          rows={3}
          cols={8}
          theme={theme}
          strength={1.2}
          className="rounded-3xl border border-zinc-200 bg-white dark:border-white/10 dark:bg-zinc-900/70"
          dividerClassName="text-zinc-200 dark:text-white/[0.06]"
        >
          <div className="flex flex-col items-center gap-5 px-6 py-16 text-center">
            <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
              Pick a part. Ask anything. Check every source.
            </h2>
            <p className="max-w-xl text-zinc-600 dark:text-zinc-400">
              Material, stock, operations, tools, tolerances, cycle times: answered from the record, or
              honestly marked as missing.
            </p>
            <motion.button
              type="button"
              onClick={palette.open}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.97 }}
              className="inline-flex h-12 items-center gap-3 rounded-2xl bg-zinc-900 px-6 font-medium text-white shadow-lg shadow-cyan-950/10 transition-colors hover:bg-cyan-600 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:bg-white dark:text-zinc-900 dark:hover:bg-cyan-300"
            >
              <Search className="size-4.5" aria-hidden /> Find a part
              <span className="inline-flex gap-0.5 opacity-80">
                <Kbd className="border-white/20 bg-white/10 text-white dark:border-zinc-300 dark:bg-zinc-100 dark:text-zinc-600">
                  Ctrl
                </Kbd>
                <Kbd className="border-white/20 bg-white/10 text-white dark:border-zinc-300 dark:bg-zinc-100 dark:text-zinc-600">
                  K
                </Kbd>
              </span>
            </motion.button>
          </div>
        </GridBeam>
      </motion.div>
    </section>
  );
}
