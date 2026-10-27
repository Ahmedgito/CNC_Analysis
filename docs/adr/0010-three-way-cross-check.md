---
status: accepted
date: 2026-10-27
---

# 0010 Three-way cross-check: pairwise verdicts, the odd one out, no majority vote

## Context

With a spreadsheet, a drawing and a 3D model, the same field (an outer diameter, a hole count)
can be stated up to three times. The brief asks to "cross-check the three sources and flag
anything that disagrees". It is tempting to take the majority as correct; that would silently
overrule a record that may be the right one (the drawing may be out of date, the model may have
been built from the drawing).

## Decision

- Reduce each field to statements (one per cell, callout or measured feature), in mm when the
  unit is known, and compare every pair of sources. The field's verdict is the worst pairwise
  verdict. The Level 2 spreadsheet-drawing rules stay authoritative for that pair.
- When two sources agree and the third differs, record `odd_one_out` and the exact `dissent` fact
  ids, and say so in plain words. Never pick a winner; every value stays cited.
- Equality is within 0.005 mm or 1e-4 of the value (inch values allow half a thousandth). A
  larger difference inside the drawing's general tolerance is `within_tolerance`, which asks for
  a look rather than claiming a match.
- Conventions are explicit verdicts, never silent matches: `equivalent_by_convention` for the
  Ra/RMS table and for a hole at the ISO 261 tap-drill size of a named thread; `consistent` when
  the part fits its raw stock; `not_modelled` for chamfers a model omits.
- Material, tolerance and finish remain two-way; the model side states that a model holds none.

## Consequences

2283's job card is named the odd one out on the OD, 3003's part card is the single dissenting
cell, and there are no false disagreements on any other field of the eight modelled parts (tested). The
UI can outline exactly the statements that differ. The language model only reports these
verdicts.
