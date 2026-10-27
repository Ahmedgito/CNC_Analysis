"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Search } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { listParts } from "@/lib/api/client";
import { useResolvedTheme } from "@/lib/theme";
import { BlurText } from "../ui/blur-text";
import { BorderBeam } from "../ui/border-beam";
import { GridBeam } from "../ui/grid-beam";
import { NumberTicker } from "../ui/number-ticker";
import { RotatingPlaceholder } from "../ui/ai-chat-input";
import { TextShimmer } from "../ui/text-shimmer";

const HINTS = [
  "Enter a part number, e.g. 2280",
  "Search by name: bushing",
  "Try 2283, the bronze-or-brass bushing",
  "Search: flange",
  "Try 2284, which only has an Excel record",
];

const ease = [0.16, 1, 0.3, 1] as const;

export function Hero() {
  const theme = useResolvedTheme();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [searching, setSearching] = useState(false);
  const { data } = useQuery({ queryKey: ["parts", ""], queryFn: () => listParts() });
  const parts = data?.parts ?? [];
  const files = new Set(parts.flatMap((p) => p.files));

  async function open(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    try {
      const exact = parts.find((p) => p.part_key.toUpperCase() === q.toUpperCase());
      if (exact) return router.push(`/parts/${encodeURIComponent(exact.part_key)}`);
      const res = await listParts(q);
      // One match by description opens it; otherwise the part page resolves and suggests.
      const target = res.parts.length === 1 ? res.parts[0].part_key : q;
      router.push(`/parts/${encodeURIComponent(target)}`);
    } catch {
      router.push(`/parts/${encodeURIComponent(q)}`);
    } finally {
      setSearching(false);
    }
  }

  return (
    <section className="relative isolate overflow-hidden pt-32 pb-20 sm:pt-40 sm:pb-28">
      <GridBeam
        rows={7}
        cols={12}
        theme={theme}
        duration={3.6}
        className="absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_75%_65%_at_50%_42%,black_35%,transparent_100%)]"
        dividerClassName="text-zinc-300/70 dark:text-white/[0.07]"
      />
      {/* Slow ambient glow behind the headline. */}
      <motion.div
        aria-hidden
        className="absolute top-24 left-1/2 -z-10 h-80 w-[min(56rem,90vw)] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(34_211_238/0.20),transparent)] blur-2xl dark:bg-[radial-gradient(closest-side,rgb(34_211_238/0.16),transparent)]"
        animate={{ scale: [1, 1.08, 1], opacity: [0.8, 1, 0.8] }}
        transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="mx-auto flex max-w-5xl flex-col items-center px-4 text-center sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease }}
        >
          <BorderBeam
            className="rounded-full"
            surfaceClassName="rounded-full bg-white/85 px-3.5 py-1.5 backdrop-blur dark:bg-zinc-950/85"
            duration={5}
          >
            <span className="flex items-center gap-2 text-xs font-medium">
              <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
              <TextShimmer>Level 2 live: Excel records + PDF drawings, cross-checked</TextShimmer>
              <span className="text-zinc-400">·</span>
              <span className="text-zinc-500">IGES next</span>
            </span>
          </BorderBeam>
        </motion.div>

        <h1 className="mt-7 text-4xl font-semibold tracking-tight text-balance sm:text-6xl lg:text-7xl">
          <BlurText text="Every answer," delay={0.15} />{" "}
          <BlurText
            text="traced to its source."
            delay={0.35}
            wordClassName="bg-gradient-to-br from-cyan-500 via-sky-500 to-teal-400 bg-clip-text pb-1 text-transparent dark:from-cyan-300 dark:via-sky-400 dark:to-teal-300"
          />
        </h1>

        <motion.p
          className="mt-6 max-w-2xl text-base text-pretty text-zinc-600 sm:text-lg dark:text-zinc-400"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.6, ease }}
        >
          Type a part number, ask about material, sizes, drawing notes, operations or times, and get a plain
          answer linked to the exact spreadsheet cell or drawing callout. Where the two files disagree, it
          shows both. If the files don&apos;t say, it tells you so.
        </motion.p>

        <motion.form
          role="search"
          onSubmit={open}
          className="mt-10 w-full max-w-2xl"
          initial={{ opacity: 0, y: 16, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.75, ease }}
        >
          <BorderBeam
            active={focused || searching}
            className="rounded-2xl shadow-xl shadow-cyan-950/5 dark:shadow-black/40"
            surfaceClassName="flex items-center gap-3 bg-white/90 p-2 pl-4 backdrop-blur dark:bg-zinc-900/90"
          >
            <Search className="size-5 shrink-0 text-zinc-400" aria-hidden />
            <label htmlFor="hero-search" className="sr-only">
              Part number or description
            </label>
            <div className="relative h-11 flex-1">
              <input
                id="hero-search"
                autoComplete="off"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                className="relative z-1 h-full w-full bg-transparent text-base outline-none sm:text-lg"
              />
              <RotatingPlaceholder
                items={HINTS}
                paused={focused || query.length > 0}
                className="text-base sm:text-lg"
              />
            </div>
            <motion.button
              type="submit"
              disabled={!query.trim() || searching}
              whileTap={{ scale: 0.96 }}
              className="inline-flex h-11 items-center gap-1.5 rounded-xl bg-zinc-900 px-5 text-sm font-medium text-white transition hover:bg-cyan-600 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none disabled:opacity-40 dark:bg-white dark:text-zinc-900 dark:hover:bg-cyan-300"
            >
              Open <ArrowRight className="size-4" aria-hidden />
            </motion.button>
          </BorderBeam>
        </motion.form>

        {parts.length ? (
          <motion.div
            className="mt-5 flex flex-wrap items-center justify-center gap-2 text-sm"
            initial="hidden"
            animate="show"
            variants={{ show: { transition: { staggerChildren: 0.06, delayChildren: 0.95 } } }}
          >
            <span className="text-zinc-500">Try</span>
            {parts.slice(0, 6).map((p) => (
              <motion.span
                key={p.part_key}
                variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
              >
                <Link
                  href={`/parts/${encodeURIComponent(p.part_key)}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-white/70 px-3 py-1 backdrop-blur transition hover:-translate-y-0.5 hover:border-cyan-400/60 hover:text-cyan-700 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:border-white/10 dark:bg-white/5 dark:hover:text-cyan-300"
                >
                  <span className="font-mono font-semibold">{p.display_part_number}</span>
                  {p.description ? <span className="text-zinc-500">{p.description}</span> : null}
                </Link>
              </motion.span>
            ))}
          </motion.div>
        ) : null}

        <motion.dl
          className="mt-14 grid w-full max-w-3xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-200 sm:grid-cols-4 dark:border-white/10 dark:bg-white/10"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 1.05, ease }}
        >
          <Stat label="Parts indexed" value={parts.length} />
          <Stat label="Workbooks" value={files.size} />
          <Stat label="Sources live" value={1} suffix=" / 3" />
          <Stat label="Unverified citations shown" value={0} />
        </motion.dl>
      </div>
    </section>
  );
}

function Stat({ label, value, suffix }: { label: string; value: number; suffix?: string }) {
  return (
    <div className="flex flex-col gap-1 bg-white/80 px-4 py-4 backdrop-blur dark:bg-zinc-950/80">
      <dt className="order-2 text-[11px] font-medium tracking-wide text-zinc-500 uppercase">{label}</dt>
      <dd className="order-1 font-mono text-2xl font-semibold sm:text-3xl">
        <NumberTicker value={value} suffix={suffix} />
      </dd>
    </div>
  );
}
