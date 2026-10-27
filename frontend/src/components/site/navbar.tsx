"use client";

/**
 * Floating glass navbar: full width at the top of the page, tightens into a centred pill once
 * the page scrolls. In the style of 21st.dev preetsuthar17/navbar-1 and morphing-island-navbar.
 */

import { Search } from "lucide-react";
import { motion, useMotionValueEvent, useScroll } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/cn";
import { Kbd } from "../ui/kbd";
import { MotionToggle } from "../ui/motion-toggle";
import { ThemeToggle } from "../ui/theme-toggle";
import { ApiStatus } from "./api-status";
import { useCommandPalette } from "./command-palette";
import { Logo } from "./logo";

const LINKS = [
  { href: "/#parts", label: "Parts" },
  { href: "/#how", label: "How it works" },
  { href: "/#trust", label: "Trust" },
];

export function Navbar() {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 24));
  const palette = useCommandPalette();

  return (
    <header className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center px-3 pt-3">
      <motion.nav
        aria-label="Main"
        initial={{ y: -24, opacity: 0, maxWidth: 1280 }}
        animate={{
          y: 0,
          opacity: 1,
          maxWidth: scrolled ? 920 : 1280,
        }}
        transition={{ type: "spring", stiffness: 220, damping: 28 }}
        className={cn(
          "pointer-events-auto flex h-14 w-full items-center gap-2 rounded-2xl border px-3 transition-[background-color,border-color,box-shadow] duration-300 sm:gap-4 sm:px-4",
          scrolled
            ? "border-zinc-200/80 bg-white/75 shadow-lg shadow-zinc-950/5 backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/70 dark:shadow-black/30"
            : "border-transparent bg-transparent",
        )}
      >
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5 rounded-lg font-semibold tracking-tight focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none"
        >
          <Logo />
          <span className="hidden sm:inline">CNC Part Analyzer</span>
        </Link>

        <ul className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                className="rounded-lg px-3 py-1.5 text-sm text-zinc-600 transition hover:bg-zinc-900/5 hover:text-zinc-900 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
              >
                {l.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          <button
            type="button"
            onClick={palette.open}
            className="group inline-flex h-9 items-center gap-2 rounded-xl border border-zinc-200 bg-white/70 px-2.5 text-sm text-zinc-500 transition hover:border-cyan-400/60 hover:text-zinc-800 focus-visible:ring-2 focus-visible:ring-cyan-500/60 focus-visible:outline-none sm:w-56 sm:px-3 dark:border-white/10 dark:bg-white/5 dark:hover:text-zinc-200"
          >
            <Search className="size-4 transition group-hover:text-cyan-500" aria-hidden />
            <span className="hidden sm:inline">Find a part…</span>
            <span className="sr-only sm:hidden">Find a part</span>
            <span className="ml-auto hidden items-center gap-0.5 sm:inline-flex">
              <Kbd>Ctrl</Kbd>
              <Kbd>K</Kbd>
            </span>
          </button>
          <ApiStatus className="hidden sm:inline-flex" />
          <MotionToggle />
          <ThemeToggle />
        </div>
      </motion.nav>
    </header>
  );
}
