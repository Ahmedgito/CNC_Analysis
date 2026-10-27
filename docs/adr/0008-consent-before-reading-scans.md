---
status: accepted
date: 2026-10-27
---

# 0008 Scanned drawings are read by a vision model only after the user agrees

## Context

`3001_gear_blank_scan.pdf` is a raster scan with no text layer. Text extraction finds nothing,
so without OCR or a vision model the app knows nothing about it. Reading it with a vision model
sends page images to an external service, costs a model call, and produces values that cannot
be checked against text in the file. The user decided: tell the user it is a scan, and read it
only if they say to proceed.

## Decision

- Ingest detects scans (images, no extractable text) and marks the drawing `scanned` and not
  `readable`. Source badges, the drawing tab and the record warnings say so.
- When a question needs that drawing, the answer status is `needs_consent`. The answer says the
  drawing is an unread scan, gives what the spreadsheet does state, and carries an action
  `{id: "read_scan", file, label, reply}`. Nothing is sent to a vision model.
- The client sends `action.reply` ("Yes, read the scanned drawing.") as the next message. The
  server recognises an affirmative reply to a pending offer, renders the pages upright at
  130 dpi, reads them with the configured `VisionProvider` (Anthropic API, Claude Code, or a
  static reader in tests), stores the result as facts with `confidence = "vision"`, rebuilds
  cross-checks, and answers the original question. `POST .../read-scan` does the same directly.
- Vision facts are always labelled: dashed chips, a "vision" tag and a warning on the answer.
  They take part in cross-checks like any other fact.
- `cnc reset-drawing <pdf>` re-extracts a drawing from its file, discarding a vision reading.

## Consequences

No image leaves the machine without a yes, and a value read from a scan is never presented as
if it were printed text. A "yes" with no pending offer is just a question. The extra round trip
is the cost, and it is visible: the pipeline stepper shows a "Reading the scanned drawing" step.
