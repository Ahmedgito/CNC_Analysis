import { Kbd } from "../ui/kbd";
import { Logo } from "./logo";

export function Footer() {
  return (
    <footer className="border-t border-zinc-200 dark:border-white/10">
      <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-4 px-4 py-8 text-sm text-zinc-500 sm:flex-row sm:items-center sm:px-6">
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <p className="font-medium text-zinc-800 dark:text-zinc-200">CNC Part Analyzer</p>
            <p className="text-xs">
              SPEC&apos;26 · Answers only from your files, with the cell they came from.
            </p>
          </div>
        </div>
        <p className="inline-flex items-center gap-1.5 text-xs">
          Press <Kbd>Ctrl</Kbd>
          <Kbd>K</Kbd> anywhere to find a part
        </p>
      </div>
    </footer>
  );
}
