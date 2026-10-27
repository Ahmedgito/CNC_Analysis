"""Cheap, deterministic checks before any LLM call."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_QUESTION_CHARS = 1000
_HAS_WORD = re.compile(r"[A-Za-z0-9]")
# A part reference only counts when introduced by a keyword, so "ISO 2768" or "6061-T6" never
# get mistaken for part numbers. Bare numbers are checked against known keys by the caller.
_KEYWORD_PART_RE = re.compile(
    r"\b(?:part|p/n|pn|item|item code|component|part no\.?|part number|#)\s*[:#]?\s*"
    r"(?P<pn>[A-Za-z]{0,4}-?\d{3,}[A-Za-z0-9\-]*)",
    re.I,
)
_BARE_NUMBER_RE = re.compile(r"(?<![\w.\-])(?P<pn>\d{3,}(?:-[A-Za-z0-9]{1,4})?)(?![\w.])")
_INJECTION_RE = re.compile(
    r"ignore (all|any|the|your|previous|prior)\b|disregard (the|your|all|previous)|"
    r"system prompt|you are now|act as|pretend (to|you)|developer mode|jailbreak|"
    r"reveal (your|the) (prompt|instructions|rules)",
    re.I,
)


@dataclass(slots=True)
class GuardResult:
    question: str
    ok: bool
    problem: str | None = None
    keyword_part_refs: list[str] = field(default_factory=list)
    bare_number_refs: list[str] = field(default_factory=list)
    suspected_injection: bool = False


def check_question(raw: str) -> GuardResult:
    question = unicodedata.normalize("NFKC", raw or "").replace(" ", " ").strip()
    question = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", question)
    if not question:
        return GuardResult(question, ok=False, problem="The question is empty.")
    if len(question) > MAX_QUESTION_CHARS:
        return GuardResult(
            question[:MAX_QUESTION_CHARS],
            ok=False,
            problem=f"The question is too long (max {MAX_QUESTION_CHARS} characters). "
            "Please ask one thing at a time.",
        )
    if not _HAS_WORD.search(question):
        return GuardResult(question, ok=False, problem="I couldn't read a question there.")
    keyword_refs = [m.group("pn") for m in _KEYWORD_PART_RE.finditer(question)]
    bare_refs = [m.group("pn") for m in _BARE_NUMBER_RE.finditer(question)]
    return GuardResult(
        question=question,
        ok=True,
        keyword_part_refs=keyword_refs,
        bare_number_refs=[b for b in bare_refs if b not in keyword_refs],
        suspected_injection=bool(_INJECTION_RE.search(question)),
    )
