"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";

export function SectionHeading({
  eyebrow,
  title,
  children,
  id,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
  id?: string;
}) {
  return (
    <motion.div
      className="mx-auto mb-10 flex max-w-2xl flex-col items-center gap-3 text-center"
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
    >
      <p className="font-mono text-xs font-medium tracking-[0.2em] text-cyan-600 uppercase dark:text-cyan-400">
        {eyebrow}
      </p>
      <h2 id={id} className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h2>
      {children ? <p className="text-pretty text-zinc-600 dark:text-zinc-400">{children}</p> : null}
    </motion.div>
  );
}
