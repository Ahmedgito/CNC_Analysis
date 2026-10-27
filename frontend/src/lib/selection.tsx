"use client";

/**
 * Linked selection across sources. Selecting any fact (a chip, a cross-check side, a drawing
 * callout, a spreadsheet cell, a model face) also marks the facts that state the same field in
 * the other files, found through the record's cross-checks. The primary fact pulses amber; its
 * counterparts get a softer outline in their own views, so the spreadsheet, the drawing and the
 * model always show the same thing at once.
 */

import { createContext, type ReactNode, useContext, useMemo } from "react";
import type { CrossCheck } from "@/lib/api/schemas";

export type Counterparts = { field: string; label: string; ids: string[] };

/** The cross-check field a fact takes part in, and every fact id on every side of it. */
export function counterparts(checks: CrossCheck[], factId: string | null | undefined): Counterparts | null {
  if (!factId) return null;
  for (const c of checks) {
    const ids = new Set([...c.excel, ...c.pdf, ...c.iges, ...c.sides.flatMap((s) => s.facts)]);
    if (ids.has(factId)) {
      ids.delete(factId);
      return { field: c.field, label: c.label, ids: [...ids] };
    }
  }
  return null;
}

type Selection = {
  primary: string | null;
  related: ReadonlySet<string>;
  field: string | null;
  isRelated: (factId: string) => boolean;
};

const EMPTY: Selection = { primary: null, related: new Set(), field: null, isRelated: () => false };
const SelectionContext = createContext<Selection>(EMPTY);

export function FactSelectionProvider({
  primary,
  checks,
  children,
}: {
  primary: string | null;
  checks: CrossCheck[];
  children: ReactNode;
}) {
  const value = useMemo<Selection>(() => {
    const cp = counterparts(checks, primary);
    const related = new Set(cp?.ids ?? []);
    return { primary, related, field: cp?.field ?? null, isRelated: (id) => related.has(id) };
  }, [primary, checks]);
  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useFactSelection() {
  return useContext(SelectionContext);
}
