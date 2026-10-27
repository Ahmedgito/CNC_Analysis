---
status: accepted
date: 2026-10-27
---

# 0002 Schema-agnostic, provenance-first spreadsheet ingestion

## Context

The organisers' sample workbooks already disagree: header on row 1 versus row 4 below banner
rows, "Part No" versus "Item Code", numeric versus text part numbers. The judges' real data
will differ again. The stretch goal is "any part number in the dataset".

## Decision

- Readers preserve every cell faithfully (type, number format, formula and cached value,
  hidden state, comments, merged-range origin) in a reader-independent `RawCell`.
- The header row is found by scoring the first 20 rows; rows above it are kept as banner
  context. A units row under the header is folded into the header text.
- Headers map to 24 canonical fields through a synonym table, then a strict fuzzy match.
  Unknown columns are kept and shown to the LLM under their raw name, never dropped.
- Part numbers are text keys (`2280`, `2280.0`, `"2280"` collide; `2280-A` stays distinct and is
  offered as a suggestion).
- Every cell is stored with its `file!sheet!cell` id, so every citation joins back to a row in
  the `cell` table.

## Consequences

New layouts ingest without code changes (proven by a generated "drift" workbook in the tests).
Heuristics can still misread exotic layouts (key-value blocks); those are listed as stretch.
