"use client";

import { Calculator, Cog, Gauge, Layers, Ruler, ShieldQuestion, Timer, Wrench } from "lucide-react";
import { Marquee } from "../ui/marquee";

const ROW_1 = [
  { Icon: Layers, q: "What material is 2280 made of?", tag: "SS304" },
  { Icon: Ruler, q: "What is the raw stock size?", tag: "Ø125 x 25" },
  { Icon: Cog, q: "List the operations in order", tag: "Op 10 → 30" },
  { Icon: Calculator, q: "Total setup time across operations?", tag: "5 + 3 + 4 = 12 min" },
  { Icon: Wrench, q: "Which tools are used?", tag: "CNMG 120408" },
];
const ROW_2 = [
  { Icon: Gauge, q: "What general tolerance applies?", tag: "±0.1 mm" },
  { Icon: Timer, q: "What is the cycle time?", tag: "28 min" },
  { Icon: ShieldQuestion, q: "What is the unit price?", tag: "Not in the files", honest: true },
  { Icon: Ruler, q: "Stock diameter in inches?", tag: "4.9213 in" },
  { Icon: ShieldQuestion, q: "Who is the customer?", tag: "Not in the files", honest: true },
];

function Pill({ Icon, q, tag, honest }: (typeof ROW_2)[number]) {
  return (
    <div className="flex shrink-0 items-center gap-3 rounded-2xl border border-zinc-200 bg-white px-4 py-3 shadow-sm dark:border-white/10 dark:bg-zinc-900">
      <span className="grid size-8 place-items-center rounded-lg bg-zinc-100 text-zinc-500 dark:bg-white/5 dark:text-zinc-400">
        <Icon className="size-4" aria-hidden />
      </span>
      <span className="text-sm whitespace-nowrap">{q}</span>
      <span
        className={
          honest
            ? "rounded-full bg-amber-100 px-2 py-0.5 font-mono text-[11px] whitespace-nowrap text-amber-800 dark:bg-amber-400/10 dark:text-amber-300"
            : "rounded-full bg-cyan-50 px-2 py-0.5 font-mono text-[11px] whitespace-nowrap text-cyan-800 dark:bg-cyan-400/10 dark:text-cyan-300"
        }
      >
        {tag}
      </span>
    </div>
  );
}

export function QuestionMarquee() {
  return (
    <div className="flex flex-col gap-3 py-6">
      <Marquee label="Example questions and answers">
        {ROW_1.map((p) => (
          <Pill key={p.q} {...p} />
        ))}
      </Marquee>
      <Marquee label="More example questions" reverse speed={1.8}>
        {ROW_2.map((p) => (
          <Pill key={p.q} {...p} />
        ))}
      </Marquee>
    </div>
  );
}
