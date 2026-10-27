---
status: accepted
date: 2026-10-27
---

# 0007 Excel-versus-drawing cross-check in code, never by the model

## Context

The sample data plants disagreements (2283: brass in the job card, bronze on the drawing;
Ø50 against Ø48) and agreements hidden behind units (2282 is in inches on the drawing and
millimetres in the workbook; 125 RMS against Ra 3.2). A language model asked to compare free
text will sometimes "correct" one file to match the other, or call 0.375 in and 9.525 mm a
mismatch.

## Decision

- `services/crosscheck.py` compares each field both files state (material, outer diameter,
  bore, length, thickness, holes, thread, tolerance, surface finish) and returns a verdict:
  `agree`, `agree_after_conversion`, `equivalent_by_convention`, `disagree`, `excel_only`,
  `pdf_only` or `not_comparable`, with the fact ids on each side and one plain sentence.
- Units come from the most specific statement available: inline (`Ø6.35 mm`), column header
  (`(mm)`), the row, the sheet banner (`Units: mm unless stated`), the drawing's title block
  or notes. When nothing states a unit, a unit is inferred only if two or more numbers in the
  same cell match the drawing under it, and the sentence says so.
- An ambiguous unit can never produce `disagree`; it becomes `not_comparable`. Unlabelled
  drawing dimensions can confirm a value but never contradict one.
- Surface roughness Ra/RMS/N-grade equivalence is a conventional table, so it is reported as
  `equivalent_by_convention`, not as agreement.
- Verdicts are computed at ingest, stored on the part record, shown in the UI and passed to
  the model, which is told to report them and never to resolve a disagreement.

## Consequences

Disagreements are found the same way every time and can be tested (`tests/unit/test_crosscheck.py`
covers every planted case in both datasets). The model's job is narrowed to phrasing. Fields
outside the compared set are still visible to the model, which may compare them itself; the
system prompt requires it to say that comparison is its own.
