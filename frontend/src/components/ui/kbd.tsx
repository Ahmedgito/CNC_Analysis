import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded border border-zinc-300 bg-zinc-50 px-1 font-sans text-[10px] font-medium text-zinc-500 dark:border-white/15 dark:bg-white/5 dark:text-zinc-400",
        className,
      )}
    >
      {children}
    </kbd>
  );
}
