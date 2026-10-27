---
status: accepted
date: 2026-10-27
---

# 0001 Structured outputs with our own evidence array, verified in code

## Context

The top judging criterion (30%) is answers that match the files and name their source; honesty
(15%) rewards saying "not in the files" over guessing. Anthropic's native citations feature
cannot be combined with structured outputs (the API returns 400), and Groq, our fallback, has
no equivalent. A part record is small (under 2k tokens), so this is a grounding problem, not a
retrieval problem.

## Decision

- Put the whole part record in the prompt as addressable cells (`file!sheet!A1` ids), values
  JSON-encoded with `<` and `>` escaped so cell text cannot forge prompt tags.
- Require one Pydantic schema (`AnswerDraft`) from every provider: status, answer, evidence
  `[{cell_id, quoted_value}]`, optional computation, general-knowledge notes kept separate.
- Verify in code before anything is shown: each citation must exist in this part's record and
  its quoted value must match the stored value. Failed citations are dropped; if none survive,
  re-ask once with the errors, then return "not in the files".
- Auto-link record values the answer states verbatim but did not cite, and flag any number in
  the answer that no cited cell, computed result or the question contains.
- The LLM never does arithmetic: it proposes an expression over cited cells; a whitelisted AST
  evaluator computes it and shows the working.

## Consequences

Citation validity is guaranteed by construction, identical across providers. The cost is one
extra LLM call in the rare case where every citation fails.
