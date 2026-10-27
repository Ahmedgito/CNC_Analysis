---
status: accepted
date: 2026-10-27
---

# 0011 Measured facts: what a 3D model may and may not be used to state

## Context

A spreadsheet cell and a drawing callout are text someone wrote; a value from a 3D model is a
measurement the app makes. "Use geometry facts you can extract reliably" needs a rule for what
counts as reliable, and for what a model must never be used to answer.

## Decision

- Model values are facts with `confidence="measured"` and a `method` that says how each was
  measured ("6 faces merged from 12; normals point to the axis; probes past both ends are
  outside material"). Values recognised within a tolerance (B-spline faces) or taken from
  surfaces that do not close are `inferred`. Header values (units, dates) are `exact`.
- Reported only when the geometry proves it: diameters and steps, bores, holes (through or
  blind, radial, counterbored), hole patterns (circular only when centred on an axis, otherwise
  grid or row with pitch), the envelope in the part's own frame, chamfers, fillets, and volume
  and area of a closed valid solid.
- Never stated from a model: material, tolerance, surface finish, heat treatment, thread size or
  class, mass or weight. Volume is never multiplied by a textbook density, because that would
  fill a missing field from general knowledge. The prompt and the offline rules engine both
  enforce this, and the cross-check marks these fields "a model does not record this".
- A measured value is not more correct than a written one; the prompt says so.

## Consequences

Answers can cite geometry with an explanation a reviewer can check. Some questions a person might
expect a CAD file to answer (weight, thread class) stay "not in the files" unless another file
states them. Free-form features are not reported as features at all rather than reported badly.
