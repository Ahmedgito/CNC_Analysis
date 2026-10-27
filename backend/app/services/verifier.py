"""Programmatic verification of an LLM answer against the record. No LLM involved.

1. Citation check: every cited fact (spreadsheet cell or drawing fact) must exist in the
   supplied record(s) and the quoted value must match the stored value (exactly after
   normalisation, or as a substring of 2+ chars). Failed citations are dropped with a reason.
2. Auto-linking: record values that appear verbatim in the answer but were not cited are added
   as evidence (flagged ``auto_linked``) so every visible fact has a source chip.
3. Number grounding: every number in the answer must appear in a cited fact, the computed
   result, the question, or the part number. Anything else is reported as unsupported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.evidence import Fact
from app.ingestion.cells import normalize_for_match
from app.llm.schemas import EvidenceItem
from app.services.compute import extract_numbers

_MIN_SUBSTRING = 2
_MIN_AUTOLINK = 4
_NULLISH = {"none", "n/a", "na", "-", "--", "nil"}
_ANSWER_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?")


@dataclass(slots=True)
class VerifiedEvidence:
    fact: Fact
    quoted: str
    auto_linked: bool = False


@dataclass(slots=True)
class DroppedEvidence:
    fact_id: str
    quoted: str
    reason: str


@dataclass(slots=True)
class Verification:
    evidence: list[VerifiedEvidence] = field(default_factory=list)
    dropped: list[DroppedEvidence] = field(default_factory=list)
    unsupported_numbers: list[str] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return len(self.evidence) + len(self.dropped)


def _quote_matches(quoted: str, value: str) -> bool:
    q, v = normalize_for_match(quoted), normalize_for_match(value)
    if not q:
        return False
    if q == v:
        return True
    try:
        if float(q) == float(v):
            return True
    except ValueError:
        pass
    return len(q) >= _MIN_SUBSTRING and q in v


def verify_citations(items: list[EvidenceItem], facts: dict[str, Fact]) -> Verification:
    result = Verification()
    seen: set[str] = set()
    for item in items:
        fact = facts.get(item.fact_id.strip())
        if fact is None:
            result.dropped.append(
                DroppedEvidence(
                    item.fact_id, item.quoted_value, "fact id not in this part's record"
                )
            )
            continue
        if not _quote_matches(item.quoted_value, fact.value):
            result.dropped.append(
                DroppedEvidence(
                    item.fact_id,
                    item.quoted_value,
                    f"quoted value does not match the file (it says '{fact.value}')",
                )
            )
            continue
        if fact.fact_id in seen:
            continue
        seen.add(fact.fact_id)
        result.evidence.append(VerifiedEvidence(fact=fact, quoted=item.quoted_value))
    return result


def auto_link(answer: str, verification: Verification, facts: dict[str, Fact]) -> None:
    """Add evidence for record values the answer states verbatim but did not cite."""
    text = normalize_for_match(answer)
    cited_values = {normalize_for_match(e.fact.value) for e in verification.evidence}
    cited_ids = {e.fact.fact_id for e in verification.evidence}
    for fact in facts.values():
        value = normalize_for_match(fact.value)
        if (
            len(value) < _MIN_AUTOLINK
            or value in _NULLISH
            or fact.fact_id in cited_ids
            or value in cited_values
            or fact.canonical == "part_number"
            or fact.stale  # history is shown only when the model chose to cite it
        ):
            continue
        if value in text:
            verification.evidence.append(
                VerifiedEvidence(fact=fact, quoted=fact.value, auto_linked=True)
            )
            cited_values.add(value)
            cited_ids.add(fact.fact_id)


def link_row_numbers(answer: str, verification: Verification, facts: dict[str, Fact]) -> None:
    """Link short numbers (an "Op 20", a quantity) that sit in a group the answer already cites.

    ``auto_link`` skips short values because "20" alone is ambiguous across a whole record.
    Inside a spreadsheet row or a drawing region the answer already relies on, it is not, so
    that fact is added as evidence.
    """
    groups = {e.fact.group for e in verification.evidence}
    if not groups:
        return
    cited_ids = {e.fact.fact_id for e in verification.evidence}
    covered = {
        form
        for e in verification.evidence
        for n in extract_numbers(e.fact.value)
        for form in _number_forms(n)
    }
    for token in _ANSWER_NUMBER_RE.findall(answer):
        forms = _number_forms(float(token)) | {token}
        if forms & covered:
            continue
        for fact in facts.values():
            if fact.group not in groups or fact.fact_id in cited_ids:
                continue
            if forms & {f for n in extract_numbers(fact.value) for f in _number_forms(n)}:
                verification.evidence.append(
                    VerifiedEvidence(fact=fact, quoted=fact.value, auto_linked=True)
                )
                cited_ids.add(fact.fact_id)
                covered |= forms
                break


def _number_forms(value: float) -> set[str]:
    forms = {repr(value)}
    if value == int(value):
        forms.add(str(int(value)))
    forms.add(f"{value:g}")
    return forms


def check_numbers(
    answer: str,
    verification: Verification,
    question: str,
    extra_allowed: list[float] | None = None,
    part_keys: list[str] | None = None,
    source_names: list[str] | None = None,
) -> list[str]:
    allowed: set[str] = set()
    for e in verification.evidence:
        for n in extract_numbers(e.fact.value):
            allowed |= _number_forms(n)
        allowed |= set(_ANSWER_NUMBER_RE.findall(e.fact.value))
        allowed |= set(_ANSWER_NUMBER_RE.findall(e.fact.label))  # "Note 3", "Op No"
        if e.fact.row is not None:
            allowed.add(str(e.fact.row))  # "row 2" style references
        if e.fact.page is not None:
            allowed.add(str(e.fact.page))  # "page 2" style references
    for n in extract_numbers(question):
        allowed |= _number_forms(n)
    for n in extra_allowed or []:
        allowed |= _number_forms(n)
    # Part numbers, and file or sheet names the answer may mention ("the Archive_2025 sheet").
    for key in [*(part_keys or []), *(source_names or [])]:
        allowed |= set(_ANSWER_NUMBER_RE.findall(key))
    unsupported: list[str] = []
    for token in _ANSWER_NUMBER_RE.findall(answer):
        try:
            num = float(token)
        except ValueError:
            continue
        if token in allowed or _number_forms(num) & allowed:
            continue
        if token not in unsupported:
            unsupported.append(token)
    return unsupported
