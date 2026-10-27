"use client";

import { Bot, Calculator, FileSpreadsheet, Hash, MessageSquareQuote, ShieldCheck } from "lucide-react";
import { motion, useScroll, useSpring } from "motion/react";
import { useRef } from "react";
import { SectionHeading } from "./section-heading";

const STEPS = [
  {
    Icon: Hash,
    title: "Resolve the part",
    body: "2280, “2280”, 2280.0 and “ 2280 ” all become one key. 2280-A stays separate and is suggested.",
  },
  {
    Icon: FileSpreadsheet,
    title: "Load the record",
    body: "Every value keeps its file, sheet and cell, whatever the workbook’s layout or header names.",
  },
  {
    Icon: Bot,
    title: "Ask the model",
    body: "Claude, with Groq as fallback, returns structured JSON that must cite the cells and drawing callouts it used.",
  },
  {
    Icon: ShieldCheck,
    title: "Verify every citation",
    body: "Each cited value is compared with the stored cell. Anything that doesn’t match is dropped.",
  },
  {
    Icon: Calculator,
    title: "Compute in code",
    body: "Totals and unit conversions run in Python, with the working shown. The model never does arithmetic.",
  },
  {
    Icon: MessageSquareQuote,
    title: "Answer with sources",
    body: "A short answer, source chips that open the cell, and a clear “not in the files” when it isn’t.",
  },
];

export function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 80%", "end 55%"] });
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 30 });

  return (
    <section id="how" aria-labelledby="how-title" className="scroll-mt-24 px-4 py-20 sm:px-6">
      <SectionHeading
        id="how-title"
        eyebrow="How an answer is made"
        title="Six steps from question to cited answer"
      >
        The live progress you see while asking is these same steps, streamed from the server.
      </SectionHeading>

      <div ref={ref} className="relative mx-auto max-w-6xl">
        {/* Scroll-linked rail on large screens. */}
        <span
          aria-hidden
          className="absolute top-0 -left-4 hidden h-full w-px bg-zinc-200 lg:block dark:bg-white/10"
        />
        <motion.span
          aria-hidden
          style={{ scaleY: progress }}
          className="absolute top-0 -left-4 hidden h-full w-px origin-top bg-gradient-to-b from-cyan-400 via-sky-500 to-teal-400 lg:block"
        />
        <ol className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {STEPS.map(({ Icon, title, body }, i) => (
            <motion.li
              key={title}
              className="group relative flex gap-4 rounded-2xl border border-zinc-200 bg-white p-5 transition-colors hover:border-cyan-400/50 dark:border-white/10 dark:bg-zinc-900/70"
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.6, delay: (i % 3) * 0.1, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="flex flex-col items-center gap-2">
                <span className="relative grid size-11 place-items-center rounded-xl bg-zinc-900 text-white dark:bg-white dark:text-zinc-900">
                  <Icon className="size-5" aria-hidden />
                  <motion.span
                    aria-hidden
                    className="absolute inset-0 rounded-xl ring-2 ring-cyan-400"
                    initial={{ opacity: 0, scale: 0.8 }}
                    whileInView={{ opacity: [0, 1, 0], scale: [0.8, 1.25, 1.4] }}
                    viewport={{ once: true }}
                    transition={{ duration: 1.2, delay: 0.3 + i * 0.12 }}
                  />
                </span>
                <span aria-hidden className="font-mono text-[11px] text-zinc-400">{`0${i + 1}`}</span>
              </div>
              <div>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{body}</p>
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
