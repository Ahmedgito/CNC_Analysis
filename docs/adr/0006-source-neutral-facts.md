---
status: accepted
date: 2026-10-27
---

# 0006 One fact model for spreadsheet cells and drawing callouts

## Context

Level 1 cited spreadsheet cells by `cell_id` (`mfg_record_A!Parts!C2`). Level 2 adds PDF
drawings, whose values sit in a title block, numbered notes, dimension callouts and revision
tables rather than in cells. The verifier, the compute engine, the prompt and the client all
keyed on `cell_id`. A second, parallel path for drawings would have doubled every guarantee
the verifier gives.

## Decision

- A source-neutral `Fact` (file, locator, label, canonical field, value, unit, confidence,
  stale flag, plus Excel row/column or PDF page/region/bbox) is the unit of evidence.
- Fact ids keep the Level 1 grammar for cells and extend it for drawings:
  `<stem>!p<page>!<tb|note|dim|rev|text>!<key>`, e.g. `2283_bushing!p1!dim!2` or
  `3003_base_plate!p1!note!3`. A person can find the fact from its id alone.
- `fact_id` replaces `cell_id` in the API. `AliasChoices` keeps answers stored before Level 2
  loading; the evaluation reads either.
- `confidence` is `exact` (printed text), `inferred` (type guessed from shape, such as an
  unlabelled `40`) or `vision` (read from a scan). `stale` marks history: archive sheets,
  superseded rows, older drawing revisions.

## Consequences

The verifier, number grounding and compute engine work unchanged for drawings: a cited value
must match the stored fact exactly, whichever file it came from. The UI renders one chip type
with a source icon and locates either a cell or a box on the rendered page. IGES (Level 3) adds
a third locator kind without touching the answer pipeline.
